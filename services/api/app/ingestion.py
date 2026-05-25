from __future__ import annotations

from dataclasses import dataclass
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import urlopen
from xml.etree import ElementTree

from .ai_client import OpenAIEditorialClient
from .models import NewsItem, PromptConfig, RawItem, SourceItem, SourceSyncState

if TYPE_CHECKING:
    from .repository import NewsRepository

SUPPORTED_ACTIVE_SOURCE_TYPES = {"rss", "news_sitemap", "scraping", "ai_research"}

POSITIVE_CONTAINER_TERMS = (
    "news",
    "article",
    "story",
    "post",
    "feed",
    "list",
    "items",
    "headline",
    "content",
    "main",
    "sport",
    "football",
    "hockey",
    "basketball",
    "tennis",
)

NEGATIVE_CONTAINER_TERMS = (
    "nav",
    "menu",
    "footer",
    "header",
    "sidebar",
    "banner",
    "promo",
    "advert",
    "login",
    "auth",
    "profile",
    "subscription",
    "subscribe",
)

BLOCKED_URL_SEGMENTS = {
    "video",
    "videos",
    "tv",
    "channel",
    "channels",
    "podcast",
    "subscription",
    "subscriptions",
    "subscribe",
    "auth",
    "login",
    "register",
    "profile",
    "account",
    "shop",
    "store",
    "about",
    "contacts",
    "contact",
    "advert",
    "advertisement",
    "advertising",
    "ads",
    "promo",
    "cookie",
    "cookies",
    "agreement",
    "privacy",
    "policy",
    "policies",
    "terms",
    "legal",
}

PREFERRED_URL_SEGMENTS = {
    "news",
    "article",
    "articles",
    "story",
    "stories",
    "sport",
    "sports",
    "football",
    "hockey",
    "basketball",
    "tennis",
    "match",
}

ARTICLE_CONTAINER_TERMS = (
    "article",
    "story",
    "content",
    "entry",
    "post",
    "body",
    "text",
    "main",
    "news",
)

ARTICLE_NEGATIVE_TERMS = (
    "nav",
    "menu",
    "footer",
    "header",
    "banner",
    "promo",
    "share",
    "related",
    "recommend",
    "sidebar",
    "comment",
)

CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("football", ("футбол", "football", "рпл", "лига чемпионов", "апл", "ла лига")),
    ("hockey", ("хоккей", "hockey", "кхл", "нхл", "nhl")),
    ("basketball", ("баскетбол", "basketball", "нба", "nba", "евролига")),
    ("tennis", ("теннис", "tennis", "atp", "wta")),
    ("betting", ("букмекер", "ставк", "bet", "коэффициент", "линия")),
]

HIGH_PRIORITY_TERMS = (
    "срочно",
    "официально",
    "эксклюзив",
    "exclusive",
    "breaking",
    "трансфер",
    "уволен",
    "травм",
    "финал",
    "чемпион",
)

MEDIUM_PRIORITY_TERMS = (
    "матч",
    "игра",
    "побед",
    "проигр",
    "турнир",
    "тренер",
    "команда",
)


@dataclass
class SourceIngestionResult:
    source: SourceItem
    items: list[RawItem]
    fetch_status: str
    parse_status: str
    error: str | None
    retry_count: int


class SourceFetchError(RuntimeError):
    pass


@dataclass
class ArticleEnrichmentResult:
    title: str | None
    full_text: str | None
    lead: str | None
    tags: list[str]


@dataclass
class SourceProbeResult:
    ok: bool
    item_count: int
    message: str
    readiness: str
    resolved_source_type: str | None
    resolved_source_url: str | None
    supports_rss: bool
    supports_news_sitemap: bool
    supports_sitemap: bool
    supports_scraping: bool
    full_text_ok: bool
    lead_ok: bool
    tags_count: int
    sample_title: str | None
    sample_url: str | None

MAJOR_EVENT_TERMS = (
    "лига чемпионов",
    "champions league",
    "плей-офф",
    "playoff",
    "финал",
    "final",
    "кубок",
    "world cup",
    "евро",
    "дерби",
    "ufc",
)

OFFICIAL_SIGNAL_TERMS = (
    "официально",
    "official",
    "объявил",
    "confirmed",
    "назначен",
    "подписал",
    "продлил",
    "disqualified",
)

SOURCE_REPUTATION_HINTS: dict[str, int] = {
    "sports.ru": 6,
    "sport-express": 7,
    "спорт-экспресс": 7,
    "championat": 6,
    "чемпионат": 6,
    "sovsport": 5,
    "советский спорт": 5,
}


def ingest_sources(
    sources: Iterable[SourceItem],
    source_states: dict[str, SourceSyncState] | None = None,
    timeout: int = 10,
    limit: int | None = None,
    limit_per_source: bool = False,
    ai_search_prompt: PromptConfig | None = None,
) -> list[RawItem]:
    collected, _ = ingest_sources_with_results(
        sources,
        source_states=source_states,
        timeout=timeout,
        limit=limit,
        limit_per_source=limit_per_source,
        ai_search_prompt=ai_search_prompt,
    )
    return collected


