# Hivemind Software — Backend Infrastructure

## 1. System Overview

Hivemind is a multi-agent strategic analysis platform composed of three independently deployed applications that communicate over HTTPS:

| Application | Technology | Role |
|---|---|---|
| **Admin** | Tauri + React (TypeScript) | Operator console for building agents, uploading knowledge, and managing the platform |
| **Cloud** | FastAPI + PostgreSQL + Qdrant (Python) | Central API server that stores all data, runs RAG retrieval, and executes multi-agent AI analysis |
| **Client** | Tauri + React (TypeScript) | End-user terminal for submitting strategic problems and viewing analysis results |

All AI computation occurs on the **cloud server**. The admin and client applications are thin frontends that make REST API calls to the cloud. The cloud server holds the Anthropic API key and is the sole component that communicates with the LLM.

---

## 2. Application Responsibilities

### 2.1 Admin Application

The admin application is used by the platform operator (not end users). It provides:

1. **Agent Management** — Create, edit, publish, and test AI agent definitions. Each agent belongs to either the "theory" or "practicality" network and is configured with a framework, principles, analytical style, scoring criteria, attached knowledge bases, and attached simulation formulas.

2. **Knowledge Base Management** — Create knowledge bases and upload three categories of documents:
   - **Framework Documents** (`.txt` files) — Text files describing analytical frameworks, algorithms, or methodologies (e.g., "Porter's Five Forces", "Monte Carlo Risk Assessment"). Each file is uploaded individually or in batches via drag-and-drop. These feed the **theory network**.
   - **Simulation Programs** (`.py` + companion `.txt` pair) — A Python program file containing a computational simulation, paired with a companion text file that describes what the simulation computes, what inputs it requires, how to plug in values correctly, and how to interpret its outputs. The pair is uploaded together; the `.py` file is stored for execution and the `.txt` file is optimized and embedded for RAG retrieval.
   - **Practicality Documents** (`.txt` files) — Text files describing real-world constraints, scoring criteria, risk frameworks, industry benchmarks, and feasibility evaluation guidelines. These feed the **practicality network** agents, providing them with domain-specific context for evaluating the feasibility of theory-generated recommendations.

3. **Simulation Formula Management** — Create and edit mathematical simulation formulas (inputs, calculations, outputs) that agents can invoke as tools during analysis.

4. **API Key Configuration** — Set the Anthropic API key that the cloud server uses for all LLM calls. The key is transmitted to the cloud and stored encrypted at rest.

5. **Server Monitoring** — Dashboard showing hosted stack status (PostgreSQL, Qdrant, API server) and connectivity.

### 2.2 Cloud Server

The cloud server is the central backend. It provides:

1. **REST API** — All endpoints for CRUD operations on agents, knowledge bases, simulations, clients, and analyses. Served via FastAPI with CORS enabled for cross-origin admin/client access.

2. **Data Storage** — PostgreSQL stores all relational data: agent definitions, knowledge base metadata, document records, text chunks, simulation formulas, client records, and analysis records.

3. **Vector Storage** — Qdrant vector database stores embedding vectors for all text chunks, enabling semantic similarity search during RAG retrieval.

4. **RAG Pipeline** — The complete Retrieval-Augmented Generation pipeline:
   - Text extraction from uploaded documents
   - LLM-powered document optimization for RAG precision
   - Text chunking with configurable token limits and overlap
   - Embedding generation via sentence-transformers (`all-MiniLM-L6-v2`)
   - Vector upsert into Qdrant collections (one collection per knowledge base)
   - Semantic retrieval at query time with configurable top-k and similarity thresholds

5. **Multi-Agent Debate Engine** — The core AI analysis system (see Section 4).

6. **API Key Management** — Stores the Anthropic API key (encrypted via Fernet symmetric encryption) and uses it for all LLM calls.

7. **File Storage** — Uploaded files are stored in an organized directory structure:
   ```
   uploads/
     knowledge/
       frameworks/      ← .txt files describing frameworks/algorithms (theory network)
     simulations/       ← .py programs and their companion .txt descriptions
     practicality/      ← .txt files for practicality network constraints/scoring
   ```
   When S3 credentials are configured, files are stored in S3 with the same key structure. Otherwise, they are stored locally. See `cloud/uploads/BASES.md` for full documentation of the storage layout.

