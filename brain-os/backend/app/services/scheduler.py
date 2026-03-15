"""Background scheduler: weekly gap report via asyncio task (no APScheduler dependency)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable, Awaitable

_job_store: dict[str, Any] = {}
_task: asyncio.Task | None = None


async def run_weekly_gap_report(
    generate_report_fn: Callable[..., Awaitable[dict]],
    get_unanswered_fn: Callable[[], Awaitable[list[dict]]],
    save_report_fn: Callable[[dict], Awaitable[None]] | None = None,
) -> None:
    """Job: collect unanswered questions, generate gap report, optionally save."""
    questions = await get_unanswered_fn()
    if not questions:
        _job_store["last_gap_report"] = {"clustered_gaps": [], "priority_ranking": [], "ai_fix_suggestions": [], "completeness_score": 0.0}
        return
    report = await generate_report_fn(questions)
    _job_store["last_gap_report"] = report
    if save_report_fn:
        await save_report_fn(report)


def _next_weekday(weekday: int, hour: int, minute: int) -> datetime:
    """Next occurrence of weekday (0=Monday) at given hour:minute."""
    now = datetime.utcnow()
    days_ahead = weekday - now.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    next_date = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    return next_date


async def _scheduler_loop(
    generate_report_fn,
    get_unanswered_fn,
    save_report_fn,
    cron_weekday: str = "mon",
    hour: int = 9,
    minute: int = 0,
):
    weekday_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    w = weekday_map.get(cron_weekday.lower()[:3], 0)
    while True:
        next_run = _next_weekday(w, hour, minute)
        delay = (next_run - datetime.utcnow()).total_seconds()
        if delay < 0:
            delay += 7 * 24 * 3600
        await asyncio.sleep(min(delay, 86400))
        if (datetime.utcnow() - next_run).total_seconds() > -60:
            await run_weekly_gap_report(generate_report_fn, get_unanswered_fn, save_report_fn)


def start_scheduler(
    generate_report_fn,
    get_unanswered_fn,
    save_report_fn=None,
    cron_weekday: str = "mon",
    hour: int = 9,
    minute: int = 0,
) -> None:
    """Start background asyncio task for weekly gap report."""
    global _task
    if _task is not None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _task = loop.create_task(
        _scheduler_loop(generate_report_fn, get_unanswered_fn, save_report_fn, cron_weekday, hour, minute)
    )


def get_last_gap_report() -> dict[str, Any] | None:
    return _job_store.get("last_gap_report")


def get_scheduler():
    """No-op for compatibility; we use asyncio task."""
    return None


def stop_scheduler():
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None
