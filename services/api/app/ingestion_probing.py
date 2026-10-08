from __future__ import annotations

import re
from urllib.parse import (
    urlsplit,
    urlunsplit,
)
from .models import SourceItem
from .ingestion_article_extraction import extract_article_enrichment
from .ingestion_collection import _collect_source_items
from .ingestion_network import fetch_remote_document
from .ingestion_text import (
    _is_probe_usable_full_text,
    _is_usable_lead,
)
from .ingestion_types import (
    ArticleEnrichmentResult,
    SourceFetchError,
    SourceProbeResult,
)
from .ingestion_urls import _normalize_candidate_url


def probe_source(source: SourceItem, timeout: int = 10) -> SourceProbeResult:
    supports_rss, supports_news_sitemap, supports_sitemap, supports_scraping = _probe_support_flags(
        source.source_type,
        ok=False,
        item_count=0,
    )
    try:
        items = _collect_source_items(source, timeout=timeout)
    except SourceFetchError as exc:
        return SourceProbeResult(
            False,
            0,
            str(exc),
            "fetch_error",
            source.source_type,
            source.url,
            supports_rss,
            supports_news_sitemap,
            supports_sitemap,
            supports_scraping,
            False,
            None,
            False,
            0,
            None,
            None,
        )
    if not items:
        if source.source_type in {"news_sitemap", "sitemap"}:
            return SourceProbeResult(
                False,
                0,
                "Sitemap не прочитан или не вернул пригодных article URL.",
                "empty",
                source.source_type,
                source.url,
                supports_rss,
                supports_news_sitemap,
                supports_sitemap,
                supports_scraping,
                False,
                None,
                False,
                0,
                None,
                None,
            )
        if source.source_type == "scraping":
            return SourceProbeResult(False, 0, "Страница не прочитана или scraping-адаптер не нашел кандидатов.", "empty", source.source_type, source.url, supports_rss, supports_news_sitemap, supports_sitemap, supports_scraping, False, None, False, 0, None, None)
        return SourceProbeResult(False, 0, "Фид не прочитан или не вернул элементов.", "empty", source.source_type, source.url, supports_rss, supports_news_sitemap, supports_sitemap, supports_scraping, False, None, False, 0, None, None)

    supports_rss, supports_news_sitemap, supports_sitemap, supports_scraping = _probe_support_flags(
        source.source_type,
        ok=True,
        item_count=len(items),
    )

    if source.source_type == "ai_research":
        sample = next((item for item in items if item.url), items[0])
        full_text_ok = _is_probe_usable_full_text(sample.full_text, sample.title, sample.summary)
        full_text_method = "ai_search" if full_text_ok else None
        lead_ok = _is_usable_lead(sample.lead)
        tags_count = len(sample.tags)

        if full_text_ok:
            readiness = "ready_ai"
            message = f"Найдено {len(items)} элементов. AI search сразу извлёк пригодный full text у sample-новости."
        elif lead_ok or tags_count:
            readiness = "partial"
            message = f"Найдено {len(items)} элементов. AI search вернул кандидатов, но full text пока слабый."
        else:
            readiness = "feed_only"
            message = (
                f"Найдено {len(items)} элементов, но AI search не смог сразу извлечь пригодный full text "
                "у sample-новости."
            )

        return SourceProbeResult(
            True,
            len(items),
            message,
            readiness,
            source.source_type,
            source.url,
            supports_rss,
            supports_news_sitemap,
            supports_sitemap,
            supports_scraping,
            full_text_ok,
            full_text_method,
            lead_ok,
            tags_count,
            sample.title,
            sample.url,
        )

    samples = [item for item in items if item.url][:3] or items[:1]
    sample = samples[0]
    enrichment: ArticleEnrichmentResult | None = None
    full_text_ok = False
    full_text_method: str | None = None
    lead_ok = False
    tags_count = 0

    for candidate in samples:
        candidate_enrichment = extract_article_enrichment(candidate.url, timeout=timeout) if candidate.url else None
        candidate_full_text_ok = _is_probe_usable_full_text(
            candidate_enrichment.full_text if candidate_enrichment is not None else None,
            candidate.title,
            candidate.summary,
        )
        candidate_lead_ok = _is_usable_lead(candidate_enrichment.lead if candidate_enrichment is not None else None)
        candidate_tags_count = len(candidate_enrichment.tags) if candidate_enrichment else 0

        if candidate_full_text_ok:
            sample = candidate
            enrichment = candidate_enrichment
            full_text_ok = True
            full_text_method = "direct_parser"
            lead_ok = candidate_lead_ok
            tags_count = candidate_tags_count
            break

        if not lead_ok and (candidate_lead_ok or candidate_tags_count):
            sample = candidate
            enrichment = candidate_enrichment
            lead_ok = candidate_lead_ok
            tags_count = candidate_tags_count

    if full_text_ok:
        readiness = "ready"
        message = f"Найдено {len(items)} элементов. Full text у одной из sample-новостей успешно извлечён."
    elif lead_ok or tags_count:
        readiness = "partial"
        message = f"Найдено {len(items)} элементов. Источник частично годится для production-flow, но full text пока слабый."
    else:
        readiness = "feed_only"
        message = (
            f"Найдено {len(items)} элементов, но ни одна из sample-новостей не дала full text enrichment. "
            "Такой источник лучше не переводить в active до доработки extractor."
        )

    return SourceProbeResult(
        True,
        len(items),
        message,
        readiness,
        source.source_type,
        source.url,
        supports_rss,
        supports_news_sitemap,
        supports_sitemap,
        supports_scraping,
        full_text_ok,
        full_text_method,
        lead_ok,
        tags_count,
        sample.title,
        sample.url,
    )


