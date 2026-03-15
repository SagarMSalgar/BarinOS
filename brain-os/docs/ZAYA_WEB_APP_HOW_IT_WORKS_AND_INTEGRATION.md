# How ZAYA Web Application Features Work & Where They Integrate

This document explains **how** the features work end-to-end and **how/where** they get integrated (Zendesk, CRM, Jira, Notion, HR, custom apps, Slack).

---

## 1. How the features work (end-to-end)

### One flow for all app types

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  YOUR APP (Zendesk / Salesforce / Jira / Notion / HR / Custom)                │
│  User opens a ticket / deal / issue / page / form                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  INTEGRATION LAYER                                                           │
│  • Widget embed: Your app loads zaya-widget.js and calls ZAYA.show(context)  │
│  • Or API-only: Your app calls POST /api/web-app/intelligence with context   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  BRAINOS BACKEND (your BrainOS API host)                                      │
│  • Receives app_type + context (e.g. ticket_subject, ticket_body, …)        │
│  • Vector search: finds relevant chunks from your knowledge base             │
│  • LLM: uses app-type-specific prompt (support / CRM / Jira / …)             │
│  • Returns structured JSON (policy, similar tickets, suggested response, …)  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  YOUR APP again                                                              │
│  • Widget: shows ZAYA panel (policy, suggestions, “Ask ZAYA” input)           │
│  • API-only: your UI renders the JSON in your own layout                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Data source:** Everything is driven by your **BrainOS knowledge base** (documents you’ve ingested: policies, playbooks, runbooks, HR docs, contracts, etc.). Same KB for every app type and for Slack.

---

## 2. Two integration options

| Option | Who does it | Where it runs | Best for |
|--------|-------------|---------------|----------|
| **Widget embed** | You add a script tag + init + call `ZAYA.show(context)` when the user opens a record. | Inside the target app’s UI (Zendesk, Salesforce, your internal app). | Any app that allows custom JS or a sidebar/custom HTML. |
| **API only** | Your backend or frontend calls BrainOS APIs and you build your own panel/UI. | Your servers or your SPA. | Full control over UI, or when you can’t inject a script. |

Both use the same backend endpoints and the same knowledge base.

---

## 3. Where each feature integrates (by application)

### 3.1 Zendesk / Freshdesk (support)

- **Where it integrates:** Inside the agent’s ticket view (sidebar or panel next to the ticket).
- **What you pass:** Ticket subject, body, customer name, order/ref.
- **What ZAYA shows:** Relevant policy, eligibility/exception notes, similar past tickets, suggested response, suggested tags, knowledge gaps.
- **How to integrate:**
  - **Widget:** Add the script in Zendesk (e.g. Guide / custom app or sidebar). When an agent opens a ticket, your code reads subject/body/customer from the Zendesk API or DOM and calls `ZAYA.init({ appType: 'zendesk', … }); ZAYA.show({ ticket_subject, ticket_body, customer_name, customer_ref });`.
  - **API only:** Your Zendesk app or middleware fetches ticket data, calls `POST /api/web-app/intelligence` with `app_type: "zendesk"` and the same context, then renders the response in your custom sidebar/panel.

### 3.2 Salesforce / HubSpot (CRM)

- **Where it integrates:** On the Deal or Contact record page (sidebar or tab).
- **What you pass:** Deal name, value, stage, plus any notes (e.g. open issues, commitments) in `context_text`.
- **What ZAYA shows:** Open issues affecting renewal, commitments made, renewal talking points, competitive risk, suggested next actions.
- **How to integrate:**
  - **Widget:** In Lightning (LWC) or a Visualforce page, or in HubSpot custom module, load the widget script. When the user opens a deal/contact, get current record from the CRM API and call `ZAYA.show({ deal_name, deal_value, deal_stage, context_text })`.
  - **API only:** Your CRM middleware or a small backend gets the record, calls `/api/web-app/intelligence` with `app_type: "salesforce"` or `"hubspot"`, and your UI shows the returned blocks (e.g. open issues, talking points).

### 3.3 Jira / Linear (project management)

- **Where it integrates:** On the issue/ticket view (sidebar or panel).
- **What you pass:** Issue title, description, status, priority.
- **What ZAYA shows:** Similar past issues + resolution, relevant runbooks/ADRs, people who solved similar, estimated resolution; for spec tickets, spec completeness (missing/vague sections).
- **How to integrate:**
  - **Widget:** In Jira (e.g. Forge app or custom panel) or Linear, load the widget. When an issue is opened, pass `issue_title`, `issue_description`, `issue_status`, `issue_priority` into `ZAYA.show(...)`.
  - **API only:** Your Jira/Linear app or a service fetches the issue, calls the intelligence API with `app_type: "jira"` or `"linear"`, and displays the result in your own panel.

### 3.4 Notion / Confluence (wiki)

- **Where it integrates:** Sidebar or inline when viewing/editing a page.
- **What you pass:** Page content (or a representative excerpt).
- **What ZAYA shows:** Freshness alerts, conflicts with other docs, unanswered questions about the topic, related pages.
- **How to integrate:**
  - **Widget:** If the product allows custom embeds or sidebar (e.g. Notion embed, Confluence macro), load the widget and pass `page_content` (and optionally `form_type: "wiki_page"`) when the page is open.
  - **API only:** Your integration gets the current page body, calls the API with `app_type: "notion"` or `"confluence"`, and shows freshness/conflicts in your UI.

