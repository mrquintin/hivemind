# Codex Task: Hivemind Codebase Remediation

You are operating on the Hivemind codebase — a multi-agent strategic analysis platform built with a Python/FastAPI backend (`cloud/`), a React+Tauri admin desktop app (`admin/`), and a React+Tauri client desktop app (`client/`). The core engine lives at `cloud/hivemind_core/` and orchestrates a multi-agent debate protocol: theory network units generate solutions, critique and revise each other iteratively, a monitor aggregates convergent solutions, a practicality network scores feasibility, and a veto gate can restart the entire pipeline.

The codebase has 17 verified defects — functional stubs, dead codepaths, unused parameters, broken imports, and missing infrastructure — that cause it to diverge from its specification. Execute all fixes below in the order listed. Each fix specifies the affected files, the current defective behavior, and the exact correction required.

Constraints:
- Preserve all existing public API contracts (endpoint paths, request/response schemas, function signatures) unless a fix explicitly requires changing them.
- Do not introduce new dependencies unless a fix explicitly calls for one.
- Do not refactor, rename, or reorganize code beyond what each fix prescribes.
- Where a fix asks you to add a prompt template string, use f-strings with the variable names specified.
- Run no destructive git operations.

---

## Fix 1 — Implement dynamic theory unit creation (currently stubbed)

**Files:** `cloud/hivemind_core/debate.py`, `cloud/hivemind_core/types.py`, `cloud/app/adapters/storage.py`, `cloud/app/adapters/vector_db.py`

**Defect:** `_get_document_token_counts()` at `debate.py:47-67` returns an empty `dict`. The fallback at line 536 hardcodes all KB IDs to 2000 tokens. The function `_create_dynamic_units()` distributes knowledge base IDs rather than individual document IDs, violating the spec that whole documents are assigned to units.

**Correction:**

1. In `StorageInterface` (`types.py`), add method signature:
```python
def get_documents_for_knowledge_bases(self, kb_ids: list[str]) -> list[dict]:
    """Return list of dicts with keys: document_id, knowledge_base_id, filename, token_count."""
    raise NotImplementedError
```

2. Implement in `PostgresStorage` (`cloud/app/adapters/storage.py`): query the `knowledge_documents` table joined with `text_chunks`, grouping by `document_id` to sum `token_count`. Return one dict per document.

3. Rewrite `_get_document_token_counts()` to accept `storage: StorageInterface` and `knowledge_base_ids: list[str]`, call `storage.get_documents_for_knowledge_bases(knowledge_base_ids)`, and return `{doc["document_id"]: doc["token_count"] for doc in results}`.

4. Rewrite `_create_dynamic_units()` to accept and distribute *document IDs* (not KB IDs). Pack documents greedily into units: for each unit, append documents until cumulative token count >= `density_value` (allow up to 1.2x overshoot; every unit must contain at least one document). Set `DynamicTheoryUnit.assigned_document_ids` to the list of document IDs in that unit.

5. Update `_dynamic_unit_to_agent()`: set `knowledge_base_ids` on the resulting `AgentDefinition` to the unit's `assigned_document_ids` (these will be used as document-level filters in RAG retrieval).

6. Add a `document_ids: list[str] | None = None` parameter to `VectorStoreInterface.retrieve()`. When provided, filter Qdrant query results to only return chunks whose `document_id` payload field is in the provided list. Implement this filter in `QdrantVectorDB` (`cloud/app/adapters/vector_db.py`).

7. Update the call site in `run_debate()` (line ~536): replace the hardcoded placeholder dict with a call to the rewritten `_get_document_token_counts(storage, all_kb_ids)`.

---

## Fix 2 — Expose data-driven density slider bounds

**Files:** `cloud/app/routers/knowledge_bases.py`, `client/src/api/client.ts`, `client/src/App.tsx`

**Defect:** The theory network density slider in `client/src/App.tsx:462-470` is hardcoded `min=1000, max=50000`. The spec requires bounds derived from actual document token counts: min = smallest single document's token count, max = sum of all document token counts across all knowledge bases attached to published theory agents.

**Correction:**

