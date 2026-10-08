from __future__ import annotations

import json
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from .models import (
    EnrichmentSchedulerSettings,
    EditorialSchedulerSettings,
    AiUsageSummaryRow,
    AiUsageSummaryTotals,
    PipelineRun,
    PipelineSkippedItem,
    PipelineSourceBreakdownItem,
    PublishSchedulerSettings,
    SchedulerSettings,
)

class SchedulersRepository:
    def list_pipeline_runs(self, limit: int = 20) -> list[PipelineRun]:
        statement = """
            SELECT
                id,
                phase,
                trigger,
                status,
                started_at,
                finished_at,
                duration_ms,
                found_count,
                saved_count,
                published_count,
                processed_count,
                enriched_count,
                planned_count,
                generated_count,
                reviewed_count,
                skipped_items,
                source_breakdown,
                error
            FROM pipeline_runs
            ORDER BY started_at DESC, created_at DESC
            LIMIT %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (limit,))
                rows = cursor.fetchall()

        return [self._map_pipeline_run_row(row) for row in rows]

    def list_ai_usage_summary(self, days: int = 14) -> tuple[list[AiUsageSummaryRow], AiUsageSummaryTotals]:
        safe_days = max(1, min(days, 90))
        statement = """
            SELECT
                (created_at AT TIME ZONE 'Europe/Moscow')::date::text AS usage_date,
                usage_group,
                operation,
                model,
                COUNT(*)::int AS request_count,
                COALESCE(SUM(input_tokens), 0)::bigint AS input_tokens,
                COALESCE(SUM(output_tokens), 0)::bigint AS output_tokens,
                COALESCE(SUM(cached_input_tokens), 0)::bigint AS cached_input_tokens,
                COALESCE(SUM(total_tokens), 0)::bigint AS total_tokens,
                COALESCE(SUM(web_search_calls), 0)::bigint AS web_search_calls,
                COALESCE(SUM(estimated_cost_usd), 0)::float AS estimated_cost_usd
            FROM ai_usage_events
            WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
            GROUP BY usage_date, usage_group, operation, model
            ORDER BY usage_date DESC, estimated_cost_usd DESC, request_count DESC
        """
        totals_statement = """
            SELECT
                COUNT(*)::int AS request_count,
                COALESCE(SUM(input_tokens), 0)::bigint AS input_tokens,
                COALESCE(SUM(output_tokens), 0)::bigint AS output_tokens,
                COALESCE(SUM(cached_input_tokens), 0)::bigint AS cached_input_tokens,
                COALESCE(SUM(total_tokens), 0)::bigint AS total_tokens,
                COALESCE(SUM(web_search_calls), 0)::bigint AS web_search_calls,
                COALESCE(SUM(estimated_cost_usd), 0)::float AS estimated_cost_usd
            FROM ai_usage_events
            WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (safe_days,))
                rows = cursor.fetchall()
                cursor.execute(totals_statement, (safe_days,))
                totals_row = cursor.fetchone()

        items = [
            AiUsageSummaryRow(
                usage_date=str(row[0]),
                usage_group=str(row[1]),
                operation=str(row[2]),
                model=str(row[3]),
                request_count=int(row[4] or 0),
                input_tokens=int(row[5] or 0),
                output_tokens=int(row[6] or 0),
                cached_input_tokens=int(row[7] or 0),
                total_tokens=int(row[8] or 0),
                web_search_calls=int(row[9] or 0),
                estimated_cost_usd=round(float(row[10] or 0), 6),
            )
            for row in rows
        ]
        totals = AiUsageSummaryTotals(
            request_count=int(totals_row[0] or 0) if totals_row else 0,
            input_tokens=int(totals_row[1] or 0) if totals_row else 0,
            output_tokens=int(totals_row[2] or 0) if totals_row else 0,
            cached_input_tokens=int(totals_row[3] or 0) if totals_row else 0,
            total_tokens=int(totals_row[4] or 0) if totals_row else 0,
            web_search_calls=int(totals_row[5] or 0) if totals_row else 0,
            estimated_cost_usd=round(float(totals_row[6] or 0), 6) if totals_row else 0,
        )
        return items, totals

    def get_latest_pipeline_run(self, *, phase: str, status: str | None = None) -> PipelineRun | None:
        status_filter = "AND status = %s" if status is not None else ""
        statement = f"""
            SELECT
                id,
                phase,
                trigger,
                status,
                started_at,
                finished_at,
                duration_ms,
                found_count,
                saved_count,
                published_count,
                processed_count,
                enriched_count,
                planned_count,
                generated_count,
                reviewed_count,
                skipped_items,
                source_breakdown,
                error
            FROM pipeline_runs
            WHERE phase = %s
              {status_filter}
            ORDER BY started_at DESC, created_at DESC
            LIMIT 1
        """
        params = (phase, status) if status is not None else (phase,)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, params)
                row = cursor.fetchone()

        return self._map_pipeline_run_row(row) if row else None

    def record_pipeline_run(
        self,
        *,
        run_id: str,
        phase: str,
        trigger: str,
        status: str,
        started_at: datetime,
        finished_at: datetime,
        duration_ms: int,
        found_count: int = 0,
        saved_count: int = 0,
        published_count: int = 0,
        processed_count: int = 0,
        enriched_count: int = 0,
        planned_count: int = 0,
        generated_count: int = 0,
        reviewed_count: int = 0,
        skipped_items: list[dict[str, str]] | None = None,
        source_breakdown: list[dict[str, object]] | None = None,
        error: str | None = None,
    ) -> PipelineRun:
        statement = """
            INSERT INTO pipeline_runs (
                id,
                phase,
                trigger,
                status,
                started_at,
                finished_at,
                duration_ms,
                found_count,
                saved_count,
                published_count,
                processed_count,
                enriched_count,
                planned_count,
                generated_count,
                reviewed_count,
                skipped_items,
                source_breakdown,
                error
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        serialized_skipped_items = json.dumps(skipped_items or [], ensure_ascii=False)
        serialized_source_breakdown = json.dumps(source_breakdown or [], ensure_ascii=False)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    statement,
                    (
                        run_id,
                        phase,
                        trigger,
                        status,
                        started_at,
                        finished_at,
                        duration_ms,
                        found_count,
                        saved_count,
                        published_count,
                        processed_count,
                        enriched_count,
                        planned_count,
                        generated_count,
                        reviewed_count,
                        serialized_skipped_items,
                        serialized_source_breakdown,
                        error,
                    ),
                )
            connection.commit()

        return PipelineRun(
            id=run_id,
            phase=phase,
            trigger=trigger,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            found_count=found_count,
            saved_count=saved_count,
            published_count=published_count,
            processed_count=processed_count,
            enriched_count=enriched_count,
            planned_count=planned_count,
            generated_count=generated_count,
            reviewed_count=reviewed_count,
            skipped_items=[
                PipelineSkippedItem(title=str(item.get("title", "")).strip(), reason=item.get("reason"))
                for item in (skipped_items or [])
                if str(item.get("title", "")).strip()
            ],
            source_breakdown=[
                PipelineSourceBreakdownItem(
                    source_key=str(item.get("source_key", "")).strip(),
                    source_title=str(item.get("source_title", "")).strip(),
                    found_count=int(item.get("found_count", 0) or 0),
                    parsed_count=int(item.get("parsed_count", item.get("found_count", 0)) or 0),
                    fresh_count=int(item.get("fresh_count", item.get("found_count", 0)) or 0),
                    filtered_count=int(item.get("filtered_count", 0) or 0),
                    filter_reasons={
                        str(reason): int(count or 0)
                        for reason, count in dict(item.get("filter_reasons") or {}).items()
                    },
                )
                for item in (source_breakdown or [])
                if str(item.get("source_title", "")).strip()
            ],
            error=error,
        )

    def get_scheduler_settings(self) -> SchedulerSettings:
        statement = """
            SELECT
                enabled,
                interval_minutes,
                batch_size,
                run_enrichment,
                last_run_at,
                next_run_at,
                last_status,
                last_error,
                last_found_count,
                last_saved_count,
                last_published_count,
                updated_at
            FROM scheduler_settings
            WHERE id = 'default'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        if row is None:
            return SchedulerSettings()

        return self._map_scheduler_settings_row(row)

    def get_enrichment_scheduler_settings(self) -> EnrichmentSchedulerSettings:
        statement = """
            SELECT
                enrichment_enabled,
                enrichment_interval_minutes,
                enrichment_batch_size,
                enrichment_last_run_at,
                enrichment_next_run_at,
                enrichment_last_status,
                enrichment_last_error,
                enrichment_last_processed_count,
                enrichment_last_enriched_count,
                updated_at
            FROM scheduler_settings
            WHERE id = 'default'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        if row is None:
            return EnrichmentSchedulerSettings()

        return self._map_enrichment_scheduler_settings_row(row)

    def get_editorial_scheduler_settings(self) -> EditorialSchedulerSettings:
        statement = """
            SELECT
                editorial_enabled,
                editorial_interval_minutes,
                editorial_batch_size,
                editorial_last_run_at,
                editorial_next_run_at,
                editorial_last_status,
                editorial_last_error,
                editorial_last_planned_count,
                editorial_last_generated_count,
                editorial_last_reviewed_count,
                updated_at
            FROM scheduler_settings
            WHERE id = 'default'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        if row is None:
            return EditorialSchedulerSettings()

        return self._map_editorial_scheduler_settings_row(row)

    def get_publish_scheduler_settings(self) -> PublishSchedulerSettings:
        statement = """
            SELECT
                publish_enabled,
                publish_interval_minutes,
                publish_batch_size,
                publish_last_run_at,
                publish_next_run_at,
                publish_last_status,
                publish_last_error,
                publish_last_published_count,
                updated_at
            FROM scheduler_settings
            WHERE id = 'default'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        if row is None:
            return PublishSchedulerSettings()

        return self._map_publish_scheduler_settings_row(row)

    def update_scheduler_settings(
        self,
        *,
        enabled: bool,
        interval_minutes: int,
        batch_size: int,
        run_enrichment: bool,
    ) -> SchedulerSettings:
        now = datetime.now(timezone.utc)
        next_run_at = now + timedelta(minutes=interval_minutes) if enabled else None

        statement = """
            INSERT INTO scheduler_settings (
                id,
                enabled,
                interval_minutes,
                batch_size,
                run_enrichment,
                next_run_at,
                last_status,
                updated_at
            )
            VALUES ('default', %s, %s, %s, %s, %s, COALESCE((SELECT last_status FROM scheduler_settings WHERE id = 'default'), 'idle'), NOW())
            ON CONFLICT (id) DO UPDATE
            SET enabled = EXCLUDED.enabled,
                interval_minutes = EXCLUDED.interval_minutes,
                batch_size = EXCLUDED.batch_size,
                run_enrichment = EXCLUDED.run_enrichment,
                next_run_at = EXCLUDED.next_run_at,
                updated_at = NOW()
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (enabled, interval_minutes, batch_size, run_enrichment, next_run_at))
            connection.commit()

        return self.get_scheduler_settings()

    def update_enrichment_scheduler_settings(
        self,
        *,
        enabled: bool,
        interval_minutes: int,
        batch_size: int,
    ) -> EnrichmentSchedulerSettings:
        now = datetime.now(timezone.utc)
        next_run_at = now + timedelta(minutes=interval_minutes) if enabled else None

        statement = """
            INSERT INTO scheduler_settings (
                id,
                enrichment_enabled,
                enrichment_interval_minutes,
                enrichment_batch_size,
                enrichment_next_run_at,
                enrichment_last_status,
                updated_at
            )
            VALUES ('default', %s, %s, %s, %s, COALESCE((SELECT enrichment_last_status FROM scheduler_settings WHERE id = 'default'), 'idle'), NOW())
            ON CONFLICT (id) DO UPDATE
            SET enrichment_enabled = EXCLUDED.enrichment_enabled,
                enrichment_interval_minutes = EXCLUDED.enrichment_interval_minutes,
                enrichment_batch_size = EXCLUDED.enrichment_batch_size,
                enrichment_next_run_at = EXCLUDED.enrichment_next_run_at,
                updated_at = NOW()
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (enabled, interval_minutes, batch_size, next_run_at))
            connection.commit()

        return self.get_enrichment_scheduler_settings()

    def update_editorial_scheduler_settings(
        self,
        *,
        enabled: bool,
        interval_minutes: int,
        batch_size: int,
    ) -> EditorialSchedulerSettings:
        now = datetime.now(timezone.utc)
        next_run_at = now + timedelta(minutes=interval_minutes) if enabled else None

        statement = """
            INSERT INTO scheduler_settings (
                id,
                editorial_enabled,
                editorial_interval_minutes,
                editorial_batch_size,
                editorial_next_run_at,
                editorial_last_status,
                updated_at
            )
            VALUES ('default', %s, %s, %s, %s, COALESCE((SELECT editorial_last_status FROM scheduler_settings WHERE id = 'default'), 'idle'), NOW())
            ON CONFLICT (id) DO UPDATE
            SET editorial_enabled = EXCLUDED.editorial_enabled,
                editorial_interval_minutes = EXCLUDED.editorial_interval_minutes,
                editorial_batch_size = EXCLUDED.editorial_batch_size,
                editorial_next_run_at = EXCLUDED.editorial_next_run_at,
                updated_at = NOW()
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (enabled, interval_minutes, batch_size, next_run_at))
            connection.commit()

        return self.get_editorial_scheduler_settings()

    def update_publish_scheduler_settings(
        self,
        *,
        enabled: bool,
        interval_minutes: int,
        batch_size: int,
    ) -> PublishSchedulerSettings:
        now = datetime.now(timezone.utc)
        next_run_at = now + timedelta(minutes=interval_minutes) if enabled else None

        statement = """
            INSERT INTO scheduler_settings (
                id,
                publish_enabled,
                publish_interval_minutes,
                publish_batch_size,
                publish_next_run_at,
                publish_last_status,
                updated_at
            )
            VALUES ('default', %s, %s, %s, %s, COALESCE((SELECT publish_last_status FROM scheduler_settings WHERE id = 'default'), 'idle'), NOW())
            ON CONFLICT (id) DO UPDATE
            SET publish_enabled = EXCLUDED.publish_enabled,
                publish_interval_minutes = EXCLUDED.publish_interval_minutes,
                publish_batch_size = EXCLUDED.publish_batch_size,
                publish_next_run_at = EXCLUDED.publish_next_run_at,
                updated_at = NOW()
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (enabled, interval_minutes, batch_size, next_run_at))
            connection.commit()

        return self.get_publish_scheduler_settings()

    def mark_scheduler_run(
        self,
        *,
        ran_at: datetime,
        next_run_at: datetime | None,
        status: str,
        error: str | None = None,
        found_count: int = 0,
        saved_count: int = 0,
        published_count: int = 0,
    ) -> SchedulerSettings:
        statement = """
            UPDATE scheduler_settings
            SET last_run_at = %s,
                next_run_at = %s,
                last_status = %s,
                last_error = %s,
                last_found_count = %s,
                last_saved_count = %s,
                last_published_count = %s,
                updated_at = NOW()
            WHERE id = 'default'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    statement,
                    (
                        ran_at,
                        next_run_at,
                        status,
                        error,
                        found_count,
                        saved_count,
                        published_count,
                    ),
                )
            connection.commit()

        return self.get_scheduler_settings()

    def set_scheduler_status(self, *, status: str, error: str | None = None) -> SchedulerSettings:
        statement = """
            UPDATE scheduler_settings
            SET last_status = %s,
                last_error = %s,
                updated_at = NOW()
            WHERE id = 'default'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (status, error))
            connection.commit()

        return self.get_scheduler_settings()

    def mark_enrichment_scheduler_run(
        self,
        *,
        ran_at: datetime,
        next_run_at: datetime | None,
        status: str,
        error: str | None = None,
        processed_count: int = 0,
        enriched_count: int = 0,
    ) -> EnrichmentSchedulerSettings:
        statement = """
            UPDATE scheduler_settings
            SET enrichment_last_run_at = %s,
                enrichment_next_run_at = %s,
                enrichment_last_status = %s,
                enrichment_last_error = %s,
                enrichment_last_processed_count = %s,
                enrichment_last_enriched_count = %s,
                updated_at = NOW()
            WHERE id = 'default'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    statement,
                    (
                        ran_at,
                        next_run_at,
                        status,
                        error,
                        processed_count,
                        enriched_count,
                    ),
                )
            connection.commit()

        return self.get_enrichment_scheduler_settings()

    def set_enrichment_scheduler_status(
        self,
        *,
        status: str,
        error: str | None = None,
    ) -> EnrichmentSchedulerSettings:
        statement = """
            UPDATE scheduler_settings
            SET enrichment_last_status = %s,
                enrichment_last_error = %s,
                updated_at = NOW()
            WHERE id = 'default'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (status, error))
            connection.commit()

        return self.get_enrichment_scheduler_settings()

    def mark_editorial_scheduler_run(
        self,
        *,
        ran_at: datetime,
        next_run_at: datetime | None,
        status: str,
        error: str | None = None,
        planned_count: int = 0,
        generated_count: int = 0,
        reviewed_count: int = 0,
    ) -> EditorialSchedulerSettings:
        statement = """
            UPDATE scheduler_settings
            SET editorial_last_run_at = %s,
                editorial_next_run_at = %s,
                editorial_last_status = %s,
                editorial_last_error = %s,
                editorial_last_planned_count = %s,
                editorial_last_generated_count = %s,
                editorial_last_reviewed_count = %s,
                updated_at = NOW()
            WHERE id = 'default'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    statement,
                    (
                        ran_at,
                        next_run_at,
                        status,
                        error,
                        planned_count,
                        generated_count,
                        reviewed_count,
                    ),
                )
            connection.commit()

        return self.get_editorial_scheduler_settings()

    def set_editorial_scheduler_status(
        self,
        *,
        status: str,
        error: str | None = None,
    ) -> EditorialSchedulerSettings:
        statement = """
            UPDATE scheduler_settings
            SET editorial_last_status = %s,
                editorial_last_error = %s,
                updated_at = NOW()
            WHERE id = 'default'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (status, error))
            connection.commit()

        return self.get_editorial_scheduler_settings()

    def mark_publish_scheduler_run(
        self,
        *,
        ran_at: datetime,
        next_run_at: datetime | None,
        status: str,
        error: str | None = None,
        published_count: int = 0,
    ) -> PublishSchedulerSettings:
        statement = """
            UPDATE scheduler_settings
            SET publish_last_run_at = %s,
                publish_next_run_at = %s,
                publish_last_status = %s,
                publish_last_error = %s,
                publish_last_published_count = %s,
                updated_at = NOW()
            WHERE id = 'default'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    statement,
                    (
                        ran_at,
                        next_run_at,
                        status,
                        error,
                        published_count,
                    ),
                )
            connection.commit()

        return self.get_publish_scheduler_settings()

    def set_publish_scheduler_status(
        self,
        *,
        status: str,
        error: str | None = None,
    ) -> PublishSchedulerSettings:
        statement = """
            UPDATE scheduler_settings
            SET publish_last_status = %s,
                publish_last_error = %s,
                updated_at = NOW()
            WHERE id = 'default'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (status, error))
            connection.commit()

        return self.get_publish_scheduler_settings()

    def recover_scheduler_if_stale(self) -> SchedulerSettings:
        settings = self.get_scheduler_settings()
        if settings.last_status != "running":
            return settings
        return self.set_scheduler_status(
            status="idle",
            error="Recovered stale running status after API restart.",
        )

    def recover_enrichment_scheduler_if_stale(self) -> EnrichmentSchedulerSettings:
        settings = self.get_enrichment_scheduler_settings()
        if settings.last_status != "running":
            return settings
        return self.set_enrichment_scheduler_status(
            status="idle",
            error="Recovered stale running status after API restart.",
        )

    def recover_editorial_scheduler_if_stale(self) -> EditorialSchedulerSettings:
        settings = self.get_editorial_scheduler_settings()
        if settings.last_status != "running":
            return settings
        return self.set_editorial_scheduler_status(
            status="idle",
            error="Recovered stale running status after API restart.",
        )

    def recover_publish_scheduler_if_stale(self) -> PublishSchedulerSettings:
        settings = self.get_publish_scheduler_settings()
        if settings.last_status != "running":
            return settings
        return self.set_publish_scheduler_status(
            status="idle",
            error="Recovered stale running status after API restart.",
        )

