from __future__ import annotations

import re
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from urllib.parse import urlsplit
from xml.etree import ElementTree
from .models import (
    RawItem,
    SourceItem,
)
from .ingestion_network import _fetch_remote_document
from .ingestion_scoring import _build_raw_item
from .ingestion_text import (
    _find_child,
    _find_child_text,
    _normalize_whitespace,
    _serialize_sitemap_payload,
    _split_meta_values,
    _try_parse_datetime,
    _xml_local_name,
)
from .ingestion_types import (
    CHAMPIONAT_ALLOWED_TOP_LEVEL_SECTIONS,
    CHAMPIONAT_BLOCKED_TOP_LEVEL_SECTIONS,
    SourceFetchError,
)
from .ingestion_urls import (
    _looks_like_generic_sitemap_article_url,
    _normalize_url,
    _title_from_url,
)


def _parse_news_sitemap_source(source: SourceItem, timeout: int) -> list[RawItem]:
    payload = _fetch_remote_document(source.url, timeout)

    encoded_payload = payload.encode("utf-8", errors="ignore")
    try:
        root = ElementTree.fromstring(encoded_payload)
    except ElementTree.ParseError:
        return []

    discovered = _parse_news_sitemap_document(
        root,
        source=source,
        timeout=timeout,
        max_child_sitemaps=6,
    )
    if not discovered:
        return []

    fetched_at = datetime.now(timezone.utc)
    payload_summary = _serialize_sitemap_payload(source, "news_sitemap", len(discovered))
    items: list[RawItem] = []

    for index, entry in enumerate(discovered):
        published = entry["published_at"] or (fetched_at - timedelta(seconds=index))
        title = entry["title"] or entry["url"]
        tags = entry["tags"]
        summary = entry["summary"] or (", ".join(tags[:3]) if tags else title)
        items.append(
            _build_raw_item(
                source=source,
                payload=payload_summary,
                fetched_at=fetched_at,
                external_id=entry["url"],
                title=title,
                summary=summary,
                lead=summary,
                source_title=entry["source_title"],
                source_url=entry["url"],
                url=entry["url"],
                published=published,
                tags=tags,
            )
        )

    items.sort(key=lambda item: (item.published_at, item.importance_score), reverse=True)
    return items


def _parse_sitemap_source(source: SourceItem, timeout: int) -> list[RawItem]:
    payload = _fetch_remote_document(source.url, timeout)

    encoded_payload = payload.encode("utf-8", errors="ignore")
    try:
        root = ElementTree.fromstring(encoded_payload)
    except ElementTree.ParseError:
        return []

    discovered = _parse_generic_sitemap_document(
        root,
        source=source,
        timeout=timeout,
        max_child_sitemaps=8,
    )
    if not discovered:
        return []

    fetched_at = datetime.now(timezone.utc)
    payload_summary = _serialize_sitemap_payload(source, "sitemap", len(discovered))
    items: list[RawItem] = []

    for index, entry in enumerate(discovered):
        published = entry["published_at"] or (fetched_at - timedelta(seconds=index))
        title = entry["title"] or entry["url"]
        summary = entry["summary"] or title
        items.append(
            _build_raw_item(
                source=source,
                payload=payload_summary,
                fetched_at=fetched_at,
                external_id=entry["url"],
                title=title,
                summary=summary,
                lead=summary,
                source_title=entry["source_title"],
                source_url=entry["url"],
                url=entry["url"],
                published=published,
                tags=entry["tags"],
            )
        )

    items.sort(key=lambda item: (item.published_at, item.importance_score), reverse=True)
    return items


def _parse_news_sitemap_document(
    root: ElementTree.Element,
    *,
    source: SourceItem,
    timeout: int,
    max_child_sitemaps: int,
) -> list[dict[str, object]]:
    root_name = _xml_local_name(root.tag)
    if root_name == "sitemapindex":
        nested_entries: list[dict[str, object]] = []
        seen_urls: set[str] = set()
        for loc, _ in _sorted_sitemapindex_children(root):
            if not loc or loc in seen_urls:
                continue
            seen_urls.add(loc)
            try:
                nested_payload = _fetch_remote_document(loc, timeout)
                nested_root = ElementTree.fromstring(nested_payload.encode("utf-8", errors="ignore"))
            except (SourceFetchError, ElementTree.ParseError):
                continue
            nested_entries.extend(
                _parse_news_sitemap_document(
                    nested_root,
                    source=source,
                    timeout=timeout,
                    max_child_sitemaps=0,
                )
            )
            if len(seen_urls) >= max_child_sitemaps:
                break
        return nested_entries

    if root_name != "urlset":
        return []

    entries: list[dict[str, object]] = []
    seen_urls: set[str] = set()

    for node in root:
        if _xml_local_name(node.tag) != "url":
            continue

        loc = _find_child_text(node, {"loc"})
        normalized_url = _normalize_url(loc) if loc else None
        if not normalized_url or normalized_url in seen_urls:
            continue
        if not _is_allowed_news_sitemap_article_url(source, normalized_url):
            continue

        news_node = _find_child(node, {"news"})
        title = _find_child_text(news_node, {"title"}) if news_node is not None else None
        published_at = _try_parse_datetime(_find_child_text(news_node, {"publication_date"}) or "")
        if published_at is None:
            published_at = _try_parse_datetime(_find_child_text(node, {"lastmod"}) or "")

        publication_node = _find_child(news_node, {"publication"}) if news_node is not None else None
        publication_name = _find_child_text(publication_node, {"name"}) if publication_node is not None else None

        keywords = _find_child_text(news_node, {"keywords"}) if news_node is not None else None
        tags = _split_meta_values(keywords or "")
        fallback_title = _title_from_url(normalized_url)
        resolved_title = _normalize_whitespace(title or fallback_title or normalized_url)
        summary = resolved_title or (", ".join(tags[:3]) if tags else normalized_url)

        seen_urls.add(normalized_url)
        entries.append(
            {
                "url": normalized_url,
                "title": resolved_title,
                "summary": _normalize_whitespace(summary),
                "published_at": published_at,
                "source_title": _normalize_whitespace(publication_name or source.title) or source.title,
                "tags": tags,
            }
        )

    return entries


