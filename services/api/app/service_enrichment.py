from __future__ import annotations

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from datetime import (
    datetime,
    timezone,
)
from fastapi import Query
from .ingestion import enrich_raw_item_content
from .models import (
    EnrichmentRunResponse,
    RawItem,
)
from .planner import select_pre_enrichment_candidates
from . import runtime
from .runtime import (
    ENRICHMENT_WEB_SEARCH_CAP_PER_RUN,
    logger,
)
from .pipeline_logging import (
    _current_ingest_started_at,
    _duration_ms,
    _log_pipeline_event,
    _run_id,
)


def run_enrichment(limit: int = Query(default=10, ge=1, le=50)) -> EnrichmentRunResponse:
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("enrichment")
    _log_pipeline_event(
        "run_started",
        phase="enrichment",
        run_id=run_id,
        trigger="manual",
        status="running",
        counts={"limit": limit},
    )
    current_ingest_started_at = _current_ingest_started_at()
    raw_items = _select_pre_enrichment_raw_items(limit=limit, since=None)
    try:
        processed, enriched = _run_enrichment_for_raw_items(raw_items)
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        runtime.repository.record_pipeline_run(
            run_id=run_id,
            phase="enrichment",
            trigger="manual",
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            processed_count=processed,
            enriched_count=enriched,
        )
        _log_pipeline_event(
            "run_finished",
            phase="enrichment",
            run_id=run_id,
            trigger="manual",
            status="ok",
            duration_ms=duration_ms,
            counts={
                "processed": processed,
                "enriched": enriched,
                "current_ingest_started_at": current_ingest_started_at.isoformat() if current_ingest_started_at else None,
            },
        )
        return EnrichmentRunResponse(processed=processed, enriched=enriched)
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        runtime.repository.record_pipeline_run(
            run_id=run_id,
            phase="enrichment",
            trigger="manual",
            status="error",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            error=str(exc),
        )
        _log_pipeline_event(
            "run_failed",
            phase="enrichment",
            run_id=run_id,
            trigger="manual",
            status="error",
            error_reason=str(exc),
            duration_ms=duration_ms,
        )
        raise


def _run_ingestion_enrichment(raw_items: list[RawItem]) -> None:
    batch_size = max(1, runtime.repository.get_enrichment_scheduler_settings().batch_size)
    shortlist = select_pre_enrichment_candidates(raw_items, limit=batch_size)
    _log_pipeline_event(
        "pre_enrichment_shortlist",
        phase="ingest",
        status="ok",
        counts={
            "candidate_pool": len(raw_items),
            "selected": len(shortlist),
            "batch_size": batch_size,
        },
    )
    _run_enrichment_for_raw_items(shortlist)


def _select_pre_enrichment_raw_items(*, limit: int, since: datetime | None) -> list[RawItem]:
    pool_limit = max(limit * 3, limit)
    candidate_pool = runtime.repository.list_pending_enrichment_raw_items(limit=pool_limit, since=since)
    return select_pre_enrichment_candidates(candidate_pool, limit=limit)


def _run_enrichment_for_raw_items(raw_items: list[RawItem]) -> tuple[int, int]:
    candidate_items = [item for item in raw_items if not item.is_duplicate]
    candidate_ids = [item.id for item in candidate_items]
    if not candidate_ids:
        _log_pipeline_event(
            "batch_skipped",
            phase="enrichment",
            status="skipped",
            error_reason="no_non_duplicate_candidates",
        )
        return (0, 0)
    web_search_budget_ids = {
        item.id
        for item in sorted(
            (
                item
                for item in candidate_items
                if item.triage_label in {"high", "medium"}
            ),
            key=lambda item: (item.importance_score, item.published_at),
            reverse=True,
        )[:ENRICHMENT_WEB_SEARCH_CAP_PER_RUN]
    }
    _log_pipeline_event(
        "batch_started",
        phase="enrichment",
        status="running",
        counts={"candidates": len(candidate_ids)},
    )
    _log_pipeline_event(
        "web_search_budget",
        phase="enrichment",
        status="ok",
        counts={
            "cap": ENRICHMENT_WEB_SEARCH_CAP_PER_RUN,
            "eligible": len(web_search_budget_ids),
        },
    )
    enriched_count = 0

    def enrich_one(raw_item_id: str) -> None:
        nonlocal enriched_count
        raw_item = runtime.repository.get_raw_item(raw_item_id)
        if raw_item is None or raw_item.is_duplicate:
            return
        before_has_any = bool((raw_item.full_text or "").strip() or (raw_item.lead or "").strip() or raw_item.tags)
        try:
            enrich_raw_item_content(
                runtime.repository,
                raw_item,
                allow_web_search_fallback=raw_item_id in web_search_budget_ids,
            )
            updated_item = runtime.repository.get_raw_item(raw_item_id)
            if updated_item is not None and not updated_item.is_duplicate:
                deduped_item = runtime.repository.recheck_raw_item_duplicate_after_enrichment(raw_item_id)
                if deduped_item is not None:
                    updated_item = deduped_item
            after_has_any = bool(
                updated_item
                and (
                    (updated_item.full_text or "").strip()
                    or (updated_item.lead or "").strip()
                    or updated_item.tags
                )
            )
            if after_has_any and not before_has_any:
                enriched_count += 1
            if updated_item is not None and updated_item.is_duplicate:
                _log_pipeline_event(
                    "duplicate_detected",
                    phase="enrichment",
                    source=raw_item.source_key,
                    status="ok",
                    counts={"enriched_count": enriched_count},
                    raw_item_id=raw_item_id,
                    duplicate_of=updated_item.duplicate_of,
                )
            _log_pipeline_event(
                "item_finished",
                phase="enrichment",
                source=raw_item.source_key,
                status="ok",
                counts={"enriched_count": enriched_count},
                raw_item_id=raw_item_id,
                enrichment_status=updated_item.enrichment_status if updated_item else None,
            )
        except Exception as exc:
            runtime.repository.update_raw_item_enrichment(
                raw_item_id,
                enrichment_status="enrichment_error",
                enrichment_error=f"Enrichment pipeline failed: {exc}",
            )
            _log_pipeline_event(
                "item_failed",
                phase="enrichment",
                source=raw_item.source_key,
                status="error",
                error_reason=str(exc),
                raw_item_id=raw_item_id,
            )
            logger.exception("Enrichment failed: raw_item_id=%s error=%s", raw_item_id, exc)

    max_workers = min(4, len(candidate_ids))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(enrich_one, raw_item_id) for raw_item_id in candidate_ids]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                # Keep source ingestion resilient even if one full-text enrichment path fails.
                continue
    _log_pipeline_event(
        "batch_finished",
        phase="enrichment",
        status="ok",
        counts={"candidates": len(candidate_ids), "enriched": enriched_count},
    )
    return (len(candidate_ids), enriched_count)

