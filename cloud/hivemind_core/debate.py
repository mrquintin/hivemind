"""Multi-agent debate engine for Hivemind core.

Orchestrates the full debate process as specified in the Hivemind Product Pitch:
1. Dynamic theory network unit creation based on density value
2. Initial solution generation by all units
3. Solution sharing between units
4. Critique and revision cycles
5. Monitor aggregation of similar solutions
6. Sufficiency-based convergence
7. Practicality network evaluation
8. Veto mechanism with full restart capability
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from hivemind_core.agents import execute_agent
from hivemind_core.types import (
    Action,
    ActionType,
    AgentDefinition,
    AgentExecutionResult,
    AggregatedSolution,
    AuditEvent,
    Critique,
    DynamicTheoryUnit,
    FeasibilityScore,
    HivemindInput,
    HivemindOutput,
    LLMInterface,
    NetworkType,
    RagConfig,
    Recommendation,
    StorageInterface,
    TheoryUnitSolution,
    VectorStoreInterface,
)


# ---------------------------------------------------------------------------
# Response Parsing Helpers
# ---------------------------------------------------------------------------


def _parse_solution_reasoning(text: str) -> tuple[str, str]:
    """Split an LLM response into (solution, reasoning) based on labelled sections.

    Falls back to using the full text for both if the labels are not found.
    """
    import re
    sol_match = re.search(r"(?i)SOLUTION\s*:\s*([\s\S]*?)(?=REASONING\s*:|$)", text)
    rea_match = re.search(r"(?i)REASONING\s*:\s*([\s\S]*)", text)
    solution = sol_match.group(1).strip() if sol_match else text.strip()
    reasoning = rea_match.group(1).strip() if rea_match else text.strip()
    return solution, reasoning


# ---------------------------------------------------------------------------
# Dynamic Theory Unit Creation (based on density value)
# ---------------------------------------------------------------------------


def _get_document_token_counts(
    storage: StorageInterface,
    knowledge_base_ids: list[str],
) -> dict[str, int]:
    """Get token counts for all documents in the knowledge bases.

    Returns:
        Dict mapping document_id to token count.
    """
    results = storage.get_documents_for_knowledge_bases(knowledge_base_ids)
    return {doc["document_id"]: doc["token_count"] for doc in results}


def _create_dynamic_units(
    density_value: int,
    all_document_ids: list[str],
    document_tokens: dict[str, int],
) -> list[DynamicTheoryUnit]:
    """Create theory network units based on density value.
    
    Documents are distributed such that each unit's knowledge base
    has a token count approximately equal to the density value.
    
    Args:
        density_value: Target token count per unit
        all_document_ids: All available document IDs
        document_tokens: Token count per document
        
    Returns:
        List of DynamicTheoryUnit with assigned documents
    """
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
        
        # Assign documents until we reach the density value
        for doc_id in remaining_docs[:]:
            doc_token_count = document_tokens.get(doc_id, 1000)  # Default estimate
            
            # Add document if it doesn't exceed density by too much
            # or if the unit is empty (must have at least one doc)
            if unit.total_tokens + doc_token_count <= density_value * 1.2 or not unit.assigned_document_ids:
                unit.assigned_document_ids.append(doc_id)
                unit.total_tokens += doc_token_count
                remaining_docs.remove(doc_id)
            
            # Stop if we've reached the target density
            if unit.total_tokens >= density_value:
                break
        
        units.append(unit)
        unit_num += 1
    
    return units


def _dynamic_unit_to_agent(
    unit: DynamicTheoryUnit,
    knowledge_base_ids: list[str],
) -> AgentDefinition:
    """Convert a dynamic unit to an agent definition for execution."""
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
    """Create a prompt for one unit to critique another's solution."""
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
    """Extract STRENGTHS, WEAKNESSES, SUGGESTIONS bullet-lists from critique text.

    Returns (strengths, weaknesses, suggestions) where each is a list of strings.
    """
    import re

    def _extract_section(heading: str) -> list[str]:
        pattern = rf"(?i){heading}\s*:?\s*\n([\s\S]*?)(?=\n\s*(?:STRENGTHS|WEAKNESSES|SUGGESTIONS|$))"
        m = re.search(pattern, text)
        if not m:
            return []
        block = m.group(1)
        items = re.findall(r"[-•*]\s*(.+)", block)
        return [item.strip() for item in items if item.strip()]

    return _extract_section("STRENGTHS"), _extract_section("WEAKNESSES"), _extract_section("SUGGESTIONS")


