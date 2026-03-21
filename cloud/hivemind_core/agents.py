"""Agent execution logic for Hivemind core.

Handles the construction of system prompts and execution of individual agents.
"""
from __future__ import annotations

from datetime import datetime, timezone

from hivemind_core.rag import format_chunks_for_prompt, retrieve_chunks
from hivemind_core.simulations import (
    format_simulations_for_prompt,
    run_simulation,
    simulations_to_tools,
)
from hivemind_core.types import (
    AgentDefinition,
    AgentExecutionResult,
    AuditEvent,
    ContextItem,
    ContextType,
    LLMInterface,
    RetrievedChunk,
    SimulationFormula,
    StorageInterface,
    VectorStoreInterface,
)


def build_theory_prompt(
    agent: AgentDefinition,
    chunks: list[RetrievedChunk],
    simulations: list[SimulationFormula],
) -> str:
    """Build the system prompt for a theory agent.

    Args:
        agent: The agent definition
        chunks: Retrieved knowledge chunks
        simulations: Available simulation formulas

    Returns:
        Complete system prompt string
    """
    rag_block = format_chunks_for_prompt(chunks)
    simulation_block = format_simulations_for_prompt(simulations)

    # Handle both dataclass and dict-like structures
    if isinstance(agent, dict):
        name = agent.get("name", "Analyst")
        framework = agent.get("framework", "strategic analysis")
        principles = agent.get("principles", "")
        analytical_style = agent.get("analytical_style", "")
    else:
        name = agent.name
        framework = agent.framework or "strategic analysis"
        principles = agent.principles or ""
        analytical_style = agent.analytical_style or ""

    return (
        f"You are {name}, a strategic analyst specializing in {framework}. "
        f"Your approach: {principles} {analytical_style}. "
        f"Your knowledge base:\n{rag_block}\n\n"
        f"Simulation library:\n{simulation_block}\n\n"
        "When analyzing: apply your framework rigorously, draw from your knowledge base, "
        "provide actionable recommendations, support claims with evidence. "
        "When critiquing: identify gaps, note principle conflicts, suggest improvements, "
        "acknowledge strengths. If a simulation is helpful, use the formulas and show your "
        "inputs and computed outputs explicitly.\n\n"
        "Format your response with these two clearly labelled sections:\n"
        "SOLUTION: <your proposed solution>\n"
        "REASONING: <your supporting reasoning>"
    )


def build_practicality_prompt(
    agent: AgentDefinition,
    chunks: list[RetrievedChunk],
) -> str:
    """Build the system prompt for a practicality agent.

    Args:
        agent: The agent definition
        chunks: Retrieved knowledge chunks

    Returns:
        Complete system prompt string
    """
    rag_block = format_chunks_for_prompt(chunks)

    # Handle both dataclass and dict-like structures
    if isinstance(agent, dict):
        name = agent.get("name", "Evaluator")
        scoring_criteria = agent.get("scoring_criteria", "")
        score_interpretation = agent.get("score_interpretation", "")
    else:
        name = agent.name
        scoring_criteria = agent.scoring_criteria or ""
        score_interpretation = agent.score_interpretation or ""

    return (
        f"You are {name}, evaluating recommendations for feasibility. "
        f"Criteria: {scoring_criteria}. Knowledge base:\n{rag_block}\n\n"
        f"Provide: FEASIBILITY SCORE (0-100), KEY RISKS, IMPLEMENTATION CHALLENGES, "
        f"MITIGATIONS, REASONING. Score interpretation: {score_interpretation}."
    )


def _format_context_for_prompt(context: list[ContextItem] | None) -> str:
    """Format context items (e.g. client-cleared text) for inclusion in the user prompt."""
    if not context:
        return ""
    parts = []
    for item in context:
        if getattr(item, "type", None) == ContextType.TEXT and isinstance(getattr(item, "content", None), str):
            parts.append(item.content.strip())
        elif isinstance(item, dict) and item.get("type") == ContextType.TEXT and isinstance(item.get("content"), str):
            parts.append(item["content"].strip())
    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n---\n\n"


