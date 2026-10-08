from __future__ import annotations

import re
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from .models import (
    RawItem,
    SourceItem,
)
from .ingestion_text import _looks_like_live_match_tracker
from .ingestion_types import CATEGORY_RULES, SOURCE_REPUTATION_HINTS
from .ingestion_types import (
    HIGH_PRIORITY_TERMS,
    MAJOR_EVENT_TERMS,
    MEDIUM_PRIORITY_TERMS,
    OFFICIAL_SIGNAL_TERMS,
)
from .ingestion_urls import _make_dedupe_key


def _build_raw_item(
    *,
    source: SourceItem,
    payload: str,
    fetched_at: datetime,
    external_id: str,
    title: str,
    summary: str,
    lead: str | None = None,
    full_text: str | None = None,
    source_title: str | None = None,
    source_url: str | None = None,
    url: str | None,
    published: datetime,
    tags: list[str] | None = None,
) -> RawItem:
    normalized_category = _classify_category(title, summary, source, tags)
    dedupe_key = _make_dedupe_key(url, title)
    importance_score = _score_importance(title, summary, published, source, tags)
    triage_label = _triage_label(importance_score)
    if _looks_like_live_match_tracker(title, summary):
        importance_score = min(importance_score, 18)
        triage_label = "low"

    return RawItem(
        id=f"{source.key}:{external_id}",
        source_key=source.key,
        source_title=source_title or source.title,
        source_url=source_url or source.url,
        category=source.category,
        normalized_category=normalized_category,
        external_id=external_id,
        dedupe_key=dedupe_key,
        title=title,
        summary=summary,
        lead=lead,
        url=url,
        published_at=published,
        fetched_at=fetched_at,
        importance_score=importance_score,
        triage_label=triage_label,
        full_text=full_text,
        tags=tags or [],
        payload=payload,
    )


def _classify_category(
    title: str,
    summary: str,
    source: SourceItem,
    tags: list[str] | None = None,
) -> str:
    haystack = " ".join(
        part
        for part in (
            title,
            summary,
            source.title,
            source.category,
            source.url,
            " ".join(tags or []),
        )
        if part
    ).lower()

    for category, keywords in CATEGORY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return category

    return "general"


def _score_importance(
    title: str,
    summary: str,
    published_at: datetime,
    source: SourceItem,
    tags: list[str] | None = None,
) -> int:
    score = 0
    for _, delta in _score_importance_components(title, summary, published_at, source, tags):
        score += delta
    return max(0, min(score, 100))


def build_importance_score_breakdown(
    *,
    title: str,
    summary: str,
    published_at: datetime,
    source: SourceItem,
    tags: list[str] | None = None,
) -> list[str]:
    components = _score_importance_components(title, summary, published_at, source, tags)
    lines = [
        f"{label}: {'+' if delta >= 0 else ''}{delta}"
        for label, delta in components
        if delta != 0 or label == "База"
    ]
    total = max(0, min(sum(delta for _, delta in components), 100))
    lines.append(f"Итог: {total}/100")
    return lines


def _score_importance_components(
    title: str,
    summary: str,
    published_at: datetime,
    source: SourceItem,
    tags: list[str] | None = None,
) -> list[tuple[str, int]]:
    components: list[tuple[str, int]] = [("База", 18)]
    title_lower = title.lower()
    summary_lower = summary.lower()
    haystack = f"{title_lower} {summary_lower}"

    components.append(("Свежесть", _freshness_bonus(published_at)))
    components.append(("Источник", _source_reputation_bonus(source)))
    components.append(("Категория", _category_bonus(source, haystack, tags)))

    for term in HIGH_PRIORITY_TERMS:
        if term in title_lower:
            components.append((f"Сильный триггер title: {term}", 16))
        elif term in summary_lower:
            components.append((f"Сильный триггер summary: {term}", 8))

    for term in MEDIUM_PRIORITY_TERMS:
        if term in title_lower:
            components.append((f"Средний триггер title: {term}", 6))
        elif term in summary_lower:
            components.append((f"Средний триггер summary: {term}", 3))

    for term in MAJOR_EVENT_TERMS:
        if term in haystack:
            components.append((f"Большое событие: {term}", 8))

    for term in OFFICIAL_SIGNAL_TERMS:
        if term in haystack:
            components.append((f"Официальный сигнал: {term}", 6))

    if re.search(r"\b\d+\s*[:\-]\s*\d+\b", title_lower):
        components.append(("Счет/результат в заголовке", 4))
    if re.search(r"\b\d+\s+(матч|тур|игр|round|game|games)\b", haystack):
        components.append(("Матчевая фактура", 4))

    if len(title.strip()) >= 55:
        components.append(("Достаточно информативный заголовок", 3))
    if len(summary.strip()) >= 140:
        components.append(("Подробный summary", 4))
    elif len(summary.strip()) < 45:
        components.append(("Слишком короткий summary", -6))

    if _looks_like_live_match_tracker(title, summary):
        components.append(("Live/match-tracker штраф", -22))
    elif any(noise in haystack for noise in ("прямой эфир", "live", "видео", "video")):
        components.append(("Сервисный/видео штраф", -6))

    return components


def _triage_label(score: int) -> str:
    if score >= 78:
        return "high"
    if score >= 48:
        return "medium"
    return "low"


def _freshness_bonus(published_at: datetime) -> int:
    age = datetime.now(timezone.utc) - published_at
    if age <= timedelta(hours=1):
        return 28
    if age <= timedelta(hours=3):
        return 22
    if age <= timedelta(hours=6):
        return 16
    if age <= timedelta(hours=12):
        return 10
    if age <= timedelta(hours=24):
        return 5
    return 0


def _source_reputation_bonus(source: SourceItem) -> int:
    haystack = f"{source.title} {source.url}".lower()
    best_match = 0
    for hint, bonus in SOURCE_REPUTATION_HINTS.items():
        if hint in haystack:
            best_match = max(best_match, bonus)
    return best_match


def _category_bonus(source: SourceItem, haystack: str, tags: list[str] | None = None) -> int:
    category = _classify_category("", haystack, source, tags)
    if category == "general":
        return 0
    if category == "betting":
        return 4
    return 6

