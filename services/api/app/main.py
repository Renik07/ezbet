from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
import psycopg

from .ai_client import OpenAIEditorialClient
from .config import get_openai_settings
from .editorial import default_prompt_configs, run_editorial_cycle
from .ingestion import (
    enrich_raw_item_content,
    ingest_sources as collect_source_items,
    ingest_sources_with_results,
    probe_source_auto,
    probe_source,
    raw_items_to_news,
)
from .models import (
    ArticleResponse,
    ContentPlanListResponse,
    ContentPlanRunResponse,
    DraftArticleListResponse,
    EnrichmentRunResponse,
    EnrichmentSchedulerRunResponse,
    EnrichmentSchedulerSettings,
    EnrichmentSchedulerSettingsUpdateRequest,
    EditorialSchedulerRunResponse,
    EditorialSchedulerSettings,
    EditorialSchedulerSettingsUpdateRequest,
    EditorialStatusResponse,
    EditorialRunResponse,
    EditorReviewListResponse,
    IngestResponse,
    NewsListResponse,
    PublishRunResponse,
    PublishSchedulerRunResponse,
    PublishSchedulerSettings,
    PublishSchedulerSettingsUpdateRequest,
    PromptConfigCreateRequest,
    PromptConfigListResponse,
    PromptStatusUpdateRequest,
    PipelineRunListResponse,
    RawItemListResponse,
    RawItemPreviewListResponse,
    RawItem,
    ResetResponse,
    SchedulerRunResponse,
    SchedulerSettings,
    SchedulerSettingsUpdateRequest,
    SourceCreateRequest,
    SourceListResponse,
    SourceProbeResponse,
    SourceUpdateRequest,
    SourceSyncStateListResponse,
    SourceItem,
)
from .planner import run_content_planner
from .repository import NewsRepository


@asynccontextmanager
async def lifespan(_: FastAPI):
    repository.ensure_schema()
    repository.recover_scheduler_if_stale()
    repository.recover_enrichment_scheduler_if_stale()
    repository.recover_editorial_scheduler_if_stale()
    repository.recover_publish_scheduler_if_stale()
    repository.ensure_prompt_defaults(default_prompt_configs())
    repository.maybe_activate_recommended_prompt("writer", "prompt:writer:v3")
    repository.maybe_activate_recommended_prompt("editor", "prompt:editor:v3")
    repository.maybe_activate_recommended_prompt("ai_search", "prompt:ai-search:v1")
    repository.sync_news_ai_review_flags()
    yield


app = FastAPI(
    title="ezbet API",
    version="0.1.0",
    description="MVP API for news collection, search, and publication.",
    lifespan=lifespan,
)

repository = NewsRepository()
SCHEDULER_LOCK_KEY = 4815162342
ENRICHMENT_SCHEDULER_LOCK_KEY = 4815162343
EDITORIAL_SCHEDULER_LOCK_KEY = 4815162344
PUBLISH_SCHEDULER_LOCK_KEY = 4815162345
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)


def _run_id(phase: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{phase}:{timestamp}"


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _raise_source_http_error(exc: Exception) -> None:
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, psycopg.Error):
        detail = getattr(exc.diag, "message_primary", None) or str(exc)
        raise HTTPException(status_code=400, detail=detail) from exc
    raise exc


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/editorial/status", response_model=EditorialStatusResponse)
def editorial_status() -> EditorialStatusResponse:
    settings = get_openai_settings()
    return EditorialStatusResponse(
        openai_enabled=settings.enabled,
        openai_model=settings.editorial_model,
        openai_search_model=settings.search_model,
        fallback_mode=not settings.enabled,
        provider_label=settings.provider_label,
        api_style=settings.api_style,
        web_search_enabled=settings.web_search_enabled,
    )


@app.get("/api/v1/news", response_model=NewsListResponse)
def list_news(
    query: Optional[str] = Query(default=None),
    ai_only: bool = Query(default=False, alias="aiOnly"),
) -> NewsListResponse:
    return NewsListResponse(items=repository.list(query, ai_only=ai_only))


