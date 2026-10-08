from __future__ import annotations

import logging
from dataclasses import dataclass
from socket import timeout as SocketTimeout
from urllib.error import (
    HTTPError,
    URLError,
)


@dataclass
class DraftGenerationResult:
    title: str
    dek: str
    body: str
    model: str
    generation_mode: str


@dataclass
class GuideResearchResult:
    brief: str
    model: str
    generation_mode: str


@dataclass
class ReviewGenerationResult:
    decision: str
    summary: str
    notes: str
    revised_title: str | None
    revised_dek: str | None
    revised_body: str | None
    model: str
    generation_mode: str


@dataclass
class PlannerRerankItem:
    raw_item_id: str
    score: int
    reason: str


@dataclass
class SourceDiscoveryItem:
    title: str
    summary: str
    url: str
    published_at: str | None
    full_text: str | None
    source_title: str | None
    tags: list[str]


@dataclass
class ResolvedArticleTarget:
    url: str
    published_at: str | None
    source_title: str | None


@dataclass
class ArticleExtractionResult:
    full_text: str | None
    lead: str | None
    tags: list[str]
    source_url: str | None
    source_title: str | None
    reference_urls: list[str]
    used_web_search: bool
    model: str
    generation_mode: str


LLM_REQUEST_EXCEPTIONS = (ValueError, HTTPError, URLError, TimeoutError, SocketTimeout, OSError)


LLM_TRANSIENT_EXCEPTIONS = (URLError, TimeoutError, SocketTimeout, OSError)


logger = logging.getLogger("uvicorn.error")

