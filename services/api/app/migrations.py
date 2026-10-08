"""Transactional PostgreSQL migrations, applied explicitly before application startup."""
from __future__ import annotations

import argparse
import hashlib
import json

from .migration_0001 import STATEMENTS as BASELINE
from .migration_0002 import STATEMENTS as WORKER_QUEUE
from .migration_0003 import STATEMENTS as PUBLICATION_DATES
from .migration_0004 import STATEMENTS as SITEMAP_RANGES

from .migration_0005 import STATEMENTS as NEWS_BUDGET

MIGRATIONS = ((1, 'baseline', BASELINE), (2, 'worker_queue', WORKER_QUEUE),
              (3, 'publication_dates', PUBLICATION_DATES), (4, 'sitemap_ranges', SITEMAP_RANGES), (5, 'news_budget', NEWS_BUDGET))
MIGRATION_LOCK_KEY = 4815162351


def _checksum(statements):
    return hashlib.sha256(json.dumps(statements, ensure_ascii=False).encode()).hexdigest()


def _validate(rows):
    known = {version: (name, _checksum(statements)) for version, name, statements in MIGRATIONS}
    for version, name, checksum in rows:
        if version not in known or known[version] != (name, checksum):
            raise RuntimeError(f'Database migration {version} differs from this release; deployment stopped.')
    applied = [row[0] for row in rows]
    expected = [version for version, _, _ in MIGRATIONS][:len(applied)]
    if applied != expected:
        raise RuntimeError('Database migration history is not a contiguous prefix of this release.')
    return applied


def migrate(connection):
    """Apply pending versions and history together; any failure rolls back the batch."""
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(%s)', (MIGRATION_LOCK_KEY,))
        connection.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )''')
        rows = connection.execute('SELECT version, name, checksum FROM schema_migrations ORDER BY version').fetchall()
        applied = _validate(rows)
        pending = []
        for version, name, statements in MIGRATIONS:
            if version in applied:
                continue
            for statement in statements:
                connection.execute(statement)
            connection.execute('INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)',
                               (version, name, _checksum(statements)))
            pending.append(version)
        return pending


def check_schema(connection):
    """Read-only startup guard: application processes never alter the schema."""
    if connection.execute("SELECT to_regclass('schema_migrations')").fetchone()[0] is None:
        raise RuntimeError('Database is not migrated. Run python -m app.migrations upgrade before startup.')
    rows = connection.execute('SELECT version, name, checksum FROM schema_migrations ORDER BY version').fetchall()
    applied = _validate(rows)
    if len(applied) != len(MIGRATIONS):
        raise RuntimeError('Database has pending migrations. Run python -m app.migrations upgrade before startup.')
    return applied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('upgrade', 'check'))
    args = parser.parse_args()
    from .repository import NewsRepository
    repository = NewsRepository()
    try:
        with repository.connect() as connection:
            versions = migrate(connection) if args.command == 'upgrade' else check_schema(connection)
        print(f'{args.command}: versions {versions}')
    finally:
        repository.close_pool()


if __name__ == '__main__':
    main()
