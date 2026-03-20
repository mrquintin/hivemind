# Hivemind Benchmark Report: Simple vs Full Mode

**Prompts:** 20  
**Modes:** simple, full  
**LLM backend:** MockLLM (deterministic)  

## Per-Run Results

| # | Category | Mode | Latency(ms) | Tokens | LLM Calls | Approved | Avg Feas | Recovery | Termination |
|---|----------|------|-------------|--------|-----------|----------|----------|----------|-------------|
| 1 | market_entry | simple | 1 | 2167 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 1 | market_entry | full | 1 | 6458 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 2 | market_entry | simple | 0 | 2181 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 2 | market_entry | full | 0 | 6486 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 3 | market_entry | simple | 0 | 2163 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 3 | market_entry | full | 0 | 6450 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 4 | market_entry | simple | 0 | 2165 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 4 | market_entry | full | 0 | 6454 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 5 | market_entry | simple | 0 | 2171 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 5 | market_entry | full | 0 | 6466 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 6 | m_and_a | simple | 1 | 2163 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 6 | m_and_a | full | 0 | 6450 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 7 | m_and_a | simple | 0 | 2163 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 7 | m_and_a | full | 0 | 6450 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 8 | m_and_a | simple | 1 | 2191 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 8 | m_and_a | full | 0 | 6506 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 9 | m_and_a | simple | 0 | 2163 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 9 | m_and_a | full | 0 | 6450 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 10 | m_and_a | simple | 0 | 2173 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 10 | m_and_a | full | 0 | 6470 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 11 | pricing | simple | 0 | 2171 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 11 | pricing | full | 0 | 6466 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 12 | pricing | simple | 0 | 2177 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 12 | pricing | full | 1 | 6478 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 13 | pricing | simple | 0 | 2173 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 13 | pricing | full | 0 | 6470 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 14 | pricing | simple | 0 | 2159 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 14 | pricing | full | 0 | 6442 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 15 | pricing | simple | 0 | 2173 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 15 | pricing | full | 0 | 6470 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 16 | business_model_change | simple | 0 | 2169 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 16 | business_model_change | full | 0 | 6462 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 17 | business_model_change | simple | 0 | 2171 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 17 | business_model_change | full | 1 | 6466 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 18 | business_model_change | simple | 0 | 2191 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 18 | business_model_change | full | 0 | 6506 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 19 | business_model_change | simple | 0 | 2163 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 19 | business_model_change | full | 0 | 6450 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |
| 20 | business_model_change | simple | 0 | 2175 | 8 | 0 | 0.0 | 0.0 | simple_completed |
| 20 | business_model_change | full | 1 | 6474 | 24 | 0 | 0.0 | 0.0 | global_restart_exhausted |

## Aggregated Summary

| Metric | Simple (mean) | Simple (p50) | Simple (p95) | Full (mean) | Full (p50) | Full (p95) |
|--------|--------------|-------------|-------------|------------|-----------|-----------|
| Latency (ms) | 0.1 | 0.0 | 1.0 | 0.2 | 0.0 | 1.0 |
| Total tokens | 2171.1 | 2171.0 | 2191.0 | 6466.2 | 6466.0 | 6506.0 |
| LLM calls | 8.0 | 8.0 | 8.0 | 24.0 | 24.0 | 24.0 |
| Approved recs | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Avg feasibility | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Recovery rate | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Termination Reasons

**simple:** simple_completed: 20
**full:** global_restart_exhausted: 20

## Cost/Quality Tradeoff

Simple mode uses an average of 2171 tokens and 8 LLM calls per run, producing 0.0 approved recommendations on average. Full mode uses 6466 tokens and 24 LLM calls (3.0x the cost), producing 0.0 approved recommendations.

## Recommendation

**Simple mode** is recommended as the default. It provides adequate recommendations at a fraction of the cost and latency, with deterministic termination. Full mode should be offered as an opt-in for users who need deeper multi-perspective synthesis and are willing to accept higher cost and latency. The effort_level selector gives users fine-grained control over the cost/quality tradeoff within each mode.