def execute_agent(
    agent: AgentDefinition,
    query: str,
    llm: LLMInterface,
    vector_store: VectorStoreInterface,
    storage: StorageInterface,
    context: list[ContextItem] | None = None,
) -> tuple[AgentExecutionResult, AuditEvent]:
    """Execute a single agent against a query.

    Args:
        agent: The agent definition
        query: The problem statement / query
        llm: LLM interface for making AI calls
        vector_store: Vector store for RAG retrieval
        storage: Storage interface for loading simulations
        context: Optional client-cleared context items to prepend to the prompt

    Returns:
        Tuple of (AgentExecutionResult, AuditEvent)
    """
    # Handle both dataclass and dict-like structures
    if isinstance(agent, dict):
        agent_id = agent.get("id", "")
        agent_name = agent.get("name", "")
        network_type = agent.get("network_type", "theory")
        knowledge_base_ids = agent.get("knowledge_base_ids", [])
        document_ids = agent.get("document_ids", [])
        simulation_formula_ids = agent.get("simulation_formula_ids", [])
        rag_config = agent.get("rag_config")
    else:
        agent_id = agent.id
        agent_name = agent.name
        network_type = agent.network_type
        knowledge_base_ids = agent.knowledge_base_ids
        document_ids = getattr(agent, "document_ids", [])
        simulation_formula_ids = getattr(agent, "simulation_formula_ids", [])
        rag_config = agent.rag_config

    # Retrieve relevant knowledge chunks
    chunks = retrieve_chunks(
        vector_store, query, knowledge_base_ids, rag_config,
        document_ids=document_ids or None,
    )

    # Load simulations for theory agents
    simulations: list[SimulationFormula] = []
    if str(network_type) == "theory" and simulation_formula_ids:
        simulations = storage.get_simulations(simulation_formula_ids)

    # Build the appropriate system prompt
    if str(network_type) == "practicality":
        system_prompt = build_practicality_prompt(agent, chunks)
    else:
        system_prompt = build_theory_prompt(agent, chunks, simulations)

    # Build user prompt: optional context + query
    context_block = _format_context_for_prompt(context)
    user_prompt = (context_block + query) if context_block else query

    # Convert simulations to tool definitions for the LLM
    tools = simulations_to_tools(simulations) if simulations else None

    # Call the LLM (with tools if available)
    result = llm.call(system_prompt=system_prompt, user_prompt=user_prompt, tools=tools)

    # Handle tool calls: execute simulation and append results to the response
    tool_results_text: list[str] = []
    for tc in result.get("tool_calls", []):
        sim_id = tc["name"].replace("sim_", "").replace("_", "-")
        matching_sim = next((s for s in simulations if s.id == sim_id), None)
        if matching_sim:
            try:
                sim_result = run_simulation(matching_sim, tc["input"])
                tool_results_text.append(
                    f"[Simulation {matching_sim.name}] inputs={tc['input']} outputs={sim_result['outputs']}"
                )
            except Exception as e:
                tool_results_text.append(f"[Simulation {matching_sim.name}] error: {e}")

    # Combine text content with tool results
    response_text = result["content"]
    if tool_results_text:
        response_text += "\n\n" + "\n".join(tool_results_text)

    # Extract chunk IDs
    chunk_ids = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            chunk_ids.append(chunk.get("id", ""))
        else:
            chunk_ids.append(chunk.id)

    # Build the execution result
    execution_result = AgentExecutionResult(
        agent_id=agent_id,
        agent_name=agent_name,
        network_type=str(network_type),
        response=response_text,
        retrieved_chunk_ids=chunk_ids,
        input_tokens=result.get("input_tokens"),
        output_tokens=result.get("output_tokens"),
        latency_ms=result.get("latency_ms"),
        raw_response=result.get("raw", {}),
    )

    # Build the audit event
    audit_event = AuditEvent(
        timestamp=datetime.now(timezone.utc),
        event_type="agent_execution",
        agent_id=agent_id,
        retrieved_chunk_ids=chunk_ids,
        input_tokens=result.get("input_tokens"),
        output_tokens=result.get("output_tokens"),
        latency_ms=result.get("latency_ms"),
        details={"raw_response": result.get("raw", {})},
    )

    return execution_result, audit_event