9. **Base Browser** — A server-rendered HTML page at `/knowledge-browser` that provides a unified view of all three base types: knowledge bases (with framework, simulation, and practicality documents), and standalone simulation formulas. Includes aggregate statistics and per-document details.

8. **WebSocket Support** — Real-time streaming of analysis progress events to connected clients.

### 2.3 Client Application

The client application is used by end users (operators cleared for access). It provides:

1. **Authentication** — Username-based login against a server-maintained allowlist.

2. **Analysis Submission** — A form where the user enters:
   - A problem statement (the strategic question to analyze)
   - Optional client context (cleared text/data)
   - Configuration parameters: sufficiency value, feasibility threshold, similarity threshold, revision strength, practicality criticality
   - Agent selection: either manual selection of theory/practicality agents, or dynamic density mode
   - Optional use-case profile and decision type for automatic agent resolution

3. **Results Display** — Approved recommendations with feasibility scores, vetoed solutions, a full audit trail, and analysis statistics.

4. **Pipeline Visualization** — Real-time progress through the five analysis stages: Problem Input → Theory Network → Monitor → Practicality Network → User Output.

---

## 3. Knowledge Base Architecture

### 3.1 Document Upload Flow

When the admin uploads a document to a knowledge base, the following sequence occurs on the cloud server:

```
[Admin App]                        [Cloud Server]
    |                                    |
    |── POST /knowledge-bases/{id}/upload ──→|
    |   (file in multipart form)         |
    |                                    |── 1. Store raw file
    |                                    |      (S3 or local filesystem)
    |                                    |
    |                                    |── 2. Extract text from file bytes
    |                                    |
    |                                    |── 3. Optimize text via LLM
    |                                    |      (Claude Sonnet call)
    |                                    |
    |                                    |── 4. Chunk optimized text
    |                                    |      (token-bounded, overlapping)
    |                                    |
    |                                    |── 5. Embed each chunk
    |                                    |      (sentence-transformers)
    |                                    |
    |                                    |── 6. Store chunks in PostgreSQL
    |                                    |      (TextChunk table)
    |                                    |
    |                                    |── 7. Upsert vectors into Qdrant
    |                                    |      (collection: kb_{id})
    |                                    |
    |                                    |── 8. Update KB aggregate counts
    |                                    |
    |←── { document_id, chunks, optimized } ──|
```

### 3.2 Document Optimization

Before chunking and embedding, every uploaded document's text is refined by the LLM to maximize RAG retrieval effectiveness. The optimization service (`document_optimizer.py`) uses Claude Sonnet with specialized system prompts:

**For framework documents**, the optimizer:
- Preserves every factual claim, statistic, formula, named entity, and causal relationship exactly
- Restructures sentences for clarity (active voice, explicit subjects, direct predication)
- Removes filler phrases, marketing language, unnecessary hedging, and repetition — only when removal does not reduce information content
- Enforces consistent terminology (picks the most precise synonym)
- Organizes text into clearly delineated sections with descriptive headings
- Numbers every step or principle in frameworks/algorithms

**For simulation description documents**, the optimizer ensures chunks convey:
- What the simulation computes and why it matters for strategic decisions
- What each input variable represents and its valid ranges/units
- How to interpret each output and what thresholds or benchmarks apply
- Common usage patterns and which strategic questions the simulation answers

**Priority order**: Precision > Clarity > Conciseness. The optimizer never sacrifices information for brevity.

If no API key is configured or the optimization call fails, the system falls back to using the raw extracted text.

### 3.3 Simulation Program Upload Flow

Simulation programs require a paired upload:

```
[Admin App]                                 [Cloud Server]
    |                                             |
    |── POST /knowledge-bases/{id}/upload-simulation ──→|
    |   (program.py + description.txt in multipart)     |
    |                                             |
    |                                             |── 1. Validate: .py + .txt
    |                                             |
    |                                             |── 2. Store .py file
    |                                             |      (simulation_program type)
    |                                             |
    |                                             |── 3. Create KnowledgeDocument
    |                                             |      record for .py
    |                                             |
    |                                             |── 4. Store .txt file
    |                                             |      (simulation_description type)
    |                                             |
    |                                             |── 5. Optimize .txt via LLM
    |                                             |
    |                                             |── 6. Create KnowledgeDocument
    |                                             |      record for .txt
    |                                             |      (with companion_document_id
    |                                             |       linking to the .py record)
    |                                             |
    |                                             |── 7. Chunk + embed optimized .txt
    |                                             |
    |                                             |── 8. Upsert vectors into Qdrant
    |                                             |
    |←── { program_document_id, description_document_id, chunks } ──|
```

