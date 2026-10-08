from __future__ import annotations

from typing import Optional
from fastapi import Query
from .models import (
    EnrichmentRunResponse,
    EnrichmentSchedulerRunResponse,
    EnrichmentSchedulerSettings,
    EnrichmentSchedulerSettingsUpdateRequest,
    EditorialSchedulerRunResponse,
    EditorialSchedulerSettings,
    EditorialSchedulerSettingsUpdateRequest,
    GuideSchedulerRunResponse,
    IngestResponse,
    PublishRunResponse,
    PublishSchedulerRunResponse,
    PublishSchedulerSettings,
    PublishSchedulerSettingsUpdateRequest,
    PipelineSchedulerRunResponse,
    SchedulerRunResponse,
    SchedulerSettings,
    SchedulerSettingsUpdateRequest,
)
from fastapi import APIRouter
from . import service_enrichment
from . import service_ingestion
from . import service_jobs
from . import service_publication
from . import service_scheduler_settings

router = APIRouter()


@router.get("/api/v1/scheduler", response_model=SchedulerSettings)
def get_scheduler_settings() -> SchedulerSettings:
    return service_scheduler_settings.get_scheduler_settings()


@router.post("/api/v1/scheduler", response_model=SchedulerSettings)
def update_scheduler_settings(payload: SchedulerSettingsUpdateRequest) -> SchedulerSettings:
    return service_scheduler_settings.update_scheduler_settings(payload=payload)


@router.post("/api/v1/scheduler/tick", response_model=SchedulerRunResponse)
def run_scheduler_tick() -> SchedulerRunResponse:
    return service_scheduler_settings.run_scheduler_tick()


@router.post("/api/v1/scheduler/run", response_model=SchedulerRunResponse)
def run_scheduler_now() -> SchedulerRunResponse:
    return service_scheduler_settings.run_scheduler_now()


@router.post("/api/v1/enrichment/run", response_model=EnrichmentRunResponse)
def run_enrichment(limit: int = Query(default=10, ge=1, le=50)) -> EnrichmentRunResponse:
    return service_enrichment.run_enrichment(limit=limit)


@router.get("/api/v1/enrichment-scheduler", response_model=EnrichmentSchedulerSettings)
def get_enrichment_scheduler_settings() -> EnrichmentSchedulerSettings:
    return service_scheduler_settings.get_enrichment_scheduler_settings()


@router.post("/api/v1/enrichment-scheduler", response_model=EnrichmentSchedulerSettings)
def update_enrichment_scheduler_settings(
    payload: EnrichmentSchedulerSettingsUpdateRequest,
) -> EnrichmentSchedulerSettings:
    return service_scheduler_settings.update_enrichment_scheduler_settings(payload=payload)


@router.post("/api/v1/enrichment-scheduler/tick", response_model=EnrichmentSchedulerRunResponse)
def run_enrichment_scheduler_tick() -> EnrichmentSchedulerRunResponse:
    return service_scheduler_settings.run_enrichment_scheduler_tick()


@router.post("/api/v1/enrichment-scheduler/run", response_model=EnrichmentSchedulerRunResponse)
def run_enrichment_scheduler_now() -> EnrichmentSchedulerRunResponse:
    return service_scheduler_settings.run_enrichment_scheduler_now()


@router.get("/api/v1/editorial-scheduler", response_model=EditorialSchedulerSettings)
def get_editorial_scheduler_settings() -> EditorialSchedulerSettings:
    return service_scheduler_settings.get_editorial_scheduler_settings()


@router.post("/api/v1/editorial-scheduler", response_model=EditorialSchedulerSettings)
def update_editorial_scheduler_settings(
    payload: EditorialSchedulerSettingsUpdateRequest,
) -> EditorialSchedulerSettings:
    return service_scheduler_settings.update_editorial_scheduler_settings(payload=payload)


@router.post("/api/v1/editorial-scheduler/tick", response_model=EditorialSchedulerRunResponse)
def run_editorial_scheduler_tick() -> EditorialSchedulerRunResponse:
    return service_scheduler_settings.run_editorial_scheduler_tick()


@router.post("/api/v1/editorial-scheduler/run", response_model=EditorialSchedulerRunResponse)
def run_editorial_scheduler_now() -> EditorialSchedulerRunResponse:
    return service_scheduler_settings.run_editorial_scheduler_now()


@router.get("/api/v1/publish-scheduler", response_model=PublishSchedulerSettings)
def get_publish_scheduler_settings() -> PublishSchedulerSettings:
    return service_scheduler_settings.get_publish_scheduler_settings()


@router.post("/api/v1/publish-scheduler", response_model=PublishSchedulerSettings)
def update_publish_scheduler_settings(
    payload: PublishSchedulerSettingsUpdateRequest,
) -> PublishSchedulerSettings:
    return service_scheduler_settings.update_publish_scheduler_settings(payload=payload)


@router.post("/api/v1/publish-scheduler/tick", response_model=PublishSchedulerRunResponse)
def run_publish_scheduler_tick() -> PublishSchedulerRunResponse:
    return service_scheduler_settings.run_publish_scheduler_tick()


@router.post("/api/v1/publish-scheduler/run", response_model=PublishSchedulerRunResponse)
def run_publish_scheduler_now() -> PublishSchedulerRunResponse:
    return service_scheduler_settings.run_publish_scheduler_now()


@router.post("/api/v1/pipeline/tick", response_model=PipelineSchedulerRunResponse)
def run_pipeline_tick() -> PipelineSchedulerRunResponse:
    return service_scheduler_settings.run_pipeline_tick()


@router.post("/api/v1/pipeline/run", response_model=PipelineSchedulerRunResponse)
def run_pipeline_now() -> PipelineSchedulerRunResponse:
    return service_scheduler_settings.run_pipeline_now()


@router.post("/api/v1/guides/scheduler/run", response_model=GuideSchedulerRunResponse)
def run_guide_scheduler_now() -> GuideSchedulerRunResponse:
    return service_scheduler_settings.run_guide_scheduler_now()


@router.post("/api/v1/pipeline/start")
def start_pipeline_now() -> dict[str, object]:
    return service_jobs.start_pipeline_now()


@router.post("/api/v1/pipeline/queue")
def queue_pipeline(force: bool = Query(default=False)) -> dict[str, object]:
    return service_jobs.queue_pipeline(force=force)


@router.get("/api/v1/worker/jobs")
def list_worker_jobs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
    return service_jobs.list_worker_jobs(limit=limit)


@router.post("/api/v1/publish/run", response_model=PublishRunResponse)
def run_publish(limit: int = Query(default=5, ge=1, le=20)) -> PublishRunResponse:
    return service_publication.run_publish(limit=limit)


@router.post("/api/v1/ingest/demo", response_model=IngestResponse)
def ingest_demo() -> IngestResponse:
    return service_ingestion.ingest_demo()


@router.post("/api/v1/ingest/rss", response_model=IngestResponse)
def ingest_rss(limit: Optional[int] = Query(default=None, ge=1, le=50)) -> IngestResponse:
    return service_ingestion.ingest_rss(limit=limit)


@router.post("/api/v1/ingest/sources", response_model=IngestResponse)
def ingest_sources(
    limit: Optional[int] = Query(default=None, ge=1, le=50),
    per_source: bool = Query(default=False, alias="perSource"),
) -> IngestResponse:
    return service_ingestion.ingest_sources(limit=limit, per_source=per_source)