def ingest_sources_with_results(
    sources: Iterable[SourceItem],
    source_states: dict[str, SourceSyncState] | None = None,
    known_external_ids_by_source: dict[str, set[str]] | None = None,
    known_dedupe_keys_by_source: dict[str, set[str]] | None = None,
    timeout: int = 10,
    limit: int | None = None,
    max_retries: int = 1,
    limit_per_source: bool = False,
    ai_search_prompt: PromptConfig | None = None,
) -> tuple[list[RawItem], list[SourceIngestionResult]]:
    collected: list[RawItem] = []
    results: list[SourceIngestionResult] = []
    seen_keys: set[str] = set()
    states = source_states or {}
    known_external_ids_map = known_external_ids_by_source or {}
    known_dedupe_keys_map = known_dedupe_keys_by_source or {}

    for source in sources:
        source_state = states.get(source.key)
        runtime_source = _resolve_source_runtime(source, source_state)
        source_result = _collect_source_items_with_retry(
            runtime_source,
            timeout=timeout,
            max_retries=max_retries,
            ai_search_prompt=ai_search_prompt,
        )
        collected_items = source_result.items
        filtered_items = _filter_new_items(
            collected_items,
            source_state,
            runtime_source.source_type,
            known_external_ids=known_external_ids_map.get(source.key, set()),
            known_dedupe_keys=known_dedupe_keys_map.get(source.key, set()),
        )
        if limit is not None and limit_per_source:
            filtered_items = filtered_items[:limit]
        for item in filtered_items:
            dedupe_key = item.dedupe_key
            if dedupe_key in seen_keys:
                item.is_duplicate = True
                item.duplicate_of = dedupe_key
            else:
                seen_keys.add(dedupe_key)
            collected.append(item)
        results.append(source_result)

    collected.sort(key=lambda item: (item.published_at, item.importance_score), reverse=True)
    if limit is not None and not limit_per_source:
        return collected[:limit], results
    return collected, results


def _resolve_source_runtime(source: SourceItem, state: SourceSyncState | None) -> SourceItem:
    if state is None:
        return source

    effective_adapter = _select_effective_adapter(source, state)
    effective_url = _select_effective_url(source, state, effective_adapter)
    if effective_adapter == source.source_type and effective_url == source.url:
        return source

    return source.model_copy(
        update={
            "source_type": effective_adapter,
            "url": effective_url,
        }
    )


def _select_effective_adapter(source: SourceItem, state: SourceSyncState) -> str:
    preferred = (state.preferred_adapter or "").strip()
    if preferred and _capability_supports_adapter(state, preferred):
        return preferred

    if _capability_supports_adapter(state, source.source_type):
        return source.source_type

    for adapter in ("rss", "news_sitemap", "scraping", "ai_research"):
        if _capability_supports_adapter(state, adapter):
            return adapter

    return source.source_type


def _select_effective_url(source: SourceItem, state: SourceSyncState, effective_adapter: str) -> str:
    preferred_url = (state.preferred_adapter_url or "").strip()
    if preferred_url and effective_adapter == (state.preferred_adapter or "").strip():
        return preferred_url
    return source.url


def _capability_supports_adapter(state: SourceSyncState, adapter: str) -> bool:
    if adapter == "rss":
        return state.supports_rss
    if adapter == "news_sitemap":
        return state.supports_news_sitemap
    if adapter == "sitemap":
        return state.supports_sitemap
    if adapter == "scraping":
        return state.supports_scraping
    if adapter == "ai_research":
        return state.last_probe_readiness in {"ready_ai", "partial"}
    return False


def raw_items_to_news(raw_items: Iterable[RawItem]) -> list[NewsItem]:
    items: list[NewsItem] = []

    for raw in raw_items:
        if raw.is_duplicate:
            continue

        items.append(
            NewsItem(
                id=raw.external_id,
                title=raw.title,
                description=raw.summary,
                category=raw.normalized_category,
                published_at=raw.published_at,
                source=raw.source_title,
                link=raw.url,
                ai_reviewed=False,
            )
        )

    return items


