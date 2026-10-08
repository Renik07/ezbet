from __future__ import annotations

from typing import Optional
from fastapi import (
    HTTPException,
    Query,
    Request,
)
from .auth import require_admin_api_token as _require_admin_api_token
from .models import (
    ArticleResponse,
    NewsListResponse,
    NewsItemResponse,
)
from . import runtime


def list_news(
    request: Request,
    query: Optional[str] = Query(default=None),
    ai_only: bool = Query(default=False, alias="aiOnly"),
    guide_only: bool = Query(default=False, alias="guideOnly"),
    include_hidden: bool = Query(default=False, alias="includeHidden"),
    limit: Optional[int] = Query(default=None, ge=1, le=100),
    page: Optional[int] = Query(default=None, ge=1),
) -> NewsListResponse:
    if include_hidden:
        _require_admin_api_token(request)

    page_meta: dict = {}
    items = runtime.repository.list(
        query, ai_only=ai_only, guide_only=guide_only,
        include_hidden=include_hidden, limit=limit, page=page, page_meta=page_meta,
    )
    return NewsListResponse(items=items, **page_meta)


def get_article(slug: str) -> ArticleResponse:
    article = runtime.repository.get_article_by_slug(slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleResponse(item=article)


def reflow_article_publication_times(
    request: Request,
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, int]:
    _require_admin_api_token(request)
    return {"updated": runtime.repository.reflow_public_published_at_for_articles(limit=limit)}


def hide_news_item(news_item_id: str, request: Request) -> NewsItemResponse:
    _require_admin_api_token(request)
    item = runtime.repository.set_news_visibility(news_item_id, "hidden")
    if item is None:
        raise HTTPException(status_code=404, detail="News item not found")
    return NewsItemResponse(item=item)


def unhide_news_item(news_item_id: str, request: Request) -> NewsItemResponse:
    _require_admin_api_token(request)
    item = runtime.repository.set_news_visibility(news_item_id, "public")
    if item is None:
        raise HTTPException(status_code=404, detail="News item not found")
    return NewsItemResponse(item=item)

