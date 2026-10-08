from __future__ import annotations

from .models import (
    EnrichmentSchedulerRunResponse,
    EnrichmentSchedulerSettings,
    EnrichmentSchedulerSettingsUpdateRequest,
    EditorialSchedulerRunResponse,
    EditorialSchedulerSettings,
    EditorialSchedulerSettingsUpdateRequest,
    GuideSchedulerRunResponse,
    PublishSchedulerRunResponse,
    PublishSchedulerSettings,
    PublishSchedulerSettingsUpdateRequest,
    PipelineSchedulerRunResponse,
    SchedulerRunResponse,
    SchedulerSettings,
    SchedulerSettingsUpdateRequest,
)
from . import runtime
from .pipeline import _run_pipeline_scheduler
from .scheduler_editorial import _run_editorial_scheduler
from .scheduler_enrichment import _run_enrichment_scheduler
from .scheduler_guides import _run_guide_scheduler
from .scheduler_ingestion import _run_scheduler
from .scheduler_publication import _run_publish_scheduler


def get_scheduler_settings() -> SchedulerSettings:
    return runtime.repository.get_scheduler_settings()


def update_scheduler_settings(payload: SchedulerSettingsUpdateRequest) -> SchedulerSettings:
    return runtime.repository.update_scheduler_settings(
        enabled=payload.enabled,
        interval_minutes=payload.interval_minutes,
        batch_size=payload.batch_size,
        run_enrichment=payload.run_enrichment,
    )


def run_scheduler_tick() -> SchedulerRunResponse:
    return _run_scheduler(force=False)


def run_scheduler_now() -> SchedulerRunResponse:
    return _run_scheduler(force=True)


def get_enrichment_scheduler_settings() -> EnrichmentSchedulerSettings:
    return runtime.repository.get_enrichment_scheduler_settings()


def update_enrichment_scheduler_settings(
    payload: EnrichmentSchedulerSettingsUpdateRequest,
) -> EnrichmentSchedulerSettings:
    return runtime.repository.update_enrichment_scheduler_settings(
        enabled=payload.enabled,
        interval_minutes=payload.interval_minutes,
        batch_size=payload.batch_size,
    )


def run_enrichment_scheduler_tick() -> EnrichmentSchedulerRunResponse:
    return _run_enrichment_scheduler(force=False)


def run_enrichment_scheduler_now() -> EnrichmentSchedulerRunResponse:
    return _run_enrichment_scheduler(force=True)


def get_editorial_scheduler_settings() -> EditorialSchedulerSettings:
    return runtime.repository.get_editorial_scheduler_settings()


def update_editorial_scheduler_settings(
    payload: EditorialSchedulerSettingsUpdateRequest,
) -> EditorialSchedulerSettings:
    return runtime.repository.update_editorial_scheduler_settings(
        enabled=payload.enabled,
        interval_minutes=payload.interval_minutes,
        batch_size=payload.batch_size,
    )


def run_editorial_scheduler_tick() -> EditorialSchedulerRunResponse:
    return _run_editorial_scheduler(force=False)


def run_editorial_scheduler_now() -> EditorialSchedulerRunResponse:
    return _run_editorial_scheduler(force=True)


def get_publish_scheduler_settings() -> PublishSchedulerSettings:
    return runtime.repository.get_publish_scheduler_settings()


def update_publish_scheduler_settings(
    payload: PublishSchedulerSettingsUpdateRequest,
) -> PublishSchedulerSettings:
    return runtime.repository.update_publish_scheduler_settings(
        enabled=payload.enabled,
        interval_minutes=payload.interval_minutes,
        batch_size=payload.batch_size,
    )


def run_publish_scheduler_tick() -> PublishSchedulerRunResponse:
    return _run_publish_scheduler(force=False)


def run_publish_scheduler_now() -> PublishSchedulerRunResponse:
    return _run_publish_scheduler(force=True)


def run_pipeline_tick() -> PipelineSchedulerRunResponse:
    return _run_pipeline_scheduler(force=False)


def run_pipeline_now() -> PipelineSchedulerRunResponse:
    return _run_pipeline_scheduler(force=True)


def run_guide_scheduler_now() -> GuideSchedulerRunResponse:
    return _run_guide_scheduler()