def enrich_raw_item_content(
    repository: "NewsRepository",
    raw_item: RawItem,
    *,
    allow_web_search_fallback: bool = True,
) -> RawItem:
    existing_full_text = (raw_item.full_text or "").strip()
    has_usable_full_text = _is_usable_full_text(existing_full_text, raw_item.summary)
    if (
        has_usable_full_text
        and ((raw_item.lead or "").strip() or raw_item.tags)
    ) or not raw_item.url:
        return raw_item

    html = fetch_remote_document(raw_item.url, timeout=10)
    direct_enrichment = _extract_article_enrichment_from_html(raw_item.url, html) if html else None
    if direct_enrichment is not None and _is_usable_full_text(direct_enrichment.full_text, raw_item.summary):
        return _persist_raw_item_enrichment(
            repository,
            raw_item,
            title=direct_enrichment.title,
            full_text=direct_enrichment.full_text,
            lead=direct_enrichment.lead,
            tags=direct_enrichment.tags,
            full_text_source_url=raw_item.url,
            full_text_source_title=raw_item.source_title,
            reference_urls=[],
            extraction_mode="direct_html",
            enrichment_status="direct_html_ok",
        )

    ai_client = OpenAIEditorialClient()
    ai_html_enrichment = (
        ai_client.extract_article_enrichment(
            url=raw_item.url,
            source_title=raw_item.source_title,
            raw_title=raw_item.title,
            raw_summary=raw_item.summary,
            html=html,
            allow_web_search=False,
        )
        if ai_client.enabled and html
        else None
    )
    if ai_html_enrichment is not None and _is_usable_full_text(ai_html_enrichment.full_text, raw_item.summary):
        return _persist_raw_item_enrichment(
            repository,
            raw_item,
            title=direct_enrichment.title if direct_enrichment is not None else None,
            full_text=ai_html_enrichment.full_text,
            lead=ai_html_enrichment.lead or (direct_enrichment.lead if direct_enrichment is not None else None),
            tags=_merge_tags(
                direct_enrichment.tags if direct_enrichment is not None else [],
                ai_html_enrichment.tags,
            ),
            full_text_source_url=ai_html_enrichment.source_url or raw_item.url,
            full_text_source_title=ai_html_enrichment.source_title or raw_item.source_title,
            reference_urls=ai_html_enrichment.reference_urls,
            extraction_mode=ai_html_enrichment.generation_mode,
            enrichment_status="ai_html_ok",
        )

    local_partial = _choose_best_local_partial_enrichment(
        direct_enrichment=direct_enrichment,
        ai_html_enrichment=ai_html_enrichment,
    )
    if not ai_client.enabled:
        if local_partial is None:
            return raw_item
        return _persist_raw_item_enrichment(
            repository,
            raw_item,
            title=local_partial["title"],
            full_text=local_partial["full_text"],
            lead=local_partial["lead"],
            tags=local_partial["tags"],
            full_text_source_url=raw_item.url,
            full_text_source_title=raw_item.source_title,
            reference_urls=[],
            extraction_mode=local_partial["extraction_mode"],
            enrichment_status=local_partial["enrichment_status"],
        )

    if not allow_web_search_fallback:
        if local_partial is not None:
            return _persist_raw_item_enrichment(
                repository,
                raw_item,
                title=local_partial["title"],
                full_text=local_partial["full_text"],
                lead=local_partial["lead"],
                tags=local_partial["tags"],
                full_text_source_url=raw_item.url,
                full_text_source_title=raw_item.source_title,
                reference_urls=[],
                extraction_mode=local_partial["extraction_mode"],
                enrichment_status="search_skipped_run_cap",
            )
        return (
            repository.update_raw_item_enrichment(
                raw_item.id,
                enrichment_status="search_skipped_run_cap",
                enrichment_error=(
                    "web_search fallback пропущен: в этом enrichment batch уже исчерпан лимит "
                    "внешнего поиска."
                ),
            )
            or raw_item
        )

    if not _should_allow_web_search_fallback(raw_item):
        if local_partial is not None:
            return _persist_raw_item_enrichment(
                repository,
                raw_item,
                title=local_partial["title"],
                full_text=local_partial["full_text"],
                lead=local_partial["lead"],
                tags=local_partial["tags"],
                full_text_source_url=raw_item.url,
                full_text_source_title=raw_item.source_title,
                reference_urls=[],
                extraction_mode=local_partial["extraction_mode"],
                enrichment_status="search_skipped_budget",
            )
        return (
            repository.update_raw_item_enrichment(
                raw_item.id,
                enrichment_status="search_skipped_budget",
                enrichment_error=(
                    "web_search fallback пропущен по budget-правилу: для low-priority новости "
                    "сначала используем только локальный extraction."
                ),
            )
            or raw_item
        )

    ai_search_enrichment = ai_client.extract_article_enrichment_via_search(
        url=raw_item.url,
        source_title=raw_item.source_title,
        raw_title=raw_item.title,
        raw_summary=raw_item.summary,
    )
    if ai_search_enrichment is None:
        if local_partial is not None:
            return _persist_raw_item_enrichment(
                repository,
                raw_item,
                title=local_partial["title"],
                full_text=local_partial["full_text"],
                lead=local_partial["lead"],
                tags=local_partial["tags"],
                full_text_source_url=raw_item.url,
                full_text_source_title=raw_item.source_title,
                reference_urls=[],
                extraction_mode=local_partial["extraction_mode"],
                enrichment_status=local_partial["enrichment_status"],
            )
        return (
            repository.update_raw_item_enrichment(
                raw_item.id,
                enrichment_status="search_no_match",
                enrichment_error="Ни direct parser, ни AI extraction по HTML, ни web_search fallback не дали пригодный текст этой новости.",
            )
            or raw_item
        )

    return (
        _persist_raw_item_enrichment(
            repository,
            raw_item,
            title=(direct_enrichment.title if direct_enrichment is not None else None),
            full_text=ai_search_enrichment.full_text,
            lead=ai_search_enrichment.lead or (local_partial["lead"] if local_partial is not None else None),
            tags=_merge_tags(
                local_partial["tags"] if local_partial is not None else [],
                ai_search_enrichment.tags,
            ),
            full_text_source_url=ai_search_enrichment.source_url,
            full_text_source_title=ai_search_enrichment.source_title,
            reference_urls=ai_search_enrichment.reference_urls,
            extraction_mode=ai_search_enrichment.generation_mode,
            enrichment_status=(
                "web_search_brief_ok" if ai_search_enrichment.full_text else "search_partial_only"
            ),
        )
        or raw_item
    )


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
                False,
                0,
                None,
                None,
            )
        if source.source_type == "scraping":
            return SourceProbeResult(False, 0, "Страница не прочитана или scraping-адаптер не нашел кандидатов.", "empty", source.source_type, source.url, supports_rss, supports_news_sitemap, supports_sitemap, supports_scraping, False, False, 0, None, None)
        return SourceProbeResult(False, 0, "Фид не прочитан или не вернул элементов.", "empty", source.source_type, source.url, supports_rss, supports_news_sitemap, supports_sitemap, supports_scraping, False, False, 0, None, None)

    supports_rss, supports_news_sitemap, supports_sitemap, supports_scraping = _probe_support_flags(
        source.source_type,
        ok=True,
        item_count=len(items),
    )

    if source.source_type == "ai_research":
        sample = next((item for item in items if item.url), items[0])
        full_text_ok = _is_usable_full_text(sample.full_text, sample.summary)
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
            lead_ok,
            tags_count,
            sample.title,
            sample.url,
        )

    samples = [item for item in items if item.url][:3] or items[:1]
    sample = samples[0]
    enrichment: ArticleEnrichmentResult | None = None
    full_text_ok = False
    lead_ok = False
    tags_count = 0

    for candidate in samples:
        candidate_enrichment = extract_article_enrichment(candidate.url, timeout=timeout) if candidate.url else None
        candidate_full_text_ok = _is_usable_full_text(
            candidate_enrichment.full_text if candidate_enrichment is not None else None,
            candidate.summary,
        )
        candidate_lead_ok = _is_usable_lead(candidate_enrichment.lead if candidate_enrichment is not None else None)
        candidate_tags_count = len(candidate_enrichment.tags) if candidate_enrichment else 0

        if candidate_full_text_ok:
            sample = candidate
            enrichment = candidate_enrichment
            full_text_ok = True
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
        False,
        0,
        None,
        None,
    )