@app.get("/api/v1/articles/{slug}", response_model=ArticleResponse)
def get_article(slug: str) -> ArticleResponse:
    article = repository.get_article_by_slug(slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleResponse(item=article)


@app.get("/api/v1/sources", response_model=SourceListResponse)
def list_sources() -> SourceListResponse:
    return SourceListResponse(items=repository.list_source_configs())


@app.post("/api/v1/sources", response_model=SourceListResponse)
def create_source(payload: SourceCreateRequest) -> SourceListResponse:
    try:
        repository.create_source_config(
            SourceItem(
                key=payload.key,
                title=payload.title,
                url=payload.url,
                category=payload.category,
                source_type=payload.source_type,
                status=payload.status,
                notes=payload.notes,
            )
        )
    except Exception as exc:
        _raise_source_http_error(exc)
    return SourceListResponse(items=repository.list_source_configs())


@app.post("/api/v1/sources/{source_key}", response_model=SourceListResponse)
def update_source(source_key: str, payload: SourceUpdateRequest) -> SourceListResponse:
    try:
        repository.update_source_config(
            SourceItem(
                key=source_key,
                title=payload.title,
                url=payload.url,
                category=payload.category,
                source_type=payload.source_type,
                status=payload.status,
                notes=payload.notes,
            )
        )
    except Exception as exc:
        _raise_source_http_error(exc)
    return SourceListResponse(items=repository.list_source_configs())


@app.post("/api/v1/sources/{source_key}/delete", response_model=SourceListResponse)
def delete_source(source_key: str) -> SourceListResponse:
    try:
        repository.delete_source_config(source_key)
    except Exception as exc:
        _raise_source_http_error(exc)
    return SourceListResponse(items=repository.list_source_configs())


@app.post("/api/v1/source-probe", response_model=SourceProbeResponse)
def probe_source_draft(payload: SourceCreateRequest) -> SourceProbeResponse:
    source = SourceItem(
        key=payload.key or "source-draft",
        title=payload.title,
        url=payload.url,
        category=payload.category,
        source_type=payload.source_type,
        status="draft",
        notes=payload.notes,
    )
    return _probe_source_item(source, persist=False, auto_detect=payload.source_type == "auto")


@app.post("/api/v1/sources/{source_key}/probe", response_model=SourceProbeResponse)
def probe_source_config(source_key: str) -> SourceProbeResponse:
    try:
        source = repository.get_source_config(source_key)
        return _probe_source_item(source, persist=True)
    except Exception as exc:
        _raise_source_http_error(exc)


def _probe_source_item(source: SourceItem, *, persist: bool, auto_detect: bool = False) -> SourceProbeResponse:
    result = probe_source_auto(source) if auto_detect else probe_source(source)
    resolved_source = source.model_copy(update={"source_type": result.resolved_source_type or source.source_type})
    if (
        result.ok
        and result.readiness not in {"ready", "ready_ai"}
    ):
        ai_client = OpenAIEditorialClient()
        if ai_client.enabled:
            probe_candidates = [
                item for item in collect_source_items([resolved_source], limit=5) if item.url
            ][:5]
            for candidate in probe_candidates:
                ai_enrichment = ai_client.extract_article_enrichment_via_search(
                    url=candidate.url,
                    source_title=source.title,
                    raw_title=candidate.title or result.sample_title or source.title,
                    raw_summary=candidate.summary,
                )
                if ai_enrichment is None:
                    continue
                if ai_enrichment.full_text and len(ai_enrichment.full_text.strip()) >= 120:
                    result.readiness = "ready_ai"
                    result.full_text_ok = True
                    result.lead_ok = result.lead_ok or bool(ai_enrichment.lead)
                    result.tags_count = max(result.tags_count, len(ai_enrichment.tags))
                    result.sample_title = candidate.title
                    result.sample_url = candidate.url
                    result.message = (
                        f"Найдено {result.item_count} элементов. Deterministic extraction слабый, "
                        "но web_search fallback успешно собрал текст у одной из sample-новостей."
                    )
                    break
                if ai_enrichment.lead or ai_enrichment.tags:
                    result.readiness = "partial"
                    result.lead_ok = result.lead_ok or bool(ai_enrichment.lead)
                    result.tags_count = max(result.tags_count, len(ai_enrichment.tags))
                    result.sample_title = candidate.title
                    result.sample_url = candidate.url
                    result.message = (
                        f"Найдено {result.item_count} элементов. Deterministic extraction слабый, "
                        "но web_search fallback смог поднять только часть enrichment-данных."
                    )
    if persist:
        repository.record_source_probe(
            source,
            ok=result.ok,
            item_count=result.item_count,
            message=result.message,
            readiness=result.readiness,
            preferred_adapter=result.resolved_source_type,
            preferred_adapter_url=result.resolved_source_url,
            supports_rss=result.supports_rss,
            supports_news_sitemap=result.supports_news_sitemap,
            supports_sitemap=result.supports_sitemap,
            supports_scraping=result.supports_scraping,
            full_text_ok=result.full_text_ok,
            lead_ok=result.lead_ok,
            tags_count=result.tags_count,
            sample_title=result.sample_title,
            sample_url=result.sample_url,
        )
    return SourceProbeResponse(
        source_key=source.key,
        ok=result.ok,
        item_count=result.item_count,
        message=result.message,
        readiness=result.readiness,
        resolved_source_type=result.resolved_source_type,
        resolved_source_url=result.resolved_source_url,
        supports_rss=result.supports_rss,
        supports_news_sitemap=result.supports_news_sitemap,
        supports_sitemap=result.supports_sitemap,
        supports_scraping=result.supports_scraping,
        full_text_ok=result.full_text_ok,
        lead_ok=result.lead_ok,
        tags_count=result.tags_count,
        sample_title=result.sample_title,
        sample_url=result.sample_url,
    )


@app.get("/api/v1/source-states", response_model=SourceSyncStateListResponse)
def list_source_states() -> SourceSyncStateListResponse:
    return SourceSyncStateListResponse(items=repository.list_source_sync_states())


@app.get("/api/v1/scheduler", response_model=SchedulerSettings)
def get_scheduler_settings() -> SchedulerSettings:
    return repository.get_scheduler_settings()


@app.post("/api/v1/scheduler", response_model=SchedulerSettings)
def update_scheduler_settings(payload: SchedulerSettingsUpdateRequest) -> SchedulerSettings:
    return repository.update_scheduler_settings(
        enabled=payload.enabled,
        interval_minutes=payload.interval_minutes,
        batch_size=payload.batch_size,
        run_enrichment=payload.run_enrichment,
    )


@app.post("/api/v1/scheduler/tick", response_model=SchedulerRunResponse)
def run_scheduler_tick() -> SchedulerRunResponse:
    return _run_scheduler(force=False)


@app.post("/api/v1/scheduler/run", response_model=SchedulerRunResponse)
def run_scheduler_now() -> SchedulerRunResponse:
    return _run_scheduler(force=True)


@app.post("/api/v1/enrichment/run", response_model=EnrichmentRunResponse)
def run_enrichment(limit: int = Query(default=10, ge=1, le=50)) -> EnrichmentRunResponse:
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("enrichment")
    raw_items = repository.list_pending_enrichment_raw_items(limit=limit)
    try:
        processed, enriched = _run_enrichment_for_raw_items(raw_items)
        finished_at = datetime.now(timezone.utc)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="enrichment",
            trigger="manual",
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
            processed_count=processed,
            enriched_count=enriched,
        )
        return EnrichmentRunResponse(processed=processed, enriched=enriched)
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="enrichment",
            trigger="manual",
            status="error",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
            error=str(exc),
        )
        raise