def _create_revision_prompt(
    original_solution: TheoryUnitSolution,
    critiques: list[Critique],
    revision_strength: float = 0.5,
) -> str:
    """Create a prompt for a unit to revise its solution based on critiques.

    Args:
        original_solution: The solution to revise.
        critiques: Critiques received from other units.
        revision_strength: 0.0 = keep original mostly intact, 1.0 = aggressively
            rewrite in response to feedback.
    """
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
# Monitor: Semantic Similarity and Aggregation
# ---------------------------------------------------------------------------


def _get_embedding_model():
    """Lazy-load the sentence-transformers model (cached after first call)."""
    if not hasattr(_get_embedding_model, "_model"):
        from sentence_transformers import SentenceTransformer
        _get_embedding_model._model = SentenceTransformer("all-MiniLM-L6-v2")
    return _get_embedding_model._model


def _compute_solution_similarity(
    llm: LLMInterface,
    solution1: TheoryUnitSolution,
    solution2: TheoryUnitSolution,
) -> float:
    """Compute semantic similarity between two solutions using cosine similarity.

    Uses sentence-transformers embeddings instead of an LLM call.
    Returns a score from 0.0 (completely different) to 1.0 (essentially identical).
    """
    try:
        model = _get_embedding_model()
        embeddings = model.encode([solution1.solution, solution2.solution])
        # Cosine similarity
        from numpy import dot
        from numpy.linalg import norm
        a, b = embeddings[0], embeddings[1]
        cosine = float(dot(a, b) / (norm(a) * norm(b) + 1e-10))
        return max(0.0, min(1.0, cosine))
    except Exception:
        return 0.5


def _aggregate_similar_solutions(
    llm: LLMInterface,
    solutions: list[TheoryUnitSolution],
    similarity_threshold: float = 0.65,
) -> list[AggregatedSolution]:
    """Aggregate similar solutions into clusters.
    
    The Monitor groups solutions that exceed the similarity threshold
    and creates merged representations with all justifications listed.
    
    Args:
        llm: LLM interface for similarity computation and merging
        solutions: All solutions from theory units
        similarity_threshold: Threshold above which solutions are considered similar
        
    Returns:
        List of aggregated solutions (distinct conclusions)
    """
    if not solutions:
        return []
    
    # Track which solutions have been assigned to clusters
    assigned = set()
    clusters: list[list[TheoryUnitSolution]] = []
    
    for i, sol in enumerate(solutions):
        if i in assigned:
            continue
        
        # Start a new cluster with this solution
        cluster = [sol]
        assigned.add(i)
        
        # Find similar solutions
        for j, other_sol in enumerate(solutions):
            if j in assigned or j == i:
                continue
            
            similarity = _compute_solution_similarity(llm, sol, other_sol)
            if similarity >= similarity_threshold:
                cluster.append(other_sol)
                assigned.add(j)
        
        clusters.append(cluster)
    
    # Convert clusters to AggregatedSolutions
    aggregated: list[AggregatedSolution] = []
    
    for cluster in clusters:
        if len(cluster) == 1:
            # Single solution - no merging needed
            sol = cluster[0]
            agg = AggregatedSolution(
                id=str(uuid.uuid4()),
                merged_solution=sol.solution,
                contributing_units=[sol.unit_id],
                justifications=[sol.reasoning],
                confidence_score=0.5,  # Lower confidence for single-source
                retrieved_chunk_ids=sol.retrieved_chunk_ids,
            )
        else:
            # Multiple similar solutions - merge them
            agg = _merge_solution_cluster(llm, cluster)
        
        aggregated.append(agg)
    
    return aggregated


def _merge_solution_cluster(
    llm: LLMInterface,
    cluster: list[TheoryUnitSolution],
) -> AggregatedSolution:
    """Merge a cluster of similar solutions into one aggregated solution."""
    solution_texts = "\n\n".join([
        f"SOLUTION FROM {sol.unit_name}:\n{sol.solution}\n\nREASONING:\n{sol.reasoning}"
        for sol in cluster
    ])
    
    prompt = f"""Multiple analysts have reached similar conclusions. Create a merged recommendation that:
1. Captures the core agreement between all analysts
2. Preserves each analyst's unique reasoning and insights
3. Notes any nuanced differences between the approaches
4. Attributes specific insights to their sources

SOLUTIONS TO MERGE:

{solution_texts}

Provide:
MERGED SOLUTION: [The unified recommendation]
SYNTHESIS: [How the different perspectives complement each other]"""

    response = llm.call(
        system_prompt="You are an expert at synthesizing multiple strategic analyses into unified recommendations.",
        user_prompt=prompt,
        max_tokens=2000,
    )
    
    merged_content = response.get("content", "")
    
    # Collect all retrieved chunks from the cluster
    all_chunks: list[str] = []
    for sol in cluster:
        all_chunks.extend(sol.retrieved_chunk_ids)
    
    # Confidence scales with number of agreeing units
    confidence = min(0.5 + (len(cluster) * 0.1), 0.95)
    
    return AggregatedSolution(
        id=str(uuid.uuid4()),
        merged_solution=merged_content,
        contributing_units=[sol.unit_id for sol in cluster],
        justifications=[sol.reasoning for sol in cluster],
        confidence_score=confidence,
        retrieved_chunk_ids=list(set(all_chunks)),
    )


