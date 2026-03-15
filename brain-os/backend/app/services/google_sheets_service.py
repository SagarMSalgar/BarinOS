"""Create and share Google Sheets for BrainOS project plans, task trackers, and clarification sheets."""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def _get_sheets_service(access_token: str):
    """Build Sheets API service from OAuth access token."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(token=access_token)
    return build("sheets", "v4", credentials=creds)


def _get_drive_service(access_token: str):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(token=access_token)
    return build("drive", "v3", credentials=creds)


def _flatten_plan_tasks(plan: dict[str, Any]) -> list[dict]:
    """Convert plan phases/tasks into flat rows."""
    rows = []
    phases = plan.get("phases") or []
    for phase in phases:
        pname = phase.get("name") or ""
        for t in phase.get("tasks") or []:
            deps = t.get("dependencies") or []
            dep_str = ", ".join(str(d) for d in deps) if isinstance(deps, list) else str(deps)
            rows.append({
                "phase": pname,
                "name": t.get("name") or "",
                "description": t.get("description") or "",
                "duration_days": t.get("duration_days") or 0,
                "dependencies": dep_str,
                "suggested_role": t.get("suggested_role") or "",
            })
    return rows


async def create_project_plan_spreadsheet(
    access_token: str,
    plan: dict[str, Any],
    project_name: str,
    *,
    tenant_id: str,
    team_id: str,
) -> dict[str, Any]:
    """Create Google Sheet with tabs: Overview, Task Tracker, Timeline, Team & Roles, Risk Register."""
    service = _get_sheets_service(access_token)
    drive = _get_drive_service(access_token)

    title = f"{project_name} — Project Plan"
    body = {"properties": {"title": title}}
    spreadsheet = service.spreadsheets().create(body=body).execute()
    sheet_id = spreadsheet["spreadsheetId"]
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

    sheets = spreadsheet.get("sheets", [])
    first_sheet_id = sheets[0]["properties"]["sheetId"] if sheets else 0

    requests = [
        {"updateSheetProperties": {"properties": {"sheetId": first_sheet_id, "title": "Project Overview"}, "fields": "title"}},
        {"addSheet": {"properties": {"title": "Task Tracker"}}},
        {"addSheet": {"properties": {"title": "Timeline"}}},
        {"addSheet": {"properties": {"title": "Team & Roles"}}},
        {"addSheet": {"properties": {"title": "Risk Register"}}},
    ]
    service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": requests}).execute()

    risks = plan.get("risks") or []
    risk_line = "; ".join((r.get("description") or "")[:80] for r in risks[:3]) if risks else "None"
    total_tasks = sum(len(p.get("tasks") or []) for p in (plan.get("phases") or []))
    overview_rows = [
        ["Project", project_name],
        ["Description", (plan.get("description") or "")[:500]],
        ["Deadline", plan.get("deadline") or "TBD"],
        ["Total tasks", str(total_tasks)],
        ["Overall status", "Not started"],
        ["Key risks", risk_line[:500]],
        ["Last updated", ""],
    ]
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id, range="Project Overview!A1:B10",
        valueInputOption="RAW", body={"values": overview_rows},
    ).execute()

    flat = _flatten_plan_tasks(plan)
    tracker_header = ["Task ID", "Phase", "Task Name", "Description", "Owner", "Status", "Start Date", "Due Date", "Dependencies", "Notes"]
    tracker_rows = [tracker_header]
    for i, t in enumerate(flat, 1):
        tracker_rows.append([
            f"T{i}", t["phase"], t["name"], (t["description"] or "")[:500], "",
            "Not started", "", "", t["dependencies"], t["suggested_role"],
        ])
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id, range="'Task Tracker'!A1:J" + str(len(tracker_rows) + 5),
        valueInputOption="RAW", body={"values": tracker_rows},
    ).execute()

    sheet_meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    tracker_sheet_id = next((s["properties"]["sheetId"] for s in sheet_meta["sheets"] if s["properties"]["title"] == "Task Tracker"), 1)
    row_count = len(tracker_rows)
    if row_count > 1:
        try:
            service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": [{
                "setDataValidation": {
                    "range": {"sheetId": tracker_sheet_id, "startRowIndex": 1, "endRowIndex": row_count, "startColumnIndex": 5, "endColumnIndex": 6},
                    "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "Not started"}, {"userEnteredValue": "In progress"}, {"userEnteredValue": "Done"}, {"userEnteredValue": "Blocked"}]}, "strict": True, "showCustomUi": True},
                }
            }]}).execute()
        except Exception as e:
            log.warning("Data validation failed: %s", e)

    roles = list({t["suggested_role"] for t in flat if t["suggested_role"]})
    team_rows = [["Role", "Person's Name", "Email", "Slack Handle"]] + [[r, "", "", ""] for r in roles]
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id, range="'Team & Roles'!A1:D20", valueInputOption="RAW", body={"values": team_rows},
    ).execute()

    risk_rows = [["Risk Description", "Likelihood", "Impact", "Mitigation Suggestion"]]
    for r in (plan.get("risks") or []):
        risk_rows.append([(r.get("description") or "")[:500], r.get("likelihood") or "Medium", r.get("impact") or "Medium", (r.get("mitigation") or "")[:500]])
    if len(risk_rows) == 1:
        risk_rows.append(["No risks identified", "", "", ""])
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id, range="'Risk Register'!A1:D30", valueInputOption="RAW", body={"values": risk_rows},
    ).execute()

    timeline_rows = [["Task", "Start Date", "End Date", "Notes"], ["(Fill dates for Gantt view)", "", "", ""]]
    for t in flat[:20]:
        timeline_rows.append([t["name"], "", "", ""])
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id, range="'Timeline'!A1:D25", valueInputOption="RAW", body={"values": timeline_rows},
    ).execute()

    tasks_for_reminders = [{"task_id": f"T{i}", "name": t["name"], "suggested_role": t["suggested_role"]} for i, t in enumerate(flat, 1)]
    return {"sheet_id": sheet_id, "sheet_url": sheet_url, "tasks_for_reminders": tasks_for_reminders, "total_tasks": len(flat)}


async def share_spreadsheet(access_token: str, sheet_id: str, share_entries: list[dict], creator_email: str | None = None) -> list[dict]:
    """share_entries: [{"email": str, "role": "writer"|"reader"|"commenter"}, ...]. Returns [{"email", "role", "success"}, ...]."""
    drive = _get_drive_service(access_token)
    results = []
    for entry in share_entries:
        email = (entry.get("email") or "").strip()
        role = (entry.get("role") or "reader").lower()
        if not email or "@" not in email:
            results.append({"email": email, "role": role, "success": False, "error": "Invalid email"})
            continue
        perm_role = "writer" if role in ("editor", "writer") else "commenter" if role == "commenter" else "reader"
        try:
            drive.permissions().create(
                fileId=sheet_id, body={"type": "user", "role": perm_role, "emailAddress": email},
                sendNotificationEmail=True, fields="id",
            ).execute()
            results.append({"email": email, "role": perm_role, "success": True})
        except Exception as e:
            results.append({"email": email, "role": role, "success": False, "error": str(e)[:200]})
    return results


async def create_action_items_sheet(access_token: str, action_items: list[dict], title: str = "Meeting action items") -> dict:
    """Single-tab sheet: What, Owner, Due, Status."""
    service = _get_sheets_service(access_token)
    spreadsheet = service.spreadsheets().create(body={"properties": {"title": title}}).execute()
    sheet_id = spreadsheet["spreadsheetId"]
    rows = [["What", "Owner", "Due", "Status"]]
    for a in action_items:
        rows.append([(a.get("what") or "")[:500], a.get("owner_mentioned") or "", a.get("due") or "", "Not started"])
    service.spreadsheets().values().update(spreadsheetId=sheet_id, range="A1:D100", valueInputOption="RAW", body={"values": rows}).execute()
    return {"sheet_id": sheet_id, "sheet_url": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"}


async def create_clarification_sheet(access_token: str, issues: list, title: str = "Requirements clarification") -> dict:
    """Columns: Issue, Question to Ask, Person to Ask, Answer, Status."""
    service = _get_sheets_service(access_token)
    spreadsheet = service.spreadsheets().create(body={"properties": {"title": title}}).execute()
    sheet_id = spreadsheet["spreadsheetId"]
    rows = [["Issue", "Question to Ask", "Person to Ask", "Answer", "Status"]]
    for i in (issues if isinstance(issues, list) else []):
        if isinstance(i, dict):
            rows.append([(i.get("requirement_or_section") or i.get("issue") or "")[:300], (i.get("note") or i.get("question") or "")[:500], "", "", "Open"])
        else:
            rows.append([str(i)[:300], "", "", "", "Open"])
    service.spreadsheets().values().update(spreadsheetId=sheet_id, range="A1:E100", valueInputOption="RAW", body={"values": rows}).execute()
    return {"sheet_id": sheet_id, "sheet_url": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"}
