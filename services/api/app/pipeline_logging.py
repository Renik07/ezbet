from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
import json
from . import runtime
from .runtime import logger


def _run_id(phase: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{phase}:{timestamp}"


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _current_ingest_started_at() -> datetime | None:
    latest_ingest_run = runtime.repository.get_latest_pipeline_run(phase="ingest", status="ok")
    return latest_ingest_run.started_at if latest_ingest_run else None


def _log_pipeline_event(
    event: str,
    *,
    phase: str,
    run_id: str | None = None,
    source: str | None = None,
    trigger: str | None = None,
    status: str | None = None,
    error_reason: str | None = None,
    duration_ms: int | None = None,
    counts: dict[str, int] | None = None,
    **extra: object,
) -> None:
    payload: dict[str, object] = {
        "event": event,
        "phase": phase,
    }
    if run_id:
        payload["run_id"] = run_id
    if source:
        payload["source"] = source
    if trigger:
        payload["trigger"] = trigger
    if status:
        payload["status"] = status
    if error_reason:
        payload["error_reason"] = error_reason
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if counts:
        payload["counts"] = counts

    for key, value in extra.items():
        if value is None:
            continue
        payload[key] = value

    logger.info("pipeline_event %s", json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))

