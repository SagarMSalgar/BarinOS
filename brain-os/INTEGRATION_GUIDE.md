# BrainOS Integration Working Guide — Implementation Status

This document maps the **Complete Integration Working Guide** (product spec) to the current codebase: what is implemented, what is partial, and what requires new applications or infrastructure.

---

## Part 1 — Slack Integration

### Implemented (current codebase)

- **Slack OAuth “Connect Slack”**  
  Deploy tab → Slack → “Connect Slack” starts OAuth 2.0. Backend builds auth URL from `SLACK_CLIENT_ID` and redirect URI `BACKEND_URL` + `/api/sources/connections/slack/callback`. Callback exchanges code for bot token via Slack `oauth.v2.access`, stores `access_token`, `team_id`, `team_name` in `connected_tools.metadata` for the tenant.  
  Location: `main.py` (`start_connection_connect`, `connection_callback`).  
  Bot uses token from DB when event includes `team_id` (lookup by `metadata->>'team_id'`); falls back to env `SLACK_BOT_TOKEN` if not found.

- **Events API webhook**  
  `POST /api/bots/slack/events` — URL verification, `app_mention` (and optional `message`) handling.  
  Location: `backend/app/routers/slack_bot.py`.

- **Immediate 200 + background processing**  
  Handler returns `{"ok": true}` within milliseconds; RAG runs in `asyncio.create_task`. Prevents Slack retries.  
  Same file: `slack_events` → `_process_slack_event_and_reply`.

- **Event deduplication**  
  `event_id` (and `event_ts`/`ts`) cached in memory so each event is processed once.  
  `_seen_event_ids`, `_prune_seen_event_ids`.

- **Same RAG as main chat**  
  `_get_answer` uses `stream_answer` with same config, vector store, tenant/namespace, episodic and user memory, and **strict_mode=False** (matches Ask BrainOS default).  
  Namespace: `SLACK_NAMESPACE=my` (My brain) or `main` (Team brain).

- **Typing indicator**  
  Background task posts “BrainOS is thinking…” then deletes it after posting the final answer (`chat.postMessage` + `chat.delete`).

- **Block Kit reply**  
  One message with: answer block, divider, sources block, context block (confidence % + “Ask follow-up in thread or in Ask BrainOS”).  
  `_process_slack_event_and_reply` builds `blocks` and posts via `chat.postMessage`.

- **Slash command**  
  `POST /api/bots/slack/slash` — same `_get_answer`, optional `response_url` for in-channel reply with blocks.

- **Scopes in use**  
  Bot needs: `chat:write`, `app_mentions:read`, `channels:read` (for OAuth flow). For typing + delete, `chat:write` covers `chat.postMessage` and `chat.delete`.

- **Knowledge capture queue**  
  Table `knowledge_capture_queue`: pending Q&A from Slack/email. Endpoints: `GET /api/knowledge/capture` (list by tenant, status), `POST /api/knowledge/capture` (add candidate), `POST /api/knowledge/capture/{id}/approve` (ingest into vector store and mark approved). Export Studio UI: “Knowledge capture queue” section with Approve buttons.

- **Personal profiles**  
  Table `personal_profiles` (tenant_id, namespace, user_key, preferences JSONB). `GET/PUT /api/profile` for preferences. RAG: `stream_answer(..., user_key=...)` loads profile and injects “User profile (preferences): …” into system prompt. Slack bot passes `event.user` as `user_key`.

- **Graph-aware retrieval**  
  After vector search, RAG loads `source_trust` and filters hits with `trust_score < 0.3`. Checks `contradictions` for open conflicts among retrieved doc names; if any, adds “Some of the retrieved sources may contradict each other…” to system prompt.  
  Location: `backend/app/services/rag.py`.

- **Meeting summary**  
  `POST /api/meetings/summarize` (body: transcript, title) returns LLM-generated summary, decisions, action_items, open_questions. Deploy tab: “Meeting summary” channel with paste-transcript UI.

- **Ingest from email / web page**  
  `POST /api/ingest/email-thread` (tenant_id, namespace, subject, messages[]) ingests thread into knowledge base. `POST /api/ingest/web-page` (tenant_id, namespace, url, title, content) runs legal verdict if URL provided, then ingests. For use by browser extension or external tools.

### Partially implemented / config-only

- **Channel list / channel picker**  
  Spec: `channels:read` and UI to pick monitored channels.  
  Current: OAuth requests `channels:read`; no channel picker in UI. Bot replies in any channel it’s invited to when @mentioned.  
  To implement: `channels:read` scope, API to list channels, DB table for “monitored channels” and optional “all messages” vs “mentions only” per channel.

### Not implemented (spec only)