def probe_source_auto(source: SourceItem, timeout: int = 10) -> SourceProbeResult:
    candidates = _build_auto_probe_candidates(source)
    best_result: SourceProbeResult | None = None
    supports = {
        "rss": False,
        "news_sitemap": False,
        "sitemap": False,
        "scraping": False,
    }

    for candidate in candidates:
        result = probe_source(candidate, timeout=timeout)
        supports["rss"] = supports["rss"] or result.supports_rss
        supports["news_sitemap"] = supports["news_sitemap"] or result.supports_news_sitemap
        supports["sitemap"] = supports["sitemap"] or result.supports_sitemap
        supports["scraping"] = supports["scraping"] or result.supports_scraping
        if best_result is None or _score_probe_result(result) > _score_probe_result(best_result):
            best_result = result
        if result.ok and result.readiness in {"ready", "ready_ai"}:
            result.supports_rss = supports["rss"]
            result.supports_news_sitemap = supports["news_sitemap"]
            result.supports_sitemap = supports["sitemap"]
            result.supports_scraping = supports["scraping"]
            return result

    if best_result is not None:
        best_result.supports_rss = supports["rss"]
        best_result.supports_news_sitemap = supports["news_sitemap"]
        best_result.supports_sitemap = supports["sitemap"]
        best_result.supports_scraping = supports["scraping"]
        return best_result

    return SourceProbeResult(
        False,
        0,
        "Автоопределение не нашло подходящий adapter для этого URL.",
        "empty",
        None,
        None,
        supports["rss"],
        supports["news_sitemap"],
        supports["sitemap"],
        supports["scraping"],
        False,
        None,
        False,
        0,
        None,
        None,
    )


def _score_probe_result(result: SourceProbeResult) -> tuple[int, int, int, int]:
    readiness_rank = {
        "ready_ai": 4,
        "ready": 3,
        "partial": 2,
        "feed_only": 1,
        "empty": 0,
        "fetch_error": -1,
    }.get(result.readiness, 0)
    adapter_rank = {
        "news_sitemap": 4,
        "rss": 3,
        "scraping": 1,
        "ai_research": 0,
        "sitemap": -1,
    }.get(result.resolved_source_type or "", 0)
    return (
        1 if result.ok else 0,
        readiness_rank,
        adapter_rank,
        result.item_count,
    )


def _probe_support_flags(source_type: str, *, ok: bool, item_count: int) -> tuple[bool, bool, bool, bool]:
    supported = ok and item_count > 0
    return (
        source_type == "rss" and supported,
        source_type == "news_sitemap" and supported,
        False,
        source_type == "scraping" and supported,
    )


def _build_auto_probe_candidates(source: SourceItem) -> list[SourceItem]:
    seen: set[tuple[str, str]] = set()
    candidates: list[SourceItem] = []

    def add_candidate(source_type: str, url: str) -> None:
        normalized_url = url.strip()
        if not normalized_url.startswith(("http://", "https://")):
            return
        key = (source_type, normalized_url)
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            SourceItem(
                key=source.key,
                title=source.title,
                url=normalized_url,
                category=source.category,
                source_type=source_type,
                status="draft",
                notes=source.notes,
            )
        )

    for candidate_url in _candidate_urls_for_news_sitemap(source.url):
        add_candidate("news_sitemap", candidate_url)
    for candidate_url in _candidate_urls_for_rss(source.url):
        add_candidate("rss", candidate_url)
    add_candidate("scraping", source.url)

    return candidates