def _collect_source_items_with_retry(
    source: SourceItem,
    *,
    timeout: int,
    max_retries: int,
    ai_search_prompt: PromptConfig | None = None,
) -> SourceIngestionResult:
    attempts = 0
    last_error: str | None = None

    while attempts <= max_retries:
        attempts += 1
        try:
            items = _collect_source_items(source, timeout=timeout, ai_search_prompt=ai_search_prompt)
        except SourceFetchError as exc:
            last_error = str(exc)
            if attempts <= max_retries:
                continue
            return SourceIngestionResult(
                source=source,
                items=[],
                fetch_status="error",
                parse_status="idle",
                error=last_error,
                retry_count=attempts - 1,
            )
        except ValueError as exc:
            last_error = str(exc)
            return SourceIngestionResult(
                source=source,
                items=[],
                fetch_status="ok",
                parse_status="error",
                error=last_error,
                retry_count=attempts - 1,
            )

        if items:
            return SourceIngestionResult(
                source=source,
                items=items,
                fetch_status="ok",
                parse_status="ok",
                error=None,
                retry_count=attempts - 1,
            )

        last_error = "Источник не вернул элементов."

    return SourceIngestionResult(
        source=source,
        items=[],
        fetch_status="ok",
        parse_status="empty",
        error=last_error,
        retry_count=max_retries,
    )


def _collect_source_items(
    source: SourceItem,
    timeout: int,
    ai_search_prompt: PromptConfig | None = None,
) -> list[RawItem]:
    if source.source_type == "rss":
        return _parse_feed(source, timeout=timeout)
    if source.source_type == "news_sitemap":
        return _parse_news_sitemap_source(source, timeout=timeout)
    if source.source_type == "sitemap":
        return _parse_sitemap_source(source, timeout=timeout)
    if source.source_type == "scraping":
        return _parse_scraping_source(source, timeout=timeout)
    if source.source_type == "ai_research":
        return _parse_ai_research_source(source, timeout=timeout, ai_search_prompt=ai_search_prompt)
    return []


def _parse_feed(source: SourceItem, timeout: int) -> list[RawItem]:
    payload = _fetch_remote_document(source.url, timeout)

    encoded_payload = payload.encode("utf-8", errors="ignore")
    try:
        root = ElementTree.fromstring(encoded_payload)
    except ElementTree.ParseError:
        return []

    if root.tag.endswith("feed"):
        return _parse_atom(root, source, payload)

    return _parse_rss(root, source, payload)


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


def _parse_scraping_source(source: SourceItem, timeout: int) -> list[RawItem]:
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


