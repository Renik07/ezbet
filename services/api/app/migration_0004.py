"""Stable sitemap ranges, independent of publication order or hidden articles."""
STATEMENTS = (
    'ALTER TABLE articles ADD COLUMN IF NOT EXISTS sitemap_id BIGINT GENERATED ALWAYS AS IDENTITY',
    'CREATE UNIQUE INDEX IF NOT EXISTS articles_sitemap_id_idx ON articles (sitemap_id)',
)
