from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
import psycopg

from .ai_client import OpenAIEditorialClient
from .config import get_openai_settings
from .editorial import (
    default_prompt_configs,
    run_editorial_cycle,
)
from .guide_topics import load_guide_topic_seed
from .ingestion import (
    _capability_supports_adapter,
    build_importance_score_breakdown,
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
    IdempotencyCheck,
    IdempotencyReportResponse,
    MonitoringAlert,
    MonitoringQueueSnapshot,
    MonitoringSchedulerState,
    MonitoringStatusResponse,
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
    GuideSchedulerRunResponse,
    GuideTopicListResponse,
    IngestResponse,
    NewsListResponse,
    NewsItemResponse,
    PublishRunResponse,
    PublishSchedulerRunResponse,
    PublishSchedulerSettings,
    PublishSchedulerSettingsUpdateRequest,
    PromptConfigCreateRequest,
    PromptCleanupResponse,
    PromptConfigListResponse,
    PromptStatusUpdateRequest,
    RecoveryAction,
    RecoveryStatusResponse,
    PipelineRunListResponse,
    PipelineSchedulerRunResponse,
    RawItemListResponse,
    RawItemPreviewListResponse,
    RawItem,
    RawItemPreview,
    ResetResponse,
    SchedulerRunResponse,
    SchedulerSettings,
    SchedulerSettingsUpdateRequest,
    SourceCreateRequest,
    SourceCapability,
    SourceCapabilityListResponse,
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
    _recover_runtime_state(trigger="startup")
    repository.ensure_prompt_defaults(default_prompt_configs())
    repository.ensure_guide_topic_defaults(load_guide_topic_seed())
    repository.maybe_activate_recommended_prompt("writer", "prompt:writer:v7")
    repository.maybe_activate_recommended_prompt("editor", "prompt:editor:v8")
    repository.maybe_activate_recommended_prompt("ai_search", "prompt:ai-search:v1")
    repository.maybe_activate_recommended_prompt("guide_writer", "prompt:guide-writer:v1")
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
GUIDE_SCHEDULER_LOCK_KEY = 4815162346
ENRICHMENT_WEB_SEARCH_CAP_PER_RUN = 3
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)
PIPELINE_RUN_LOCK = threading.Lock()
PIPELINE_RUN_RUNNING = False


