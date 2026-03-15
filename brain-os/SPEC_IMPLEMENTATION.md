# BrainOS — Spec Implementation Status

This document maps the **Complete Screen & Feature Working Specification** and **Export & Training Data Studio** to what is implemented and what remains. Industry practices: config-driven behaviour, LLM-agnostic backend, no hardcoded copy in prompts, proper error handling and validation.

---

## ✅ Implemented (Production-Ready)

### Screen 0 — Onboarding
- **Step 1 — Name your brain:** Input saved to localStorage and synced to backend via `PUT /api/brain/settings` (persisted in `brain_settings` table). Name appears in sidebar.
- **Step 2 — Select domain:** Medical / Legal / Retail / SaaS / Finance / Custom. Stored in DB and localStorage. Backend uses domain for future tuning (domain_expert persona available via API).
- **Step 3 — First knowledge source:** Paste or URL. For **paste**: ingestion runs in background (`POST /api/ingest?wait=false`); UI polls `GET /api/ingest/status?document_id=` and shows **live progress** (progress bar + log lines: "Reading your document...", "Creating N chunks...", "Embedding chunk X of Y..."). On completion: **confetti** animation then redirect to Chat. For **URL**: sync ingest; then confetti and redirect. "Skip for now" goes straight to Chat.
- **Progress bar** at top (Step 1/2/3). Step content uses fade/slide-in style.

### Backend — New/Updated APIs
- **Ingestion progress:** `GET /api/ingest/status?document_id=`, `GET /api/ingest/active`. `POST /api/ingest?wait=false` starts background ingest with progress callback; progress stored in-memory (use Redis for multi-instance).
- **Brain settings:** `GET /api/brain/settings?tenant_id=`, `PUT /api/brain/settings` (body: `tenant_id`, `brain_name?`, `domain?`). Stored in `brain_settings` table.
- **Name validation:** `POST /api/brain/validate-name` (body: `name`) — LLM checks not offensive/not too generic; returns `{ valid, message }`.
- **Dashboard stats:** `GET /api/stats?tenant_id=&namespace=` returns `total_chunks`, `average_freshness`, `queries_answered_this_month`, `knowledge_gaps_count` for the Knowledge Sources stats row and links.

### Screen 2 — Knowledge Sources
- **Top stats row (4 cards):** Total Chunks, Average Freshness (colour by threshold), Queries Answered, Knowledge Gaps (clickable → `/gaps`). Data from `GET /api/stats`.
- **Live ingestion card:** When any job is in progress (from `GET /api/ingest/active` + status poll), a card at top shows gradient progress bar and live log message. Disappears when phase is `done` or `error`.
- **Drop zone:** Paste/URL tabs, Add to knowledge base. Paste uses async ingest so progress appears in the live card.
- **Re-sync (watchdog)** and source list with freshness badges and stale warning.

### Export & Export Studio
- **Export screen** (sidebar: Export Studio): Loads records from `GET /api/export/records`, format selector for JSONL (Alpaca, ShareGPT, OpenAI Chat, DPO), **Download JSONL / CSV / Parquet**, data preview table, JSON Schema display. Backend: `GET /api/export/records`, `POST /api/export/jsonl`, `POST /api/export/csv`, `POST /api/export/parquet`, `GET /api/export/schema`.

### Infrastructure
- **PostgreSQL:** `brain_settings` table for brain name and domain. `documents` metadata fix for JSONB (string vs dict) in `_row_to_record`.
- **Qdrant:** Client pinned to 1.7.x; integer point IDs for 1.7 server compatibility; optional `check_compatibility=False`.

---

## 🔶 Partially Implemented / Next Steps

### Screen 1 — Ask BrainOS (Chat)
- **Done:** Streaming answers, citations, confidence, follow-ups, source preview panel (right), copy-with-citation.
- **To do (spec):** "BrainOS is thinking..." &lt; 200ms; citation **chips** inline with freshness colour (green/amber/red by last verified); uncertainty handling message when no answer; **voice input** (mic → speech recognition); **conversation memory** per session; **status bar** at bottom ("Querying N sources · M chunks · Last verified X ago"); suggestion pills above input; auto-resize textarea max 4 lines.

