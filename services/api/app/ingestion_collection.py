from __future__ import annotations

from typing import Iterable
from urllib.parse import (
    urlsplit,
    urlunsplit,
)
from .models import (
    NewsItem,
    PromptConfig,
    RawItem,
    SourceItem,
    SourceSyncState,
)
from .ingestion_ai_discovery import _parse_ai_research_source
from .ingestion_feeds import _parse_feed
from .ingestion_filtering import _filter_new_items_with_reasons
from .ingestion_scraping import _parse_scraping_source
from .ingestion_sitemaps import (
    _is_allowed_championat_news_url,
    _is_championat_source,
    _parse_news_sitemap_source,
    _parse_sitemap_source,
)
from .ingestion_text import _should_drop_raw_item_as_service_page
from .ingestion_types import (
    SourceFetchError,
    SourceIngestionResult,
)


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
        try:
            source_result = _collect_source_items_with_retry(
                runtime_source,
                timeout=timeout,
                max_retries=max_retries,
                ai_search_prompt=ai_search_prompt,
            )
            collected_items = source_result.items
            filtered_items, filter_reasons = _filter_new_items_with_reasons(
                collected_items,
                source_state,
                runtime_source.source_type,
                known_external_ids=known_external_ids_map.get(source.key, set()),
                known_dedupe_keys=known_dedupe_keys_map.get(source.key, set()),
            )
            collection_reasons = source_result.filter_reasons or {}
            source_result.filter_reasons = dict(collection_reasons)
            for reason, count in filter_reasons.items():
                source_result.filter_reasons[reason] = (
                    source_result.filter_reasons.get(reason, 0) + count
                )
        except Exception as exc:
            source_result = SourceIngestionResult(
                source=runtime_source,
                items=[],
                fetch_status="error",
                parse_status="idle",
                error=f"Unhandled source ingestion error: {exc}",
                retry_count=max_retries,
                filter_reasons={},
            )
            filtered_items = []
        if limit is not None and limit_per_source:
            if len(filtered_items) > limit:
                source_result.filter_reasons = dict(source_result.filter_reasons or {})
                source_result.filter_reasons["batch_limit"] = (
                    source_result.filter_reasons.get("batch_limit", 0) + len(filtered_items) - limit
                )
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


def _collect_source_items_with_retry(
    source: SourceItem,
    *,
    timeout: int,
    max_retries: int,
    ai_search_prompt: PromptConfig | None = None,
) -> SourceIngestionResult:
    attempts = 0
    last_error: str | None = None
    ai_fallback_attempted = False

    while attempts <= max_retries:
        attempts += 1
        try:
            items = _collect_source_items(source, timeout=timeout, ai_search_prompt=ai_search_prompt)
        except SourceFetchError as exc:
            last_error = str(exc)
            if not ai_fallback_attempted:
                ai_fallback_attempted = True
                fallback_items = _collect_source_items_via_ai_fallback(
                    source,
                    timeout=timeout,
                    ai_search_prompt=ai_search_prompt,
                )
                if fallback_items:
                    return SourceIngestionResult(
                        source=source,
                        items=fallback_items,
                        fetch_status="ok",
                        parse_status="ok",
                        error=None,
                        retry_count=attempts - 1,
                        filter_reasons={"source_fetch_ai_fallback": len(fallback_items)},
                    )

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
        if not ai_fallback_attempted:
            ai_fallback_attempted = True
            fallback_items = _collect_source_items_via_ai_fallback(
                source,
                timeout=timeout,
                ai_search_prompt=ai_search_prompt,
            )
            if fallback_items:
                return SourceIngestionResult(
                    source=source,
                    items=fallback_items,
                    fetch_status="ok",
                    parse_status="ok",
                    error=None,
                    retry_count=attempts - 1,
                    filter_reasons={"source_empty_ai_fallback": len(fallback_items)},
                )

    return SourceIngestionResult(
        source=source,
        items=[],
        fetch_status="ok",
        parse_status="empty",
        error=last_error,
        retry_count=max_retries,
    )


def _collect_source_items_via_ai_fallback(
    source: SourceItem,
    *,
    timeout: int,
    ai_search_prompt: PromptConfig | None,
) -> list[RawItem]:
    if source.source_type == "ai_research" or not _is_championat_source(source):
        return []

    parts = urlsplit(source.url)
    if not parts.scheme or not parts.netloc:
        return []

    fallback_source = source.model_copy(
        update={
            "source_type": "ai_research",
            "url": urlunsplit((parts.scheme, parts.netloc, "/news/", "", "")),
            "notes": (
                f"{source.notes.strip()}\n"
                "Ищи только свежие спортивные новости Championat.com. "
                "Не включай розыгрыши, рекламу, трансляции и неспортивные разделы."
            ).strip(),
        }
    )

    try:
        items = _parse_ai_research_source(
            fallback_source,
            timeout=timeout,
            ai_search_prompt=ai_search_prompt,
            allow_listing_fallback=False,
        )
    except (SourceFetchError, ValueError):
        return []

    return [
        item
        for item in items
        if _is_allowed_championat_news_url(item.url or item.source_url)
        and not _should_drop_raw_item_as_service_page(item)
    ]


def _collect_source_items(
    source: SourceItem,
    timeout: int,
    ai_search_prompt: PromptConfig | None = None,
) -> list[RawItem]:
    items: list[RawItem]
    if source.source_type == "rss":
        items = _parse_feed(source, timeout=timeout)
    elif source.source_type == "news_sitemap":
        items = _parse_news_sitemap_source(source, timeout=timeout)
    elif source.source_type == "sitemap":
        items = _parse_sitemap_source(source, timeout=timeout)
    elif source.source_type == "scraping":
        items = _parse_scraping_source(source, timeout=timeout)
    elif source.source_type == "ai_research":
        items = _parse_ai_research_source(source, timeout=timeout, ai_search_prompt=ai_search_prompt)
    else:
        items = []

    return [item for item in items if not _should_drop_raw_item_as_service_page(item)]

