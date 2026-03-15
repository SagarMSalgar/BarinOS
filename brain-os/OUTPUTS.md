# BrainOS — Outputs Implemented

| Output | Who Sees It | Format | When | Implementation |
|--------|-------------|--------|------|----------------|
| Streaming answer + citations | End user | Chat UI / SSE | Every query | `POST /api/chat/stream`, `stream_answer()` → tokens, citation, confidence, freshness, follow_ups |
| Copy-with-citation | End user | Text | On request | `POST /api/chat` returns `copy_with_citation` |
| Indexed knowledge base | System | Qdrant + in-memory registry | On ingest | `ingest_document()` → vector_store.upsert (Qdrant), registry.update |
| Document registry | Admin | JSON | On list | `GET /api/documents?tenant_id=` |
| Freshness report | Admin | JSON | On change | `POST /api/freshness/diff`, `POST /api/freshness/notification`, `semantic_diff()` |
| Gap report | Admin | JSON | Weekly / on demand | `POST /api/gaps/report`, `generate_gap_report()` |
| Web widget chat | Customer | Embedded HTML | Every visit | `/widget` page (iframe-ready) |
| REST API | Developer | JSON | Every call | All `POST/GET /api/*` |
| Analytics / activity log | Admin | JSON + dashboard | Continuous | `GET /api/analytics/activity`, `/dashboard` |
| PII scan report | Compliance | JSON | On ingest | `POST /api/compliance/pii-scan` |
| Scraping verdict | Admin | JSON | When URL added | `POST /api/web/verdict` |
| Domain expert persona | Technical | JSON | On request | `GET /api/domain-expert/persona?domain=` |
| Export JSONL/CSV/schema | Data team | JSONL/CSV/JSON | On demand | `POST /api/export/jsonl`, `GET /api/export/schema` |

All behavior is driven by **config** (`backend/config/schema.yaml` and `prompts/*.yaml`). **LLM is agnostic**: swap provider in config; same interfaces for completion and embeddings.
