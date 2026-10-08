from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from .models import SchedulerRunResponse
from . import runtime
from .runtime import (
    SCHEDULER_LOCK_KEY,
    logger,
)
from .pipeline_logging import (
    _log_pipeline_event,
    _run_id,
)
from .service_ingestion import _run_source_ingestion


def _run_scheduler(*, force: bool, allow_inline_enrichment: bool = True) -> SchedulerRunResponse:
    settings = runtime.repository.get_scheduler_settings()
    now = datetime.now(timezone.utc)
    run_id = _run_id("scheduler")
    trigger = "run" if force else "tick"
    _log_pipeline_event(
        "scheduler_tick",
        phase="scheduler",
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
            phase="scheduler",
            run_id=run_id,
            trigger=trigger,
            status="skipped",
            error_reason="disabled",
        )
        return SchedulerRunResponse(ran=False, reason="disabled", next_run_at=settings.next_run_at)

    if not force and settings.next_run_at and settings.next_run_at > now:
        _log_pipeline_event(
            "scheduler_skipped",
            phase="scheduler",
            run_id=run_id,
            trigger=trigger,
            status="skipped",
            error_reason="not_due",
            now=now.isoformat(),
            next_run_at=settings.next_run_at.isoformat(),
        )
        return SchedulerRunResponse(ran=False, reason="not_due", next_run_at=settings.next_run_at)

    with runtime.repository.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (SCHEDULER_LOCK_KEY,))
            row = cursor.fetchone()
            locked = bool(row and row[0])

        if not locked:
            _log_pipeline_event(
                "scheduler_skipped",
                phase="scheduler",
                run_id=run_id,
                trigger=trigger,
                status="skipped",
                error_reason="locked",
            )
            return SchedulerRunResponse(ran=False, reason="locked", next_run_at=settings.next_run_at)

        try:
            runtime.repository.set_scheduler_status(status="running", error=None)
            scheduler_batch_size = max(1, settings.batch_size)
            _log_pipeline_event(
                "scheduler_run_started",
                phase="scheduler",
                run_id=run_id,
                trigger=trigger,
                status="running",
                counts={"batch_size": scheduler_batch_size},
                per_source=True,
                run_enrichment=settings.run_enrichment,
            )
            ingest_response = _run_source_ingestion(
                limit=scheduler_batch_size,
                per_source=True,
                run_enrichment=settings.run_enrichment and allow_inline_enrichment,
                trigger="scheduler",
            )
            latest_settings = runtime.repository.get_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            runtime.repository.mark_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="ok",
                error=None,
                found_count=ingest_response.ingested,
                saved_count=ingest_response.raw_items,
                published_count=ingest_response.published,
            )
            _log_pipeline_event(
                "scheduler_run_finished",
                phase="scheduler",
                run_id=run_id,
                trigger=trigger,
                status="ok",
                counts={
                    "ingested": ingest_response.ingested,
                    "published": ingest_response.published,
                    "raw_items": ingest_response.raw_items,
                },
                next_run_at=next_run_at.isoformat() if next_run_at else None,
            )
            return SchedulerRunResponse(
                ran=True,
                reason="ok",
                ingested=ingest_response.ingested,
                published=ingest_response.published,
                raw_items=ingest_response.raw_items,
                next_run_at=next_run_at,
            )
        except Exception as exc:
            latest_settings = runtime.repository.get_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            runtime.repository.mark_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="error",
                error=str(exc),
            )
            _log_pipeline_event(
                "scheduler_run_failed",
                phase="scheduler",
                run_id=run_id,
                trigger=trigger,
                status="error",
                error_reason=str(exc),
                next_run_at=next_run_at.isoformat() if next_run_at else None,
            )
            logger.exception("Scheduler run failed: %s", exc)
            raise
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (SCHEDULER_LOCK_KEY,))
            _log_pipeline_event(
                "scheduler_lock_released",
                phase="scheduler",
                run_id=run_id,
                trigger=trigger,
                status="ok",
            )