- **Additional scopes**  
  `channels:history`, `users:read`, `users:read.email`, `im:history`, `im:write`, `files:read`, `reactions:read` — for reading DMs, files, reactions, user directory, etc. Would be needed for: knowledge extraction from channel messages, proactive DMs, Google Sheets sharing by email, “message changed”, “file_shared”, “reaction_added”, “member_joined_channel”.

- **Subscribed events**  
  Only `app_mention` (and optionally `message`) are handled. No `message_changed`, `file_shared`, `reaction_added`, `member_joined_channel`.

- **Knowledge extraction from Slack**  
  No classifier (knowledge density / Q&A structure / sensitivity), no “Add to BrainOS?” ephemeral, no capture queue or ingestion from Slack threads.

- **Project planner**  
  No trigger from Slack, no Google Sheets creation, no file/URL extraction from messages, no sharing by email via `users:read.email`.

- **Pinecone**  
  Spec mentions Pinecone; codebase uses **Qdrant** as the vector store. Behavior is “vector store + RAG”; only the provider differs.

---

## Part 2 — Google Docs Integration

### Not implemented

- **Browser extension**  
  No Chrome/Firefox extension. No sidebar in Google Docs, no MutationObserver, no “Add to BrainOS” from Docs.

- **Google Drive API**  
  No version tracking, no polling of Drive file mtime, no re-ingest on change.

- **Real-time contradiction detection in Docs**  
  No extension sending paragraph text to BrainOS or showing conflict warnings in a sidebar.

All of Part 2 would require a separate browser-extension project and Google OAuth (Drive/Docs scopes) and backend endpoints for “add from Docs” and “check contradictions”.

---

## Part 3 — Email Integration (Gmail and Outlook)

### Not implemented

- **Gmail/Outlook tooling**  
  No extension for Gmail/Outlook, no “add thread to BrainOS”, no compose panel with suggested knowledge, no classifier for “high-value email” banner.

- **Outlook Add-in / COM add-in**  
  None.

Part 3 requires a separate extension/add-in and provider-specific APIs (Gmail API, Microsoft Graph).

---

## Part 4 — Browser Extension (Universal Layer)

### Implemented (current codebase)

- **Browser extension**  
  Chrome/Edge-compatible extension in `browser-extension/`: Manifest V3, popup, options, content script, background service worker.

- **Add page to knowledge base**  
  Toolbar popup: “Add this page to BrainOS” sends current tab’s URL, title, and `document.body.innerText` to `POST /api/ingest/web-page` (tenant_id, namespace from extension settings). Backend runs legal verdict when URL is present, then ingests.

- **“Ask BrainOS about this” (selected text)**  
  Content script: on text selection, a floating button “Ask BrainOS about this” appears. Click opens a side panel with the selected text as context, a question input, and an “Ask” button. Background script calls `POST /api/chat` with `question` and `pasted_context`; the panel shows the non-streamed answer.

- **Settings**  
  Options page: Backend API URL (required), optional API key, tenant ID, namespace. Stored in `chrome.storage.sync`.

- **Loading the extension**  
  1. Open `chrome://extensions`, enable “Developer mode”, “Load unpacked”, select the repo’s `browser-extension` folder.  
  2. Set Backend API URL (e.g. `http://localhost:8000`) and tenant/namespace in extension Settings.  
  3. Use “Add this page” from the toolbar or select text and use the floating “Ask BrainOS about this” button.

### Not implemented (spec only)

- **Current context (URL + title)**  
  No opt-in “share browsing context” sent to RAG; can be added by including URL/title in the chat request or pasted_context.

- **Google Docs / Gmail-specific UI**  
  Extension runs on all URLs; no Docs sidebar or Gmail compose integration (would require provider-specific content scripts and OAuth).

---

## Part 5 — Meeting Intelligence (Zoom and Google Meet)

### Not implemented

- **Meeting bot**  
  No joining of Zoom/Meet as a bot, no Calendar API or Zoom API integration.

- **Transcription**  
  No Whisper integration, no speaker diarization, no “Speaker 1 → Sarah” resolution.

- **Meeting summary pipeline**  
  No post-meeting summary (decisions, action items, open questions), no posting to Slack or creating Google Docs/Sheets, no knowledge-graph event nodes.

Part 5 would require: Zoom/Meet and Calendar OAuth, bot join flows, audio pipeline, Whisper (or similar), and backend jobs for summary and delivery.

---

## Part 6 — Knowledge Graph Database

### Partially implemented

- **Claims and contradictions**  
  Backend has claims extraction, contradiction detection, and trust-related endpoints. Not a full graph DB (e.g. Neo4j) with Document/Topic/Person/Question nodes and edges (COVERS, CONTRADICTS, EXPERT_IN, ANSWERED_BY, etc.).

