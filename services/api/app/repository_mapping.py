from __future__ import annotations

import json
from .display_time import news_display_time
from .models import (
    Article,
    ContentPlanItem,
    DraftArticle,
    EnrichmentSchedulerSettings,
    EditorialSchedulerSettings,
    EditorReview,
    GuideTopic,
    MatchForecast,
    NewsItem,
    PipelineRun,
    PipelineSkippedItem,
    PipelineSourceBreakdownItem,
    PublishSchedulerSettings,
    PromptConfig,
    RawItem,
    RawItemPreview,
    SchedulerSettings,
    SourceSyncState,
)

class MappingRepository:
    @staticmethod
    def _map_news_row(row: tuple[object, ...]) -> NewsItem:
        return NewsItem(
            id=str(row[0]),
            title=str(row[1]),
            description=str(row[2]),
            category=str(row[3]),
            published_at=row[4],
            source=str(row[5]),
            link=row[6],
            status=str(row[7]),
            visibility=str(row[8]),
            ai_reviewed=bool(row[9]),
            article_slug=row[10],
            updated_at=row[11] if len(row) > 11 else None,
            display_published_at=news_display_time(row[12], row[4]) if len(row) > 12 and row[12] and not str(row[0]).startswith("guide:") else None,
        )

    @staticmethod
    def _map_article_row(row: tuple[object, ...]) -> Article:
        return Article(
            id=str(row[0]),
            slug=str(row[1]),
            news_item_id=str(row[2]),
            raw_item_id=str(row[3] or row[2] or row[0]),
            title=str(row[4]),
            lead=row[5],
            dek=str(row[6]),
            body=str(row[7]),
            category=str(row[8]),
            source_title=str(row[9]),
            source_url=row[10],
            tags=list(row[11] or []),
            published_at=row[12],
            display_published_at=news_display_time(row[0], row[12]) if not str(row[3]).startswith("guide-topic:") else None,
            ai_reviewed=bool(row[13]),
            created_at=row[14],
            updated_at=row[15],
        )

    @staticmethod
    def _map_raw_row(row: tuple[object, ...]) -> RawItem:
        return RawItem(
            id=str(row[0]),
            source_key=str(row[1]),
            source_title=str(row[2]),
            source_url=str(row[3]),
            category=str(row[4]),
            normalized_category=str(row[5]),
            external_id=str(row[6]),
            dedupe_key=str(row[7]),
            title=str(row[8]),
            summary=str(row[9]),
            lead=row[10],
            url=row[11],
            published_at=row[12],
            fetched_at=row[13],
            importance_score=int(row[14]),
            triage_label=str(row[15]),
            is_duplicate=bool(row[16]),
            duplicate_of=row[17],
            duplicate_stage=row[18],
            duplicate_reason=row[19],
            full_text=row[20],
            full_text_source_url=row[21],
            full_text_source_title=row[22],
            reference_urls=list(row[23] or []),
            extraction_mode=row[24],
            enrichment_status=row[25],
            enrichment_error=row[26],
            tags=list(row[27] or []),
            payload=str(row[28]),
        )

    @staticmethod
    def _map_raw_preview_row(row: tuple[object, ...]) -> RawItemPreview:
        return RawItemPreview(
            id=str(row[0]),
            source_key=str(row[1]),
            source_title=str(row[2]),
            category=str(row[3]),
            normalized_category=str(row[4]),
            title=str(row[5]),
            summary=str(row[6]),
            lead=row[7],
            url=row[8],
            published_at=row[9],
            fetched_at=row[10],
            importance_score=int(row[11]),
            triage_label=str(row[12]),
            is_duplicate=bool(row[13]),
            duplicate_of=row[14],
            duplicate_stage=row[15],
            duplicate_reason=row[16],
            full_text=row[17],
            full_text_source_url=row[18],
            full_text_source_title=row[19],
            reference_urls=list(row[20] or []),
            extraction_mode=row[21],
            enrichment_status=row[22],
            enrichment_error=row[23],
            content_plan_status=row[24],
            content_plan_reason=row[25],
            content_plan_priority_label=row[26],
            tags=list(row[27] or []),
        )

    @staticmethod
    def _map_match_forecast_row(row: tuple[object, ...]) -> MatchForecast:
        return MatchForecast(
            slug=str(row[0]),
            home_team=str(row[1]),
            away_team=str(row[2]),
            home_logo=row[3],
            away_logo=row[4],
            league=str(row[5]),
            kickoff=row[6],
            odds_home=float(row[7]),
            odds_draw=float(row[8]),
            odds_away=float(row[9]),
            selection_score=int(row[10]),
            research_brief=row[11],
            lead=row[12],
            home_form=row[13],
            away_form=row[14],
            factors=list(row[15] or []),
            pick=row[16],
            generation_status=str(row[17] or "pending"),
            updated_at=row[18],
            source_urls=list(row[19] or []),
        )

    @staticmethod
    def _map_prompt_row(row: tuple[object, ...]) -> PromptConfig:
        return PromptConfig(
            id=str(row[0]),
            agent_key=str(row[1]),
            name=str(row[2]),
            version=int(row[3]),
            status=str(row[4]),
            system_prompt=str(row[5]),
            user_prompt_template=str(row[6]),
            model=str(row[7]),
            provider=str(row[8]),
            notes=str(row[9]),
            created_at=row[10],
        )

    @staticmethod
    def _map_guide_topic_row(row: tuple[object, ...]) -> GuideTopic:
        return GuideTopic(
            id=int(row[0]),
            topic_number=int(row[1]),
            title=str(row[2]),
            section=str(row[3]),
            category=str(row[4]),
            requires_web_search=bool(row[5]),
            search_context_size=str(row[6] or "low"),
            status=str(row[7]),
            article_id=row[8],
            article_slug=row[9],
            last_error=row[10],
            created_at=row[11],
            updated_at=row[12],
        )

    @staticmethod
    def _map_source_sync_state_row(row: tuple[object, ...]) -> SourceSyncState:
        return SourceSyncState(
            source_key=str(row[0]),
            source_title=str(row[1]),
            last_fetched_at=row[2],
            last_successful_fetch_at=row[3],
            last_successful_parse_at=row[4],
            last_published_at=row[5],
            last_external_id=row[6],
            last_item_count=int(row[7] or 0),
            fetch_status=str(row[8]),
            parse_status=str(row[9]),
            fetch_error_count=int(row[10] or 0),
            parse_error_count=int(row[11] or 0),
            consecutive_failures=int(row[12] or 0),
            retry_count=int(row[13] or 0),
            last_probe_at=row[14],
            last_probe_count=int(row[15] or 0),
            last_probe_readiness=str(row[16] or "unknown"),
            preferred_adapter=row[17],
            preferred_adapter_url=row[18],
            supports_rss=bool(row[19]),
            supports_news_sitemap=bool(row[20]),
            supports_sitemap=bool(row[21]),
            supports_scraping=bool(row[22]),
            last_probe_full_text_ok=bool(row[23]),
            last_probe_full_text_method=row[24],
            last_probe_lead_ok=bool(row[25]),
            last_probe_tags_count=int(row[26] or 0),
            last_probe_sample_title=row[27],
            last_probe_sample_url=row[28],
            last_status=str(row[29]),
            last_error=row[30],
            updated_at=row[31],
        )

    @staticmethod
    def _map_scheduler_settings_row(row: tuple[object, ...]) -> SchedulerSettings:
        return SchedulerSettings(
            enabled=bool(row[0]),
            interval_minutes=int(row[1] or 60),
            batch_size=int(row[2] or 100),
            run_enrichment=bool(row[3]),
            last_run_at=row[4],
            next_run_at=row[5],
            last_status=str(row[6] or "idle"),
            last_error=row[7],
            last_found_count=int(row[8] or 0),
            last_saved_count=int(row[9] or 0),
            last_published_count=int(row[10] or 0),
            updated_at=row[11],
        )

    @staticmethod
    def _map_enrichment_scheduler_settings_row(
        row: tuple[object, ...]
    ) -> EnrichmentSchedulerSettings:
        return EnrichmentSchedulerSettings(
            enabled=bool(row[0]),
            interval_minutes=int(row[1] or 60),
            batch_size=int(row[2] or 20),
            last_run_at=row[3],
            next_run_at=row[4],
            last_status=str(row[5] or "idle"),
            last_error=row[6],
            last_processed_count=int(row[7] or 0),
            last_enriched_count=int(row[8] or 0),
            updated_at=row[9],
        )

    @staticmethod
    def _map_editorial_scheduler_settings_row(
        row: tuple[object, ...]
    ) -> EditorialSchedulerSettings:
        return EditorialSchedulerSettings(
            enabled=bool(row[0]),
            interval_minutes=int(row[1] or 60),
            batch_size=int(row[2] or 10),
            last_run_at=row[3],
            next_run_at=row[4],
            last_status=str(row[5] or "idle"),
            last_error=row[6],
            last_planned_count=int(row[7] or 0),
            last_generated_count=int(row[8] or 0),
            last_reviewed_count=int(row[9] or 0),
            updated_at=row[10],
        )

    @staticmethod
    def _map_publish_scheduler_settings_row(
        row: tuple[object, ...]
    ) -> PublishSchedulerSettings:
        return PublishSchedulerSettings(
            enabled=bool(row[0]),
            interval_minutes=int(row[1] or 60),
            batch_size=int(row[2] or 10),
            last_run_at=row[3],
            next_run_at=row[4],
            last_status=str(row[5] or "idle"),
            last_error=row[6],
            last_published_count=int(row[7] or 0),
            updated_at=row[8],
        )

    @staticmethod
    def _map_pipeline_run_row(row: tuple[object, ...]) -> PipelineRun:
        try:
            skipped_items_payload = json.loads(str(row[15] or "[]"))
        except json.JSONDecodeError:
            skipped_items_payload = []
        try:
            source_breakdown_payload = json.loads(str(row[16] or "[]"))
        except json.JSONDecodeError:
            source_breakdown_payload = []
        return PipelineRun(
            id=str(row[0]),
            phase=str(row[1]),
            trigger=str(row[2]),
            status=str(row[3]),
            started_at=row[4],
            finished_at=row[5],
            duration_ms=int(row[6] or 0),
            found_count=int(row[7] or 0),
            saved_count=int(row[8] or 0),
            published_count=int(row[9] or 0),
            processed_count=int(row[10] or 0),
            enriched_count=int(row[11] or 0),
            planned_count=int(row[12] or 0),
            generated_count=int(row[13] or 0),
            reviewed_count=int(row[14] or 0),
            skipped_items=[
                PipelineSkippedItem(
                    title=str(item.get("title", "")).strip(),
                    reason=str(item.get("reason")).strip() if item.get("reason") else None,
                )
                for item in skipped_items_payload
                if isinstance(item, dict) and str(item.get("title", "")).strip()
            ],
            source_breakdown=[
                PipelineSourceBreakdownItem(
                    source_key=str(item.get("source_key", "")).strip(),
                    source_title=str(item.get("source_title", "")).strip(),
                    found_count=int(item.get("found_count", 0) or 0),
                )
                for item in source_breakdown_payload
                if isinstance(item, dict) and str(item.get("source_title", "")).strip()
            ],
            error=row[17],
        )

    @staticmethod
    def _map_draft_row(row: tuple[object, ...]) -> DraftArticle:
        return DraftArticle(
            id=str(row[0]),
            raw_item_id=str(row[1]),
            title=str(row[2]),
            dek=str(row[3]),
            body=str(row[4]),
            writer_title=row[5],
            writer_dek=row[6],
            writer_body=row[7],
            category=str(row[8]),
            source_title=str(row[9]),
            source_url=row[10],
            published_at=row[11],
            status=str(row[12]),
            review_status=str(row[13]),
            review_summary=row[14],
            publish_decision=str(row[15]),
            publish_reason=row[16],
            prompt_config_id=str(row[17]),
            prompt_name=str(row[18]),
            model=str(row[19]),
            generation_mode=str(row[20]),
            created_at=row[21],
            updated_at=row[22],
        )

    @staticmethod
    def _map_review_row(row: tuple[object, ...]) -> EditorReview:
        return EditorReview(
            id=str(row[0]),
            draft_id=str(row[1]),
            status=str(row[2]),
            decision=str(row[3]),
            summary=str(row[4]),
            notes=str(row[5]),
            revised_title=row[6],
            revised_dek=row[7],
            revised_body=row[8],
            prompt_config_id=str(row[9]),
            prompt_name=str(row[10]),
            model=str(row[11]),
            created_at=row[12],
        )

    @staticmethod
    def _map_content_plan_row(row: tuple[object, ...]) -> ContentPlanItem:
        return ContentPlanItem(
            id=str(row[0]),
            raw_item_id=str(row[1]),
            title=str(row[2]),
            source_title=str(row[3]),
            category=str(row[4]),
            priority_score=int(row[5]),
            priority_label=str(row[6]),
            planned_format=str(row[7]),
            status=str(row[8]),
            reason=str(row[9]),
            created_at=row[10],
            updated_at=row[11],
        )

