import asyncio
import json
import os
import re
import unittest
from unittest.mock import patch

from fastapi.routing import APIRoute

from services.api.app import main
from services.api.app.auth import PUBLIC_READ_ROUTES, validate_admin_configuration


async def request(method, path, token=None, body=b'{}'):
    path, _, query = path.partition('?')
    headers = [(b'content-type', b'application/json')]
    if token is not None:
        headers.append((b'x-admin-token', token.encode()))
    messages = []
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        return {'type': 'http.disconnect'}

    async def send(message):
        messages.append(message)

    await main.app({
        'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
        'method': method, 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
        'query_string': query.encode(), 'headers': headers,
        'client': ('127.0.0.1', 1234), 'server': ('test', 80), 'root_path': '',
    }, receive, send)
    status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
    content = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
    return status, json.loads(content) if content else None


class AdminAuthTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'EZBET_ADMIN_API_TOKEN': 'test-token', 'EZBET_ENV': 'development'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_every_private_route_rejects_anonymous_requests(self):
        with patch.object(main, 'repository') as repo:
            for route in main.app.routes:
                if not isinstance(route, APIRoute):
                    continue
                for method in route.methods:
                    if method in {'GET', 'HEAD'} and route.path in PUBLIC_READ_ROUTES:
                        continue
                    path = re.sub(r'\{[^}]+\}', 'test', route.path)
                    with self.subTest(method=method, path=path):
                        self.assertEqual(asyncio.run(request(method, path))[0], 403)
            self.assertEqual(repo.mock_calls, [])

    def test_wrong_token_rejected_and_valid_token_reaches_endpoint(self):
        with patch.object(main.repository, 'delete_archived_prompt_versions', return_value=2) as cleanup:
            self.assertEqual(asyncio.run(request('POST', '/api/v1/prompts/cleanup', 'wrong'))[0], 403)
            cleanup.assert_not_called()
            status, payload = asyncio.run(request('POST', '/api/v1/prompts/cleanup', 'test-token'))
            self.assertEqual(status, 200)
            self.assertEqual(payload, {'deletedCount': 2})
            cleanup.assert_called_once()

    def test_private_reads_accept_token(self):
        with patch.object(main.repository, 'list_source_configs', return_value=[]) as sources:
            self.assertEqual(asyncio.run(request('GET', '/api/v1/sources', 'test-token')), (200, {'items': []}))
            sources.assert_called_once()

    def test_public_reads_stay_available_without_token(self):
        with patch.dict(os.environ, {'EZBET_ADMIN_API_TOKEN': ''}), patch.object(main, 'repository') as repo:
            repo.list.return_value = []
            repo.get_article_by_slug.return_value = None
            repo.list_match_forecasts.return_value = []
            repo.get_match_forecast.return_value = None
            for path, expected in [('/health', 200), ('/api/v1/news', 200), ('/api/v1/articles/missing', 404), ('/api/v1/forecasts', 200), ('/api/v1/forecasts/missing', 404)]:
                with self.subTest(path=path):
                    self.assertEqual(asyncio.run(request('GET', path))[0], expected)

    def test_hidden_news_require_token(self):
        with patch.object(main.repository, 'list', return_value=[]) as news:
            self.assertEqual(asyncio.run(request('GET', '/api/v1/news?includeHidden=true'))[0], 403)
            news.assert_not_called()
            self.assertEqual(asyncio.run(request('GET', '/api/v1/news?includeHidden=true', 'test-token'))[0], 200)

    def test_missing_token_fails_closed(self):
        for token in ['', '***', 'your_admin_api_token_here']:
            with self.subTest(token=token), patch.dict(os.environ, {'EZBET_ADMIN_API_TOKEN': token}):
                self.assertEqual(asyncio.run(request('POST', '/api/v1/pipeline/start'))[0], 503)

    def test_production_requires_strong_token_before_database_startup(self):
        with patch.dict(os.environ, {'EZBET_ENV': 'production', 'EZBET_ADMIN_API_TOKEN': 'short'}), patch.object(main.repository, 'ensure_schema') as schema:
            async def start():
                async with main.lifespan(main.app):
                    pass
            with self.assertRaises(RuntimeError):
                asyncio.run(start())
            schema.assert_not_called()
        with patch.dict(os.environ, {'EZBET_ENV': 'production', 'EZBET_ADMIN_API_TOKEN': 'x' * 32}):
            validate_admin_configuration()

    def test_pipeline_start_enqueues_without_running_in_api(self):
        job = {'id': 'fixture-job', 'status': 'pending', 'createdAt': '2026-10-08T00:00:00+00:00'}
        with patch.object(main, 'JobQueue') as queue_type, patch.object(main, '_run_pipeline_scheduler') as pipeline:
            queue_type.return_value.enqueue.return_value = (True, job)
            status, payload = asyncio.run(request('POST', '/api/v1/pipeline/start', 'test-token'))
            self.assertEqual(status, 200)
            self.assertTrue(payload['started'])
            self.assertEqual(payload['jobId'], 'fixture-job')
            queue_type.return_value.enqueue.assert_called_once_with(force=True)
            pipeline.assert_not_called()
