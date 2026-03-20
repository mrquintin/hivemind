#!/usr/bin/env python3
"""Benchmark simple vs full mode on a standard prompt set.

Usage:
    cd cloud && PYTHONPATH=. python3 scripts/benchmark_modes.py

Outputs:
    cloud/scripts/benchmark_report.md
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

# Ensure the cloud package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hivemind_core.debate import run_debate
from hivemind_core.llm import MockLLM
from hivemind_core.types import (
    AgentDefinition,
    HivemindInput,
    NetworkType,
    RecommendationStatus,
    StorageInterface,
    VectorStoreInterface,
    RetrievedChunk,
)


# ---------------------------------------------------------------------------
# Lightweight in-memory implementations for benchmarking
# ---------------------------------------------------------------------------


class _BenchmarkStorage(StorageInterface):
    """In-memory storage with pre-configured theory and practicality agents."""

    def __init__(self):
        self._agents = {
            "bench-theory-1": AgentDefinition(
                id="bench-theory-1", name="Strategic Analyst",
                network_type=NetworkType.THEORY,
                framework="Porter Five Forces + SWOT",
                principles="Data-driven strategic analysis",
                status="published",
            ),
            "bench-theory-2": AgentDefinition(
                id="bench-theory-2", name="Innovation Advisor",
                network_type=NetworkType.THEORY,
                framework="Blue Ocean Strategy",
                principles="Explore uncontested market spaces",
                status="published",
            ),
            "bench-pract-1": AgentDefinition(
                id="bench-pract-1", name="Risk Assessor",
                network_type=NetworkType.PRACTICALITY,
                framework="Risk Matrix Analysis",
                scoring_criteria="Feasibility 1-100 based on risk exposure",
                status="published",
            ),
        }

    def get_agent(self, agent_id: str):
        return self._agents.get(agent_id)

    def list_agents(self, status=None):
        return list(self._agents.values())

    def get_simulation(self, formula_id):
        return None

    def get_simulations(self, formula_ids):
        return []

    def get_documents_for_knowledge_bases(self, kb_ids):
        return []


class _BenchmarkVectorStore(VectorStoreInterface):
    def retrieve(self, query, knowledge_base_ids, top_k=8, similarity_threshold=0.0, document_ids=None):
        return []

    def upsert(self, collection, ids, embeddings, payloads):
        pass


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@dataclass
class RunMetrics:
    prompt_idx: int
    category: str
    prompt: str
    mode: str
    latency_ms: int
    total_tokens: int
    llm_calls: int
    recommendations_approved: int
    avg_feasibility: float
    repair_recovery_rate: float
    termination_reason: str


def _run_single(
    prompt_idx: int,
    category: str,
    prompt_text: str,
    mode: str,
    storage: StorageInterface,
    vector_store: VectorStoreInterface,
) -> RunMetrics:
    """Run one benchmark pass and collect metrics."""
    llm = MockLLM()

    inp = HivemindInput(
        query=prompt_text,
        theory_agent_ids=["bench-theory-1", "bench-theory-2"],
        practicality_agent_ids=["bench-pract-1"],
        analysis_mode=mode,
        effort_level="medium",
        sufficiency_value=2,
        feasibility_threshold=50,
    )

    output = run_debate(inp, llm, vector_store, storage)

    approved = [r for r in output.recommendations if r.status == RecommendationStatus.APPROVED.value]
    avg_feas = (
        statistics.mean(r.average_feasibility for r in approved)
        if approved else 0.0
    )
    rs = output.repair_stats
    recovery_rate = (
        rs.recommendations_recovered / rs.recommendations_repaired
        if rs.recommendations_repaired > 0 else 0.0
    )

    return RunMetrics(
        prompt_idx=prompt_idx,
        category=category,
        prompt=prompt_text[:80],
        mode=mode,
        latency_ms=output.budget_usage.wallclock_ms,
        total_tokens=output.budget_usage.total_tokens,
        llm_calls=output.budget_usage.llm_calls,
        recommendations_approved=len(approved),
        avg_feasibility=round(avg_feas, 1),
        repair_recovery_rate=round(recovery_rate, 2),
        termination_reason=output.termination_reason,
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _percentile(data: list[float], pct: int) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * pct / 100)
    idx = min(idx, len(sorted_data) - 1)
    return sorted_data[idx]


def _generate_report(results: list[RunMetrics]) -> str:
    lines: list[str] = []
    lines.append("# Hivemind Benchmark Report: Simple vs Full Mode")
    lines.append("")
    lines.append(f"**Prompts:** {len(results) // 2}  ")
    lines.append(f"**Modes:** simple, full  ")
    lines.append(f"**LLM backend:** MockLLM (deterministic)  ")
    lines.append("")

    # Per-run table
    lines.append("## Per-Run Results")
    lines.append("")
    lines.append("| # | Category | Mode | Latency(ms) | Tokens | LLM Calls | Approved | Avg Feas | Recovery | Termination |")
    lines.append("|---|----------|------|-------------|--------|-----------|----------|----------|----------|-------------|")

    for r in results:
        lines.append(
            f"| {r.prompt_idx} | {r.category} | {r.mode} | {r.latency_ms} | "
            f"{r.total_tokens} | {r.llm_calls} | {r.recommendations_approved} | "
            f"{r.avg_feasibility} | {r.repair_recovery_rate} | {r.termination_reason} |"
        )

    lines.append("")

    # Aggregated summary by mode
    lines.append("## Aggregated Summary")
    lines.append("")
    lines.append("| Metric | Simple (mean) | Simple (p50) | Simple (p95) | Full (mean) | Full (p50) | Full (p95) |")
    lines.append("|--------|--------------|-------------|-------------|------------|-----------|-----------|")

    for metric_name, getter in [
        ("Latency (ms)", lambda r: r.latency_ms),
        ("Total tokens", lambda r: r.total_tokens),
        ("LLM calls", lambda r: r.llm_calls),
        ("Approved recs", lambda r: r.recommendations_approved),
        ("Avg feasibility", lambda r: r.avg_feasibility),
        ("Recovery rate", lambda r: r.repair_recovery_rate),
    ]:
        simple_vals = [float(getter(r)) for r in results if r.mode == "simple"]
        full_vals = [float(getter(r)) for r in results if r.mode == "full"]

        s_mean = round(statistics.mean(simple_vals), 1) if simple_vals else 0
        s_p50 = round(_percentile(simple_vals, 50), 1)
        s_p95 = round(_percentile(simple_vals, 95), 1)
        f_mean = round(statistics.mean(full_vals), 1) if full_vals else 0
        f_p50 = round(_percentile(full_vals, 50), 1)
        f_p95 = round(_percentile(full_vals, 95), 1)

        lines.append(
            f"| {metric_name} | {s_mean} | {s_p50} | {s_p95} | {f_mean} | {f_p50} | {f_p95} |"
        )

    lines.append("")

    # Termination reason distribution
    lines.append("## Termination Reasons")
    lines.append("")
    for mode in ("simple", "full"):
        mode_results = [r for r in results if r.mode == mode]
        reasons: dict[str, int] = {}
        for r in mode_results:
            reasons[r.termination_reason] = reasons.get(r.termination_reason, 0) + 1
        lines.append(f"**{mode}:** " + ", ".join(f"{k}: {v}" for k, v in sorted(reasons.items())))
    lines.append("")

    # Cost/quality tradeoff
    lines.append("## Cost/Quality Tradeoff")
    lines.append("")

    simple_tokens = [r.total_tokens for r in results if r.mode == "simple"]
    full_tokens = [r.total_tokens for r in results if r.mode == "full"]
    simple_calls = [r.llm_calls for r in results if r.mode == "simple"]
    full_calls = [r.llm_calls for r in results if r.mode == "full"]
    simple_approved = [r.recommendations_approved for r in results if r.mode == "simple"]
    full_approved = [r.recommendations_approved for r in results if r.mode == "full"]

    s_tok_avg = statistics.mean(simple_tokens) if simple_tokens else 0
    f_tok_avg = statistics.mean(full_tokens) if full_tokens else 0
    s_call_avg = statistics.mean(simple_calls) if simple_calls else 0
    f_call_avg = statistics.mean(full_calls) if full_calls else 0
    s_app_avg = statistics.mean(simple_approved) if simple_approved else 0
    f_app_avg = statistics.mean(full_approved) if full_approved else 0

    if s_tok_avg > 0:
        tok_ratio = f_tok_avg / s_tok_avg
    else:
        tok_ratio = 0

    lines.append(
        f"Simple mode uses an average of {s_tok_avg:.0f} tokens and {s_call_avg:.0f} LLM calls "
        f"per run, producing {s_app_avg:.1f} approved recommendations on average. "
        f"Full mode uses {f_tok_avg:.0f} tokens and {f_call_avg:.0f} LLM calls "
        f"({tok_ratio:.1f}x the cost), producing {f_app_avg:.1f} approved recommendations."
    )
    lines.append("")

    # Recommendation
    lines.append("## Recommendation")
    lines.append("")
    lines.append(
        "**Simple mode** is recommended as the default. It provides adequate recommendations "
        "at a fraction of the cost and latency, with deterministic termination. Full mode "
        "should be offered as an opt-in for users who need deeper multi-perspective synthesis "
        "and are willing to accept higher cost and latency. The effort_level selector gives "
        "users fine-grained control over the cost/quality tradeoff within each mode."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    prompts_path = Path(__file__).parent / "benchmark_prompts.json"
    report_path = Path(__file__).parent / "benchmark_report.md"

    with open(prompts_path) as f:
        prompts = json.load(f)

    print(f"Loaded {len(prompts)} prompts from {prompts_path}")

    storage = _BenchmarkStorage()
    vector_store = _BenchmarkVectorStore()

    results: list[RunMetrics] = []

    for idx, p in enumerate(prompts):
        category = p["category"]
        prompt_text = p["prompt"]

        for mode in ("simple", "full"):
            print(f"  [{idx+1}/{len(prompts)}] {category} / {mode}...", end=" ", flush=True)
            metrics = _run_single(idx + 1, category, prompt_text, mode, storage, vector_store)
            results.append(metrics)
            print(f"done ({metrics.llm_calls} calls, {metrics.termination_reason})")

    report = _generate_report(results)

    with open(report_path, "w") as f:
        f.write(report)

    print(f"\nReport written to {report_path}")
    print(f"Total runs: {len(results)}")


if __name__ == "__main__":
    main()