### Screen 3 — Deploy
- **Done:** 6 channel cards, live widget preview (iframe).
- **To do:** Per-channel setup panels (Web Widget: customize, access control, embed code; Slack: OAuth, channels, trigger; API: key, request builder, rate limits). Real OAuth and embed code generation.

### Screen 4 — Knowledge Gaps
- **Done:** Clustered gaps, priority, AI suggestions, run report, completeness.
- **To do:** Alert banner with count and red if High &gt; 3 days; employee knowledge capture ("Add Sarah's answer to KB?"); "+ Add Knowledge" pre-filtered by source type.

### Screen 5 — Health Monitor
- **Done:** 4 health cards, 6 agent panels, live agent log (activity from `get_recent`).
- **To do:** Real health formulas (Knowledge Health composite, Answer Accuracy from feedback), agent status from actual workers, log with emoji/colour by type, pause button, 30-day trend sparklines.

### Screen 6 — Settings
- **Done:** Configuration cards (LLM, vector store, domain, PII, bots, export).
- **To do:** Full forms: LLM model selector, retrieval params, response style, language; Team & Permissions (invite, roles, per-surface); Privacy (PII level, redaction mode, data residency, audit export); Domain Expert (training status, cost estimate, history, endpoint).

### Export Studio (Full Spec)
- **Done:** Single export screen with format selector, preview, JSONL/CSV/Parquet download, schema.
- **To do:** **Three-column layout** (Dataset Builder 240px, Live Preview fluid, Quality Dashboard 320px). **Format-specific builders:** Pre-Training JSONL (filters, quality, dedup); **Alpaca SFT** (LLM-generated instruction pairs from chunks); **ShareGPT** (multi-turn generation); **DPO** (degradation strategies, score gap); **RAG Chunks** (with/without embeddings, chunk size). **Annotated Google Sheets** (8 tabs, OAuth, human_review column). **A/B dataset tester**, **Persona transformer**, **Training cost estimator**. **One-click push** (Hugging Face, OpenAI, GCS/S3, W&B). **Incremental export** (by content hash). **Export compliance gate** (PII scan, legal re-check, export log).

### Notifications
- **To do:** Toast notifications (green/amber/blue/red) bottom-right, clickable to screen/item; trigger on ingest complete, stale warning, new gap, PII redaction.

---

## 🔴 Not Started (Spec References)

- **Domain-specific behaviour:** Medical → HIPAA mode, 18 identifiers in PII scanner, clinical chunking (config and code paths to wire).
- **Gmail / Slack / Drive / Dropbox** OAuth "Connect a tool" in onboarding and Sources.
- **View chunks** (all N chunks with text) and **Edit metadata** / **Re-sync schedule** / **Remove** in source card 3-dot menu.
- **Web source** extra section: compliance status, watchdog schedule, last change.
- **Embed code** and **live widget preview** tied to Web Widget settings.
- **Slack/Teams/WhatsApp** setup panels with OAuth and test preview.

---

## How to Run

- **Backend:** `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`. Requires PostgreSQL (`DATABASE_URL`), Qdrant (`QDRANT_URL` or host/port), and LLM API keys.
- **Frontend:** `cd frontend && npm install && npm run dev`. Set `NEXT_PUBLIC_API_URL` if API is not on localhost:8000.
- **Full stack:** `docker compose up --build`.

---

## File Reference

| Spec area           | Backend | Frontend |
|---------------------|---------|----------|
| Onboarding progress | `app/services/ingestion_progress.py`, `app/main.py` (ingest `wait`, status, active) | `components/Onboarding.tsx`, `components/Confetti.tsx` |
| Brain settings      | `app/main.py` (brain/settings, validate-name), `app/db/connection.py` (brain_settings) | `lib/api.ts`, `lib/onboarding.ts` |
| Stats               | `app/main.py` (`/api/stats`) | `app/(main)/sources/page.tsx` |
| Live ingestion card | Same progress API | `app/(main)/sources/page.tsx` (poll active + status) |
| Export              | `app/main.py` (export/records, jsonl, csv, parquet, schema) | `app/(main)/export/page.tsx`, `lib/api.ts` |
