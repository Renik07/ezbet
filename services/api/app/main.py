from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from .ai_client import OpenAIEditorialClient
from .config import get_openai_settings
from .editorial import default_prompt_configs, run_editorial_cycle
from .ingestion import (
    fetch_remote_document,
    ingest_sources as collect_source_items,
    ingest_sources_with_results,
    probe_source,
    raw_items_to_news,
)
from .models import (
    ArticleResponse,
    ContentPlanListResponse,
    ContentPlanRunResponse,
    DraftArticleListResponse,
    EditorialStatusResponse,
    EditorialRunResponse,
    EditorReviewListResponse,
    IngestResponse,
    NewsListResponse,
    PromptConfigCreateRequest,
    PromptConfigListResponse,
    PromptStatusUpdateRequest,
    RawItemListResponse,
    RawItemPreviewListResponse,
    ResetResponse,
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


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/editorial/status", response_model=EditorialStatusResponse)
def editorial_status() -> EditorialStatusResponse:
    settings = get_openai_settings()
    return EditorialStatusResponse(
        openai_enabled=settings.enabled,
        openai_model=settings.model,
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SourceListResponse(items=repository.list_source_configs())


@app.post("/api/v1/sources/{source_key}/delete", response_model=SourceListResponse)
def delete_source(source_key: str) -> SourceListResponse:
    repository.delete_source_config(source_key)
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
    return _probe_source_item(source, persist=False)


@app.post("/api/v1/sources/{source_key}/probe", response_model=SourceProbeResponse)
def probe_source_config(source_key: str) -> SourceProbeResponse:
    source = repository.get_source_config(source_key)
    return _probe_source_item(source, persist=True)


def _probe_source_item(source: SourceItem, *, persist: bool) -> SourceProbeResponse:
    result = probe_source(source)
    if (
        result.ok
        and result.readiness not in {"ready", "ready_ai"}
    ):
        ai_client = OpenAIEditorialClient()
        if ai_client.enabled:
            probe_candidates = [
                item for item in collect_source_items([source], limit=5) if item.url
            ][:5]
            for candidate in probe_candidates:
                html = fetch_remote_document(candidate.url, timeout=10)
                if not html:
                    continue
                ai_enrichment = ai_client.extract_article_enrichment(
                    url=candidate.url,
                    source_title=source.title,
                    raw_title=candidate.title or result.sample_title or source.title,
                    raw_summary=candidate.summary,
                    html=html,
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
                        "но AI fallback успешно извлёк full text у одной из sample-новостей."
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
                        "AI fallback смог поднять только часть enrichment-данных."
                    )
    if persist:
        repository.record_source_probe(
            source,
            ok=result.ok,
            item_count=result.item_count,
            message=result.message,
            readiness=result.readiness,
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
        full_text_ok=result.full_text_ok,
        lead_ok=result.lead_ok,
        tags_count=result.tags_count,
        sample_title=result.sample_title,
        sample_url=result.sample_url,
    )


@app.get("/api/v1/source-states", response_model=SourceSyncStateListResponse)
def list_source_states() -> SourceSyncStateListResponse:
    return SourceSyncStateListResponse(items=repository.list_source_sync_states())


@app.get("/api/v1/raw-items", response_model=RawItemListResponse)
def list_raw_items(limit: int = Query(default=50, ge=1, le=200)) -> RawItemListResponse:
    return RawItemListResponse(items=repository.list_raw_items(limit))


@app.get("/api/v1/raw-items/preview", response_model=RawItemPreviewListResponse)
def list_raw_item_previews(limit: int = Query(default=50, ge=1, le=200)) -> RawItemPreviewListResponse:
    return RawItemPreviewListResponse(items=repository.list_raw_item_previews(limit))


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
    drafts, reviews = run_editorial_cycle(repository, limit=limit)
    return EditorialRunResponse(generated=len(drafts), reviewed=len(reviews), drafts=drafts)


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


def _run_source_ingestion(limit: Optional[int], *, per_source: bool = False) -> IngestResponse:
    sources = repository.list_active_sources()
    ai_search_prompt = repository.get_active_prompt("ai_search")
    raw_items, source_results = ingest_sources_with_results(
        sources,
        repository.get_source_sync_state_map(),
        limit=limit,
        limit_per_source=per_source,
        ai_search_prompt=ai_search_prompt,
    )
    inserted_raw_items = repository.insert_raw_items(raw_items)
    for result in source_results:
        source_items = [item for item in raw_items if item.source_key == result.source.key]
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
    return IngestResponse(
        ingested=len(raw_items),
        published=len(published),
        items=published,
        raw_items=inserted_raw_items,
    )


@app.post("/api/v1/dev/reset", response_model=ResetResponse)
def reset_dev_database() -> ResetResponse:
    repository.reset_runtime_data()
    repository.sync_news_ai_review_flags()
    return ResetResponse(cleared=True)