1. Add `GET /knowledge-bases/density-bounds` to the knowledge bases router. Query all `AgentDefinition` rows where `network_type == "theory"` and `status == "published"`, collect their `knowledge_base_ids`, query `text_chunks` for those KBs, group by `document_id`, compute per-document token sums, then return `{"min_tokens": <smallest document sum>, "max_tokens": <total across all documents>}`. Return `{"min_tokens": 1000, "max_tokens": 50000}` as fallback if no data exists.

2. In `client/src/api/client.ts`, add `getDensityBounds(): Promise<{min_tokens: number, max_tokens: number}>` calling this endpoint.

3. In `client/src/App.tsx`, fetch density bounds after agent sync and use them as the slider's `min` and `max` props. Fall back to `1000`/`50000` on error.

---

## Fix 3 — Wire `revision_strength` into debate revision prompts

**Files:** `cloud/hivemind_core/debate.py`

**Defect:** `HivemindInput.revision_strength` (float, 0.0–1.0, default 0.5) is accepted from the client and stored on `input_data` but never referenced during the critique-revision loop.

**Correction:**

1. Thread `input_data.revision_strength` into `_create_revision_prompt()` by adding a `revision_strength: float` parameter.

2. Append to the revision prompt a directive that modulates revision aggressiveness:
   - If `revision_strength < 0.3`: instruct the unit to preserve its original position and only incorporate feedback it strongly agrees with.
   - If `0.3 <= revision_strength <= 0.7`: instruct the unit to balance its original reasoning with valid critique.
   - If `revision_strength > 0.7`: instruct the unit to thoroughly integrate all constructive feedback.

3. Update the call site in `run_debate()` (inside the revision loop, ~line 718) to pass `input_data.revision_strength` to the rewritten function.

---

## Fix 4 — Wire `practicality_criticality` into feasibility evaluation

**Files:** `cloud/hivemind_core/debate.py`

**Defect:** `HivemindInput.practicality_criticality` (float, 0.0–1.0, default 0.5) is accepted but never referenced. Practicality agents evaluate solutions with no guidance on strictness.

**Correction:**

Modify the feasibility evaluation query construction in `run_debate()` (~line 813). Append a strictness directive to `eval_query` based on `input_data.practicality_criticality`:
- If `< 0.3`: "Be lenient — only flag major, deal-breaking concerns."
- If `0.3–0.7`: "Be balanced in your assessment."
- If `> 0.7`: "Be extremely strict — flag every possible risk and concern."

---

## Fix 5 — Implement `run_debate_streaming()` generator

**Files:** `cloud/hivemind_core/debate.py`, `cloud/hivemind_core/engine.py`

**Defect:** `engine.py:9` imports `run_debate_streaming` from `hivemind_core.debate`, but no such function exists. The SSE endpoint `POST /analysis/run/stream` and the WebSocket handler both call `engine.analyze_streaming()`, which delegates to this missing function. Both crash at runtime with `ImportError`.

**Correction:**

Implement `run_debate_streaming()` in `debate.py` as a Python generator with the same signature as `run_debate()` plus identical internal logic, but yielding `dict` events at each pipeline stage instead of only returning the final `HivemindOutput`. Required event types and their payloads:

| `type` | Yield point | Payload keys |
|---|---|---|
| `"debate_start"` | After theory agent resolution | `theory_agents`, `practicality_agents`, `veto_restart` |
| `"initial_solutions"` | After all initial solutions generated | `count`, `solutions` (list of unit names) |
| `"round_start"` | At top of each critique-revision iteration | `round`, `solutions_count`, `aggregated_count` |
| `"critiques_completed"` | After all critiques in a round | `round`, `total_critiques` |
| `"revisions_completed"` | After all revisions in a round | `round`, `revised_count` |
| `"aggregation_update"` | After re-aggregation | `round`, `aggregated_count`, `target_sufficiency` |
| `"feasibility_evaluation"` | After each practicality agent scores a rec | `agent_name`, `recommendation_title`, `score` |
| `"veto"` | When veto triggered | `threshold`, `restart_number` |
| `"complete"` | End of pipeline | `output` (the full `HivemindOutput`) |

The final `"complete"` event must include the full `HivemindOutput` object so the SSE/WebSocket layer can serialize and deliver results.

