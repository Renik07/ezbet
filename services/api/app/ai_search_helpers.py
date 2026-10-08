from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit
from urllib.parse import urlunsplit


def _normalize_source_discovery_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return url.strip()

    path = parts.path or "/"

    # Discovery should search a section/listing, not a single article.
    article_like = (
        path.endswith(".html")
        or path.endswith(".htm")
        or "/news/" in path
        or path.rstrip("/").split("/")[-1].isdigit()
    )
    if article_like:
        normalized_path = path
        if normalized_path.endswith((".html", ".htm")):
            normalized_path = normalized_path.rsplit("/", 1)[0] + "/"
        elif not normalized_path.endswith("/"):
            normalized_path = normalized_path.rsplit("/", 1)[0] + "/"
        if not normalized_path:
            normalized_path = "/"
        return urlunsplit((parts.scheme, parts.netloc, normalized_path, "", ""))

    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _build_article_search_profiles(
    *,
    url: str,
    source_title: str,
    raw_title: str,
    raw_summary: str,
) -> list[dict[str, Any]]:
    compact_title = _compress_search_text(raw_title, limit=180)
    compact_summary = _compress_search_text(raw_summary, limit=260)
    fact_keywords = _extract_fact_keywords(raw_title, raw_summary, limit=8)
    fact_hint = ", ".join(fact_keywords)
    host = urlsplit(url).netloc.lower()

    profiles: list[dict[str, Any]] = [
        {
            "name": "same_domain_title_first",
            "query_hint": (
                f'Find the same news on the original source first. Domain: {host or source_title}. '
                f'Use this title: "{compact_title}".'
            ),
            "restrict_to_source_domain": True,
        },
        {
            "name": "title_plus_summary",
            "query_hint": (
                f'Find the same news story by title and facts. Title: "{compact_title}". '
                f"Summary facts: {compact_summary}"
            ),
            "restrict_to_source_domain": False,
        },
    ]

    if fact_hint:
        profiles.append(
            {
                "name": "fact_keywords",
                "query_hint": (
                    "Find the same sports news story by factual keywords and entities, even if the original title "
                    f"is noisy or transliterated. Keywords: {fact_hint}"
                ),
                "restrict_to_source_domain": False,
            }
        )

    return profiles


def _compress_search_text(value: str, *, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip(" ,.;:!?")


def _extract_fact_keywords(raw_title: str, raw_summary: str, *, limit: int) -> list[str]:
    text = f"{raw_title} {raw_summary}"
    candidates = re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9'’.-]{2,}", text)
    keywords: list[str] = []
    seen: set[str] = set()
    stopwords = {
        "что",
        "это",
        "как",
        "для",
        "при",
        "или",
        "его",
        "еще",
        "after",
        "with",
        "from",
        "this",
        "that",
        "have",
        "will",
        "been",
        "news",
        "sport",
    }

    for candidate in candidates:
        lowered = candidate.lower()
        if lowered in seen or lowered in stopwords:
            continue
        if len(lowered) <= 2:
            continue
        seen.add(lowered)
        keywords.append(candidate)
        if len(keywords) >= limit:
            break

    return keywords


def _score_partial_search_candidate(
    *,
    lead: str | None,
    tags: list[str],
    reference_urls: list[str],
) -> int:
    score = 0
    if lead:
        score += 3
        if len(lead) >= 80:
            score += 2
    if tags:
        score += min(len(tags), 4)
    if reference_urls:
        score += min(len(reference_urls), 3)
    return score


def _truncate_for_llm(value: str, limit: int) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit]


def _prepare_html_for_article_extraction(
    *,
    html: str,
    raw_title: str,
    raw_summary: str,
    limit: int,
) -> str:
    cleaned = html.strip()
    if len(cleaned) <= limit:
        return cleaned

    snippets: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add_snippet(label: str, snippet: str | None) -> None:
        if not snippet:
            return
        compact = snippet.strip()
        if not compact or compact in seen:
            return
        seen.add(compact)
        snippets.append((label, compact))

    add_snippet("HEAD", cleaned[:5000])
    add_snippet("TAIL", cleaned[-3000:])

    focus_terms = [raw_title, raw_summary]
    focus_terms.extend(
        term
        for term in (
            "<article",
            "<main",
            "articlebody",
            "article-body",
            "story-body",
            "news__content",
            "articlecontent",
            "\"article\"",
            "\"content\"",
        )
    )

    lowered = cleaned.lower()
    for term in focus_terms:
        normalized_term = (term or "").strip()
        if not normalized_term:
            continue
        lookup = normalized_term.lower()
        index = lowered.find(lookup)
        if index == -1 and len(lookup) > 80:
            lookup = lookup[:80]
            index = lowered.find(lookup)
        if index == -1:
            continue
        start = max(0, index - 5000)
        end = min(len(cleaned), index + 18000)
        add_snippet(f"FOCUS:{normalized_term[:48]}", cleaned[start:end])
        if sum(len(text) for _, text in snippets) >= limit:
            break

    if not snippets:
        return _truncate_for_llm(cleaned, limit)

    parts: list[str] = []
    total = 0
    for label, snippet in snippets:
        block = f"<!-- {label} -->\n{snippet}"
        remaining = limit - total
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining]
        parts.append(block)
        total += len(block)

    prepared = "\n\n".join(parts).strip()
    return prepared or _truncate_for_llm(cleaned, limit)