def _is_allowed_news_sitemap_article_url(source: SourceItem, url: str) -> bool:
    if _is_championat_source(source):
        return _is_allowed_championat_news_url(url)
    return True


def _is_championat_source(source: SourceItem) -> bool:
    host = urlsplit(source.url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host == "championat.com" or host.endswith(".championat.com")


def _is_allowed_championat_news_url(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if "championat.com" not in host:
        return True

    segments = [segment for segment in parts.path.strip("/").lower().split("/") if segment]
    if not segments:
        return False

    top_level = segments[0]
    if top_level in CHAMPIONAT_BLOCKED_TOP_LEVEL_SECTIONS:
        return False
    if top_level in CHAMPIONAT_ALLOWED_TOP_LEVEL_SECTIONS:
        return True

    # Championship article urls often start with the sports section.
    # Unknown top-level sections are treated conservatively and skipped.
    return False


def _parse_generic_sitemap_document(
    root: ElementTree.Element,
    *,
    source: SourceItem,
    timeout: int,
    max_child_sitemaps: int,
) -> list[dict[str, object]]:
    root_name = _xml_local_name(root.tag)
    if root_name == "sitemapindex":
        nested_entries: list[dict[str, object]] = []
        seen_sitemaps: set[str] = set()
        for loc, _ in _sorted_sitemapindex_children(root):
            normalized_loc = _normalize_url(loc) if loc else None
            if not normalized_loc or normalized_loc in seen_sitemaps:
                continue
            seen_sitemaps.add(normalized_loc)
            try:
                nested_payload = _fetch_remote_document(normalized_loc, timeout)
                nested_root = ElementTree.fromstring(nested_payload.encode("utf-8", errors="ignore"))
            except (SourceFetchError, ElementTree.ParseError):
                continue
            nested_entries.extend(
                _parse_generic_sitemap_document(
                    nested_root,
                    source=source,
                    timeout=timeout,
                    max_child_sitemaps=0,
                )
            )
            if len(seen_sitemaps) >= max_child_sitemaps:
                break
        return nested_entries

    if root_name != "urlset":
        return []

    entries: list[dict[str, object]] = []
    seen_urls: set[str] = set()

    for node in root:
        if _xml_local_name(node.tag) != "url":
            continue

        loc = _find_child_text(node, {"loc"})
        normalized_url = _normalize_url(loc) if loc else None
        if not normalized_url or normalized_url in seen_urls:
            continue
        if not _looks_like_generic_sitemap_article_url(normalized_url):
            continue

        lastmod = _find_child_text(node, {"lastmod"})
        published_at = _try_parse_datetime(lastmod or "")
        title = _title_from_url(normalized_url)
        summary = title or normalized_url

        seen_urls.add(normalized_url)
        entries.append(
            {
                "url": normalized_url,
                "title": title,
                "summary": summary,
                "published_at": published_at,
                "source_title": source.title,
                "tags": [],
            }
        )

    return entries


def _sorted_sitemapindex_children(root: ElementTree.Element) -> list[tuple[str, datetime | None]]:
    children: list[tuple[str, datetime | None]] = []
    for node in root:
        if _xml_local_name(node.tag) != "sitemap":
            continue
        loc = _find_child_text(node, {"loc"})
        if not loc:
            continue
        lastmod = _try_parse_datetime(_find_child_text(node, {"lastmod"}) or "")
        children.append((loc, lastmod))

    children.sort(
        key=lambda item: (
            item[1] is not None,
            item[1] or datetime.min.replace(tzinfo=timezone.utc),
            _extract_sitemap_order_hint(item[0]),
            item[0],
        ),
        reverse=True,
    )
    return children


def _extract_sitemap_order_hint(url: str) -> int:
    numbers = re.findall(r"\d+", url)
    if not numbers:
        return -1
    try:
        return int(numbers[-1])
    except ValueError:
        return -1

