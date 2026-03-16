# Hivemind: Product Pitch vs. Codebase Alignment Plan

This document identifies where the current software infrastructure diverges from the
product described in the Hivemind Product Pitch, and prescribes how to correct each flaw.

---

## Severity Key

- **P0 (Critical):** Core product promise is broken or unusable
- **P1 (Important):** Degrades product quality, security, or correctness
- **P2 (Moderate):** Technical debt or polish issue

---

## P0 - Critical Misalignments

### 1. Dynamic Theory Unit Creation Is Stubbed Out

**Pitch requirement:** The theory network density value determines how knowledge base
*documents* are distributed across dynamically-created theory units. Each unit receives
complete documents such that its total token count approximates the density value. The
number of units is an emergent result of this distribution.

**Current state:** `_get_document_token_counts()` in `debate.py:47-67` returns an empty
dict. The fallback on line 536 hardcodes every KB ID to 2000 tokens. Furthermore, the
code distributes *knowledge base IDs*, not individual *documents* within those KBs.

**Fix:**
1. Add a `get_documents_for_knowledge_bases(kb_ids) -> list[DocumentMeta]` method to
   `StorageInterface` that returns document ID, filename, and `token_count` for every
   `KnowledgeDocument` belonging to the specified KBs.
2. Implement this method in `PostgresStorage` by querying `knowledge_documents` joined
   with `text_chunks` (sum of `token_count` per document, or use the already-extracted
   text length / 4 as approximation).
3. Rewrite `_get_document_token_counts()` to call this new method and return
   `{document_id: token_count}`.
4. Rewrite `_create_dynamic_units()` to distribute *documents* (not KB IDs) into units.
   Each unit should receive whole documents until its cumulative token count approximates
   the density value (no document splitting).
5. Rewrite `_dynamic_unit_to_agent()` so each dynamic unit's RAG retrieval pulls only
   from chunks belonging to its assigned documents (not entire KBs). This may require
   adding a `document_ids` filter to `VectorStoreInterface.retrieve()`.

**Files:** `cloud/hivemind_core/debate.py`, `cloud/hivemind_core/types.py`,
`cloud/app/adapters/storage.py`, `cloud/app/adapters/vector_db.py`

---

### 2. Density Slider Range Is Hardcoded, Not Data-Driven

**Pitch requirement:** The density value has "a minimum value of the number of tokens in
the self-enclosed strategic theory document with the smallest number of tokens, and a
maximum value of the sum of all tokens across all the strategic theory documents."

**Current state:** The client slider is hardcoded `min=1000, max=50000` in
`client/src/App.tsx:462-470`.

**Fix:**
1. Add a `GET /knowledge-bases/density-bounds` endpoint that queries all published
   theory agent knowledge bases, computes `min_doc_tokens` and `sum_all_doc_tokens`,
   and returns them.
2. In the client app, fetch these bounds after login / agent sync and use them as the
   slider's min/max. Fall back to current hardcoded values if the endpoint fails.

**Files:** `cloud/app/routers/knowledge_bases.py`, `client/src/api/client.ts`,
`client/src/App.tsx`

---

### 3. `revision_strength` Is Accepted But Never Used

**Pitch requirement:** "The degree to which theory network units revise their solution
when receiving criticism" is one of the key dynamics that must be balanced.

**Current state:** `HivemindInput.revision_strength` (default 0.5) is carried through
from client to engine but never referenced in `debate.py`. Units currently revise with
no guidance on how aggressively to incorporate feedback.

**Fix:**
Inject `revision_strength` into the revision prompt (`_create_revision_prompt`). At low
values (0.0-0.3) the prompt should instruct the unit to mostly preserve its original
position and only incorporate feedback it strongly agrees with. At high values (0.7-1.0)
the prompt should instruct the unit to fully integrate all valid critique. At moderate
values, use balanced language. Example addition to the revision system prompt:

```
Revision intensity: {revision_strength:.0%}. At this level, you should
{"minimally adjust — only accept feedback you strongly agree with" if low,
 "moderately revise — balance your original reasoning with valid critique" if mid,
 "thoroughly revise — integrate all constructive feedback fully" if high}.
```

**Files:** `cloud/hivemind_core/debate.py`

---

