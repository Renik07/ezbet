"""Migration behavior against private PostgreSQL schemas, never production tables."""
import os
import subprocess
import sys
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from services.api.app import bootstrap, runtime
from services.api.app import migrations
from services.api.app.migration_0001 import STATEMENTS as LEGACY_SCHEMA
from services.api.app.migration_0002 import STATEMENTS as LEGACY_QUEUE


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'TEST_DATABASE_URL is not configured')
class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.schema = 'migration_test_' + uuid.uuid4().hex
        self.url = os.environ['TEST_DATABASE_URL']
        with psycopg.connect(self.url) as connection:
            connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.private_url = make_conninfo(self.url, options='-c search_path=' + self.schema)

    def tearDown(self):
        with psycopg.connect(self.url) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    def test_fresh_database_repeat_and_read_only_check(self):
        with psycopg.connect(self.private_url) as connection:
            with self.assertRaisesRegex(RuntimeError, 'not migrated'):
                migrations.check_schema(connection)
            self.assertEqual(migrations.migrate(connection), [1, 2, 3])
            timestamps = connection.execute('SELECT applied_at FROM schema_migrations ORDER BY version').fetchall()
            self.assertEqual(migrations.migrate(connection), [])
            self.assertEqual(migrations.check_schema(connection), [1, 2, 3])
            self.assertEqual(timestamps, connection.execute('SELECT applied_at FROM schema_migrations ORDER BY version').fetchall())
            connection.commit()
            connection.execute('SET TRANSACTION READ ONLY')
            self.assertEqual(migrations.check_schema(connection), [1, 2, 3])

    def test_legacy_database_preserves_content_and_scheduler_settings(self):
        with psycopg.connect(self.private_url) as connection:
            for statement in (*LEGACY_SCHEMA, *LEGACY_QUEUE):
                connection.execute(statement)
            connection.execute("INSERT INTO news_items (id,title,description,category,published_at,source) VALUES ('existing','Title','Body','football',NOW(),'Source')")
            connection.execute("UPDATE scheduler_settings SET enabled=TRUE, batch_size=17 WHERE id='default'")
            connection.execute("INSERT INTO worker_jobs (id,force) VALUES ('existing-job', TRUE)")
            connection.commit()
            self.assertEqual(migrations.migrate(connection), [1, 2, 3])
            self.assertEqual(connection.execute("SELECT title,description FROM news_items WHERE id='existing'").fetchone(), ('Title','Body'))
            self.assertEqual(connection.execute("SELECT enabled,batch_size FROM scheduler_settings WHERE id='default'").fetchone(), (True,17))
            self.assertEqual(connection.execute("SELECT status FROM worker_jobs WHERE id='existing-job'").fetchone(), ('pending',))

    def test_failed_batch_rolls_back_schema_and_history(self):
        broken = (*migrations.MIGRATIONS, (4, 'broken', ('CREATE TABLE should_rollback (id INT)', 'SELECT missing_column')))
        with psycopg.connect(self.private_url) as connection:
            with patch.object(migrations, 'MIGRATIONS', broken):
                with self.assertRaises(psycopg.errors.UndefinedColumn):
                    migrations.migrate(connection)
            self.assertIsNone(connection.execute("SELECT to_regclass('should_rollback')").fetchone()[0])
            self.assertIsNone(connection.execute("SELECT to_regclass('schema_migrations')").fetchone()[0])
            self.assertIsNone(connection.execute("SELECT to_regclass('news_items')").fetchone()[0])
            self.assertEqual(migrations.migrate(connection), [1, 2, 3])

    def test_concurrent_migrations_apply_each_version_once(self):
        def upgrade(_):
            with psycopg.connect(self.private_url) as connection:
                return migrations.migrate(connection)
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(upgrade, range(4)))
        self.assertEqual(sorted(results, key=len), [[], [], [], [1, 2, 3]])

    def test_changed_or_future_history_is_rejected(self):
        with psycopg.connect(self.private_url) as connection:
            migrations.migrate(connection)
            connection.execute("UPDATE schema_migrations SET checksum='tampered' WHERE version=1")
            with self.assertRaisesRegex(RuntimeError, 'differs'):
                migrations.check_schema(connection)
            with self.assertRaisesRegex(RuntimeError, 'differs'):
                migrations.migrate(connection)
            connection.execute('DELETE FROM schema_migrations')
            connection.execute("INSERT INTO schema_migrations VALUES (99,'future','unknown',NOW())")
            with self.assertRaisesRegex(RuntimeError, 'differs'):
                migrations.check_schema(connection)

    def test_pending_and_gapped_history_are_rejected(self):
        with psycopg.connect(self.private_url) as connection:
            migrations.migrate(connection)
            connection.execute('DELETE FROM schema_migrations WHERE version=3')
            with self.assertRaisesRegex(RuntimeError, 'pending'):
                migrations.check_schema(connection)
            self.assertEqual(migrations.migrate(connection), [3])
            connection.execute('DELETE FROM schema_migrations WHERE version=1')
            with self.assertRaisesRegex(RuntimeError, 'contiguous'):
                migrations.migrate(connection)

    def test_cli_upgrade_and_check(self):
        environment = {**os.environ, 'DATABASE_URL': self.private_url}
        command = [sys.executable, '-m', 'services.api.app.migrations']
        initial = subprocess.run([*command, 'check'], env=environment, capture_output=True, text=True)
        self.assertNotEqual(initial.returncode, 0)
        for action in ('upgrade', 'check', 'upgrade'):
            result = subprocess.run([*command, action], env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('versions []', result.stdout)

    def test_older_schema_gets_missing_columns_without_resetting_data(self):
        with psycopg.connect(self.private_url) as connection:
            for statement in LEGACY_SCHEMA:
                connection.execute(statement)
            connection.execute('ALTER TABLE articles DROP COLUMN lead')
            connection.execute('ALTER TABLE source_configs DROP COLUMN notes')
            connection.execute("INSERT INTO source_configs (key,title,url,category) VALUES ('old-source','Old source','https://example.com','football')")
            connection.commit()
            self.assertEqual(migrations.migrate(connection), [1, 2, 3])
            self.assertEqual(connection.execute("SELECT title,notes FROM source_configs WHERE key='old-source'").fetchone(), ('Old source',''))
            self.assertEqual(connection.execute('SELECT lead FROM articles LIMIT 1').fetchall(), [])

    def test_failed_new_version_preserves_applied_versions_and_data(self):
        with psycopg.connect(self.private_url) as connection:
            migrations.migrate(connection)
            connection.execute("INSERT INTO worker_jobs (id,force) VALUES ('keep-job',FALSE)")
            connection.commit()
            broken = (*migrations.MIGRATIONS, (4, 'broken', ('DELETE FROM worker_jobs', 'SELECT missing_column')))
            with patch.object(migrations, 'MIGRATIONS', broken):
                with self.assertRaises(psycopg.errors.UndefinedColumn):
                    migrations.migrate(connection)
            self.assertEqual(migrations.check_schema(connection), [1, 2, 3])
            self.assertEqual(connection.execute("SELECT id FROM worker_jobs").fetchall(), [('keep-job',)])

    def test_application_startup_requires_migrations_without_creating_tables(self):
        from services.api.app.repository import NewsRepository
        repository = NewsRepository()
        repository.database_url = self.private_url
        try:
            with patch.object(runtime, 'repository', repository), patch.object(bootstrap, 'validate_admin_configuration'):
                with self.assertRaisesRegex(RuntimeError, 'not migrated'):
                    bootstrap._initialize_runtime()
            with psycopg.connect(self.private_url) as connection:
                self.assertIsNone(connection.execute("SELECT to_regclass('news_items')").fetchone()[0])
                self.assertIsNone(connection.execute("SELECT to_regclass('schema_migrations')").fetchone()[0])
        finally:
            repository.close_pool()

    def test_publication_date_migration_restores_history_without_changing_content_or_modified_date(self):
        from datetime import datetime, timedelta, timezone
        with psycopg.connect(self.private_url) as connection:
            with patch.object(migrations, 'MIGRATIONS', migrations.MIGRATIONS[:2]):
                migrations.migrate(connection)
            created = datetime.now(timezone.utc) - timedelta(days=3)
            modified = created + timedelta(days=1)
            fake = created - timedelta(hours=1)
            for key, raw_id in [('news', 'raw:news'), ('guide', 'guide-topic:1')]:
                connection.execute("INSERT INTO news_items (id,title,description,category,published_at,source) VALUES (%s,'Title','Body','football',%s,'Source')", (key, fake))
                connection.execute("""INSERT INTO articles (id,slug,news_item_id,raw_item_id,title,dek,body,category,source_title,published_at,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,'Title','Lead','Body','football','Source',%s,%s,%s)""", (key,key,key,raw_id,fake,created,modified))
            connection.commit()
            self.assertEqual(migrations.migrate(connection), [3])
            self.assertEqual(connection.execute("SELECT published_at,updated_at,body FROM articles WHERE id='news'").fetchone(), (created,modified,'Body'))
            self.assertEqual(connection.execute("SELECT published_at FROM news_items WHERE id='news'").fetchone()[0], created)
            self.assertEqual(connection.execute("SELECT published_at FROM articles WHERE id='guide'").fetchone()[0], fake)
            self.assertEqual(migrations.migrate(connection), [])
