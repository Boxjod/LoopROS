import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from loop_robot.terminal.reasoning import choices, remember, metadata
from loop_robot.terminal.completion import SlashCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.completion import CompleteEvent


class ReasoningChoicesTests(unittest.TestCase):
    def app(self, model='gpt-6-astra'):
        return SimpleNamespace(client=SimpleNamespace(
            config={'base_url':'https://gateway.example/v1','protocol':'openai','model':model},
            resolved_key=Mock(return_value='first-key')))

    def test_endpoint_overrides_official_and_credentials_scope_cache(self):
        app = self.app()
        remember(app, [{'id':'gpt-6-astra','reasoning_efforts':['high']}])
        self.assertEqual(choices(app)['choices'], ['default','high'])
        app.client.resolved_key.return_value='second-key'
        result=choices(app)
        self.assertIn('low',result['choices'])
        self.assertIn('not verified',result['notice'])
        self.assertNotIn('none',result['choices'])
        remember(app,[{'id':'gpt-6-astra','reasoning_efforts':[]}])
        self.assertEqual(choices(app)['choices'],['default'])
        app.client.config['base_url']='https://other.example/v1'
        self.assertIn('low',choices(app)['choices'])

    def test_unknown_metadata_and_cache_expiry(self):
        self.assertIsNone(metadata({'reasoning_effort':True}))
        self.assertEqual(metadata({'reasoning_effort':{'enum':['high','invented','low']}}), ['low','high'])
        app=self.app('unknown-model')
        self.assertEqual(choices(app)['choices'],['default'])
        remember(app,[{'id':'unknown-model','reasoning_efforts':['high']}])
        with patch('loop_robot.terminal.reasoning.time.monotonic',return_value=app.reasoning_catalog[1]+301):
            self.assertEqual(choices(app)['choices'],['default'])

    def test_discovery_retains_endpoint_effort_enum(self):
        import json
        from loop_robot.terminal.setup import discover_models
        with patch('loop_robot.terminal.setup.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps({'data': [
                {'id': 'model-a', 'supported_reasoning_efforts': ['low', 'high']},
                {'id': 'model-b', 'reasoning_effort': True}]}).encode()
            rows = discover_models({'base_url': 'https://gateway.example/v1'}, 'test-key')
        self.assertEqual(rows[0]['reasoning_efforts'], ['low', 'high'])
        self.assertNotIn('reasoning_efforts', rows[1])

    def test_official_models_and_dynamic_completions(self):
        self.assertEqual(choices(self.app('qwen3.8-max'))['choices'],['default','low','medium','xhigh'])
        self.assertIn('none',choices(self.app('gpt-5.6-sol'))['choices'])
        completer=SlashCompleter('/model ID EFFORT',reasoning=lambda:['default','high'])
        self.assertEqual([c.text for c in completer.get_completions(Document('/model chosen '),CompleteEvent())],['default','high'])