---

## Fix 6 — Client data management (Phase A only)

**Files:** New file `cloud/app/models/client_data.py`, new file `cloud/app/routers/client_data.py`, `cloud/app/main.py` (router registration), `client/src/App.tsx`, `client/src/api/client.ts`

**Defect:** The spec requires persistent client-cleared data accessible to all analyses. Currently the client only provides an ephemeral textarea. No `ClientData` model, no CRUD endpoints, no persistent data store exists.

**Correction:**

1. Create SQLAlchemy model `ClientData` in `cloud/app/models/client_data.py`:
   - Columns: `id` (UUID PK), `client_id` (UUID FK to `clients`), `data_type` (String: "document" | "text" | "structured"), `content` (Text), `filename` (String, nullable), `uploaded_at` (DateTime, server_default=now).

2. Create router `cloud/app/routers/client_data.py` with:
   - `GET /clients/{client_id}/data` — list all ClientData for a client.
   - `POST /clients/{client_id}/data` — create a new ClientData entry (accept JSON body with `data_type`, `content`, optional `filename`).
   - `DELETE /clients/{client_id}/data/{data_id}` — delete a specific entry.

3. Register the router in `main.py`.

4. In `client/src/api/client.ts`, add `listClientData()`, `createClientData()`, `deleteClientData()` methods.

5. In `client/src/App.tsx`, add a collapsible "My Data" panel in the input section. Display existing data entries with delete buttons. Provide a textarea + "Save" button for adding text entries. When submitting an analysis, include all persisted client data entries as `context_document_texts` in the request payload.

---

## Fix 7 — Enforce JWT authentication on API routes

**Files:** `cloud/app/deps.py`, all router files in `cloud/app/routers/`

**Defect:** JWT tokens are generated at `/auth/login` and `/auth/client-connect` but never validated on any downstream endpoint. All routes are publicly accessible.

**Correction:**

1. In `cloud/app/deps.py`, add a `get_current_user` FastAPI dependency that:
   - Extracts the `Authorization: Bearer <token>` header.
   - Decodes and validates the JWT using the app's `JWT_SECRET` and `JWT_ALGORITHM`.
   - Raises `HTTPException(401)` on missing/invalid/expired tokens.
   - Returns the decoded payload dict.

2. Add this dependency to all router endpoints except: `POST /auth/login`, `POST /auth/client-connect`, `GET /health`, `GET /health/detailed`, `POST /admin/ping`, `GET /admin/ping-status`.

3. Create a parallel `get_current_client` dependency for client-issued tokens (those from `/auth/client-connect`) and apply it to `/analysis/*` and `/sync/*` routes.

---

## Fix 8 — Add `status` query parameter to agent listing endpoint

**Files:** `cloud/app/routers/agents.py`

**Defect:** The client calls `GET /agents?status=published` but the endpoint ignores the query parameter and returns all agents.

**Correction:**

Add `status: str | None = None` as a query parameter to the `list_agents` endpoint. When provided, filter the SQLAlchemy query with `.filter(AgentDefinition.status == status)`.

---

## Fix 9 — Consolidate duplicate interface definitions

**Files:** `cloud/hivemind_core/interfaces.py`, `cloud/hivemind_core/types.py`, `cloud/hivemind_core/adapters/sqlalchemy_storage.py`, `cloud/app/adapters/storage.py`

**Defect:** `StorageInterface`, `VectorStoreInterface`, and `LLMInterface` are defined in both `types.py` and `interfaces.py` with divergent method signatures. `PostgresStorage` and `SQLAlchemyStorage` are duplicate adapter implementations.

**Correction:**

1. Designate `types.py` as the canonical source for all three interfaces. Merge any methods unique to the `interfaces.py` versions into the `types.py` definitions.
2. Rewrite `interfaces.py` to re-export from `types.py`: `from hivemind_core.types import StorageInterface, VectorStoreInterface, LLMInterface`.
3. Merge any unique methods from `SQLAlchemyStorage` into `PostgresStorage`. Delete `sqlalchemy_storage.py`.
4. Update all import statements across the codebase to reference `types.py` or the re-exports in `interfaces.py`.

---

