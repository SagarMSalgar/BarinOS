# ZAYA Web Application Widget

Embeddable widget that brings ZAYA (BrainOS) intelligence into any web application — Zendesk, Freshdesk, Salesforce, HubSpot, Jira, Notion, HR systems, accounting tools, recruitment apps, or custom internal tools.

**Supported surfaces:** Web (this widget) and **Slack** only. The browser extension is a separate, passive overlay; this widget is for deep integration inside specific apps.

## Quick embed (3 lines)

Add to your application's HTML (e.g. Zendesk Guide, Salesforce Lightning, or any SaaS that allows custom script):

```html
<link rel="stylesheet" href="https://your-brainos-host/static/zaya-widget.css">
<script src="https://your-brainos-host/static/zaya-widget.js"></script>
<script>
  ZAYA.init({
    apiBase: 'https://your-brainos-api.com',  // BrainOS backend URL
    tenantId: 'default',
    namespace: 'main',
    appType: 'zendesk'   // zendesk | freshdesk | salesforce | hubspot | jira | linear | notion | confluence | hr | accounting | recruitment | custom
  });
</script>
```

When the user opens a ticket (or deal, issue, page), call:

```javascript
ZAYA.show({
  ticket_subject: 'Refund request',
  ticket_body: 'Customer wants refund for order #ORD-2847...',
  customer_name: 'Rahul Sharma',
  customer_ref: 'ORD-2847'
});
```

The widget will call `POST /api/web-app/intelligence` with this context and display the ZAYA panel (relevant policy, similar tickets, suggested response, etc.).

## App types and context shape

| App type       | Example context keys |
|----------------|----------------------|
| zendesk, freshdesk | ticket_subject, ticket_body, customer_name, customer_ref |
| salesforce, hubspot | deal_name, deal_value, deal_stage, context_text |
| jira, linear  | issue_title, issue_description, issue_status, issue_priority |
| notion, confluence | page_content |
| hr            | form_type, context_text |
| accounting    | context_text (invoice/vendor/expense details) |
| recruitment   | candidate_name, role_name, context_text |
| custom        | any keys; ZAYA returns relevant_docs, key_facts, suggested_actions |

## Ask ZAYA

The panel includes an input at the bottom. Users can type a question; the widget calls `POST /api/web-app/chat` and shows the answer in context of the current view.

## Where to see the widget on UI

- **Option A — Backend serving the demo**  
  Start the BrainOS backend (e.g. `uvicorn app.main:app --reload` from `backend/`), then open in a browser:
  - **`http://localhost:8000/static/demo.html`**  
  You’ll see the demo page with scenario buttons (Zendesk, CRM, Jira, Notion, HR, Custom). Click any button to open the ZAYA panel; the floating **Z** button also opens the panel with the last context.

- **Option B — From the BrainOS app (Deploy)**  
  In the main BrainOS frontend, go to **Deploy** and use the **“Open ZAYA Web App Demo”** link. It opens the same demo page (`/static/demo.html`) on your API host in a new tab.

- **Option C — Local file**  
  Open `web-app-widget/demo.html` directly in a browser. If the demo runs on a different origin than the API, set the backend URL in the demo (e.g. `apiBase: 'http://localhost:8000'`) and ensure CORS allows that origin.

## Demo

Open `demo.html` (via one of the options above). Set your backend URL if needed (default `http://localhost:8000`) and click the scenario buttons to simulate Zendesk, CRM, Jira, Notion, HR, and custom contexts. Ensure your BrainOS backend is running and CORS allows the demo origin.

## Backend

- `POST /api/web-app/intelligence` — body: `{ app_type, context, tenant_id?, namespace? }` → app-type-specific intelligence (policies, similar items, suggestions).
- `POST /api/web-app/chat` — body: `{ app_type, context, question, tenant_id?, namespace? }` → answer from knowledge base in context.
- `GET /api/web-app/app-types` — returns list of supported `app_type` values.

All powered by the same BrainOS knowledge base; one source of truth across web apps and Slack.
