"""Integration tests use only an explicitly supplied TEST_DATABASE_URL and a private schema."""
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from services.api.app import main
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
        with psycopg.connect(cls.url) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))

    def setUp(self):
        with self.repo.connect() as conn:
            conn.execute('TRUNCATE raw_items, draft_articles, articles, news_items, content_plan_items CASCADE')

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
        with patch.object(main, 'repository', self.repo):
            self.assertEqual(main._run_publish_for_drafts(limit=2), 1)
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
            lock_connection.execute('SELECT pg_advisory_xact_lock(%s)', (main.PUBLISH_EXECUTION_LOCK_KEY,))
            with patch.object(main, 'repository', self.repo):
                self.assertEqual(main._run_publish_for_drafts(limit=2), 0)
            with self.repo.connect() as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0], 0)
        with patch.object(main, 'repository', self.repo):
            self.assertEqual(main._run_publish_for_drafts(limit=2), 1)

    def test_previous_batch_remains_in_enrichment_and_plan_queues(self):
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        incomplete = self.raw('incomplete', fetched_at=old_time)
        complete = self.raw('complete', fetched_at=old_time,
            full_text='Спартак выиграл матч чемпионата России и вышел в следующий раунд турнира. ' * 5)
        self.repo.insert_raw_items([incomplete, complete])
        self.assertIn('incomplete', [r.id for r in self.repo.list_pending_enrichment_raw_items(limit=10, since=None)])
        self.assertIn('complete', [r.id for r in self.repo.list_raw_candidates_for_plan(limit=10, since=None, require_full_text=True)])