## Fix 10 — Replace LLM-based similarity with embedding cosine similarity

**Files:** `cloud/hivemind_core/debate.py`

**Defect:** `_compute_solution_similarity()` makes a full LLM API call per solution pair — O(N^2) calls per aggregation pass. This is slow and expensive. The spec notes the monitor should emphasize aggregation, not content generation.

**Correction:**

1. Rewrite `_compute_solution_similarity()` to embed both solutions using `sentence_transformers.SentenceTransformer("all-MiniLM-L6-v2")` (already a project dependency), then return their cosine similarity as a float in [0.0, 1.0]. Cache the model instance at module level via `functools.lru_cache`.

2. Retain the existing `_merge_solution_cluster()` function unchanged — it legitimately requires LLM generation for merging.

---

## Fix 11 — Remove duplicate WebSocket handler

**Files:** `cloud/app/ws/analysis.py`, `cloud/app/ws/__init__.py`, `cloud/app/ws/handlers.py`

**Defect:** Both `ws/analysis.py` and `ws/handlers.py` define WebSocket endpoints at `/ws/analysis/{client_id}`. `analysis.py` references `ContextType.STRUCTURED_DATA` which does not exist in the `ContextType` enum (correct value is `ContextType.STRUCTURED`).

**Correction:**

1. Delete `cloud/app/ws/analysis.py`.
2. Remove any import of `analysis.py` from `__init__.py`.
3. Verify `handlers.py` uses `ContextType.STRUCTURED` (not `STRUCTURED_DATA`). Fix if needed.

---

## Fix 12 — Add missing `use_case_profile` and `decision_types` columns

**Files:** `cloud/app/models/agent.py`, `cloud/app/models/knowledge_base.py`, `admin/src/pages/AgentEdit.tsx`, `admin/src/pages/KnowledgeBases.tsx`

**Defect:** The analysis router's `_resolve_agents_by_profile_and_decision()` queries `AgentDefinition.use_case_profile` and `KnowledgeBase.decision_types`, but neither column exists in the SQLAlchemy model definitions. These queries will raise `AttributeError` at runtime.

**Correction:**

1. Add `use_case_profile = Column(String, nullable=True)` to the `AgentDefinition` model.
2. Add `decision_types = Column(JSONB, default=list)` to the `KnowledgeBase` model.
3. In the admin `AgentEdit.tsx`, add a "Use Case Profile" dropdown field (options: `small_business`, `individual_career`, `enterprise`, or blank) bound to the agent's `use_case_profile`.
4. In the admin `KnowledgeBases.tsx`, add a "Decision Types" multi-select or tag input (options: `market_entry`, `m_and_a`, `pricing`, or custom) bound to the KB's `decision_types`.
5. Update the corresponding Pydantic schemas in `cloud/app/schemas/agent.py` and `cloud/app/schemas/knowledge_base.py` to include these new fields.

---

## Fix 13 — Parse critique response into structured fields

**Files:** `cloud/hivemind_core/debate.py`

**Defect:** When constructing `Critique` objects (~line 688-698), `strengths`, `weaknesses`, and `suggestions` are always empty lists. Only `critique_text` is populated. The revision prompt then renders these as "None noted" / "None provided", losing structured feedback.

**Correction:**

Add a `_parse_critique_response(response_text: str) -> tuple[list[str], list[str], list[str]]` function that parses the LLM critique response. Detect section headers ("STRENGTHS", "WEAKNESSES", "SUGGESTIONS") and collect bullet points (lines starting with `-` or `*`) under each section. Return `(strengths, weaknesses, suggestions)`. Use this parser when constructing the `Critique` object to populate all three fields.

---

## Fix 14 — Separate solution text from theoretical reasoning

**Files:** `cloud/hivemind_core/agents.py`, `cloud/hivemind_core/debate.py`

**Defect:** In `run_debate()` lines 620-628, `TheoryUnitSolution.solution` and `TheoryUnitSolution.reasoning` are both set to `result.response` (identical). The spec requires them to be distinct: the solution is the strategic recommendation; the reasoning is the theoretical justification. The spec also requires the monitor to pass only solutions (not justifications) to the practicality network.

**Correction:**

