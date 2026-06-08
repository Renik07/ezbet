from __future__ import annotations

import json
import re
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import psycopg

from .config import get_database_url
from .ingestion import SUPPORTED_ACTIVE_SOURCE_TYPES
from .models import (
    Article,
    ContentPlanItem,
    DraftArticle,
    EnrichmentSchedulerSettings,
    EditorialSchedulerSettings,
    EditorReview,
    NewsItem,
    PipelineRun,
    PipelineSkippedItem,
    PipelineSourceBreakdownItem,
    PublishSchedulerSettings,
    PromptConfig,
    RawItem,
    RawItemPreview,
    SchedulerSettings,
    SourceItem,
    SourceSyncState,
)


@dataclass
class InsertRawItemsResult:
    inserted_count: int
    skipped_items: list[dict[str, str]]


@dataclass
class PrefilterRawItemsResult:
    fresh_items: list[RawItem]
    skipped_items: list[dict[str, str]]


def _is_retryable_db_error(exc: psycopg.OperationalError) -> bool:
    message = str(exc).lower()
    transient_markers = (
        "ssl syscall error: eof detected",
        "ssl connection has been closed unexpectedly",
        "server closed the connection unexpectedly",
        "connection not open",
        "connection reset by peer",
        "could not receive data from server",
        "terminating connection due to administrator command",
    )
    return any(marker in message for marker in transient_markers)


