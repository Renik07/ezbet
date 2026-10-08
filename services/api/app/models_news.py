from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    id: str
    title: str
    description: str
    category: str
    published_at: datetime = Field(serialization_alias="publishedAt")
    source: str
    link: Optional[str] = None
    status: str = "published"
    visibility: str = "public"
    ai_reviewed: bool = Field(default=False, serialization_alias="aiReviewed")
    article_slug: Optional[str] = Field(default=None, serialization_alias="articleSlug")


class Article(BaseModel):
    id: str
    slug: str
    news_item_id: str = Field(serialization_alias="newsItemId")
    raw_item_id: str = Field(serialization_alias="rawItemId")
    title: str
    lead: Optional[str] = None
    dek: str
    body: str
    category: str
    source_title: str = Field(serialization_alias="sourceTitle")
    source_url: Optional[str] = Field(default=None, serialization_alias="sourceUrl")
    tags: list[str] = Field(default_factory=list)
    published_at: datetime = Field(serialization_alias="publishedAt")
    ai_reviewed: bool = Field(default=True, serialization_alias="aiReviewed")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="createdAt",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="updatedAt",
    )


class NewsListResponse(BaseModel):
    items: list[NewsItem]
    total: int | None = None
    page: int | None = None


class NewsItemResponse(BaseModel):
    item: NewsItem


class ArticleResponse(BaseModel):
    item: Article

