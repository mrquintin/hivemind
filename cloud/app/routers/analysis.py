"""
Analysis endpoints - thin wrapper around Hivemind Core engine.
"""
from __future__ import annotations

import dataclasses
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.deps import get_db
from app.engine import create_engine
from app.models.agent import AgentDefinition
from app.models.analysis import AnalysisResult
from app.models.knowledge_base import KnowledgeBase
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
def run_analysis(payload: AnalysisRequest, db: Session = Depends(get_db)):
    """Run a strategic analysis using the Hivemind Core engine."""
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

    engine = create_engine(db)
    start = time.time()

    hivemind_input = _build_hivemind_input(payload, theory_ids, practicality_ids, context)
    output = engine.analyze(hivemind_input)

    recommendations = [_recommendation_to_out(rec) for rec in output.recommendations]
    vetoed = [_recommendation_to_out(rec) for rec in output.vetoed_solutions]
    audit_trail = [_audit_event_to_dict(event) for event in output.audit_trail]

    analysis = AnalysisResult(
        request=payload.model_dump(),
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
async def run_analysis_streaming(payload: AnalysisRequest, db: Session = Depends(get_db)):
    """Run analysis with streaming progress updates."""
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
def get_analysis(analysis_id: str, db: Session = Depends(get_db)):
    """Get a previous analysis by ID."""
    analysis = db.query(AnalysisResult).filter(AnalysisResult.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@router.get("/{analysis_id}/audit")
def get_audit(analysis_id: str, db: Session = Depends(get_db)):
    """Get the audit trail for an analysis."""
    analysis = db.query(AnalysisResult).filter(AnalysisResult.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"audit_trail": analysis.audit_trail or []}