@app.get("/api/v1/enrichment-scheduler", response_model=EnrichmentSchedulerSettings)
def get_enrichment_scheduler_settings() -> EnrichmentSchedulerSettings:
    return repository.get_enrichment_scheduler_settings()


@app.post("/api/v1/enrichment-scheduler", response_model=EnrichmentSchedulerSettings)
def update_enrichment_scheduler_settings(
    payload: EnrichmentSchedulerSettingsUpdateRequest,
) -> EnrichmentSchedulerSettings:
    return repository.update_enrichment_scheduler_settings(
        enabled=payload.enabled,
        interval_minutes=payload.interval_minutes,
        batch_size=payload.batch_size,
    )


@app.post("/api/v1/enrichment-scheduler/tick", response_model=EnrichmentSchedulerRunResponse)
def run_enrichment_scheduler_tick() -> EnrichmentSchedulerRunResponse:
    return _run_enrichment_scheduler(force=False)


@app.post("/api/v1/enrichment-scheduler/run", response_model=EnrichmentSchedulerRunResponse)
def run_enrichment_scheduler_now() -> EnrichmentSchedulerRunResponse:
    return _run_enrichment_scheduler(force=True)


@app.get("/api/v1/editorial-scheduler", response_model=EditorialSchedulerSettings)
def get_editorial_scheduler_settings() -> EditorialSchedulerSettings:
    return repository.get_editorial_scheduler_settings()


@app.post("/api/v1/editorial-scheduler", response_model=EditorialSchedulerSettings)
def update_editorial_scheduler_settings(
    payload: EditorialSchedulerSettingsUpdateRequest,
) -> EditorialSchedulerSettings:
    return repository.update_editorial_scheduler_settings(
        enabled=payload.enabled,
        interval_minutes=payload.interval_minutes,
        batch_size=payload.batch_size,
    )


@app.post("/api/v1/editorial-scheduler/tick", response_model=EditorialSchedulerRunResponse)
def run_editorial_scheduler_tick() -> EditorialSchedulerRunResponse:
    return _run_editorial_scheduler(force=False)


@app.post("/api/v1/editorial-scheduler/run", response_model=EditorialSchedulerRunResponse)
def run_editorial_scheduler_now() -> EditorialSchedulerRunResponse:
    return _run_editorial_scheduler(force=True)