### 4. `practicality_criticality` Is Accepted But Never Used

**Pitch requirement:** "The degree to which practicality network units are critical of
the solutions they receive" is a key dynamic.

**Current state:** `HivemindInput.practicality_criticality` (default 0.5) is never
referenced in `debate.py` or `agents.py`.

**Fix:**
Inject `practicality_criticality` into the feasibility evaluation query in
`run_debate()` (line ~813). At low values the prompt should instruct practicality agents
to be lenient, at high values to be extremely strict. This modulates how harshly they
score, directly affecting whether solutions survive the veto gate. Example:

```
Evaluation strictness: {practicality_criticality:.0%}.
{"Be lenient — only flag major, deal-breaking concerns." if low,
 "Be balanced in your assessment." if mid,
 "Be extremely strict — flag every possible risk and concern." if high}
```

**Files:** `cloud/hivemind_core/debate.py`

---

### 5. Streaming Analysis Endpoint Is Broken

**Pitch context:** Real-time progress feedback is essential for long-running analyses
(the debate loop can take minutes).

**Current state:** `engine.py:9` imports `run_debate_streaming` from
`hivemind_core.debate`, but no such function exists in `debate.py`. The SSE streaming
endpoint (`POST /analysis/run/stream`) and the WebSocket handler both call
`engine.analyze_streaming()`, which delegates to the missing function. These will crash
at runtime.

**Fix:**
1. Implement `run_debate_streaming()` in `debate.py` as a generator that mirrors
   `run_debate()` but yields progress events at each major stage: `debate_start`,
   `initial_solutions`, `round_start`, `critiques_completed`, `revisions_completed`,
   `aggregation_update`, `feasibility_evaluation`, `veto`, `complete`.
2. Each yielded event should be a dict with `type` and relevant payload so the
   WebSocket/SSE layer can forward it to clients.

**Files:** `cloud/hivemind_core/debate.py`, `cloud/hivemind_core/engine.py`

---

### 6. No Client Data Collection or Internet Scraping

**Pitch requirement:** "Before the client prompts Hivemind, the tool will have access to
any and all data the client has cleared for collection and usage by the model — as well
as data scraped from the internet."

**Current state:** The client provides a single text area for pasting context. There is
no structured data management, no persistent client data store, and no internet scraping.

**Fix (phased):**

**Phase A - Client-Cleared Data Management:**
1. Add a `ClientData` model: `id`, `client_id`, `data_type` (document/text/structured),
   `content`, `filename`, `uploaded_at`.
2. Add CRUD endpoints under `/clients/{id}/data` for uploading, listing, and deleting
   client-cleared data.
3. In the client app, add a "My Data" panel where the user can upload documents, paste
   text snippets, or provide structured data. These persist across sessions.
4. When running an analysis, automatically include all client-cleared data as context
   items (in addition to the query).

**Phase B - Internet Data Scraping:**
1. Add a web scraping service (e.g., using `httpx` + `BeautifulSoup` or a headless
   browser) that can fetch and extract text from URLs.
2. Add a `/scrape` endpoint or integrate it into the analysis pipeline so agents can
   reference internet data.
3. Consider rate limiting, caching, and content filtering for safety.

**Files:** New model, new router, `client/src/App.tsx`, `cloud/app/services/`

---

## P1 - Important Issues

### 7. No Authentication Enforcement on API Routes

**Pitch context:** The product serves paying clients with licensed access. Routes must
be protected.

**Current state:** JWT tokens are generated at login but never verified on any endpoint.
Agents, knowledge bases, simulations, analyses, and client routes are all unprotected.

**Fix:**
1. Create a `get_current_user` dependency in `cloud/app/deps.py` that extracts and
   validates the JWT from the `Authorization: Bearer <token>` header.
2. Apply this dependency to all routers except `/auth/login`, `/health`, and
   `/admin/ping`.
3. For client-facing routes, create a `get_current_client` dependency that validates
   client JWTs issued via `/auth/client-connect`.

**Files:** `cloud/app/deps.py`, all routers

---

### 8. Published Agent Filtering Broken on Client Sync

**Pitch context:** Clients should only see published agents.

**Current state:** The client calls `GET /agents?status=published` but the agents
router's `list_agents` endpoint doesn't accept a `status` query parameter. It returns
all agents regardless of status.