def _candidate_urls_for_news_sitemap(url: str) -> list[str]:
    candidates = _build_candidate_urls(
        url,
        (
            "news-sitemap.xml",
            "news_sitemap.xml",
            "sitemap-news.xml",
            "sitemap_news.xml",
            "sitemap/news.xml",
            "sitemap/news/index.xml",
            "news.xml",
        ),
    )
    for item in _extract_sitemap_urls_from_robots(url):
        lowered = item.lower()
        if "news" in lowered and item not in candidates:
            candidates.insert(0, item)
    return candidates


def _candidate_urls_for_sitemap(url: str) -> list[str]:
    candidates = _build_candidate_urls(
        url,
        (
            "sitemap.xml",
            "sitemap_index.xml",
            "sitemap/news.xml",
            "post-sitemap.xml",
            "news.xml",
        ),
    )
    for item in _extract_sitemap_urls_from_robots(url):
        if item not in candidates:
            candidates.insert(0, item)
    return candidates


def _candidate_urls_for_rss(url: str) -> list[str]:
    candidates = _host_specific_rss_candidates(url) + _build_candidate_urls(
        url,
        (
            "rss",
            "rss.xml",
            "feed",
            "feed.xml",
            "news/rss",
            "rss/news",
            "feeds/news.xml",
        ),
    )
    html = fetch_remote_document(url, timeout=6)
    if html:
        autodiscovered = _extract_feed_links_from_html(url, html)
        for item in autodiscovered:
            if item not in candidates:
                candidates.insert(0, item)
    return candidates


def _host_specific_rss_candidates(url: str) -> list[str]:
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return []

    host = parts.netloc.lower()
    base_root = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    candidates: list[str] = []

    if "sport-express.ru" in host:
        candidates.extend(
            [
                f"{base_root}/services/materials/news/se/",
                f"{base_root}/services/materials/news/se",
            ]
        )

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(candidate)
    return unique


def _build_candidate_urls(url: str, suffixes: tuple[str, ...]) -> list[str]:
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return [url.strip()]
    candidates: list[str] = []
    for base_url in _auto_probe_base_urls(url):
        candidates.append(base_url)
        base_parts = urlsplit(base_url)
        base_root = urlunsplit((base_parts.scheme, base_parts.netloc, "", "", ""))
        base_path = base_parts.path.strip("/")
        for suffix in suffixes:
            candidates.append(f"{base_root}/{suffix}")
            if base_path:
                candidates.append(f"{base_root}/{base_path.rstrip('/')}/{suffix}")

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(candidate)
    return unique


def _auto_probe_base_urls(url: str) -> list[str]:
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return [url.strip()]

    bases: list[str] = []

    def add_base(path: str) -> None:
        candidate = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        if candidate not in bases:
            bases.append(candidate)

    normalized_path = parts.path or "/"
    add_base(normalized_path)

    section_path = _section_probe_path(normalized_path)
    if section_path != normalized_path:
        add_base(section_path)

    add_base("/")
    return bases


def _section_probe_path(path: str) -> str:
    cleaned = path or "/"
    if cleaned.endswith(".xml"):
        return cleaned

    stripped = cleaned.rstrip("/")
    if not stripped:
        return "/"

    article_like = (
        stripped.endswith(".html")
        or stripped.endswith(".htm")
        or stripped.split("/")[-1].isdigit()
        or "/news/" in stripped
    )
    if article_like and "/" in stripped:
        parent = stripped.rsplit("/", 1)[0]
        return parent if parent.startswith("/") else f"/{parent}"
    return cleaned


def _extract_sitemap_urls_from_robots(url: str) -> list[str]:
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return []

    robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    robots = fetch_remote_document(robots_url, timeout=6)
    if not robots:
        return []

    matches = re.findall(r"(?im)^sitemap:\s*(https?://\S+)\s*$", robots)
    urls: list[str] = []
    for item in matches:
        normalized = item.strip()
        if normalized and normalized not in urls:
            urls.append(normalized)
    return urls


def _extract_feed_links_from_html(base_url: str, html: str) -> list[str]:
    matches = re.findall(
        r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]+href=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    urls: list[str] = []
    for href in matches:
        normalized = _normalize_candidate_url(base_url, href)
        if normalized and normalized not in urls:
            urls.append(normalized)
    return urls