The `.py` file is stored for execution but is **not** embedded or chunked — it does not enter the vector store. Only the companion `.txt` description is optimized, chunked, and embedded so that RAG retrieval can surface relevant simulation context when agents analyze problems.

### 3.4 Practicality Document Upload Flow

Practicality documents follow the same flow as framework documents but are stored in the `practicality/` directory and tagged with `document_type="practicality"`:

```
[Admin App]                                    [Cloud Server]
    |                                                |
    |── POST /knowledge-bases/{id}/upload-practicality ──→|
    |   (file in multipart form)                     |
    |                                                |── 1. Store raw file in practicality/
    |                                                |── 2. Extract text
    |                                                |── 3. Optimize via LLM
    |                                                |── 4. Chunk + embed
    |                                                |── 5. Upsert vectors into Qdrant
    |                                                |── 6. Update KB counts
    |                                                |
    |←── { document_id, chunks, optimized } ─────────|
```

Practicality documents describe real-world constraints, industry benchmarks, scoring criteria, and risk frameworks. When practicality agents evaluate theory-generated recommendations, RAG retrieval surfaces relevant practicality chunks to ground their feasibility scoring in domain-specific knowledge.

### 3.5 Data Model

```
KnowledgeBase
  ├── id (UUID)
  ├── name
  ├── description
  ├── decision_types[]         ← used to match KB to analysis requests
  ├── document_count           ← aggregate
  ├── chunk_count              ← aggregate
  ├── total_tokens             ← aggregate
  └── embedding_model          ← "all-MiniLM-L6-v2"

KnowledgeDocument
  ├── id (UUID)
  ├── knowledge_base_id (FK)
  ├── filename
  ├── content_type
  ├── s3_path                  ← S3 URI or local path
  ├── extracted_text           ← raw text from file
  ├── optimized_text           ← LLM-refined text (nullable)
  ├── document_type            ← "framework" | "simulation_program" | "simulation_description" | "practicality"
  ├── companion_document_id    ← FK to .py document (for simulation descriptions)
  └── upload_timestamp

TextChunk
  ├── id (UUID)
  ├── document_id (FK)
  ├── knowledge_base_id (FK)
  ├── content                  ← chunk text
  ├── token_count
  └── chunk_index

Qdrant Collection: "kb_{knowledge_base_id}"
  ├── point ID = TextChunk.id
  ├── vector = embedding(chunk.content)
  └── payload = { knowledge_base_id, document_id, chunk_index }
```

### 3.6 RAG Retrieval at Query Time

When an agent executes during analysis, retrieval proceeds as follows:

1. The query text is embedded using the same sentence-transformer model
2. Qdrant performs approximate nearest-neighbor search across the relevant `kb_{id}` collections
3. Results are filtered by similarity threshold and limited to top-k
4. Chunk content is fetched from PostgreSQL by ID
5. Retrieved chunks are injected into the agent's prompt as contextual knowledge

---

## 4. Multi-Agent Debate Engine

The debate engine is the core intellectual process. It implements the following pipeline:

### 4.1 Theory Network

The theory network consists of multiple AI units, each configured with a distinct analytical framework and attached knowledge bases. There are two modes:

- **Manual Mode** — The operator selects specific theory agent definitions to use.
- **Dynamic Density Mode** — The system automatically creates theory units by distributing knowledge base documents across units such that each unit receives approximately `theory_network_density` tokens of context. This creates units with overlapping but non-identical knowledge, encouraging diverse perspectives.

Each theory unit:
1. Receives the problem statement
2. Has its knowledge base chunks retrieved via RAG
3. Has its simulation formulas available as callable tools
4. Generates an initial solution with reasoning

### 4.2 Cross-Critique and Revision

After initial solutions are generated:

1. Each unit's solution is shared with every other unit
2. Each unit critiques the others' solutions, identifying strengths, weaknesses, and suggestions
3. Each unit revises its own solution in light of the critiques received
4. The `revision_strength` parameter (0–1) controls how aggressively units revise

### 4.3 Monitor Aggregation

The Monitor is a specialized LLM call that:

