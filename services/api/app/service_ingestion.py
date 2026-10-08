from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from typing import Optional
from fastapi import Query
from .ingestion import (
    ingest_sources_with_results,
    raw_items_to_news,
)
from .models import IngestResponse
from . import runtime
from .pipeline_logging import (
    _duration_ms,
    _log_pipeline_event,
    _run_id,
)
from .service_enrichment import (
    _run_ingestion_enrichment,
    run_enrichment,
)


def ingest_demo() -> IngestResponse:
    items = runtime.repository.ingest_demo_batch()
    return IngestResponse(
        ingested=len(items),
        published=len(items),
        items=items,
        raw_items=0,
    )


def ingest_rss(limit: Optional[int] = Query(default=None, ge=1, le=50)) -> IngestResponse:
    return _run_source_ingestion(limit)


def ingest_sources(
    limit: Optional[int] = Query(default=None, ge=1, le=50),
    per_source: bool = Query(default=False, alias="perSource"),
) -> IngestResponse:
    return _run_source_ingestion(limit, per_source=per_source)


def _run_source_ingestion(
    limit: Optional[int],
    *,
    per_source: bool = False,
    run_enrichment: bool = True,
    trigger: str = "manual",
) -> IngestResponse:
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("ingest")
    sources = runtime.repository.list_active_sources()
    _log_pipeline_event(
        "run_started",
        phase="ingest",
        run_id=run_id,
        trigger=trigger,
        status="running",
        counts={"active_sources": len(sources)},
        limit=limit or 0,
        per_source=per_source,
        run_enrichment=run_enrichment,
    )
    try:
        ai_search_prompt = runtime.repository.get_active_prompt("ai_search")
        source_keys = [source.key for source in sources]
        known_external_ids_by_source = runtime.repository.get_recent_known_external_ids_by_source(
            source_keys
        )
        known_dedupe_keys_by_source = runtime.repository.get_recent_known_dedupe_keys_by_source(
            source_keys
        )
        raw_items, source_results = ingest_sources_with_results(
            sources,
            runtime.repository.get_source_sync_state_map(),
            known_external_ids_by_source=known_external_ids_by_source,
            known_dedupe_keys_by_source=known_dedupe_keys_by_source,
            limit=limit,
            limit_per_source=per_source,
            ai_search_prompt=ai_search_prompt,
        )
        prefilter_result = runtime.repository.prefilter_known_raw_items(raw_items)
        raw_items = prefilter_result.fresh_items
        _log_pipeline_event(
            "source_collection_completed",
            phase="ingest",
            run_id=run_id,
            trigger=trigger,
            status="ok",
            counts={
                "total_candidates": len(raw_items) + len(prefilter_result.skipped_items),
                "fresh_after_prefilter": len(raw_items),
                "source_results": len(source_results),
            },
        )
        insert_result = runtime.repository.insert_raw_items(raw_items)
        inserted_raw_items = insert_result.inserted_count
        _log_pipeline_event(
            "raw_items_inserted",
            phase="ingest",
            run_id=run_id,
            trigger=trigger,
            status="ok",
            counts={"inserted": inserted_raw_items},
        )
        if run_enrichment:
            _run_ingestion_enrichment(raw_items)
            _log_pipeline_event(
                "ingestion_enrichment_completed",
                phase="ingest",
                run_id=run_id,
                trigger=trigger,
                status="ok",
                counts={"candidate_items": len(raw_items)},
            )
        else:
            _log_pipeline_event(
                "ingestion_enrichment_skipped",
                phase="ingest",
                run_id=run_id,
                trigger=trigger,
                status="skipped",
                error_reason="run_enrichment_disabled",
            )
        for result in source_results:
            source_items = [item for item in raw_items if item.source_key == result.source.key]
            _log_pipeline_event(
                "source_result",
                phase="ingest",
                run_id=run_id,
                source=result.source.key,
                trigger=trigger,
                status="ok" if not result.error else "error",
                error_reason=result.error,
                counts={
                    "parsed": len(result.items),
                    "fresh": len(source_items),
                    "filtered": max(0, len(result.items) - len(source_items)),
                    "filter_reasons": result.filter_reasons or {},
                    "retry_count": result.retry_count,
                },
                fetch_status=result.fetch_status,
                parse_status=result.parse_status,
            )
            runtime.repository.update_source_sync_state(
                result.source,
                source_items,
                fetch_status=result.fetch_status,
                parse_status=result.parse_status,
                error=result.error,
                retry_count=result.retry_count,
            )
        published = runtime.repository.upsert_many(raw_items_to_news(raw_items))
        runtime.repository.sync_news_ai_review_flags()
        skipped_items = _merge_skipped_ingest_items(
            prefilter_result.skipped_items,
            insert_result.skipped_items,
            [
                {
                    "title": item.title,
                    "reason": item.duplicate_reason or "Новость отсечена как дубль и не попала в ленту.",
                }
                for item in raw_items
                if item.is_duplicate
            ],
        )
        total_parsed_items = sum(len(result.items) for result in source_results)
        source_breakdown = [
            {
                "source_key": result.source.key,
                "source_title": result.source.title,
                "found_count": len(result.items),
                "parsed_count": len(result.items),
                "fresh_count": len([item for item in raw_items if item.source_key == result.source.key]),
                "filtered_count": max(
                    0,
                    len(result.items) - len([item for item in raw_items if item.source_key == result.source.key]),
                ),
                "filter_reasons": result.filter_reasons or {},
            }
            for result in source_results
        ]
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        runtime.repository.record_pipeline_run(
            run_id=run_id,
            phase="ingest",
            trigger=trigger,
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            found_count=total_parsed_items,
            saved_count=inserted_raw_items,
            published_count=len(published),
            skipped_items=skipped_items,
            source_breakdown=source_breakdown,
        )
        _log_pipeline_event(
            "run_finished",
            phase="ingest",
            run_id=run_id,
            trigger=trigger,
            status="ok",
            duration_ms=duration_ms,
            counts={
                "raw_items": len(raw_items),
                "parsed": total_parsed_items,
                "inserted": inserted_raw_items,
                "published": len(published),
                "skipped": len(skipped_items),
            },
        )
        return IngestResponse(
            ingested=len(raw_items),
            published=len(published),
            items=published,
            raw_items=inserted_raw_items,
        )
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        runtime.repository.record_pipeline_run(
            run_id=run_id,
            phase="ingest",
            trigger=trigger,
            status="error",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            error=str(exc),
        )
        _log_pipeline_event(
            "run_failed",
            phase="ingest",
            run_id=run_id,
            trigger=trigger,
            status="error",
            error_reason=str(exc),
            duration_ms=duration_ms,
        )
        raise


def _merge_skipped_ingest_items(
    *groups: list[dict[str, str]],
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for group in groups:
        for item in group:
            title = str(item.get("title", "")).strip()
            reason = str(item.get("reason", "")).strip()
            if not title:
                continue
            key = (title, reason)
            if key in seen:
                continue
            seen.add(key)
            merged.append({"title": title, "reason": reason})

    return merged

