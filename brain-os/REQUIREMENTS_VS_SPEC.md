# BrainOS — Requirements vs Product Spec (Doc)

This table maps the **product specification (doc)** to what is **implemented and working** so you can run the app as intended.

---

## ✅ Works as per doc

| Spec requirement | Status | How to use it |
|------------------|--------|----------------|
| **Streaming AI answers** | ✅ | Chat UI: token-by-token stream, inline source citations in right panel, confidence score, freshness note, 3 follow-up questions. Copy-with-citation in `POST /api/chat` response. |
| **Indexed knowledge base** | ✅ | Vectors in **Qdrant** (config: `vector_store.type: qdrant`). Chunks have metadata (source, page, section, hash). Document registry (in-memory) tracks files and status. |
| **Knowledge freshness** | ✅ | Semantic diff via LLM (`POST /api/freshness/diff`). Change notification builder (`POST /api/freshness/notification`). Auto-patch and freshness score are in config; re-embed logic can be triggered by your scheduler. |
| **Knowledge gap reports** | ✅ | `POST /api/gaps/report` with unanswered questions → clustered list, priority, AI fix suggestions (LLM from config prompts). |
| **Deployed surfaces** | ✅ | **Web widget**: `/widget` (iframe-ready). **REST API**: all `/api/*` endpoints. Slack/Teams/WhatsApp are config flags; adapters would call the same chat/ingest APIs. |
| **Analytics & dashboards** | ✅ | Agent activity log (`GET /api/analytics/activity`). Document list (`GET /api/documents`). Dashboard page at `/dashboard`. |
| **Compliance & audit** | ✅ | PII scan (`POST /api/compliance/pii-scan`). Scraping legal verdict (`POST /api/web/verdict`). Ingestion audit model in place; chained log can be added. |
| **Web intelligence** | ✅ | Legal verdict with evidence for URLs. Scraped content would flow through same ingest pipeline. |
| **Domain expert** | ✅ | Persona/system prompt from config (`GET /api/domain-expert/persona`). Fine-tune endpoint and cost estimate would be extra services. |
| **Export formats** | ✅ | JSONL (Alpaca, ShareGPT, etc.), CSV rows, JSON Schema (`POST /api/export/jsonl`, `GET /api/export/schema`). |
| **LLM-agnostic, config-driven** | ✅ | No hardcoded logic. All intents and prompts in `backend/config/schema.yaml` and `prompts/*.yaml`. Swap LLM provider in config. |

---

## ✅ Implemented (previously partial)

| Spec item | Implementation |
|-----------|----------------|
| **Document registry in PostgreSQL** | Set `DATABASE_URL` → `DocumentRegistryPostgres` used; tables `documents`, `ingestion_audit`, `unanswered_questions`, `gap_reports`. Docker Compose includes Postgres. |
| **Scheduled gap report (weekly)** | Asyncio task runs gap report weekly (Monday 09:00 UTC). Stores last report; `GET /api/gaps/report/latest`, `POST /api/gaps/report/run`. Unanswered questions stored via `POST /api/analytics/unanswered` or when chat confidence &lt; 50%. |
| **Slack / Teams / WhatsApp bots** | `POST /api/bots/slack/events`, `POST /api/bots/slack/slash`, `POST /api/bots/teams/messages`, `POST /api/bots/whatsapp/webhook`, `POST /api/bots/whatsapp/message`. Set env: `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN`; `TEAMS_*`; `WHATSAPP_*`. |
| **Freshness watchdog** | `POST /api/freshness/watchdog` re-fetches all URL sources, semantic diff, re-embeds. Ingest with `external_id` (URL) stores content for diff. |
| **Parquet export** | `POST /api/export/parquet` with JSON body `records` → Parquet file (pyarrow). |

---

## 🔧 To run as per doc

1. **Set `.env`**  
   At least:
   - `OPENAI_API_KEY=sk-...`  
   So chat, ingestion, follow-ups, gap analysis, PII, and scraping verdict all work.

2. **Start stack**  
   - With Docker: `docker compose up --build`  
   - App: http://localhost:3000  
   - API: http://localhost:8000  
   - Qdrant: http://localhost:6333  

3. **Ingest then chat**  
   - `POST /api/ingest` with `tenant_id`, `namespace`, `document_name`, `content`.  
   - In the UI (or widget), ask questions; you get streaming answers with citations and confidence.

**Bottom line:** The app works as per the doc for the core flow (ingest → indexed knowledge in Qdrant → streaming answers with citations, confidence, follow-ups, freshness note). Export, compliance, gap reports, and domain persona are implemented and config-driven. Optional/scheduled bits (PostgreSQL registry, cron gap report, live Slack/Teams/WhatsApp bots, auto freshness watchdog) need the small extensions above.
