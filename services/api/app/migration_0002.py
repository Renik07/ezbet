"""Immutable migration; append a new version for subsequent changes."""

STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS worker_jobs (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'pipeline',
        force BOOLEAN NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
        attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 2,
        worker_id TEXT, lease_until TIMESTAMPTZ, error TEXT, result JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_worker_jobs_active ON worker_jobs (kind) WHERE status IN ('pending', 'running')
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_worker_jobs_created ON worker_jobs (created_at DESC)
    """,
)
