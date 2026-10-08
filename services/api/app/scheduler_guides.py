from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from .ai_client import OpenAIEditorialClient
from .models import GuideSchedulerRunResponse
from . import runtime
from .runtime import (
    GUIDE_SCHEDULER_LOCK_KEY,
    logger,
)
from .pipeline_logging import (
    _duration_ms,
    _log_pipeline_event,
    _run_id,
)


def _run_guide_scheduler() -> GuideSchedulerRunResponse:
    started_at = datetime.now(timezone.utc)
    run_id = _run_id("guide")
    _log_pipeline_event(
        "scheduler_tick",
        phase="guide",
        run_id=run_id,
        trigger="run",
        status="starting",
    )

    with runtime.repository.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (GUIDE_SCHEDULER_LOCK_KEY,))
            row = cursor.fetchone()
            locked = bool(row and row[0])

        if not locked:
            _log_pipeline_event(
                "scheduler_skipped",
                phase="guide",
                run_id=run_id,
                trigger="run",
                status="skipped",
                error_reason="locked",
            )
            return GuideSchedulerRunResponse(ran=False, reason="locked")

        topic = None
        try:
            topic = runtime.repository.claim_next_guide_topic()
            if topic is None:
                finished_at = datetime.now(timezone.utc)
                runtime.repository.record_pipeline_run(
                    run_id=run_id,
                    phase="guide",
                    trigger="scheduler",
                    status="ok",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=_duration_ms(started_at, finished_at),
                )
                return GuideSchedulerRunResponse(ran=False, reason="no_planned_topics")

            prompt = runtime.repository.get_active_prompt("guide_writer")
            guide_editor_prompt = runtime.repository.get_active_prompt("guide_editor")
            generated = OpenAIEditorialClient().generate_guide_article(topic, prompt, guide_editor_prompt)
            if generated is None:
                raise RuntimeError("Guide writer did not return a valid article.")

            article = runtime.repository.publish_guide_article(
                topic=topic,
                title=generated.title,
                dek=generated.dek,
                body=generated.body,
                model=generated.model,
                generation_mode=generated.generation_mode,
                prompt=prompt,
            )
            stored_topic = runtime.repository.get_guide_topic(topic.id) or topic
            finished_at = datetime.now(timezone.utc)
            runtime.repository.record_pipeline_run(
                run_id=run_id,
                phase="guide",
                trigger="scheduler",
                status="ok",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                generated_count=1,
                published_count=1,
            )
            _log_pipeline_event(
                "scheduler_run_finished",
                phase="guide",
                run_id=run_id,
                trigger="run",
                status="ok",
                duration_ms=_duration_ms(started_at, finished_at),
                counts={"generated": 1, "published": 1},
                topic_number=topic.topic_number,
                article_slug=article.slug,
            )
            return GuideSchedulerRunResponse(
                ran=True,
                reason="ok",
                generated=1,
                published=1,
                topic=stored_topic,
                article=article,
            )
        except Exception as exc:
            if topic is not None:
                runtime.repository.mark_guide_topic_error(topic.id, str(exc))
            finished_at = datetime.now(timezone.utc)
            runtime.repository.record_pipeline_run(
                run_id=run_id,
                phase="guide",
                trigger="scheduler",
                status="error",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_duration_ms(started_at, finished_at),
                error=str(exc),
            )
            _log_pipeline_event(
                "scheduler_run_failed",
                phase="guide",
                run_id=run_id,
                trigger="run",
                status="error",
                error_reason=str(exc),
                duration_ms=_duration_ms(started_at, finished_at),
            )
            logger.exception("Guide scheduler failed: %s", exc)
            raise
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (GUIDE_SCHEDULER_LOCK_KEY,))

