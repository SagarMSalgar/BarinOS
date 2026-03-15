# BrainOS Browser Extension — Feature Map

All features below are implemented end-to-end (extension UI + backend APIs).

---

## Feature 1 — Selected text vs knowledge base

- **Context menu (right-click on selection):**
  - **Compare with our knowledge** — Semantic comparison: CONSISTENT vs CONFLICTS from your KB.
  - **Fact-check against our docs** — Verdict (correct / incorrect / unverified), explanation, sources.
  - **Find our position on this** — Internal position/talking points + sources and confidence.
- **Flow:** Select text → right-click → action → backend `POST /api/extension/text-vs-kb` → side panel. **Ask BrainOS** in panel opens Q&A with that selection as context.

---

## Feature 2 — Live document assistant (Google Docs)

- **Content script:** `content-docs.js` on `docs.google.com`.
- **UI:** “Verify with BrainOS” button (top-right). Select text (or use full visible content) → click → sentences sent to `POST /api/extension/verify-claims` → panel shows each claim as Supported or Unverified/Incorrect with explanation and sources.

---

## Feature 3 — Email intelligence (Gmail)

- **Content script:** `content-gmail.js` on `mail.google.com`.
- **UI:** “Email intel” button. Click → visible email context (subject from title, body from main area) sent to `POST /api/extension/email-analyze` → side panel with key info, suggested actions, reply context, related doc names.

---

## Feature 4 — Meeting preparation (Google Calendar)

- **Content script:** `content-calendar.js` on `calendar.google.com`.
- **UI:** “Get meeting brief” button. Uses page title or selection as meeting title → `POST /api/extension/meeting-prep` → panel with brief, related docs, suggested questions from KB.

---

## Feature 5 — Competitive intelligence watcher

- **Context menu:** Right-click page → **Watch this page (BrainOS)** → URL stored in backend; first check saves baseline.
- **Popup:** “Check current page for changes” → sends current page text to `POST /api/extension/watch-page` (action: check) → panel shows “Content changed” or “No changes”. Watched list shown in popup via `GET /api/extension/watched-pages`.
- **Backend:** Table `extension_watched_pages`; hash diff for change detection.

---

## Feature 6 — Contract and document reviewer

- **Context menu:** Right-click page → **Review with ZAYA (contract)** → full page text sent to `POST /api/extension/contract-review` → panel with consistent clauses, deviations (risk), and clauses not in standard.

---

## Feature 7 — Research synthesis

- **Popup:** “Add this page to research” (stores url, title, text in `chrome.storage.local`). “Synthesise research” → sends collected sources to `POST /api/extension/research-synthesize` → panel on current tab with key findings, agreements, disagreements, synthesis draft.
- **Context menu:** **Add page to research** (same as popup add).

---

## Feature 8 — WhatsApp Web knowledge capture

- **Content script:** `content-whatsapp.js` on `web.whatsapp.com`.
- **UI:** “Capture to BrainOS” button. Click → visible chat text + chat title sent to `POST /api/ingest` (document_name e.g. “WhatsApp - [Chat] - date”) → ingest into KB. Ask about captured content via main BrainOS chat/extension.

---

## Feature 9 — Form and RFP auto-fill

- **Context menu:** Right-click page → **Fill form with BrainOS** → form fields (labels from name/id/placeholder/label) sent to `POST /api/extension/form-suggest` → panel with suggestions and **Fill all** (applies values to matching inputs/textareas).
- **Floating button:** On pages with `<form>`, “Fill with BrainOS” button (bottom-right) → same flow.

---

## Backend APIs summary

| Endpoint | Purpose |
|----------|--------|
| `POST /api/extension/text-vs-kb` | Compare / fact-check / position. |
| `POST /api/extension/verify-claims` | Verify list of claims (Docs assistant). |
| `POST /api/extension/email-analyze` | Email key info, actions, reply context. |
| `POST /api/extension/contract-review` | Contract vs standard terms. |
| `POST /api/extension/research-synthesize` | Synthesize multiple sources. |
| `POST /api/extension/form-suggest` | Form field value suggestions. |
| `POST /api/extension/meeting-prep` | Meeting brief from KB. |
| `GET /api/extension/watched-pages` | List watched URLs. |
| `POST /api/extension/watch-page` | Add (action: add) or check (action: check) page. |

---

## How to test

1. **Backend:** Run with vector store and LLM; ingest some documents. Ensure CORS allows your extension origin (or use a proxy).
2. **Extension:** Load unpacked from `browser-extension/`. Options: API URL (e.g. `http://localhost:8000`), API key (if required), tenant ID, namespace.
3. **Compare / fact-check / position:** Any page → select text → right-click → choose action.
4. **Gmail:** Open Gmail → click “Email intel”.
5. **Docs:** Open a Google Doc → select text → “Verify with BrainOS”.
6. **Calendar:** Open Google Calendar → “Get meeting brief”.
7. **Watch:** Right-click page → “Watch this page”; later use popup “Check current page for changes”.
8. **Contract:** Right-click contract page → “Review with ZAYA”.
9. **Research:** Add a few pages via popup or context menu → “Synthesise research”.
10. **WhatsApp Web:** Open web.whatsapp.com → “Capture to BrainOS”.
11. **Forms:** Open a page with a form → “Fill with BrainOS” or right-click → “Fill form with BrainOS”.