1. Modify the theory agent prompt suffix in `build_theory_prompt()` (`agents.py`) to instruct the LLM to structure its output with explicit delimiters:
```
Format your response as:
SOLUTION:
[Your strategic recommendation]

REASONING:
[Your theoretical justification and evidence]
```

2. Add a `_parse_solution_response(response: str) -> tuple[str, str]` function in `debate.py` that splits on the `SOLUTION:` and `REASONING:` headers. Return `(solution_text, reasoning_text)`. If parsing fails, fall back to using the full response for both.

3. Update the `TheoryUnitSolution` construction in `run_debate()` to use the parsed values.

---

## Fix 15 — Add test suite

**Files:** New directory `cloud/tests/`, `cloud/requirements.txt`

**Defect:** No test files exist. The debate engine has complex convergence, veto, and restart logic that is untested.

**Correction:**

1. Add `pytest>=7.0` to `cloud/requirements.txt`.
2. Create `cloud/tests/__init__.py` (empty).
3. Create `cloud/tests/test_debate.py` with:
   - Unit test for `_create_dynamic_units()`: given known document token counts and a density value, assert correct number of units and document assignments.
   - Unit test for `_parse_feasibility_score()`: given sample LLM response strings, assert correct score, risks, challenges, mitigations extraction.
   - Unit test for `_parse_critique_response()` (from Fix 13): given sample critique text, assert correct field extraction.
   - Integration test for `run_debate()` using `MockLLM`: configure mock responses, run a full debate, assert output structure, debate round count, and that sufficiency convergence is respected.
   - Integration test for veto-restart: configure `MockLLM` to return low feasibility scores on first pass, verify `veto_restarts > 0` in output.

4. Create `cloud/tests/test_simulations.py` with:
   - Unit test for `run_simulation()`: given a formula and inputs, assert correct outputs.
   - Unit test for AST validation: assert that formulas containing disallowed constructs (imports, attribute access) are rejected.

---

## Fix 16 — Extract inline HTML from main.py into template files

**Files:** `cloud/app/main.py`, new files `cloud/app/templates/dashboard.html`, `cloud/app/templates/knowledge_browser.html`

**Defect:** `main.py` contains ~300+ lines of inline HTML string construction for the `/dashboard` and `/knowledge-browser` endpoints. This is fragile and unmaintainable.

**Correction:**

1. Create `cloud/app/templates/` directory.
2. Extract the dashboard HTML into `dashboard.html` as a Jinja2 template. Parameterize dynamic values (uptime, service statuses, ping data) as template variables.
3. Extract the knowledge browser HTML into `knowledge_browser.html` similarly.
4. Add `jinja2` and `aiofiles` to `requirements.txt` if not already present.
5. Configure Jinja2 templates in the FastAPI app: `templates = Jinja2Templates(directory="app/templates")`.
6. Rewrite the `/dashboard` and `/knowledge-browser` endpoints to use `templates.TemplateResponse()`.

---

## Fix 17 — Enable simulation formula execution during debate via tool use

**Files:** `cloud/hivemind_core/agents.py`, `cloud/hivemind_core/llm.py`, `cloud/hivemind_core/debate.py`

**Defect:** Theory agents receive simulation formula metadata in their system prompt but have no mechanism to invoke `run_simulation()` during generation. They can only describe hypothetical computation.

**Correction:**

1. In `ClaudeLLM.call()` (`llm.py`), add an optional `tools: list[dict] | None = None` parameter. When provided, pass it to the Anthropic API request as the `tools` field (Anthropic tool-use format).

2. In `execute_agent()` (`agents.py`), when the agent is a theory agent with `simulation_formula_ids`:
   - Construct tool definitions from each `SimulationFormula`: tool name = formula name (slugified), description = formula description, input schema = JSON schema derived from `formula.inputs`.
   - Pass these tools to `llm.call()`.
   - If the LLM response contains `tool_use` blocks, execute each via `run_simulation()`, construct a tool result, and make a follow-up `llm.call()` with the tool result appended. Loop until the LLM produces a final text response (cap at 3 tool-use rounds to prevent infinite loops).

3. Update `LLMInterface.call()` signature in `types.py` to accept the optional `tools` parameter.
