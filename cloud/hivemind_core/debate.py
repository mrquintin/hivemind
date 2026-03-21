"""Multi-agent debate engine for Hivemind core.

Supports two execution modes:
- simple: Fast/cheap baseline. No peer critique rounds, at most 1 repair iteration.
- full: Deeper synthesis with bounded complexity, debate rounds, and per-recommendation repair.

Both streaming and non-streaming paths call the same core subroutines to prevent drift.
"""
from __future__ import annotations

import json
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Generator

from hivemind_core.agents import execute_agent
from hivemind_core.types import (
    Action,
    ActionType,
    AgentDefinition,
    AggregatedSolution,
    AuditEvent,
    BudgetExhausted,
    BudgetUsage,
    Critique,
    DynamicTheoryUnit,
    EFFORT_DEFAULTS,
    FeasibilityScore,
    HivemindInput,
    HivemindOutput,
    LLMInterface,
    NetworkType,
    RagConfig,
    Recommendation,
    RecommendationStatus,
    RepairStats,
    StorageInterface,
    TerminationReason,
    TheoryUnitSolution,
    VectorStoreInterface,
)


# ---------------------------------------------------------------------------
# Audit Event Helper
# ---------------------------------------------------------------------------


def _make_audit_details(
    mode: str,
    run_id: str,
    round: int = 0,
    **extra: Any,
) -> dict[str, Any]:
    """Build audit event details with required base fields."""
    base = {
        "event_version": "v2",
        "mode": mode,
        "round": round,
        "run_id": run_id,
        "timestamp_iso": datetime.now(timezone.utc).isoformat() + "Z",
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Response Parsing Helpers
# ---------------------------------------------------------------------------


def _parse_solution_reasoning(text: str) -> tuple[str, str]:
    """Split an LLM response into (solution, reasoning) based on labelled sections."""
    import re
    sol_match = re.search(r"(?i)SOLUTION\s*:\s*([\s\S]*?)(?=REASONING\s*:|$)", text)
    rea_match = re.search(r"(?i)REASONING\s*:\s*([\s\S]*)", text)
    solution = sol_match.group(1).strip() if sol_match else text.strip()
    reasoning = rea_match.group(1).strip() if rea_match else text.strip()
    return solution, reasoning


# ---------------------------------------------------------------------------
# Budget Guard
# ---------------------------------------------------------------------------


class _BudgetGuard:
    """Centralized budget enforcement. Check before every LLM call."""

    def __init__(self, input_data: HivemindInput):
        self.max_llm_calls = input_data.get_effective_max_llm_calls()
        self.max_total_tokens = input_data.max_total_tokens
        self.max_wallclock_ms = input_data.max_wallclock_ms
        self.usage = BudgetUsage()
        self._start_ms = int(time.time() * 1000)

    def check(self) -> None:
        """Raise BudgetExhausted if any ceiling is exceeded."""
        self.usage.wallclock_ms = int(time.time() * 1000) - self._start_ms
        if self.usage.llm_calls >= self.max_llm_calls:
            raise BudgetExhausted(f"LLM call limit reached ({self.max_llm_calls})")
        if self.max_total_tokens is not None and self.usage.total_tokens >= self.max_total_tokens:
            raise BudgetExhausted(f"Token limit reached ({self.max_total_tokens})")
        if self.max_wallclock_ms is not None and self.usage.wallclock_ms >= self.max_wallclock_ms:
            raise BudgetExhausted(f"Wall-clock limit reached ({self.max_wallclock_ms}ms)")

    def record_call(self, response: dict[str, Any]) -> None:
        """Record an LLM call's token usage."""
        self.usage.llm_calls += 1
        inp = response.get("input_tokens", 0)
        out = response.get("output_tokens", 0)
        self.usage.input_tokens += inp
        self.usage.output_tokens += out
        self.usage.total_tokens += inp + out

    def record_agent_call(self, result) -> None:
        """Record an agent execution's token usage."""
        self.usage.llm_calls += 1
        inp = result.input_tokens or 0
        out = result.output_tokens or 0
        self.usage.input_tokens += inp
        self.usage.output_tokens += out
        self.usage.total_tokens += inp + out

    def finalize(self) -> BudgetUsage:
        """Return final usage snapshot."""
        self.usage.wallclock_ms = int(time.time() * 1000) - self._start_ms
        return BudgetUsage(
            llm_calls=self.usage.llm_calls,
            input_tokens=self.usage.input_tokens,
            output_tokens=self.usage.output_tokens,
            total_tokens=self.usage.total_tokens,
            wallclock_ms=self.usage.wallclock_ms,
        )


# ---------------------------------------------------------------------------
# Stagnation Detector
# ---------------------------------------------------------------------------


class _StagnationDetector:
    """Detect when debate rounds stop making progress."""

    def __init__(self, window: int, min_improvement: int):
        self.window = window
        self.min_improvement = min_improvement
        self._history: list[int] = []

    def record(self, aggregated_count: int) -> None:
        self._history.append(aggregated_count)

    def is_stagnant(self) -> bool:
        if len(self._history) < self.window + 1:
            return False
        recent = self._history[-(self.window + 1):]
        improvement = recent[0] - recent[-1]
        return improvement < self.min_improvement


# ---------------------------------------------------------------------------
# Dynamic Theory Unit Creation (based on density value)
# ---------------------------------------------------------------------------


def _get_document_token_counts(
    storage: StorageInterface,
    knowledge_base_ids: list[str],
) -> dict[str, int]:
    results = storage.get_documents_for_knowledge_bases(knowledge_base_ids)
    return {doc["document_id"]: doc["token_count"] for doc in results}


def _create_dynamic_units(
    density_value: int,
    all_document_ids: list[str],
    document_tokens: dict[str, int],
) -> list[DynamicTheoryUnit]:
    if not all_document_ids or not document_tokens:
        return []

    units: list[DynamicTheoryUnit] = []
    remaining_docs = list(all_document_ids)
    unit_num = 1

    while remaining_docs:
        unit = DynamicTheoryUnit(
            id=f"dynamic-unit-{unit_num}",
            name=f"Theory Unit {unit_num}",
            assigned_document_ids=[],
            total_tokens=0,
        )

        for doc_id in remaining_docs[:]:
            doc_token_count = document_tokens.get(doc_id, 1000)
            if unit.total_tokens + doc_token_count <= density_value * 1.2 or not unit.assigned_document_ids:
                unit.assigned_document_ids.append(doc_id)
                unit.total_tokens += doc_token_count
                remaining_docs.remove(doc_id)
            if unit.total_tokens >= density_value:
                break

        units.append(unit)
        unit_num += 1

    return units


def _dynamic_unit_to_agent(
    unit: DynamicTheoryUnit,
    knowledge_base_ids: list[str],
) -> AgentDefinition:
    return AgentDefinition(
        id=unit.id,
        name=unit.name,
        network_type=NetworkType.THEORY,
        description=f"Dynamically created theory unit with {len(unit.assigned_document_ids)} documents",
        framework=unit.framework,
        principles=unit.principles,
        analytical_style="comprehensive",
        knowledge_base_ids=knowledge_base_ids,
        document_ids=unit.assigned_document_ids,
        rag_config=RagConfig(chunks_to_retrieve=10, similarity_threshold=0.3),
        status="published",
    )


# ---------------------------------------------------------------------------
# Critique and Revision Prompts
# ---------------------------------------------------------------------------


def _create_critique_prompt(
    solution: TheoryUnitSolution,
    critic_framework: str,
) -> str:
    return f"""You are analyzing a strategic solution proposed by another analyst.

PROPOSED SOLUTION:
{solution.solution}

REASONING PROVIDED:
{solution.reasoning}

Using your analytical framework ({critic_framework}), provide a critique of this solution:

1. STRENGTHS: What aspects of this solution are well-reasoned?
2. WEAKNESSES: What gaps or flaws do you identify?
3. SUGGESTIONS: What specific improvements would strengthen this solution?

Be constructive but rigorous. Focus on substantive strategic issues, not minor details."""


def _parse_critique_response(text: str) -> tuple[list[str], list[str], list[str]]:
    import re

    def _extract_section(heading: str) -> list[str]:
        pattern = rf"(?i){heading}\s*:?\s*\n([\s\S]*?)(?=\n\s*(?:STRENGTHS|WEAKNESSES|SUGGESTIONS|$))"
        m = re.search(pattern, text)
        if not m:
            return []
        block = m.group(1)
        items = re.findall(r"[-\u2022*]\s*(.+)", block)
        return [item.strip() for item in items if item.strip()]

    return _extract_section("STRENGTHS"), _extract_section("WEAKNESSES"), _extract_section("SUGGESTIONS")


def _create_revision_prompt(
    original_solution: TheoryUnitSolution,
    critiques: list[Critique],
    revision_strength: float = 0.5,
) -> str:
    critique_text = "\n\n".join([
        f"CRITIQUE FROM UNIT {c.source_unit_id}:\n"
        f"Strengths: {', '.join(c.strengths) if c.strengths else 'None noted'}\n"
        f"Weaknesses: {', '.join(c.weaknesses) if c.weaknesses else 'None noted'}\n"
        f"Suggestions: {', '.join(c.suggestions) if c.suggestions else 'None provided'}\n"
        f"Full critique: {c.critique_text}"
        for c in critiques
    ])

    strength_pct = int(revision_strength * 100)

    return f"""You previously proposed this solution:

ORIGINAL SOLUTION:
{original_solution.solution}

ORIGINAL REASONING:
{original_solution.reasoning}

You have received the following critiques from other analysts:

{critique_text}

Revision strength is {strength_pct}% — 0% means keep your original nearly intact, 100% means aggressively rewrite in response to feedback.

Revise your solution taking into account all the critiques received. Your revised solution should:
1. Address the valid weaknesses identified
2. Incorporate useful suggestions
3. Maintain the strengths of your original approach
4. Provide updated reasoning that explains how you addressed the feedback

Provide your REVISED SOLUTION and UPDATED REASONING."""


# ---------------------------------------------------------------------------
# Monitor v2: Three-Stage Clustering Pipeline
# ---------------------------------------------------------------------------


def _get_embedding_model():
    """Lazy-load the sentence-transformers model (cached after first call)."""
    if not hasattr(_get_embedding_model, "_model"):
        from sentence_transformers import SentenceTransformer
        _get_embedding_model._model = SentenceTransformer("all-MiniLM-L6-v2")
    return _get_embedding_model._model


def _compute_embedding_similarity(
    solution1: TheoryUnitSolution,
    solution2: TheoryUnitSolution,
) -> float:
    """Stage 1: Compute embedding cosine similarity between two solutions."""
    try:
        model = _get_embedding_model()
        embeddings = model.encode([solution1.solution, solution2.solution])
        from numpy import dot
        from numpy.linalg import norm
        a, b = embeddings[0], embeddings[1]
        cosine = float(dot(a, b) / (norm(a) * norm(b) + 1e-10))
        return max(0.0, min(1.0, cosine))
    except Exception:
        return 0.5


def _llm_adjudicate_similarity(
    llm: LLMInterface,
    sol1: TheoryUnitSolution,
    sol2: TheoryUnitSolution,
    budget: _BudgetGuard,
) -> dict[str, Any]:
    """Stage 2: LLM classifier for borderline similarity pairs.

    Returns {"same_intent": bool, "confidence": float, "rationale": str}.
    Falls back to {"same_intent": False, ...} on parse failure.
    """
    try:
        budget.check()
    except BudgetExhausted:
        return {"same_intent": False, "confidence": 0.0, "rationale": "budget_exhausted"}

    prompt = f"""Compare these two strategic solutions and determine if they have the same core intent.

SOLUTION A:
{sol1.solution[:500]}

SOLUTION B:
{sol2.solution[:500]}

Respond with ONLY valid JSON (no other text):
{{"same_intent": true/false, "confidence": 0.0-1.0, "rationale": "max 300 chars"}}"""

    response = llm.call(
        system_prompt="You are a solution similarity classifier. Output only JSON.",
        user_prompt=prompt,
        max_tokens=200,
    )
    budget.record_call(response)

    content = response.get("content", "")
    try:
        # Try to extract JSON from the response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(content[start:end])
            return {
                "same_intent": bool(parsed.get("same_intent", False)),
                "confidence": float(parsed.get("confidence", 0.0)),
                "rationale": str(parsed.get("rationale", ""))[:300],
            }
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    # F1: Fallback to conservative "distinct" decision
    return {"same_intent": False, "confidence": 0.0, "rationale": "parse_fallback"}


def cluster_solutions_monitor_v2(
    llm: LLMInterface,
    solutions: list[TheoryUnitSolution],
    budget: _BudgetGuard,
    similarity_threshold: float = 0.65,
    threshold_low: float = 0.55,
    threshold_high: float = 0.80,
    *,
    mode: str = "",
    run_id: str = "",
) -> tuple[list[AggregatedSolution], list[AuditEvent]]:
    """Three-stage clustering pipeline (Monitor v2).

    Stage 1: Embedding cosine for candidate neighbors.
    Stage 2: LLM adjudication for borderline pairs [threshold_low, threshold_high].
    Stage 3: Canonical form merge with contradiction check.

    Returns (aggregated_solutions, audit_events).
    """
    if not solutions:
        return [], []

    audit_events: list[AuditEvent] = []
    n = len(solutions)

    # Stage 1: Compute pairwise embedding similarities
    pairwise_scores: dict[tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            score = _compute_embedding_similarity(solutions[i], solutions[j])
            pairwise_scores[(i, j)] = score

    # Stage 2: LLM adjudication for borderline pairs
    adjudications: dict[tuple[int, int], dict[str, Any]] = {}
    for (i, j), score in pairwise_scores.items():
        if score >= threshold_high:
            # Definitely similar — skip LLM call
            adjudications[(i, j)] = {"same_intent": True, "confidence": score, "rationale": "high_embedding"}
        elif score < threshold_low:
            # Definitely distinct — skip LLM call
            adjudications[(i, j)] = {"same_intent": False, "confidence": 1.0 - score, "rationale": "low_embedding"}
        else:
            # Borderline — use LLM classifier
            result = _llm_adjudicate_similarity(llm, solutions[i], solutions[j], budget)
            adjudications[(i, j)] = result
            if result.get("rationale") == "parse_fallback":
                audit_events.append(AuditEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="monitor_parse_fallback",
                    details=_make_audit_details(
                        mode, run_id,
                        solution_i=solutions[i].unit_id,
                        solution_j=solutions[j].unit_id,
                        embedding_score=score,
                    ),
                ))

    # Build adjacency for clustering
    assigned = set()
    clusters: list[list[int]] = []

    for i in range(n):
        if i in assigned:
            continue
        cluster = [i]
        assigned.add(i)
        for j in range(n):
            if j in assigned or j == i:
                continue
            key = (min(i, j), max(i, j))
            adj = adjudications.get(key, {})
            emb_score = pairwise_scores.get(key, 0.0)
            # Merge if same_intent or embedding above threshold
            if adj.get("same_intent", False) or emb_score >= threshold_high:
                cluster.append(j)
                assigned.add(j)
        clusters.append(cluster)

    # Stage 3: Convert clusters to AggregatedSolutions with evidence
    aggregated: list[AggregatedSolution] = []
    for cluster_idx, member_indices in enumerate(clusters):
        cluster_solutions = [solutions[i] for i in member_indices]
        cluster_id = str(uuid.uuid4())

        # Build cluster evidence for audit
        member_pairs = []
        for a_idx in member_indices:
            for b_idx in member_indices:
                if a_idx < b_idx:
                    key = (a_idx, b_idx)
                    member_pairs.append({
                        "solution_a": solutions[a_idx].unit_id,
                        "solution_b": solutions[b_idx].unit_id,
                        "embedding_score": pairwise_scores.get(key, 0.0),
                        "adjudication": adjudications.get(key, {}),
                    })

        cluster_confidence = 0.5
        if len(member_indices) > 1:
            confidences = []
            for a_idx in member_indices:
                for b_idx in member_indices:
                    if a_idx < b_idx:
                        key = (a_idx, b_idx)
                        emb = pairwise_scores.get(key, 0.5)
                        adj_conf = adjudications.get(key, {}).get("confidence", 0.5)
                        confidences.append((emb + adj_conf) / 2)
            if confidences:
                cluster_confidence = sum(confidences) / len(confidences)

        evidence = {
            "cluster_id": cluster_id,
            "member_solution_ids": [solutions[i].unit_id for i in member_indices],
            "pairwise_scores": member_pairs,
            "cluster_confidence": cluster_confidence,
        }

        if len(cluster_solutions) == 1:
            sol = cluster_solutions[0]
            agg = AggregatedSolution(
                id=cluster_id,
                merged_solution=sol.solution,
                contributing_units=[sol.unit_id],
                justifications=[sol.reasoning],
                confidence_score=0.5,
                retrieved_chunk_ids=sol.retrieved_chunk_ids,
                cluster_evidence=evidence,
            )
        else:
            agg = _merge_solution_cluster(llm, cluster_solutions, budget)
            agg.id = cluster_id
            agg.cluster_evidence = evidence
            agg.confidence_score = cluster_confidence

        aggregated.append(agg)

    # Emit monitor audit event
    audit_events.append(AuditEvent(
        timestamp=datetime.now(timezone.utc),
        event_type="monitor_v2_clustering",
        details=_make_audit_details(
            mode, run_id,
            total_solutions=n,
            clusters_formed=len(clusters),
            llm_adjudications=sum(
                1 for adj in adjudications.values()
                if adj.get("rationale") not in ("high_embedding", "low_embedding")
            ),
        ),
    ))

    return aggregated, audit_events


def _extract_canonical_form(
    llm: LLMInterface,
    solution: TheoryUnitSolution,
    budget: _BudgetGuard,
) -> dict[str, Any]:
    """Extract canonical form from a solution. Returns structured dict.

    On parse failure, falls back to raw solution text as objective.
    """
    try:
        budget.check()
    except BudgetExhausted:
        return {"objective": solution.solution[:500], "mechanism": "", "dependencies": [], "key_constraints": [], "expected_outcomes": []}

    prompt = f"""Extract the canonical strategic form from this solution. Respond with ONLY valid JSON.

SOLUTION:
{solution.solution[:800]}

Output this exact JSON structure:
{{
  "objective": "the primary strategic goal in one sentence",
  "mechanism": "the approach or method to achieve the objective",
  "dependencies": ["dependency 1", "dependency 2"],
  "key_constraints": ["constraint 1", "constraint 2"],
  "expected_outcomes": ["outcome 1", "outcome 2"]
}}"""

    response = llm.call(
        system_prompt="You are a strategic analyst. Extract structured canonical form. Output only JSON.",
        user_prompt=prompt,
        max_tokens=500,
    )
    budget.record_call(response)

    content = response.get("content", "")
    try:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(content[start:end])
            return {
                "objective": str(parsed.get("objective", ""))[:500],
                "mechanism": str(parsed.get("mechanism", ""))[:500],
                "dependencies": [str(d)[:200] for d in parsed.get("dependencies", [])][:10],
                "key_constraints": [str(c)[:200] for c in parsed.get("key_constraints", [])][:10],
                "expected_outcomes": [str(o)[:200] for o in parsed.get("expected_outcomes", [])][:10],
            }
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        pass

    # Fallback: raw solution as objective
    return {"objective": solution.solution[:500], "mechanism": "", "dependencies": [], "key_constraints": [], "expected_outcomes": []}


def _detect_contradiction(
    llm: LLMInterface,
    form_a: dict[str, Any],
    form_b: dict[str, Any],
    budget: _BudgetGuard,
) -> bool:
    """Return True if two canonical forms have contradictory objectives/mechanisms."""
    obj_a = form_a.get("objective", "")
    obj_b = form_b.get("objective", "")
    mech_a = form_a.get("mechanism", "")
    mech_b = form_b.get("mechanism", "")

    # If objectives/mechanisms are identical or empty, no contradiction
    if not obj_a or not obj_b:
        return False
    if obj_a == obj_b and mech_a == mech_b:
        return False

    try:
        budget.check()
    except BudgetExhausted:
        return False  # Conservative: allow merge on budget exhaustion

    prompt = f"""Do these two strategic approaches contradict each other? A contradiction means they have opposing goals or mutually exclusive methods.

APPROACH A:
Objective: {obj_a}
Mechanism: {mech_a}

APPROACH B:
Objective: {obj_b}
Mechanism: {mech_b}

Respond with ONLY valid JSON:
{{"contradicts": true/false, "reason": "brief explanation"}}"""

    response = llm.call(
        system_prompt="You are a strategic contradiction detector. Output only JSON.",
        user_prompt=prompt,
        max_tokens=150,
    )
    budget.record_call(response)

    content = response.get("content", "")
    try:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(content[start:end])
            return bool(parsed.get("contradicts", False))
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    return False  # Conservative fallback


def _merge_canonical_forms(forms: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple canonical forms, preserving all unique entries."""
    merged = {"objective": "", "mechanism": "", "dependencies": [], "key_constraints": [], "expected_outcomes": []}

    objectives = [f.get("objective", "") for f in forms if f.get("objective")]
    mechanisms = [f.get("mechanism", "") for f in forms if f.get("mechanism")]
    merged["objective"] = objectives[0] if objectives else ""
    merged["mechanism"] = mechanisms[0] if mechanisms else ""

    seen_deps: set[str] = set()
    seen_constraints: set[str] = set()
    seen_outcomes: set[str] = set()
    for f in forms:
        for d in f.get("dependencies", []):
            if d and d not in seen_deps:
                merged["dependencies"].append(d)
                seen_deps.add(d)
        for c in f.get("key_constraints", []):
            if c and c not in seen_constraints:
                merged["key_constraints"].append(c)
                seen_constraints.add(c)
        for o in f.get("expected_outcomes", []):
            if o and o not in seen_outcomes:
                merged["expected_outcomes"].append(o)
                seen_outcomes.add(o)

    return merged


def _merge_solution_cluster(
    llm: LLMInterface,
    cluster: list[TheoryUnitSolution],
    budget: _BudgetGuard,
) -> AggregatedSolution:
    """Stage 3: Canonical form extraction, contradiction check, and structured merge."""
    # 3a: Extract canonical forms
    canonical_forms: list[dict[str, Any]] = []
    for sol in cluster:
        form = _extract_canonical_form(llm, sol, budget)
        canonical_forms.append(form)

    # 3b: Check for contradictions — if any pair contradicts, skip merge
    has_contradiction = False
    for i in range(len(canonical_forms)):
        for j in range(i + 1, len(canonical_forms)):
            if _detect_contradiction(llm, canonical_forms[i], canonical_forms[j], budget):
                has_contradiction = True
                break
        if has_contradiction:
            break

    if has_contradiction:
        # Don't merge contradictory solutions — use first as representative
        sol = cluster[0]
        all_chunks = list(set(cid for s in cluster for cid in s.retrieved_chunk_ids))
        return AggregatedSolution(
            id=str(uuid.uuid4()),
            merged_solution=sol.solution,
            contributing_units=[s.unit_id for s in cluster],
            justifications=[s.reasoning for s in cluster],
            confidence_score=0.3,
            retrieved_chunk_ids=all_chunks,
            cluster_evidence={"canonical_forms": canonical_forms, "contradiction_detected": True},
        )

    # 3c: Merge canonical forms and produce merged solution
    merged_form = _merge_canonical_forms(canonical_forms)

    solution_texts = "\n\n".join([
        f"SOLUTION FROM {sol.unit_name}:\n{sol.solution}\n\nREASONING:\n{sol.reasoning}"
        for sol in cluster
    ])

    prompt = f"""Multiple analysts have reached similar conclusions. Create a merged recommendation that:
1. Captures the core agreement between all analysts
2. Preserves each analyst's unique reasoning and insights
3. Notes any nuanced differences between the approaches

CANONICAL FORM (shared strategic structure):
Objective: {merged_form['objective']}
Mechanism: {merged_form['mechanism']}
Dependencies: {', '.join(merged_form['dependencies']) or 'None'}
Key Constraints: {', '.join(merged_form['key_constraints']) or 'None'}
Expected Outcomes: {', '.join(merged_form['expected_outcomes']) or 'None'}

INDIVIDUAL SOLUTIONS:

{solution_texts}

Provide:
MERGED SOLUTION: [The unified recommendation incorporating the canonical structure]
SYNTHESIS: [How the different perspectives complement each other]"""

    try:
        budget.check()
    except BudgetExhausted:
        sol = cluster[0]
        all_chunks = list(set(cid for s in cluster for cid in s.retrieved_chunk_ids))
        return AggregatedSolution(
            id=str(uuid.uuid4()),
            merged_solution=sol.solution,
            contributing_units=[s.unit_id for s in cluster],
            justifications=[s.reasoning for s in cluster],
            confidence_score=0.5,
            retrieved_chunk_ids=all_chunks,
            cluster_evidence={"canonical_forms": canonical_forms, "merged_canonical": merged_form},
        )

    response = llm.call(
        system_prompt="You are an expert at synthesizing multiple strategic analyses into unified recommendations.",
        user_prompt=prompt,
        max_tokens=2000,
    )
    budget.record_call(response)

    merged_content = response.get("content", "")
    all_chunks: list[str] = []
    for sol in cluster:
        all_chunks.extend(sol.retrieved_chunk_ids)

    confidence = min(0.5 + (len(cluster) * 0.1), 0.95)

    return AggregatedSolution(
        id=str(uuid.uuid4()),
        merged_solution=merged_content,
        contributing_units=[sol.unit_id for sol in cluster],
        justifications=[sol.reasoning for sol in cluster],
        confidence_score=confidence,
        retrieved_chunk_ids=list(set(all_chunks)),
        cluster_evidence={"canonical_forms": canonical_forms, "merged_canonical": merged_form},
    )


# Backward-compatible wrapper for old code
def _aggregate_similar_solutions(
    llm: LLMInterface,
    solutions: list[TheoryUnitSolution],
    similarity_threshold: float = 0.65,
) -> list[AggregatedSolution]:
    """Legacy wrapper. Prefer cluster_solutions_monitor_v2 for new code."""
    budget = _BudgetGuard(HivemindInput(query="", max_total_llm_calls=999))
    aggregated, _ = cluster_solutions_monitor_v2(
        llm, solutions, budget, similarity_threshold=similarity_threshold,
    )
    return aggregated


# ---------------------------------------------------------------------------
# Feasibility Parsing and Actions
# ---------------------------------------------------------------------------


def _parse_feasibility_score(response: str) -> tuple[int, list[str], list[str], list[str], str]:
    score = 50
    risks: list[str] = []
    challenges: list[str] = []
    mitigations: list[str] = []
    reasoning = response

    lines = response.split("\n")
    current_section = None

    for line in lines:
        line_lower = line.lower().strip()

        if "feasibility score" in line_lower or "score:" in line_lower:
            for word in line.split():
                try:
                    num = int(word.replace("/100", "").replace("%", ""))
                    if 0 <= num <= 100:
                        score = num
                        break
                except ValueError:
                    continue
        elif "risk" in line_lower:
            current_section = "risks"
        elif "challenge" in line_lower:
            current_section = "challenges"
        elif "mitigation" in line_lower:
            current_section = "mitigations"
        elif "reasoning" in line_lower:
            current_section = "reasoning"
        elif line.strip().startswith("-") or line.strip().startswith("\u2022"):
            item = line.strip().lstrip("-\u2022").strip()
            if current_section == "risks":
                risks.append(item)
            elif current_section == "challenges":
                challenges.append(item)
            elif current_section == "mitigations":
                mitigations.append(item)

    return score, risks, challenges, mitigations, reasoning


def _generate_suggested_actions(recommendation: Recommendation) -> list[Action]:
    actions: list[Action] = []

    actions.append(
        Action(
            type=ActionType.LOG,
            target="audit_log",
            payload={"recommendation_id": recommendation.id},
            description=f"Log recommendation: {recommendation.title}",
        )
    )

    if recommendation.average_feasibility >= 80:
        actions.append(
            Action(
                type=ActionType.NOTIFY,
                target="stakeholders",
                payload={"recommendation_id": recommendation.id, "priority": "high"},
                description=f"Notify stakeholders: {recommendation.title}",
            )
        )
    elif recommendation.average_feasibility >= 50:
        actions.append(
            Action(
                type=ActionType.CONFIRM,
                target="decision_maker",
                payload={"recommendation_id": recommendation.id},
                description=f"Requires review: {recommendation.title}",
                requires_confirmation=True,
            )
        )

    return actions


# ---------------------------------------------------------------------------
# Practicality Scoring (shared by simple + full)
# ---------------------------------------------------------------------------


def apply_practicality_scoring(
    recommendations: list[Recommendation],
    practicality_agent_ids: list[str],
    input_data: HivemindInput,
    llm: LLMInterface,
    vector_store: VectorStoreInterface,
    storage: StorageInterface,
    budget: _BudgetGuard,
    audit_trail: list[AuditEvent],
    on_event: Any = None,
    *,
    mode: str = "",
    run_id: str = "",
) -> None:
    """Score each recommendation using practicality agents. Mutates recommendations in-place."""
    if not practicality_agent_ids:
        return

    practicality_agents: list[AgentDefinition] = []
    for agent_id in practicality_agent_ids:
        agent = storage.get_agent(agent_id)
        if agent:
            practicality_agents.append(agent)

    if not practicality_agents:
        return

    if on_event:
        on_event({"type": "practicality_start", "agent_count": len(practicality_agents)})

    criticality = getattr(input_data, "practicality_criticality", 0.5)
    criticality_pct = int(criticality * 100)

    for rec in recommendations:
        feasibility_scores: list[FeasibilityScore] = []

        for p_agent in practicality_agents:
            try:
                budget.check()
            except BudgetExhausted:
                # F2: Partial scoring — record what we have and flag
                rec.feasibility_scores = feasibility_scores
                if feasibility_scores:
                    rec.average_feasibility = sum(fs.score for fs in feasibility_scores) / len(feasibility_scores)
                rec.partial_scoring = True
                audit_trail.append(AuditEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="partial_practicality_scoring",
                    details=_make_audit_details(
                        mode, run_id,
                        rec_id=rec.id,
                        agents_scored=len(feasibility_scores),
                        agents_total=len(practicality_agents),
                        reason="budget_exhausted",
                    ),
                ))
                return

            eval_query = f"""Evaluate the feasibility of this strategic recommendation.

RECOMMENDATION:
{rec.content}

Criticality level: {criticality_pct}% — 0% means lenient (assume ideal conditions), 100% means maximally harsh (assume worst-case constraints).

Provide:
1. FEASIBILITY SCORE: (1-100)
2. RISKS: Key risks identified
3. CHALLENGES: Implementation challenges
4. MITIGATIONS: Suggested mitigations

Be rigorous in your assessment."""

            result, audit = execute_agent(
                agent=p_agent, query=eval_query,
                llm=llm, vector_store=vector_store, storage=storage,
            )
            audit_trail.append(audit)
            budget.record_agent_call(result)

            score, risks, challenges, mitigations, reasoning = _parse_feasibility_score(result.response)

            feasibility_scores.append(FeasibilityScore(
                agent_id=result.agent_id, agent_name=result.agent_name,
                score=score, risks=risks, challenges=challenges,
                mitigations=mitigations, reasoning=reasoning,
                retrieved_chunk_ids=result.retrieved_chunk_ids,
            ))

            if on_event:
                on_event({
                    "type": "feasibility_score",
                    "agent_id": p_agent.id,
                    "agent_name": p_agent.name,
                    "rec_id": rec.id,
                    "score": score,
                })

        rec.feasibility_scores = feasibility_scores
        if feasibility_scores:
            rec.average_feasibility = sum(fs.score for fs in feasibility_scores) / len(feasibility_scores)


# ---------------------------------------------------------------------------
# Recommendation-Level Repair Loop
# ---------------------------------------------------------------------------


def repair_failed_recommendations(
    recommendations: list[Recommendation],
    threshold: int,
    max_iterations: int,
    llm: LLMInterface,
    vector_store: VectorStoreInterface,
    storage: StorageInterface,
    input_data: HivemindInput,
    budget: _BudgetGuard,
    audit_trail: list[AuditEvent],
    repair_stats: RepairStats,
    on_event: Any = None,
    *,
    mode: str = "",
    run_id: str = "",
) -> None:
    """Per-recommendation repair loop. Mutates recommendations in-place.

    For each recommendation with avg_feasibility <= threshold:
    - Construct a deterministic repair packet from risks/challenges/mitigations
    - Ask theory LLM to revise preserving core intent
    - Rescore with practicality agents
    - Stop when score passes or max_iterations reached
    """
    for rec in recommendations:
        if rec.average_feasibility > threshold:
            rec.status = RecommendationStatus.APPROVED.value
            continue

        repair_stats.recommendations_repaired += 1

        if on_event:
            on_event({"type": "repair_start", "rec_id": rec.id, "avg_score": rec.average_feasibility})

        for iteration in range(max_iterations):
            try:
                budget.check()
            except BudgetExhausted:
                # F3: Stop immediately, preserve best-known version
                if rec.average_feasibility > threshold:
                    rec.status = RecommendationStatus.APPROVED.value
                    repair_stats.recommendations_recovered += 1
                else:
                    rec.status = RecommendationStatus.FAILED_AFTER_REPAIRS.value
                    repair_stats.recommendations_failed_after_repairs += 1
                repair_stats.total_repair_iterations += iteration
                return

            # Build repair packet
            all_risks = []
            all_challenges = []
            all_mitigations = []
            for fs in rec.feasibility_scores:
                all_risks.extend(fs.risks)
                all_challenges.extend(fs.challenges)
                all_mitigations.extend(fs.mitigations)

            repair_prompt = f"""You must revise this strategic recommendation to improve its feasibility.

CURRENT RECOMMENDATION:
{rec.content}

CURRENT AVERAGE FEASIBILITY SCORE: {rec.average_feasibility:.0f}/100
TARGET MINIMUM SCORE: {threshold + 5}

TOP RISKS (address these):
{chr(10).join(f'- {r}' for r in all_risks[:5]) or '- None identified'}

TOP CHALLENGES (address these):
{chr(10).join(f'- {c}' for c in all_challenges[:5]) or '- None identified'}

REQUIRED MITIGATIONS (incorporate these):
{chr(10).join(f'- {m}' for m in all_mitigations[:5]) or '- None identified'}

Requirements:
1. Preserve the core strategic intent where possible
2. Explicitly address each risk and challenge listed above
3. Incorporate the required mitigations
4. Include a "CHANGES MADE" section listing what you modified

Provide:
REVISED RECOMMENDATION: [your revised recommendation]
CHANGES MADE: [list of specific changes]"""

            response = llm.call(
                system_prompt="You are a strategic analyst revising a recommendation to improve its real-world feasibility.",
                user_prompt=repair_prompt,
                max_tokens=2000,
            )
            budget.record_call(response)

            revised_content = response.get("content", rec.content)
            old_score = rec.average_feasibility

            # Update the recommendation content
            rec.content = revised_content

            # Re-score with practicality agents
            rec.feasibility_scores = []
            rec.average_feasibility = 0.0
            apply_practicality_scoring(
                [rec],
                input_data.practicality_agent_ids,
                input_data, llm, vector_store, storage,
                budget, audit_trail,
                mode=mode, run_id=run_id,
            )

            rec.repair_history.append({
                "iteration": iteration + 1,
                "feedback_summary": f"Risks: {len(all_risks[:5])}, Challenges: {len(all_challenges[:5])}, Mitigations: {len(all_mitigations[:5])}",
                "score_before": old_score,
                "score_after": rec.average_feasibility,
            })

            audit_trail.append(AuditEvent(
                timestamp=datetime.now(timezone.utc),
                event_type="repair_iteration",
                details=_make_audit_details(
                    mode, run_id,
                    rec_id=rec.id,
                    iteration=iteration + 1,
                    score_before=old_score,
                    score_after=rec.average_feasibility,
                ),
            ))

            if on_event:
                on_event({
                    "type": "repair_iteration",
                    "rec_id": rec.id,
                    "iteration": iteration + 1,
                    "score_before": old_score,
                    "score_after": rec.average_feasibility,
                })

            if rec.average_feasibility > threshold:
                rec.status = RecommendationStatus.APPROVED.value
                repair_stats.recommendations_recovered += 1
                repair_stats.total_repair_iterations += iteration + 1
                break
        else:
            # Exhausted all repair iterations
            rec.status = RecommendationStatus.FAILED_AFTER_REPAIRS.value
            repair_stats.recommendations_failed_after_repairs += 1
            repair_stats.total_repair_iterations += max_iterations


# ---------------------------------------------------------------------------
# Theory agent resolution (shared)
# ---------------------------------------------------------------------------


def _resolve_theory_agents(
    input_data: HivemindInput,
    storage: StorageInterface,
    audit_trail: list[AuditEvent],
    *,
    mode: str = "",
    run_id: str = "",
) -> tuple[list[AgentDefinition], int]:
    """Resolve theory agents from input config. Returns (agents, units_created)."""
    theory_agents: list[AgentDefinition] = []
    theory_units_created = 0

    if input_data.theory_network_density is not None:
        all_kb_ids: list[str] = []
        for agent_id in (input_data.theory_agent_ids or input_data.agent_ids):
            agent = storage.get_agent(agent_id)
            if agent:
                all_kb_ids.extend(agent.knowledge_base_ids)
        all_kb_ids = list(set(all_kb_ids))

        doc_tokens = _get_document_token_counts(storage, all_kb_ids)
        dynamic_units = _create_dynamic_units(
            density_value=input_data.theory_network_density,
            all_document_ids=list(doc_tokens.keys()),
            document_tokens=doc_tokens,
        )
        theory_units_created = len(dynamic_units)
        theory_agents = [_dynamic_unit_to_agent(unit, all_kb_ids) for unit in dynamic_units]

        audit_trail.append(AuditEvent(
            timestamp=datetime.now(timezone.utc),
            event_type="dynamic_units_created",
            details=_make_audit_details(
                mode, run_id,
                density_value=input_data.theory_network_density,
                units_created=len(dynamic_units),
                total_documents=len(all_kb_ids),
            ),
        ))
    else:
        theory_agent_ids = input_data.theory_agent_ids or input_data.agent_ids
        for agent_id in theory_agent_ids:
            agent = storage.get_agent(agent_id)
            if agent:
                theory_agents.append(agent)
        theory_units_created = len(theory_agents)

    return theory_agents, theory_units_created


def _generate_initial_solutions(
    theory_agents: list[AgentDefinition],
    input_data: HivemindInput,
    llm: LLMInterface,
    vector_store: VectorStoreInterface,
    storage: StorageInterface,
    budget: _BudgetGuard,
    audit_trail: list[AuditEvent],
    on_event: Any = None,
    *,
    mode: str = "",
    run_id: str = "",
) -> list[TheoryUnitSolution]:
    """Generate one solution per theory agent."""
    solutions: list[TheoryUnitSolution] = []
    run_context = getattr(input_data, "context", None) or []

    if on_event:
        on_event({"type": "initial_solutions_start", "agent_count": len(theory_agents)})

    for agent in theory_agents:
        try:
            budget.check()
        except BudgetExhausted:
            break

        result, audit = execute_agent(
            agent=agent, query=input_data.query,
            llm=llm, vector_store=vector_store, storage=storage,
            context=run_context,
        )
        audit_trail.append(audit)
        budget.record_agent_call(result)

        parsed_solution, parsed_reasoning = _parse_solution_reasoning(result.response)
        solutions.append(TheoryUnitSolution(
            unit_id=agent.id,
            unit_name=agent.name,
            solution=parsed_solution,
            reasoning=parsed_reasoning,
            knowledge_base_ids=agent.knowledge_base_ids,
            retrieved_chunk_ids=result.retrieved_chunk_ids,
        ))

        if on_event:
            on_event({"type": "solution_generated", "agent_id": agent.id, "agent_name": agent.name})

    audit_trail.append(AuditEvent(
        timestamp=datetime.now(timezone.utc),
        event_type="initial_solutions_generated",
        details=_make_audit_details(mode, run_id, count=len(solutions)),
    ))

    return solutions


# ---------------------------------------------------------------------------
# Simple Mode
# ---------------------------------------------------------------------------


def run_simple_mode(
    input_data: HivemindInput,
    llm: LLMInterface,
    vector_store: VectorStoreInterface,
    storage: StorageInterface,
    budget: _BudgetGuard,
    on_event: Any = None,
) -> HivemindOutput:
    """Simple mode: fast/cheap baseline.

    1. Resolve theory + practicality agent IDs.
    2. Generate one solution per theory agent (no peer critique rounds).
    3. Aggregate once with monitor v2.
    4. Practicality score aggregated recommendations.
    5. Run at most 1 repair iteration on failing recommendations.
    6. Finalize approved + vetoed/failed_after_repairs.
    """
    run_id = str(uuid.uuid4())
    audit_trail: list[AuditEvent] = []
    repair_stats = RepairStats()
    termination_reason = TerminationReason.SIMPLE_COMPLETED.value

    if on_event:
        on_event({"type": "debate_start", "query": input_data.query, "mode": "simple"})

    # Step 1: Resolve theory agents
    theory_agents, theory_units_created = _resolve_theory_agents(
        input_data, storage, audit_trail, mode="simple", run_id=run_id,
    )

    if not theory_agents:
        # F4: No theory agents resolved
        return HivemindOutput(
            id=run_id,
            termination_reason=TerminationReason.VALIDATION_ERROR.value,
            mode_used="simple",
            budget_usage=budget.finalize(),
            audit_trail=[AuditEvent(
                timestamp=datetime.now(timezone.utc),
                event_type="error",
                details=_make_audit_details("simple", run_id, error="No theory agents found or created. Ensure theory agents are configured or density is set."),
            )],
        )

    if on_event:
        on_event({"type": "units_created", "count": theory_units_created})

    audit_trail.append(AuditEvent(
        timestamp=datetime.now(timezone.utc),
        event_type="debate_start",
        details=_make_audit_details(
            "simple", run_id,
            theory_agents=len(theory_agents),
            practicality_agents=len(input_data.practicality_agent_ids),
        ),
    ))

    try:
        # Step 2: Generate solutions (no critique rounds)
        solutions = _generate_initial_solutions(
            theory_agents, input_data, llm, vector_store, storage,
            budget, audit_trail, on_event,
            mode="simple", run_id=run_id,
        )

        if not solutions:
            return HivemindOutput(
                id=run_id,
                termination_reason=TerminationReason.BUDGET_EXHAUSTED.value,
                mode_used="simple",
                budget_usage=budget.finalize(),
                audit_trail=audit_trail,
            )

        # Step 3: Aggregate once with monitor v2
        sim_threshold = input_data.similarity_threshold
        aggregated, monitor_events = cluster_solutions_monitor_v2(
            llm, solutions, budget, similarity_threshold=sim_threshold,
            mode="simple", run_id=run_id,
        )
        audit_trail.extend(monitor_events)

        # Convert to recommendations
        recommendations = _aggregated_to_recommendations(aggregated)

        # Step 4: Practicality scoring
        apply_practicality_scoring(
            recommendations, input_data.practicality_agent_ids,
            input_data, llm, vector_store, storage,
            budget, audit_trail, on_event,
            mode="simple", run_id=run_id,
        )

        # Step 5: Repair (at most 1 iteration in simple mode)
        max_repair = min(1, input_data.get_effective_max_repair_iterations())
        threshold = input_data.feasibility_threshold

        repair_failed_recommendations(
            recommendations, threshold, max_repair,
            llm, vector_store, storage, input_data,
            budget, audit_trail, repair_stats, on_event,
            mode="simple", run_id=run_id,
        )

        if repair_stats.recommendations_recovered > 0:
            termination_reason = TerminationReason.SIMPLE_COMPLETED.value

    except BudgetExhausted:
        termination_reason = TerminationReason.BUDGET_EXHAUSTED.value
        # Preserve whatever we have
        if "recommendations" not in dir():
            recommendations = []

    # Step 6: Finalize
    threshold = input_data.feasibility_threshold
    surviving = []
    vetoed = []
    for rec in recommendations:
        if rec.status == RecommendationStatus.APPROVED.value and rec.average_feasibility > threshold:
            rec.status = RecommendationStatus.APPROVED.value
            surviving.append(rec)
        elif rec.status == RecommendationStatus.FAILED_AFTER_REPAIRS.value:
            surviving.append(rec)  # Include but mark as failed
        else:
            rec.status = RecommendationStatus.VETOED.value
            vetoed.append(rec)

    # I4 guard: approved recommendations must be above threshold.
    # Resilient — demote rather than crash (bare assert is stripped by python -O).
    _log = logging.getLogger("hivemind.debate")
    for rec in surviving[:]:
        if rec.status == RecommendationStatus.APPROVED.value and rec.average_feasibility <= threshold:
            _log.error("I4 violation corrected: rec %s (score %.1f) demoted to vetoed", rec.id, rec.average_feasibility)
            rec.status = RecommendationStatus.VETOED.value
            surviving.remove(rec)
            vetoed.append(rec)

    all_actions: list[Action] = []
    for rec in surviving:
        if rec.status == RecommendationStatus.APPROVED.value:
            actions = _generate_suggested_actions(rec)
            rec.suggested_actions = actions
            all_actions.extend(actions)

    final_usage = budget.finalize()

    output = HivemindOutput(
        id=run_id,
        recommendations=surviving,
        vetoed_solutions=vetoed,
        audit_trail=audit_trail,
        suggested_actions=all_actions,
        debate_rounds=0,
        veto_restarts=0,
        aggregated_solution_count=len(aggregated) if "aggregated" in dir() else 0,
        theory_units_created=theory_units_created,
        duration_ms=final_usage.wallclock_ms,
        total_tokens=final_usage.total_tokens,
        termination_reason=termination_reason,
        budget_usage=final_usage,
        mode_used="simple",
        repair_stats=repair_stats,
    )

    if on_event:
        on_event({"type": "termination", "reason": termination_reason})
        on_event({"type": "complete", "output": output})

    return output


# ---------------------------------------------------------------------------
# Full Mode
# ---------------------------------------------------------------------------


def run_full_mode(
    input_data: HivemindInput,
    llm: LLMInterface,
    vector_store: VectorStoreInterface,
    storage: StorageInterface,
    budget: _BudgetGuard,
    on_event: Any = None,
) -> HivemindOutput:
    """Full mode: deeper synthesis with bounded complexity.

    1. Theory unit setup.
    2. Initial solution generation.
    3. Debate loop (critique + revision) with strict stop conditions.
    4. Practicality scoring.
    5. Per-recommendation repair loop.
    6. Emergency global restart (capped at 1 by default).
    7. Finalize and return.
    """
    run_id = str(uuid.uuid4())
    audit_trail: list[AuditEvent] = []
    repair_stats = RepairStats()
    termination_reason = TerminationReason.SUFFICIENCY_REACHED.value

    max_rounds = input_data.get_effective_max_rounds()
    max_repair = input_data.get_effective_max_repair_iterations()
    threshold = input_data.feasibility_threshold
    # Cap global restarts: 1 by default, 0 for low effort
    max_global_restarts = 0 if input_data.effort_level == "low" else min(input_data.max_veto_restarts, 1)
    global_restarts = 0

    stagnation = _StagnationDetector(
        window=input_data.stagnation_window_rounds,
        min_improvement=input_data.min_aggregation_improvement,
    )

    if on_event:
        on_event({"type": "debate_start", "query": input_data.query, "mode": "full"})

    # Outer loop for global restart
    while global_restarts <= max_global_restarts:
        theory_agents, theory_units_created = _resolve_theory_agents(
            input_data, storage, audit_trail, mode="full", run_id=run_id,
        )

        if not theory_agents:
            return HivemindOutput(
                id=run_id,
                termination_reason=TerminationReason.VALIDATION_ERROR.value,
                mode_used="full",
                budget_usage=budget.finalize(),
                audit_trail=[AuditEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="error",
                    details=_make_audit_details("full", run_id, error="No theory agents found or created."),
                )],
            )

        if on_event:
            on_event({"type": "units_created", "count": theory_units_created})

        audit_trail.append(AuditEvent(
            timestamp=datetime.now(timezone.utc),
            event_type="debate_start",
            details=_make_audit_details(
                "full", run_id,
                theory_agents=len(theory_agents),
                practicality_agents=len(input_data.practicality_agent_ids),
                global_restart=global_restarts,
            ),
        ))

        try:
            # Step 2: Initial solutions
            solutions = _generate_initial_solutions(
                theory_agents, input_data, llm, vector_store, storage,
                budget, audit_trail, on_event,
                mode="full", run_id=run_id,
            )

            if not solutions:
                termination_reason = TerminationReason.BUDGET_EXHAUSTED.value
                break

            # Step 3: Debate loop
            sim_threshold = input_data.similarity_threshold
            aggregated, monitor_events = cluster_solutions_monitor_v2(
                llm, solutions, budget, similarity_threshold=sim_threshold,
                mode="full", run_id=run_id,
            )
            audit_trail.extend(monitor_events)
            stagnation.record(len(aggregated))

            debate_rounds = 0
            sufficiency = input_data.sufficiency_value

            while len(aggregated) > sufficiency and debate_rounds < max_rounds:
                debate_rounds += 1

                if on_event:
                    on_event({"type": "round_start", "round": debate_rounds, "aggregated_count": len(aggregated)})

                audit_trail.append(AuditEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="debate_round_start",
                    details=_make_audit_details(
                        "full", run_id, round=debate_rounds,
                        solutions_count=len(solutions),
                        aggregated_count=len(aggregated),
                    ),
                ))

                # Critique phase
                all_critiques: dict[str, list[Critique]] = {sol.unit_id: [] for sol in solutions}
                for critic_sol in solutions:
                    for target_sol in solutions:
                        if critic_sol.unit_id == target_sol.unit_id:
                            continue
                        try:
                            budget.check()
                        except BudgetExhausted:
                            termination_reason = TerminationReason.BUDGET_EXHAUSTED.value
                            raise

                        critic_agent = next((a for a in theory_agents if a.id == critic_sol.unit_id), None)
                        critic_framework = critic_agent.framework if critic_agent else "Strategic Analysis"
                        critique_prompt = _create_critique_prompt(target_sol, critic_framework)

                        response = llm.call(
                            system_prompt=f"You are a strategic analyst using the {critic_framework} framework. Provide constructive critique.",
                            user_prompt=critique_prompt, max_tokens=1000,
                        )
                        budget.record_call(response)

                        critique_content = response.get("content", "")
                        strengths, weaknesses, suggestions = _parse_critique_response(critique_content)
                        all_critiques[target_sol.unit_id].append(Critique(
                            source_unit_id=critic_sol.unit_id, target_unit_id=target_sol.unit_id,
                            critique_text=critique_content,
                            strengths=strengths, weaknesses=weaknesses, suggestions=suggestions,
                        ))

                # Revision phase
                revised_solutions: list[TheoryUnitSolution] = []
                for sol in solutions:
                    critiques = all_critiques.get(sol.unit_id, [])
                    if critiques:
                        try:
                            budget.check()
                        except BudgetExhausted:
                            revised_solutions.append(sol)
                            continue

                        revision_prompt = _create_revision_prompt(
                            sol, critiques, revision_strength=input_data.revision_strength,
                        )
                        agent = next((a for a in theory_agents if a.id == sol.unit_id), None)
                        framework = agent.framework if agent else "Strategic Analysis"
                        response = llm.call(
                            system_prompt=f"You are a strategic analyst using the {framework} framework. Revise your analysis based on peer feedback.",
                            user_prompt=revision_prompt, max_tokens=2000,
                        )
                        budget.record_call(response)

                        rev_text = response.get("content", "")
                        rv_s, rv_r = _parse_solution_reasoning(rev_text) if rev_text else (sol.solution, sol.reasoning)
                        revised_solutions.append(TheoryUnitSolution(
                            unit_id=sol.unit_id, unit_name=sol.unit_name,
                            solution=rv_s, reasoning=rv_r,
                            knowledge_base_ids=sol.knowledge_base_ids,
                            retrieved_chunk_ids=sol.retrieved_chunk_ids,
                            revision_count=sol.revision_count + 1,
                        ))
                    else:
                        revised_solutions.append(sol)

                solutions = revised_solutions

                # Re-aggregate
                aggregated, monitor_events = cluster_solutions_monitor_v2(
                    llm, solutions, budget, similarity_threshold=sim_threshold,
                    mode="full", run_id=run_id,
                )
                audit_trail.extend(monitor_events)
                stagnation.record(len(aggregated))

                if on_event:
                    on_event({"type": "round_complete", "round": debate_rounds, "aggregated_count": len(aggregated)})

                audit_trail.append(AuditEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="debate_round_complete",
                    details=_make_audit_details(
                        "full", run_id, round=debate_rounds,
                        aggregated_count=len(aggregated),
                        target_sufficiency=sufficiency,
                    ),
                ))

                # Check stagnation
                if stagnation.is_stagnant():
                    termination_reason = TerminationReason.STAGNATION_EARLY_STOP.value
                    break

            # Determine debate termination reason
            if termination_reason not in (TerminationReason.STAGNATION_EARLY_STOP.value, TerminationReason.BUDGET_EXHAUSTED.value):
                if len(aggregated) <= sufficiency:
                    termination_reason = TerminationReason.SUFFICIENCY_REACHED.value
                elif debate_rounds >= max_rounds:
                    termination_reason = TerminationReason.MAX_ROUNDS_REACHED.value

            # Convert to recommendations
            recommendations = _aggregated_to_recommendations(aggregated)

            # Step 4: Practicality scoring
            if on_event:
                on_event({"type": "pass_to_practicality"})

            apply_practicality_scoring(
                recommendations, input_data.practicality_agent_ids,
                input_data, llm, vector_store, storage,
                budget, audit_trail, on_event,
                mode="full", run_id=run_id,
            )

            # Step 5: Per-recommendation repair
            failed_recs = [r for r in recommendations if r.average_feasibility <= threshold]
            if failed_recs:
                if on_event:
                    on_event({"type": "repair_phase_start", "count": len(failed_recs)})

                repair_failed_recommendations(
                    recommendations, threshold, max_repair,
                    llm, vector_store, storage, input_data,
                    budget, audit_trail, repair_stats, on_event,
                    mode="full", run_id=run_id,
                )

                if repair_stats.recommendations_recovered > 0:
                    termination_reason = TerminationReason.COMPLETED_WITH_REPAIRS.value

            # Step 6: Check if emergency global restart needed
            any_passing = any(r.average_feasibility > threshold for r in recommendations)
            if not any_passing and global_restarts < max_global_restarts:
                global_restarts += 1
                audit_trail.append(AuditEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="global_restart",
                    details=_make_audit_details(
                        "full", run_id,
                        restart_number=global_restarts,
                        reason="no_recommendations_passed_after_repair",
                    ),
                ))
                if on_event:
                    on_event({"type": "veto", "restart_number": global_restarts})
                continue

            if not any_passing and global_restarts >= max_global_restarts:
                termination_reason = TerminationReason.GLOBAL_RESTART_EXHAUSTED.value

            # Finalize — I4 guard: approved only if avg_feasibility > threshold
            surviving = []
            vetoed = []
            for rec in recommendations:
                if rec.status == RecommendationStatus.APPROVED.value and rec.average_feasibility > threshold:
                    surviving.append(rec)
                elif rec.status == RecommendationStatus.FAILED_AFTER_REPAIRS.value:
                    surviving.append(rec)
                else:
                    if rec.average_feasibility > threshold:
                        rec.status = RecommendationStatus.APPROVED.value
                        surviving.append(rec)
                    else:
                        rec.status = RecommendationStatus.VETOED.value
                        vetoed.append(rec)

            # I4 guard: approved recommendations must be above threshold.
            # Resilient — demote rather than crash (bare assert is stripped by python -O).
            _log = logging.getLogger("hivemind.debate")
            for rec in surviving[:]:
                if rec.status == RecommendationStatus.APPROVED.value and rec.average_feasibility <= threshold:
                    _log.error("I4 violation corrected: rec %s (score %.1f) demoted to vetoed", rec.id, rec.average_feasibility)
                    rec.status = RecommendationStatus.VETOED.value
                    surviving.remove(rec)
                    vetoed.append(rec)

            all_actions: list[Action] = []
            for rec in surviving:
                if rec.status == RecommendationStatus.APPROVED.value:
                    actions = _generate_suggested_actions(rec)
                    rec.suggested_actions = actions
                    all_actions.extend(actions)

            final_usage = budget.finalize()

            output = HivemindOutput(
                id=run_id,
                recommendations=surviving,
                vetoed_solutions=vetoed,
                audit_trail=audit_trail,
                suggested_actions=all_actions,
                debate_rounds=debate_rounds,
                veto_restarts=global_restarts,
                aggregated_solution_count=len(aggregated),
                theory_units_created=theory_units_created,
                duration_ms=final_usage.wallclock_ms,
                total_tokens=final_usage.total_tokens,
                termination_reason=termination_reason,
                budget_usage=final_usage,
                mode_used="full",
                repair_stats=repair_stats,
            )

            if on_event:
                on_event({"type": "termination", "reason": termination_reason})
                on_event({"type": "complete", "output": output})

            return output

        except BudgetExhausted:
            termination_reason = TerminationReason.BUDGET_EXHAUSTED.value
            break

    # Exhausted global restarts or budget
    final_usage = budget.finalize()
    output = HivemindOutput(
        id=run_id,
        recommendations=[],
        vetoed_solutions=[],
        audit_trail=audit_trail,
        suggested_actions=[],
        debate_rounds=0,
        veto_restarts=global_restarts,
        aggregated_solution_count=0,
        theory_units_created=0,
        duration_ms=final_usage.wallclock_ms,
        total_tokens=final_usage.total_tokens,
        termination_reason=termination_reason,
        budget_usage=final_usage,
        mode_used="full",
        repair_stats=repair_stats,
        metadata={"error": f"Terminated: {termination_reason}"},
    )

    if on_event:
        on_event({"type": "termination", "reason": termination_reason})
        on_event({"type": "complete", "output": output})

    return output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _aggregated_to_recommendations(aggregated: list[AggregatedSolution]) -> list[Recommendation]:
    """Convert aggregated solutions to recommendations."""
    recommendations: list[Recommendation] = []
    for agg in aggregated:
        rec = Recommendation(
            id=agg.id,
            title=f"Strategic Recommendation ({len(agg.contributing_units)} sources)",
            content=agg.merged_solution,
            reasoning="\n\n---\n\n".join(agg.justifications),
            contributing_agents=agg.contributing_units,
            retrieved_chunk_ids=agg.retrieved_chunk_ids,
        )
        recommendations.append(rec)
    return recommendations


# ---------------------------------------------------------------------------
# Main Entry Points (non-streaming + streaming)
# ---------------------------------------------------------------------------


def run_debate(
    input_data: HivemindInput,
    llm: LLMInterface,
    vector_store: VectorStoreInterface,
    storage: StorageInterface,
    max_rounds: int = 5,
) -> HivemindOutput:
    """Run the debate process. Dispatches to simple or full mode."""
    budget = _BudgetGuard(input_data)
    mode = getattr(input_data, "analysis_mode", "simple")

    if mode == "full":
        return run_full_mode(input_data, llm, vector_store, storage, budget)
    else:
        return run_simple_mode(input_data, llm, vector_store, storage, budget)


def run_debate_streaming(
    input_data: HivemindInput,
    llm: LLMInterface,
    vector_store: VectorStoreInterface,
    storage: StorageInterface,
    max_rounds: int = 5,
) -> Generator[dict[str, Any], None, None]:
    """Streaming wrapper. Yields event dicts in real-time as they occur.

    Uses a thread + queue pattern so events are yielded immediately as
    the debate engine produces them, rather than buffering until completion.
    The final event has type "complete" and includes the HivemindOutput.
    """
    import queue
    import threading

    _SENTINEL = object()
    event_queue: queue.Queue = queue.Queue()

    def push_event(event: dict[str, Any]) -> None:
        event_queue.put(event)

    def run_in_thread() -> None:
        try:
            budget = _BudgetGuard(input_data)
            mode = getattr(input_data, "analysis_mode", "simple")
            if mode == "full":
                run_full_mode(input_data, llm, vector_store, storage, budget, on_event=push_event)
            else:
                run_simple_mode(input_data, llm, vector_store, storage, budget, on_event=push_event)
        except Exception as exc:
            event_queue.put({"type": "error", "message": str(exc)})
        finally:
            event_queue.put(_SENTINEL)

    worker = threading.Thread(target=run_in_thread, daemon=True)
    worker.start()

    while True:
        item = event_queue.get()
        if item is _SENTINEL:
            break
        yield item

    worker.join(timeout=5)
