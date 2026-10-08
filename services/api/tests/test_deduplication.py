import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.api.app.deduplication import facts_conflict
from services.api.app.ingestion import _normalize_url
from services.api.app.repository import NewsRepository
from services.api.app.editorial import evaluate_published_duplicate_guard
from services.api.app import pipeline_logging, runtime, service_editorial, service_enrichment, service_publication


class DeduplicationTests(unittest.TestCase):
    def test_content_parameters_survive_tracking_cleanup(self):
        self.assertEqual(_normalize_url('https://EXAMPLE.com/news/?id=123&utm_source=tg#top'), 'https://example.com/news?id=123')
        self.assertNotEqual(_normalize_url('https://example.com/news?id=123'), _normalize_url('https://example.com/news?id=456'))
        self.assertEqual(_normalize_url('https://example.com/news?b=2&a=&fbclid=x'), 'https://example.com/news?a=&b=2')

    def test_fact_changes_are_retained(self):
        for left, right in [('Счет 1:0', 'Счет 0:1'), ('Сумма 10 млн', 'Сумма 20 млн'), ('Игрок перейдет', 'Игрок не перейдет')]:
            self.assertTrue(facts_conflict(left, right))
        self.assertFalse(facts_conflict('Счет 1 : 0', 'Счет 1:0'))

    def test_ingest_keeps_changed_scores_and_negation(self):
        repo = NewsRepository()
        title = 'Спартак победил Зенит со счетом 1:0 в матче чемпионата России'
        for other in [title.replace('1:0', '0:1'), title.replace('победил', 'не победил')]:
            tokens = repo._tokenize_similarity_text(title)
            self.assertIsNone(repo._best_duplicate_candidate(item_id='new', target_tokens=tokens, candidates=[('old', other, repo._normalize_similarity_text(other))]))
        self.assertIsNotNone(repo._best_duplicate_candidate(item_id='new', target_tokens=repo._tokenize_similarity_text(title), candidates=[('old', title, repo._normalize_similarity_text(title))]))

    def test_publish_guard_retains_changed_facts(self):
        draft = SimpleNamespace(title='Спартак победил Зенит', dek='Матч чемпионата России', body='Встреча завершилась со счетом 1:0.')
        candidate = SimpleNamespace(title=draft.title, dek=draft.dek, body=draft.body.replace('1:0', '0:1'))
        self.assertIsNone(evaluate_published_duplicate_guard(draft, [candidate]))
        candidate.body = draft.body
        self.assertEqual(evaluate_published_duplicate_guard(draft, [candidate]).decision, 'skip')

    def test_same_batch_is_rechecked_before_each_publication(self):
        repo = MagicMock()
        draft = SimpleNamespace(id='draft:1', raw_item_id='raw:1', title='Спартак победил Зенит', dek='Матч чемпионата России', body='Встреча завершилась со счетом 1:0.', category='football', review_summary='OK')
        second = SimpleNamespace(**{**draft.__dict__, 'id': 'draft:2', 'raw_item_id': 'raw:2'})
        raw = SimpleNamespace(url="https://example.com/news/1", published_at=datetime.now(timezone.utc), id='raw:1', external_id='1', title=draft.title, summary=draft.dek, lead=None, full_text=draft.body, is_duplicate=False, duplicate_reason=None)
        repo.list_publishable_drafts.return_value = [draft, second]
        repo.get_raw_item.return_value = raw
        repo.list_article_similarity_candidates.side_effect = [[], [draft]]
        with patch.object(runtime, 'repository', repo):
            self.assertEqual(service_publication._run_publish_for_drafts(limit=2), 1)
        repo.publish_draft_to_news.assert_called_once()
        self.assertEqual(repo.list_article_similarity_candidates.call_count, 2)
        self.assertIsNone(repo.list_article_similarity_candidates.call_args.kwargs['category'])
        self.assertIsNone(repo.list_article_similarity_candidates.call_args.kwargs['limit'])

    def test_queue_does_not_depend_on_last_ingest(self):
        repo = MagicMock()
        repo.list_pending_enrichment_raw_items.return_value = []
        with patch.object(runtime, 'repository', repo):
            self.assertEqual(service_enrichment._select_pre_enrichment_raw_items(limit=5, since=None), [])
        repo.list_pending_enrichment_raw_items.assert_called_once_with(limit=15, since=None)
        with patch.object(service_editorial, 'run_content_planner', return_value=[]) as planner, patch.object(pipeline_logging, '_current_ingest_started_at', side_effect=AssertionError('must not gate queue')):
            service_editorial.run_planner(limit=5)
        planner.assert_called_once_with(runtime.repository, limit=5, since=None)


if __name__ == '__main__':
    unittest.main()
