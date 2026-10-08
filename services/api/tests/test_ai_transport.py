"""Provider requests are mocked: test payloads and bounded calls without paid API use."""
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from urllib.error import URLError
from unittest.mock import MagicMock, patch

from services.api.app import ai_transport
from services.api.app.ai_client import OpenAIEditorialClient
from services.api.app.config import OpenAISettings


class AITransportTests(unittest.TestCase):
    def settings(self, **changes):
        settings = OpenAISettings(api_key='test-key', editorial_model='test-editor', search_model='test-search',
            base_url='https://api.openai.com/v1', timeout_seconds=10, api_style='responses',
            provider_label='test', web_search_enabled=True, web_search_live=False, web_search_context_size='low')
        return replace(settings, **changes)

    def response(self, payload):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        return response

    def test_responses_request_keeps_options_citations_and_usage(self):
        client = OpenAIEditorialClient(self.settings())
        payload = {'output_text': '{"title":"Example"}', 'usage': {'input_tokens': 7},
                   'output': [{'type': 'web_search_call'}, {'content': [{'annotations': [
                       {'type': 'url_citation', 'url': 'https://example.com/news'}]}]}]}
        citations = []
        with patch.object(ai_transport, 'urlopen', return_value=self.response(payload)) as request, patch.object(ai_transport, 'record_ai_usage_event') as usage:
            text = client._create_response(instructions='System', input_text='Input', model='test-search',
                tools=client._build_web_search_tools('https://example.com/news'), max_output_tokens=123,
                reasoning_effort='low', text_format={'type': 'json_object'}, citation_urls=citations,
                operation='fixture', related_id='raw:fixture')
        self.assertEqual(text, payload['output_text'])
        request.assert_called_once()
        body = json.loads(request.call_args.args[0].data)
        self.assertEqual(body['max_output_tokens'], 123)
        self.assertEqual(body['reasoning'], {'effort': 'low'})
        self.assertEqual(body['tools'][0]['filters'], {'allowed_domains': ['example.com']})
        self.assertFalse(body['tools'][0]['external_web_access'])
        self.assertEqual(citations, ['https://example.com/news'])
        self.assertEqual(usage.call_args.kwargs['web_search_calls'], 1)

    def test_chat_completion_uses_one_request_without_search_tools(self):
        client = OpenAIEditorialClient(self.settings(api_style='chat_completions'))
        payload = {'choices': [{'message': {'content': '{"title":"Example"}'}}]}
        with patch.object(ai_transport, 'urlopen', return_value=self.response(payload)) as request, patch.object(ai_transport, 'record_ai_usage_event') as usage:
            client._create_response(instructions='System', input_text='Input', tools=[{'type': 'web_search'}])
        request.assert_called_once()
        body = json.loads(request.call_args.args[0].data)
        self.assertNotIn('tools', body)
        self.assertEqual(body['response_format'], {'type': 'json_object'})
        self.assertTrue(request.call_args.args[0].full_url.endswith('/chat/completions'))
        self.assertFalse(usage.call_args.kwargs['used_web_search'])

    def test_transient_transport_retry_stays_bounded_to_two_attempts(self):
        client = OpenAIEditorialClient(self.settings())
        with patch.object(ai_transport, 'urlopen', side_effect=URLError('fixture')) as request, patch.object(ai_transport, 'sleep') as sleep, patch.object(ai_transport, 'record_ai_usage_event') as usage:
            with self.assertRaises(URLError):
                client._create_response(instructions='System', input_text='Input')
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1)
        usage.assert_not_called()

    def test_draft_generation_uses_one_call_and_preserves_operation(self):
        client = OpenAIEditorialClient(self.settings())
        raw = SimpleNamespace(id='raw:fixture', full_text='Full text', lead=None, tags=[], source_title='Source',
            title='Original', summary='Summary', normalized_category='football', triage_label='high', importance_score=80)
        prompt = SimpleNamespace(system_prompt='System', user_prompt_template='Template')
        payload = {'output_text': json.dumps({'title': 'Title', 'dek': 'Lead', 'body': 'Body'})}
        with patch.object(ai_transport, 'urlopen', return_value=self.response(payload)) as request, patch.object(ai_transport, 'record_ai_usage_event') as usage:
            draft = client.generate_draft(raw, prompt)
        self.assertEqual(draft.body, 'Body')
        request.assert_called_once()
        self.assertEqual(usage.call_args.kwargs['operation'], 'news_writer')
        with patch.object(ai_transport, 'urlopen') as request:
            self.assertIsNone(OpenAIEditorialClient(self.settings(api_key=None)).generate_draft(raw, prompt))
        request.assert_not_called()
