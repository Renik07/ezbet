from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from .models import EnrichmentSchedulerRunResponse
from . import runtime
from .runtime import (
    ENRICHMENT_SCHEDULER_LOCK_KEY,
    logger,
)
from .pipeline_logging import (
    _current_ingest_started_at,
    _duration_ms,
    _log_pipeline_event,
    _run_id,
)
from .service_enrichment import (
    _run_enrichment_for_raw_items,
    _select_pre_enrichment_raw_items,
)


def _run_enrichment_scheduler(*, force: bool) -> EnrichmentSchedulerRunResponse:
    settings = runtime.repository.get_enrichment_scheduler_settings()
    now = datetime.now(timezone.utc)
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("enrichment")
    trigger = "run" if force else "tick"
    _log_pipeline_event(
        "scheduler_tick",
        phase="enrichment",
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
            phase="enrichment",
            run_id=run_id,
            trigger=trigger,
            status="skipped",
            error_reason="disabled",
        )
        return EnrichmentSchedulerRunResponse(ran=False, reason="disabled", next_run_at=settings.next_run_at)

    if not force and settings.next_run_at and settings.next_run_at > now:
        _log_pipeline_event(
            "scheduler_skipped",
            phase="enrichment",
            run_id=run_id,
            trigger=trigger,
            status="skipped",
            error_reason="not_due",
            now=now.isoformat(),
            next_run_at=settings.next_run_at.isoformat(),
        )
        return EnrichmentSchedulerRunResponse(ran=False, reason="not_due", next_run_at=settings.next_run_at)

    with runtime.repository.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (ENRICHMENT_SCHEDULER_LOCK_KEY,))
            row = cursor.fetchone()
            locked = bool(row and row[0])

        if not locked:
            _log_pipeline_event(
                "scheduler_skipped",
                phase="enrichment",
                run_id=run_id,
                trigger=trigger,
                status="skipped",
                error_reason="locked",
            )
            return EnrichmentSchedulerRunResponse(ran=False, reason="locked", next_run_at=settings.next_run_at)

        try:
            runtime.repository.set_enrichment_scheduler_status(status="running", error=None)
            batch_size = max(1, settings.batch_size)
            current_ingest_started_at = _current_ingest_started_at()
            raw_items = _select_pre_enrichment_raw_items(limit=batch_size, since=None)
            _log_pipeline_event(
                "scheduler_run_started",
                phase="enrichment",
                run_id=run_id,
                trigger=trigger,
                status="running",
                counts={
                    "batch_size": batch_size,
                    "candidates_found": len(raw_items),
                    "current_ingest_started_at": current_ingest_started_at.isoformat()
                    if current_ingest_started_at
                    else None,
                },
            )
            processed, enriched = _run_enrichment_for_raw_items(raw_items)
            latest_settings = runtime.repository.get_enrichment_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            runtime.repository.mark_enrichment_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="ok",
                error=None,
                processed_count=processed,
                enriched_count=enriched,
            )
            finished_at = datetime.now(timezone.utc)
            runtime.repository.record_pipeline_run(
                run_id=run_id,
                phase="enrichment",
                trigger="scheduler",
                status="ok",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                processed_count=processed,
                enriched_count=enriched,
            )
            _log_pipeline_event(
                "scheduler_run_finished",
                phase="enrichment",
                run_id=run_id,
                trigger=trigger,
                status="ok",
                duration_ms=_duration_ms(started_at, finished_at),
                counts={"processed": processed, "enriched": enriched},
                next_run_at=next_run_at.isoformat() if next_run_at else None,
            )
            return EnrichmentSchedulerRunResponse(
                ran=True,
                reason="ok",
                processed=processed,
                enriched=enriched,
                next_run_at=next_run_at,
            )
        except Exception as exc:
            latest_settings = runtime.repository.get_enrichment_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            runtime.repository.mark_enrichment_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="error",
                error=str(exc),
            )
            finished_at = datetime.now(timezone.utc)
            runtime.repository.record_pipeline_run(
                run_id=run_id,
                phase="enrichment",
                trigger="scheduler",
                status="error",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                error=str(exc),
            )
            _log_pipeline_event(
                "scheduler_run_failed",
                phase="enrichment",
                run_id=run_id,
                trigger=trigger,
                status="error",
                error_reason=str(exc),
                duration_ms=_duration_ms(started_at, finished_at),
                next_run_at=next_run_at.isoformat() if next_run_at else None,
            )
            logger.exception("Enrichment scheduler failed: %s", exc)
            raise
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (ENRICHMENT_SCHEDULER_LOCK_KEY,))
            _log_pipeline_event(
                "scheduler_lock_released",
                phase="enrichment",
                run_id=run_id,
                trigger=trigger,
                status="ok",
            )