@app.get("/api/v1/publish-scheduler", response_model=PublishSchedulerSettings)
def get_publish_scheduler_settings() -> PublishSchedulerSettings:
    return repository.get_publish_scheduler_settings()


@app.post("/api/v1/publish-scheduler", response_model=PublishSchedulerSettings)
def update_publish_scheduler_settings(
    payload: PublishSchedulerSettingsUpdateRequest,
) -> PublishSchedulerSettings:
    return repository.update_publish_scheduler_settings(
        enabled=payload.enabled,
        interval_minutes=payload.interval_minutes,
        batch_size=payload.batch_size,
    )


@app.post("/api/v1/publish-scheduler/tick", response_model=PublishSchedulerRunResponse)
def run_publish_scheduler_tick() -> PublishSchedulerRunResponse:
    return _run_publish_scheduler(force=False)


@app.post("/api/v1/publish-scheduler/run", response_model=PublishSchedulerRunResponse)
def run_publish_scheduler_now() -> PublishSchedulerRunResponse:
    return _run_publish_scheduler(force=True)


@app.get("/api/v1/raw-items", response_model=RawItemListResponse)
def list_raw_items(limit: int = Query(default=50, ge=1, le=200)) -> RawItemListResponse:
    return RawItemListResponse(items=repository.list_raw_items(limit))


@app.get("/api/v1/raw-items/preview", response_model=RawItemPreviewListResponse)
def list_raw_item_previews(limit: int = Query(default=50, ge=1, le=200)) -> RawItemPreviewListResponse:
    return RawItemPreviewListResponse(items=repository.list_raw_item_previews(limit))


@app.get("/api/v1/pipeline-runs", response_model=PipelineRunListResponse)
def list_pipeline_runs(limit: int = Query(default=20, ge=1, le=100)) -> PipelineRunListResponse:
    return PipelineRunListResponse(items=repository.list_pipeline_runs(limit))


@app.get("/api/v1/content-plan", response_model=ContentPlanListResponse)
def list_content_plan(
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
) -> ContentPlanListResponse:
    return ContentPlanListResponse(items=repository.list_content_plan(limit=limit, status=status))


@app.post("/api/v1/content-plan/run", response_model=ContentPlanRunResponse)
def run_planner(limit: int = Query(default=6, ge=1, le=20)) -> ContentPlanRunResponse:
    items = run_content_planner(repository, limit=limit)
    return ContentPlanRunResponse(planned=len(items), items=items)


@app.get("/api/v1/prompts", response_model=PromptConfigListResponse)
def list_prompts(agent_key: Optional[str] = Query(default=None)) -> PromptConfigListResponse:
    return PromptConfigListResponse(items=repository.list_prompt_configs(agent_key))


@app.post("/api/v1/prompts", response_model=PromptConfigListResponse)
def create_prompt_version(payload: PromptConfigCreateRequest) -> PromptConfigListResponse:
    prompt = repository.create_prompt_version(
        agent_key=payload.agent_key,
        name=payload.name,
        system_prompt=payload.system_prompt,
        user_prompt_template=payload.user_prompt_template,
        model=payload.model,
        notes=payload.notes,
        activate=payload.activate,
    )
    return PromptConfigListResponse(items=[prompt])


@app.post("/api/v1/prompts/{prompt_id}/status", response_model=PromptConfigListResponse)
def update_prompt_status(prompt_id: str, payload: PromptStatusUpdateRequest) -> PromptConfigListResponse:
    prompt = repository.set_prompt_status(prompt_id, payload.status)
    return PromptConfigListResponse(items=[prompt])


@app.get("/api/v1/drafts", response_model=DraftArticleListResponse)
def list_drafts(
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    review_status: Optional[str] = Query(default=None, alias="reviewStatus"),
) -> DraftArticleListResponse:
    return DraftArticleListResponse(
        items=repository.list_drafts(limit=limit, status=status, review_status=review_status)
    )


@app.get("/api/v1/reviews", response_model=EditorReviewListResponse)
def list_reviews(limit: int = Query(default=20, ge=1, le=100)) -> EditorReviewListResponse:
    return EditorReviewListResponse(items=repository.list_reviews(limit))


@app.post("/api/v1/editorial/run", response_model=EditorialRunResponse)
def run_editorial(limit: int = Query(default=2, ge=1, le=10)) -> EditorialRunResponse:
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("editorial")
    try:
        drafts, reviews = run_editorial_cycle(repository, limit=limit)
        published_count = len([draft for draft in drafts if draft.status == "published"])
        finished_at = datetime.now(timezone.utc)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="editorial",
            trigger="manual",
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
            published_count=published_count,
            generated_count=len(drafts),
            reviewed_count=len(reviews),
        )
        return EditorialRunResponse(generated=len(drafts), reviewed=len(reviews), drafts=drafts)
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="editorial",
            trigger="manual",
            status="error",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
            error=str(exc),
        )
        raise