def _run_id(phase: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{phase}:{timestamp}"


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _require_admin_api_token(request: Request) -> None:
    expected = (os.getenv("EZBET_ADMIN_API_TOKEN") or "").strip()
    if not expected:
        return

    provided = (request.headers.get("x-admin-token") or "").strip()
    if provided != expected:
        raise HTTPException(status_code=403, detail="Admin token is required for this action.")


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


def _alert_rank(severity: str) -> int:
    if severity == "critical":
        return 3
    if severity == "warning":
        return 2
    return 1


def _overall_monitoring_status(alerts: list[MonitoringAlert]) -> str:
    if any(alert.severity == "critical" for alert in alerts):
        return "critical"
    if alerts:
        return "warning"
    return "ok"


def _scheduler_stale_threshold_minutes(interval_minutes: int) -> int:
    return max(interval_minutes * 3, interval_minutes + 15)


def _build_scheduler_monitor(
    *,
    phase: str,
    settings: object,
    queue_count: int | None,
    now: datetime,
) -> MonitoringSchedulerState:
    alerts: list[MonitoringAlert] = []
    enabled = bool(getattr(settings, "enabled"))
    interval_minutes = int(getattr(settings, "interval_minutes"))
    last_status = str(getattr(settings, "last_status") or "idle")
    last_run_at = getattr(settings, "last_run_at")
    next_run_at = getattr(settings, "next_run_at")
    last_error = getattr(settings, "last_error")
    batch_size = max(1, int(getattr(settings, "batch_size")))

    if enabled and last_status == "error":
        alerts.append(
            MonitoringAlert(
                severity="critical",
                phase=phase,
                code="scheduler_error",
                message=f"{phase} завершился ошибкой и требует проверки.",
                error_reason=last_error,
            )
        )

    if enabled and last_run_at is None:
        alerts.append(
            MonitoringAlert(
                severity="warning",
                phase=phase,
                code="never_ran",
                message=f"{phase} еще ни разу не запускался после включения.",
            )
        )

    if enabled and last_run_at is not None:
        stale_threshold = _scheduler_stale_threshold_minutes(interval_minutes)
        age_minutes = int((now - last_run_at).total_seconds() // 60)
        if age_minutes > stale_threshold:
            alerts.append(
                MonitoringAlert(
                    severity="critical" if (queue_count or 0) > 0 else "warning",
                    phase=phase,
                    code="stale_run",
                    message=f"{phase} не запускался слишком долго.",
                    observed_value=age_minutes,
                    threshold_value=stale_threshold,
                )
            )

    if queue_count is not None:
        if not enabled and queue_count > 0:
            alerts.append(
                MonitoringAlert(
                    severity="warning",
                    phase=phase,
                    code="queue_while_disabled",
                    message=f"У {phase} есть очередь, но scheduler выключен.",
                    observed_value=queue_count,
                )
            )
        backlog_threshold = max(batch_size * 3, 10)
        if queue_count >= backlog_threshold:
            alerts.append(
                MonitoringAlert(
                    severity="warning",
                    phase=phase,
                    code="queue_backlog",
                    message=f"Очередь {phase} растет быстрее, чем ее успевают разбирать.",
                    observed_value=queue_count,
                    threshold_value=backlog_threshold,
                )
            )

    alerts.sort(key=lambda item: _alert_rank(item.severity), reverse=True)
    return MonitoringSchedulerState(
        phase=phase,
        enabled=enabled,
        healthy=not alerts,
        last_status=last_status,
        last_run_at=last_run_at,
        next_run_at=next_run_at,
        interval_minutes=interval_minutes,
        queue_count=queue_count,
        alerts=alerts,
    )


def _build_monitoring_status() -> MonitoringStatusResponse:
    now = datetime.now(timezone.utc)
    scheduler_settings = repository.get_scheduler_settings()
    enrichment_settings = repository.get_enrichment_scheduler_settings()
    editorial_settings = repository.get_editorial_scheduler_settings()
    publish_settings = repository.get_publish_scheduler_settings()

    queues = MonitoringQueueSnapshot(
        enrichment=repository.count_pending_enrichment_raw_items(),
        editorial=repository.count_planned_raw_items_for_drafts(),
        publish=repository.count_publishable_drafts(),
    )

    schedulers = [
        _build_scheduler_monitor(
            phase="ingest",
            settings=scheduler_settings,
            queue_count=None,
            now=now,
        ),
        _build_scheduler_monitor(
            phase="enrichment",
            settings=enrichment_settings,
            queue_count=queues.enrichment,
            now=now,
        ),
        _build_scheduler_monitor(
            phase="editorial",
            settings=editorial_settings,
            queue_count=queues.editorial,
            now=now,
        ),
        _build_scheduler_monitor(
            phase="publish",
            settings=publish_settings,
            queue_count=queues.publish,
            now=now,
        ),
    ]

    alerts = [alert for scheduler in schedulers for alert in scheduler.alerts]
    alerts.sort(key=lambda item: _alert_rank(item.severity), reverse=True)
    return MonitoringStatusResponse(
        status=_overall_monitoring_status(alerts),
        generated_at=now,
        queues=queues,
        schedulers=schedulers,
        alerts=alerts,
    )


def _recover_runtime_state(*, trigger: str) -> RecoveryStatusResponse:
    checked_at = datetime.now(timezone.utc)
    actions: list[RecoveryAction] = []
    recovery_plan = [
        ("ingest", repository.get_scheduler_settings, repository.recover_scheduler_if_stale),
        ("enrichment", repository.get_enrichment_scheduler_settings, repository.recover_enrichment_scheduler_if_stale),
        ("editorial", repository.get_editorial_scheduler_settings, repository.recover_editorial_scheduler_if_stale),
        ("publish", repository.get_publish_scheduler_settings, repository.recover_publish_scheduler_if_stale),
    ]

    for phase, get_settings, recover_fn in recovery_plan:
        settings = get_settings()
        if settings.last_status != "running":
            continue
        recovered_settings = recover_fn()
        action = RecoveryAction(
            phase=phase,
            previous_status="running",
            recovered_status=recovered_settings.last_status,
            message=recovered_settings.last_error or "Recovered stale running status.",
            updated_at=recovered_settings.updated_at,
        )
        actions.append(action)
        _log_pipeline_event(
            "recovery_action",
            phase=phase,
            trigger=trigger,
            status=recovered_settings.last_status,
            error_reason=recovered_settings.last_error,
            updated_at=recovered_settings.updated_at.isoformat() if recovered_settings.updated_at else None,
        )

    if not actions:
        _log_pipeline_event(
            "recovery_check",
            phase="pipeline",
            trigger=trigger,
            status="ok",
            counts={"recovered": 0},
        )
    else:
        _log_pipeline_event(
            "recovery_completed",
            phase="pipeline",
            trigger=trigger,
            status="ok",
            counts={"recovered": len(actions)},
        )

    return RecoveryStatusResponse(
        recovered=bool(actions),
        trigger=trigger,
        checked_at=checked_at,
        actions=actions,
    )


def _build_idempotency_report() -> IdempotencyReportResponse:
    checked_at = datetime.now(timezone.utc)
    ready_to_publish_with_existing_article = repository.count_ready_to_publish_with_existing_article()
    published_drafts_missing_article = repository.count_published_drafts_missing_article()
    published_drafts_missing_news_item = repository.count_published_drafts_missing_news_item()
    articles_missing_published_draft = repository.count_articles_missing_published_draft()
    multiple_articles_per_news_item = repository.count_multiple_articles_per_news_item()

    checks = [
        IdempotencyCheck(
            code="ready_to_publish_already_has_article",
            passed=ready_to_publish_with_existing_article == 0,
            message="Draft в очереди publish не должен уже иметь опубликованную article-запись.",
            observed_value=ready_to_publish_with_existing_article,
            expected_value=0,
            severity="critical",
        ),
        IdempotencyCheck(
            code="published_draft_missing_article",
            passed=published_drafts_missing_article == 0,
            message="Published draft должен иметь связанную article-запись.",
            observed_value=published_drafts_missing_article,
            expected_value=0,
            severity="critical",
        ),
        IdempotencyCheck(
            code="published_draft_missing_news_item",
            passed=published_drafts_missing_news_item == 0,
            message="Published draft должен иметь связанную news_item-запись.",
            observed_value=published_drafts_missing_news_item,
            expected_value=0,
            severity="critical",
        ),
        IdempotencyCheck(
            code="article_missing_published_draft",
            passed=articles_missing_published_draft == 0,
            message="Каждая article-запись из auto-pipeline должна происходить из published draft.",
            observed_value=articles_missing_published_draft,
            expected_value=0,
            severity="warning",
        ),
        IdempotencyCheck(
            code="multiple_articles_per_news_item",
            passed=multiple_articles_per_news_item == 0,
            message="Один news_item не должен иметь несколько article-записей.",
            observed_value=multiple_articles_per_news_item,
            expected_value=0,
            severity="critical",
        ),
    ]

    status = "critical" if any((not check.passed) and check.severity == "critical" for check in checks) else (
        "warning" if any(not check.passed for check in checks) else "ok"
    )
    return IdempotencyReportResponse(status=status, checked_at=checked_at, checks=checks)


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


@app.get("/api/v1/monitoring/status", response_model=MonitoringStatusResponse)
def monitoring_status() -> MonitoringStatusResponse:
    return _build_monitoring_status()


@app.post("/api/v1/recovery/run", response_model=RecoveryStatusResponse)
def run_recovery() -> RecoveryStatusResponse:
    return _recover_runtime_state(trigger="manual")


@app.get("/api/v1/monitoring/idempotency", response_model=IdempotencyReportResponse)
def monitoring_idempotency() -> IdempotencyReportResponse:
    return _build_idempotency_report()


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
    request: Request,
    query: Optional[str] = Query(default=None),
    ai_only: bool = Query(default=False, alias="aiOnly"),
    guide_only: bool = Query(default=False, alias="guideOnly"),
    include_hidden: bool = Query(default=False, alias="includeHidden"),
    limit: Optional[int] = Query(default=None, ge=1, le=100),
) -> NewsListResponse:
    if include_hidden:
        _require_admin_api_token(request)

    return NewsListResponse(
        items=repository.list(
            query,
            ai_only=ai_only,
            guide_only=guide_only,
            include_hidden=include_hidden,
            limit=limit,
        )
    )


@app.get("/api/v1/articles/{slug}", response_model=ArticleResponse)
def get_article(slug: str) -> ArticleResponse:
    article = repository.get_article_by_slug(slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleResponse(item=article)


@app.post("/api/v1/articles/reflow-publication-times")
def reflow_article_publication_times(
    request: Request,
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, int]:
    _require_admin_api_token(request)
    return {"updated": repository.reflow_public_published_at_for_articles(limit=limit)}


@app.post("/api/v1/news/{news_item_id:path}/hide", response_model=NewsItemResponse)
def hide_news_item(news_item_id: str, request: Request) -> NewsItemResponse:
    _require_admin_api_token(request)
    item = repository.set_news_visibility(news_item_id, "hidden")
    if item is None:
        raise HTTPException(status_code=404, detail="News item not found")
    return NewsItemResponse(item=item)


@app.post("/api/v1/news/{news_item_id:path}/unhide", response_model=NewsItemResponse)
def unhide_news_item(news_item_id: str, request: Request) -> NewsItemResponse:
    _require_admin_api_token(request)
    item = repository.set_news_visibility(news_item_id, "public")
    if item is None:
        raise HTTPException(status_code=404, detail="News item not found")
    return NewsItemResponse(item=item)


@app.get("/api/v1/sources", response_model=SourceListResponse)
def list_sources() -> SourceListResponse:
    return SourceListResponse(items=repository.list_source_configs())


@app.post("/api/v1/sources", response_model=SourceListResponse)
def create_source(payload: SourceCreateRequest) -> SourceListResponse:
    try:
        source_type = payload.resolved_source_type or payload.source_type
        _validate_source_create_request(payload, source_type)
        source = SourceItem(
            key=payload.key,
            title=payload.title,
            url=payload.url,
            category=payload.category,
            source_type=source_type,
            status=payload.status,
            notes=payload.notes,
        )

        if payload.probe_ok:
            draft_source = source.model_copy(update={"status": "draft"})
            repository.create_source_config(draft_source)
            repository.record_source_probe(
                draft_source,
                ok=payload.probe_ok,
                item_count=payload.probe_item_count,
                message="Preflight сохранен из UI перед активацией источника.",
                readiness=payload.probe_readiness,
                preferred_adapter=payload.resolved_source_type or source_type,
                preferred_adapter_url=payload.resolved_source_url or payload.url,
                supports_rss=payload.supports_rss,
                supports_news_sitemap=payload.supports_news_sitemap,
                supports_sitemap=payload.supports_sitemap,
                supports_scraping=payload.supports_scraping,
                full_text_ok=payload.full_text_ok,
                lead_ok=payload.lead_ok,
                tags_count=payload.tags_count,
                sample_title=payload.sample_title,
                sample_url=payload.sample_url,
            )
            repository.update_source_config(draft_source.model_copy(update={"status": "active"}))
        else:
            repository.create_source_config(source)
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
    try:
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
    except Exception as exc:
        _raise_source_probe_http_error(exc)


@app.post("/api/v1/sources/{source_key}/probe", response_model=SourceProbeResponse)
def probe_source_config(source_key: str) -> SourceProbeResponse:
    try:
        source = repository.get_source_config(source_key)
        return _probe_source_item(source, persist=True)
    except Exception as exc:
        _raise_source_probe_http_error(exc)


def _raise_source_probe_http_error(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.exception("source_probe_failed")
    raise HTTPException(status_code=502, detail=f"Source probe failed: {exc}") from exc


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
                    result.full_text_method = "web_search"
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
            full_text_method=result.full_text_method,
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
        full_text_method=result.full_text_method,
        lead_ok=result.lead_ok,
        tags_count=result.tags_count,
        sample_title=result.sample_title,
        sample_url=result.sample_url,
    )


@app.get("/api/v1/source-states", response_model=SourceSyncStateListResponse)
def list_source_states() -> SourceSyncStateListResponse:
    return SourceSyncStateListResponse(items=repository.list_source_sync_states())


@app.get("/api/v1/source-capabilities", response_model=SourceCapabilityListResponse)
def list_source_capabilities() -> SourceCapabilityListResponse:
    sources = repository.list_source_configs()
    states = repository.list_source_sync_states()
    state_map = {state.source_key: state for state in states}
    items = [_build_source_capability(source, state_map.get(source.key)) for source in sources]
    return SourceCapabilityListResponse(items=items)


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
    _log_pipeline_event(
        "run_started",
        phase="enrichment",
        run_id=run_id,
        trigger="manual",
        status="running",
        counts={"limit": limit},
    )
    raw_items = repository.list_pending_enrichment_raw_items(limit=limit)
    try:
        processed, enriched = _run_enrichment_for_raw_items(raw_items)
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="enrichment",
            trigger="manual",
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            processed_count=processed,
            enriched_count=enriched,
        )
        _log_pipeline_event(
            "run_finished",
            phase="enrichment",
            run_id=run_id,
            trigger="manual",
            status="ok",
            duration_ms=duration_ms,
            counts={"processed": processed, "enriched": enriched},
        )
        return EnrichmentRunResponse(processed=processed, enriched=enriched)
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="enrichment",
            trigger="manual",
            status="error",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            error=str(exc),
        )
        _log_pipeline_event(
            "run_failed",
            phase="enrichment",
            run_id=run_id,
            trigger="manual",
            status="error",
            error_reason=str(exc),
            duration_ms=duration_ms,
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


@app.post("/api/v1/pipeline/tick", response_model=PipelineSchedulerRunResponse)
def run_pipeline_tick() -> PipelineSchedulerRunResponse:
    return _run_pipeline_scheduler(force=False)


@app.post("/api/v1/pipeline/run", response_model=PipelineSchedulerRunResponse)
def run_pipeline_now() -> PipelineSchedulerRunResponse:
    return _run_pipeline_scheduler(force=True)


@app.get("/api/v1/guides/topics", response_model=GuideTopicListResponse)
def list_guide_topics(
    limit: int = Query(default=50, ge=1, le=365),
    status: Optional[str] = Query(default=None),
) -> GuideTopicListResponse:
    return GuideTopicListResponse(items=repository.list_guide_topics(limit=limit, status=status))


@app.post("/api/v1/guides/scheduler/run", response_model=GuideSchedulerRunResponse)
def run_guide_scheduler_now() -> GuideSchedulerRunResponse:
    return _run_guide_scheduler()


@app.post("/api/v1/pipeline/start")
def start_pipeline_now() -> dict[str, object]:
    global PIPELINE_RUN_RUNNING

    with PIPELINE_RUN_LOCK:
        if PIPELINE_RUN_RUNNING:
            return {
                "started": False,
                "reason": "already_running",
                "message": "Pipeline уже выполняется в фоне.",
            }
        PIPELINE_RUN_RUNNING = True

    started_at = datetime.now(timezone.utc)

    def _worker() -> None:
        global PIPELINE_RUN_RUNNING
        try:
            _run_pipeline_scheduler(force=True)
        except Exception:
            logger.exception("Background pipeline run failed")
        finally:
            with PIPELINE_RUN_LOCK:
                PIPELINE_RUN_RUNNING = False

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"pipeline-run-{started_at.strftime('%Y%m%d%H%M%S%f')}",
    ).start()
    return {
        "started": True,
        "reason": "background_started",
        "message": "Pipeline запущен в фоне. Обновите Admin или Studio через несколько секунд.",
        "startedAt": started_at.isoformat(),
    }


