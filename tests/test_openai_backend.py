import io
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from reader.backends import ModelError, call, openai_key
from financial_brief.server import create_app


class OpenAIBackendTests(unittest.TestCase):
    def test_gpt5_mini_uses_responses_schema_and_server_side_key(self):
        reply = {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": '{"facts":[]}'}]}]}
        schema = {"type": "object", "properties": {"facts": {"type": "array", "items": {"type": "string"}}},
                  "required": ["facts"], "additionalProperties": False}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch('reader.backends.post', return_value=reply) as post:
            self.assertEqual(call('openai', 'gpt-5-mini', 'Read this', schema, 'http://unused', 4500), {"facts": []})
        url, body, headers = post.call_args.args
        self.assertEqual(url, 'https://api.openai.com/v1/responses')
        self.assertEqual(headers['Authorization'], 'Bearer test-key')
        self.assertEqual(body['reasoning'], {'effort': 'minimal'})
        self.assertNotIn('temperature', body)
        self.assertNotIn('max_tokens', body)
        self.assertFalse(body['store'])
        self.assertTrue(body['text']['format']['strict'])
        self.assertEqual(body['text']['format']['schema'], schema)
        self.assertEqual(body['max_output_tokens'], 4500)

    def test_independent_context_stage_can_request_more_reasoning(self):
        reply={"status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":'{"ok":true}'}]}]}
        with patch.dict(os.environ,{"OPENAI_API_KEY":"test-key"}),patch('reader.backends.post',return_value=reply) as post:
            call('openai','gpt-5-mini','Review',{},reasoning_effort='medium')
        self.assertEqual(post.call_args.args[1]['reasoning'],{'effort':'medium'})

    def test_tls_request_avoids_macos_system_proxy_discovery(self):
        import ssl
        from reader.backends import post
        with patch('urllib.request.getproxies', side_effect=AssertionError('unsafe after fork')), \
             patch('urllib.request.getproxies_environment', return_value={}), \
             patch('urllib.request.OpenerDirector.open') as send:
            send.return_value.__enter__.return_value = io.BytesIO(b'{"ok":true}')
            self.assertEqual(post('https://api.openai.com/v1/responses', {},
                                  context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)), {'ok': True})

    def test_key_file_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'key'
            for contents in ['test-key', 'OPENAI_API_KEY="test-key"', "export OPENAI_API_KEY='test-key'"]:
                path.write_text(contents)
                with patch.dict(os.environ, {'OPENAI_API_KEY': '', 'OPENAI_API_KEY_FILE': str(path)}):
                    self.assertEqual(openai_key(), 'test-key')
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'env-key', 'OPENAI_API_KEY_FILE': str(path)}):
                self.assertEqual(openai_key(), 'env-key')

    def test_provider_errors_are_actionable_and_do_not_echo_response_or_key(self):
        for code, message in [(401, 'API key'), (404, 'unavailable'), (429, 'quota')]:
            exc = urllib.error.HTTPError('https://api.openai.com/v1/responses', code, 'failure', {}, io.BytesIO(b'sensitive'))
            with self.subTest(code=code), patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), patch('reader.backends.post', side_effect=exc):
                with self.assertRaises(ModelError) as caught:
                    call('openai', 'gpt-5-mini', 'private document', {})
                self.assertIn(message, str(caught.exception))
                self.assertNotIn('test-key', str(caught.exception))
                self.assertNotIn('sensitive', str(caught.exception))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), patch('reader.backends.post', side_effect=urllib.error.URLError('DNS')):
            with self.assertRaisesRegex(ModelError, 'DNS'):
                call('openai', 'gpt-5-mini', 'private document', {})

    def test_refusal_and_incomplete_responses_are_not_parsed_as_reports(self):
        for response in [{'status': 'incomplete'}, {'status': 'completed', 'output': [
                {'type': 'message', 'content': [{'type': 'refusal', 'refusal': 'No'}]}]}]:
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), patch('reader.backends.post', return_value=response):
                with self.assertRaises(ModelError):
                    call('openai', 'gpt-5-mini', 'Read this', {})

    def test_local_provider_configuration_and_environment_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text('{"backend":"openai","model":"gpt-5-mini"}')
            with patch.dict(os.environ, {'BRIEF_CONFIG': str(path), 'OPENAI_API_KEY': 'test-key'}, clear=True):
                app = create_app({'TESTING': True, 'DATA_DIR': str(Path(directory) / 'reports')})
                self.assertEqual(app.config['BACKEND'], 'openai')
                self.assertEqual(app.config['MODEL'], 'gpt-5-mini')
                self.assertEqual(app.test_client().get('/healthz').json,
                                 {'status': 'ok', 'backend': 'openai', 'model': 'gpt-5-mini', 'models': {'extract': 'gpt-5-mini', 'write': 'gpt-5-mini', 'review': 'gpt-5-mini'}, 'concurrency': 2})
                with patch.dict(os.environ, {'BRIEF_BACKEND': 'link', 'BRIEF_MODEL': 'other-model'}):
                    app = create_app({'TESTING': True, 'DATA_DIR': str(Path(directory) / 'reports')})
                    self.assertEqual(app.config['BACKEND'], 'link')
                    self.assertEqual(app.config['MODEL'], 'other-model')
