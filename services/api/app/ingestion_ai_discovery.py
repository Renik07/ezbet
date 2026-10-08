from __future__ import annotations

import json
from datetime import (
    datetime,
    timezone,
)
from .ai_client import OpenAIEditorialClient
from .models import (
    PromptConfig,
    RawItem,
    SourceItem,
)
from .ingestion_scoring import _build_raw_item
from .ingestion_scraping import _discover_ai_research_candidates_from_listing
from .ingestion_text import _try_parse_datetime
from .ingestion_types import SourceFetchError


def _parse_ai_research_source(
    source: SourceItem,
    timeout: int,
    ai_search_prompt: PromptConfig | None = None,
    allow_listing_fallback: bool = True,
) -> list[RawItem]:
    ai_client = OpenAIEditorialClient()
    if not ai_client.enabled:
        raise SourceFetchError("AI search source requires an enabled OpenAI Responses client.")

    discovered = ai_client.discover_source_items(source, limit=5, prompt=ai_search_prompt)
    if not discovered and allow_listing_fallback:
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


def _serialize_ai_discovery_payload(source: SourceItem, discovered_items: list[object]) -> str:
    return (
        f'{{"source_type":"ai_research","source_key":{json.dumps(source.key)},'
        f'"source_url":{json.dumps(source.url)},"item_count":{len(discovered_items)}}}'
    )

