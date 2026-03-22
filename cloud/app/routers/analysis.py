"""
Analysis endpoints - thin wrapper around Hivemind Core engine.
"""
from __future__ import annotations

import collections
import dataclasses
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.deps import get_any_authenticated, get_db
from app.engine import create_engine
from app.models.agent import AgentDefinition
from app.models.analysis import AnalysisResult
from app.models.knowledge_base import KnowledgeBase
from app.models.scraped_source import ScrapedSource
from app.schemas.analysis import (
    AnalysisRequest,
    AnalysisResultOut,
    BudgetUsageOut,
    FeasibilityScoreOut,
    RecommendationOut,
    RepairStatsOut,
)
from hivemind_core import HivemindInput
from hivemind_core.types import ContextItem, ContextType

router = APIRouter(prefix="/analysis", tags=["analysis"])


# ---------------------------------------------------------------------------
# Lightweight per-user rate limiter (no external dependency)
# ---------------------------------------------------------------------------

_RATE_LIMIT_MAX = 10           # max requests per window
_RATE_LIMIT_WINDOW_S = 60      # window size in seconds
_rate_lock = threading.Lock()
_rate_buckets: dict[str, collections.deque] = {}


def _check_rate_limit(user_id: str) -> None:
    """Raise 429 if the user exceeds _RATE_LIMIT_MAX requests in the window."""
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_buckets.setdefault(user_id, collections.deque())
        # Evict timestamps outside the window
        while bucket and bucket[0] < now - _RATE_LIMIT_WINDOW_S:
            bucket.popleft()
        if len(bucket) >= _RATE_LIMIT_MAX:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {_RATE_LIMIT_MAX} analysis requests per {_RATE_LIMIT_WINDOW_S}s.",
            )
        bucket.append(now)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def _assert_analysis_access(analysis: AnalysisResult, current_user: dict) -> None:
    """Enforce analysis ownership for client-role users."""
    if current_user.get("role") == "operator":
        return

    current_sub = str(current_user.get("sub") or "")
    if not current_sub:
        raise HTTPException(status_code=403, detail="Invalid token subject")

    request_data = analysis.request if isinstance(analysis.request, dict) else {}
    owner_sub = request_data.get("_owner_sub")
    if isinstance(owner_sub, str) and owner_sub == current_sub:
        return

    if analysis.client_id and analysis.client_id == current_sub:
        return

    # Hide existence for unauthorized users
    raise HTTPException(status_code=404, detail="Analysis not found")


def _resolve_agents_by_profile_and_decision(
    db: Session,
    use_case_profile: str | None,
    decision_type: str | None,
    enabled_theory_agent_ids: list[str],
    enabled_practicality_agent_ids: list[str],
) -> tuple[list[str], list[str]]:
    """Resolve theory/practicality agent IDs from use_case_profile and decision_type when provided."""
    theory_ids = list(enabled_theory_agent_ids)
    practicality_ids = list(enabled_practicality_agent_ids)

    if use_case_profile:
        agents = (
            db.query(AgentDefinition)
            .filter(
                AgentDefinition.network_type == "practicality",
                AgentDefinition.status == "published",
                AgentDefinition.use_case_profile == use_case_profile,
            )
            .all()
        )
        practicality_ids = [a.id for a in agents]

    if decision_type:
        kbs = (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.decision_types.contains([decision_type]))
            .all()
        )
        kb_ids = {kb.id for kb in kbs}
        theory_agents = (
            db.query(AgentDefinition)
            .filter(
                AgentDefinition.network_type == "theory",
                AgentDefinition.status == "published",
            )
            .all()
        )
        theory_ids = [
            a.id
            for a in theory_agents
            if (a.knowledge_base_ids or []) and any(kid in kb_ids for kid in (a.knowledge_base_ids or []))
        ]

    return theory_ids, practicality_ids


