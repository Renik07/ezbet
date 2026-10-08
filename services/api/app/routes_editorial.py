from __future__ import annotations

from typing import Optional
from fastapi import (
    Query,
    Request,
)
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
    ResetResponse,
)
from fastapi import APIRouter
from . import service_editorial

router = APIRouter()


@router.get("/api/v1/editorial/status", response_model=EditorialStatusResponse)
def editorial_status() -> EditorialStatusResponse:
    return service_editorial.editorial_status()


@router.get("/api/v1/ai-usage/summary", response_model=AiUsageSummaryResponse)
def ai_usage_summary(
    request: Request,
    days: int = Query(default=14, ge=1, le=90),
) -> AiUsageSummaryResponse:
    return service_editorial.ai_usage_summary(request=request, days=days)


@router.get("/api/v1/guides/topics", response_model=GuideTopicListResponse)
def list_guide_topics(
    limit: int = Query(default=50, ge=1, le=800),
    status: Optional[str] = Query(default=None),
) -> GuideTopicListResponse:
    return service_editorial.list_guide_topics(limit=limit, status=status)


@router.get("/api/v1/raw-items", response_model=RawItemListResponse)
def list_raw_items(limit: int = Query(default=50, ge=1, le=200)) -> RawItemListResponse:
    return service_editorial.list_raw_items(limit=limit)


@router.get("/api/v1/raw-items/preview", response_model=RawItemPreviewListResponse)
def list_raw_item_previews(
    limit: int = Query(default=50, ge=1, le=200),
    scope: str = Query(default="latest"),
) -> RawItemPreviewListResponse:
    return service_editorial.list_raw_item_previews(limit=limit, scope=scope)


@router.get("/api/v1/pipeline-runs", response_model=PipelineRunListResponse)
def list_pipeline_runs(limit: int = Query(default=20, ge=1, le=100)) -> PipelineRunListResponse:
    return service_editorial.list_pipeline_runs(limit=limit)


@router.get("/api/v1/content-plan", response_model=ContentPlanListResponse)
def list_content_plan(
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
) -> ContentPlanListResponse:
    return service_editorial.list_content_plan(limit=limit, status=status)


@router.post("/api/v1/content-plan/run", response_model=ContentPlanRunResponse)
def run_planner(limit: int = Query(default=6, ge=1, le=20)) -> ContentPlanRunResponse:
    return service_editorial.run_planner(limit=limit)


@router.get("/api/v1/prompts", response_model=PromptConfigListResponse)
def list_prompts(agent_key: Optional[str] = Query(default=None)) -> PromptConfigListResponse:
    return service_editorial.list_prompts(agent_key=agent_key)


@router.post("/api/v1/prompts", response_model=PromptConfigListResponse)
def create_prompt_version(payload: PromptConfigCreateRequest) -> PromptConfigListResponse:
    return service_editorial.create_prompt_version(payload=payload)


@router.post("/api/v1/prompts/{prompt_id}/status", response_model=PromptConfigListResponse)
def update_prompt_status(prompt_id: str, payload: PromptStatusUpdateRequest) -> PromptConfigListResponse:
    return service_editorial.update_prompt_status(prompt_id=prompt_id, payload=payload)


@router.post("/api/v1/prompts/cleanup", response_model=PromptCleanupResponse)
def cleanup_prompt_versions() -> PromptCleanupResponse:
    return service_editorial.cleanup_prompt_versions()


@router.get("/api/v1/drafts", response_model=DraftArticleListResponse)
def list_drafts(
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    review_status: Optional[str] = Query(default=None, alias="reviewStatus"),
) -> DraftArticleListResponse:
    return service_editorial.list_drafts(limit=limit, status=status, review_status=review_status)


@router.get("/api/v1/reviews", response_model=EditorReviewListResponse)
def list_reviews(limit: int = Query(default=20, ge=1, le=100)) -> EditorReviewListResponse:
    return service_editorial.list_reviews(limit=limit)


@router.post("/api/v1/editorial/run", response_model=EditorialRunResponse)
def run_editorial(limit: int = Query(default=2, ge=1, le=10)) -> EditorialRunResponse:
    return service_editorial.run_editorial(limit=limit)


@router.post("/api/v1/dev/reset", response_model=ResetResponse)
def reset_dev_database() -> ResetResponse:
    return service_editorial.reset_dev_database()