@app.get("/api/v1/raw-items", response_model=RawItemListResponse)
def list_raw_items(limit: int = Query(default=50, ge=1, le=200)) -> RawItemListResponse:
    items = [_with_score_breakdown(item) for item in repository.list_raw_items(limit)]
    return RawItemListResponse(items=items)


@app.get("/api/v1/raw-items/preview", response_model=RawItemPreviewListResponse)
def list_raw_item_previews(
    limit: int = Query(default=50, ge=1, le=200),
    scope: str = Query(default="latest"),
) -> RawItemPreviewListResponse:
    if scope == "latest_ingest":
        scheduler_settings = repository.get_scheduler_settings()
        raw_items = (
            repository.list_raw_item_previews_since(scheduler_settings.last_run_at, limit)
            if scheduler_settings.last_run_at
            else []
        )
    else:
        raw_items = repository.list_raw_item_previews(limit)

    items = [_with_score_breakdown(item) for item in raw_items]
    return RawItemPreviewListResponse(items=items)


def _with_score_breakdown(item: RawItem | RawItemPreview) -> RawItem | RawItemPreview:
    source_url = item.source_url if isinstance(item, RawItem) else ""
    source = SourceItem(
        key=item.source_key,
        title=item.source_title,
        url=source_url,
        category=item.category,
    )
    breakdown = build_importance_score_breakdown(
        title=item.title,
        summary=item.summary,
        published_at=item.published_at,
        source=source,
        tags=item.tags,
    )
    return item.model_copy(update={"score_breakdown": breakdown})


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


