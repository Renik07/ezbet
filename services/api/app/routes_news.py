from __future__ import annotations

from typing import Optional
from fastapi import (
    Query,
    Request,
)
from .models import (
    ArticleResponse,
    NewsListResponse,
    NewsItemResponse,
)
from fastapi import APIRouter
from . import service_news

router = APIRouter()


@router.get("/api/v1/news", response_model=NewsListResponse)
def list_news(
    request: Request,
    query: Optional[str] = Query(default=None),
    ai_only: bool = Query(default=False, alias="aiOnly"),
    guide_only: bool = Query(default=False, alias="guideOnly"),
    include_hidden: bool = Query(default=False, alias="includeHidden"),
    limit: Optional[int] = Query(default=None, ge=1, le=100),
    page: Optional[int] = Query(default=None, ge=1),
) -> NewsListResponse:
    return service_news.list_news(request=request, query=query, ai_only=ai_only, guide_only=guide_only, include_hidden=include_hidden, limit=limit, page=page)


@router.get("/api/v1/articles/{slug}", response_model=ArticleResponse)
def get_article(slug: str) -> ArticleResponse:
    return service_news.get_article(slug=slug)


@router.post("/api/v1/articles/reflow-publication-times")
def reflow_article_publication_times(
    request: Request,
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, int]:
    return service_news.reflow_article_publication_times(request=request, limit=limit)


@router.post("/api/v1/news/{news_item_id:path}/hide", response_model=NewsItemResponse)
def hide_news_item(news_item_id: str, request: Request) -> NewsItemResponse:
    return service_news.hide_news_item(news_item_id=news_item_id, request=request)


@router.post("/api/v1/news/{news_item_id:path}/unhide", response_model=NewsItemResponse)
def unhide_news_item(news_item_id: str, request: Request) -> NewsItemResponse:
    return service_news.unhide_news_item(news_item_id=news_item_id, request=request)


