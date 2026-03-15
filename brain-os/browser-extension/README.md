# BrainOS Browser Extension

Chrome/Edge extension to add web pages to your BrainOS knowledge base and to ask BrainOS about selected text.

## Features

- **Add this page to BrainOS** — From the toolbar popup, send the current tab’s URL, title, and body text to your backend (`POST /api/ingest/web-page`). The backend runs a legal verdict on the URL (if configured) and ingests the content.
- **Ask BrainOS about this** — Select text on any page; a floating “Ask BrainOS about this” button appears. Click it to open a panel, enter a question, and get an answer from your BrainOS RAG (`POST /api/chat` with `pasted_context`).

## Setup

1. **Load the extension**
   - Open `chrome://extensions` (or your browser’s equivalent).
   - Enable **Developer mode**.
   - Click **Load unpacked** and select this `browser-extension` folder.

2. **Configure**
   - Click the extension icon → **Settings** (or right-click the icon → Options).
   - Set **Backend API URL** (e.g. `http://localhost:8000` or your deployed BrainOS backend).
   - Optionally set **API key** if your backend requires it.
   - Set **Tenant ID** and **Namespace** (defaults: `default`, `main`).

3. **Use**
   - **Add page:** Open any page, click the extension icon, then “Add this page to BrainOS”.
   - **Ask about selection:** Select text, click the floating “Ask BrainOS about this” button, type a question, and click Ask.

## Requirements

- BrainOS backend running and reachable from the browser (CORS is configured to allow all origins).
- For “Add this page”, the backend’s `POST /api/ingest/web-page` is used; if the URL is set, the backend may run a legal/robots check.
- For “Ask about this”, the backend’s `POST /api/chat` (non-streaming) is used with `question` and `pasted_context`.

## Files

- `manifest.json` — Manifest V3.
- `popup.html` / `popup.js` — Toolbar popup (Add page, Settings link).
- `options.html` / `options.js` — Settings (API URL, API key, tenant, namespace).
- `content.js` / `content.css` — Injected on all pages: selection detection, floating button, side panel for “Ask BrainOS”.
- `background.js` — Service worker: handles `ask` messages from content script and calls the backend `/api/chat`.