@app.post("/api/v1/prompts/cleanup", response_model=PromptCleanupResponse)
def cleanup_prompt_versions() -> PromptCleanupResponse:
    deleted_count = repository.delete_archived_prompt_versions()
    return PromptCleanupResponse(deleted_count=deleted_count)


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
    _log_pipeline_event(
        "run_started",
        phase="editorial",
        run_id=run_id,
        trigger="manual",
        status="running",
        counts={"limit": limit},
    )
    try:
        drafts, reviews = run_editorial_cycle(repository, limit=limit)
        published_count = len([draft for draft in drafts if draft.status == "published"])
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="editorial",
            trigger="manual",
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            published_count=published_count,
            generated_count=len(drafts),
            reviewed_count=len(reviews),
        )
        _log_pipeline_event(
            "run_finished",
            phase="editorial",
            run_id=run_id,
            trigger="manual",
            status="ok",
            duration_ms=duration_ms,
            counts={
                "generated": len(drafts),
                "reviewed": len(reviews),
                "published_ready": published_count,
            },
        )
        return EditorialRunResponse(generated=len(drafts), reviewed=len(reviews), drafts=drafts)
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="editorial",
            trigger="manual",
            status="error",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            error=str(exc),
        )
        _log_pipeline_event(
            "run_failed",
            phase="editorial",
            run_id=run_id,
            trigger="manual",
            status="error",
            error_reason=str(exc),
            duration_ms=duration_ms,
        )
        raise


