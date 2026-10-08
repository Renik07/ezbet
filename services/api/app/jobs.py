"""Durable, bounded pipeline queue. Completed jobs are retained for diagnostics."""
from uuid import uuid4


class JobQueue:
    def __init__(self, repository):
        self.repository = repository

    def ensure_schema(self):
        with self.repository.connect() as connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS worker_jobs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL DEFAULT 'pipeline',
                    force BOOLEAN NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
                    attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 2,
                    worker_id TEXT, lease_until TIMESTAMPTZ, error TEXT, result JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            ''')
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_worker_jobs_active ON worker_jobs (kind) WHERE status IN ('pending', 'running')")
            connection.execute('CREATE INDEX IF NOT EXISTS idx_worker_jobs_created ON worker_jobs (created_at DESC)')

    def enqueue(self, *, force):
        with self.repository.connect() as connection:
            for _ in range(3):
                row = connection.execute('''
                    INSERT INTO worker_jobs (id, force) VALUES (%s, %s)
                    ON CONFLICT (kind) WHERE status IN ('pending', 'running') DO NOTHING
                    RETURNING id, status, created_at
                ''', (str(uuid4()), force)).fetchone()
                if row:
                    return True, {'id': row[0], 'status': row[1], 'createdAt': row[2].isoformat()}
                row = connection.execute("SELECT id, status, created_at FROM worker_jobs WHERE kind = 'pipeline' AND status IN ('pending', 'running')").fetchone()
                if row:
                    return False, {'id': row[0], 'status': row[1], 'createdAt': row[2].isoformat()}
        raise RuntimeError('Queue changed repeatedly; try again.')

    def recover_stale(self):
        # Called only while holding the process-wide worker advisory lock.
        with self.repository.connect() as connection:
            connection.execute('''
                UPDATE worker_jobs SET
                    status = CASE WHEN attempts < max_attempts THEN 'pending' ELSE 'failed' END,
                    worker_id = NULL, lease_until = NULL,
                    error = 'Worker interrupted; recovered expired lease.', updated_at = NOW()
                WHERE status = 'running' AND lease_until < NOW()
            ''')

    def claim(self, worker_id, lease_seconds=300):
        with self.repository.connect() as connection:
            row = connection.execute('''
                UPDATE worker_jobs SET status = 'running', attempts = attempts + 1,
                    worker_id = %s, lease_until = NOW() + %s * INTERVAL '1 second', updated_at = NOW()
                WHERE id = (SELECT id FROM worker_jobs WHERE status = 'pending' AND attempts < max_attempts
                    ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
                RETURNING id, force, attempts
            ''', (worker_id, lease_seconds)).fetchone()
        return {'id': row[0], 'force': row[1], 'attempts': row[2]} if row else None

    def heartbeat(self, job_id, worker_id, lease_seconds=300):
        with self.repository.connect() as connection:
            return bool(connection.execute('''
                UPDATE worker_jobs SET lease_until = NOW() + %s * INTERVAL '1 second', updated_at = NOW()
                WHERE id = %s AND worker_id = %s AND status = 'running' RETURNING id
            ''', (lease_seconds, job_id, worker_id)).fetchone())

    def finish(self, job_id, worker_id, *, result=None, error=None):
        from psycopg.types.json import Jsonb
        with self.repository.connect() as connection:
            return bool(connection.execute('''
                UPDATE worker_jobs SET status = %s, result = %s, error = %s,
                    lease_until = NULL, updated_at = NOW()
                WHERE id = %s AND worker_id = %s AND status = 'running' RETURNING id
            ''', ('failed' if error else 'succeeded', Jsonb(result) if result is not None else None,
                  error[:2000] if error else None, job_id, worker_id)).fetchone())

    def list_jobs(self, limit=20):
        with self.repository.connect() as connection:
            rows = connection.execute('''SELECT id, status, force, attempts, max_attempts,
                worker_id, lease_until, error, result, created_at, updated_at
                FROM worker_jobs ORDER BY created_at DESC LIMIT %s''', (limit,)).fetchall()
        keys = ('id', 'status', 'force', 'attempts', 'maxAttempts', 'workerId', 'leaseUntil', 'error', 'result', 'createdAt', 'updatedAt')
        return [{key: value.isoformat() if hasattr(value, 'isoformat') else value
                 for key, value in zip(keys, row)} for row in rows]
