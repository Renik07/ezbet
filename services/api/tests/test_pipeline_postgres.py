"""Integration tests use only an explicitly supplied TEST_DATABASE_URL and a private schema."""
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from services.api.app import pipeline, runtime, service_monitoring, service_publication
from services.api.app.models import DraftArticle, RawItem
from services.api.app.repository import NewsRepository


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'TEST_DATABASE_URL is not configured')
class PipelinePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = 'pipeline_test_' + uuid.uuid4().hex
        cls.url = os.environ['TEST_DATABASE_URL']
        with psycopg.connect(cls.url) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(cls.schema)))
        cls.repo = NewsRepository()
        cls.repo.database_url = make_conninfo(cls.url, options='-c search_path=' + cls.schema)
        cls.repo.ensure_schema()

    @classmethod
    def tearDownClass(cls):
        cls.repo.close_pool()
        with psycopg.connect(cls.url) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))

    def setUp(self):
        with self.repo.connect() as conn:
            conn.execute('TRUNCATE raw_items, draft_articles, articles, news_items, content_plan_items CASCADE')
            if conn.execute("SELECT to_regclass('worker_jobs')").fetchone()[0]:
                conn.execute('TRUNCATE worker_jobs')

    def raw(self, key, **updates):
        now = datetime.now(timezone.utc)
        return RawItem(**{
            'id': key, 'source_key': 'test', 'source_title': 'Test', 'source_url': 'https://example.com',
            'category': 'football', 'normalized_category': 'football', 'external_id': key,
            'dedupe_key': 'https://example.com/' + key,
            'title': 'Спартак победил Зенит в матче чемпионата России',
            'summary': 'Встреча завершилась со счетом 1:0.',
            'published_at': now, 'fetched_at': now, 'importance_score': 80, 'triage_label': 'high',
            'url': 'https://example.com/' + key, 'payload': '{}', **updates,
        })

    def draft(self, raw):
        return DraftArticle(id='draft:' + raw.id, raw_item_id=raw.id, title=raw.title,
            dek=raw.summary, body=raw.full_text or raw.summary, category=raw.normalized_category,
            source_title=raw.source_title, published_at=raw.published_at,
            status='ready_for_publish', review_status='reviewed', publish_decision='publish_auto',
            prompt_config_id='test', prompt_name='test', model='test', generation_mode='ai')

    def test_ingest_full_text_and_changed_score(self):
        original = self.raw('a', full_text='Встреча завершилась со счетом 1:0. Команды сыграли в Москве, победитель вышел в следующий раунд турнира.')
        self.repo.insert_raw_items([original])
        copy = self.raw('b', full_text=original.full_text)
        changed = self.raw('c', full_text=original.full_text.replace('1:0', '0:1'))
        self.repo.insert_raw_items([copy, changed])
        self.assertTrue(self.repo.get_raw_item('b').is_duplicate)
        self.assertFalse(self.repo.get_raw_item('c').is_duplicate)

    def test_previous_batch_remains_publishable(self):
        raw = self.raw('old', fetched_at=datetime.now(timezone.utc) - timedelta(hours=2))
        self.repo.insert_raw_items([raw])
        self.repo.upsert_draft(self.draft(raw))
        self.assertEqual(len(self.repo.list_publishable_drafts(since=None)), 1)
        self.assertEqual(self.repo.list_publishable_drafts(since=datetime.now(timezone.utc)), [])
        self.assertEqual(self.repo.count_ready_to_publish_with_existing_article(), 0)

    def test_same_batch_duplicate_is_held_across_categories(self):
        first = self.raw('first')
        second = self.raw('second', normalized_category='betting')
        self.repo.insert_raw_items([first, second])
        # Simulate a duplicate that escaped earlier ingestion checks.
        with self.repo.connect() as conn:
            conn.execute('UPDATE raw_items SET is_duplicate = FALSE')
        for raw in (first, second):
            self.repo.upsert_draft(self.draft(raw))
        with patch.object(runtime, 'repository', self.repo):
            self.assertEqual(service_publication._run_publish_for_drafts(limit=2), 1)
        with self.repo.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM draft_articles WHERE status = 'hold'").fetchone()[0], 1)

    def test_failure_rolls_back_article_and_draft_status(self):
        raw = self.raw('rollback')
        self.repo.insert_raw_items([raw])
        draft = self.repo.upsert_draft(self.draft(raw))
        # Fail the news insert after the article has been written.
        with self.repo.connect() as conn:
            conn.execute("ALTER TABLE news_items ADD CONSTRAINT test_reject_news CHECK (title = 'impossible')")
        try:
            with self.assertRaises(psycopg.errors.CheckViolation):
                self.repo.publish_draft_to_news(draft, raw)
            with self.repo.connect() as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0], 0)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM news_items').fetchone()[0], 0)
                self.assertEqual(conn.execute('SELECT status FROM draft_articles WHERE id = %s', (draft.id,)).fetchone()[0], 'ready_for_publish')
        finally:
            with self.repo.connect() as conn:
                conn.execute('ALTER TABLE news_items DROP CONSTRAINT test_reject_news')

    def test_concurrent_publisher_cannot_enter(self):
        raw = self.raw('locked')
        self.repo.insert_raw_items([raw])
        self.repo.upsert_draft(self.draft(raw))
        with self.repo.connect() as lock_connection:
            lock_connection.execute('SELECT pg_advisory_xact_lock(%s)', (runtime.PUBLISH_EXECUTION_LOCK_KEY,))
            with patch.object(runtime, 'repository', self.repo):
                self.assertEqual(service_publication._run_publish_for_drafts(limit=2), 0)
            with self.repo.connect() as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0], 0)
        with patch.object(runtime, 'repository', self.repo):
            self.assertEqual(service_publication._run_publish_for_drafts(limit=2), 1)

    def test_previous_batch_remains_in_enrichment_and_plan_queues(self):
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        incomplete = self.raw('incomplete', fetched_at=old_time)
        complete = self.raw('complete', fetched_at=old_time,
            full_text='Спартак выиграл матч чемпионата России и вышел в следующий раунд турнира. ' * 5)
        self.repo.insert_raw_items([incomplete, complete])
        self.assertIn('incomplete', [r.id for r in self.repo.list_pending_enrichment_raw_items(limit=10, since=None)])
        self.assertIn('complete', [r.id for r in self.repo.list_raw_candidates_for_plan(limit=10, since=None, require_full_text=True)])

    def test_queue_survives_repository_restart_and_coalesces_submissions(self):
        from services.api.app.jobs import JobQueue
        queue = JobQueue(self.repo)
        queue.ensure_schema()
        created, first = queue.enqueue(force=True)
        self.assertTrue(created)
        other = NewsRepository()
        other.database_url = self.repo.database_url
        try:
            created, second = JobQueue(other).enqueue(force=True)
            self.assertFalse(created)
            self.assertEqual(first['id'], second['id'])
        finally:
            other.close_pool()

    def test_worker_recovers_stale_jobs_and_bounds_attempts(self):
        from services.api.app.jobs import JobQueue
        queue = JobQueue(self.repo)
        queue.ensure_schema()
        queue.enqueue(force=True)
        job = queue.claim('old-worker', lease_seconds=-1)
        queue.recover_stale()
        retry = queue.claim('new-worker', lease_seconds=-1)
        self.assertEqual(job['id'], retry['id'])
        self.assertEqual(retry['attempts'], 2)
        self.assertFalse(queue.finish(job['id'], 'old-worker'))
        queue.recover_stale()
        self.assertIsNone(queue.claim('third-worker'))
        self.assertEqual(queue.list_jobs()[0]['status'], 'failed')

    def test_worker_excludes_concurrent_consumers_and_saves_result(self):
        from services.api.app.jobs import JobQueue
        from services.api.app.worker import PipelineWorker, WORKER_LOCK_KEY
        from services.api.app.models import (PipelineSchedulerRunResponse, SchedulerRunResponse,
            EnrichmentSchedulerRunResponse, EditorialSchedulerRunResponse, PublishSchedulerRunResponse)
        queue = JobQueue(self.repo)
        queue.ensure_schema()
        queue.enqueue(force=True)
        now = datetime.now(timezone.utc)
        response = PipelineSchedulerRunResponse(mode='run', started_at=now, finished_at=now,
            ingest=SchedulerRunResponse(ran=True, reason='ok'),
            enrichment=EnrichmentSchedulerRunResponse(ran=True, reason='ok'),
            editorial=EditorialSchedulerRunResponse(ran=True, reason='ok'),
            publish=PublishSchedulerRunResponse(ran=True, reason='ok'))
        worker = PipelineWorker(self.repo)
        with self.repo.connect() as connection:
            connection.execute('SELECT pg_advisory_xact_lock(%s)', (WORKER_LOCK_KEY,))
            self.assertFalse(worker.run_once(lambda **kwargs: self.fail('Must not execute while locked')))
        def run(**kwargs):
            self.assertTrue(kwargs['force'])
            self.assertTrue(kwargs['should_continue']())
            self.assertFalse(PipelineWorker(self.repo).run_once(lambda **_: self.fail('Concurrent worker entered')))
            return response
        self.assertTrue(worker.run_once(run))
        job = queue.list_jobs()[0]
        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(job['result']['mode'], 'run')
        self.assertFalse(worker.run_once(run))

    def test_worker_failure_is_visible_without_automatic_paid_retry(self):
        from services.api.app.jobs import JobQueue
        from services.api.app.worker import PipelineWorker
        queue = JobQueue(self.repo)
        queue.ensure_schema()
        queue.enqueue(force=True)
        def fail(**kwargs):
            raise RuntimeError('fixture failure')
        with self.assertLogs('services.api.app.worker', level='ERROR'):
            self.assertTrue(PipelineWorker(self.repo).run_once(fail))
        job = queue.list_jobs()[0]
        self.assertEqual(job['status'], 'failed')
        self.assertIn('fixture failure', job['error'])
        self.assertFalse(PipelineWorker(self.repo).run_once(fail))

    def test_recovery_preserves_live_scheduler(self):
        self.repo.set_scheduler_status(status='running', error=None)
        with self.repo.connect() as connection:
            connection.execute('SELECT pg_advisory_xact_lock(%s)', (runtime.SCHEDULER_LOCK_KEY,))
            with patch.object(runtime, 'repository', self.repo):
                service_monitoring._recover_runtime_state(trigger='test')
            self.assertEqual(self.repo.get_scheduler_settings().last_status, 'running')
        with patch.object(runtime, 'repository', self.repo):
            service_monitoring._recover_runtime_state(trigger='test')
        self.assertEqual(self.repo.get_scheduler_settings().last_status, 'idle')

    def test_pool_releases_session_locks_after_failure(self):
        import time
        with self.assertRaises(RuntimeError):
            with self.repo.connect() as connection:
                connection.execute('SELECT pg_advisory_lock(%s)', (99123456,))
                raise RuntimeError('fixture rollback')
        deadline = time.monotonic() + 2
        while self.repo.pool_stats()['pool_available'] == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        with psycopg.connect(self.url) as connection:
            self.assertTrue(connection.execute('SELECT pg_try_advisory_xact_lock(%s)', (99123456,)).fetchone()[0])

    def test_pool_bounds_connections_under_parallel_load(self):
        from concurrent.futures import ThreadPoolExecutor
        other = NewsRepository()
        other.database_url = self.repo.database_url
        try:
            with patch.dict(os.environ, {'EZBET_DB_POOL_MAX': '8'}):
                def query(_):
                    with other.connect() as connection:
                        connection.execute('SELECT pg_sleep(0.01)')
                        return connection.execute('SELECT pg_backend_pid()').fetchone()[0]
                with ThreadPoolExecutor(max_workers=16) as executor:
                    backends = list(executor.map(query, range(32)))
                self.assertLessEqual(len(set(backends)), 8)
                self.assertLessEqual(other.pool_stats()['pool_size'], 8)
        finally:
            other.close_pool()

    def test_worker_heartbeat_renews_lease(self):
        import threading
        from services.api.app.jobs import JobQueue
        from services.api.app.worker import PipelineWorker
        from services.api.app.models import (PipelineSchedulerRunResponse, SchedulerRunResponse,
            EnrichmentSchedulerRunResponse, EditorialSchedulerRunResponse, PublishSchedulerRunResponse)
        queue = JobQueue(self.repo)
        queue.ensure_schema()
        queue.enqueue(force=False)
        worker = PipelineWorker(self.repo, heartbeat_seconds=0.01)
        renewed = threading.Event()
        original = worker.queue.heartbeat
        def heartbeat(*args, **kwargs):
            success = original(*args, **kwargs)
            renewed.set()
            return success
        def run(**kwargs):
            self.assertTrue(renewed.wait(2))
            self.assertTrue(kwargs['should_continue']())
            now = datetime.now(timezone.utc)
            return PipelineSchedulerRunResponse(mode='tick', started_at=now, finished_at=now,
                ingest=SchedulerRunResponse(ran=False, reason='disabled'),
                enrichment=EnrichmentSchedulerRunResponse(ran=False, reason='disabled'),
                editorial=EditorialSchedulerRunResponse(ran=False, reason='disabled'),
                publish=PublishSchedulerRunResponse(ran=False, reason='disabled'))
        with patch.object(worker.queue, 'heartbeat', side_effect=heartbeat):
            worker.run_once(run)
        self.assertEqual(queue.list_jobs()[0]['status'], 'succeeded')

    def test_worker_process_consumes_persisted_job_without_ai(self):
        import subprocess
        import sys
        import time
        from services.api.app.jobs import JobQueue
        queue = JobQueue(self.repo)
        queue.ensure_schema()
        self.repo.update_scheduler_settings(enabled=False, interval_minutes=60, batch_size=5, run_enrichment=False)
        self.repo.update_enrichment_scheduler_settings(enabled=False, interval_minutes=60, batch_size=5)
        self.repo.update_editorial_scheduler_settings(enabled=False, interval_minutes=60, batch_size=5)
        self.repo.update_publish_scheduler_settings(enabled=False, interval_minutes=60, batch_size=5)
        queue.enqueue(force=False)
        env = {**os.environ, 'DATABASE_URL': self.repo.database_url,
               'EZBET_ENV': 'development', 'EZBET_ADMIN_API_TOKEN': 'fixture-' + 'x' * 32,
               'OPENAI_API_KEY': '', 'PYTHONPYCACHEPREFIX': '/tmp/ezbet-pycache'}
        process = subprocess.Popen([sys.executable, '-m', 'services.api.app.worker'], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 20
            status = 'pending'
            while time.monotonic() < deadline and process.poll() is None:
                status = queue.list_jobs()[0]['status']
                if status in {'succeeded', 'failed'}:
                    break
                time.sleep(0.05)
            self.assertEqual(status, 'succeeded')
        finally:
            process.terminate()
            try:
                _, errors = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                _, errors = process.communicate()
            self.assertEqual(process.returncode, 0, errors)

    def test_lost_worker_ownership_stops_before_next_stage(self):
        with patch.object(runtime, 'repository', self.repo), patch.object(pipeline, '_run_scheduler') as ingest:
            with self.assertRaisesRegex(RuntimeError, 'lost ownership'):
                pipeline._run_pipeline_scheduler(force=True, should_continue=lambda: False)
            ingest.assert_not_called()

    def test_pool_replaces_dead_connection(self):
        import time
        other = NewsRepository()
        other.database_url = self.repo.database_url
        try:
            with other.connect() as connection:
                backend = connection.execute('SELECT pg_backend_pid()').fetchone()[0]
            deadline = time.monotonic() + 2
            while other.pool_stats()['pool_available'] == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            with psycopg.connect(self.url) as control:
                control.execute('SELECT pg_terminate_backend(%s)', (backend,))
            with other.connect() as connection:
                self.assertNotEqual(connection.execute('SELECT pg_backend_pid()').fetchone()[0], backend)
        finally:
            other.close_pool()