def _recommendation_to_out(rec) -> RecommendationOut:
    """Convert a Recommendation to the output schema."""
    feasibility_scores = [
        FeasibilityScoreOut(
            agent_id=fs.agent_id,
            agent_name=fs.agent_name,
            score=fs.score,
            risks=fs.risks,
            challenges=fs.challenges,
            mitigations=fs.mitigations,
            reasoning=fs.reasoning,
        )
        for fs in (rec.feasibility_scores or [])
    ]

    return RecommendationOut(
        id=rec.id,
        title=rec.title,
        content=rec.content,
        reasoning=rec.reasoning,
        contributing_agents=rec.contributing_agents,
        retrieved_chunk_ids=rec.retrieved_chunk_ids,
        feasibility_scores=feasibility_scores,
        average_feasibility=rec.average_feasibility,
        status=getattr(rec, "status", "approved"),
        repair_history=getattr(rec, "repair_history", []),
        partial_scoring=getattr(rec, "partial_scoring", False),
    )


def _audit_event_to_dict(event) -> dict[str, Any]:
    """Convert an AuditEvent to a dict for JSON response."""
    return {
        "event_type": event.event_type,
        "agent_id": event.agent_id,
        "retrieved_chunk_ids": event.retrieved_chunk_ids,
        "input_tokens": event.input_tokens,
        "output_tokens": event.output_tokens,
        "latency_ms": event.latency_ms,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "details": event.details,
    }


def _build_hivemind_input(
    payload: AnalysisRequest,
    theory_ids: list[str],
    practicality_ids: list[str],
    context: list[ContextItem],
) -> HivemindInput:
    """Map AnalysisRequest to HivemindInput with backward compatibility."""
    return HivemindInput(
        query=payload.problem_statement,
        context=context,
        theory_agent_ids=theory_ids,
        practicality_agent_ids=practicality_ids,
        analysis_mode=payload.analysis_mode,
        effort_level=payload.effort_level,
        sufficiency_value=payload.sufficiency_value,
        feasibility_threshold=payload.feasibility_threshold,
        max_total_llm_calls=payload.max_total_llm_calls,
        max_total_tokens=payload.max_total_tokens,
        max_wallclock_ms=payload.max_wallclock_ms,
        max_repair_iterations=payload.max_repair_iterations,
        theory_network_density=payload.theory_network_density,
        max_veto_restarts=payload.max_veto_restarts,
        similarity_threshold=payload.similarity_threshold,
        revision_strength=payload.revision_strength,
        practicality_criticality=payload.practicality_criticality,
    )


def _budget_usage_to_out(bu) -> BudgetUsageOut:
    return BudgetUsageOut(
        llm_calls=bu.llm_calls,
        input_tokens=bu.input_tokens,
        output_tokens=bu.output_tokens,
        total_tokens=bu.total_tokens,
        wallclock_ms=bu.wallclock_ms,
    )


def _repair_stats_to_out(rs) -> RepairStatsOut:
    return RepairStatsOut(
        recommendations_repaired=rs.recommendations_repaired,
        recommendations_recovered=rs.recommendations_recovered,
        recommendations_failed_after_repairs=rs.recommendations_failed_after_repairs,
        total_repair_iterations=rs.total_repair_iterations,
    )