@app.post("/api/v1/publish/run", response_model=PublishRunResponse)
def run_publish(limit: int = Query(default=5, ge=1, le=20)) -> PublishRunResponse:
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("publish")
    _log_pipeline_event(
        "run_started",
        phase="publish",
        run_id=run_id,
        trigger="manual",
        status="running",
        counts={"limit": limit},
    )
    try:
        published = _run_publish_for_drafts(limit=limit)
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="publish",
            trigger="manual",
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            published_count=published,
        )
        _log_pipeline_event(
            "run_finished",
            phase="publish",
            run_id=run_id,
            trigger="manual",
            status="ok",
            duration_ms=duration_ms,
            counts={"published": published},
        )
        return PublishRunResponse(published=published)
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="publish",
            trigger="manual",
            status="error",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            error=str(exc),
        )
        _log_pipeline_event(
            "run_failed",
            phase="publish",
            run_id=run_id,
            trigger="manual",
            status="error",
            error_reason=str(exc),
            duration_ms=duration_ms,
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
    _log_pipeline_event(
        "run_started",
        phase="ingest",
        run_id=run_id,
        trigger=trigger,
        status="running",
        counts={"active_sources": len(sources)},
        limit=limit or 0,
        per_source=per_source,
        run_enrichment=run_enrichment,
    )
    try:
        ai_search_prompt = repository.get_active_prompt("ai_search")
        source_keys = [source.key for source in sources]
        known_external_ids_by_source = repository.get_recent_known_external_ids_by_source(
            source_keys
        )
        known_dedupe_keys_by_source = repository.get_recent_known_dedupe_keys_by_source(
            source_keys
        )
        raw_items, source_results = ingest_sources_with_results(
            sources,
            repository.get_source_sync_state_map(),
            known_external_ids_by_source=known_external_ids_by_source,
            known_dedupe_keys_by_source=known_dedupe_keys_by_source,
            limit=limit,
            limit_per_source=per_source,
            ai_search_prompt=ai_search_prompt,
        )
        prefilter_result = repository.prefilter_known_raw_items(raw_items)
        raw_items = prefilter_result.fresh_items
        _log_pipeline_event(
            "source_collection_completed",
            phase="ingest",
            run_id=run_id,
            trigger=trigger,
            status="ok",
            counts={
                "total_candidates": len(raw_items) + len(prefilter_result.skipped_items),
                "fresh_after_prefilter": len(raw_items),
                "source_results": len(source_results),
            },
        )
        insert_result = repository.insert_raw_items(raw_items)
        inserted_raw_items = insert_result.inserted_count
        _log_pipeline_event(
            "raw_items_inserted",
            phase="ingest",
            run_id=run_id,
            trigger=trigger,
            status="ok",
            counts={"inserted": inserted_raw_items},
        )
        if run_enrichment:
            _run_ingestion_enrichment(raw_items)
            _log_pipeline_event(
                "ingestion_enrichment_completed",
                phase="ingest",
                run_id=run_id,
                trigger=trigger,
                status="ok",
                counts={"candidate_items": len(raw_items)},
            )
        else:
            _log_pipeline_event(
                "ingestion_enrichment_skipped",
                phase="ingest",
                run_id=run_id,
                trigger=trigger,
                status="skipped",
                error_reason="run_enrichment_disabled",
            )
        for result in source_results:
            source_items = [item for item in raw_items if item.source_key == result.source.key]
            _log_pipeline_event(
                "source_result",
                phase="ingest",
                run_id=run_id,
                source=result.source.key,
                trigger=trigger,
                status="ok" if not result.error else "error",
                error_reason=result.error,
                counts={
                    "parsed": len(result.items),
                    "fresh": len(source_items),
                    "filtered": max(0, len(result.items) - len(source_items)),
                    "filter_reasons": result.filter_reasons or {},
                    "retry_count": result.retry_count,
                },
                fetch_status=result.fetch_status,
                parse_status=result.parse_status,
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
        skipped_items = _merge_skipped_ingest_items(
            prefilter_result.skipped_items,
            insert_result.skipped_items,
            [
                {
                    "title": item.title,
                    "reason": item.duplicate_reason or "Новость отсечена как дубль и не попала в ленту.",
                }
                for item in raw_items
                if item.is_duplicate
            ],
        )
        source_breakdown = [
            {
                "source_key": result.source.key,
                "source_title": result.source.title,
                "found_count": len([item for item in raw_items if item.source_key == result.source.key]),
                "parsed_count": len(result.items),
                "fresh_count": len([item for item in raw_items if item.source_key == result.source.key]),
                "filtered_count": max(
                    0,
                    len(result.items) - len([item for item in raw_items if item.source_key == result.source.key]),
                ),
                "filter_reasons": result.filter_reasons or {},
            }
            for result in source_results
        ]
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="ingest",
            trigger=trigger,
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            found_count=len(raw_items),
            saved_count=inserted_raw_items,
            published_count=len(published),
            skipped_items=skipped_items,
            source_breakdown=source_breakdown,
        )
        _log_pipeline_event(
            "run_finished",
            phase="ingest",
            run_id=run_id,
            trigger=trigger,
            status="ok",
            duration_ms=duration_ms,
            counts={
                "raw_items": len(raw_items),
                "inserted": inserted_raw_items,
                "published": len(published),
                "skipped": len(skipped_items),
            },
        )
        return IngestResponse(
            ingested=len(raw_items),
            published=len(published),
            items=published,
            raw_items=inserted_raw_items,
        )
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        repository.record_pipeline_run(
            run_id=run_id,
            phase="ingest",
            trigger=trigger,
            status="error",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            error=str(exc),
        )
        _log_pipeline_event(
            "run_failed",
            phase="ingest",
            run_id=run_id,
            trigger=trigger,
            status="error",
            error_reason=str(exc),
            duration_ms=duration_ms,
        )
        raise


def _merge_skipped_ingest_items(
    *groups: list[dict[str, str]],
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for group in groups:
        for item in group:
            title = str(item.get("title", "")).strip()
            reason = str(item.get("reason", "")).strip()
            if not title:
                continue
            key = (title, reason)
            if key in seen:
                continue
            seen.add(key)
            merged.append({"title": title, "reason": reason})

    return merged


def _run_scheduler(*, force: bool) -> SchedulerRunResponse:
    settings = repository.get_scheduler_settings()
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

    with repository.connect() as connection:
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
            repository.set_scheduler_status(status="running", error=None)
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


def _run_enrichment_scheduler(*, force: bool) -> EnrichmentSchedulerRunResponse:
    settings = repository.get_enrichment_scheduler_settings()
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

    with repository.connect() as connection:
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
            repository.set_enrichment_scheduler_status(status="running", error=None)
            batch_size = max(1, settings.batch_size)
            ingest_settings = repository.get_scheduler_settings()
            raw_items = repository.list_pending_enrichment_raw_items(
                limit=batch_size,
                since=ingest_settings.last_run_at,
            )
            _log_pipeline_event(
                "scheduler_run_started",
                phase="enrichment",
                run_id=run_id,
                trigger=trigger,
                status="running",
                counts={"batch_size": batch_size, "candidates_found": len(raw_items)},
            )
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


def _run_editorial_scheduler(*, force: bool) -> EditorialSchedulerRunResponse:
    settings = repository.get_editorial_scheduler_settings()
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

    with repository.connect() as connection:
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
            repository.set_editorial_scheduler_status(status="running", error=None)
            batch_size = max(1, settings.batch_size)
            ingest_settings = repository.get_scheduler_settings()
            current_ingest_started_at = ingest_settings.last_run_at
            planned_items = run_content_planner(
                repository,
                limit=batch_size,
                since=current_ingest_started_at,
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
                repository,
                limit=batch_size,
                since=current_ingest_started_at,
            )
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


def _run_publish_scheduler(*, force: bool) -> PublishSchedulerRunResponse:
    settings = repository.get_publish_scheduler_settings()
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

    with repository.connect() as connection:
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
            repository.set_publish_scheduler_status(status="running", error=None)
            batch_size = max(1, settings.batch_size)
            _log_pipeline_event(
                "scheduler_run_started",
                phase="publish",
                run_id=run_id,
                trigger=trigger,
                status="running",
                counts={"batch_size": batch_size},
            )
            ingest_settings = repository.get_scheduler_settings()
            published = _run_publish_for_drafts(limit=batch_size, since=ingest_settings.last_run_at)
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


def _run_pipeline_scheduler(*, force: bool) -> PipelineSchedulerRunResponse:
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
    ingest = _run_pipeline_stage(
        "ingest",
        run_id=run_id,
        trigger=mode,
        run=lambda: _run_scheduler(force=force),
        fallback=lambda error: SchedulerRunResponse(ran=False, reason=f"error: {error}"),
    )
    enrichment = _run_pipeline_stage(
        "enrichment",
        run_id=run_id,
        trigger=mode,
        run=lambda: _run_enrichment_scheduler(force=force),
        fallback=lambda error: EnrichmentSchedulerRunResponse(ran=False, reason=f"error: {error}"),
    )
    editorial = _run_pipeline_stage(
        "editorial",
        run_id=run_id,
        trigger=mode,
        run=lambda: _run_editorial_scheduler(force=force),
        fallback=lambda error: EditorialSchedulerRunResponse(ran=False, reason=f"error: {error}"),
    )
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


def _run_ingestion_enrichment(raw_items: list[RawItem]) -> None:
    _run_enrichment_for_raw_items(raw_items)


def _run_guide_scheduler() -> GuideSchedulerRunResponse:
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("guide")
    _log_pipeline_event(
        "scheduler_tick",
        phase="guide",
        run_id=run_id,
        trigger="run",
        status="starting",
    )

    with repository.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (GUIDE_SCHEDULER_LOCK_KEY,))
            row = cursor.fetchone()
            locked = bool(row and row[0])

        if not locked:
            _log_pipeline_event(
                "scheduler_skipped",
                phase="guide",
                run_id=run_id,
                trigger="run",
                status="skipped",
                error_reason="locked",
            )
            return GuideSchedulerRunResponse(ran=False, reason="locked")

        topic = None
        try:
            topic = repository.claim_next_guide_topic()
            if topic is None:
                finished_at = datetime.now(timezone.utc)
                repository.record_pipeline_run(
                    run_id=run_id,
                    phase="guide",
                    trigger="scheduler",
                    status="ok",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=_duration_ms(started_at, finished_at),
                )
                return GuideSchedulerRunResponse(ran=False, reason="no_planned_topics")

            prompt = repository.get_active_prompt("guide_writer")
            generated = OpenAIEditorialClient().generate_guide_article(topic, prompt)
            if generated is None:
                raise RuntimeError("Guide writer did not return a valid article.")

            article = repository.publish_guide_article(
                topic=topic,
                title=generated.title,
                dek=generated.dek,
                body=generated.body,
                model=generated.model,
                generation_mode=generated.generation_mode,
                prompt=prompt,
            )
            stored_topic = repository.get_guide_topic(topic.id) or topic
            finished_at = datetime.now(timezone.utc)
            repository.record_pipeline_run(
                run_id=run_id,
                phase="guide",
                trigger="scheduler",
                status="ok",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                generated_count=1,
                published_count=1,
            )
            _log_pipeline_event(
                "scheduler_run_finished",
                phase="guide",
                run_id=run_id,
                trigger="run",
                status="ok",
                duration_ms=_duration_ms(started_at, finished_at),
                counts={"generated": 1, "published": 1},
                topic_number=topic.topic_number,
                article_slug=article.slug,
            )
            return GuideSchedulerRunResponse(
                ran=True,
                reason="ok",
                generated=1,
                published=1,
                topic=stored_topic,
                article=article,
            )
        except Exception as exc:
            if topic is not None:
                repository.mark_guide_topic_error(topic.id, str(exc))
            finished_at = datetime.now(timezone.utc)
            repository.record_pipeline_run(
                run_id=run_id,
                phase="guide",
                trigger="scheduler",
                status="error",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                error=str(exc),
            )
            _log_pipeline_event(
                "scheduler_run_failed",
                phase="guide",
                run_id=run_id,
                trigger="run",
                status="error",
                error_reason=str(exc),
                duration_ms=_duration_ms(started_at, finished_at),
            )
            logger.exception("Guide scheduler failed: %s", exc)
            raise
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (GUIDE_SCHEDULER_LOCK_KEY,))