**Fix:**
Add an optional `status` query parameter to `GET /agents`:
```python
@router.get("/agents")
def list_agents(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(AgentDefinition)
    if status:
        query = query.filter(AgentDefinition.status == status)
    return query.all()
```

**Files:** `cloud/app/routers/agents.py`

---

### 9. Duplicate Interface Definitions Cause Confusion

**Current state:** `StorageInterface`, `VectorStoreInterface`, and `LLMInterface` are
defined in both `hivemind_core/types.py` AND `hivemind_core/interfaces.py` with
different method signatures. Similarly, `PostgresStorage` (in `app/adapters/storage.py`)
and `SQLAlchemyStorage` (in `hivemind_core/adapters/sqlalchemy_storage.py`) overlap.

**Fix:**
1. Canonicalize interfaces in `types.py` only. Remove duplicates from `interfaces.py`
   or have `interfaces.py` re-export from `types.py`.
2. Consolidate storage adapters: keep `PostgresStorage` in `app/adapters/` as the
   production implementation. If `SQLAlchemyStorage` adds extra methods, merge them into
   `PostgresStorage` and delete the duplicate.
3. Update all imports throughout the codebase.

**Files:** `cloud/hivemind_core/interfaces.py`, `cloud/hivemind_core/types.py`,
`cloud/hivemind_core/adapters/sqlalchemy_storage.py`, `cloud/app/adapters/storage.py`

---

### 10. Monitor Aggregation Uses Expensive LLM Calls for Similarity

**Pitch note:** "It is likely for the monitor AI a simple LLM will not work — the
emphasis of the monitor's function is on aggregation and summarization, not content
generation."

**Current state:** `_compute_solution_similarity()` makes a full LLM call per pair of
solutions (O(N^2) calls). This is extremely expensive and slow. With 5 units, that's
10 similarity calls per round, each costing money and time.

**Fix:**
1. Replace LLM-based similarity with embedding-based similarity. Embed each solution
   using the same `SentenceTransformer` model used for RAG, then compute cosine
   similarity between embeddings. This is instant and free.
2. Keep the LLM-based merge (`_merge_solution_cluster`) for producing the merged
   recommendation text, since that genuinely requires language generation.
3. This aligns with the pitch's note that the monitor should NOT be a typical LLM -
   it should emphasize aggregation logic.

**Files:** `cloud/hivemind_core/debate.py`

---

### 11. Duplicate / Conflicting WebSocket Handlers

**Current state:** Both `cloud/app/ws/analysis.py` and `cloud/app/ws/handlers.py`
define WebSocket analysis endpoints at the same path. The `analysis.py` version
references `ContextType.STRUCTURED_DATA` which doesn't exist in the enum (it should be
`ContextType.STRUCTURED`).

**Fix:**
1. Delete `cloud/app/ws/analysis.py` (the `handlers.py` version is the one actually
   imported).
2. Ensure `handlers.py` references the correct `ContextType.STRUCTURED` enum value.

**Files:** `cloud/app/ws/analysis.py`, `cloud/app/ws/__init__.py`

---

### 12. Use Case Profile / Decision Type Columns May Not Exist

**Current state:** The analysis router (`_resolve_agents_by_profile_and_decision`)
queries `AgentDefinition.use_case_profile` and `KnowledgeBase.decision_types`, but
these columns don't appear in the SQLAlchemy model definitions.

**Fix:**
1. Add `use_case_profile = Column(String, nullable=True)` to the `AgentDefinition`
   model.
2. Add `decision_types = Column(JSONB, default=[])` to the `KnowledgeBase` model.
3. Add corresponding fields to the admin UI so admins can tag agents and KBs.
4. Run a migration or rely on `auto_create_tables` to add the columns.

**Files:** `cloud/app/models/agent.py`, `cloud/app/models/knowledge_base.py`,
`admin/src/pages/AgentEdit.tsx`, `admin/src/pages/KnowledgeBases.tsx`

---

## P2 - Moderate Issues

### 13. Critique Strengths/Weaknesses/Suggestions Not Parsed

