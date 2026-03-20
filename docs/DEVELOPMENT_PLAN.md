# Hivemind Development Plan: Next Steps

This document maps the Hivemind product specification to the current codebase and outlines **what needs to be coded next**, in priority order.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the system design and product-to-codebase mapping.

---

## 0. Product Vision (Spec Summary)

**Mission**: Democratize rigorous academia in business strategy. Career-focused individuals and small organizations should be able to make strategic decisions like educated, rigorously refined business experts.

**Core workflow**: Prompt → Theory Network → Monitor → Practicality Network. Client provides (1) textual problem, (2) sufficiency value, (3) feasibility value (1–100), (4) theory network density. Key dynamics: revision strength, monitor similarity threshold, practicality criticality. Use-case tailoring: theory network for decision types; practicality network for industries (small biz, individual career, enterprise).

---

## 1. Quick Reference: What Was Implemented (This Worktree)

| Priority | What was coded | Where |
|----------|----------------|--------|
| 1 | Fix API client: forward `context_document_texts`, `similarity_threshold`, `revision_strength`, `practicality_criticality` | `client/src/api/client.ts` |
| 2 | Admin: add `use_case_profile` to Agent create/edit | `admin/src/pages/AgentEdit.tsx`, admin API, cloud models/schemas |
| 3 | Admin: add `decision_types` to KnowledgeBase create/edit | `admin/src/pages/KnowledgeBases.tsx`, cloud models/schemas |
| 4 | Client: add use-case profile and decision type selectors; forward in request; server-side resolution | `client/src/App.tsx`, `client/src/api/client.ts`, `cloud/app/routers/analysis.py` |
| 5 | Backend: `context_document_texts` → context, key dynamics in `HivemindInput`, similarity_threshold in debate aggregation | `cloud/app/schemas/analysis.py`, `cloud/hivemind_core/types.py`, `cloud/hivemind_core/debate.py`, `cloud/hivemind_core/agents.py` |

---

## 2. Remaining Gaps (Future Work)

- **Client-cleared data (stored docs)**: Upload pipeline for documents, consent flag, `context_documents` (IDs) flow.
- **Scraped internet data**: No scraping or ingestion pipeline.
- **Simulations as Python programs**: Currently formula-based only.
- **Monitor aggregation focus**: Dedicated aggregation-focused prompt or model.
- **Export & distribution**: PKG installers or pre-built apps in archives; First Run Setup coverage.

---

## 3. Summary

The codebase in this worktree has been aligned with DEVELOPMENT_PLAN Phase A (API client forwarding) and Phase B (use-case profile and decision type in Admin and Client). Backend supports context from client-cleared text and key dynamics (similarity threshold, revision strength, practicality criticality). Server resolves theory/practicality agents by `decision_type` and `use_case_profile` when provided by the client.
