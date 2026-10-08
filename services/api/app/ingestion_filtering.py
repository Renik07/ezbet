from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from .news_candidates import news_rejection_reason
from .models import (
    RawItem,
    SourceSyncState,
)
from .ingestion_types import DEFAULT_INGEST_MAX_ITEM_AGE


def _filter_new_items(
    items: list[RawItem],
    state: SourceSyncState | None,
    source_type: str,
    *,
    known_external_ids: set[str] | None = None,
    known_dedupe_keys: set[str] | None = None,
) -> list[RawItem]:
    fresh_items, _ = _filter_new_items_with_reasons(
        items,
        state,
        source_type,
        known_external_ids=known_external_ids,
        known_dedupe_keys=known_dedupe_keys,
    )
    return fresh_items


def _add_filter_reason(reasons: dict[str, int], reason: str, count: int = 1) -> None:
    if count <= 0:
        return
    reasons[reason] = reasons.get(reason, 0) + count


def _filter_new_items_with_reasons(
    items: list[RawItem],
    state: SourceSyncState | None,
    source_type: str,
    *,
    known_external_ids: set[str] | None = None,
    known_dedupe_keys: set[str] | None = None,
) -> tuple[list[RawItem], dict[str, int]]:
    cutoff = datetime.now(timezone.utc) - DEFAULT_INGEST_MAX_ITEM_AGE
    reasons: dict[str, int] = {}
    eligible = []
    for item in items:
        reason = news_rejection_reason(item)
        if reason:
            _add_filter_reason(reasons, reason)
        else:
            eligible.append(item)
    items = eligible
    original_items = items
    items = [item for item in original_items if item.published_at >= cutoff]
    _add_filter_reason(reasons, "older_than_max_age", len(original_items) - len(items))
    if not items:
        return [], reasons

    known_ids = known_external_ids or set()
    known_keys = known_dedupe_keys or set()
    if state is not None and source_type == "scraping":
        fresh_items: list[RawItem] = []
        for item in items:
            if state.last_external_id and item.external_id == state.last_external_id:
                _add_filter_reason(reasons, "reached_last_external_id", len(items) - len(fresh_items))
                return fresh_items, reasons
            if item.external_id in known_ids:
                _add_filter_reason(reasons, "known_external_id", len(items) - len(fresh_items))
                return fresh_items, reasons
            if item.dedupe_key in known_keys:
                _add_filter_reason(reasons, "known_dedupe_key", len(items) - len(fresh_items))
                return fresh_items, reasons
            fresh_items.append(item)
        return fresh_items, reasons

    if state is None or state.last_published_at is None:
        return items, reasons

    last_published_at = state.last_published_at
    last_external_id = state.last_external_id

    if source_type in {"rss", "news_sitemap"} and _items_look_descending_by_freshness(items):
        fresh_items: list[RawItem] = []
        for item in items:
            if last_external_id is not None and item.external_id == last_external_id:
                _add_filter_reason(reasons, "reached_last_external_id", len(items) - len(fresh_items))
                break

            if item.external_id in known_ids:
                _add_filter_reason(reasons, "known_external_id", len(items) - len(fresh_items))
                break

            if item.dedupe_key in known_keys:
                _add_filter_reason(reasons, "known_dedupe_key", len(items) - len(fresh_items))
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
                _add_filter_reason(reasons, "not_newer_than_last_published", len(items) - len(fresh_items))
                break

        if fresh_items:
            return fresh_items, reasons

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
            continue

        _add_filter_reason(reasons, "not_newer_than_last_published")

    return fresh_items, reasons


def _items_look_descending_by_freshness(items: list[RawItem]) -> bool:
    if len(items) < 2:
        return True

    previous = items[0].published_at
    for item in items[1:]:
        if item.published_at > previous:
            return False
        previous = item.published_at
    return True

