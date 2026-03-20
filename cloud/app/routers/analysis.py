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
    FeasibilityScoreOut,
    RecommendationOut,
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


@router.post("/run", response_model=AnalysisResultOut)
def run_analysis(payload: AnalysisRequest, db: Session = Depends(get_db)):
    """Run a strategic analysis using the Hivemind Core engine.
    
    This endpoint implements the full Hivemind workflow:
    1. Creates theory network units (dynamic if density specified)
    2. Units generate initial solutions
    3. Units critique and revise each other's solutions
    4. Monitor aggregates similar solutions
    5. Practicality network evaluates solutions
    6. Veto mechanism can restart entire process if needed
    """
    # Resolve agents by use_case_profile / decision_type when provided
    theory_ids, practicality_ids = _resolve_agents_by_profile_and_decision(
        db,
        payload.use_case_profile,
        payload.decision_type,
        list(payload.enabled_theory_agent_ids),
        list(payload.enabled_practicality_agent_ids),
    )

    # Allow running with density-based dynamic units OR specified agents
    if not theory_ids and payload.theory_network_density is None:
        raise HTTPException(
            status_code=400,
            detail="Either theory agents or theory_network_density must be specified (or set decision_type / use_case_profile with matching data)",
        )

    # Build context from client-cleared text
    context: list[ContextItem] = [
        ContextItem(type=ContextType.TEXT, content=text, source="client")
        for text in (payload.context_document_texts or [])
        if (text and isinstance(text, str) and text.strip())
    ]

    # Create engine and run analysis
    engine = create_engine(db)
    start = time.time()

    hivemind_input = HivemindInput(
        query=payload.problem_statement,
        context=context,
        theory_agent_ids=theory_ids,
        practicality_agent_ids=practicality_ids,
        sufficiency_value=payload.sufficiency_value,
        feasibility_threshold=payload.feasibility_threshold,
        theory_network_density=payload.theory_network_density,
        max_veto_restarts=payload.max_veto_restarts,
        similarity_threshold=payload.similarity_threshold,
        revision_strength=payload.revision_strength,
        practicality_criticality=payload.practicality_criticality,
    )

    output = engine.analyze(hivemind_input)
    
    # Convert to response format
    recommendations = [_recommendation_to_out(rec) for rec in output.recommendations]
    vetoed = [_recommendation_to_out(rec) for rec in output.vetoed_solutions]
    audit_trail = [_audit_event_to_dict(event) for event in output.audit_trail]
    
    # Store result
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

    hivemind_input = HivemindInput(
        query=payload.problem_statement,
        context=context,
        theory_agent_ids=theory_ids,
        practicality_agent_ids=practicality_ids,
        sufficiency_value=payload.sufficiency_value,
        feasibility_threshold=payload.feasibility_threshold,
        theory_network_density=payload.theory_network_density,
        max_veto_restarts=payload.max_veto_restarts,
        similarity_threshold=payload.similarity_threshold,
        revision_strength=payload.revision_strength,
        practicality_criticality=payload.practicality_criticality,
    )

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