1. Receives all current solutions from all theory units
2. Groups solutions that are semantically similar (controlled by `similarity_threshold`)
3. Merges similar solutions into aggregated conclusions, preserving all justifications
4. Checks whether the number of distinct aggregated conclusions ≤ `sufficiency_value`
5. If not converged, triggers another round of critique-and-revision
6. The debate continues until convergence or the maximum round limit

### 4.4 Practicality Network

Once the theory network converges, the aggregated solutions are evaluated by the practicality network:

1. Each practicality agent receives the aggregated solutions
2. Each evaluates feasibility on a 0–100 scale
3. Each provides: risks, implementation challenges, mitigations, and reasoning
4. The `practicality_criticality` parameter (0–1) influences scoring strictness

### 4.5 Veto Gate

After practicality evaluation:

1. The average feasibility score across all practicality agents is computed for each solution
2. If the average is ≤ `feasibility_threshold`, the solution is **vetoed**
3. If **all** solutions are vetoed, the entire theory network restarts from scratch (up to `max_veto_restarts` times)
4. Solutions that pass form the final approved recommendations

### 4.6 Output

The final output contains:
- Approved recommendations with feasibility scores, contributing agents, and reasoning
- Vetoed solutions (for transparency)
- Complete audit trail (every LLM call, retrieval, timing)
- Statistics: debate rounds, veto restarts, units created, total tokens, duration

---

## 5. API Key Flow

```
[Admin Settings Page]
    |
    |── POST /settings/api-key { api_key: "sk-ant-..." }
    |
    [Cloud Server]
    |── Validate format (must start with "sk-")
    |── Encrypt with Fernet symmetric encryption
    |── Store in .hivemind_settings.json
    |
    [On any LLM call (analysis, optimization)]
    |── get_active_api_key() resolves from:
    |     1. .hivemind_settings.json (encrypted)
    |     2. ANTHROPIC_API_KEY environment variable
    |── Decrypt and use for Anthropic API calls
```

The API key is never exposed in API responses. The status endpoint returns only whether a key is configured and the last 4 characters (masked).

---

## 6. Communication Architecture

```
┌─────────────┐     HTTPS/REST      ┌─────────────────┐     HTTPS/REST      ┌──────────────┐
│   Admin App  │◄──────────────────►│   Cloud Server    │◄──────────────────►│  Client App   │
│  (Tauri/React│                     │ (FastAPI/Python) │                     │ (Tauri/React) │
│   Desktop)   │                     │                  │                     │   Desktop)    │
└─────────────┘                     │   ┌──────────┐   │                     └──────────────┘
                                    │   │PostgreSQL│   │
                                    │   └──────────┘   │
                                    │   ┌──────────┐   │
                                    │   │  Qdrant  │   │
                                    │   └──────────┘   │
                                    │                  │
                                    │   Anthropic API──────►  Claude LLM
                                    └──────────────────┘
```

- **Admin → Cloud**: Agent CRUD, knowledge base CRUD, document uploads (framework, simulation, practicality), API key management, connection health checks
- **Client → Cloud**: Authentication, agent listing, analysis submission and result retrieval
- **Cloud → Anthropic**: LLM calls for agent execution, document optimization, monitor aggregation, critique/revision, feasibility evaluation
- **Cloud → Qdrant**: Vector upsert during document processing, vector search during RAG retrieval
- **Cloud → PostgreSQL**: All relational data storage and retrieval

The cloud server is intended to be exposed from AWS via EC2 networking, an HTTPS endpoint, and restricted security groups.

---

## 7. File System Layout