### 3.5 HR systems (Darwinbox, Keka, Zoho People, etc.)

- **Where it integrates:** On the leave application, reimbursement form, or performance review screen.
- **What you pass:** `form_type` (e.g. `leave_application`, `reimbursement`) and any visible context (e.g. employee id, dates).
- **What ZAYA shows:** Policy summary, balance/eligibility, approval process, warnings; for reviews, suggested talking points.
- **How to integrate:**
  - **Widget:** If the HR app allows custom script or a “help” panel, load the widget and call `ZAYA.show({ form_type: 'leave_application', context_text: '...' })` when the user is on that form.
  - **API only:** Your HR integration or middleware sends form type + context to `/api/web-app/intelligence` with `app_type: "hr"` and renders the response (e.g. policy, balance) in the HR app’s custom panel or a linked help page.

### 3.6 Accounting (Tally, Zoho Books, QuickBooks, etc.)

- **Where it integrates:** When viewing/approving an invoice or expense.
- **What you pass:** Invoice/vendor/expense details in `context_text` (vendor name, amount, rates, category).
- **What ZAYA shows:** Vendor approval status, rate variance vs contract, budget check, compliance notes, suggested action.
- **How to integrate:**
  - **Widget or API:** Same pattern: when the user opens an invoice, your code sends context to the intelligence API with `app_type: "accounting"` and either the widget displays the result or your own UI does.

### 3.7 Recruitment (Keka Recruit, Zoho Recruit, Naukri RMS, etc.)

- **Where it integrates:** On the candidate profile or role screen.
- **What you pass:** Candidate name, role name, and any summary (resume highlights, JD) in `context_text`.
- **What ZAYA shows:** Candidate match to JD, compensation guide, interview questions, similar past hire.
- **How to integrate:**
  - **Widget or API:** Load widget or call API with `app_type: "recruitment"` and `candidate_name`, `role_name`, `context_text` when viewing a candidate; render the returned match and questions in your ATS UI.

### 3.8 Custom internal tools (dashboards, CRMs, ops tools)

- **Where it integrates:** Any screen where the user needs knowledge (e.g. customer view, logistics view, report).
- **What you pass:** Any context (e.g. `page_type`, `record_id`, `context_text`).
- **What ZAYA shows:** Relevant docs, key facts, suggested actions, short summary (`custom_intelligence` prompt).
- **How to integrate:**
  - **Widget:** Add the script to your SPA or internal portal. On route or record change, call `ZAYA.init({ appType: 'custom', ... }); ZAYA.show({ page_type, record_id, context_text })`.
  - **API only:** Your backend or frontend calls `POST /api/web-app/intelligence` with `app_type: "custom"` and your context; you render the JSON in your own component.

---

## 4. Slack (separate surface, same KB)

- **Where it integrates:** Inside Slack (channels and DMs where the BrainOS app is installed).
- **How it works:** BrainOS classifies messages (e.g. project planning, meeting notes, requirements). When it detects an intent, it posts one proactive offer (e.g. “Create a plan?”, “Summarise this meeting?”). User clicks; BrainOS uses the **same knowledge base** to generate plans, summaries, action items, and can create Google Sheets, send reminders, run standup, etc.
- **Integration:** You connect Slack via OAuth in BrainOS (Deploy → Slack). No widget in Slack; the bot and the backend do the work. See `PROACTIVE_SLACK.md`.

---

## 5. Technical summary: endpoints and widget

- **Intelligence (context → structured help):**  
  `POST /api/web-app/intelligence`  
  Body: `{ "app_type": "zendesk"|"salesforce"|"jira"|…|"custom", "context": { … }, "tenant_id": "default", "namespace": "main" }`  
  Response: app-type-specific JSON (e.g. `relevant_policy`, `suggested_response` for Zendesk; `open_issues`, `suggested_next_actions` for CRM).

- **Ask ZAYA (question in context):**  
  `POST /api/web-app/chat`  
  Body: `{ "app_type", "context", "question", "tenant_id", "namespace" }`  
  Response: `{ "answer", "citations" }`.

- **Widget script (for embed):**  
  Served by your BrainOS backend at `/static/zaya-widget.js` and `/static/zaya-widget.css`.  
  Init: `ZAYA.init({ apiBase: 'https://your-brainos-api.com', tenantId, namespace, appType })`.  
  Show: `ZAYA.show(context)` when the user opens a ticket/deal/issue/page/form.  
  Demo: `https://your-brainos-api.com/static/demo.html`.

- **App types:**  
  `GET /api/web-app/app-types` returns the list of supported `app_type` values.

---

## 6. Who does what (roles)

| Role | Responsibility |
|------|-----------------|
| **BrainOS admin** | Ingest and maintain the knowledge base; configure tenant/namespace; (optional) set `WEB_APP_WIDGET_DIR` or volume for Docker so `/static` serves the widget. |
| **Your dev / integration team** | In each target app (Zendesk, Salesforce, Jira, Notion, HR, accounting, recruitment, custom): either embed the widget and pass context, or call the APIs and build your own UI. Ensure CORS allows your BrainOS API host if the widget runs in the browser. |
| **End users (agents, sales, engineers, HR, finance)** | Use the ZAYA panel or your custom UI inside the app they already use; type questions in “Ask ZAYA” when needed. |

Once the widget is embedded or the API is called with the right `app_type` and `context`, the **feature runs automatically**: backend does RAG + LLM and returns the right structure; the widget (or your UI) displays it.
