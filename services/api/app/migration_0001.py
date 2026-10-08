"""Immutable migration; append a new version for subsequent changes."""

STATEMENTS = (
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
    """,
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
    """,
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
    """,
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
    """,
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
    """,
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
    """,
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
    """,
    """
    CREATE TABLE IF NOT EXISTS guide_topics (
        id SERIAL PRIMARY KEY,
        topic_number INTEGER NOT NULL UNIQUE,
        title TEXT NOT NULL,
        section TEXT NOT NULL,
        category TEXT NOT NULL,
        requires_web_search BOOLEAN NOT NULL DEFAULT FALSE,
        search_context_size TEXT NOT NULL DEFAULT 'low',
        status TEXT NOT NULL DEFAULT 'planned',
        article_id TEXT,
        article_slug TEXT,
        last_error TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_guide_topics_status_number ON guide_topics (status, topic_number)
    """,
    """
    ALTER TABLE guide_topics ADD COLUMN IF NOT EXISTS requires_web_search BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE guide_topics ADD COLUMN IF NOT EXISTS search_context_size TEXT NOT NULL DEFAULT 'low'
    """,
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
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_raw_items_dedupe_key
    ON raw_items (dedupe_key)
    WHERE dedupe_key <> ''
    """,
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
    """,
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
    """,
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
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_usage_events (
        id BIGSERIAL PRIMARY KEY,
        operation TEXT NOT NULL,
        usage_group TEXT NOT NULL,
        model TEXT NOT NULL,
        input_tokens INTEGER NOT NULL DEFAULT 0,
        output_tokens INTEGER NOT NULL DEFAULT 0,
        cached_input_tokens INTEGER NOT NULL DEFAULT 0,
        total_tokens INTEGER NOT NULL DEFAULT 0,
        web_search_calls INTEGER NOT NULL DEFAULT 0,
        estimated_cost_usd NUMERIC(14, 8) NOT NULL DEFAULT 0,
        related_id TEXT,
        rate_source TEXT NOT NULL DEFAULT 'openai_pricing_2026_06_plus_web_search',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ai_usage_events_created_at ON ai_usage_events (created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ai_usage_events_group_created_at ON ai_usage_events (usage_group, created_at DESC)
    """,
    """
    ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS skipped_items TEXT NOT NULL DEFAULT '[]'
    """,
    """
    ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS source_breakdown TEXT NOT NULL DEFAULT '[]'
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS batch_size INTEGER NOT NULL DEFAULT 100
    """,
    """
    ALTER TABLE scheduler_settings ALTER COLUMN batch_size SET DEFAULT 100
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS run_enrichment BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS last_found_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS last_saved_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS last_published_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_enabled BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_interval_minutes INTEGER NOT NULL DEFAULT 60
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_batch_size INTEGER NOT NULL DEFAULT 20
    """,
    """
    ALTER TABLE scheduler_settings ALTER COLUMN enrichment_batch_size SET DEFAULT 20
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_last_run_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_next_run_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_last_status TEXT NOT NULL DEFAULT 'idle'
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_last_error TEXT
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_last_processed_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS enrichment_last_enriched_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_enabled BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_interval_minutes INTEGER NOT NULL DEFAULT 60
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_batch_size INTEGER NOT NULL DEFAULT 10
    """,
    """
    ALTER TABLE scheduler_settings ALTER COLUMN editorial_batch_size SET DEFAULT 10
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_last_run_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_next_run_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_last_status TEXT NOT NULL DEFAULT 'idle'
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_last_error TEXT
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_last_planned_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_last_generated_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS editorial_last_reviewed_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_enabled BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_interval_minutes INTEGER NOT NULL DEFAULT 60
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_batch_size INTEGER NOT NULL DEFAULT 10
    """,
    """
    ALTER TABLE scheduler_settings ALTER COLUMN publish_batch_size SET DEFAULT 10
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_last_run_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_next_run_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_last_status TEXT NOT NULL DEFAULT 'idle'
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_last_error TEXT
    """,
    """
    ALTER TABLE scheduler_settings ADD COLUMN IF NOT EXISTS publish_last_published_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS publish_decision TEXT NOT NULL DEFAULT 'publish_pending'
    """,
    """
    ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS publish_reason TEXT
    """,
    """
    ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS writer_title TEXT
    """,
    """
    ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS writer_dek TEXT
    """,
    """
    ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS writer_body TEXT
    """,
    """
    ALTER TABLE news_items ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'public'
    """,
    """
    ALTER TABLE news_items ADD COLUMN IF NOT EXISTS ai_reviewed BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE editor_reviews ADD COLUMN IF NOT EXISTS decision TEXT NOT NULL DEFAULT 'approve'
    """,
    """
    ALTER TABLE editor_reviews ADD COLUMN IF NOT EXISTS revised_title TEXT
    """,
    """
    ALTER TABLE editor_reviews ADD COLUMN IF NOT EXISTS revised_dek TEXT
    """,
    """
    ALTER TABLE editor_reviews ADD COLUMN IF NOT EXISTS revised_body TEXT
    """,
    """
    ALTER TABLE source_configs ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'rss'
    """,
    """
    ALTER TABLE source_configs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'
    """,
    """
    ALTER TABLE source_configs ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT ''
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_successful_fetch_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_successful_parse_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_item_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS fetch_status TEXT NOT NULL DEFAULT 'idle'
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS parse_status TEXT NOT NULL DEFAULT 'idle'
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS fetch_error_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS parse_error_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_readiness TEXT NOT NULL DEFAULT 'unknown'
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS preferred_adapter TEXT
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS preferred_adapter_url TEXT
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS supports_rss BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS supports_news_sitemap BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS supports_sitemap BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS supports_scraping BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_full_text_ok BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_full_text_method TEXT
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_lead_ok BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_authors_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_tags_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_sample_title TEXT
    """,
    """
    ALTER TABLE source_sync_state ADD COLUMN IF NOT EXISTS last_probe_sample_url TEXT
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS normalized_category TEXT NOT NULL DEFAULT 'general'
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS dedupe_key TEXT NOT NULL DEFAULT ''
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_raw_items_dedupe_key
    ON raw_items (dedupe_key)
    WHERE dedupe_key <> ''
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS importance_score INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS triage_label TEXT NOT NULL DEFAULT 'low'
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS duplicate_of TEXT
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS duplicate_stage TEXT
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS duplicate_reason TEXT
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS full_text TEXT
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS full_text_source_url TEXT
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS full_text_source_title TEXT
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS reference_urls TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS extraction_mode TEXT
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS enrichment_status TEXT
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS enrichment_error TEXT
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS lead TEXT
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS authors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
    """,
    """
    ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
    """,
    """
    ALTER TABLE articles ADD COLUMN IF NOT EXISTS lead TEXT
    """,
    """
    ALTER TABLE articles ADD COLUMN IF NOT EXISTS news_item_id TEXT
    """,
    """
    ALTER TABLE articles ADD COLUMN IF NOT EXISTS raw_item_id TEXT
    """,
    """
    UPDATE articles
    SET raw_item_id = COALESCE(NULLIF(raw_item_id, ''), NULLIF(news_item_id, ''), id)
    WHERE raw_item_id IS NULL OR raw_item_id = ''
    """,
    """
    ALTER TABLE articles ADD COLUMN IF NOT EXISTS authors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
    """,
    """
    ALTER TABLE articles ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
    """,
    """
    ALTER TABLE articles ADD COLUMN IF NOT EXISTS ai_reviewed BOOLEAN NOT NULL DEFAULT TRUE
    """,
    """
    CREATE TABLE IF NOT EXISTS match_forecasts (
        slug TEXT PRIMARY KEY,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        home_logo TEXT,
        away_logo TEXT,
        league TEXT NOT NULL,
        kickoff TIMESTAMPTZ NOT NULL,
        odds_home DOUBLE PRECISION NOT NULL,
        odds_draw DOUBLE PRECISION NOT NULL,
        odds_away DOUBLE PRECISION NOT NULL,
        selection_score INTEGER NOT NULL,
        source_order INTEGER NOT NULL,
        research_brief TEXT,
        source_urls TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
        lead TEXT,
        home_form TEXT,
        away_form TEXT,
        factors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
        pick TEXT,
        generation_status TEXT NOT NULL DEFAULT 'pending',
        is_current BOOLEAN NOT NULL DEFAULT TRUE,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    ALTER TABLE match_forecasts ADD COLUMN IF NOT EXISTS research_brief TEXT
    """,
    """
    ALTER TABLE match_forecasts ADD COLUMN IF NOT EXISTS source_urls TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
    """,
    """
    ALTER TABLE match_forecasts ADD COLUMN IF NOT EXISTS lead TEXT
    """,
    """
    ALTER TABLE match_forecasts ADD COLUMN IF NOT EXISTS home_form TEXT
    """,
    """
    ALTER TABLE match_forecasts ADD COLUMN IF NOT EXISTS away_form TEXT
    """,
    """
    ALTER TABLE match_forecasts ADD COLUMN IF NOT EXISTS factors TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
    """,
    """
    ALTER TABLE match_forecasts ADD COLUMN IF NOT EXISTS pick TEXT
    """,
    """
    ALTER TABLE match_forecasts ADD COLUMN IF NOT EXISTS generation_status TEXT NOT NULL DEFAULT 'pending'
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_match_forecasts_current_kickoff ON match_forecasts (is_current, kickoff)
    """,
    """
    CREATE TABLE IF NOT EXISTS article_slug_redirects (
        old_slug TEXT PRIMARY KEY,
        article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
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
    """,
)
