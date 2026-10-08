from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from .editorial import run_editorial_cycle
from .models import EditorialSchedulerRunResponse
from .planner import run_content_planner
from . import runtime
from .runtime import (
    EDITORIAL_SCHEDULER_LOCK_KEY,
    logger,
)
from .pipeline_logging import (
    _duration_ms,
    _log_pipeline_event,
    _run_id,
)


def _run_editorial_scheduler(*, force: bool) -> EditorialSchedulerRunResponse:
    settings = runtime.repository.get_editorial_scheduler_settings()
    now = datetime.now(timezone.utc)
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("editorial")
    trigger = "run" if force else "tick"
    _log_pipeline_event(
        "scheduler_tick",
        phase="editorial",
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
            phase="editorial",
            run_id=run_id,
            trigger=trigger,
            status="skipped",
            error_reason="disabled",
        )
        return EditorialSchedulerRunResponse(ran=False, reason="disabled", next_run_at=settings.next_run_at)

    if not force and settings.next_run_at and settings.next_run_at > now:
        _log_pipeline_event(
            "scheduler_skipped",
            phase="editorial",
            run_id=run_id,
            trigger=trigger,
            status="skipped",
            error_reason="not_due",
            now=now.isoformat(),
            next_run_at=settings.next_run_at.isoformat(),
        )
        return EditorialSchedulerRunResponse(ran=False, reason="not_due", next_run_at=settings.next_run_at)

    with runtime.repository.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (EDITORIAL_SCHEDULER_LOCK_KEY,))
            row = cursor.fetchone()
            locked = bool(row and row[0])

        if not locked:
            _log_pipeline_event(
                "scheduler_skipped",
                phase="editorial",
                run_id=run_id,
                trigger=trigger,
                status="skipped",
                error_reason="locked",
            )
            return EditorialSchedulerRunResponse(ran=False, reason="locked", next_run_at=settings.next_run_at)

        try:
            runtime.repository.set_editorial_scheduler_status(status="running", error=None)
            batch_size = max(1, settings.batch_size)
            planned_items = run_content_planner(
                runtime.repository,
                limit=batch_size,
                since=None,
            )
            _log_pipeline_event(
                "scheduler_run_started",
                phase="editorial",
                run_id=run_id,
                trigger=trigger,
                status="running",
                counts={"batch_size": batch_size, "planned": len(planned_items)},
            )
            drafts, reviews = run_editorial_cycle(
                runtime.repository,
                limit=batch_size,
                since=None,
            )
            published_count = len([draft for draft in drafts if draft.status == "published"])
            latest_settings = runtime.repository.get_editorial_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            runtime.repository.mark_editorial_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="ok",
                error=None,
                planned_count=len(planned_items),
                generated_count=len(drafts),
                reviewed_count=len(reviews),
            )
            finished_at = datetime.now(timezone.utc)
            runtime.repository.record_pipeline_run(
                run_id=run_id,
                phase="editorial",
                trigger="scheduler",
                status="ok",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                published_count=published_count,
                planned_count=len(planned_items),
                generated_count=len(drafts),
                reviewed_count=len(reviews),
            )
            _log_pipeline_event(
                "scheduler_run_finished",
                phase="editorial",
                run_id=run_id,
                trigger=trigger,
                status="ok",
                duration_ms=_duration_ms(started_at, finished_at),
                counts={
                    "planned": len(planned_items),
                    "generated": len(drafts),
                    "reviewed": len(reviews),
                    "published_ready": published_count,
                },
                next_run_at=next_run_at.isoformat() if next_run_at else None,
            )
            return EditorialSchedulerRunResponse(
                ran=True,
                reason="ok",
                planned=len(planned_items),
                generated=len(drafts),
                reviewed=len(reviews),
                next_run_at=next_run_at,
            )
        except Exception as exc:
            latest_settings = runtime.repository.get_editorial_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            runtime.repository.mark_editorial_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="error",
                error=str(exc),
            )
            finished_at = datetime.now(timezone.utc)
            runtime.repository.record_pipeline_run(
                run_id=run_id,
                phase="editorial",
                trigger="scheduler",
                status="error",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                error=str(exc),
            )
            _log_pipeline_event(
                "scheduler_run_failed",
                phase="editorial",
                run_id=run_id,
                trigger=trigger,
                status="error",
                error_reason=str(exc),
                duration_ms=_duration_ms(started_at, finished_at),
                next_run_at=next_run_at.isoformat() if next_run_at else None,
            )
            logger.exception("Editorial scheduler failed: %s", exc)
            raise
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (EDITORIAL_SCHEDULER_LOCK_KEY,))
            _log_pipeline_event(
                "scheduler_lock_released",
                phase="editorial",
                run_id=run_id,
                trigger=trigger,
                status="ok",
            )

