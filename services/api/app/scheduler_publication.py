from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from .models import PublishSchedulerRunResponse
from . import runtime
from .runtime import (
    PUBLISH_SCHEDULER_LOCK_KEY,
    logger,
)
from .pipeline_logging import (
    _duration_ms,
    _log_pipeline_event,
    _run_id,
)
from .service_publication import _run_publish_for_drafts


def _run_publish_scheduler(*, force: bool) -> PublishSchedulerRunResponse:
    settings = runtime.repository.get_publish_scheduler_settings()
    now = datetime.now(timezone.utc)
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("publish")
    trigger = "run" if force else "tick"
    _log_pipeline_event(
        "scheduler_tick",
        phase="publish",
        run_id=run_id,
        trigger=trigger,
        status=settings.last_status or "idle",
        force=force,
        enabled=settings.enabled,
        next_run_at=settings.next_run_at.isoformat() if settings.next_run_at else None,
    )

    if not force and not settings.enabled:
        _log_pipeline_event(
            "scheduler_skipped",
            phase="publish",
            run_id=run_id,
            trigger=trigger,
            status="skipped",
            error_reason="disabled",
        )
        return PublishSchedulerRunResponse(ran=False, reason="disabled", next_run_at=settings.next_run_at)

    if not force and settings.next_run_at and settings.next_run_at > now:
        _log_pipeline_event(
            "scheduler_skipped",
            phase="publish",
            run_id=run_id,
            trigger=trigger,
            status="skipped",
            error_reason="not_due",
            now=now.isoformat(),
            next_run_at=settings.next_run_at.isoformat(),
        )
        return PublishSchedulerRunResponse(ran=False, reason="not_due", next_run_at=settings.next_run_at)

    with runtime.repository.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (PUBLISH_SCHEDULER_LOCK_KEY,))
            row = cursor.fetchone()
            locked = bool(row and row[0])

        if not locked:
            _log_pipeline_event(
                "scheduler_skipped",
                phase="publish",
                run_id=run_id,
                trigger=trigger,
                status="skipped",
                error_reason="locked",
            )
            return PublishSchedulerRunResponse(ran=False, reason="locked", next_run_at=settings.next_run_at)

        try:
            runtime.repository.set_publish_scheduler_status(status="running", error=None)
            batch_size = max(1, settings.batch_size)
            _log_pipeline_event(
                "scheduler_run_started",
                phase="publish",
                run_id=run_id,
                trigger=trigger,
                status="running",
                counts={"batch_size": batch_size},
            )
            published = _run_publish_for_drafts(limit=batch_size, since=None)
            latest_settings = runtime.repository.get_publish_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            runtime.repository.mark_publish_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="ok",
                error=None,
                published_count=published,
            )
            finished_at = datetime.now(timezone.utc)
            runtime.repository.record_pipeline_run(
                run_id=run_id,
                phase="publish",
                trigger="scheduler",
                status="ok",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                published_count=published,
            )
            _log_pipeline_event(
                "scheduler_run_finished",
                phase="publish",
                run_id=run_id,
                trigger=trigger,
                status="ok",
                duration_ms=_duration_ms(started_at, finished_at),
                counts={"published": published},
                next_run_at=next_run_at.isoformat() if next_run_at else None,
            )
            return PublishSchedulerRunResponse(
                ran=True,
                reason="ok",
                published=published,
                next_run_at=next_run_at,
            )
        except Exception as exc:
            latest_settings = runtime.repository.get_publish_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            runtime.repository.mark_publish_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="error",
                error=str(exc),
            )
            finished_at = datetime.now(timezone.utc)
            runtime.repository.record_pipeline_run(
                run_id=run_id,
                phase="publish",
                trigger="scheduler",
                status="error",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                error=str(exc),
            )
            _log_pipeline_event(
                "scheduler_run_failed",
                phase="publish",
                run_id=run_id,
                trigger=trigger,
                status="error",
                error_reason=str(exc),
                duration_ms=_duration_ms(started_at, finished_at),
                next_run_at=next_run_at.isoformat() if next_run_at else None,
            )
            logger.exception("Publish scheduler failed: %s", exc)
            raise
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (PUBLISH_SCHEDULER_LOCK_KEY,))
            _log_pipeline_event(
                "scheduler_lock_released",
                phase="publish",
                run_id=run_id,
                trigger=trigger,
                status="ok",
            )

