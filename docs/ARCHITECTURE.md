# Hivemind Architecture

This document maps the Hivemind product specification to the codebase and describes the architecture for strategic analysis software development.

---

## Product Vision

**Mission**: Democratize rigorous academia in business strategy. Career-focused individuals and small organizations should make strategic decisions like educated, rigorously refined business experts.

**Core workflow**: Prompt → Theory Network → Monitor → Practicality Network → Output

---

## System Components

| Component | Purpose | Location |
|-----------|---------|----------|
| **Cloud** | Python server: AI orchestration, RAG, debate engine, storage | `cloud/` |
| **Admin** | Desktop app: build agents, upload documents, manage knowledge bases | `admin/` |
| **Client** | Desktop app: run analyses, view recommendations | `client/` |
| **Hivemind Core** | Platform-agnostic analysis engine (theory network, monitor, practicality network) | `cloud/hivemind_core/` |

---

## Client Prompt Input

Per the product spec, the client prompt has four components:

1. **Textual problem description** — text box
2. **Sufficiency value** — sliding scale (target number of aggregate conclusions)
3. **Feasibility value** — sliding scale 1–100 (veto threshold)
4. **Theory network density** — sliding scale (token count per theory unit)

Additional parameters (key dynamics):

- **Similarity threshold** — how similar solutions must be for the monitor to lump them (0–1)
- **Revision strength** — how much theory units revise when receiving criticism (0–1)
- **Practicality criticality** — how critical practicality units are when scoring (0–1)

Use-case profiles and decision types can resolve agents server-side instead of manual selection.

---

## Theory Network

- **Units**: Variable number of AI units, each with a portion of the strategic knowledge base.
- **Density**: Theory network density determines token size per unit. Documents are assigned so each unit’s KB is ~equal in tokens.
- **Flow**: Units generate initial solutions → critique each other → revise → repeat until monitor aggregates to sufficiency.

---

## Monitor

- **Role**: Aggregates similar solutions, counts unique aggregate conclusions.
- **Stopping condition**: When unique conclusions ≤ sufficiency value, passes solutions to practicality network.
- **Note**: Monitor is aggregation/summarization-focused; a simple LLM may not suffice for production.

---

## Practicality Network

- **Role**: Each unit scores each solution 1–100.
- **Veto**: If average feasibility ≤ feasibility threshold, entire list is vetoed; theory network restarts from scratch.
- **Tailoring**: Use-case profiles (small business, individual career, enterprise) adjust knowledge bases (e.g., legal/PR vs. social/occupational feasibility).

---

## Codebase Structure

```
cloud/
├── app/
│   ├── main.py              # FastAPI app, routes, dashboard/knowledge-browser
│   ├── config.py            # Environment settings
│   ├── engine.py            # Engine factory: create_engine(db) → HivemindEngine
│   ├── adapters/            # App-specific implementations
│   │   ├── llm.py           # ClaudeAdapter (LLMInterface)
│   │   ├── storage.py       # PostgresStorage (StorageInterface)
│   │   └── vector_db.py     # QdrantVectorDB (VectorStoreInterface)
│   ├── routers/             # REST API
│   ├── schemas/             # Request/response models
│   ├── services/            # Thin wrappers (agent_execution → engine)
│   ├── models/              # SQLAlchemy models
│   ├── rag/                 # Embeddings, chunking, vector store ops
│   └── templates/           # HTML for dashboard, knowledge browser
│
├── hivemind_core/           # Platform-agnostic engine
│   ├── engine.py            # HivemindEngine
│   ├── debate.py            # run_debate, run_debate_streaming
│   ├── agents.py            # execute_agent, prompt builders
│   ├── rag.py               # retrieve_chunks, format_chunks_for_prompt
│   ├── types.py             # HivemindInput, HivemindOutput, interfaces
│   └── adapters/            # Alternative backends (Qdrant, SQLAlchemy)
```

---

## Engine and Adapters

All analysis flows (REST `/analysis/run`, agent test, WebSocket) should use:

```python
from app.engine import create_engine

engine = create_engine(db)
output = engine.analyze(hivemind_input)
```

`create_engine(db)` returns a `HivemindEngine` configured with:

- **ClaudeAdapter** — LLM (Anthropic)
- **QdrantVectorDB** — RAG retrieval
- **PostgresStorage** — agents, knowledge bases, simulations

---

## Remaining Gaps (per DEVELOPMENT_PLAN)

- Client-cleared data pipeline (upload, consent, `context_documents` flow)
- Scraped internet data ingestion
- Simulations as Python programs (currently formula-based)
- Dedicated monitor aggregation model
- Export & distribution (PKG installers, First Run Setup)

---

## Key Dynamics (Tunable)

1. Revision strength — how much units revise when criticized
2. Similarity threshold — monitor’s propensity to lump solutions
3. Practicality criticality — how strict practicality units are

These are exposed in the API and client UI.
