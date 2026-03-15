"""Ingestion job progress for live UI updates. In-memory store; use Redis in multi-instance."""
from __future__ import annotations

from typing import Any

_jobs: dict[str, dict[str, Any]] = {}
_MAX_LOG = 80


def set_progress(document_id: str, phase: str, current: int, total: int, message: str) -> None:
    existing = _jobs.get(document_id) or {}
    log: list[str] = list(existing.get("log") or [])
    log.append(message)
    if len(log) > _MAX_LOG:
        log = log[-_MAX_LOG:]
    _jobs[document_id] = {
        "document_id": document_id,
        "phase": phase,
        "current": current,
        "total": total,
        "message": message,
        "percentage": round(100 * current / total, 1) if total else 0,
        "log": log,
    }


def append_log(document_id: str, message: str) -> None:
    """Append a log line without changing phase/percentage (e.g. for crawl: 'Reading page 3 of 20...')."""
    existing = _jobs.get(document_id) or {}
    log: list[str] = list(existing.get("log") or [])
    log.append(message)
    if len(log) > _MAX_LOG:
        log = log[-_MAX_LOG:]
    _jobs[document_id] = {**existing, "message": message, "log": log}


def set_done(document_id: str, chunks_created: int) -> None:
    existing = _jobs.get(document_id) or {}
    log: list[str] = list(existing.get("log") or [])
    log.append(f"Indexed {chunks_created} chunks. Your AI is ready.")
    if len(log) > _MAX_LOG:
        log = log[-_MAX_LOG:]
    _jobs[document_id] = {
        "document_id": document_id,
        "phase": "done",
        "current": chunks_created,
        "total": chunks_created,
        "message": f"Indexed {chunks_created} chunks. Your AI is ready.",
        "percentage": 100,
        "log": log,
    }


def set_error(document_id: str, error: str) -> None:
    existing = _jobs.get(document_id) or {}
    log: list[str] = list(existing.get("log") or [])
    log.append(f"Error: {error}")
    _jobs[document_id] = {
        "document_id": document_id,
        "phase": "error",
        "message": error,
        "percentage": 0,
        "log": log,
    }


def get_progress(document_id: str) -> dict[str, Any] | None:
    return _jobs.get(document_id)


def get_active_jobs(tenant_id: str | None = None) -> list[dict[str, Any]]:
    """Return all jobs that are not done/error (for live ingestion card)."""
    out = []
    for j in _jobs.values():
        if j.get("phase") not in ("done", "error"):
            out.append(j)
    return out[:10]
