import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from services.api.app import migrations
from services.api.app.news_budget import claim_news_stage
from services.api.app.display_time import news_display_time
from services.api.app.news_candidates import news_rejection_reason


class NewsPresentationTests(unittest.TestCase):
    def test_display_time_is_stable_and_within_previous_hour(self):
        real = datetime(2026, 10, 8, 11, 8, tzinfo=timezone.utc)
        times = [news_display_time('article-'+str(i), real) for i in range(14)]
        self.assertGreater(len(set(times)), 1)
        self.assertTrue(all(real-timedelta(hours=1) < t < real for t in times))
        self.assertEqual(times[0], news_display_time('article-0', real))
        self.assertEqual(real.hour, 11)

    def test_non_news_pages_and_old_queue_items_are_rejected(self):
        now = datetime.now(timezone.utc)
        for url in ['https://www.sports.ru/tags/4084863', 'https://www.sports.ru/tennis/match/1992317']:
            self.assertEqual(news_rejection_reason(SimpleNamespace(url=url, published_at=now)), 'non_news_page')
        good = SimpleNamespace(url='https://www.sports.ru/football/news/123.html', published_at=now)
        self.assertIsNone(news_rejection_reason(good))
        good.published_at = now-timedelta(days=2)
        self.assertEqual(news_rejection_reason(good), 'expired_news')


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'TEST_DATABASE_URL is not configured')
class NewsBudgetTests(unittest.TestCase):
    def test_shared_concurrent_budget_survives_restart_and_expires(self):
        url = os.environ['TEST_DATABASE_URL']; schema = 'budget_test_'+uuid.uuid4().hex
        with psycopg.connect(url) as c:
            c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        private = make_conninfo(url, options='-c search_path='+schema)
        repo = SimpleNamespace(connect=lambda: psycopg.connect(private))
        try:
            with repo.connect() as c: migrations.migrate(c)
            with ThreadPoolExecutor(max_workers=16) as pool:
                claims=list(pool.map(lambda i:claim_news_stage(repo, str(i), 'planner'), range(32)))
            self.assertEqual(sum(claims), 8)
            ids=[str(i) for i,claimed in enumerate(claims) if claimed]
            restarted=SimpleNamespace(connect=lambda:psycopg.connect(private))
            self.assertFalse(claim_news_stage(restarted, 'new-item', 'editorial'))
            self.assertTrue(claim_news_stage(restarted, ids[0], 'editorial'))
            self.assertFalse(claim_news_stage(restarted, ids[0], 'editorial'))
            self.assertTrue(claim_news_stage(restarted, ids[0], 'enrichment'))
            with repo.connect() as c:
                self.assertEqual(c.execute('SELECT count(*) FROM news_ai_budget').fetchone()[0],8)
                c.execute("UPDATE news_ai_budget SET claimed_at=NOW()-INTERVAL '61 minutes'")
            self.assertTrue(claim_news_stage(restarted, 'new-item', 'planner'))
            self.assertTrue(claim_news_stage(restarted, ids[0], 'planner'))
        finally:
            with psycopg.connect(url) as c:
                c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

class BudgetGuardTests(unittest.TestCase):
    def test_denied_editorial_budget_does_not_call_paid_operations(self):
        from unittest.mock import MagicMock, patch
        from services.api.app import editorial
        raw=SimpleNamespace(id='raw',url='https://example.com/news',published_at=datetime.now(timezone.utc))
        repo=MagicMock();repo.list_planned_raw_items_for_drafts.return_value=[raw]
        with patch.object(editorial,'claim_news_stage',return_value=False), patch.object(editorial,'enrich_raw_item_if_needed') as enrich, patch.object(editorial,'generate_draft') as generate:
            self.assertEqual(editorial.run_editorial_cycle(repo),([],[]))
            enrich.assert_not_called();generate.assert_not_called()

    def test_denied_planner_budget_leaves_candidate_queued(self):
        from unittest.mock import MagicMock, patch
        from services.api.app import planner
        raw=SimpleNamespace(id='raw',url='https://example.com/news',published_at=datetime.now(timezone.utc))
        repo=MagicMock();repo.list_raw_candidates_for_plan.return_value=[raw]
        with patch.object(planner,'claim_news_stage',return_value=False), patch.object(planner,'build_editorial_shortlist',return_value=[raw]), patch.object(planner,'OpenAIEditorialClient') as client:
            self.assertEqual(planner.run_content_planner(repo),[])
            client.return_value.rerank_plan_candidates.assert_not_called()
            repo.upsert_content_plan_item.assert_not_called()