class NewsRepository:
    """PostgreSQL-backed repository for the MVP news and editorial flow."""

    def __init__(self) -> None:
        self.database_url = get_database_url()

    def connect(self) -> psycopg.Connection:
        attempts = 0
        last_error: psycopg.OperationalError | None = None

        while attempts < 3:
            attempts += 1
            try:
                return psycopg.connect(self.database_url)
            except psycopg.OperationalError as exc:
                last_error = exc
                if attempts >= 3 or not _is_retryable_db_error(exc):
                    raise
                time.sleep(0.25 * attempts)

        if last_error is not None:
            raise last_error
        raise psycopg.OperationalError("Database connection failed without error details.")

    def ensure_schema(self) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS news_items (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        category TEXT NOT NULL,
                        published_at TIMESTAMPTZ NOT NULL,
                        source TEXT NOT NULL,
                        link TEXT,
                        status TEXT NOT NULL DEFAULT 'published',
                        visibility TEXT NOT NULL DEFAULT 'public',
                        ai_reviewed BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS articles (
                        id TEXT PRIMARY KEY,
                        slug TEXT NOT NULL UNIQUE,
                        news_item_id TEXT NOT NULL UNIQUE,
                        raw_item_id TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL,
                        lead TEXT,
                        dek TEXT NOT NULL,
                        body TEXT NOT NULL,
                        category TEXT NOT NULL,
                        source_title TEXT NOT NULL,
                        source_url TEXT,
                        authors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
                        tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
                        published_at TIMESTAMPTZ NOT NULL,
                        ai_reviewed BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS raw_items (
                        id TEXT PRIMARY KEY,
                        source_key TEXT NOT NULL,
                        source_title TEXT NOT NULL,
                        source_url TEXT NOT NULL,
                        category TEXT NOT NULL,
                        normalized_category TEXT NOT NULL DEFAULT 'general',
                        external_id TEXT NOT NULL,
                        dedupe_key TEXT NOT NULL DEFAULT '',
                        title TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        lead TEXT,
                        url TEXT,
                        published_at TIMESTAMPTZ NOT NULL,
                        fetched_at TIMESTAMPTZ NOT NULL,
                        importance_score INTEGER NOT NULL DEFAULT 0,
                        triage_label TEXT NOT NULL DEFAULT 'low',
                        is_duplicate BOOLEAN NOT NULL DEFAULT FALSE,
                        duplicate_of TEXT,
                        duplicate_stage TEXT,
                        duplicate_reason TEXT,
                        full_text TEXT,
                        full_text_source_url TEXT,
                        full_text_source_title TEXT,
                        reference_urls TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
                        extraction_mode TEXT,
                        enrichment_status TEXT,
                        enrichment_error TEXT,
                        authors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
                        tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
                        payload TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS prompt_configs (
                        id TEXT PRIMARY KEY,
                        agent_key TEXT NOT NULL,
                        name TEXT NOT NULL,
                        version INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        system_prompt TEXT NOT NULL,
                        user_prompt_template TEXT NOT NULL,
                        model TEXT NOT NULL,
                        provider TEXT NOT NULL DEFAULT 'internal',
                        notes TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE (agent_key, version)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS draft_articles (
                        id TEXT PRIMARY KEY,
                        raw_item_id TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL,
                        dek TEXT NOT NULL,
                        body TEXT NOT NULL,
                        writer_title TEXT,
                        writer_dek TEXT,
                        writer_body TEXT,
                        category TEXT NOT NULL,
                        source_title TEXT NOT NULL,
                        source_url TEXT,
                        published_at TIMESTAMPTZ NOT NULL,
                        status TEXT NOT NULL DEFAULT 'draft',
                        review_status TEXT NOT NULL DEFAULT 'pending',
                        review_summary TEXT,
                        publish_decision TEXT NOT NULL DEFAULT 'publish_pending',
                        publish_reason TEXT,
                        prompt_config_id TEXT NOT NULL,
                        prompt_name TEXT NOT NULL,
                        model TEXT NOT NULL,
                        generation_mode TEXT NOT NULL DEFAULT 'template',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS editor_reviews (
                        id TEXT PRIMARY KEY,
                        draft_id TEXT NOT NULL UNIQUE,
                        status TEXT NOT NULL DEFAULT 'reviewed',
                        decision TEXT NOT NULL DEFAULT 'approve',
                        summary TEXT NOT NULL,
                        notes TEXT NOT NULL DEFAULT '',
                        revised_title TEXT,
                        revised_dek TEXT,
                        revised_body TEXT,
                        prompt_config_id TEXT NOT NULL,
                        prompt_name TEXT NOT NULL,
                        model TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS content_plan_items (
                        id TEXT PRIMARY KEY,
                        raw_item_id TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL,
                        source_title TEXT NOT NULL,
                        category TEXT NOT NULL,
                        priority_score INTEGER NOT NULL,
                        priority_label TEXT NOT NULL,
                        planned_format TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'planned',
                        reason TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS source_configs (
                        key TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL,
                        category TEXT NOT NULL,
                        source_type TEXT NOT NULL DEFAULT 'rss',
                        status TEXT NOT NULL DEFAULT 'active',
                        notes TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_raw_items_dedupe_key
                    ON raw_items (dedupe_key)
                    WHERE dedupe_key <> ''
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS source_sync_state (
                        source_key TEXT PRIMARY KEY,
                        source_title TEXT NOT NULL,
                        last_fetched_at TIMESTAMPTZ,
                        last_successful_fetch_at TIMESTAMPTZ,
                        last_successful_parse_at TIMESTAMPTZ,
                        last_published_at TIMESTAMPTZ,
                        last_external_id TEXT,
                        last_item_count INTEGER NOT NULL DEFAULT 0,
                        fetch_status TEXT NOT NULL DEFAULT 'idle',
                        parse_status TEXT NOT NULL DEFAULT 'idle',
                        fetch_error_count INTEGER NOT NULL DEFAULT 0,
                        parse_error_count INTEGER NOT NULL DEFAULT 0,
                        consecutive_failures INTEGER NOT NULL DEFAULT 0,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        last_probe_at TIMESTAMPTZ,
                        last_probe_count INTEGER NOT NULL DEFAULT 0,
                        last_probe_readiness TEXT NOT NULL DEFAULT 'unknown',
                        preferred_adapter TEXT,
                        preferred_adapter_url TEXT,
                        supports_rss BOOLEAN NOT NULL DEFAULT FALSE,
                        supports_news_sitemap BOOLEAN NOT NULL DEFAULT FALSE,
                        supports_sitemap BOOLEAN NOT NULL DEFAULT FALSE,
                        supports_scraping BOOLEAN NOT NULL DEFAULT FALSE,
                        last_probe_full_text_ok BOOLEAN NOT NULL DEFAULT FALSE,
                        last_probe_full_text_method TEXT,
                        last_probe_lead_ok BOOLEAN NOT NULL DEFAULT FALSE,
                        last_probe_authors_count INTEGER NOT NULL DEFAULT 0,
                        last_probe_tags_count INTEGER NOT NULL DEFAULT 0,
                        last_probe_sample_title TEXT,
                        last_probe_sample_url TEXT,
                        last_status TEXT NOT NULL DEFAULT 'idle',
                        last_error TEXT,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scheduler_settings (
                        id TEXT PRIMARY KEY,
                        enabled BOOLEAN NOT NULL DEFAULT FALSE,
                        interval_minutes INTEGER NOT NULL DEFAULT 60,
                        batch_size INTEGER NOT NULL DEFAULT 100,
                        run_enrichment BOOLEAN NOT NULL DEFAULT FALSE,
                        last_run_at TIMESTAMPTZ,
                        next_run_at TIMESTAMPTZ,
                        last_status TEXT NOT NULL DEFAULT 'idle',
                        last_error TEXT,
                        last_found_count INTEGER NOT NULL DEFAULT 0,
                        last_saved_count INTEGER NOT NULL DEFAULT 0,
                        last_published_count INTEGER NOT NULL DEFAULT 0,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pipeline_runs (
                        id TEXT PRIMARY KEY,
                        phase TEXT NOT NULL,
                        trigger TEXT NOT NULL,
                        status TEXT NOT NULL,
                        started_at TIMESTAMPTZ NOT NULL,
                        finished_at TIMESTAMPTZ NOT NULL,
                        duration_ms INTEGER NOT NULL DEFAULT 0,
                        found_count INTEGER NOT NULL DEFAULT 0,
                        saved_count INTEGER NOT NULL DEFAULT 0,
                        published_count INTEGER NOT NULL DEFAULT 0,
                        processed_count INTEGER NOT NULL DEFAULT 0,
                        enriched_count INTEGER NOT NULL DEFAULT 0,
                        planned_count INTEGER NOT NULL DEFAULT 0,
                        generated_count INTEGER NOT NULL DEFAULT 0,
                        reviewed_count INTEGER NOT NULL DEFAULT 0,
                        skipped_items TEXT NOT NULL DEFAULT '[]',
                        source_breakdown TEXT NOT NULL DEFAULT '[]',
                        error TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS skipped_items TEXT NOT NULL DEFAULT '[]'"
                )
                cursor.execute(
                    "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS source_breakdown TEXT NOT NULL DEFAULT '[]'"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS batch_size INTEGER NOT NULL DEFAULT 100"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ALTER COLUMN batch_size SET DEFAULT 100"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS run_enrichment BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS last_found_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS last_saved_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS last_published_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_enabled BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_interval_minutes INTEGER NOT NULL DEFAULT 60"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_batch_size INTEGER NOT NULL DEFAULT 20"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ALTER COLUMN enrichment_batch_size SET DEFAULT 20"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_last_run_at TIMESTAMPTZ"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_next_run_at TIMESTAMPTZ"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_last_status TEXT NOT NULL DEFAULT 'idle'"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_last_error TEXT"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_last_processed_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_last_enriched_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_enabled BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_interval_minutes INTEGER NOT NULL DEFAULT 60"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_batch_size INTEGER NOT NULL DEFAULT 10"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ALTER COLUMN editorial_batch_size SET DEFAULT 10"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_last_run_at TIMESTAMPTZ"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_next_run_at TIMESTAMPTZ"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_last_status TEXT NOT NULL DEFAULT 'idle'"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_last_error TEXT"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_last_planned_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_last_generated_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_last_reviewed_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_enabled BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_interval_minutes INTEGER NOT NULL DEFAULT 60"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_batch_size INTEGER NOT NULL DEFAULT 10"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ALTER COLUMN publish_batch_size SET DEFAULT 10"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_last_run_at TIMESTAMPTZ"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_next_run_at TIMESTAMPTZ"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_last_status TEXT NOT NULL DEFAULT 'idle'"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_last_error TEXT"
                )
                cursor.execute(
                    "ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_last_published_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS publish_decision TEXT NOT NULL DEFAULT 'publish_pending'"
                )
                cursor.execute(
                    "ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS publish_reason TEXT"
                )
                cursor.execute(
                    "ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS writer_title TEXT"
                )
                cursor.execute(
                    "ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS writer_dek TEXT"
                )
                cursor.execute(
                    "ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS writer_body TEXT"
                )
                cursor.execute(
                    "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'public'"
                )
                cursor.execute(
                    "ALTER TABLE editor_reviews ADD COLUMN IF NOT EXISTS decision TEXT NOT NULL DEFAULT 'approve'"
                )
                cursor.execute(
                    "ALTER TABLE editor_reviews ADD COLUMN IF NOT EXISTS revised_title TEXT"
                )
                cursor.execute(
                    "ALTER TABLE editor_reviews ADD COLUMN IF NOT EXISTS revised_dek TEXT"
                )
                cursor.execute(
                    "ALTER TABLE editor_reviews ADD COLUMN IF NOT EXISTS revised_body TEXT"
                )
                cursor.execute(
                    "ALTER TABLE source_configs ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'rss'"
                )
                cursor.execute(
                    "ALTER TABLE source_configs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'"
                )
                cursor.execute(
                    "ALTER TABLE source_configs ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT ''"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_successful_fetch_at TIMESTAMPTZ"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_successful_parse_at TIMESTAMPTZ"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_item_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS fetch_status TEXT NOT NULL DEFAULT 'idle'"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS parse_status TEXT NOT NULL DEFAULT 'idle'"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS fetch_error_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS parse_error_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_at TIMESTAMPTZ"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_readiness TEXT NOT NULL DEFAULT 'unknown'"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS preferred_adapter TEXT"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS preferred_adapter_url TEXT"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS supports_rss BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS supports_news_sitemap BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS supports_sitemap BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS supports_scraping BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_full_text_ok BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_full_text_method TEXT"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_lead_ok BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_authors_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_tags_count INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_sample_title TEXT"
                )
                cursor.execute(
                    "ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_sample_url TEXT"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS normalized_category TEXT NOT NULL DEFAULT 'general'"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS dedupe_key TEXT NOT NULL DEFAULT ''"
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_raw_items_dedupe_key
                    ON raw_items (dedupe_key)
                    WHERE dedupe_key <> ''
                    """
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS importance_score INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS triage_label TEXT NOT NULL DEFAULT 'low'"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN NOT NULL DEFAULT FALSE"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS duplicate_of TEXT"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS duplicate_stage TEXT"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS duplicate_reason TEXT"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS full_text TEXT"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS full_text_source_url TEXT"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS full_text_source_title TEXT"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS reference_urls TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS extraction_mode TEXT"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS enrichment_status TEXT"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS enrichment_error TEXT"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS lead TEXT"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS authors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]"
                )
                cursor.execute(
                    "ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]"
                )
                cursor.execute(
                    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS lead TEXT"
                )
                cursor.execute(
                    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS authors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]"
                )
                cursor.execute(
                    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]"
                )
                cursor.execute(
                    """
                    INSERT INTO scheduler_settings (
                        id,
                        enabled,
                        interval_minutes,
                        batch_size,
                        run_enrichment,
                        enrichment_enabled,
                        enrichment_interval_minutes,
                        enrichment_batch_size,
                        editorial_enabled,
                        editorial_interval_minutes,
                        editorial_batch_size,
                        publish_enabled,
                        publish_interval_minutes,
                        publish_batch_size,
                        last_status
                    )
                    VALUES ('default', FALSE, 60, 100, FALSE, FALSE, 60, 20, FALSE, 60, 10, FALSE, 60, 10, 'idle')
                    ON CONFLICT (id) DO NOTHING
                    """
                )
            connection.commit()

    def ensure_prompt_defaults(self, prompts: list[PromptConfig]) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                for prompt in prompts:
                    cursor.execute(
                        """
                        INSERT INTO prompt_configs (
                            id,
                            agent_key,
                            name,
                            version,
                            status,
                            system_prompt,
                            user_prompt_template,
                            model,
                            provider,
                            notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (
                            prompt.id,
                            prompt.agent_key,
                            prompt.name,
                            prompt.version,
                            prompt.status,
                            prompt.system_prompt,
                            prompt.user_prompt_template,
                            prompt.model,
                            prompt.provider,
                            prompt.notes,
                        ),
                    )
            connection.commit()

    def ensure_source_defaults(self, sources: list[SourceItem]) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                for source in sources:
                    cursor.execute(
                        """
                        INSERT INTO source_configs (
                            key,
                            title,
                            url,
                            category,
                            source_type,
                            status,
                            notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (key) DO NOTHING
                        """,
                        (
                            source.key,
                            source.title,
                            source.url,
                            source.category,
                            source.source_type,
                            source.status,
                            source.notes,
                        ),
                    )
                    cursor.execute(
                        """
                        INSERT INTO source_sync_state (
                            source_key,
                            source_title,
                            last_status
                        )
                        VALUES (%s, %s, 'idle')
                        ON CONFLICT (source_key) DO UPDATE SET
                            source_title = EXCLUDED.source_title
                        """,
                        (source.key, source.title),
                    )
            connection.commit()

    def list_source_configs(self) -> list[SourceItem]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT key, title, url, category, source_type, status, notes
                    FROM source_configs
                    ORDER BY created_at ASC, title ASC
                    """
                )
                rows = cursor.fetchall()

        return [
            SourceItem(
                key=str(row[0]),
                title=str(row[1]),
                url=str(row[2]),
                category=str(row[3]),
                source_type=str(row[4]),
                status=str(row[5]),
                notes=str(row[6]),
            )
            for row in rows
        ]

    def list_active_sources(self) -> list[SourceItem]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT key, title, url, category, source_type, status, notes
                    FROM source_configs
                    WHERE status = 'active'
                      AND source_type = ANY(%s)
                    ORDER BY created_at ASC, title ASC
                    """,
                    (list(SUPPORTED_ACTIVE_SOURCE_TYPES),),
                )
                rows = cursor.fetchall()

        return [
            SourceItem(
                key=str(row[0]),
                title=str(row[1]),
                url=str(row[2]),
                category=str(row[3]),
                source_type=str(row[4]),
                status=str(row[5]),
                notes=str(row[6]),
            )
            for row in rows
        ]

    def create_source_config(self, source: SourceItem) -> SourceItem:
        source = self._normalize_source_config(source)
        self._validate_source_config(source)
        self._validate_source_activation_readiness(source)
        try:
            with self.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO source_configs (
                            key,
                            title,
                            url,
                            category,
                            source_type,
                            status,
                            notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            source.key,
                            source.title,
                            source.url,
                            source.category,
                            source.source_type,
                            source.status,
                            source.notes,
                        ),
                    )
                    cursor.execute(
                        """
                        INSERT INTO source_sync_state (source_key, source_title, last_status)
                        VALUES (%s, %s, 'idle')
                        ON CONFLICT (source_key) DO NOTHING
                        """,
                        (source.key, source.title),
                    )
                connection.commit()
        except psycopg.errors.UniqueViolation as exc:
            try:
                existing = self.get_source_config(source.key)
            except LookupError:
                raise ValueError("Источник с таким key уже существует.") from exc

            if existing.status == "draft":
                return self.update_source_config(source)

            raise ValueError(
                "Источник с таким key уже существует. Удалите текущий источник или используйте другой key."
            ) from exc
        return self.get_source_config(source.key)

    def update_source_config(self, source: SourceItem) -> SourceItem:
        source = self._normalize_source_config(source)
        self._validate_source_config(source)
        self._validate_source_activation_readiness(source)
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE source_configs
                    SET title = %s,
                        url = %s,
                        category = %s,
                        source_type = %s,
                        status = %s,
                        notes = %s,
                        updated_at = NOW()
                    WHERE key = %s
                    """,
                    (
                        source.title,
                        source.url,
                        source.category,
                        source.source_type,
                        source.status,
                        source.notes,
                        source.key,
                    ),
                )
                cursor.execute(
                    """
                    UPDATE source_sync_state
                    SET source_title = %s,
                        updated_at = NOW()
                    WHERE source_key = %s
                    """,
                    (source.title, source.key),
                )
            connection.commit()
        return self.get_source_config(source.key)

    def delete_source_config(self, key: str) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM source_sync_state WHERE source_key = %s", (key,))
                cursor.execute("DELETE FROM source_configs WHERE key = %s", (key,))
            connection.commit()

    def get_source_config(self, key: str) -> SourceItem:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT key, title, url, category, source_type, status, notes
                    FROM source_configs
                    WHERE key = %s
                    """,
                    (key,),
                )
                row = cursor.fetchone()
        if row is None:
            raise LookupError(f"Source {key} was not found.")
        return SourceItem(
            key=str(row[0]),
            title=str(row[1]),
            url=str(row[2]),
            category=str(row[3]),
            source_type=str(row[4]),
            status=str(row[5]),
            notes=str(row[6]),
        )

    def reset_runtime_data(self) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    TRUNCATE TABLE
                        editor_reviews,
                        draft_articles,
                        content_plan_items,
                        news_items,
                        raw_items,
                        source_sync_state
                    RESTART IDENTITY CASCADE
                    """
                )
            connection.commit()

    def sync_news_ai_review_flags(self) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE news_items
                    SET ai_reviewed = FALSE
                    """
                )
                cursor.execute(
                    """
                    UPDATE news_items n
                    SET ai_reviewed = TRUE
                    FROM raw_items r
                    JOIN draft_articles d ON d.raw_item_id = r.id
                    WHERE r.external_id = n.id
                      AND d.status = 'published'
                    """
                )
            connection.commit()

    def list(
        self,
        query: Optional[str] = None,
        ai_only: bool = False,
        *,
        include_hidden: bool = False,
        limit: int | None = None,
    ) -> list[NewsItem]:
        statement = """
            SELECT n.id, n.title, n.description, n.category, n.published_at, n.source, n.link, n.status, n.visibility, n.ai_reviewed, a.slug
            FROM news_items n
            LEFT JOIN articles a ON a.news_item_id = n.id
        """
        params: list[object] = []
        clauses: list[str] = []

        if not include_hidden:
            clauses.append("COALESCE(n.visibility, 'public') = 'public'")

        if ai_only:
            clauses.append("n.ai_reviewed = TRUE")

        if query:
            clauses.append(
                """
                (
                    n.title ILIKE %s
                    OR n.description ILIKE %s
                    OR n.category ILIKE %s
                    OR n.source ILIKE %s
                )
                """
            )
            search = f"%{query.strip()}%"
            params.extend((search, search, search, search))

        if clauses:
            statement += " WHERE " + " AND ".join(clauses)

        statement += " ORDER BY n.published_at DESC"
        if limit is not None:
            statement += " LIMIT %s"
            params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_news_row(row) for row in rows]

    def list_raw_items(self, limit: int = 50) -> list[RawItem]:
        statement = """
            SELECT
                id,
                source_key,
                source_title,
                source_url,
                category,
                normalized_category,
                external_id,
                dedupe_key,
                title,
                summary,
                lead,
                url,
                published_at,
                fetched_at,
                importance_score,
                triage_label,
                is_duplicate,
                duplicate_of,
                duplicate_stage,
                duplicate_reason,
                full_text,
                full_text_source_url,
                full_text_source_title,
                reference_urls,
                extraction_mode,
                enrichment_status,
                enrichment_error,
                tags,
                payload
            FROM raw_items
            ORDER BY fetched_at DESC, published_at DESC
            LIMIT %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (limit,))
                rows = cursor.fetchall()

        return [self._map_raw_row(row) for row in rows]

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
                )
                for item in (source_breakdown or [])
                if str(item.get("source_title", "")).strip()
            ],
            error=error,
        )

    def list_raw_item_previews(self, limit: int = 50) -> list[RawItemPreview]:
        statement = """
            SELECT
                r.id,
                r.source_key,
                r.source_title,
                r.category,
                r.normalized_category,
                r.title,
                r.summary,
                r.lead,
                r.url,
                r.published_at,
                r.fetched_at,
                r.importance_score,
                r.triage_label,
                r.is_duplicate,
                r.duplicate_of,
                r.duplicate_stage,
                r.duplicate_reason,
                r.full_text,
                r.full_text_source_url,
                r.full_text_source_title,
                r.reference_urls,
                r.extraction_mode,
                r.enrichment_status,
                r.enrichment_error,
                cp.status,
                cp.reason,
                cp.priority_label,
                r.tags
            FROM raw_items r
            LEFT JOIN content_plan_items cp ON cp.raw_item_id = r.id
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            ORDER BY
                r.fetched_at DESC,
                r.published_at DESC
            LIMIT %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (limit,))
                rows = cursor.fetchall()

        return [self._map_raw_preview_row(row) for row in rows]

    def list_raw_item_previews_for_ingest_run(self, run: PipelineRun, limit: int = 50) -> list[RawItemPreview]:
        statement = """
            SELECT
                r.id,
                r.source_key,
                r.source_title,
                r.category,
                r.normalized_category,
                r.title,
                r.summary,
                r.lead,
                r.url,
                r.published_at,
                r.fetched_at,
                r.importance_score,
                r.triage_label,
                r.is_duplicate,
                r.duplicate_of,
                r.duplicate_stage,
                r.duplicate_reason,
                r.full_text,
                r.full_text_source_url,
                r.full_text_source_title,
                r.reference_urls,
                r.extraction_mode,
                r.enrichment_status,
                r.enrichment_error,
                cp.status,
                cp.reason,
                cp.priority_label,
                r.tags
            FROM raw_items r
            LEFT JOIN content_plan_items cp ON cp.raw_item_id = r.id
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            WHERE r.fetched_at >= (%s - INTERVAL '2 minutes')
              AND r.fetched_at <= (%s + INTERVAL '2 minutes')
            ORDER BY
                r.fetched_at DESC,
                r.published_at DESC
            LIMIT %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (run.started_at, run.finished_at, limit))
                rows = cursor.fetchall()

        return [self._map_raw_preview_row(row) for row in rows]

    def list_raw_item_previews_since(self, since: datetime, limit: int = 50) -> list[RawItemPreview]:
        statement = """
            SELECT
                r.id,
                r.source_key,
                r.source_title,
                r.category,
                r.normalized_category,
                r.title,
                r.summary,
                r.lead,
                r.url,
                r.published_at,
                r.fetched_at,
                r.importance_score,
                r.triage_label,
                r.is_duplicate,
                r.duplicate_of,
                r.duplicate_stage,
                r.duplicate_reason,
                r.full_text,
                r.full_text_source_url,
                r.full_text_source_title,
                r.reference_urls,
                r.extraction_mode,
                r.enrichment_status,
                r.enrichment_error,
                cp.status,
                cp.reason,
                cp.priority_label,
                r.tags
            FROM raw_items r
            LEFT JOIN content_plan_items cp ON cp.raw_item_id = r.id
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            WHERE r.fetched_at >= (%s - INTERVAL '2 minutes')
            ORDER BY
                r.fetched_at DESC,
                r.published_at DESC
            LIMIT %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (since, limit))
                rows = cursor.fetchall()

        return [self._map_raw_preview_row(row) for row in rows]

    def list_pending_enrichment_raw_items(self, limit: int = 20, since: datetime | None = None) -> list[RawItem]:
        statement = """
            SELECT
                r.id,
                r.source_key,
                r.source_title,
                r.source_url,
                r.category,
                r.normalized_category,
                r.external_id,
                r.dedupe_key,
                r.title,
                r.summary,
                r.lead,
                r.url,
                r.published_at,
                r.fetched_at,
                r.importance_score,
                r.triage_label,
                r.is_duplicate,
                r.duplicate_of,
                r.duplicate_stage,
                r.duplicate_reason,
                r.full_text,
                r.full_text_source_url,
                r.full_text_source_title,
                r.reference_urls,
                r.extraction_mode,
                r.enrichment_status,
                r.enrichment_error,
                r.tags,
                r.payload
            FROM raw_items r
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            LEFT JOIN source_configs s ON s.key = r.source_key
            WHERE r.is_duplicate = FALSE
              AND d.raw_item_id IS NULL
              AND r.url IS NOT NULL
              AND r.fetched_at >= NOW() - INTERVAL '48 hours'
              AND (
                r.full_text IS NULL
                OR BTRIM(r.full_text) = ''
                OR r.lead IS NULL
                OR BTRIM(r.lead) = ''
                OR COALESCE(array_length(r.tags, 1), 0) = 0
              )
        """
        params: list[object] = []
        if since is not None:
            statement += " AND r.fetched_at >= (%s - INTERVAL '2 minutes')"
            params.append(since)
        statement += """
            ORDER BY
              CASE
                WHEN r.full_text IS NULL OR BTRIM(r.full_text) = '' THEN 0
                ELSE 1
              END,
              CASE
                WHEN r.lead IS NULL OR BTRIM(r.lead) = '' THEN 0
                ELSE 1
              END,
              CASE
                WHEN COALESCE(array_length(r.tags, 1), 0) = 0 THEN 0
                ELSE 1
              END,
              CASE r.triage_label
                WHEN 'high' THEN 0
                WHEN 'medium' THEN 1
                ELSE 2
              END,
              CASE COALESCE(s.source_type, '')
                WHEN 'news_sitemap' THEN 0
                WHEN 'rss' THEN 1
                WHEN 'scraping' THEN 2
                WHEN 'ai_research' THEN 3
                ELSE 4
              END,
              r.importance_score DESC,
              r.fetched_at DESC,
              r.published_at DESC
            LIMIT %s
        """
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_raw_row(row) for row in rows]

    def count_pending_enrichment_raw_items(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM raw_items r
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            WHERE r.is_duplicate = FALSE
              AND d.raw_item_id IS NULL
              AND r.url IS NOT NULL
              AND r.fetched_at >= NOW() - INTERVAL '48 hours'
              AND (
                r.full_text IS NULL
                OR BTRIM(r.full_text) = ''
                OR r.lead IS NULL
                OR BTRIM(r.lead) = ''
                OR COALESCE(array_length(r.tags, 1), 0) = 0
              )
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def get_article_by_slug(self, slug: str, *, include_hidden: bool = False) -> Article | None:
        statement = """
            SELECT
                a.id,
                a.slug,
                a.news_item_id,
                a.raw_item_id,
                a.title,
                a.lead,
                a.dek,
                a.body,
                a.category,
                a.source_title,
                a.source_url,
                a.tags,
                a.published_at,
                a.ai_reviewed,
                a.created_at,
                a.updated_at
            FROM articles a
            JOIN news_items n ON n.id = a.news_item_id
            WHERE a.slug = %s
        """

        if not include_hidden:
            statement += " AND COALESCE(n.visibility, 'public') = 'public'"

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (slug,))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._map_article_row(row)

    def get_news_item(self, news_item_id: str, *, include_hidden: bool = False) -> NewsItem | None:
        statement = """
            SELECT n.id, n.title, n.description, n.category, n.published_at, n.source, n.link, n.status, n.visibility, n.ai_reviewed, a.slug
            FROM news_items n
            LEFT JOIN articles a ON a.news_item_id = n.id
            WHERE n.id = %s
        """
        params: list[object] = [news_item_id]

        if not include_hidden:
            statement += " AND COALESCE(n.visibility, 'public') = 'public'"

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._map_news_row(row)

    def set_news_visibility(self, news_item_id: str, visibility: str) -> NewsItem | None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE news_items
                    SET visibility = %s
                    WHERE id = %s
                    """,
                    (visibility, news_item_id),
                )
            connection.commit()

        return self.get_news_item(news_item_id, include_hidden=True)

    def list_article_similarity_candidates(
        self,
        *,
        category: str,
        published_at: datetime,
        exclude_news_item_id: str | None = None,
        window_hours: int = 24,
        limit: int = 20,
    ) -> list[Article]:
        statement = """
            SELECT
                id,
                slug,
                news_item_id,
                raw_item_id,
                title,
                lead,
                dek,
                body,
                category,
                source_title,
                source_url,
                tags,
                published_at,
                ai_reviewed,
                created_at,
                updated_at
            FROM articles
            WHERE category = %s
              AND published_at >= %s
              AND published_at <= %s
        """
        params: list[object] = [
            category,
            published_at - timedelta(hours=window_hours),
            published_at,
        ]

        if exclude_news_item_id is not None:
            statement += " AND news_item_id <> %s"
            params.append(exclude_news_item_id)

        statement += " ORDER BY published_at DESC LIMIT %s"
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_article_row(row) for row in rows]

    def list_prompt_configs(self, agent_key: Optional[str] = None) -> list[PromptConfig]:
        statement = """
            SELECT
                id,
                agent_key,
                name,
                version,
                status,
                system_prompt,
                user_prompt_template,
                model,
                provider,
                notes,
                created_at
            FROM prompt_configs
        """
        params: tuple[object, ...] = ()

        if agent_key:
            statement += " WHERE agent_key = %s"
            params = (agent_key,)

        statement += " ORDER BY agent_key ASC, version DESC"

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, params)
                rows = cursor.fetchall()

        return [self._map_prompt_row(row) for row in rows]

    def list_source_sync_states(self) -> list[SourceSyncState]:
        statement = """
            SELECT
                source_key,
                source_title,
                last_fetched_at,
                last_successful_fetch_at,
                last_successful_parse_at,
                last_published_at,
                last_external_id,
                last_item_count,
                fetch_status,
                parse_status,
                fetch_error_count,
                parse_error_count,
                consecutive_failures,
                retry_count,
                last_probe_at,
                last_probe_count,
                last_probe_readiness,
                preferred_adapter,
                preferred_adapter_url,
                supports_rss,
                supports_news_sitemap,
                supports_sitemap,
                supports_scraping,
                last_probe_full_text_ok,
                last_probe_full_text_method,
                last_probe_lead_ok,
                last_probe_tags_count,
                last_probe_sample_title,
                last_probe_sample_url,
                last_status,
                last_error,
                updated_at
            FROM source_sync_state
            ORDER BY source_title ASC
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                rows = cursor.fetchall()

        return [self._map_source_sync_state_row(row) for row in rows]

    def get_source_sync_state_map(self) -> dict[str, SourceSyncState]:
        return {item.source_key: item for item in self.list_source_sync_states()}

    def get_recent_known_external_ids_by_source(
        self,
        source_keys: list[str],
        *,
        per_source_limit: int = 200,
    ) -> dict[str, set[str]]:
        if not source_keys:
            return {}

        statement = """
            SELECT source_key, external_id
            FROM (
                SELECT
                    source_key,
                    external_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY source_key
                        ORDER BY fetched_at DESC, published_at DESC
                    ) AS rn
                FROM raw_items
                WHERE source_key = ANY(%s)
                  AND external_id <> ''
            ) ranked
            WHERE rn <= %s
        """

        known_by_source: dict[str, set[str]] = {key: set() for key in source_keys}
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (source_keys, per_source_limit))
                rows = cursor.fetchall()

        for row in rows:
            source_key = str(row[0])
            external_id = str(row[1])
            known_by_source.setdefault(source_key, set()).add(external_id)

        return known_by_source

    def get_recent_known_dedupe_keys_by_source(
        self,
        source_keys: list[str],
        *,
        per_source_limit: int = 200,
    ) -> dict[str, set[str]]:
        if not source_keys:
            return {}

        statement = """
            SELECT source_key, dedupe_key
            FROM (
                SELECT
                    source_key,
                    dedupe_key,
                    ROW_NUMBER() OVER (
                        PARTITION BY source_key
                        ORDER BY fetched_at DESC, published_at DESC
                    ) AS rn
                FROM raw_items
                WHERE source_key = ANY(%s)
                  AND dedupe_key <> ''
            ) ranked
            WHERE rn <= %s
        """

        known_by_source: dict[str, set[str]] = {key: set() for key in source_keys}
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (source_keys, per_source_limit))
                rows = cursor.fetchall()

        for row in rows:
            source_key = str(row[0])
            dedupe_key = str(row[1])
            known_by_source.setdefault(source_key, set()).add(dedupe_key)

        return known_by_source

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

    def update_source_sync_state(
        self,
        source: SourceItem,
        raw_items: list[RawItem],
        *,
        fetch_status: str = "ok",
        parse_status: str = "ok",
        error: str | None = None,
        retry_count: int = 0,
    ) -> None:
        now = datetime.now(timezone.utc)
        last_fetched_at = now
        newest_item = max(raw_items, key=lambda item: (item.published_at, item.external_id), default=None)
        last_published_at = newest_item.published_at if newest_item is not None else None
        last_external_id = newest_item.external_id if newest_item is not None else None
        last_item_count = len(raw_items)
        fetch_ok = fetch_status == "ok"
        parse_ok = parse_status == "ok"
        overall_status = "ok" if (fetch_ok and parse_ok) else ("error" if error else parse_status)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO source_sync_state (
                        source_key,
                        source_title,
                        last_fetched_at,
                        last_successful_fetch_at,
                        last_successful_parse_at,
                        last_published_at,
                        last_external_id,
                        last_item_count,
                        fetch_status,
                        parse_status,
                        fetch_error_count,
                        parse_error_count,
                        consecutive_failures,
                        retry_count,
                        last_status,
                        last_error
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_key) DO UPDATE SET
                        source_title = EXCLUDED.source_title,
                        last_fetched_at = EXCLUDED.last_fetched_at,
                        last_successful_fetch_at = COALESCE(EXCLUDED.last_successful_fetch_at, source_sync_state.last_successful_fetch_at),
                        last_successful_parse_at = COALESCE(EXCLUDED.last_successful_parse_at, source_sync_state.last_successful_parse_at),
                        last_published_at = COALESCE(EXCLUDED.last_published_at, source_sync_state.last_published_at),
                        last_external_id = COALESCE(EXCLUDED.last_external_id, source_sync_state.last_external_id),
                        last_item_count = EXCLUDED.last_item_count,
                        fetch_status = EXCLUDED.fetch_status,
                        parse_status = EXCLUDED.parse_status,
                        fetch_error_count = CASE
                            WHEN EXCLUDED.fetch_status = 'ok' THEN source_sync_state.fetch_error_count
                            WHEN EXCLUDED.fetch_status = 'error' THEN source_sync_state.fetch_error_count + 1
                            ELSE source_sync_state.fetch_error_count
                        END,
                        parse_error_count = CASE
                            WHEN EXCLUDED.parse_status IN ('ok', 'empty') THEN source_sync_state.parse_error_count
                            WHEN EXCLUDED.parse_status = 'error' THEN source_sync_state.parse_error_count + 1
                            ELSE source_sync_state.parse_error_count
                        END,
                        consecutive_failures = CASE
                            WHEN EXCLUDED.fetch_status = 'ok' AND EXCLUDED.parse_status = 'ok' THEN 0
                            WHEN EXCLUDED.fetch_status = 'ok' AND EXCLUDED.parse_status = 'empty' THEN source_sync_state.consecutive_failures + 1
                            ELSE source_sync_state.consecutive_failures + 1
                        END,
                        retry_count = EXCLUDED.retry_count,
                        last_status = EXCLUDED.last_status,
                        last_error = EXCLUDED.last_error,
                        updated_at = NOW()
                    """,
                    (
                        source.key,
                        source.title,
                        last_fetched_at,
                        now if fetch_ok else None,
                        now if parse_ok else None,
                        last_published_at,
                        last_external_id,
                        last_item_count,
                        fetch_status,
                        parse_status,
                        0,
                        0,
                        0 if (fetch_ok and parse_ok) else 1,
                        retry_count,
                        overall_status,
                        error,
                    ),
                )
            connection.commit()

    def record_source_probe(
        self,
        source: SourceItem,
        *,
        ok: bool,
        item_count: int,
        message: str,
        readiness: str = "unknown",
        preferred_adapter: str | None = None,
        preferred_adapter_url: str | None = None,
        supports_rss: bool = False,
        supports_news_sitemap: bool = False,
        supports_sitemap: bool = False,
        supports_scraping: bool = False,
        full_text_ok: bool = False,
        full_text_method: str | None = None,
        lead_ok: bool = False,
        tags_count: int = 0,
        sample_title: str | None = None,
        sample_url: str | None = None,
    ) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO source_sync_state (
                        source_key,
                        source_title,
                        last_probe_at,
                        last_probe_count,
                        last_probe_readiness,
                        preferred_adapter,
                        preferred_adapter_url,
                        supports_rss,
                        supports_news_sitemap,
                        supports_sitemap,
                        supports_scraping,
                        last_probe_full_text_ok,
                        last_probe_full_text_method,
                        last_probe_lead_ok,
                        last_probe_tags_count,
                        last_probe_sample_title,
                        last_probe_sample_url,
                        last_status,
                        last_error
                    )
                    VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_key) DO UPDATE SET
                        source_title = EXCLUDED.source_title,
                        last_probe_at = EXCLUDED.last_probe_at,
                        last_probe_count = EXCLUDED.last_probe_count,
                        last_probe_readiness = EXCLUDED.last_probe_readiness,
                        preferred_adapter = EXCLUDED.preferred_adapter,
                        preferred_adapter_url = EXCLUDED.preferred_adapter_url,
                        supports_rss = EXCLUDED.supports_rss,
                        supports_news_sitemap = EXCLUDED.supports_news_sitemap,
                        supports_sitemap = EXCLUDED.supports_sitemap,
                        supports_scraping = EXCLUDED.supports_scraping,
                        last_probe_full_text_ok = EXCLUDED.last_probe_full_text_ok,
                        last_probe_full_text_method = EXCLUDED.last_probe_full_text_method,
                        last_probe_lead_ok = EXCLUDED.last_probe_lead_ok,
                        last_probe_tags_count = EXCLUDED.last_probe_tags_count,
                        last_probe_sample_title = EXCLUDED.last_probe_sample_title,
                        last_probe_sample_url = EXCLUDED.last_probe_sample_url,
                        last_status = EXCLUDED.last_status,
                        last_error = EXCLUDED.last_error,
                        updated_at = NOW()
                    """,
                    (
                        source.key,
                        source.title,
                        item_count,
                        readiness,
                        preferred_adapter,
                        preferred_adapter_url,
                        supports_rss,
                        supports_news_sitemap,
                        supports_sitemap,
                        supports_scraping,
                        full_text_ok,
                        full_text_method,
                        lead_ok,
                        tags_count,
                        sample_title,
                        sample_url,
                        "probe_ok" if ok else "probe_error",
                        None if ok else message,
                    ),
                )
            connection.commit()

    def get_active_prompt(self, agent_key: str) -> PromptConfig:
        statement = """
            SELECT
                id,
                agent_key,
                name,
                version,
                status,
                system_prompt,
                user_prompt_template,
                model,
                provider,
                notes,
                created_at
            FROM prompt_configs
            WHERE agent_key = %s AND status = 'active'
            ORDER BY version DESC
            LIMIT 1
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (agent_key,))
                row = cursor.fetchone()

        if row is None:
            raise LookupError(f"No active prompt config found for {agent_key}.")

        return self._map_prompt_row(row)

    def create_prompt_version(
        self,
        *,
        agent_key: str,
        name: str,
        system_prompt: str,
        user_prompt_template: str,
        model: str,
        notes: str = "",
        activate: bool = True,
    ) -> PromptConfig:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM prompt_configs WHERE agent_key = %s",
                    (agent_key,),
                )
                next_version = int(cursor.fetchone()[0]) + 1

                if activate:
                    cursor.execute(
                        "UPDATE prompt_configs SET status = 'archived' WHERE agent_key = %s AND status = 'active'",
                        (agent_key,),
                    )

                prompt_id = f"prompt:{agent_key}:v{next_version}"
                cursor.execute(
                    """
                    INSERT INTO prompt_configs (
                        id,
                        agent_key,
                        name,
                        version,
                        status,
                        system_prompt,
                        user_prompt_template,
                        model,
                        provider,
                        notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        prompt_id,
                        agent_key,
                        name,
                        next_version,
                        "active" if activate else "draft",
                        system_prompt,
                        user_prompt_template,
                        model,
                        "internal",
                        notes,
                    ),
                )
            connection.commit()

        return self.get_prompt(prompt_id)

    def get_prompt(self, prompt_id: str) -> PromptConfig:
        statement = """
            SELECT
                id,
                agent_key,
                name,
                version,
                status,
                system_prompt,
                user_prompt_template,
                model,
                provider,
                notes,
                created_at
            FROM prompt_configs
            WHERE id = %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (prompt_id,))
                row = cursor.fetchone()

        if row is None:
            raise LookupError(f"Prompt {prompt_id} was not found.")

        return self._map_prompt_row(row)

    def set_prompt_status(self, prompt_id: str, status: str) -> PromptConfig:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT agent_key FROM prompt_configs WHERE id = %s", (prompt_id,))
                row = cursor.fetchone()
                if row is None:
                    raise LookupError(f"Prompt {prompt_id} was not found.")

                agent_key = str(row[0])
                if status == "active":
                    cursor.execute(
                        "UPDATE prompt_configs SET status = 'archived' WHERE agent_key = %s AND status = 'active'",
                        (agent_key,),
                    )

                cursor.execute(
                    "UPDATE prompt_configs SET status = %s WHERE id = %s",
                    (status, prompt_id),
                )
            connection.commit()

        return self.get_prompt(prompt_id)

    def delete_archived_prompt_versions(self) -> int:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM prompt_configs WHERE status <> 'active'")
                deleted_count = cursor.rowcount or 0
            connection.commit()

        return int(deleted_count)

    def maybe_activate_recommended_prompt(self, agent_key: str, recommended_prompt_id: str) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id
                    FROM prompt_configs
                    WHERE agent_key = %s AND status = 'active'
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (agent_key,),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        "UPDATE prompt_configs SET status = 'active' WHERE id = %s",
                        (recommended_prompt_id,),
                    )
                    connection.commit()
                    return

                active_id = str(row[0])
                legacy_system_prompt_ids = {
                    "writer": {"prompt:writer:v1", "prompt:writer:v2"},
                    "editor": {"prompt:editor:v1", "prompt:editor:v2"},
                }
                if active_id not in legacy_system_prompt_ids.get(agent_key, set()):
                    return

                cursor.execute(
                    "UPDATE prompt_configs SET status = 'archived' WHERE agent_key = %s AND status = 'active'",
                    (agent_key,),
                )
                cursor.execute(
                    "UPDATE prompt_configs SET status = 'active' WHERE id = %s",
                    (recommended_prompt_id,),
                )
            connection.commit()

    def list_drafts(
        self,
        limit: int = 20,
        status: Optional[str] = None,
        review_status: Optional[str] = None,
    ) -> list[DraftArticle]:
        statement = """
            SELECT
                id,
                raw_item_id,
                title,
                dek,
                body,
                writer_title,
                writer_dek,
                writer_body,
                category,
                source_title,
                source_url,
                published_at,
                status,
                review_status,
                review_summary,
                publish_decision,
                publish_reason,
                prompt_config_id,
                prompt_name,
                model,
                generation_mode,
                created_at,
                updated_at
            FROM draft_articles
        """
        params: list[object] = []
        clauses: list[str] = []

        if status:
            clauses.append("status = %s")
            params.append(status)
        if review_status:
            clauses.append("review_status = %s")
            params.append(review_status)

        if clauses:
            statement += " WHERE " + " AND ".join(clauses)

        statement += " ORDER BY published_at DESC, updated_at DESC LIMIT %s"
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_draft_row(row) for row in rows]

    def list_content_plan(self, limit: int = 20, status: Optional[str] = None) -> list[ContentPlanItem]:
        statement = """
            SELECT
                id,
                raw_item_id,
                title,
                source_title,
                category,
                priority_score,
                priority_label,
                planned_format,
                status,
                reason,
                created_at,
                updated_at
            FROM content_plan_items
        """
        params: list[object] = []

        if status:
            statement += " WHERE status = %s"
            params.append(status)

        statement += " ORDER BY priority_score DESC, updated_at DESC LIMIT %s"
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_content_plan_row(row) for row in rows]

    def get_content_plan_item(self, item_id: str) -> ContentPlanItem | None:
        statement = """
            SELECT
                id,
                raw_item_id,
                title,
                source_title,
                category,
                priority_score,
                priority_label,
                planned_format,
                status,
                reason,
                created_at,
                updated_at
            FROM content_plan_items
            WHERE id = %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (item_id,))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._map_content_plan_row(row)

    def list_reviews(self, limit: int = 20) -> list[EditorReview]:
        statement = """
            SELECT
                id,
                draft_id,
                status,
                decision,
                summary,
                notes,
                revised_title,
                revised_dek,
                revised_body,
                prompt_config_id,
                prompt_name,
                model,
                created_at
            FROM editor_reviews
            ORDER BY created_at DESC
            LIMIT %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (limit,))
                rows = cursor.fetchall()

        return [self._map_review_row(row) for row in rows]

    def list_raw_candidates_for_plan(self, limit: int = 6, since: datetime | None = None) -> list[RawItem]:
        statement = """
            SELECT
                r.id,
                r.source_key,
                r.source_title,
                r.source_url,
                r.category,
                r.normalized_category,
                r.external_id,
                r.dedupe_key,
                r.title,
                r.summary,
                r.lead,
                r.url,
                r.published_at,
                r.fetched_at,
                r.importance_score,
                r.triage_label,
                r.is_duplicate,
                r.duplicate_of,
                r.duplicate_stage,
                r.duplicate_reason,
                r.full_text,
                r.full_text_source_url,
                r.full_text_source_title,
                r.reference_urls,
                r.extraction_mode,
                r.enrichment_status,
                r.enrichment_error,
                r.tags,
                r.payload
            FROM raw_items r
            LEFT JOIN content_plan_items cp ON cp.raw_item_id = r.id
            WHERE r.is_duplicate = FALSE
              AND cp.raw_item_id IS NULL
        """
        params: list[object] = []
        if since is not None:
            statement += " AND r.fetched_at >= (%s - INTERVAL '2 minutes')"
            params.append(since)
        statement += """
            ORDER BY
                CASE r.triage_label
                    WHEN 'high' THEN 0
                    WHEN 'medium' THEN 1
                    ELSE 2
                END,
                r.importance_score DESC,
                r.fetched_at DESC,
                r.published_at DESC
            LIMIT %s
        """
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_raw_row(row) for row in rows]

    def list_planned_raw_items_for_drafts(self, limit: int = 3, since: datetime | None = None) -> list[RawItem]:
        statement = """
            SELECT
                r.id,
                r.source_key,
                r.source_title,
                r.source_url,
                r.category,
                r.normalized_category,
                r.external_id,
                r.dedupe_key,
                r.title,
                r.summary,
                r.lead,
                r.url,
                r.published_at,
                r.fetched_at,
                r.importance_score,
                r.triage_label,
                r.is_duplicate,
                r.duplicate_of,
                r.duplicate_stage,
                r.duplicate_reason,
                r.full_text,
                r.full_text_source_url,
                r.full_text_source_title,
                r.reference_urls,
                r.extraction_mode,
                r.enrichment_status,
                r.enrichment_error,
                r.tags,
                r.payload
            FROM content_plan_items cp
            JOIN raw_items r ON r.id = cp.raw_item_id
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            WHERE cp.status = 'planned'
              AND d.raw_item_id IS NULL
        """
        params: list[object] = []
        if since is not None:
            statement += " AND r.fetched_at >= (%s - INTERVAL '2 minutes')"
            params.append(since)
        statement += " ORDER BY cp.priority_score DESC, r.published_at DESC LIMIT %s"
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_raw_row(row) for row in rows]

    def count_planned_raw_items_for_drafts(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM content_plan_items cp
            JOIN raw_items r ON r.id = cp.raw_item_id
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            WHERE cp.status = 'planned'
              AND d.raw_item_id IS NULL
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def list_publishable_drafts(self, limit: int = 5, since: datetime | None = None) -> list[DraftArticle]:
        statement = """
            SELECT
                d.id,
                d.raw_item_id,
                d.title,
                d.dek,
                d.body,
                d.writer_title,
                d.writer_dek,
                d.writer_body,
                d.category,
                d.source_title,
                d.source_url,
                d.published_at,
                d.status,
                d.review_status,
                d.review_summary,
                d.publish_decision,
                d.publish_reason,
                d.prompt_config_id,
                d.prompt_name,
                d.model,
                d.generation_mode,
                d.created_at,
                d.updated_at
            FROM draft_articles d
            JOIN raw_items r ON r.id = d.raw_item_id
            WHERE d.status = 'ready_for_publish'
              AND d.review_status = 'reviewed'
              AND d.publish_decision = 'publish_auto'
        """
        params: list[object] = []
        if since is not None:
            statement += " AND r.fetched_at >= (%s - INTERVAL '2 minutes')"
            params.append(since)
        statement += " ORDER BY d.updated_at ASC, d.published_at DESC LIMIT %s"
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_draft_row(row) for row in rows]

    def count_publishable_drafts(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM draft_articles
            WHERE status = 'ready_for_publish'
              AND review_status = 'reviewed'
              AND publish_decision = 'publish_auto'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def count_ready_to_publish_with_existing_article(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM draft_articles d
            JOIN articles a ON a.raw_item_id = d.raw_item_id
            WHERE d.status = 'ready_for_publish'
              AND d.review_status = 'reviewed'
              AND d.publish_decision = 'publish_auto'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def count_articles_missing_published_draft(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM articles a
            LEFT JOIN draft_articles d ON d.raw_item_id = a.raw_item_id
            WHERE d.raw_item_id IS NULL
               OR d.status <> 'published'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def count_published_drafts_missing_article(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM draft_articles d
            LEFT JOIN articles a ON a.raw_item_id = d.raw_item_id
            WHERE d.status = 'published'
              AND a.raw_item_id IS NULL
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def count_published_drafts_missing_news_item(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM draft_articles d
            JOIN raw_items r ON r.id = d.raw_item_id
            LEFT JOIN news_items n ON n.id = r.external_id
            WHERE d.status = 'published'
              AND n.id IS NULL
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def count_multiple_articles_per_news_item(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM (
                SELECT news_item_id
                FROM articles
                GROUP BY news_item_id
                HAVING COUNT(*) > 1
            ) duplicates
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def get_raw_item(self, raw_item_id: str) -> RawItem | None:
        statement = """
            SELECT
                id,
                source_key,
                source_title,
                source_url,
                category,
                normalized_category,
                external_id,
                dedupe_key,
                title,
                summary,
                lead,
                url,
                published_at,
                fetched_at,
                importance_score,
                triage_label,
                is_duplicate,
                duplicate_of,
                duplicate_stage,
                duplicate_reason,
                full_text,
                full_text_source_url,
                full_text_source_title,
                reference_urls,
                extraction_mode,
                enrichment_status,
                enrichment_error,
                tags,
                payload
            FROM raw_items
            WHERE id = %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (raw_item_id,))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._map_raw_row(row)

    def get_draft(self, draft_id: str) -> DraftArticle | None:
        statement = """
            SELECT
                id,
                raw_item_id,
                title,
                dek,
                body,
                writer_title,
                writer_dek,
                writer_body,
                category,
                source_title,
                source_url,
                published_at,
                status,
                review_status,
                review_summary,
                publish_decision,
                publish_reason,
                prompt_config_id,
                prompt_name,
                model,
                generation_mode,
                created_at,
                updated_at
            FROM draft_articles
            WHERE id = %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (draft_id,))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._map_draft_row(row)

    def upsert_draft(self, draft: DraftArticle) -> DraftArticle:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO draft_articles (
                        id,
                        raw_item_id,
                        title,
                        dek,
                        body,
                        writer_title,
                        writer_dek,
                        writer_body,
                        category,
                        source_title,
                        source_url,
                        published_at,
                        status,
                        review_status,
                        review_summary,
                        publish_decision,
                        publish_reason,
                        prompt_config_id,
                        prompt_name,
                        model,
                        generation_mode
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        dek = EXCLUDED.dek,
                        body = EXCLUDED.body,
                        writer_title = COALESCE(draft_articles.writer_title, EXCLUDED.writer_title),
                        writer_dek = COALESCE(draft_articles.writer_dek, EXCLUDED.writer_dek),
                        writer_body = COALESCE(draft_articles.writer_body, EXCLUDED.writer_body),
                        category = EXCLUDED.category,
                        source_title = EXCLUDED.source_title,
                        source_url = EXCLUDED.source_url,
                        published_at = EXCLUDED.published_at,
                        status = EXCLUDED.status,
                        review_status = EXCLUDED.review_status,
                        review_summary = EXCLUDED.review_summary,
                        publish_decision = EXCLUDED.publish_decision,
                        publish_reason = EXCLUDED.publish_reason,
                        prompt_config_id = EXCLUDED.prompt_config_id,
                        prompt_name = EXCLUDED.prompt_name,
                        model = EXCLUDED.model,
                        generation_mode = EXCLUDED.generation_mode,
                        updated_at = NOW()
                    """,
                    (
                        draft.id,
                        draft.raw_item_id,
                        draft.title,
                        draft.dek,
                        draft.body,
                        draft.writer_title,
                        draft.writer_dek,
                        draft.writer_body,
                        draft.category,
                        draft.source_title,
                        draft.source_url,
                        draft.published_at,
                        draft.status,
                        draft.review_status,
                        draft.review_summary,
                        draft.publish_decision,
                        draft.publish_reason,
                        draft.prompt_config_id,
                        draft.prompt_name,
                        draft.model,
                        draft.generation_mode,
                    ),
                )
            connection.commit()

        stored = self.get_draft(draft.id)
        if stored is None:
            raise LookupError(f"Draft {draft.id} was not stored.")
        return stored

    def upsert_review(self, review: EditorReview) -> EditorReview:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO editor_reviews (
                        id,
                        draft_id,
                        status,
                        decision,
                        summary,
                        notes,
                        revised_title,
                        revised_dek,
                        revised_body,
                        prompt_config_id,
                        prompt_name,
                        model
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (draft_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        decision = EXCLUDED.decision,
                        summary = EXCLUDED.summary,
                        notes = EXCLUDED.notes,
                        revised_title = EXCLUDED.revised_title,
                        revised_dek = EXCLUDED.revised_dek,
                        revised_body = EXCLUDED.revised_body,
                        prompt_config_id = EXCLUDED.prompt_config_id,
                        prompt_name = EXCLUDED.prompt_name,
                        model = EXCLUDED.model,
                        created_at = NOW()
                    """,
                    (
                        review.id,
                        review.draft_id,
                        review.status,
                        review.decision,
                        review.summary,
                        review.notes,
                        review.revised_title,
                        review.revised_dek,
                        review.revised_body,
                        review.prompt_config_id,
                        review.prompt_name,
                        review.model,
                    ),
                )
            connection.commit()

        stored = next((item for item in self.list_reviews(limit=100) if item.draft_id == review.draft_id), None)
        if stored is None:
            raise LookupError(f"Review for draft {review.draft_id} was not stored.")
        return stored

    def upsert_content_plan_item(self, item: ContentPlanItem) -> ContentPlanItem:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO content_plan_items (
                        id,
                        raw_item_id,
                        title,
                        source_title,
                        category,
                        priority_score,
                        priority_label,
                        planned_format,
                        status,
                        reason
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        source_title = EXCLUDED.source_title,
                        category = EXCLUDED.category,
                        priority_score = EXCLUDED.priority_score,
                        priority_label = EXCLUDED.priority_label,
                        planned_format = EXCLUDED.planned_format,
                        status = EXCLUDED.status,
                        reason = EXCLUDED.reason,
                        updated_at = NOW()
                    """,
                    (
                        item.id,
                        item.raw_item_id,
                        item.title,
                        item.source_title,
                        item.category,
                        item.priority_score,
                        item.priority_label,
                        item.planned_format,
                        item.status,
                        item.reason,
                    ),
                )
            connection.commit()

        stored = self.get_content_plan_item(item.id)
        if stored is None:
            raise LookupError(f"Content plan item {item.id} was not stored.")
        return stored

    def set_content_plan_status(self, raw_item_id: str, status: str) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE content_plan_items
                    SET status = %s,
                        updated_at = NOW()
                    WHERE raw_item_id = %s
                    """,
                    (status, raw_item_id),
                )
            connection.commit()

    def set_draft_review_status(
        self,
        draft_id: str,
        *,
        review_status: str,
        status: str,
        review_summary: str,
        publish_decision: str | None = None,
        publish_reason: str | None = None,
    ) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE draft_articles
                    SET review_status = %s,
                        status = %s,
                        review_summary = %s,
                        publish_decision = COALESCE(%s, publish_decision),
                        publish_reason = COALESCE(%s, publish_reason),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (review_status, status, review_summary, publish_decision, publish_reason, draft_id),
                )
            connection.commit()

    def ingest_demo_batch(self) -> list[NewsItem]:
        timestamp = int(datetime.now(timezone.utc).timestamp())
        generated = self._default_news_item(
            item_id=str(timestamp),
            title="Scheduler нашел новый инфоповод и отправил его на AI-редактуру",
            description=(
                "Это демонстрационная запись для MVP: ingestion добавляет новость, "
                "после чего она становится доступна для публикации на сайте."
            ),
            category="Система",
            source="scheduler demo",
            link=f"https://example.com/news/system-{timestamp}",
        )
        return self.upsert_many([generated])

    def insert_raw_items(self, items: list[RawItem]) -> InsertRawItemsResult:
        inserted = 0
        skipped_items: list[dict[str, str]] = []
        dedupe_keys = sorted({item.dedupe_key for item in items if item.dedupe_key})

        with self.connect() as connection:
            with connection.cursor() as cursor:
                known_dedupe_map: dict[str, tuple[str, str]] = {}
                if dedupe_keys:
                    cursor.execute(
                        """
                        SELECT dedupe_key, id, title
                        FROM raw_items
                        WHERE dedupe_key = ANY(%s)
                        """,
                        (dedupe_keys,),
                    )
                    known_dedupe_map = {
                        str(row[0]): (str(row[1]), str(row[2] or ""))
                        for row in cursor.fetchall()
                    }
                recent_similarity_candidates = self._load_recent_dedup_candidates(cursor, window_hours=24)
                pending_similarity_candidates: dict[str, list[tuple[str, str, str]]] = {}

                for item in items:
                    existing_raw = known_dedupe_map.get(item.dedupe_key)
                    if existing_raw and existing_raw[0] != item.id:
                        item.is_duplicate = True
                        item.duplicate_of = existing_raw[0]
                        item.duplicate_stage = "ingest"
                        item.duplicate_reason = (
                            f"Точный дубль найден при первичной загрузке по dedupe key / URL. "
                            f"Совпало с новостью: «{existing_raw[1] or existing_raw[0]}»."
                        )
                    elif item.is_duplicate and not item.duplicate_of:
                        exact_match = known_dedupe_map.get(item.dedupe_key)
                        item.duplicate_of = exact_match[0] if exact_match is not None else item.id
                        item.duplicate_stage = item.duplicate_stage or "ingest"
                        item.duplicate_reason = item.duplicate_reason or "Новость помечена как дубль при первичной загрузке."
                    else:
                        duplicate_match = self._find_near_duplicate_match(
                            item,
                            recent_similarity_candidates,
                            pending_similarity_candidates,
                        )
                        if duplicate_match is not None and duplicate_match[0] != item.id:
                            item.is_duplicate = True
                            item.duplicate_of = duplicate_match[0]
                            item.duplicate_stage = "ingest"
                            item.duplicate_reason = (
                                "Похожая новость найдена при первичной загрузке среди свежих raw items. "
                                f"Совпало с новостью: «{duplicate_match[1]}» (similarity {duplicate_match[2]:.2f})."
                            )

                    cursor.execute(
                        """
                        INSERT INTO raw_items (
                            id,
                            source_key,
                            source_title,
                            source_url,
                            category,
                            normalized_category,
                            external_id,
                            dedupe_key,
                            title,
                            summary,
                            lead,
                            url,
                            published_at,
                            fetched_at,
                            importance_score,
                            triage_label,
                            is_duplicate,
                            duplicate_of,
                            duplicate_stage,
                            duplicate_reason,
                            full_text,
                            full_text_source_url,
                            full_text_source_title,
                            reference_urls,
                            extraction_mode,
                            enrichment_status,
                            enrichment_error,
                            tags,
                            payload
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        RETURNING id
                        """,
                        (
                            item.id,
                            item.source_key,
                            item.source_title,
                            item.source_url,
                            item.category,
                            item.normalized_category,
                            item.external_id,
                            item.dedupe_key,
                            item.title,
                            item.summary,
                            item.lead,
                            item.url,
                            item.published_at,
                            item.fetched_at,
                            item.importance_score,
                            item.triage_label,
                            item.is_duplicate,
                            item.duplicate_of,
                            item.duplicate_stage,
                            item.duplicate_reason,
                            item.full_text,
                            item.full_text_source_url,
                            item.full_text_source_title,
                            item.reference_urls,
                            item.extraction_mode,
                            item.enrichment_status,
                            item.enrichment_error,
                            item.tags,
                            item.payload,
                        ),
                    )
                    if cursor.fetchone():
                        inserted += 1
                        known_dedupe_map[item.dedupe_key] = (item.id, item.title)
                        if not item.is_duplicate:
                            combined_text = self._build_similarity_text(item)
                            recent_similarity_candidates.setdefault(item.normalized_category, []).append(
                                (item.id, item.title, combined_text)
                            )
                            pending_similarity_candidates.setdefault(item.normalized_category, []).append(
                                (item.id, item.title, combined_text)
                            )
                    else:
                        skipped_items.append(
                            {
                                "title": item.title,
                                "reason": item.duplicate_reason
                                or "Новость уже была сохранена ранее и не была добавлена повторно.",
                            }
                        )
            connection.commit()

        return InsertRawItemsResult(inserted_count=inserted, skipped_items=skipped_items)

    def prefilter_known_raw_items(self, items: list[RawItem]) -> PrefilterRawItemsResult:
        if not items:
            return PrefilterRawItemsResult(fresh_items=[], skipped_items=[])

        dedupe_keys = sorted({item.dedupe_key for item in items if item.dedupe_key})
        if not dedupe_keys:
            return PrefilterRawItemsResult(fresh_items=items, skipped_items=[])

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT dedupe_key
                    FROM raw_items
                    WHERE dedupe_key = ANY(%s)
                    """,
                    (dedupe_keys,),
                )
                known_dedupe_keys = {str(row[0]) for row in cursor.fetchall()}

        if not known_dedupe_keys:
            return PrefilterRawItemsResult(fresh_items=items, skipped_items=[])

        fresh_items: list[RawItem] = []
        skipped_items: list[dict[str, str]] = []
        for item in items:
            if item.dedupe_key in known_dedupe_keys:
                skipped_items.append(
                    {
                        "title": item.title,
                        "reason": "Новость уже была загружена ранее и отсечена до повторного сохранения.",
                    }
                )
                continue
            fresh_items.append(item)

        return PrefilterRawItemsResult(fresh_items=fresh_items, skipped_items=skipped_items)

    def update_raw_item_enrichment(
        self,
        raw_item_id: str,
        *,
        title: str | None = None,
        summary: str | None = None,
        full_text: str | None = None,
        lead: str | None = None,
        full_text_source_url: str | None = None,
        full_text_source_title: str | None = None,
        reference_urls: list[str] | None = None,
        extraction_mode: str | None = None,
        enrichment_status: str | None = None,
        enrichment_error: str | None = None,
        tags: list[str] | None = None,
    ) -> RawItem | None:
        cleaned_title = (title or "").strip() or None
        cleaned_summary = (summary or "").strip() or None
        cleaned_full_text = (full_text or "").strip() or None
        cleaned_lead = (lead or "").strip() or None
        cleaned_full_text_source_url = (full_text_source_url or "").strip() or None
        cleaned_full_text_source_title = (full_text_source_title or "").strip() or None
        cleaned_reference_urls = [value.strip() for value in (reference_urls or []) if value.strip()]
        cleaned_extraction_mode = (extraction_mode or "").strip() or None
        cleaned_enrichment_status = (enrichment_status or "").strip() or None
        cleaned_enrichment_error = (enrichment_error or "").strip() or None
        cleaned_tags = [value.strip() for value in (tags or []) if value.strip()]

        if (
            cleaned_title is None
            and cleaned_summary is None
            and cleaned_full_text is None
            and cleaned_lead is None
            and cleaned_full_text_source_url is None
            and cleaned_full_text_source_title is None
            and not cleaned_reference_urls
            and cleaned_extraction_mode is None
            and cleaned_enrichment_status is None
            and cleaned_enrichment_error is None
            and not cleaned_tags
        ):
            return self.get_raw_item(raw_item_id)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE raw_items
                    SET title = COALESCE(%s, title),
                        summary = COALESCE(%s, summary),
                        full_text = COALESCE(%s, full_text),
                        lead = COALESCE(%s, lead),
                        full_text_source_url = COALESCE(%s, full_text_source_url),
                        full_text_source_title = COALESCE(%s, full_text_source_title),
                        reference_urls = CASE WHEN %s::TEXT[] <> ARRAY[]::TEXT[] THEN %s ELSE reference_urls END,
                        extraction_mode = COALESCE(%s, extraction_mode),
                        enrichment_status = COALESCE(%s, enrichment_status),
                        enrichment_error = COALESCE(%s, enrichment_error),
                        tags = CASE WHEN %s::TEXT[] <> ARRAY[]::TEXT[] THEN %s ELSE tags END
                    WHERE id = %s
                    """,
                    (
                        cleaned_title,
                        cleaned_summary,
                        cleaned_full_text,
                        cleaned_lead,
                        cleaned_full_text_source_url,
                        cleaned_full_text_source_title,
                        cleaned_reference_urls,
                        cleaned_reference_urls,
                        cleaned_extraction_mode,
                        cleaned_enrichment_status,
                        cleaned_enrichment_error,
                        cleaned_tags,
                        cleaned_tags,
                        raw_item_id,
                    ),
                )
            connection.commit()

        return self.get_raw_item(raw_item_id)

    def update_raw_item_full_text(self, raw_item_id: str, full_text: str) -> RawItem | None:
        return self.update_raw_item_enrichment(raw_item_id, full_text=full_text)

    def recheck_raw_item_duplicate_after_enrichment(
        self,
        raw_item_id: str,
        *,
        window_hours: int = 24,
    ) -> RawItem | None:
        item = self.get_raw_item(raw_item_id)
        if item is None or item.is_duplicate:
            return item

        candidate_texts: dict[str, list[tuple[str, str, str]]] = {}
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, normalized_category, title, summary, full_text
                    FROM raw_items
                    WHERE id <> %s
                      AND is_duplicate = FALSE
                      AND fetched_at >= %s
                    ORDER BY fetched_at DESC, published_at DESC
                    """,
                    (
                        raw_item_id,
                        datetime.now(timezone.utc) - timedelta(hours=window_hours),
                    ),
                )
                rows = cursor.fetchall()

        for row in rows:
            candidate_id = str(row[0])
            category = str(row[1])
            title = str(row[2] or "")
            summary = str(row[3] or "")
            full_text = str(row[4] or "")
            source_text = full_text or summary
            candidate_texts.setdefault(category, []).append(
                (candidate_id, title, self._normalize_similarity_text(f"{title} {source_text}"))
            )

        duplicate_match = self._find_near_duplicate_match(
            item,
            recent_similarity_candidates=candidate_texts,
            pending_similarity_candidates={},
        )
        if not duplicate_match:
            return item

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE raw_items
                    SET is_duplicate = TRUE,
                        duplicate_of = %s,
                        duplicate_stage = 'after_enrichment',
                        duplicate_reason = %s
                    WHERE id = %s
                    """,
                    (
                        duplicate_match[0],
                        (
                            "Похожая новость найдена после добора full text и нормализации заголовка. "
                            f"Совпало с новостью: «{duplicate_match[1]}» (similarity {duplicate_match[2]:.2f})."
                        ),
                        raw_item_id,
                    ),
                )
            connection.commit()

        return self.get_raw_item(raw_item_id)

    def upsert_many(self, items: list[NewsItem]) -> list[NewsItem]:
        added: list[NewsItem] = []

        with self.connect() as connection:
            with connection.cursor() as cursor:
                for item in items:
                    cursor.execute(
                        """
                        INSERT INTO news_items (
                            id,
                            title,
                            description,
                            category,
                            published_at,
                            source,
                            link,
                            status,
                            ai_reviewed
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        RETURNING id
                        """,
                        (
                            item.id,
                            item.title,
                            item.description,
                            item.category,
                            item.published_at,
                            item.source,
                            item.link,
                            item.status,
                            item.ai_reviewed,
                        ),
                    )
                    if cursor.fetchone():
                        added.append(item)
            connection.commit()

        return added

    def publish_draft_to_news(self, draft: DraftArticle, raw_item: RawItem) -> NewsItem:
        if draft.generation_mode == "template" or draft.status == "fallback_only":
            raise ValueError("Template fallback drafts must never be published.")

        public_published_at = _build_public_published_at(raw_item)
        article = self.upsert_article(draft, raw_item, public_published_at=public_published_at)
        published_item = NewsItem(
            id=raw_item.external_id,
            title=draft.title,
            description=draft.dek,
            category=draft.category,
            published_at=public_published_at,
            source=raw_item.source_title,
            link=raw_item.url,
            status="published",
            ai_reviewed=True,
            article_slug=article.slug,
            visibility="public",
        )

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                        INSERT INTO news_items (
                            id,
                            title,
                            description,
                            category,
                        published_at,
                        source,
                        link,
                        status,
                        ai_reviewed
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        category = EXCLUDED.category,
                        published_at = EXCLUDED.published_at,
                        source = EXCLUDED.source,
                        link = EXCLUDED.link,
                        status = EXCLUDED.status,
                        ai_reviewed = EXCLUDED.ai_reviewed
                    """,
                    (
                        published_item.id,
                        published_item.title,
                        published_item.description,
                        published_item.category,
                        published_item.published_at,
                        published_item.source,
                            published_item.link,
                            published_item.status,
                            published_item.ai_reviewed,
                        ),
                    )
            connection.commit()

        return published_item

    def reflow_public_published_at_for_articles(self, *, limit: int = 500) -> int:
        statement = """
            SELECT
                a.id,
                n.id,
                r.source_key,
                r.external_id,
                r.title,
                r.fetched_at
            FROM articles a
            JOIN news_items n ON n.id = a.news_item_id
            JOIN raw_items r ON r.id = a.raw_item_id
            WHERE n.ai_reviewed = TRUE
            ORDER BY r.fetched_at DESC
            LIMIT %s
        """
        rows: list[tuple[object, ...]]
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (limit,))
                rows = cursor.fetchall()

                for row in rows:
                    public_published_at = _build_public_published_at_from_values(
                        source_key=str(row[2]),
                        external_id=str(row[3]),
                        title=str(row[4]),
                        fetched_at=row[5],
                    )
                    cursor.execute(
                        """
                        UPDATE articles
                        SET published_at = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (public_published_at, row[0]),
                    )
                    cursor.execute(
                        """
                        UPDATE news_items
                        SET published_at = %s
                        WHERE id = %s
                        """,
                        (public_published_at, row[1]),
                    )
            connection.commit()

        return len(rows)

    def upsert_article(
        self,
        draft: DraftArticle,
        raw_item: RawItem,
        *,
        public_published_at: datetime | None = None,
    ) -> Article:
        display_published_at = public_published_at or _build_public_published_at(raw_item)
        article = Article(
            id=f"article:{raw_item.external_id}",
            slug=_build_article_slug(draft.title, raw_item.external_id),
            news_item_id=raw_item.external_id,
            raw_item_id=raw_item.id,
            title=draft.title,
            lead=raw_item.lead,
            dek=draft.dek,
            body=draft.body,
            category=draft.category,
            source_title=raw_item.source_title,
            source_url=raw_item.url,
            tags=raw_item.tags,
            published_at=display_published_at,
            ai_reviewed=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO articles (
                        id,
                        slug,
                        news_item_id,
                        raw_item_id,
                        title,
                        lead,
                        dek,
                        body,
                        category,
                        source_title,
                        source_url,
                        tags,
                        published_at,
                        ai_reviewed
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        slug = EXCLUDED.slug,
                        news_item_id = EXCLUDED.news_item_id,
                        raw_item_id = EXCLUDED.raw_item_id,
                        title = EXCLUDED.title,
                        lead = EXCLUDED.lead,
                        dek = EXCLUDED.dek,
                        body = EXCLUDED.body,
                        category = EXCLUDED.category,
                        source_title = EXCLUDED.source_title,
                        source_url = EXCLUDED.source_url,
                        tags = EXCLUDED.tags,
                        published_at = EXCLUDED.published_at,
                        ai_reviewed = EXCLUDED.ai_reviewed,
                        updated_at = NOW()
                    """,
                    (
                        article.id,
                        article.slug,
                        article.news_item_id,
                        article.raw_item_id,
                        article.title,
                        article.lead,
                        article.dek,
                        article.body,
                        article.category,
                        article.source_title,
                        article.source_url,
                        article.tags,
                        article.published_at,
                        article.ai_reviewed,
                    ),
                )
            connection.commit()

        stored = self.get_article_by_slug(article.slug)
        if stored is None:
            raise LookupError(f"Article {article.slug} was not stored.")
        return stored

    def _load_recent_dedup_candidates(
        self,
        cursor: psycopg.Cursor[tuple[object, ...]],
        *,
        window_hours: int,
    ) -> dict[str, list[tuple[str, str, str]]]:
        cursor.execute(
            """
            SELECT id, normalized_category, title, summary
            FROM raw_items
            WHERE published_at >= %s
              AND is_duplicate = FALSE
            ORDER BY published_at DESC
            """,
            (datetime.now(timezone.utc) - timedelta(hours=window_hours),),
        )
        rows = cursor.fetchall()

        grouped: dict[str, list[tuple[str, str, str]]] = {}
        for row in rows:
            item_id = str(row[0])
            category = str(row[1])
            title = str(row[2])
            summary = str(row[3])
            grouped.setdefault(category, []).append(
                (item_id, title, self._normalize_similarity_text(f"{title} {summary}"))
            )
        return grouped

    def _find_near_duplicate_match(
        self,
        item: RawItem,
        recent_similarity_candidates: dict[str, list[tuple[str, str, str]]],
        pending_similarity_candidates: dict[str, list[tuple[str, str, str]]],
    ) -> tuple[str, str, float] | None:
        category = item.normalized_category
        target = self._build_similarity_text(item)
        target_tokens = self._tokenize_similarity_text(target)
        if len(target_tokens) < 4:
            return None

        same_category_match = self._best_duplicate_candidate(
            item_id=item.id,
            target_tokens=target_tokens,
            candidates=recent_similarity_candidates.get(category, []) + pending_similarity_candidates.get(category, []),
        )
        if same_category_match is not None and same_category_match[2] >= 0.84:
            return same_category_match

        cross_category_candidates: list[tuple[str, str, str]] = []
        for candidate_category, candidate_items in recent_similarity_candidates.items():
            if candidate_category == category:
                continue
            cross_category_candidates.extend(candidate_items)
        for candidate_category, candidate_items in pending_similarity_candidates.items():
            if candidate_category == category:
                continue
            cross_category_candidates.extend(candidate_items)

        cross_category_match = self._best_duplicate_candidate(
            item_id=item.id,
            target_tokens=target_tokens,
            candidates=cross_category_candidates,
        )
        if cross_category_match is not None and cross_category_match[2] >= 0.9:
            return cross_category_match
        return None

    def _best_duplicate_candidate(
        self,
        *,
        item_id: str,
        target_tokens: set[str],
        candidates: list[tuple[str, str, str]],
    ) -> tuple[str, str, float] | None:
        best_match_id: str | None = None
        best_match_title = ""
        best_score = 0.0

        for candidate_id, candidate_title, candidate_text in candidates:
            if candidate_id == item_id:
                continue
            similarity = self._compute_similarity_from_texts(target_tokens, candidate_text)
            if similarity > best_score:
                best_score = similarity
                best_match_id = candidate_id
                best_match_title = candidate_title

        if best_match_id is None:
            return None
        return (best_match_id, best_match_title, best_score)

    def _build_similarity_text(self, item: RawItem) -> str:
        source_text = item.full_text or item.summary
        return self._normalize_similarity_text(f"{item.title} {source_text}")

    @staticmethod
    def _normalize_similarity_text(value: str) -> str:
        lowered = " ".join(value.lower().split())
        folded = NewsRepository._fold_similarity_text(lowered)
        return " ".join(folded.split())

    @staticmethod
    def _fold_similarity_text(value: str) -> str:
        replacements = {
            "а": "a",
            "б": "b",
            "в": "v",
            "г": "g",
            "д": "d",
            "е": "e",
            "ё": "e",
            "ж": "zh",
            "з": "z",
            "и": "i",
            "й": "i",
            "к": "k",
            "л": "l",
            "м": "m",
            "н": "n",
            "о": "o",
            "п": "p",
            "р": "r",
            "с": "s",
            "т": "t",
            "у": "u",
            "ф": "f",
            "х": "kh",
            "ц": "ts",
            "ч": "ch",
            "ш": "sh",
            "щ": "shch",
            "ъ": "",
            "ы": "y",
            "ь": "",
            "э": "e",
            "ю": "yu",
            "я": "ya",
        }
        folded = "".join(replacements.get(char, char) for char in value)
        return re.sub(r"[^a-z0-9]+", " ", folded)

    @staticmethod
    def _tokenize_similarity_text(value: str) -> set[str]:
        normalized = NewsRepository._normalize_similarity_text(value)
        return {token for token in re.findall(r"[a-z0-9]+", normalized) if len(token) > 2}

    def _compute_similarity_from_texts(self, left_tokens: set[str], right_text: str) -> float:
        right_tokens = self._tokenize_similarity_text(right_text)
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        if union == 0:
            return 0.0
        return intersection / union

    @staticmethod
    def _normalize_source_type(value: str) -> str:
        normalized = value.strip().lower()
        if normalized == "ai_search":
            return "ai_research"
        if normalized in {"news-sitemap", "newssitemap"}:
            return "news_sitemap"
        if normalized == "site_map":
            return "sitemap"
        return normalized

    @classmethod
    def _normalize_source_config(cls, source: SourceItem) -> SourceItem:
        normalized_type = cls._normalize_source_type(source.source_type)
        normalized_url = source.url.strip()
        if normalized_type == "ai_research":
            normalized_url = cls._normalize_ai_research_url(normalized_url)
        return SourceItem(
            key=source.key.strip(),
            title=source.title.strip(),
            url=normalized_url,
            category=source.category.strip(),
            source_type=normalized_type,
            status=source.status.strip().lower(),
            notes=source.notes.strip(),
        )

    @staticmethod
    def _normalize_ai_research_url(url: str) -> str:
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            return url

        path = parts.path or "/"
        article_like = (
            path.endswith(".html")
            or path.endswith(".htm")
            or path.rstrip("/").split("/")[-1].isdigit()
        )

        if article_like:
            if "/" in path.rstrip("/"):
                path = path.rsplit("/", 1)[0] + "/"
            else:
                path = "/"

        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))

    @staticmethod
    def _validate_source_config(source: SourceItem) -> None:
        key = source.key.strip()
        url = source.url.strip()

        if not key:
            raise ValueError("Source key is required.")
        if not url.startswith(("http://", "https://")):
            raise ValueError("Source URL must start with http:// or https://")
        if source.source_type not in {"rss", "news_sitemap", "sitemap", "scraping", "ai_research"}:
            raise ValueError("Unsupported source type.")
        if source.status not in {"draft", "active", "archived"}:
            raise ValueError("Unsupported source status.")
        if source.status == "active" and source.source_type not in SUPPORTED_ACTIVE_SOURCE_TYPES:
            supported = ", ".join(sorted(SUPPORTED_ACTIVE_SOURCE_TYPES))
            raise ValueError(
                f"Only supported source adapters can be active right now: {supported}."
            )

    def _validate_source_activation_readiness(self, source: SourceItem) -> None:
        if source.status != "active" or source.source_type not in {"scraping", "news_sitemap"}:
            return

        state = self.get_source_sync_state_map().get(source.key)
        if state is None or state.last_probe_at is None:
            raise ValueError("Перед активацией источника сначала запустите Проверить.")
        if state.last_probe_readiness in {"unknown", "empty", "fetch_error"}:
            source_label = {
                "news_sitemap": "News sitemap",
            }.get(source.source_type, "Scraping")
            raise ValueError(
                f"{source_label}-источник можно переводить в active только после успешного preflight, "
                "когда источник действительно возвращает новости."
            )

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
        )

    @staticmethod
    def _map_article_row(row: tuple[object, ...]) -> Article:
        return Article(
            id=str(row[0]),
            slug=str(row[1]),
            news_item_id=str(row[2]),
            raw_item_id=str(row[3]),
            title=str(row[4]),
            lead=row[5],
            dek=str(row[6]),
            body=str(row[7]),
            category=str(row[8]),
            source_title=str(row[9]),
            source_url=row[10],
            tags=list(row[11] or []),
            published_at=row[12],
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

    @staticmethod
    def _default_news_item(
        item_id: str,
        title: str,
        description: str,
        category: str,
        source: str,
        link: str,
    ) -> NewsItem:
        return NewsItem(
            id=item_id,
            title=title,
            description=description,
            category=category,
            published_at=datetime.now(timezone.utc),
            source=source,
            link=link,
        )


def _build_article_slug(title: str, external_id: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in title)
    slug = "-".join(part for part in normalized.split("-") if part).strip("-")
    if not slug:
        slug = "article"

    suffix_source = external_id
    parsed = urlsplit(external_id)
    if parsed.path:
        suffix_source = parsed.path.rstrip("/").split("/")[-1] or external_id

    suffix = "".join(char.lower() for char in suffix_source if char.isalnum())[-10:] or "item"
    return f"{slug[:70].rstrip('-')}-{suffix}"


def _build_public_published_at(raw_item: RawItem) -> datetime:
    return _build_public_published_at_from_values(
        source_key=raw_item.source_key,
        external_id=raw_item.external_id,
        title=raw_item.title,
        fetched_at=raw_item.fetched_at,
    )


def _build_public_published_at_from_values(
    *,
    source_key: str,
    external_id: str,
    title: str,
    fetched_at: datetime,
) -> datetime:
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    else:
        fetched_at = fetched_at.astimezone(timezone.utc)

    seed = f"{source_key}:{external_id}:{title}".encode("utf-8", errors="ignore")
    hash_value = zlib.crc32(seed)
    offset_seconds = 120 + (hash_value % (54 * 60))
    return fetched_at - timedelta(hours=1) + timedelta(seconds=offset_seconds)
