from __future__ import annotations

import re
from urllib.parse import (
    parse_qsl,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)
from .models import SourceItem
from .ingestion_types import (
    BLOCKED_URL_SEGMENTS,
    PREFERRED_URL_SEGMENTS,
)


def _make_dedupe_key(url: str | None, title: str) -> str:
    if url:
        normalized_url = _normalize_url(url)
        if normalized_url:
            return normalized_url

    normalized_title = " ".join(title.lower().split())
    return normalized_title[:240]


def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return url.strip().lower()

    tracking_keys = {"gclid", "fbclid", "yclid", "msclkid", "_ga", "_gl"}
    query = urlencode(sorted(
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in tracking_keys
    ))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def _normalize_candidate_url(base_url: str, href: str) -> str | None:
    normalized = _normalize_url(urljoin(base_url, href))
    parts = urlsplit(normalized)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return normalized


def _looks_like_scraping_article_url(url: str) -> bool:
    parts = urlsplit(url)
    path = parts.path.rstrip("/").lower()
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False

    leaf = segments[-1]
    if leaf == "news":
        return False

    if len(segments) >= 2 and segments[-2] == "news" and not re.search(r"\d", leaf):
        return False

    if any(segment in BLOCKED_URL_SEGMENTS for segment in segments):
        return False

    if leaf in {
        "football",
        "hockey",
        "tennis",
        "basketball",
        "boxing",
        "mma",
        "bobsleigh",
        "skeleton",
        "luge",
        "athletics",
        "f1",
        "news",
    }:
        return False

    if re.search(r"\.(html?|php|aspx?)$", leaf):
        return True
    if re.search(r"\d", leaf):
        return True
    if leaf.count("-") >= 3 or leaf.count("_") >= 3:
        return True

    if len(segments) >= 3 and segments[-2] in {"news", "article", "articles", "story", "stories"}:
        return leaf.count("-") >= 2 or leaf.count("_") >= 2

    return False


def _looks_like_generic_sitemap_article_url(url: str) -> bool:
    parts = urlsplit(url)
    path = parts.path.rstrip("/").lower()
    if not path:
        return False

    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    if any(segment in BLOCKED_URL_SEGMENTS for segment in segments):
        return False

    leaf = segments[-1]
    if leaf in {
        "index",
        "home",
        "main",
        "news",
        "sport",
        "sports",
        "football",
        "hockey",
        "tennis",
        "basketball",
        "cookies",
        "cookie",
        "agreement",
        "advertisement",
        "privacy",
        "terms",
    }:
        return False

    if re.search(r"\.(html?|php|aspx?)$", leaf):
        return True
    if re.search(r"\d", leaf):
        return True
    if leaf.count("-") >= 3 or leaf.count("_") >= 3:
        return True

    if len(segments) >= 3 and any(segment in PREFERRED_URL_SEGMENTS for segment in segments[:-1]):
        if leaf.count("-") >= 2 or leaf.count("_") >= 2:
            return True

    if len(segments) >= 4 and all(re.fullmatch(r"\d{1,4}", segment) for segment in segments[-4:-1]):
        return len(re.findall(r"[a-zа-я0-9]+", leaf, flags=re.IGNORECASE)) >= 3

    return False


def _title_from_url(url: str) -> str:
    path = urlsplit(url).path.strip("/")
    if not path:
        return url
    slug = path.split("/")[-1]
    slug = re.sub(r"\.(html|htm|php|aspx?)$", "", slug, flags=re.IGNORECASE)
    slug = slug.replace("-", " ").replace("_", " ").strip()
    slug = re.sub(r"\s+", " ", slug)
    if not slug:
        return url
    return slug[:1].upper() + slug[1:]


def _is_sovsport_articles_source(source: SourceItem) -> bool:
    parts = urlsplit(source.url.strip())
    host = parts.netloc.lower()
    path = parts.path.rstrip("/").lower()
    return (
        "sovsport.ru" in host
        and source.source_type == "scraping"
        and path == "/articles"
    )


def _is_sovsport_news_source(source: SourceItem) -> bool:
    parts = urlsplit(source.url.strip())
    host = parts.netloc.lower()
    path = parts.path.rstrip("/").lower()
    return (
        "sovsport.ru" in host
        and source.source_type == "scraping"
        and path == "/news"
    )


def _build_sovsport_news_article_url(base_root: str, category_type: str, slug: str) -> str | None:
    normalized_slug = slug.strip().strip("/")
    if not normalized_slug:
        return None

    normalized_category = category_type.strip().strip("/").lower()
    if normalized_category:
        candidate = _normalize_url(f"{base_root}/{normalized_category}/news/{normalized_slug}")
        if candidate:
            return candidate

    return _normalize_url(f"{base_root}/news/{normalized_slug}")


def _is_sovsport_host(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return host.endswith("sovsport.ru") or ".sovsport.ru" in host


def _looks_like_news_url(url: str) -> bool:
    parts = urlsplit(url)
    path = parts.path.strip("/").lower()
    if not path:
        return False

    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False

    if any(segment in BLOCKED_URL_SEGMENTS for segment in segments):
        return False

    if any(segment in PREFERRED_URL_SEGMENTS for segment in segments):
        return True

    if len(segments) >= 2:
        return True

    return bool(re.search(r"\d", path))