```
HivemindSoftware/
├── admin/                    ← Admin Tauri + React application
│   ├── src/
│   │   ├── api/client.ts     ← API client with typed methods
│   │   ├── pages/            ← React pages (Dashboard, Agents, KnowledgeBases, Settings, etc.)
│   │   ├── components/       ← Shared components (Sidebar)
│   │   └── styles.css        ← Global styles
│   └── src-tauri/            ← Tauri native shell
│
├── client/                   ← Client Tauri + React application
│   ├── src/
│   │   ├── api/client.ts     ← API client for client-facing endpoints
│   │   ├── App.tsx           ← Single-page terminal UI
│   │   └── styles.css        ← Bloomberg-terminal-style CSS
│   └── src-tauri/
│
├── cloud/                    ← Cloud FastAPI server
│   ├── app/
│   │   ├── main.py           ← FastAPI app initialization and routing
│   │   ├── config.py         ← Settings from environment / .env
│   │   ├── models/           ← SQLAlchemy ORM models
│   │   ├── routers/          ← API endpoint handlers
│   │   │   ├── agents.py
│   │   │   ├── knowledge_bases.py
│   │   │   ├── simulations.py
│   │   │   ├── settings.py   ← API key management
│   │   │   ├── analysis.py
│   │   │   └── ...
│   │   ├── schemas/          ← Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── document_optimizer.py  ← LLM-based document refinement
│   │   │   ├── rag.py                 ← RAG retrieval service
│   │   │   ├── storage.py             ← File storage (S3 or local)
│   │   │   └── simulations.py
│   │   ├── rag/              ← RAG pipeline components
│   │   │   ├── chunking.py   ← Token-bounded text chunking
│   │   │   ├── embeddings.py ← Sentence-transformer embeddings
│   │   │   ├── extraction.py ← Text extraction from file bytes
│   │   │   └── vector_store.py ← Qdrant client operations
│   │   ├── secrets.py        ← Fernet encryption utilities
│   │   ├── templates/        ← Jinja2 HTML templates (dashboard, knowledge browser)
│   │   └── ws/               ← WebSocket handlers
│   │
│   ├── hivemind_core/        ← Platform-agnostic core engine
│   │   ├── engine.py         ← HivemindEngine orchestrator
│   │   ├── types.py          ← All dataclasses and interfaces
│   │   ├── debate.py         ← Multi-agent debate protocol
│   │   ├── agents.py         ← Agent execution (RAG + LLM + tool use)
│   │   ├── simulations.py    ← Simulation formula execution
│   │   ├── llm.py            ← Claude LLM adapter
│   │   └── rag.py            ← RAG retrieval adapter
│   │
│   ├── uploads/              ← Local file storage (see uploads/BASES.md)
│   │   ├── knowledge/
│   │   │   └── frameworks/   ← Uploaded .txt framework files (theory network)
│   │   ├── simulations/      ← Uploaded .py + .txt simulation pairs
│   │   └── practicality/     ← Uploaded .txt practicality constraint files
│   │
│   └── .hivemind_settings.json  ← Runtime settings (encrypted API key)
│
├── scripts/                  ← Build, archive, and launcher scripts
├── backend/launchers/        ← Platform-specific setup scripts
└── exports/                  ← Archive output directory
```

---

## 8. Configuration

### Environment Variables (Cloud Server)

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg2://hivemind:hivemind@postgres:5432/hivemind` |
| `VECTOR_DB_URL` | Qdrant HTTP URL | `http://qdrant:6333` |
| `ANTHROPIC_API_KEY` | Anthropic API key (alternative to Settings UI) | None |
| `EMBEDDING_MODEL` | Sentence-transformer model name | `all-MiniLM-L6-v2` |
| `RAG_CHUNK_MIN_TOKENS` | Minimum tokens per chunk | 100 |
| `RAG_CHUNK_MAX_TOKENS` | Maximum tokens per chunk | 512 |
| `RAG_CHUNK_OVERLAP` | Token overlap between chunks | 50 |
| `S3_CREDENTIALS` | JSON string with `access_key`, `secret_key`, `region` | None (local storage) |
| `S3_BUCKET` | S3 bucket name | None (local storage) |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated or `*`) | `*` |
| `AUTO_CREATE_TABLES` | Create DB tables on startup | `true` |

### Environment Variables (Admin/Client)

| Variable | Description | Default |
|---|---|---|
| `VITE_API_URL` | Cloud server URL | `https://www.thenashlabhivemind.com` |

---

## 9. Security Considerations

1. **API Key Protection** — The Anthropic API key is encrypted at rest using Fernet symmetric encryption and never exposed through API responses. Only the last 4 characters are shown in the admin UI for verification.

2. **Client Authentication** — Clients authenticate via username against a server-maintained allowlist. JWT tokens are issued for session management.

3. **CORS** — The cloud server is configured with appropriate CORS headers. In production, origins should be restricted to known admin and client domains.

4. **File Uploads** — Uploaded files are validated by extension (`.txt` for frameworks and practicality documents, `.py` + `.txt` for simulations) before processing.

5. **No Client-Side AI Keys** — Neither the admin nor client applications ever hold or transmit the Anthropic API key directly to the LLM. All AI calls are proxied through the cloud server.
