from __future__ import annotations

import json
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from html.parser import HTMLParser
from urllib.parse import (
    urljoin,
    urlsplit,
    urlunsplit,
)
from .models import (
    RawItem,
    SourceItem,
)
from .ingestion_network import _fetch_remote_document
from .ingestion_scoring import _build_raw_item
from .ingestion_text import (
    _container_score,
    _extract_time_hint,
    _looks_like_category_label,
    _looks_like_listing_title,
    _looks_like_story_title,
    _normalize_whitespace,
    _try_parse_datetime,
)
from .ingestion_types import SourceFetchError
from .ingestion_urls import (
    _build_sovsport_news_article_url,
    _is_sovsport_articles_source,
    _is_sovsport_news_source,
    _looks_like_scraping_article_url,
    _normalize_candidate_url,
    _normalize_url,
)


def _parse_scraping_source(source: SourceItem, timeout: int) -> list[RawItem]:
    sovsport_news_items = _parse_sovsport_news_source(source, timeout=timeout)
    if sovsport_news_items:
        return sovsport_news_items

    sovsport_articles_items = _parse_sovsport_articles_source(source, timeout=timeout)
    if sovsport_articles_items:
        return sovsport_articles_items

    payload = _fetch_remote_document(source.url, timeout)

    parser = _ScrapingDocumentParser(source.url)
    try:
        parser.feed(payload)
        parser.close()
    except ValueError:
        return []

    fetched_at = datetime.now(timezone.utc)
    items: list[RawItem] = []

    for index, candidate in enumerate(parser.candidates):
        if _looks_like_listing_title(candidate.title):
            continue
        if not _looks_like_scraping_article_url(candidate.url):
            continue
        published = candidate.published_at or (fetched_at - timedelta(seconds=index))
        items.append(
            _build_raw_item(
                source=source,
                payload=payload,
                fetched_at=fetched_at,
                external_id=candidate.url,
                title=candidate.title,
                summary=candidate.summary,
                url=candidate.url,
                published=published,
            )
        )

    if items:
        return items

    fallback_title = parser.og_title or parser.page_title or source.title
    fallback_summary = parser.og_description or parser.meta_description or fallback_title
    canonical_url = parser.canonical_url or source.url
    if not fallback_title or _looks_like_listing_title(fallback_title) or not _looks_like_scraping_article_url(canonical_url):
        return []

    return [
        _build_raw_item(
            source=source,
            payload=payload,
            fetched_at=fetched_at,
            external_id=canonical_url,
            title=fallback_title,
            summary=fallback_summary,
            url=canonical_url,
            published=fetched_at,
        )
    ]


def _parse_sovsport_articles_source(source: SourceItem, *, timeout: int) -> list[RawItem]:
    if not _is_sovsport_articles_source(source):
        return []

    parts = urlsplit(source.url.strip())
    base_root = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    api_url = f"{base_root}/api/proxy/api/articles"
    try:
        payload = _fetch_remote_document(api_url, timeout)
        data = json.loads(payload)
    except (SourceFetchError, json.JSONDecodeError):
        return []

    records = data.get("data")
    if not isinstance(records, list):
        return []

    fetched_at = datetime.now(timezone.utc)
    items: list[RawItem] = []

    for record in records:
        if not isinstance(record, dict):
            continue
        slug = _normalize_whitespace(str(record.get("url") or ""))
        title = _normalize_whitespace(str(record.get("title") or ""))
        if not slug or not title:
            continue

        article_url = _normalize_url(urljoin(f"{base_root}/articles/", slug))
        if not article_url:
            continue

        summary = _normalize_whitespace(str(record.get("subTitle") or "")) or title
        published = _try_parse_datetime(str(record.get("publicPublishedAt") or "")) or fetched_at
        sport_category = record.get("sportCategory") if isinstance(record.get("sportCategory"), dict) else {}
        tags: list[str] = []
        category_name = _normalize_whitespace(str(sport_category.get("name") or ""))
        category_type = _normalize_whitespace(str(sport_category.get("typeId") or ""))
        if category_name:
            tags.append(category_name)
        if category_type and category_type not in {tag.lower() for tag in tags}:
            tags.append(category_type)

        items.append(
            _build_raw_item(
                source=source,
                payload=payload,
                fetched_at=fetched_at,
                external_id=article_url,
                title=title,
                summary=summary,
                lead=summary,
                source_title=source.title,
                source_url=article_url,
                url=article_url,
                published=published,
                tags=tags,
            )
        )

    items.sort(key=lambda item: (item.published_at, item.importance_score), reverse=True)
    return items


def _parse_sovsport_news_source(source: SourceItem, *, timeout: int) -> list[RawItem]:
    if not _is_sovsport_news_source(source):
        return []

    parts = urlsplit(source.url.strip())
    base_root = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    api_url = f"{base_root}/api/proxy/api/news-collection"
    try:
        payload = _fetch_remote_document(api_url, timeout)
        data = json.loads(payload)
    except (SourceFetchError, json.JSONDecodeError):
        return []

    records = data.get("data")
    if not isinstance(records, list):
        return []

    fetched_at = datetime.now(timezone.utc)
    items: list[RawItem] = []

    for record in records:
        if not isinstance(record, dict):
            continue
        slug = _normalize_whitespace(str(record.get("url") or ""))
        title = _normalize_whitespace(str(record.get("title") or ""))
        if not slug or not title:
            continue

        sport_category = record.get("sportCategory") if isinstance(record.get("sportCategory"), dict) else {}
        category_type = _normalize_whitespace(str(sport_category.get("typeId") or ""))
        article_url = _build_sovsport_news_article_url(base_root, category_type, slug)
        if not article_url:
            continue

        summary = _normalize_whitespace(str(record.get("subTitle") or "")) or title
        published = _try_parse_datetime(str(record.get("publicPublishedAt") or "")) or fetched_at
        tags: list[str] = []
        category_name = _normalize_whitespace(str(sport_category.get("name") or ""))
        if category_name:
            tags.append(category_name)
        if category_type and category_type.lower() not in {tag.lower() for tag in tags}:
            tags.append(category_type)

        items.append(
            _build_raw_item(
                source=source,
                payload=payload,
                fetched_at=fetched_at,
                external_id=article_url,
                title=title,
                summary=summary,
                lead=summary,
                source_title=source.title,
                source_url=article_url,
                url=article_url,
                published=published,
                tags=tags,
            )
        )

    items.sort(key=lambda item: (item.published_at, item.importance_score), reverse=True)
    return items


