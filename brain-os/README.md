# BrainOS — Make AI Know Your Business

LLM-agnostic, intent-driven platform that turns private business data into a live, accurate, cited AI. No hardcoded logic; intelligence and behavior are driven by config and LLM.

## Quick Start with Docker Compose (recommended)

Runs **backend**, **frontend**, and **Qdrant** vector DB:

```bash
# From repo root
docker compose up --build
```

**First-time run:** Docker will pull Postgres, Qdrant, and build backend/frontend. The pull can take several minutes (image size and network). Compose only shows a spinner—to see layer-by-layer progress, run `docker compose pull` first, then `docker compose up --build`.

- **App:** http://localhost:3000  
- **API:** http://localhost:8000  
- **Qdrant dashboard:** http://localhost:6333/dashboard  

Set `OPENAI_API_KEY` (and optionally `ANTHROPIC_API_KEY`) in `.env` or in the shell before `docker compose up` so the backend can call the LLM.

## Local development (no Docker)

```bash
# Terminal 1 — Qdrant (vector DB)
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant:v1.7.4

# Terminal 2 — Backend
cd backend && pip install -r requirements.txt && QDRANT_URL=http://localhost:6333 uvicorn app.main:app --reload

# Terminal 3 — Frontend
cd frontend && npm install && npm run dev
```

## Architecture

- **Vector store:** **Qdrant** (default). Configure in `backend/config/schema.yaml` under `vector_store`; set `QDRANT_URL` (or `QDRANT_HOST`/`QDRANT_PORT`) when running.
- **Config-driven:** All intents, prompts, and provider settings live in `backend/config/`. No hardcoded business logic.
- **LLM-agnostic:** Swap providers via config; same interface for streaming, completion, embeddings.
- **Outputs:** Streaming answers with citations, knowledge base (Qdrant + document registry), freshness reports, gap reports, deployed surfaces (widget, Slack, API), analytics, compliance (PII, GDPR, audit), web intelligence, domain expert mode, export formats.

## Project Layout

- `backend/` — FastAPI, ingestion, RAG, Qdrant store, watchdog, PII, scraper, exports
- `frontend/` — Next.js 14, streaming chat, dashboards
- `backend/config/` — YAML for providers, intents, prompts; `vector_store.type: qdrant`
