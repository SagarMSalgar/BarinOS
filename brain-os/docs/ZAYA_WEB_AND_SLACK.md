# ZAYA — Web Application Support & Slack (Supported Surfaces)

ZAYA is the intelligent layer inside every web application your team uses and in Slack. **Supported surfaces are Web and Slack only** (no browser extension in this scope).

## Two surfaces

| Surface | How it works | Use case |
|--------|----------------|----------|
| **Web** | Embeddable widget + backend APIs. Your app (Zendesk, Salesforce, Jira, Notion, HR, accounting, recruitment, or custom) embeds the ZAYA widget and passes context (ticket, deal, issue, page). ZAYA returns app-type-specific intelligence and "Ask ZAYA" answers. | Deep integration inside each app — right help at the right moment. |
| **Slack** | BrainOS Slack app: proactive offers (project plan, meeting summary, requirements), reminders, standup, onboarding. Same knowledge base. | Where teams already talk and share; knowledge surfaces in conversation. |

One knowledge base powers both. Update a policy once; it’s reflected in every web app panel and in Slack.

## Web application support (summary)

- **Zendesk / Freshdesk:** Ticket context → relevant policy, similar tickets, suggested response, tags, knowledge gaps.
- **Salesforce / HubSpot:** Deal/contact context → open issues, commitments, renewal talking points, competitive risk, next actions.
- **Jira / Linear:** Issue context → similar past issues, runbooks, ADRs, people who solved similar, spec completeness.
- **Notion / Confluence:** Page context → freshness, conflicts, unanswered questions, related pages.
- **HR (Darwinbox, Keka, etc.):** Form context → policy summary, balance/eligibility, approval process.
- **Accounting (Tally, Zoho Books):** Invoice/vendor context → vendor check, rate variance, budget, compliance.
- **Recruitment (Keka Recruit, Zoho Recruit):** Candidate + role → match to JD, compensation guide, interview questions.
- **Custom internal tools:** Widget embed with context (page type, record ID) → relevant docs, key facts, suggested actions.

Integration mechanisms:

- **Widget embed:** Most SaaS tools allow a custom script or sidebar; embed the ZAYA widget (see `web-app-widget/README.md`).
- **Native integration:** For platforms with apps/plugins (e.g. Zendesk app, Salesforce Lightning), the same widget or API can be used inside the native app.
- **API only:** Backend-to-backend: your app calls `POST /api/web-app/intelligence` and `POST /api/web-app/chat` with context and displays the response in your own UI.

## Slack (summary)

See **PROACTIVE_SLACK.md** for full configuration. BrainOS in Slack provides:

- Smart project planner, meeting summary, requirements analyser (with optional Google Sheet creation).
- Smart reminder (DM when a task is due).
- Standup collector and onboarding buddy.

Same tenant/namespace and knowledge base as the web widget.

## Implementation checklist

- [x] Backend: `POST /api/web-app/intelligence`, `POST /api/web-app/chat`, `GET /api/web-app/app-types`.
- [x] Backend: App-type-specific prompts and RAG in `web_app_service` (support, CRM, Jira, Notion, HR, accounting, recruitment, custom).
- [x] Embeddable widget: `web-app-widget/zaya-widget.js`, `zaya-widget.css`, configurable `apiBase`, `appType`, `tenantId`, `namespace`.
- [x] Widget demo: `web-app-widget/demo.html` (and served at `/static/demo.html` when running the backend).
- [x] Static mount: Backend serves `web-app-widget` at `/static` for script/style and demo.
- [x] Slack: Existing proactive flows and docs (PROACTIVE_SLACK.md).

## Running the widget demo

1. Start the BrainOS backend (e.g. `uvicorn app.main:app --reload` from `backend/`).
2. Open `http://localhost:8000/static/demo.html` (or open `web-app-widget/demo.html` in a browser and set `apiBase` to `http://localhost:8000` if CORS allows).
3. Choose a scenario (Zendesk, CRM, Jira, etc.) and click to open the ZAYA panel with that context.
