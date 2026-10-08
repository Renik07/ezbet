from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from typing import Optional
from fastapi import (
    Query,
    Request,
)
from .auth import require_admin_api_token as _require_admin_api_token
from .config import get_openai_settings
from .editorial import run_editorial_cycle
from .ingestion import build_importance_score_breakdown
from .models import (
    AiUsageSummaryResponse,
    ContentPlanListResponse,
    ContentPlanRunResponse,
    DraftArticleListResponse,
    EditorialStatusResponse,
    EditorialRunResponse,
    EditorReviewListResponse,
    GuideTopicListResponse,
    PromptConfigCreateRequest,
    PromptCleanupResponse,
    PromptConfigListResponse,
    PromptStatusUpdateRequest,
    PipelineRunListResponse,
    RawItemListResponse,
    RawItemPreviewListResponse,
    RawItem,
    RawItemPreview,
    ResetResponse,
    SourceItem,
)
from .planner import run_content_planner
from . import runtime
from .pipeline_logging import (
    _current_ingest_started_at,
    _duration_ms,
    _log_pipeline_event,
    _run_id,
)


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


def ai_usage_summary(
    request: Request,
    days: int = Query(default=14, ge=1, le=90),
) -> AiUsageSummaryResponse:
    _require_admin_api_token(request)
    items, totals = runtime.repository.list_ai_usage_summary(days=days)
    return AiUsageSummaryResponse(items=items, totals=totals, days=days)


def list_guide_topics(
    limit: int = Query(default=50, ge=1, le=800),
    status: Optional[str] = Query(default=None),
) -> GuideTopicListResponse:
    return GuideTopicListResponse(items=runtime.repository.list_guide_topics(limit=limit, status=status))


def list_raw_items(limit: int = Query(default=50, ge=1, le=200)) -> RawItemListResponse:
    items = [_with_score_breakdown(item) for item in runtime.repository.list_raw_items(limit)]
    return RawItemListResponse(items=items)


def list_raw_item_previews(
    limit: int = Query(default=50, ge=1, le=200),
    scope: str = Query(default="latest"),
) -> RawItemPreviewListResponse:
    if scope == "latest_ingest":
        current_ingest_started_at = _current_ingest_started_at()
        raw_items = (
            runtime.repository.list_raw_item_previews_since(current_ingest_started_at, limit)
            if current_ingest_started_at
            else []
        )
    else:
        raw_items = runtime.repository.list_raw_item_previews(limit)

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


def list_pipeline_runs(limit: int = Query(default=20, ge=1, le=100)) -> PipelineRunListResponse:
    return PipelineRunListResponse(items=runtime.repository.list_pipeline_runs(limit))


def list_content_plan(
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
) -> ContentPlanListResponse:
    return ContentPlanListResponse(items=runtime.repository.list_content_plan(limit=limit, status=status))


def run_planner(limit: int = Query(default=6, ge=1, le=20)) -> ContentPlanRunResponse:
    items = run_content_planner(runtime.repository, limit=limit, since=None)
    return ContentPlanRunResponse(planned=len(items), items=items)


def list_prompts(agent_key: Optional[str] = Query(default=None)) -> PromptConfigListResponse:
    return PromptConfigListResponse(items=runtime.repository.list_prompt_configs(agent_key))


def create_prompt_version(payload: PromptConfigCreateRequest) -> PromptConfigListResponse:
    prompt = runtime.repository.create_prompt_version(
        agent_key=payload.agent_key,
        name=payload.name,
        system_prompt=payload.system_prompt,
        user_prompt_template=payload.user_prompt_template,
        model=payload.model,
        notes=payload.notes,
        activate=payload.activate,
    )
    return PromptConfigListResponse(items=[prompt])


def update_prompt_status(prompt_id: str, payload: PromptStatusUpdateRequest) -> PromptConfigListResponse:
    prompt = runtime.repository.set_prompt_status(prompt_id, payload.status)
    return PromptConfigListResponse(items=[prompt])


def cleanup_prompt_versions() -> PromptCleanupResponse:
    deleted_count = runtime.repository.delete_archived_prompt_versions()
    return PromptCleanupResponse(deleted_count=deleted_count)


def list_drafts(
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    review_status: Optional[str] = Query(default=None, alias="reviewStatus"),
) -> DraftArticleListResponse:
    return DraftArticleListResponse(
        items=runtime.repository.list_drafts(limit=limit, status=status, review_status=review_status)
    )


def list_reviews(limit: int = Query(default=20, ge=1, le=100)) -> EditorReviewListResponse:
    return EditorReviewListResponse(items=runtime.repository.list_reviews(limit))


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
        drafts, reviews = run_editorial_cycle(runtime.repository, limit=limit, since=None)
        published_count = len([draft for draft in drafts if draft.status == "published"])
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        runtime.repository.record_pipeline_run(
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
        runtime.repository.record_pipeline_run(
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


def reset_dev_database() -> ResetResponse:
    runtime.repository.reset_runtime_data()
    runtime.repository.sync_news_ai_review_flags()
    return ResetResponse(cleared=True)

