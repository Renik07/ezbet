from __future__ import annotations
from .news_budget import NEWS_HOURLY_LIMIT
from .news_candidates import news_rejection_reason

from datetime import (
    datetime,
    timezone,
)
from fastapi import Query
from .content_filters import detect_promotional_giveaway
from .editorial import evaluate_published_duplicate_guard
from .models import PublishRunResponse
from . import runtime
from .runtime import PUBLISH_EXECUTION_LOCK_KEY
from .pipeline_logging import (
    _duration_ms,
    _log_pipeline_event,
    _run_id,
)


def run_publish(limit: int = Query(default=5, ge=1, le=20)) -> PublishRunResponse:
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("publish")
    _log_pipeline_event(
        "run_started",
        phase="publish",
        run_id=run_id,
        trigger="manual",
        status="running",
        counts={"limit": limit},
    )
    try:
        published = _run_publish_for_drafts(limit=limit, since=None)
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        runtime.repository.record_pipeline_run(
            run_id=run_id,
            phase="publish",
            trigger="manual",
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            published_count=published,
        )
        _log_pipeline_event(
            "run_finished",
            phase="publish",
            run_id=run_id,
            trigger="manual",
            status="ok",
            duration_ms=duration_ms,
            counts={"published": published},
        )
        return PublishRunResponse(published=published)
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        duration_ms = _duration_ms(started_at, finished_at)
        runtime.repository.record_pipeline_run(
            run_id=run_id,
            phase="publish",
            trigger="manual",
            status="error",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            error=str(exc),
        )
        _log_pipeline_event(
            "run_failed",
            phase="publish",
            run_id=run_id,
            trigger="manual",
            status="error",
            error_reason=str(exc),
            duration_ms=duration_ms,
        )
        raise


def _run_publish_for_drafts(*, limit: int, since: datetime | None = None) -> int:
    # Shared by manual and scheduled callers, across API processes.
    with runtime.repository.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", (PUBLISH_EXECUTION_LOCK_KEY,))
            if not cursor.fetchone()[0]:
                return 0
        return _publish_ready_drafts(limit=limit, since=since)


def _publish_ready_drafts(*, limit: int, since: datetime | None = None) -> int:
    drafts = runtime.repository.list_publishable_drafts(limit=min(NEWS_HOURLY_LIMIT, limit), since=since)
    published = 0

    for draft in drafts:
        raw_item = runtime.repository.get_raw_item(draft.raw_item_id)
        if raw_item is None:
            continue
        rejection = news_rejection_reason(raw_item)
        if rejection:
            runtime.repository.set_draft_review_status(draft.id, review_status="quality_hold", status="hold",
                review_summary=rejection, publish_decision="publish_skip", publish_reason=rejection)
            runtime.repository.set_content_plan_status(raw_item.id, "hold")
            continue
        promotional_marker = detect_promotional_giveaway(
            raw_item.title,
            raw_item.summary,
            raw_item.lead,
            raw_item.full_text,
            draft.title,
            draft.dek,
            draft.body,
        )
        if promotional_marker is not None:
            reason = f"Publish guard: промо-розыгрыш запрещен ({promotional_marker})."
            runtime.repository.set_draft_review_status(
                draft.id,
                review_status="quality_hold",
                status="hold",
                review_summary=reason,
                publish_decision="publish_skip",
                publish_reason=reason,
            )
            runtime.repository.set_content_plan_status(raw_item.id, "hold")
            continue
        candidates = runtime.repository.list_article_similarity_candidates(
            category=None,
            published_at=datetime.now(timezone.utc),
            exclude_news_item_id=raw_item.external_id,
            window_hours=48,
            limit=None,
        )
        duplicate_guard = evaluate_published_duplicate_guard(draft, candidates)
        if raw_item.is_duplicate or duplicate_guard is not None:
            reason = raw_item.duplicate_reason or (
                duplicate_guard.reason if duplicate_guard
                else "Publish guard: исходная новость отмечена дублем."
            )
            runtime.repository.set_draft_review_status(
                draft.id, review_status="quality_hold", status="hold",
                review_summary=reason, publish_decision="publish_hold", publish_reason=reason,
            )
            runtime.repository.set_content_plan_status(raw_item.id, "hold")
            continue
        runtime.repository.publish_draft_to_news(draft, raw_item)
        published += 1

    if published:
        runtime.repository.sync_news_ai_review_flags()

    return published