# ---------------------------------------------------------------------------
# Feasibility Parsing and Actions
# ---------------------------------------------------------------------------


def _parse_feasibility_score(response: str) -> tuple[int, list[str], list[str], list[str], str]:
    """Parse a practicality agent's response to extract structured data.

    Returns:
        Tuple of (score, risks, challenges, mitigations, reasoning)
    """
    score = 50  # Default
    risks: list[str] = []
    challenges: list[str] = []
    mitigations: list[str] = []
    reasoning = response

    lines = response.split("\n")
    current_section = None

    for line in lines:
        line_lower = line.lower().strip()

        if "feasibility score" in line_lower or "score:" in line_lower:
            # Try to extract numeric score
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
        elif line.strip().startswith("-") or line.strip().startswith("•"):
            item = line.strip().lstrip("-•").strip()
            if current_section == "risks":
                risks.append(item)
            elif current_section == "challenges":
                challenges.append(item)
            elif current_section == "mitigations":
                mitigations.append(item)

    return score, risks, challenges, mitigations, reasoning


def _generate_suggested_actions(recommendation: Recommendation) -> list[Action]:
    """Generate suggested actions from a recommendation."""
    actions: list[Action] = []

    # Basic action: log the recommendation
    actions.append(
        Action(
            type=ActionType.LOG,
            target="audit_log",
            payload={"recommendation_id": recommendation.id},
            description=f"Log recommendation: {recommendation.title}",
        )
    )

    # If feasibility is high, suggest execution
    if recommendation.average_feasibility >= 80:
        actions.append(
            Action(
                type=ActionType.NOTIFY,
                target="stakeholders",
                payload={
                    "recommendation_id": recommendation.id,
                    "priority": "high",
                },
                description=f"Notify stakeholders: {recommendation.title}",
            )
        )

    # If feasibility is moderate, suggest review
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
# Main Debate Engine
# ---------------------------------------------------------------------------