def _run_publish_for_drafts(*, limit: int, since: datetime | None = None) -> int:
    drafts = repository.list_publishable_drafts(limit=limit, since=since)
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
    candidate_items = [item for item in raw_items if not item.is_duplicate]
    candidate_ids = [item.id for item in candidate_items]
    if not candidate_ids:
        _log_pipeline_event(
            "batch_skipped",
            phase="enrichment",
            status="skipped",
            error_reason="no_non_duplicate_candidates",
        )
        return (0, 0)
    web_search_budget_ids = {
        item.id
        for item in sorted(
            (
                item
                for item in candidate_items
                if item.triage_label in {"high", "medium"}
            ),
            key=lambda item: (item.importance_score, item.published_at),
            reverse=True,
        )[:ENRICHMENT_WEB_SEARCH_CAP_PER_RUN]
    }
    _log_pipeline_event(
        "batch_started",
        phase="enrichment",
        status="running",
        counts={"candidates": len(candidate_ids)},
    )
    _log_pipeline_event(
        "web_search_budget",
        phase="enrichment",
        status="ok",
        counts={
            "cap": ENRICHMENT_WEB_SEARCH_CAP_PER_RUN,
            "eligible": len(web_search_budget_ids),
        },
    )
    enriched_count = 0

    def enrich_one(raw_item_id: str) -> None:
        nonlocal enriched_count
        raw_item = repository.get_raw_item(raw_item_id)
        if raw_item is None or raw_item.is_duplicate:
            return
        before_has_any = bool((raw_item.full_text or "").strip() or (raw_item.lead or "").strip() or raw_item.tags)
        try:
            enrich_raw_item_content(
                repository,
                raw_item,
                allow_web_search_fallback=raw_item_id in web_search_budget_ids,
            )
            updated_item = repository.get_raw_item(raw_item_id)
            if updated_item is not None and not updated_item.is_duplicate:
                deduped_item = repository.recheck_raw_item_duplicate_after_enrichment(raw_item_id)
                if deduped_item is not None:
                    updated_item = deduped_item
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
            if updated_item is not None and updated_item.is_duplicate:
                _log_pipeline_event(
                    "duplicate_detected",
                    phase="enrichment",
                    source=raw_item.source_key,
                    status="ok",
                    counts={"enriched_count": enriched_count},
                    raw_item_id=raw_item_id,
                    duplicate_of=updated_item.duplicate_of,
                )
            _log_pipeline_event(
                "item_finished",
                phase="enrichment",
                source=raw_item.source_key,
                status="ok",
                counts={"enriched_count": enriched_count},
                raw_item_id=raw_item_id,
                enrichment_status=updated_item.enrichment_status if updated_item else None,
            )
        except Exception as exc:
            repository.update_raw_item_enrichment(
                raw_item_id,
                enrichment_status="enrichment_error",
                enrichment_error=f"Enrichment pipeline failed: {exc}",
            )
            _log_pipeline_event(
                "item_failed",
                phase="enrichment",
                source=raw_item.source_key,
                status="error",
                error_reason=str(exc),
                raw_item_id=raw_item_id,
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
    _log_pipeline_event(
        "batch_finished",
        phase="enrichment",
        status="ok",
        counts={"candidates": len(candidate_ids), "enriched": enriched_count},
    )
    return (len(candidate_ids), enriched_count)


def _validate_source_create_request(payload: SourceCreateRequest, source_type: str) -> None:
    if not source_type or source_type == "auto":
        raise ValueError("Проверка не подтвердила подходящий тип источника. Сначала выполните preflight.")
    if source_type == "sitemap":
        raise ValueError(
            "Обычный sitemap больше не используется в автоматическом новостном pipeline. "
            "Нужен RSS, news sitemap, scraping или ai search."
        )
    if source_type not in {"rss", "news_sitemap", "scraping", "ai_research"}:
        raise ValueError(f"Источник типа {source_type} нельзя активировать в текущем pipeline.")
    if not payload.probe_ok:
        raise ValueError("Сначала выполните успешную проверку источника.")
    if payload.probe_item_count <= 0:
        raise ValueError("Проверка источника не подтвердила ни одной новости.")

    readiness = payload.probe_readiness or "unknown"
    if source_type == "rss":
        if not payload.supports_rss and payload.resolved_source_type != "rss":
            raise ValueError("Проверка не подтвердила, что источник действительно отдает рабочий RSS.")
        if readiness not in {"ready", "ready_ai", "partial", "feed_only"}:
            raise ValueError(
                "RSS-источник не прошел preflight: лента читается, но sample-новости пока выглядят слишком слабо."
            )
        return

    if source_type == "news_sitemap":
        if not payload.supports_news_sitemap and payload.resolved_source_type != "news_sitemap":
            raise ValueError("Проверка не подтвердила рабочий news sitemap.")
        if readiness not in {"ready", "ready_ai", "partial", "feed_only"}:
            raise ValueError(
                "News sitemap не прошел preflight: sample-новости не выглядят пригодными для auto-pipeline."
            )
        return

    if source_type == "scraping":
        if not payload.supports_scraping and payload.resolved_source_type != "scraping":
            raise ValueError("Проверка не подтвердила рабочий scraping-источник.")
        if readiness not in {"ready", "ready_ai", "partial"}:
            raise ValueError(
                "Scraping-источник не прошел preflight: страница пока больше похожа на хаб, ленту или служебный раздел."
            )
        return

    if source_type == "ai_research" and readiness not in {"ready_ai", "partial"}:
        raise ValueError(
            "AI search-источник не прошел preflight: даже fallback-режим не подтвердил, что из него получится собирать новости."
        )


def _build_source_capability(source: SourceItem, state) -> SourceCapability:
    readiness = state.last_probe_readiness if state is not None else "unknown"
    preferred_adapter = state.preferred_adapter if state is not None else None
    preferred_adapter_url = state.preferred_adapter_url if state is not None else None

    effective_adapter = source.source_type
    if state is not None:
        if preferred_adapter and _capability_supports_adapter(state, preferred_adapter):
            effective_adapter = preferred_adapter
        elif _capability_supports_adapter(state, source.source_type):
            effective_adapter = source.source_type
        else:
            for adapter in ("rss", "news_sitemap", "scraping", "ai_research"):
                if _capability_supports_adapter(state, adapter):
                    effective_adapter = adapter
                    break

    effective_url = (
        preferred_adapter_url
        if preferred_adapter_url and effective_adapter == preferred_adapter
        else source.url
    )

    return SourceCapability(
        source_key=source.key,
        source_title=source.title,
        configured_source_type=source.source_type,
        configured_url=source.url,
        preferred_adapter=preferred_adapter,
        preferred_adapter_url=preferred_adapter_url,
        effective_adapter=effective_adapter,
        effective_url=effective_url,
        readiness=readiness,
        supports_rss=state.supports_rss if state is not None else False,
        supports_news_sitemap=state.supports_news_sitemap if state is not None else False,
        supports_sitemap=state.supports_sitemap if state is not None else False,
        supports_scraping=state.supports_scraping if state is not None else False,
        full_text_ok=state.last_probe_full_text_ok if state is not None else False,
        lead_ok=state.last_probe_lead_ok if state is not None else False,
        tags_count=state.last_probe_tags_count if state is not None else 0,
        sample_title=state.last_probe_sample_title if state is not None else None,
        sample_url=state.last_probe_sample_url if state is not None else None,
    )


@app.post("/api/v1/dev/reset", response_model=ResetResponse)
def reset_dev_database() -> ResetResponse:
    repository.reset_runtime_data()
    repository.sync_news_ai_review_flags()
    return ResetResponse(cleared=True)