@app.post("/api/v1/publish/run", response_model=PublishRunResponse)
def run_publish(limit: int = Query(default=5, ge=1, le=20)) -> PublishRunResponse:
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("publish")
    try:
        published = _run_publish_for_drafts(limit=limit)
        finished_at = datetime.now(timezone.utc)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="publish",
            trigger="manual",
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
            published_count=published,
        )
        return PublishRunResponse(published=published)
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="publish",
            trigger="manual",
            status="error",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
            error=str(exc),
        )
        raise


@app.post("/api/v1/ingest/demo", response_model=IngestResponse)
def ingest_demo() -> IngestResponse:
    items = repository.ingest_demo_batch()
    return IngestResponse(
        ingested=len(items),
        published=len(items),
        items=items,
        raw_items=0,
    )


@app.post("/api/v1/ingest/rss", response_model=IngestResponse)
def ingest_rss(limit: Optional[int] = Query(default=None, ge=1, le=50)) -> IngestResponse:
    return _run_source_ingestion(limit)


@app.post("/api/v1/ingest/sources", response_model=IngestResponse)
def ingest_sources(
    limit: Optional[int] = Query(default=None, ge=1, le=50),
    per_source: bool = Query(default=False, alias="perSource"),
) -> IngestResponse:
    return _run_source_ingestion(limit, per_source=per_source)


def _run_source_ingestion(
    limit: Optional[int],
    *,
    per_source: bool = False,
    run_enrichment: bool = True,
    trigger: str = "manual",
) -> IngestResponse:
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("ingest")
    sources = repository.list_active_sources()
    logger.info(
        "Ingestion started: active_sources=%s limit=%s per_source=%s run_enrichment=%s",
        len(sources),
        limit,
        per_source,
        run_enrichment,
    )
    try:
        ai_search_prompt = repository.get_active_prompt("ai_search")
        raw_items, source_results = ingest_sources_with_results(
            sources,
            repository.get_source_sync_state_map(),
            limit=limit,
            limit_per_source=per_source,
            ai_search_prompt=ai_search_prompt,
        )
        logger.info(
            "Ingestion collected raw items: total=%s source_results=%s",
            len(raw_items),
            len(source_results),
        )
        inserted_raw_items = repository.insert_raw_items(raw_items)
        logger.info("Ingestion inserted raw items: inserted=%s", inserted_raw_items)
        if run_enrichment:
            _run_ingestion_enrichment(raw_items)
            logger.info("Ingestion enrichment finished for batch: candidate_items=%s", len(raw_items))
        else:
            logger.info("Ingestion enrichment skipped for this run")
        for result in source_results:
            source_items = [item for item in raw_items if item.source_key == result.source.key]
            logger.info(
                "Source result: key=%s fetch=%s parse=%s items=%s retry=%s error=%s",
                result.source.key,
                result.fetch_status,
                result.parse_status,
                len(source_items),
                result.retry_count,
                result.error or "-",
            )
            repository.update_source_sync_state(
                result.source,
                source_items,
                fetch_status=result.fetch_status,
                parse_status=result.parse_status,
                error=result.error,
                retry_count=result.retry_count,
            )
        published = repository.upsert_many(raw_items_to_news(raw_items))
        repository.sync_news_ai_review_flags()
        logger.info(
            "Ingestion finished: raw_items=%s inserted=%s published=%s",
            len(raw_items),
            inserted_raw_items,
            len(published),
        )
        finished_at = datetime.now(timezone.utc)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="ingest",
            trigger=trigger,
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
            found_count=len(raw_items),
            saved_count=inserted_raw_items,
            published_count=len(published),
        )
        return IngestResponse(
            ingested=len(raw_items),
            published=len(published),
            items=published,
            raw_items=inserted_raw_items,
        )
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="ingest",
            trigger=trigger,
            status="error",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_duration_ms(started_at, finished_at),
            error=str(exc),
        )
        raise