def run_debate(
    input_data: HivemindInput,
    llm: LLMInterface,
    vector_store: VectorStoreInterface,
    storage: StorageInterface,
    max_rounds: int = 5,
) -> HivemindOutput:
    """Run the full multi-agent debate process.
    
    This implements the complete Hivemind workflow:
    1. Create theory network units (dynamic if density specified, else use agent IDs)
    2. Each unit generates an initial solution
    3. Units share solutions and critique each other
    4. Units revise based on critiques received
    5. Monitor aggregates similar solutions
    6. Repeat until unique conclusions <= sufficiency_value
    7. Practicality network evaluates solutions
    8. If avg feasibility <= threshold, VETO and restart from scratch
    9. Output approved solutions to user
    
    Args:
        input_data: The Hivemind input with query and configuration
        llm: LLM interface for AI calls
        vector_store: Vector store for RAG
        storage: Storage interface for agents/simulations
        max_rounds: Maximum debate rounds before forced convergence
    
    Returns:
        HivemindOutput with recommendations, audit trail, and actions
    """
    start_time = datetime.utcnow()
    audit_trail: list[AuditEvent] = []
    total_tokens = 0
    veto_restarts = 0
    theory_units_created = 0
    max_veto_restarts = input_data.max_veto_restarts
    
    # Main loop - can restart on veto
    while veto_restarts <= max_veto_restarts:
        
        # Reset for this attempt
        current_solutions: list[TheoryUnitSolution] = []
        
        # ======================================================================
        # STEP 1: Create Theory Network Units
        # ======================================================================
        
        theory_agents: list[AgentDefinition] = []
        
        if input_data.theory_network_density is not None:
            # Dynamic unit creation based on density value
            # Get all knowledge base IDs from practicality agents or use defaults
            all_kb_ids: list[str] = []
            for agent_id in (input_data.theory_agent_ids or input_data.agent_ids):
                agent = storage.get_agent(agent_id)
                if agent:
                    all_kb_ids.extend(agent.knowledge_base_ids)
            
            # Remove duplicates
            all_kb_ids = list(set(all_kb_ids))
            
            # Get document token counts from storage
            doc_tokens = _get_document_token_counts(storage, all_kb_ids)

            # Create dynamic units based on density
            dynamic_units = _create_dynamic_units(
                density_value=input_data.theory_network_density,
                all_document_ids=list(doc_tokens.keys()),
                document_tokens=doc_tokens,
            )
            
            theory_units_created = len(dynamic_units)
            
            # Convert to agent definitions
            theory_agents = [_dynamic_unit_to_agent(unit, all_kb_ids) for unit in dynamic_units]
            
            audit_trail.append(
                AuditEvent(
                    timestamp=datetime.utcnow(),
                    event_type="dynamic_units_created",
                    details={
                        "density_value": input_data.theory_network_density,
                        "units_created": len(dynamic_units),
                        "total_documents": len(all_kb_ids),
                    },
                )
            )
        else:
            # Use specified theory agent IDs
            theory_agent_ids = input_data.theory_agent_ids or input_data.agent_ids
            for agent_id in theory_agent_ids:
                agent = storage.get_agent(agent_id)
                if agent:
                    theory_agents.append(agent)
            
            theory_units_created = len(theory_agents)
        
        if not theory_agents:
            return HivemindOutput(
                id=str(uuid.uuid4()),
                recommendations=[],
                audit_trail=[
                    AuditEvent(
                        timestamp=datetime.utcnow(),
                        event_type="error",
                        details={"error": "No theory agents found or created"},
                    )
                ],
                debate_rounds=0,
                veto_restarts=veto_restarts,
                theory_units_created=0,
                duration_ms=0,
                total_tokens=0,
            )
        
        audit_trail.append(
            AuditEvent(
                timestamp=datetime.utcnow(),
                event_type="debate_start",
                details={
                    "query": input_data.query,
                    "theory_agents": len(theory_agents),
                    "practicality_agents": len(input_data.practicality_agent_ids),
                    "veto_restart": veto_restarts,
                },
            )
        )
        
        # ======================================================================
        # STEP 2: Initial Solution Generation
        # ======================================================================
        
        run_context = getattr(input_data, "context", None) or []

        for agent in theory_agents:
            result, audit = execute_agent(
                agent=agent,
                query=input_data.query,
                llm=llm,
                vector_store=vector_store,
                storage=storage,
                context=run_context,
            )
            audit_trail.append(audit)
            total_tokens += (result.input_tokens or 0) + (result.output_tokens or 0)
            
            parsed_solution, parsed_reasoning = _parse_solution_reasoning(result.response)

            solution = TheoryUnitSolution(
                unit_id=agent.id,
                unit_name=agent.name,
                solution=parsed_solution,
                reasoning=parsed_reasoning,
                knowledge_base_ids=agent.knowledge_base_ids,
                retrieved_chunk_ids=result.retrieved_chunk_ids,
                revision_count=0,
            )
            current_solutions.append(solution)
        
        audit_trail.append(
            AuditEvent(
                timestamp=datetime.utcnow(),
                event_type="initial_solutions_generated",
                details={"count": len(current_solutions)},
            )
        )
        
        # ======================================================================
        # STEPS 3-4: Critique/Revision Loop
        # ======================================================================
        
        debate_rounds = 0
        sufficiency = input_data.sufficiency_value
        
        # Aggregate to check initial solution count
        sim_threshold = getattr(input_data, "similarity_threshold", 0.65)
        aggregated = _aggregate_similar_solutions(llm, current_solutions, similarity_threshold=sim_threshold)
        
        while len(aggregated) > sufficiency and debate_rounds < max_rounds:
            debate_rounds += 1
            
            audit_trail.append(
                AuditEvent(
                    timestamp=datetime.utcnow(),
                    event_type="debate_round_start",
                    details={
                        "round": debate_rounds,
                        "solutions_count": len(current_solutions),
                        "aggregated_count": len(aggregated),
                    },
                )
            )
            
            # Each unit critiques every other unit's solution
            all_critiques: dict[str, list[Critique]] = {sol.unit_id: [] for sol in current_solutions}
            
            for critic_sol in current_solutions:
                for target_sol in current_solutions:
                    if critic_sol.unit_id == target_sol.unit_id:
                        continue
                    
                    # Get the critic's framework
                    critic_agent = next(
                        (a for a in theory_agents if a.id == critic_sol.unit_id), 
                        None
                    )
                    critic_framework = critic_agent.framework if critic_agent else "Strategic Analysis"
                    
                    critique_prompt = _create_critique_prompt(target_sol, critic_framework)
                    
                    response = llm.call(
                        system_prompt=f"You are a strategic analyst using the {critic_framework} framework. Provide constructive critique.",
                        user_prompt=critique_prompt,
                        max_tokens=1000,
                    )
                    total_tokens += response.get("input_tokens", 0) + response.get("output_tokens", 0)
                    
                    critique_content = response.get("content", "")
                    strengths, weaknesses, suggestions = _parse_critique_response(critique_content)

                    critique = Critique(
                        source_unit_id=critic_sol.unit_id,
                        target_unit_id=target_sol.unit_id,
                        critique_text=critique_content,
                        strengths=strengths,
                        weaknesses=weaknesses,
                        suggestions=suggestions,
                    )
                    
                    all_critiques[target_sol.unit_id].append(critique)
            
            audit_trail.append(
                AuditEvent(
                    timestamp=datetime.utcnow(),
                    event_type="critiques_completed",
                    details={
                        "round": debate_rounds,
                        "total_critiques": sum(len(c) for c in all_critiques.values()),
                    },
                )
            )
            
            # Each unit revises based on critiques received
            revised_solutions: list[TheoryUnitSolution] = []
            
            for sol in current_solutions:
                critiques = all_critiques.get(sol.unit_id, [])
                
                if critiques:
                    revision_prompt = _create_revision_prompt(
                        sol, critiques,
                        revision_strength=getattr(input_data, "revision_strength", 0.5),
                    )
                    
                    # Get the agent for this unit
                    agent = next((a for a in theory_agents if a.id == sol.unit_id), None)
                    if agent:
                        framework = agent.framework or "Strategic Analysis"
                        system_prompt = f"You are a strategic analyst using the {framework} framework. Revise your analysis based on peer feedback."
                    else:
                        system_prompt = "You are a strategic analyst. Revise your analysis based on peer feedback."
                    
                    response = llm.call(
                        system_prompt=system_prompt,
                        user_prompt=revision_prompt,
                        max_tokens=2000,
                    )
                    total_tokens += response.get("input_tokens", 0) + response.get("output_tokens", 0)
                    
                    rev_text = response.get("content", "")
                    rev_solution, rev_reasoning = _parse_solution_reasoning(rev_text) if rev_text else (sol.solution, sol.reasoning)

                    revised = TheoryUnitSolution(
                        unit_id=sol.unit_id,
                        unit_name=sol.unit_name,
                        solution=rev_solution,
                        reasoning=rev_reasoning,
                        knowledge_base_ids=sol.knowledge_base_ids,
                        retrieved_chunk_ids=sol.retrieved_chunk_ids,
                        revision_count=sol.revision_count + 1,
                    )
                    revised_solutions.append(revised)
                else:
                    revised_solutions.append(sol)
            
            current_solutions = revised_solutions
            
            # Re-aggregate after revisions
            aggregated = _aggregate_similar_solutions(llm, current_solutions, similarity_threshold=sim_threshold)
            
            audit_trail.append(
                AuditEvent(
                    timestamp=datetime.utcnow(),
                    event_type="debate_round_complete",
                    details={
                        "round": debate_rounds,
                        "revised_count": len(revised_solutions),
                        "aggregated_count": len(aggregated),
                        "target_sufficiency": sufficiency,
                    },
                )
            )
        
        # ======================================================================
        # STEP 5: Convert Aggregated Solutions to Recommendations
        # ======================================================================
        
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
        
        audit_trail.append(
            AuditEvent(
                timestamp=datetime.utcnow(),
                event_type="monitor_aggregation_complete",
                details={
                    "input_solutions": len(current_solutions),
                    "aggregated_conclusions": len(recommendations),
                    "debate_rounds": debate_rounds,
                },
            )
        )
        
        # ======================================================================
        # STEP 6: Practicality Network Evaluation
        # ======================================================================
        
        practicality_agent_ids = input_data.practicality_agent_ids
        
        if practicality_agent_ids:
            practicality_agents: list[AgentDefinition] = []
            for agent_id in practicality_agent_ids:
                agent = storage.get_agent(agent_id)
                if agent:
                    practicality_agents.append(agent)
            
            # Evaluate each recommendation
            for rec in recommendations:
                feasibility_scores: list[FeasibilityScore] = []
                
                criticality = getattr(input_data, "practicality_criticality", 0.5)
                criticality_pct = int(criticality * 100)

                for p_agent in practicality_agents:
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
                        agent=p_agent,
                        query=eval_query,
                        llm=llm,
                        vector_store=vector_store,
                        storage=storage,
                    )
                    audit_trail.append(audit)
                    total_tokens += (result.input_tokens or 0) + (result.output_tokens or 0)
                    
                    score, risks, challenges, mitigations, reasoning = _parse_feasibility_score(
                        result.response
                    )
                    
                    feasibility_scores.append(
                        FeasibilityScore(
                            agent_id=result.agent_id,
                            agent_name=result.agent_name,
                            score=score,
                            risks=risks,
                            challenges=challenges,
                            mitigations=mitigations,
                            reasoning=reasoning,
                            retrieved_chunk_ids=result.retrieved_chunk_ids,
                        )
                    )
                
                rec.feasibility_scores = feasibility_scores
                if feasibility_scores:
                    rec.average_feasibility = sum(fs.score for fs in feasibility_scores) / len(
                        feasibility_scores
                    )
        
        # ======================================================================
        # STEP 7: Veto Mechanism
        # ======================================================================
        
        threshold = input_data.feasibility_threshold
        
        # Check if ANY recommendation triggers a veto
        # Per the spec: if avg feasibility <= threshold, entire list is vetoed
        any_vetoed = False
        for rec in recommendations:
            if rec.average_feasibility <= threshold:
                any_vetoed = True
                break
        
        if any_vetoed and veto_restarts < max_veto_restarts:
            # VETO: Restart the entire process
            audit_trail.append(
                AuditEvent(
                    timestamp=datetime.utcnow(),
                    event_type="full_veto",
                    details={
                        "reason": "Average feasibility below threshold",
                        "threshold": threshold,
                        "restart_number": veto_restarts + 1,
                        "max_restarts": max_veto_restarts,
                    },
                )
            )
            veto_restarts += 1
            continue  # Restart the main loop
        
        # ======================================================================
        # STEP 8: Finalize Output
        # ======================================================================
        
        # Separate vetoed from surviving recommendations
        vetoed: list[Recommendation] = []
        surviving: list[Recommendation] = []
        
        for rec in recommendations:
            if rec.average_feasibility <= threshold:
                vetoed.append(rec)
            else:
                surviving.append(rec)
        
        # Generate suggested actions for surviving recommendations
        all_actions: list[Action] = []
        for rec in surviving:
            actions = _generate_suggested_actions(rec)
            rec.suggested_actions = actions
            all_actions.extend(actions)
        
        # Build final output
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        
        audit_trail.append(
            AuditEvent(
                timestamp=end_time,
                event_type="debate_complete",
                details={
                    "recommendations_count": len(surviving),
                    "vetoed_count": len(vetoed),
                    "debate_rounds": debate_rounds,
                    "veto_restarts": veto_restarts,
                    "theory_units_created": theory_units_created,
                    "total_tokens": total_tokens,
                    "duration_ms": duration_ms,
                },
            )
        )
        
        return HivemindOutput(
            id=str(uuid.uuid4()),
            recommendations=surviving,
            vetoed_solutions=vetoed,
            audit_trail=audit_trail,
            suggested_actions=all_actions,
            debate_rounds=debate_rounds,
            veto_restarts=veto_restarts,
            aggregated_solution_count=len(aggregated),
            theory_units_created=theory_units_created,
            duration_ms=duration_ms,
            total_tokens=total_tokens,
        )
    
    # If we've exhausted all veto restarts
    end_time = datetime.utcnow()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    
    audit_trail.append(
        AuditEvent(
            timestamp=end_time,
            event_type="max_restarts_exceeded",
            details={
                "veto_restarts": veto_restarts,
                "max_restarts": max_veto_restarts,
            },
        )
    )
    
    return HivemindOutput(
        id=str(uuid.uuid4()),
        recommendations=[],
        vetoed_solutions=[],
        audit_trail=audit_trail,
        suggested_actions=[],
        debate_rounds=0,
        veto_restarts=veto_restarts,
        aggregated_solution_count=0,
        theory_units_created=theory_units_created,
        duration_ms=duration_ms,
        total_tokens=total_tokens,
        metadata={"error": "Max veto restarts exceeded - no feasible solutions found"},
    )