def _parse_ai_research_source(
    source: SourceItem,
    timeout: int,
    ai_search_prompt: PromptConfig | None = None,
) -> list[RawItem]:
    ai_client = OpenAIEditorialClient()
    if not ai_client.enabled:
        raise SourceFetchError("AI search source requires an enabled OpenAI Responses client.")

    discovered = ai_client.discover_source_items(source, limit=5, prompt=ai_search_prompt)
    if not discovered:
        discovered = _discover_ai_research_candidates_from_listing(source, timeout=timeout)[:5]
    if not discovered:
        return []

    fetched_at = datetime.now(timezone.utc)
    items: list[RawItem] = []
    payload = ""

    for discovered_item in discovered:
        resolved_url = discovered_item.url
        resolved_published_at = discovered_item.published_at
        resolved_source_title = discovered_item.source_title

        published = _try_parse_datetime(resolved_published_at or "") or fetched_at
        payload = payload or _serialize_ai_discovery_payload(source, discovered)
        lead = discovered_item.summary
        tags = discovered_item.tags

        items.append(
            _build_raw_item(
                source=source,
                payload=payload,
                fetched_at=fetched_at,
                external_id=resolved_url,
                title=discovered_item.title,
                summary=discovered_item.summary,
                lead=lead,
                source_title=resolved_source_title,
                source_url=resolved_url,
                url=resolved_url,
                published=published,
                tags=tags,
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
        for node in root:
            if _xml_local_name(node.tag) != "sitemap":
                continue
            loc = _find_child_text(node, {"loc"})
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
        for node in root:
            if _xml_local_name(node.tag) != "sitemap":
                continue
            loc = _find_child_text(node, {"loc"})
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


def extract_article_enrichment(url: str | None, timeout: int = 10) -> ArticleEnrichmentResult | None:
    if not url:
        return None

    try:
        payload = _fetch_remote_document(url, timeout)
    except SourceFetchError:
        return None

    return _extract_article_enrichment_from_html(url, payload)


def _extract_article_enrichment_from_html(url: str, payload: str | None) -> ArticleEnrichmentResult | None:
    if not payload:
        return None

    parser = _ArticleDocumentParser(url)
    try:
        parser.feed(payload)
        parser.close()
    except ValueError:
        return None

    paragraphs = _dedupe_article_paragraphs(
        [paragraph for paragraph in parser.paragraphs if len(paragraph) >= 40]
    )
    full_text: str | None = None
    if len(paragraphs) >= 2:
        full_text = "\n\n".join(paragraphs)
    elif paragraphs:
        full_text = paragraphs[0]
    else:
        fallback = parser.og_description or parser.meta_description
        if fallback and len(fallback) >= 80:
            full_text = fallback

    resolved_title = parser.og_title or parser.heading_title or parser.page_title
    if resolved_title:
        resolved_title = _normalize_whitespace(resolved_title)

    lead = parser.og_description or parser.meta_description
    if lead:
        lead = _normalize_whitespace(lead)

    if _looks_like_listing_text(full_text):
        full_text = None

    return ArticleEnrichmentResult(
        title=resolved_title or None,
        full_text=full_text,
        lead=lead or None,
        tags=parser.tags,
    )


def _merge_tags(*tag_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in tag_groups:
        for tag in group:
            normalized = _normalize_whitespace(tag)
            lowered = normalized.lower()
            if not normalized or lowered in seen:
                continue
            seen.add(lowered)
            merged.append(normalized)
    return merged


def _choose_best_local_partial_enrichment(
    *,
    direct_enrichment: ArticleEnrichmentResult | None,
    ai_html_enrichment,
) -> dict[str, str | list[str] | None] | None:
    ai_lead = ai_html_enrichment.lead if ai_html_enrichment is not None else None
    ai_tags = ai_html_enrichment.tags if ai_html_enrichment is not None else []
    direct_title = direct_enrichment.title if direct_enrichment is not None else None
    direct_full_text = direct_enrichment.full_text if direct_enrichment is not None else None
    direct_lead = direct_enrichment.lead if direct_enrichment is not None else None
    direct_tags = direct_enrichment.tags if direct_enrichment is not None else []

    if ai_html_enrichment is not None and (
        (ai_html_enrichment.full_text or "").strip() or (ai_lead or "").strip() or ai_tags
    ):
        return {
            "title": direct_title,
            "full_text": ai_html_enrichment.full_text,
            "lead": ai_lead or direct_lead,
            "tags": _merge_tags(direct_tags, ai_tags),
            "extraction_mode": ai_html_enrichment.generation_mode,
            "enrichment_status": "ai_html_partial_only",
        }

    if direct_enrichment is not None and (
        (direct_full_text or "").strip() or (direct_lead or "").strip() or direct_tags
    ):
        return {
            "title": direct_title,
            "full_text": direct_full_text,
            "lead": direct_lead,
            "tags": direct_tags,
            "extraction_mode": "direct_html",
            "enrichment_status": "direct_html_partial_only",
        }

    return None


def _persist_raw_item_enrichment(
    repository: "NewsRepository",
    raw_item: RawItem,
    *,
    title: str | None,
    full_text: str | None,
    lead: str | None,
    tags: list[str],
    full_text_source_url: str | None,
    full_text_source_title: str | None,
    reference_urls: list[str],
    extraction_mode: str,
    enrichment_status: str,
) -> RawItem:
    normalized_title, normalized_summary = _resolve_enriched_raw_headline(
        raw_item.title,
        raw_item.summary,
        title,
        lead,
        full_text,
    )
    return (
        repository.update_raw_item_enrichment(
            raw_item.id,
            title=normalized_title,
            summary=normalized_summary,
            full_text=full_text,
            lead=lead,
            full_text_source_url=full_text_source_url,
            full_text_source_title=full_text_source_title,
            reference_urls=reference_urls,
            extraction_mode=extraction_mode,
            enrichment_status=enrichment_status,
            tags=tags,
        )
        or raw_item
    )


def _is_usable_full_text(value: str | None, source_summary: str | None = None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    if _looks_like_listing_text(normalized):
        return False
    if len(normalized) >= 180:
        return True
    if normalized.count("\n\n") >= 1 and len(normalized) >= 120:
        return True
    summary = (source_summary or "").strip()
    if summary and len(normalized) >= max(120, int(len(summary) * 1.35)):
        return True
    return False


def _is_usable_lead(value: str | None) -> bool:
    return bool(value and len(value.strip()) >= 40)


def _should_allow_web_search_fallback(raw_item: RawItem) -> bool:
    return raw_item.triage_label in {"high", "medium"} and raw_item.importance_score >= 48


def extract_article_full_text(url: str | None, timeout: int = 10) -> str | None:
    enrichment = extract_article_enrichment(url, timeout=timeout)
    if enrichment is None:
        return None
    return enrichment.full_text


def fetch_remote_document(url: str | None, timeout: int = 10) -> str | None:
    if not url:
        return None
    try:
        return _fetch_remote_document(url, timeout)
    except SourceFetchError:
        return None


def _filter_new_items(
    items: list[RawItem],
    state: SourceSyncState | None,
    source_type: str,
    *,
    known_external_ids: set[str] | None = None,
    known_dedupe_keys: set[str] | None = None,
) -> list[RawItem]:
    known_ids = known_external_ids or set()
    known_keys = known_dedupe_keys or set()
    if state is not None and source_type == "scraping":
        fresh_items: list[RawItem] = []
        for item in items:
            if (
                (state.last_external_id and item.external_id == state.last_external_id)
                or item.external_id in known_ids
                or item.dedupe_key in known_keys
            ):
                return fresh_items
            fresh_items.append(item)
        return fresh_items

    if state is None or state.last_published_at is None:
        return items

    last_published_at = state.last_published_at
    last_external_id = state.last_external_id

    if source_type in {"rss", "news_sitemap"} and _items_look_descending_by_freshness(items):
        fresh_items: list[RawItem] = []
        for item in items:
            if last_external_id is not None and item.external_id == last_external_id:
                break

            if item.external_id in known_ids:
                break

            if item.dedupe_key in known_keys:
                break

            if item.published_at > last_published_at:
                fresh_items.append(item)
                continue

            if (
                item.published_at == last_published_at
                and last_external_id is not None
                and item.external_id != last_external_id
            ):
                fresh_items.append(item)
                continue

            if item.published_at < last_published_at:
                break

        if fresh_items:
            return fresh_items

    fresh_items: list[RawItem] = []

    for item in items:
        if item.published_at > last_published_at:
            fresh_items.append(item)
            continue

        if (
            item.published_at == last_published_at
            and last_external_id is not None
            and item.external_id != last_external_id
        ):
            fresh_items.append(item)

    return fresh_items


def _items_look_descending_by_freshness(items: list[RawItem]) -> bool:
    if len(items) < 2:
        return True

    previous = items[0].published_at
    for item in items[1:]:
        if item.published_at > previous:
            return False
        previous = item.published_at
    return True


def _parse_rss(root: ElementTree.Element, source: SourceItem, payload: str) -> list[RawItem]:
    items: list[RawItem] = []
    fetched_at = datetime.now(timezone.utc)

    for node in root.findall("./channel/item"):
        title = _node_text(node.find("title")) or "Без заголовка"
        summary = _strip_html(_node_text(node.find("description")) or "Описание отсутствует.")
        url = _node_text(node.find("link"))
        published = _parse_datetime(_node_text(node.find("pubDate")))
        external_id = url or f"{source.key}:{title}"
        category_nodes = [_normalize_whitespace(_node_text(category)) for category in node.findall("category")]
        tags = [value for value in category_nodes if value]

        items.append(
            _build_raw_item(
                source=source,
                payload=payload,
                fetched_at=fetched_at,
                external_id=external_id,
                title=title,
                summary=summary,
                lead=summary,
                url=url,
                published=published,
                tags=tags,
            )
        )

    return items


def _parse_atom(root: ElementTree.Element, source: SourceItem, payload: str) -> list[RawItem]:
    items: list[RawItem] = []
    fetched_at = datetime.now(timezone.utc)
    namespace = {"atom": "http://www.w3.org/2005/Atom"}

    for node in root.findall("atom:entry", namespace):
        title = _node_text(node.find("atom:title", namespace)) or "Без заголовка"
        summary = _strip_html(_node_text(node.find("atom:summary", namespace)) or "Описание отсутствует.")
        link_node = node.find("atom:link", namespace)
        url = link_node.get("href") if link_node is not None else None
        category_nodes = [_normalize_whitespace(node.get("term", "")) for node in node.findall("atom:category", namespace)]
        tags = [value for value in category_nodes if value]
        published = _parse_datetime(
            _node_text(node.find("atom:updated", namespace))
            or _node_text(node.find("atom:published", namespace))
        )
        external_id = url or f"{source.key}:{title}"

        items.append(
            _build_raw_item(
                source=source,
                payload=payload,
                fetched_at=fetched_at,
                external_id=external_id,
                title=title,
                summary=summary,
                lead=summary,
                url=url,
                published=published,
                tags=tags,
            )
        )

    return items


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
    normalized_category = _classify_category(title, summary, source)
    dedupe_key = _make_dedupe_key(url, title)
    importance_score = _score_importance(title, summary, published, source)
    triage_label = _triage_label(importance_score)

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


class _ArticleDocumentParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self._container_scores: list[int] = [0]
        self._skip_depth = 0
        self._text_capture_depth = 0
        self._text_capture_parts: list[str] = []
        self._in_paragraph = False
        self._paragraph_parts: list[str] = []
        self._in_title_tag = False
        self._title_parts: list[str] = []
        self._in_h1_tag = False
        self._h1_parts: list[str] = []
        self.paragraphs: list[str] = []
        self.page_title: str | None = None
        self.og_title: str | None = None
        self.heading_title: str | None = None
        self.meta_description: str | None = None
        self.og_description: str | None = None
        self.tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        tag = tag.lower()
        self._container_scores.append(self._container_scores[-1] + _article_container_score(tag, attr_map))

        if tag == "title":
            self._in_title_tag = True
            return
        if tag == "h1":
            self._in_h1_tag = True
            self._h1_parts = []

        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return

        if (
            self._skip_depth == 0
            and self._text_capture_depth == 0
            and self._container_scores[-1] >= 3
            and _looks_like_article_text_container(attr_map)
        ):
            self._text_capture_depth = 1
            self._text_capture_parts = []
        elif self._text_capture_depth > 0:
            self._text_capture_depth += 1

        if tag == "meta":
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
            elif name == "keywords":
                self._add_tags(content)
            elif prop in {"article:tag", "og:article:tag"}:
                self._add_tags(content)
            return

        if tag == "p" and self._skip_depth == 0 and self._container_scores[-1] >= 2:
            self._in_paragraph = True
            self._paragraph_parts = []

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
            if tag == "h1" and self._in_h1_tag:
                self._in_h1_tag = False
                heading = _normalize_whitespace(" ".join(self._h1_parts))
                if heading and not self.heading_title:
                    self.heading_title = heading
                self._h1_parts = []

            if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
                self._skip_depth -= 1
                return

            if tag == "p" and self._in_paragraph:
                text = _normalize_whitespace(" ".join(self._paragraph_parts))
                if text and text not in self.paragraphs:
                    self.paragraphs.append(text)
                self._in_paragraph = False
                self._paragraph_parts = []

            if self._text_capture_depth > 0:
                self._text_capture_depth -= 1
                if self._text_capture_depth == 0:
                    text = _normalize_article_text(" ".join(self._text_capture_parts))
                    for paragraph in _split_article_text(text):
                        if paragraph not in self.paragraphs:
                            self.paragraphs.append(paragraph)
                    self._text_capture_parts = []
        finally:
            if self._container_scores:
                self._container_scores.pop()

    def handle_data(self, data: str) -> None:
        if self._in_title_tag:
            self._title_parts.append(data)
        if self._in_h1_tag:
            self._h1_parts.append(data)
        if self._skip_depth > 0:
            return
        if self._in_paragraph:
            self._paragraph_parts.append(data)
        if self._text_capture_depth > 0:
            self._text_capture_parts.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._container_scores:
            self._container_scores.pop()

    def _add_tags(self, value: str) -> None:
        for tag in _split_meta_values(value):
            if tag not in self.tags:
                self.tags.append(tag)


def _classify_category(title: str, summary: str, source: SourceItem) -> str:
    haystack = f"{title} {summary} {source.title}".lower()

    for category, keywords in CATEGORY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return category

    return "general"


def _score_importance(title: str, summary: str, published_at: datetime, source: SourceItem) -> int:
    score = 18
    title_lower = title.lower()
    summary_lower = summary.lower()
    haystack = f"{title_lower} {summary_lower}"

    score += _freshness_bonus(published_at)
    score += _source_reputation_bonus(source)
    score += _category_bonus(source, haystack)

    for term in HIGH_PRIORITY_TERMS:
        if term in title_lower:
            score += 16
        elif term in summary_lower:
            score += 8

    for term in MEDIUM_PRIORITY_TERMS:
        if term in title_lower:
            score += 6
        elif term in summary_lower:
            score += 3

    for term in MAJOR_EVENT_TERMS:
        if term in haystack:
            score += 8

    for term in OFFICIAL_SIGNAL_TERMS:
        if term in haystack:
            score += 6

    if re.search(r"\b\d+\s*[:\-]\s*\d+\b", title_lower):
        score += 4
    if re.search(r"\b\d+\s+(матч|тур|игр|round|game|games)\b", haystack):
        score += 4

    if len(title.strip()) >= 55:
        score += 3
    if len(summary.strip()) >= 140:
        score += 4
    elif len(summary.strip()) < 45:
        score -= 6

    if any(noise in haystack for noise in ("прямой эфир", "live", "видео", "video")):
        score -= 6

    return max(0, min(score, 100))


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


def _category_bonus(source: SourceItem, haystack: str) -> int:
    category = _classify_category("", haystack, source)
    if category in {"football", "hockey", "basketball", "tennis"}:
        return 6
    if category == "betting":
        return 4
    return 0


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

    cleaned = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))
    return cleaned.rstrip("/")


def _normalize_candidate_url(base_url: str, href: str) -> str | None:
    normalized = _normalize_url(urljoin(base_url, href))
    parts = urlsplit(normalized)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return normalized


def _looks_like_story_title(value: str) -> bool:
    lowered = value.strip().lower()
    if len(lowered) < 18:
        return False
    if len(re.findall(r"[a-zа-я0-9]+", lowered, flags=re.IGNORECASE)) < 3:
        return False

    blocked = {
        "читать далее",
        "подробнее",
        "новости",
        "главная",
        "войти",
        "регистрация",
        "все новости",
        "прямой эфир",
        "смотреть",
    }
    if lowered in blocked:
        return False
    blocked_terms = ("канал", "подписк", "кинотеатр", "okko", "аккаунт", "авторизац")
    if any(term in lowered for term in blocked_terms):
        return False
    return not _looks_like_category_label(lowered)


def _looks_like_listing_title(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return False
    patterns = (
        "новости ",
        "последние новости",
        "актуальные события",
        "самые свежие",
        "все новости",
    )
    return any(pattern in lowered for pattern in patterns)


def _looks_like_category_label(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return False

    words = re.findall(r"[a-zа-я0-9]+", lowered, flags=re.IGNORECASE)
    if 1 <= len(words) <= 4 and lowered.count("/") >= 1 and not re.search(r"\d", lowered):
        return True

    generic_labels = {
        "футбол",
        "хоккей",
        "теннис",
        "баскетбол",
        "биатлон",
        "бобслей",
        "скелетон",
        "санный спорт",
        "фигурное катание",
        "мма",
        "бокс",
        "авто",
        "формула 1",
        "кхл",
        "нхл",
        "рпл",
        "апл",
        "ла лига",
        "серия а",
        "лига 1",
        "бундеслига",
    }
    return lowered in generic_labels


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


def _normalize_whitespace(value: str) -> str:
    return " ".join(unescape(value).split())


def _split_meta_values(value: str) -> list[str]:
    cleaned = _normalize_whitespace(value)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"[;,|/]", cleaned) if part.strip()]


def _looks_like_article_text_container(attr_map: dict[str, str]) -> bool:
    haystack = " ".join(
        filter(
            None,
            (
                attr_map.get("class", ""),
                attr_map.get("id", ""),
                attr_map.get("itemprop", ""),
                attr_map.get("data-testid", ""),
            ),
        )
    ).lower()
    if not haystack:
        return False

    positive = (
        "articletext",
        "article-text",
        "article_text",
        "articlebody",
        "article-body",
        "article_body",
        "articlecontent",
        "article-content",
        "article_content",
        "article-card-text",
        "news-text",
        "news_content",
        "storytext",
        "story-text",
        "post-content",
        "entry-content",
        "material-content",
        "contentbody",
        "content-body",
        "bodytext",
        "textcontainer",
        "text-container",
    )
    negative = (
        "card",
        "cards",
        "container",
        "preview",
        "related",
        "recommend",
        "comment",
        "share",
        "tag",
        "author",
        "breadcrumb",
        "pagination",
    )
    return any(term in haystack for term in positive) and not any(term in haystack for term in negative)


def _normalize_article_text(value: str) -> str:
    cleaned = _normalize_whitespace(value)
    cleaned = re.sub(r"\s+(?=[,.;:!?])", "", cleaned)
    return cleaned


def _split_article_text(value: str) -> list[str]:
    if not value:
        return []
    chunks = re.split(r"(?<=[.!?])\s+(?=[А-ЯA-Z«\"0-9])", value)
    paragraphs: list[str] = []
    current: list[str] = []
    current_len = 0
    for chunk in chunks:
        cleaned = chunk.strip()
        if not cleaned:
            continue
        current.append(cleaned)
        current_len += len(cleaned)
        if current_len >= 180:
            paragraphs.append(" ".join(current))
            current = []
            current_len = 0
    if current:
        paragraphs.append(" ".join(current))
    return [paragraph for paragraph in paragraphs if len(paragraph) >= 40]


def _dedupe_article_paragraphs(paragraphs: list[str]) -> list[str]:
    unique: list[str] = []
    normalized_seen: list[str] = []

    for paragraph in paragraphs:
        normalized = _normalize_dedupe_text(paragraph)
        if not normalized:
            continue

        is_duplicate = False
        for seen in normalized_seen:
            if normalized == seen:
                is_duplicate = True
                break
            if normalized in seen and len(normalized) >= int(len(seen) * 0.7):
                is_duplicate = True
                break
            if seen in normalized and len(seen) >= int(len(normalized) * 0.7):
                is_duplicate = True
                break
            if _text_overlap_ratio(normalized, seen) >= 0.9:
                is_duplicate = True
                break

        if is_duplicate:
            continue

        unique.append(paragraph)
        normalized_seen.append(normalized)

    return unique


def _normalize_dedupe_text(value: str) -> str:
    cleaned = _normalize_whitespace(value).lower()
    cleaned = cleaned.replace("ё", "е")
    cleaned = re.sub(r"[^\w\sа-яa-z0-9]", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _text_overlap_ratio(left: str, right: str) -> float:
    left_tokens = {token for token in left.split() if len(token) > 2}
    right_tokens = {token for token in right.split() if len(token) > 2}
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    baseline = min(len(left_tokens), len(right_tokens))
    if baseline == 0:
        return 0.0
    return intersection / baseline


def _serialize_ai_discovery_payload(source: SourceItem, discovered_items: list[object]) -> str:
    return (
        f'{{"source_type":"ai_research","source_key":{json.dumps(source.key)},'
        f'"source_url":{json.dumps(source.url)},"item_count":{len(discovered_items)}}}'
    )


def _serialize_sitemap_payload(source: SourceItem, source_type: str, item_count: int) -> str:
    return (
        "{"
        f'"source_type":{json.dumps(source_type)},'
        f'"source_key":{json.dumps(source.key)},'
        f'"source_url":{json.dumps(source.url)},'
        f'"item_count":{item_count}'
        "}"
    )


def _fetch_remote_document(url: str, timeout: int) -> str:
    try:
        with urlopen(url, timeout=timeout) as response:
            if getattr(response, "status", 200) >= 400:
                raise SourceFetchError(f"Fetch failed for {url}: HTTP {response.status}")
            payload = response.read()
    except HTTPError as exc:
        raise SourceFetchError(f"Fetch failed for {url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise SourceFetchError(f"Fetch failed for {url}: {exc.reason if hasattr(exc, 'reason') else exc}") from exc

    return payload.decode("utf-8", errors="ignore")


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _find_child(node: ElementTree.Element | None, names: set[str]) -> ElementTree.Element | None:
    if node is None:
        return None
    wanted = {name.lower() for name in names}
    for child in node:
        if _xml_local_name(child.tag) in wanted:
            return child
    return None


def _find_child_text(node: ElementTree.Element | None, names: set[str]) -> str | None:
    child = _find_child(node, names)
    return _node_text(child)


def _extract_time_hint(attr_map: dict[str, str]) -> datetime | None:
    candidate_keys = (
        "datetime",
        "data-datetime",
        "data-date",
        "data-published",
        "data-published-at",
        "data-created-at",
    )
    for key in candidate_keys:
        value = _normalize_whitespace(attr_map.get(key, ""))
        if not value:
            continue
        parsed = _try_parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _container_score(tag: str, attr_map: dict[str, str]) -> int:
    score = 0
    if tag in {"article", "main", "section", "li", "h2", "h3", "h4"}:
        score += 1

    haystack = " ".join(
        filter(
            None,
            (
                attr_map.get("class", ""),
                attr_map.get("id", ""),
                attr_map.get("data-testid", ""),
            ),
        )
    ).lower()

    if any(term in haystack for term in POSITIVE_CONTAINER_TERMS):
        score += 1
    if any(term in haystack for term in NEGATIVE_CONTAINER_TERMS):
        score -= 2

    return score


def _article_container_score(tag: str, attr_map: dict[str, str]) -> int:
    score = 0
    if tag in {"article", "main", "section", "div"}:
        score += 1

    haystack = " ".join(
        filter(
            None,
            (
                attr_map.get("class", ""),
                attr_map.get("id", ""),
                attr_map.get("itemprop", ""),
                attr_map.get("role", ""),
            ),
        )
    ).lower()

    if any(term in haystack for term in ARTICLE_CONTAINER_TERMS):
        score += 2
    if any(term in haystack for term in ARTICLE_NEGATIVE_TERMS):
        score -= 3

    return score


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


def _looks_like_listing_text(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    if not normalized:
        return False

    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if len(lines) >= 4:
        list_like_lines = sum(
            1
            for line in lines
            if re.match(r"^\d{1,2}:\d{2}\s+", line) and "|" in line
        )
        if list_like_lines >= 3:
            return True

    compact = " ".join(normalized.split())
    matches = re.findall(r"\b\d{1,2}:\d{2}\b.*?\|\s*\d+", compact)
    return len(matches) >= 3


def _looks_like_translit_slug_title(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    if re.search(r"[А-Яа-я]", normalized):
        return False
    words = re.findall(r"[a-z0-9]+", normalized.lower())
    if len(words) < 4:
        return False
    translit_patterns = (
        "zh",
        "shh",
        "sh",
        "kh",
        "ts",
        "ch",
        "ya",
        "yu",
        "yo",
        "cz",
    )
    translit_word_count = sum(
        1 for word in words if any(pattern in word for pattern in translit_patterns)
    )
    if translit_word_count >= 2:
        return True

    translit_markers = {
        "povyol",
        "kubka",
        "stenli",
        "zabili",
        "golu",
        "vyshel",
        "chempionov",
        "rossiya",
        "futbol",
        "khokkey",
        "rolan",
        "garros",
        "ukrainskih",
        "diskvalificzirovala",
        "korrupcziyu",
        "tennisisty",
        "ogranichat",
        "obshhenie",
    }
    return any(marker in words for marker in translit_markers)


def _resolve_enriched_raw_headline(
    current_title: str,
    current_summary: str,
    extracted_title: str | None,
    extracted_lead: str | None,
    extracted_full_text: str | None,
) -> tuple[str | None, str | None]:
    current_title_has_cyrillic = bool(re.search(r"[А-Яа-я]", current_title or ""))
    current_summary_has_cyrillic = bool(re.search(r"[А-Яа-я]", current_summary or ""))
    if current_title_has_cyrillic and current_summary_has_cyrillic:
        return None, None

    candidate_title = (extracted_title or "").strip()
    candidate_lead = (extracted_lead or "").strip()
    candidate_full_text = (extracted_full_text or "").strip()

    if candidate_title and re.search(r"[А-Яа-я]", candidate_title):
        resolved_title = candidate_title
    elif candidate_lead and re.search(r"[А-Яа-я]", candidate_lead):
        resolved_title = candidate_lead.split(". ", 1)[0].strip().rstrip(".")
    elif candidate_full_text and re.search(r"[А-Яа-я]", candidate_full_text):
        resolved_title = candidate_full_text.split(". ", 1)[0].strip().rstrip(".")
    else:
        return None, None

    if len(resolved_title) < 12:
        return None, None

    resolved_summary = candidate_lead or resolved_title

    next_title = resolved_title if not current_title_has_cyrillic or _looks_like_translit_slug_title(current_title) else None
    next_summary = resolved_summary if not current_summary_has_cyrillic or current_summary.strip() == current_title.strip() else None
    return next_title, next_summary


def _try_parse_datetime(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _node_text(node: ElementTree.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    return node.text.strip()


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)

    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _strip_html(value: str) -> str:
    if "<" not in value:
        return value

    try:
        return " ".join(ElementTree.fromstring(f"<root>{value}</root>").itertext())
    except ElementTree.ParseError:
        return value