def _run_scheduler(*, force: bool) -> SchedulerRunResponse:
    settings = repository.get_scheduler_settings()
    now = datetime.now(timezone.utc)
    logger.info(
        "Scheduler tick: force=%s enabled=%s status=%s next_run_at=%s",
        force,
        settings.enabled,
        settings.last_status,
        settings.next_run_at.isoformat() if settings.next_run_at else "-",
    )

    if not force and not settings.enabled:
        logger.info("Scheduler skipped: disabled")
        return SchedulerRunResponse(ran=False, reason="disabled", next_run_at=settings.next_run_at)

    if not force and settings.next_run_at and settings.next_run_at > now:
        logger.info(
            "Scheduler skipped: not due yet now=%s next_run_at=%s",
            now.isoformat(),
            settings.next_run_at.isoformat(),
        )
        return SchedulerRunResponse(ran=False, reason="not_due", next_run_at=settings.next_run_at)

    with psycopg.connect(repository.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (SCHEDULER_LOCK_KEY,))
            row = cursor.fetchone()
            locked = bool(row and row[0])

        if not locked:
            logger.info("Scheduler skipped: advisory lock is already held")
            return SchedulerRunResponse(ran=False, reason="locked", next_run_at=settings.next_run_at)

        try:
            repository.set_scheduler_status(status="running", error=None)
            logger.info("Scheduler run started")
            scheduler_batch_size = max(1, settings.batch_size)
            logger.info(
                "Scheduler run ingestion mode: limit=%s per_source=%s run_enrichment=%s",
                scheduler_batch_size,
                True,
                settings.run_enrichment,
            )
            ingest_response = _run_source_ingestion(
                limit=scheduler_batch_size,
                per_source=True,
                run_enrichment=settings.run_enrichment,
                trigger="scheduler",
            )
            latest_settings = repository.get_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            repository.mark_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="ok",
                error=None,
                found_count=ingest_response.ingested,
                saved_count=ingest_response.raw_items,
                published_count=ingest_response.published,
            )
            logger.info(
                "Scheduler run finished: ingested=%s published=%s raw_items=%s next_run_at=%s",
                ingest_response.ingested,
                ingest_response.published,
                ingest_response.raw_items,
                next_run_at.isoformat() if next_run_at else "-",
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
            latest_settings = repository.get_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            repository.mark_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="error",
                error=str(exc),
            )
            logger.exception("Scheduler run failed: %s", exc)
            raise
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (SCHEDULER_LOCK_KEY,))
            logger.info("Scheduler advisory lock released")


def _run_enrichment_scheduler(*, force: bool) -> EnrichmentSchedulerRunResponse:
    settings = repository.get_enrichment_scheduler_settings()
    now = datetime.now(timezone.utc)
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("enrichment")
    logger.info(
        "Enrichment scheduler tick: force=%s enabled=%s status=%s next_run_at=%s",
        force,
        settings.enabled,
        settings.last_status,
        settings.next_run_at.isoformat() if settings.next_run_at else "-",
    )

    if not force and not settings.enabled:
        logger.info("Enrichment scheduler skipped: disabled")
        return EnrichmentSchedulerRunResponse(ran=False, reason="disabled", next_run_at=settings.next_run_at)

    if not force and settings.next_run_at and settings.next_run_at > now:
        logger.info(
            "Enrichment scheduler skipped: not due yet now=%s next_run_at=%s",
            now.isoformat(),
            settings.next_run_at.isoformat(),
        )
        return EnrichmentSchedulerRunResponse(ran=False, reason="not_due", next_run_at=settings.next_run_at)

    with psycopg.connect(repository.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (ENRICHMENT_SCHEDULER_LOCK_KEY,))
            row = cursor.fetchone()
            locked = bool(row and row[0])

        if not locked:
            logger.info("Enrichment scheduler skipped: advisory lock is already held")
            return EnrichmentSchedulerRunResponse(ran=False, reason="locked", next_run_at=settings.next_run_at)

        try:
            repository.set_enrichment_scheduler_status(status="running", error=None)
            logger.info("Enrichment scheduler run started")
            batch_size = max(1, settings.batch_size)
            raw_items = repository.list_pending_enrichment_raw_items(limit=batch_size)
            logger.info("Enrichment scheduler selected candidates: batch_size=%s found=%s", batch_size, len(raw_items))
            processed, enriched = _run_enrichment_for_raw_items(raw_items)
            latest_settings = repository.get_enrichment_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            repository.mark_enrichment_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="ok",
                error=None,
                processed_count=processed,
                enriched_count=enriched,
            )
            finished_at = datetime.now(timezone.utc)
            repository.record_pipeline_run(
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
            logger.info(
                "Enrichment scheduler finished: processed=%s enriched=%s next_run_at=%s",
                processed,
                enriched,
                next_run_at.isoformat() if next_run_at else "-",
            )
            return EnrichmentSchedulerRunResponse(
                ran=True,
                reason="ok",
                processed=processed,
                enriched=enriched,
                next_run_at=next_run_at,
            )
        except Exception as exc:
            latest_settings = repository.get_enrichment_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            repository.mark_enrichment_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="error",
                error=str(exc),
            )
            finished_at = datetime.now(timezone.utc)
            repository.record_pipeline_run(
                run_id=run_id,
                phase="enrichment",
                trigger="scheduler",
                status="error",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                error=str(exc),
            )
            logger.exception("Enrichment scheduler failed: %s", exc)
            raise
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (ENRICHMENT_SCHEDULER_LOCK_KEY,))
            logger.info("Enrichment scheduler advisory lock released")


