# BrainOS Proactive Assistant — Slack

BrainOS in Slack follows **one offer, one time, then silence**. If the user ignores an offer, BrainOS never mentions it again in that conversation.

## Required Slack app configuration

### Scopes (OAuth & Permissions)

**Bot token scopes:**

- `app_mentions:read` — receive @mentions
- `chat:write` — post messages and ephemeral
- `chat:write.public` — post in channels without joining (optional)
- `chat:write.customize` — optional
- `channels:history` — read channel messages (for thread replies)
- `groups:history` — read private channel messages
- `im:history` — read DMs (for reminders/onboarding)
- `im:write` — send DMs
- `mpim:history` — read multi-party IM
- `users:read` — resolve @mentions to emails (for sharing sheets)
- `users:read.email` — get user email for sharing
- `files:read` — download files shared in threads (PDF, DOCX, images, etc.)
- `reactions:read` — optional
- `commands` — if using slash command

**Event subscriptions (Subscribe to bot events):**

- `app_mention` — when someone @mentions the app
- `message.channels` — messages in public channels (for proactive classifier)
- `message.groups` — messages in private channels
- `message.im` — DMs
- `member_joined_channel` — for onboarding DM

**Interactivity & Shortcuts:**

- Enable Interactivity and set **Request URL** to:  
  `https://<your-backend>/api/bots/slack/interactions`
- Use this for block actions (buttons) and modal submissions.

### Environment variables

- `SLACK_SIGNING_SECRET` — from App Credentials
- `SLACK_BOT_TOKEN` — bot token (or use OAuth and store in `connected_tools`)
- `SLACK_TENANT_ID`, `SLACK_NAMESPACE` — default tenant/namespace
- `SLACK_SKIP_SIGNATURE_VERIFICATION` — set to `1` only in dev

For Google Sheets (project plan, action items, clarification sheet):

- Connect Google in BrainOS (Sources): OAuth with scope `https://www.googleapis.com/auth/spreadsheets` and `https://www.googleapis.com/auth/drive`. Store access token in `connected_tools` with provider `google_sheets` or `drive`.

## Features

1. **Smart Project Planner** — When the classifier sees planning/task/deadline language (≥3 signals) in a thread, BrainOS posts one *ephemeral* offer. If the user clicks "Yes", they share text/files; BrainOS extracts content, cross-references the knowledge base, generates a plan, shows a preview, then creates a Google Sheet (Overview, Task Tracker, Timeline, Team & Roles, Risk Register) and can share it.
2. **Meeting Summary** — When meeting notes/transcript are shared, BrainOS offers to extract decisions, action items, and open questions, and optionally create an action-items sheet.
3. **Requirements Analyser** — When a requirements doc/spec is shared, BrainOS offers to analyse clarity, missing sections, effort, and questions to ask, and optionally create a clarification sheet.
4. **Smart Reminder** — One DM to the assignee when a task is due soon (no channel posts, no escalation). Configure via `reminders-run` cron.
5. **Standup Collector** — Admin configures a channel and time. At that time, BrainOS posts a message with "Submit standup"; users open a modal (Yesterday / Today / Blockers). Use `standup-publish` to compile and post the summary.
6. **Onboarding Buddy** — When a user joins a channel (`member_joined_channel`), BrainOS sends one DM with the top 5 questions from the knowledge base. Never messages again unless they ask.

## API endpoints (for cron / admin)

- `POST /api/bots/slack/standup-trigger?team_id=...&channel_id=...` — Post standup prompt (call at configured time).
- `POST /api/bots/slack/standup-publish?team_id=...&channel_id=...&submission_date=...` — Compile and post standup summary.
- `POST /api/bots/slack/reminders-run?team_id=...` — Send task-due DMs (extend when assignees/due dates are stored).
- `GET/POST /api/bots/slack/standup-config` — List or set standup channel and time.
- `GET/POST /api/bots/slack/quiet-channels` — List or set channels where BrainOS never makes proactive offers.

## Anti-stalking rules

- One offer per thread per feature; then silence.
- Proactive offers are *ephemeral* (only the recipient sees them).
- Every offer includes a "Turn off this feature" link (point to your settings page).
- Reminders go by DM only; never post in channel or escalate to manager.
- Classifier confidence must be ≥ 85% before any offer.
- Quiet channels: no proactive offers; only respond when @mentioned.