**Current state:** When critiques are generated (line ~688-698), the `Critique` object's
`strengths`, `weaknesses`, and `suggestions` lists are always empty. Only
`critique_text` is populated. The revision prompt references these fields, so they
appear as "None noted" / "None provided."

**Fix:**
Parse the LLM's critique response to extract structured strengths, weaknesses, and
suggestions. Use section header detection similar to `_parse_feasibility_score()`.

**Files:** `cloud/hivemind_core/debate.py`

---

### 14. Solution and Reasoning Are Identical

**Current state:** In `run_debate()` lines 620-628, when creating `TheoryUnitSolution`,
both `solution` and `reasoning` are set to `result.response`. The pitch describes them
as separate: the solution is the strategic recommendation, the reasoning is the
theoretical justification.

**Fix:**
Modify the theory agent prompt to produce output in a structured format with separate
`SOLUTION:` and `REASONING:` sections. Parse the response to split them. This ensures
the monitor can pass solutions without justifications to the practicality network (per
the pitch), while retaining justifications for the final output.

**Files:** `cloud/hivemind_core/agents.py`, `cloud/hivemind_core/debate.py`

---

### 15. No Test Suite

**Current state:** No tests exist. The pitch describes a complex multi-agent workflow
with specific convergence, veto, and restart behaviors that are easy to get wrong.

**Fix:**
1. Add `pytest` to requirements and create a `cloud/tests/` directory.
2. Write unit tests for: `_create_dynamic_units()`, `_aggregate_similar_solutions()`,
   `_parse_feasibility_score()`, `run_simulation()`.
3. Write integration tests for: full `run_debate()` flow using `MockLLM`, veto/restart
   behavior, sufficiency convergence.

**Files:** `cloud/tests/`, `cloud/requirements.txt`

---

### 16. Inline HTML Dashboards in main.py

**Current state:** `main.py` contains ~300+ lines of inline HTML for the server
dashboard and knowledge browser. This is fragile and hard to maintain.

**Fix:**
Move the HTML templates to separate files (e.g., `cloud/app/templates/dashboard.html`,
`cloud/app/templates/knowledge_browser.html`) and serve them via
`FileResponse` or Jinja2 templates.

**Files:** `cloud/app/main.py`, new template files

---

### 17. Simulation Formulas Not Actually Invoked During Debate

**Current state:** Theory agents receive simulation formulas as part of their system
prompt (listing available formulas with their inputs/outputs). However, there is no
mechanism for agents to actually *execute* a simulation during the debate. The prompt
says "if a simulation is helpful, use the formulas and show your inputs and computed
outputs explicitly," but the agent can only describe what the simulation would do -
it cannot call `run_simulation()`.

**Fix (two options):**
- **Option A (simpler):** Keep the current approach where agents describe simulation
  usage in their text. This is acceptable if the simulations are simple enough to be
  computed by the LLM.
- **Option B (full implementation):** Implement tool-use / function-calling so theory
  agents can invoke simulations mid-response. This requires using Anthropic's tool-use
  API feature, defining simulation formulas as callable tools, executing them, and
  injecting results back into the conversation. This is more complex but aligns with
  the pitch's intent.

**Files:** `cloud/hivemind_core/agents.py`, `cloud/hivemind_core/llm.py`

---

## Implementation Order

Recommended sequence (respecting dependencies):

1. **P0-1** Dynamic unit creation fix (foundational to product correctness)
2. **P0-3 + P0-4** Wire revision_strength and practicality_criticality
3. **P0-5** Implement streaming debate
4. **P1-8** Fix published agent filtering
5. **P1-9** Consolidate duplicate interfaces
6. **P1-10** Replace LLM similarity with embedding similarity
7. **P1-11** Clean up WebSocket duplicates
8. **P2-14** Separate solution from reasoning in output
9. **P2-13** Parse critique structure
10. **P0-2** Data-driven density slider bounds
11. **P1-7** Add auth enforcement
12. **P1-12** Add use_case_profile / decision_types columns
13. **P0-6** Client data management (Phase A)
14. **P2-15** Test suite
15. **P2-17** Simulation tool-use (if pursuing Option B)
16. **P0-6** Internet scraping (Phase B)
17. **P2-16** Extract inline HTML

---

*Generated 2026-03-01 by automated codebase analysis.*
