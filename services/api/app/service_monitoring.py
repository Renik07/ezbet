from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from .models import (
    IdempotencyCheck,
    IdempotencyReportResponse,
    MonitoringAlert,
    MonitoringQueueSnapshot,
    MonitoringSchedulerState,
    MonitoringStatusResponse,
    RecoveryAction,
    RecoveryStatusResponse,
)
from . import runtime
from .runtime import (
    EDITORIAL_SCHEDULER_LOCK_KEY,
    ENRICHMENT_SCHEDULER_LOCK_KEY,
    PUBLISH_SCHEDULER_LOCK_KEY,
    SCHEDULER_LOCK_KEY,
)
from .pipeline_logging import _log_pipeline_event


def _alert_rank(severity: str) -> int:
    if severity == "critical":
        return 3
    if severity == "warning":
        return 2
    return 1


def _overall_monitoring_status(alerts: list[MonitoringAlert]) -> str:
    if any(alert.severity == "critical" for alert in alerts):
        return "critical"
    if alerts:
        return "warning"
    return "ok"


def _scheduler_stale_threshold_minutes(interval_minutes: int) -> int:
    return max(interval_minutes * 3, interval_minutes + 15)


def _build_scheduler_monitor(
    *,
    phase: str,
    settings: object,
    queue_count: int | None,
    now: datetime,
) -> MonitoringSchedulerState:
    alerts: list[MonitoringAlert] = []
    enabled = bool(getattr(settings, "enabled"))
    interval_minutes = int(getattr(settings, "interval_minutes"))
    last_status = str(getattr(settings, "last_status") or "idle")
    last_run_at = getattr(settings, "last_run_at")
    next_run_at = getattr(settings, "next_run_at")
    last_error = getattr(settings, "last_error")
    batch_size = max(1, int(getattr(settings, "batch_size")))

    if enabled and last_status == "error":
        alerts.append(
            MonitoringAlert(
                severity="critical",
                phase=phase,
                code="scheduler_error",
                message=f"{phase} завершился ошибкой и требует проверки.",
                error_reason=last_error,
            )
        )

    if enabled and last_run_at is None:
        alerts.append(
            MonitoringAlert(
                severity="warning",
                phase=phase,
                code="never_ran",
                message=f"{phase} еще ни разу не запускался после включения.",
            )
        )

    if enabled and last_run_at is not None:
        stale_threshold = _scheduler_stale_threshold_minutes(interval_minutes)
        age_minutes = int((now - last_run_at).total_seconds() // 60)
        if age_minutes > stale_threshold:
            alerts.append(
                MonitoringAlert(
                    severity="critical" if (queue_count or 0) > 0 else "warning",
                    phase=phase,
                    code="stale_run",
                    message=f"{phase} не запускался слишком долго.",
                    observed_value=age_minutes,
                    threshold_value=stale_threshold,
                )
            )

    if queue_count is not None:
        if not enabled and queue_count > 0:
            alerts.append(
                MonitoringAlert(
                    severity="warning",
                    phase=phase,
                    code="queue_while_disabled",
                    message=f"У {phase} есть очередь, но scheduler выключен.",
                    observed_value=queue_count,
                )
            )
        backlog_threshold = max(batch_size * 3, 10)
        if queue_count >= backlog_threshold:
            alerts.append(
                MonitoringAlert(
                    severity="warning",
                    phase=phase,
                    code="queue_backlog",
                    message=f"Очередь {phase} растет быстрее, чем ее успевают разбирать.",
                    observed_value=queue_count,
                    threshold_value=backlog_threshold,
                )
            )

    alerts.sort(key=lambda item: _alert_rank(item.severity), reverse=True)
    return MonitoringSchedulerState(
        phase=phase,
        enabled=enabled,
        healthy=not alerts,
        last_status=last_status,
        last_run_at=last_run_at,
        next_run_at=next_run_at,
        interval_minutes=interval_minutes,
        queue_count=queue_count,
        alerts=alerts,
    )


def _build_monitoring_status() -> MonitoringStatusResponse:
    now = datetime.now(timezone.utc)
    scheduler_settings = runtime.repository.get_scheduler_settings()
    enrichment_settings = runtime.repository.get_enrichment_scheduler_settings()
    editorial_settings = runtime.repository.get_editorial_scheduler_settings()
    publish_settings = runtime.repository.get_publish_scheduler_settings()

    queues = MonitoringQueueSnapshot(
        enrichment=runtime.repository.count_pending_enrichment_raw_items(),
        editorial=runtime.repository.count_planned_raw_items_for_drafts(),
        publish=runtime.repository.count_publishable_drafts(),
    )

    schedulers = [
        _build_scheduler_monitor(
            phase="ingest",
            settings=scheduler_settings,
            queue_count=None,
            now=now,
        ),
        _build_scheduler_monitor(
            phase="enrichment",
            settings=enrichment_settings,
            queue_count=queues.enrichment,
            now=now,
        ),
        _build_scheduler_monitor(
            phase="editorial",
            settings=editorial_settings,
            queue_count=queues.editorial,
            now=now,
        ),
        _build_scheduler_monitor(
            phase="publish",
            settings=publish_settings,
            queue_count=queues.publish,
            now=now,
        ),
    ]

    alerts = [alert for scheduler in schedulers for alert in scheduler.alerts]
    alerts.sort(key=lambda item: _alert_rank(item.severity), reverse=True)
    return MonitoringStatusResponse(
        status=_overall_monitoring_status(alerts),
        generated_at=now,
        queues=queues,
        schedulers=schedulers,
        alerts=alerts,
    )


def _recover_runtime_state(*, trigger: str) -> RecoveryStatusResponse:
    checked_at = datetime.now(timezone.utc)
    actions: list[RecoveryAction] = []
    recovery_plan = [
        ("ingest", runtime.repository.get_scheduler_settings, runtime.repository.recover_scheduler_if_stale),
        ("enrichment", runtime.repository.get_enrichment_scheduler_settings, runtime.repository.recover_enrichment_scheduler_if_stale),
        ("editorial", runtime.repository.get_editorial_scheduler_settings, runtime.repository.recover_editorial_scheduler_if_stale),
        ("publish", runtime.repository.get_publish_scheduler_settings, runtime.repository.recover_publish_scheduler_if_stale),
    ]

    recovery_locks = {
        "ingest": SCHEDULER_LOCK_KEY, "enrichment": ENRICHMENT_SCHEDULER_LOCK_KEY,
        "editorial": EDITORIAL_SCHEDULER_LOCK_KEY, "publish": PUBLISH_SCHEDULER_LOCK_KEY,
    }
    for phase, get_settings, recover_fn in recovery_plan:
        with runtime.repository.connect() as connection:
            locked = connection.execute(
                "SELECT pg_try_advisory_xact_lock(%s)", (recovery_locks[phase],),
            ).fetchone()[0]
            if not locked:
                continue
            settings = get_settings()
            if settings.last_status != "running":
                continue
            recovered_settings = recover_fn()
            action = RecoveryAction(
                phase=phase,
                previous_status="running",
                recovered_status=recovered_settings.last_status,
                message=recovered_settings.last_error or "Recovered stale running status.",
                updated_at=recovered_settings.updated_at,
            )
            actions.append(action)
            _log_pipeline_event(
                "recovery_action",
                phase=phase,
                trigger=trigger,
                status=recovered_settings.last_status,
                error_reason=recovered_settings.last_error,
                updated_at=recovered_settings.updated_at.isoformat() if recovered_settings.updated_at else None,
            )

    if not actions:
        _log_pipeline_event(
            "recovery_check",
            phase="pipeline",
            trigger=trigger,
            status="ok",
            counts={"recovered": 0},
        )
    else:
        _log_pipeline_event(
            "recovery_completed",
            phase="pipeline",
            trigger=trigger,
            status="ok",
            counts={"recovered": len(actions)},
        )

    return RecoveryStatusResponse(
        recovered=bool(actions),
        trigger=trigger,
        checked_at=checked_at,
        actions=actions,
    )


def _build_idempotency_report() -> IdempotencyReportResponse:
    checked_at = datetime.now(timezone.utc)
    ready_to_publish_with_existing_article = runtime.repository.count_ready_to_publish_with_existing_article()
    published_drafts_missing_article = runtime.repository.count_published_drafts_missing_article()
    published_drafts_missing_news_item = runtime.repository.count_published_drafts_missing_news_item()
    articles_missing_published_draft = runtime.repository.count_articles_missing_published_draft()
    multiple_articles_per_news_item = runtime.repository.count_multiple_articles_per_news_item()

    checks = [
        IdempotencyCheck(
            code="ready_to_publish_already_has_article",
            passed=ready_to_publish_with_existing_article == 0,
            message="Draft в очереди publish не должен уже иметь опубликованную article-запись.",
            observed_value=ready_to_publish_with_existing_article,
            expected_value=0,
            severity="critical",
        ),
        IdempotencyCheck(
            code="published_draft_missing_article",
            passed=published_drafts_missing_article == 0,
            message="Published draft должен иметь связанную article-запись.",
            observed_value=published_drafts_missing_article,
            expected_value=0,
            severity="critical",
        ),
        IdempotencyCheck(
            code="published_draft_missing_news_item",
            passed=published_drafts_missing_news_item == 0,
            message="Published draft должен иметь связанную news_item-запись.",
            observed_value=published_drafts_missing_news_item,
            expected_value=0,
            severity="critical",
        ),
        IdempotencyCheck(
            code="article_missing_published_draft",
            passed=articles_missing_published_draft == 0,
            message="Каждая article-запись из auto-pipeline должна происходить из published draft.",
            observed_value=articles_missing_published_draft,
            expected_value=0,
            severity="warning",
        ),
        IdempotencyCheck(
            code="multiple_articles_per_news_item",
            passed=multiple_articles_per_news_item == 0,
            message="Один news_item не должен иметь несколько article-записей.",
            observed_value=multiple_articles_per_news_item,
            expected_value=0,
            severity="critical",
        ),
    ]

    status = "critical" if any((not check.passed) and check.severity == "critical" for check in checks) else (
        "warning" if any(not check.passed for check in checks) else "ok"
    )
    return IdempotencyReportResponse(status=status, checked_at=checked_at, checks=checks)


def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


def monitoring_status() -> MonitoringStatusResponse:
    return _build_monitoring_status()


def run_recovery() -> RecoveryStatusResponse:
    return _recover_runtime_state(trigger="manual")


def monitoring_idempotency() -> IdempotencyReportResponse:
    return _build_idempotency_report()