# ---------------------------------------------------------------------------
# Streaming variant
# ---------------------------------------------------------------------------


def run_debate_streaming(
    input_data: HivemindInput,
    llm: LLMInterface,
    vector_store: VectorStoreInterface,
    storage: StorageInterface,
    max_rounds: int = 5,
):
    """Streaming wrapper around the debate process.

    Yields event dicts at key milestones. The final event has
    ``type`` = ``"complete"`` and includes the full ``HivemindOutput``
    serialised under the ``"output"`` key.
    """
    start_time = datetime.utcnow()
    audit_trail: list[AuditEvent] = []
    total_tokens = 0
    veto_restarts = 0
    theory_units_created = 0
    max_veto_restarts = input_data.max_veto_restarts

    yield {"type": "debate_start", "query": input_data.query}

    while veto_restarts <= max_veto_restarts:
        current_solutions: list[TheoryUnitSolution] = []
        theory_agents: list[AgentDefinition] = []

        # --- Dynamic or static unit creation ---
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

            yield {"type": "units_created", "count": theory_units_created}
        else:
            theory_agent_ids = input_data.theory_agent_ids or input_data.agent_ids
            for agent_id in theory_agent_ids:
                agent = storage.get_agent(agent_id)
                if agent:
                    theory_agents.append(agent)
            theory_units_created = len(theory_agents)

        if not theory_agents:
            yield {"type": "error", "message": "No theory agents found or created"}
            return

        # --- Initial solution generation ---
        yield {"type": "initial_solutions_start", "agent_count": len(theory_agents)}

        run_context = getattr(input_data, "context", None) or []

        for agent in theory_agents:
            result, audit = execute_agent(
                agent=agent, query=input_data.query,
                llm=llm, vector_store=vector_store, storage=storage,
                context=run_context,
            )
            audit_trail.append(audit)
            total_tokens += (result.input_tokens or 0) + (result.output_tokens or 0)

            s_parsed, r_parsed = _parse_solution_reasoning(result.response)
            current_solutions.append(TheoryUnitSolution(
                unit_id=agent.id, unit_name=agent.name,
                solution=s_parsed, reasoning=r_parsed,
                knowledge_base_ids=agent.knowledge_base_ids,
                retrieved_chunk_ids=result.retrieved_chunk_ids,
            ))

            yield {"type": "solution_generated", "agent_id": agent.id, "agent_name": agent.name}

        # --- Debate loop ---
        debate_rounds = 0
        sufficiency = input_data.sufficiency_value
        sim_threshold = getattr(input_data, "similarity_threshold", 0.65)
        aggregated = _aggregate_similar_solutions(llm, current_solutions, similarity_threshold=sim_threshold)

        while len(aggregated) > sufficiency and debate_rounds < max_rounds:
            debate_rounds += 1
            yield {"type": "round_start", "round": debate_rounds, "aggregated_count": len(aggregated)}

            all_critiques: dict[str, list[Critique]] = {sol.unit_id: [] for sol in current_solutions}
            for critic_sol in current_solutions:
                for target_sol in current_solutions:
                    if critic_sol.unit_id == target_sol.unit_id:
                        continue
                    critic_agent = next((a for a in theory_agents if a.id == critic_sol.unit_id), None)
                    critic_framework = critic_agent.framework if critic_agent else "Strategic Analysis"
                    critique_prompt = _create_critique_prompt(target_sol, critic_framework)
                    response = llm.call(
                        system_prompt=f"You are a strategic analyst using the {critic_framework} framework. Provide constructive critique.",
                        user_prompt=critique_prompt, max_tokens=1000,
                    )
                    total_tokens += response.get("input_tokens", 0) + response.get("output_tokens", 0)
                    all_critiques[target_sol.unit_id].append(Critique(
                        source_unit_id=critic_sol.unit_id, target_unit_id=target_sol.unit_id,
                        critique_text=response.get("content", ""),
                    ))

            revised_solutions: list[TheoryUnitSolution] = []
            for sol in current_solutions:
                critiques = all_critiques.get(sol.unit_id, [])
                if critiques:
                    revision_prompt = _create_revision_prompt(
                        sol, critiques,
                        revision_strength=getattr(input_data, "revision_strength", 0.5),
                    )
                    agent = next((a for a in theory_agents if a.id == sol.unit_id), None)
                    framework = agent.framework if agent else "Strategic Analysis"
                    response = llm.call(
                        system_prompt=f"You are a strategic analyst using the {framework} framework. Revise your analysis based on peer feedback.",
                        user_prompt=revision_prompt, max_tokens=2000,
                    )
                    total_tokens += response.get("input_tokens", 0) + response.get("output_tokens", 0)
                    rev_t = response.get("content", "")
                    rv_s, rv_r = _parse_solution_reasoning(rev_t) if rev_t else (sol.solution, sol.reasoning)
                    revised_solutions.append(TheoryUnitSolution(
                        unit_id=sol.unit_id, unit_name=sol.unit_name,
                        solution=rv_s, reasoning=rv_r,
                        knowledge_base_ids=sol.knowledge_base_ids,
                        retrieved_chunk_ids=sol.retrieved_chunk_ids,
                        revision_count=sol.revision_count + 1,
                    ))
                else:
                    revised_solutions.append(sol)

            current_solutions = revised_solutions
            aggregated = _aggregate_similar_solutions(llm, current_solutions, similarity_threshold=sim_threshold)

            yield {"type": "round_complete", "round": debate_rounds, "aggregated_count": len(aggregated)}

        # --- Recommendations ---
        recommendations: list[Recommendation] = []
        for agg in aggregated:
            recommendations.append(Recommendation(
                id=agg.id,
                title=f"Strategic Recommendation ({len(agg.contributing_units)} sources)",
                content=agg.merged_solution,
                reasoning="\n\n---\n\n".join(agg.justifications),
                contributing_agents=agg.contributing_units,
                retrieved_chunk_ids=agg.retrieved_chunk_ids,
            ))

        # --- Practicality evaluation ---
        practicality_agent_ids = input_data.practicality_agent_ids
        if practicality_agent_ids:
            yield {"type": "practicality_start", "agent_count": len(practicality_agent_ids)}
            practicality_agents: list[AgentDefinition] = []
            for agent_id in practicality_agent_ids:
                agent = storage.get_agent(agent_id)
                if agent:
                    practicality_agents.append(agent)

            criticality = getattr(input_data, "practicality_criticality", 0.5)
            criticality_pct = int(criticality * 100)

            for rec in recommendations:
                feasibility_scores: list[FeasibilityScore] = []
                for p_agent in practicality_agents:
                    eval_query = f"""Evaluate the feasibility of this strategic recommendation.

RECOMMENDATION:
{rec.content}

Criticality level: {criticality_pct}% — 0% means lenient, 100% means maximally harsh.

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
                    total_tokens += (result.input_tokens or 0) + (result.output_tokens or 0)
                    score, risks, challenges, mitigations, reasoning = _parse_feasibility_score(result.response)
                    feasibility_scores.append(FeasibilityScore(
                        agent_id=result.agent_id, agent_name=result.agent_name,
                        score=score, risks=risks, challenges=challenges,
                        mitigations=mitigations, reasoning=reasoning,
                        retrieved_chunk_ids=result.retrieved_chunk_ids,
                    ))
                    yield {"type": "feasibility_score", "agent_id": p_agent.id, "agent_name": p_agent.name, "rec_id": rec.id, "score": score}
                rec.feasibility_scores = feasibility_scores
                if feasibility_scores:
                    rec.average_feasibility = sum(fs.score for fs in feasibility_scores) / len(feasibility_scores)

        # --- Veto check ---
        threshold = input_data.feasibility_threshold
        any_vetoed = any(rec.average_feasibility <= threshold for rec in recommendations)

        if any_vetoed and veto_restarts < max_veto_restarts:
            veto_restarts += 1
            yield {"type": "veto", "restart_number": veto_restarts}
            continue

        # --- Finalise ---
        vetoed = [r for r in recommendations if r.average_feasibility <= threshold]
        surviving = [r for r in recommendations if r.average_feasibility > threshold]
        all_actions: list[Action] = []
        for rec in surviving:
            actions = _generate_suggested_actions(rec)
            rec.suggested_actions = actions
            all_actions.extend(actions)

        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        output = HivemindOutput(
            id=str(uuid.uuid4()),
            recommendations=surviving,
            vetoed_solutions=vetoed,
            audit_trail=audit_trail,
            suggested_actions=all_actions,
            debate_rounds=debate_rounds,
            veto_restarts=veto_restarts,
            aggregated_solution_count=len(aggregated),
            theory_units_created=theory_units_created,
            duration_ms=duration_ms,
            total_tokens=total_tokens,
        )

        yield {"type": "complete", "output": output}
        return

    # Exhausted veto restarts
    end_time = datetime.utcnow()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    output = HivemindOutput(
        id=str(uuid.uuid4()),
        recommendations=[], vetoed_solutions=[],
        audit_trail=audit_trail, suggested_actions=[],
        debate_rounds=0, veto_restarts=veto_restarts,
        aggregated_solution_count=0, theory_units_created=theory_units_created,
        duration_ms=duration_ms, total_tokens=total_tokens,
        metadata={"error": "Max veto restarts exceeded"},
    )
    yield {"type": "complete", "output": output}