def _run_editorial_scheduler(*, force: bool) -> EditorialSchedulerRunResponse:
    settings = repository.get_editorial_scheduler_settings()
    now = datetime.now(timezone.utc)
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("editorial")
    logger.info(
        "Editorial scheduler tick: force=%s enabled=%s status=%s next_run_at=%s",
        force,
        settings.enabled,
        settings.last_status,
        settings.next_run_at.isoformat() if settings.next_run_at else "-",
    )

    if not force and not settings.enabled:
        logger.info("Editorial scheduler skipped: disabled")
        return EditorialSchedulerRunResponse(ran=False, reason="disabled", next_run_at=settings.next_run_at)

    if not force and settings.next_run_at and settings.next_run_at > now:
        logger.info(
            "Editorial scheduler skipped: not due yet now=%s next_run_at=%s",
            now.isoformat(),
            settings.next_run_at.isoformat(),
        )
        return EditorialSchedulerRunResponse(ran=False, reason="not_due", next_run_at=settings.next_run_at)

    with psycopg.connect(repository.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (EDITORIAL_SCHEDULER_LOCK_KEY,))
            row = cursor.fetchone()
            locked = bool(row and row[0])

        if not locked:
            logger.info("Editorial scheduler skipped: advisory lock is already held")
            return EditorialSchedulerRunResponse(ran=False, reason="locked", next_run_at=settings.next_run_at)

        try:
            repository.set_editorial_scheduler_status(status="running", error=None)
            logger.info("Editorial scheduler run started")
            batch_size = max(1, settings.batch_size)
            planned_items = run_content_planner(repository, limit=batch_size)
            logger.info("Editorial scheduler planner finished: planned=%s", len(planned_items))
            drafts, reviews = run_editorial_cycle(repository, limit=batch_size)
            published_count = len([draft for draft in drafts if draft.status == "published"])
            latest_settings = repository.get_editorial_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            repository.mark_editorial_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="ok",
                error=None,
                planned_count=len(planned_items),
                generated_count=len(drafts),
                reviewed_count=len(reviews),
            )
            finished_at = datetime.now(timezone.utc)
            repository.record_pipeline_run(
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
            logger.info(
                "Editorial scheduler finished: planned=%s generated=%s reviewed=%s next_run_at=%s",
                len(planned_items),
                len(drafts),
                len(reviews),
                next_run_at.isoformat() if next_run_at else "-",
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
            latest_settings = repository.get_editorial_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            repository.mark_editorial_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="error",
                error=str(exc),
            )
            finished_at = datetime.now(timezone.utc)
            repository.record_pipeline_run(
                run_id=run_id,
                phase="editorial",
                trigger="scheduler",
                status="error",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                error=str(exc),
            )
            logger.exception("Editorial scheduler failed: %s", exc)
            raise
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (EDITORIAL_SCHEDULER_LOCK_KEY,))
            logger.info("Editorial scheduler advisory lock released")