- **Vector store**  
  Qdrant holds chunks and metadata (document_id, document_name, etc.). Used for retrieval and citations. No separate “graph retrieval” or reranking by trust/contradictions/history.

- **Feedback (thumbs up/down)**  
  No Slack (or in-app) feedback that updates document trust or answer quality in a graph.

To align with the spec would require: a graph database, write path for every document/question/feedback, and a retrieval path that merges vector + graph (trust, contradictions, “answered_by” quality).

---

## Part 7 — Personal Intelligence Layer

### Implemented (current codebase)

- **Personal profile**  
  Table `personal_profiles` (tenant_id, namespace, user_key, preferences JSONB). `GET/PUT /api/profile` for reading/updating preferences. RAG injects “User profile (preferences): …” into the system prompt when `user_key` is provided (e.g. from Slack `event.user`).

- **Inference from feedback**  
  When the user submits feedback via `POST /api/feedback` (thumbs down + “What was wrong?”), the backend infers preference deltas and merges them into `personal_profiles.preferences`. Mapping: `missing_info` → answer_length_preference “long”, detail_preference “high”; `wrong` → technical_depth “lower”, format_preference “concise”; free-text “too long”/“too much” → answer_length_preference “short”; “too short”/“show more” → “long” + detail “high”. Optional `user_key` in the feedback body (default “default”) so preferences are per user.  
  Location: `backend/app/services/preference_inference.py`; called from `submit_feedback` in `main.py`.  
  Table `answer_feedback` has optional `user_key` column (added in `init_db` if missing).

### Not implemented (spec only)

- **Topic weights, current project context, working patterns**  
  No schema or UI for these; preferences are free-form key/value and can be extended.

---

## Summary Table

| Component                    | Status        | Where / Notes                                      |
|----------------------------|---------------|----------------------------------------------------|
| Slack events + RAG reply   | Implemented   | `slack_bot.py` — 200 + background, dedup, Block Kit |
| Slack typing + confidence | Implemented   | “BrainOS is thinking…”, then delete; confidence in block |
| Slack OAuth + token from DB | Implemented | Deploy “Connect Slack”, callback stores token; bot uses by team_id |
| Knowledge capture queue + approve | Implemented | DB table, API, Export Studio section |
| Personal profiles + RAG         | Implemented | DB table, GET/PUT /api/profile, user_key in stream_answer |
| Graph-aware retrieval          | Implemented | Trust filter + contradiction note in rag.py |
| Meeting summarize API + UI     | Implemented | POST /api/meetings/summarize, Deploy “Meeting summary” |
| Ingest email / web page         | Implemented | POST /api/ingest/email-thread, /api/ingest/web-page |
| Browser extension          | Implemented | `browser-extension/` — Add page, Ask about selection, options |
| Google Docs / Drive        | Not implemented | Requires extension + Google OAuth                  |
| Gmail / Outlook            | Not implemented | Requires extension/add-in + provider APIs          |
| Meeting bot (Meet/Zoom)    | Not implemented | New services + OAuth + Whisper                     |
| Full knowledge graph       | Partial       | Claims/contradictions + trust + retrieval; no full graph DB |
| Personal intelligence      | Implemented  | Profile store + RAG injection + inference from feedback (what_wrong → preferences) |

---

## How to Extend Toward the Full Spec

1. **Slack**  
   Add Slack OAuth in Deploy (redirect + callback), store token per workspace, optionally add `channels:read` and channel picker. Then add event subscriptions and handlers for `message`, `file_shared`, etc., and a classifier + capture pipeline if you want knowledge extraction from Slack.

2. **Browser extension**  
   The repo includes a Chrome extension in `browser-extension/`. Load it via “Load unpacked” and set the Backend API URL in Settings. To add Docs/Gmail-specific UI (sidebar, “Add to BrainOS” from compose), add content scripts for those origins and optional OAuth.

3. **Meetings**  
   New service(s) for Meet/Zoom OAuth, bot join, audio → Whisper, and a job that builds summaries and posts to Slack / creates Docs/Sheets.

4. **Knowledge graph**  
   Introduce a graph DB (e.g. Neo4j), model nodes/edges as in the spec, and add a graph retrieval step that merges with vector retrieval and reranking.

5. **Personal layer**  
   Profile storage, RAG injection, and inference from feedback are implemented. To go further: add topic weights, current project context, and working patterns to the profile schema and UI.

The current codebase gives you a **working Slack bot** that uses the same RAG as Ask BrainOS, with typing indicator and Block Kit (answer, sources, confidence). The rest of the guide describes a larger product that can be added incrementally as above.