def _discover_ai_research_candidates_from_listing(
    source: SourceItem,
    *,
    timeout: int,
) -> list["SourceDiscoveryItem"]:
    try:
        payload = _fetch_remote_document(source.url, timeout)
    except SourceFetchError:
        return []

    parser = _ScrapingDocumentParser(source.url)
    try:
        parser.feed(payload)
        parser.close()
    except ValueError:
        return []

    from .ai_client import SourceDiscoveryItem

    items: list[SourceDiscoveryItem] = []
    for candidate in parser.candidates[:12]:
        items.append(
            SourceDiscoveryItem(
                title=candidate.title,
                summary=candidate.summary,
                url=candidate.url,
                published_at=candidate.published_at.isoformat() if candidate.published_at is not None else None,
                full_text=None,
                source_title=source.title,
                tags=[],
            )
        )

    return items


class _ScrapingCandidate:
    def __init__(
        self,
        url: str,
        title: str,
        summary: str,
        published_at: datetime | None = None,
    ) -> None:
        self.url = url
        self.title = title
        self.summary = summary
        self.published_at = published_at


class _ScrapingDocumentParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.base_host = urlsplit(base_url).netloc.lower()
        self.candidates: list[_ScrapingCandidate] = []
        self._seen_candidate_urls: set[str] = set()
        self._anchor_href: str | None = None
        self._anchor_title: str | None = None
        self._anchor_text_parts: list[str] = []
        self._anchor_context_score = 0
        self._anchor_published_at: datetime | None = None
        self._in_title_tag = False
        self._title_parts: list[str] = []
        self._container_scores: list[int] = [0]
        self._container_time_hints: list[datetime | None] = [None]
        self.page_title: str | None = None
        self.og_title: str | None = None
        self.meta_description: str | None = None
        self.og_description: str | None = None
        self.canonical_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        tag = tag.lower()
        self._container_scores.append(self._container_scores[-1] + _container_score(tag, attr_map))
        self._container_time_hints.append(_extract_time_hint(attr_map) or self._container_time_hints[-1])

        if tag == "title":
            self._in_title_tag = True
            return

        if tag == "a":
            self._anchor_href = attr_map.get("href") or None
            self._anchor_title = attr_map.get("title") or None
            self._anchor_text_parts = []
            self._anchor_context_score = self._container_scores[-1]
            self._anchor_published_at = self._container_time_hints[-1]
            return

        if tag == "link" and attr_map.get("rel", "").lower() == "canonical":
            href = attr_map.get("href")
            if href:
                self.canonical_url = urljoin(self.base_url, href)
            return

        if tag != "meta":
            return

        name = attr_map.get("name", "").lower()
        prop = attr_map.get("property", "").lower()
        content = _normalize_whitespace(attr_map.get("content", ""))
        if not content:
            return

        if name == "description":
            self.meta_description = content
        elif prop == "og:title":
            self.og_title = content
        elif prop == "og:description":
            self.og_description = content
        elif prop == "og:url":
            self.canonical_url = content

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        try:
            if tag == "title":
                self._in_title_tag = False
                title = _normalize_whitespace(" ".join(self._title_parts))
                if title:
                    self.page_title = title
                self._title_parts = []
                return

            if tag != "a" or self._anchor_href is None:
                return

            href = self._anchor_href
            title = _normalize_whitespace(" ".join(self._anchor_text_parts)) or _normalize_whitespace(
                self._anchor_title or ""
            )
            url = _normalize_candidate_url(self.base_url, href)
            self._anchor_href = None
            self._anchor_title = None
            self._anchor_text_parts = []
            published_at = self._anchor_published_at

            if not url or not title or not _looks_like_story_title(title):
                return
            if _looks_like_listing_title(title) or _looks_like_category_label(title):
                return
            if self._anchor_context_score < 1:
                return
            if urlsplit(url).netloc.lower() != self.base_host:
                return
            if not _looks_like_scraping_article_url(url):
                return
            if url in self._seen_candidate_urls:
                return

            self._seen_candidate_urls.add(url)
            self.candidates.append(
                _ScrapingCandidate(
                    url=url,
                    title=title,
                    summary=title,
                    published_at=published_at,
                )
            )
        finally:
            if self._container_scores:
                self._container_scores.pop()
            if self._container_time_hints:
                self._container_time_hints.pop()

    def handle_data(self, data: str) -> None:
        if self._in_title_tag:
            self._title_parts.append(data)
        if self._anchor_href is not None:
            self._anchor_text_parts.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._container_scores:
            self._container_scores.pop()
        if self._container_time_hints:
            self._container_time_hints.pop()

