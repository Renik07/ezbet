from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from typing import Callable
from .models import (
    EnrichmentSchedulerRunResponse,
    EditorialSchedulerRunResponse,
    PublishSchedulerRunResponse,
    PipelineSchedulerRunResponse,
    SchedulerRunResponse,
)
from . import runtime
from .runtime import logger
from .pipeline_logging import (
    _duration_ms,
    _log_pipeline_event,
    _run_id,
)
from .scheduler_editorial import _run_editorial_scheduler
from .scheduler_enrichment import _run_enrichment_scheduler
from .scheduler_ingestion import _run_scheduler
from .scheduler_publication import _run_publish_scheduler


def _run_pipeline_scheduler(*, force: bool, should_continue: Callable[[], bool] | None = None) -> PipelineSchedulerRunResponse:
    with runtime.repository.connect() as connection:
        locked = connection.execute("SELECT pg_try_advisory_xact_lock(%s)", (4815162350,)).fetchone()[0]
        if not locked:
            now = datetime.now(timezone.utc)
            return PipelineSchedulerRunResponse(
                mode="run" if force else "tick", started_at=now, finished_at=now,
                ingest=SchedulerRunResponse(ran=False, reason="locked"),
                enrichment=EnrichmentSchedulerRunResponse(ran=False, reason="locked"),
                editorial=EditorialSchedulerRunResponse(ran=False, reason="locked"),
                publish=PublishSchedulerRunResponse(ran=False, reason="locked"),
            )
        return _execute_pipeline(force=force, should_continue=should_continue)


def _execute_pipeline(*, force: bool, should_continue: Callable[[], bool] | None = None) -> PipelineSchedulerRunResponse:
    started_at = datetime.now(timezone.utc)
    mode = "run" if force else "tick"
    run_id = _run_id("pipeline")
    _log_pipeline_event(
        "pipeline_run_started",
        phase="pipeline",
        run_id=run_id,
        trigger=mode,
        status="running",
    )
    if should_continue is not None and not should_continue():
        raise RuntimeError("Worker lost ownership before ingest stage.")
    ingest = _run_pipeline_stage(
        "ingest",
        run_id=run_id,
        trigger=mode,
        run=lambda: _run_scheduler(force=force, allow_inline_enrichment=False),
        fallback=lambda error: SchedulerRunResponse(ran=False, reason=f"error: {error}"),
    )
    if should_continue is not None and not should_continue():
        raise RuntimeError("Worker lost ownership before enrichment stage.")
    enrichment = _run_pipeline_stage(
        "enrichment",
        run_id=run_id,
        trigger=mode,
        run=lambda: _run_enrichment_scheduler(force=force),
        fallback=lambda error: EnrichmentSchedulerRunResponse(ran=False, reason=f"error: {error}"),
    )
    if should_continue is not None and not should_continue():
        raise RuntimeError("Worker lost ownership before editorial stage.")
    editorial = _run_pipeline_stage(
        "editorial",
        run_id=run_id,
        trigger=mode,
        run=lambda: _run_editorial_scheduler(force=force),
        fallback=lambda error: EditorialSchedulerRunResponse(ran=False, reason=f"error: {error}"),
    )
    if should_continue is not None and not should_continue():
        raise RuntimeError("Worker lost ownership before publish stage.")
    publish = _run_pipeline_stage(
        "publish",
        run_id=run_id,
        trigger=mode,
        run=lambda: _run_publish_scheduler(force=force),
        fallback=lambda error: PublishSchedulerRunResponse(ran=False, reason=f"error: {error}"),
    )
    finished_at = datetime.now(timezone.utc)
    pipeline_status = (
        "partial_error"
        if any(
            response.reason.startswith("error:")
            for response in (ingest, enrichment, editorial, publish)
        )
        else "ok"
    )
    _log_pipeline_event(
        "pipeline_run_finished",
        phase="pipeline",
        run_id=run_id,
        trigger=mode,
        status=pipeline_status,
        duration_ms=_duration_ms(started_at, finished_at),
        ingest_reason=ingest.reason,
        enrichment_reason=enrichment.reason,
        editorial_reason=editorial.reason,
        publish_reason=publish.reason,
    )
    return PipelineSchedulerRunResponse(
        mode=mode,
        ingest=ingest,
        enrichment=enrichment,
        editorial=editorial,
        publish=publish,
        started_at=started_at,
        finished_at=finished_at,
    )


def _run_pipeline_stage(
    stage: str,
    *,
    run_id: str,
    trigger: str,
    run,
    fallback,
):
    try:
        return run()
    except Exception as exc:
        _log_pipeline_event(
            "pipeline_stage_failed",
            phase="pipeline",
            run_id=run_id,
            trigger=trigger,
            status="error",
            error_reason=str(exc),
            failed_phase=stage,
        )
        logger.exception("Pipeline stage failed: %s", stage)
        return fallback(str(exc))