@router.post("/run", response_model=AnalysisResultOut)
def run_analysis(payload: AnalysisRequest, db: Session = Depends(get_db), _client: dict = Depends(get_any_authenticated)):
    """Run a strategic analysis using the Hivemind Core engine."""
    _check_rate_limit(_client["sub"])
    theory_ids, practicality_ids = _resolve_agents_by_profile_and_decision(
        db,
        payload.use_case_profile,
        payload.decision_type,
        list(payload.enabled_theory_agent_ids),
        list(payload.enabled_practicality_agent_ids),
    )

    if not theory_ids and payload.theory_network_density is None:
        raise HTTPException(
            status_code=400,
            detail="Either theory agents or theory_network_density must be specified (or set decision_type / use_case_profile with matching data)",
        )

    context: list[ContextItem] = [
        ContextItem(type=ContextType.TEXT, content=text, source="client")
        for text in (payload.context_document_texts or [])
        if (text and isinstance(text, str) and text.strip())
    ]

    # Include completed scraped web sources as context
    scraped = db.query(ScrapedSource).filter(
        ScrapedSource.status == "completed",
        ScrapedSource.scraped_text.isnot(None),
    ).all()
    for s in scraped:
        if s.scraped_text and s.scraped_text.strip():
            context.append(ContextItem(
                type=ContextType.TEXT,
                content=f"[Web source: {s.url_or_query}]\n{s.scraped_text}",
                source="web_scrape",
            ))

    engine = create_engine(db)
    start = time.time()

    hivemind_input = _build_hivemind_input(payload, theory_ids, practicality_ids, context)
    output = engine.analyze(hivemind_input)

    recommendations = [_recommendation_to_out(rec) for rec in output.recommendations]
    vetoed = [_recommendation_to_out(rec) for rec in output.vetoed_solutions]
    audit_trail = [_audit_event_to_dict(event) for event in output.audit_trail]

    owner_sub = str(_client.get("sub") or "")
    request_payload = payload.model_dump()
    request_payload["_owner_sub"] = owner_sub
    request_payload["_owner_role"] = _client.get("role")
    owner_client_id = owner_sub if _client.get("role") == "client" and _is_uuid(owner_sub) else None

    analysis = AnalysisResult(
        client_id=owner_client_id,
        request=request_payload,
        recommendations=[r.model_dump() for r in recommendations],
        vetoed_solutions=[v.model_dump() for v in vetoed],
        debate_rounds=output.debate_rounds,
        duration=int(time.time() - start),
        total_tokens=output.total_tokens,
        audit_trail=audit_trail,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return AnalysisResultOut(
        id=analysis.id,
        recommendations=recommendations,
        vetoed_solutions=vetoed,
        audit_trail=audit_trail,
        debate_rounds=output.debate_rounds,
        veto_restarts=output.veto_restarts,
        theory_units_created=output.theory_units_created,
        total_tokens=output.total_tokens,
        duration_ms=output.duration_ms,
        termination_reason=output.termination_reason,
        budget_usage=_budget_usage_to_out(output.budget_usage),
        mode_used=output.mode_used,
        repair_stats=_repair_stats_to_out(output.repair_stats),
    )


@router.post("/run/stream")
async def run_analysis_streaming(payload: AnalysisRequest, db: Session = Depends(get_db), _client: dict = Depends(get_any_authenticated)):
    """Run analysis with streaming progress updates."""
    _check_rate_limit(_client["sub"])
    theory_ids, practicality_ids = _resolve_agents_by_profile_and_decision(
        db,
        payload.use_case_profile,
        payload.decision_type,
        list(payload.enabled_theory_agent_ids),
        list(payload.enabled_practicality_agent_ids),
    )
    if not theory_ids and payload.theory_network_density is None:
        raise HTTPException(
            status_code=400,
            detail="Either theory agents or theory_network_density must be specified (or set decision_type / use_case_profile with matching data)",
        )

    context: list[ContextItem] = [
        ContextItem(type=ContextType.TEXT, content=text, source="client")
        for text in (payload.context_document_texts or [])
        if (text and isinstance(text, str) and text.strip())
    ]

    # Include completed scraped web sources as context
    scraped = db.query(ScrapedSource).filter(
        ScrapedSource.status == "completed",
        ScrapedSource.scraped_text.isnot(None),
    ).all()
    for s in scraped:
        if s.scraped_text and s.scraped_text.strip():
            context.append(ContextItem(
                type=ContextType.TEXT,
                content=f"[Web source: {s.url_or_query}]\n{s.scraped_text}",
                source="web_scrape",
            ))

    engine = create_engine(db)
    hivemind_input = _build_hivemind_input(payload, theory_ids, practicality_ids, context)

    import json

    def _serialize(obj):
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_serialize(v) for v in obj]
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        if hasattr(obj, 'value'):
            return obj.value
        return obj

    def generate():
        for event in engine.analyze_streaming(hivemind_input):
            yield f"data: {json.dumps(_serialize(event))}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )


@router.get("/{analysis_id}")
def get_analysis(analysis_id: str, db: Session = Depends(get_db), _client: dict = Depends(get_any_authenticated)):
    """Get a previous analysis by ID."""
    analysis = db.query(AnalysisResult).filter(AnalysisResult.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    _assert_analysis_access(analysis, _client)
    return analysis


@router.get("/{analysis_id}/audit")
def get_audit(analysis_id: str, db: Session = Depends(get_db), _client: dict = Depends(get_any_authenticated)):
    """Get the audit trail for an analysis."""
    analysis = db.query(AnalysisResult).filter(AnalysisResult.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    _assert_analysis_access(analysis, _client)
    return {"audit_trail": analysis.audit_trail or []}