def _run_publish_scheduler(*, force: bool) -> PublishSchedulerRunResponse:
    settings = repository.get_publish_scheduler_settings()
    now = datetime.now(timezone.utc)
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("publish")
    logger.info(
        "Publish scheduler tick: force=%s enabled=%s status=%s next_run_at=%s",
        force,
        settings.enabled,
        settings.last_status,
        settings.next_run_at.isoformat() if settings.next_run_at else "-",
    )

    if not force and not settings.enabled:
        logger.info("Publish scheduler skipped: disabled")
        return PublishSchedulerRunResponse(ran=False, reason="disabled", next_run_at=settings.next_run_at)

    if not force and settings.next_run_at and settings.next_run_at > now:
        logger.info(
            "Publish scheduler skipped: not due yet now=%s next_run_at=%s",
            now.isoformat(),
            settings.next_run_at.isoformat(),
        )
        return PublishSchedulerRunResponse(ran=False, reason="not_due", next_run_at=settings.next_run_at)

    with psycopg.connect(repository.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (PUBLISH_SCHEDULER_LOCK_KEY,))
            row = cursor.fetchone()
            locked = bool(row and row[0])

        if not locked:
            logger.info("Publish scheduler skipped: advisory lock is already held")
            return PublishSchedulerRunResponse(ran=False, reason="locked", next_run_at=settings.next_run_at)

        try:
            repository.set_publish_scheduler_status(status="running", error=None)
            logger.info("Publish scheduler run started")
            batch_size = max(1, settings.batch_size)
            published = _run_publish_for_drafts(limit=batch_size)
            latest_settings = repository.get_publish_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            repository.mark_publish_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="ok",
                error=None,
                published_count=published,
            )
            finished_at = datetime.now(timezone.utc)
            repository.record_pipeline_run(
                run_id=run_id,
                phase="publish",
                trigger="scheduler",
                status="ok",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                published_count=published,
            )
            logger.info(
                "Publish scheduler finished: published=%s next_run_at=%s",
                published,
                next_run_at.isoformat() if next_run_at else "-",
            )
            return PublishSchedulerRunResponse(
                ran=True,
                reason="ok",
                published=published,
                next_run_at=next_run_at,
            )
        except Exception as exc:
            latest_settings = repository.get_publish_scheduler_settings()
            next_run_at = (
                now + timedelta(minutes=latest_settings.interval_minutes)
                if latest_settings.enabled
                else None
            )
            repository.mark_publish_scheduler_run(
                ran_at=now,
                next_run_at=next_run_at,
                status="error",
                error=str(exc),
            )
            finished_at = datetime.now(timezone.utc)
            repository.record_pipeline_run(
                run_id=run_id,
                phase="publish",
                trigger="scheduler",
                status="error",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                error=str(exc),
            )
            logger.exception("Publish scheduler failed: %s", exc)
            raise
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (PUBLISH_SCHEDULER_LOCK_KEY,))
            logger.info("Publish scheduler advisory lock released")


def _run_ingestion_enrichment(raw_items: list[RawItem]) -> None:
    _run_enrichment_for_raw_items(raw_items)


def _run_publish_for_drafts(*, limit: int) -> int:
    drafts = repository.list_publishable_drafts(limit=limit)
    published = 0

    for draft in drafts:
        raw_item = repository.get_raw_item(draft.raw_item_id)
        if raw_item is None:
            continue
        repository.publish_draft_to_news(draft, raw_item)
        repository.set_draft_review_status(
            draft.id,
            review_status="reviewed",
            status="published",
            review_summary=draft.review_summary or "Материал опубликован publish-этапом.",
            publish_decision="publish_auto",
            publish_reason="Материал опубликован отдельным publish-этапом.",
        )
        repository.set_content_plan_status(raw_item.id, "published")
        published += 1

    if published:
        repository.sync_news_ai_review_flags()

    return published


def _run_enrichment_for_raw_items(raw_items: list[RawItem]) -> tuple[int, int]:
    candidate_ids = [item.id for item in raw_items if not item.is_duplicate]
    if not candidate_ids:
        logger.info("Enrichment skipped: no non-duplicate raw items in batch")
        return (0, 0)
    logger.info("Enrichment started: candidates=%s", len(candidate_ids))
    enriched_count = 0

    def enrich_one(raw_item_id: str) -> None:
        nonlocal enriched_count
        raw_item = repository.get_raw_item(raw_item_id)
        if raw_item is None or raw_item.is_duplicate:
            return
        before_has_any = bool((raw_item.full_text or "").strip() or (raw_item.lead or "").strip() or raw_item.tags)
        try:
            enrich_raw_item_content(repository, raw_item)
            updated_item = repository.get_raw_item(raw_item_id)
            after_has_any = bool(
                updated_item
                and (
                    (updated_item.full_text or "").strip()
                    or (updated_item.lead or "").strip()
                    or updated_item.tags
                )
            )
            if after_has_any and not before_has_any:
                enriched_count += 1
            logger.info("Enrichment finished: raw_item_id=%s source=%s", raw_item_id, raw_item.source_key)
        except Exception as exc:
            repository.update_raw_item_enrichment(
                raw_item_id,
                enrichment_status="enrichment_error",
                enrichment_error=f"Enrichment pipeline failed: {exc}",
            )
            logger.exception("Enrichment failed: raw_item_id=%s error=%s", raw_item_id, exc)

    max_workers = min(4, len(candidate_ids))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(enrich_one, raw_item_id) for raw_item_id in candidate_ids]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                # Keep source ingestion resilient even if one full-text enrichment path fails.
                continue
    logger.info("Enrichment batch completed: candidates=%s", len(candidate_ids))
    return (len(candidate_ids), enriched_count)


@app.post("/api/v1/dev/reset", response_model=ResetResponse)
def reset_dev_database() -> ResetResponse:
    repository.reset_runtime_data()
    repository.sync_news_ai_review_flags()
    return ResetResponse(cleared=True)
