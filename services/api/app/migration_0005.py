"""Rolling news allowance; display time remains separate from publication time."""
STATEMENTS = (
    '''CREATE TABLE IF NOT EXISTS news_ai_budget (
        raw_item_id TEXT PRIMARY KEY, claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        stages TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
    )''',
    'CREATE INDEX IF NOT EXISTS news_ai_budget_claimed_idx ON news_ai_budget (claimed_at)',
    '''INSERT INTO news_ai_budget (raw_item_id,claimed_at,stages)
        SELECT raw_item_id,created_at,ARRAY['editorial']::TEXT[] FROM draft_articles
        WHERE created_at > NOW() - INTERVAL '1 hour' AND raw_item_id NOT LIKE 'guide-topic:%'
        ON CONFLICT (raw_item_id) DO NOTHING''',
    '''UPDATE scheduler_settings SET enrichment_batch_size=LEAST(enrichment_batch_size,8),
        editorial_batch_size=LEAST(editorial_batch_size,8), publish_batch_size=LEAST(publish_batch_size,8)''',
)
