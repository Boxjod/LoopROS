import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from loop_robot.terminal.config import load_config, validate_provider
from loop_robot.terminal.home import saved_key
from loop_robot.terminal.providers import ProviderStore
from loop_robot.terminal.setup import quick_setup, ensure_setup, discover_models, check_connection
from loop_robot.terminal.llm import QwenClient, ChatAgent, ModelAPIError
from loop_robot.terminal.protocols import encode, decode


class SetupTests(unittest.TestCase):
    def test_recovery_reuses_saved_profile_without_key_prompt_or_discovery(self):
        from loop_robot.terminal.setup import recover_profile
        from loop_robot.terminal.home import save_key
        config={**load_config()['llm'],'base_url':'https://existing.example/v1','model':'existing-model'}
        self.store.save('existing',config);save_key(config,'saved-test-key')
        self.store.deduplicate();profiles=self.store.list();index=next(i for i,p in enumerate(profiles,1) if p['name']=='existing')
        output=[]
        with patch('loop_robot.terminal.setup.quick_setup',side_effect=AssertionError('Must reuse')), patch('loop_robot.terminal.setup.discover_models',side_effect=AssertionError('No network')):
            self.assertEqual(recover_profile(self.store,read=lambda _:str(index),write=output.append),'existing')
        self.assertEqual(self.store.selected()['master'],'existing')
        self.assertEqual(saved_key(self.store.get('existing')),'saved-test-key')
        self.assertNotIn('saved-test-key','\n'.join(output))

    def test_all_failed_profiles_open_setup_without_another_menu(self):
        from loop_robot.terminal.setup import recover_profile
        self.store.deduplicate()
        config = {**load_config()['llm'], 'base_url': 'https://second.example/v1'}
        self.store.save('second', config)
        for profile in self.store.list():
            self.store.use('master', profile['name'])
            self.store.record_check('failed (HTTP 404)')
        output = []
        with patch('loop_robot.terminal.setup.quick_setup', return_value='new-profile') as setup:
            self.assertEqual(recover_profile(self.store, read=Mock(side_effect=AssertionError('No failed menu')), write=output.append), 'new-profile')
            setup.assert_called_once_with(self.store)
        self.assertIn('All saved profiles failed', '\n'.join(output))
        self.assertNotIn('Saved profiles (', '\n'.join(output))
        self.store.record_check('passed')
        with patch('loop_robot.terminal.setup.quick_setup', side_effect=AssertionError('Keep usable profiles')):
            self.assertIsNone(recover_profile(self.store, read=lambda _: '0', write=lambda _: None))

    def test_setup_can_select_saved_key_even_when_all_profiles_failed(self):
        from loop_robot.terminal.home import save_key
        self.store.deduplicate()
        name = self.store.list()[0]['name']
        self.store.use('master', name)
        config = self.store.get(name)
        save_key(config, 'existing-private-test-key')
        self.store.record_check('failed (HTTP 404)')
        output = []
        with patch('loop_robot.terminal.setup.discover_models', side_effect=AssertionError('No network')):
            result = quick_setup(self.store, read=Mock(side_effect=['s', '1']),
                                 secret=Mock(side_effect=AssertionError('No key prompt')), write=output.append)
        self.assertEqual(result, name)
        self.assertEqual(saved_key(config), 'existing-private-test-key')
        self.assertIn('Saved profiles (selection reuses saved credentials):', output)
        self.assertNotIn('existing-private-test-key', '\n'.join(output))
        self.assertIsNone(quick_setup(self.store, read=Mock(side_effect=['s', '0']), write=lambda _: None))

    def test_recovery_cancel_and_retry_preserve_selection(self):
        from loop_robot.terminal.setup import recover_profile
        self.store.deduplicate()
        before=self.store.selected()
        self.assertIsNone(recover_profile(self.store,read=lambda _:'0',write=lambda _:None))
        self.assertEqual(recover_profile(self.store,read=lambda _:'r',write=lambda _:None),before['master'])
        self.assertEqual(self.store.selected(),before)

    def test_duplicate_credentials_keep_latest_and_repoint_selection(self):
        from loop_robot.terminal.home import save_key
        config = {**load_config()['llm'], 'base_url': 'https://duplicate.example/v1'}
        save_key(config, 'private-test-key')
        self.store.save('old', config)
        self.store.use('master', 'old')
        self.store.save('latest', {**config, 'model': 'new-model', 'protocol': 'openai-responses'})
        self.assertGreaterEqual(self.store.deduplicate(), 1)
        self.assertEqual(self.store.selected()['master'], 'latest')
        self.assertEqual(self.store.selected()['expert'], 'latest')
        with self.assertRaises(ValueError):
            self.store.get('old')
        other = {**config, 'api_key_env': 'OTHER_ACCOUNT'}
        save_key(other, 'different-key')
        self.store.save('other-account', other)
        self.store.save('different-path', {**config, 'base_url': 'https://duplicate.example'})
        self.assertEqual(self.store.deduplicate(), 1)
        self.assertNotIn('private-test-key', json.dumps(self.store.list()))

    def test_removed_defaults_stay_removed_after_reopen(self):
        self.store.deduplicate()
        before = {p['name'] for p in self.store.list()}
        other = ProviderStore(Path(self.tmp.name) / 'profiles.sqlite', load_config())
        try:
            self.assertEqual({p['name'] for p in other.list()}, before)
        finally:
            other.close()

    def test_check_results_persist_in_menu_and_expire_on_key_change(self):
        from loop_robot.terminal.home import save_key
        from loop_robot.terminal.setup import recover_profile
        config = {**load_config()['llm'], 'base_url': 'https://tested.example/v1'}
        save_key(config, 'first-key')
        self.store.save('tested', config)
        self.store.use('master', 'tested')
        self.store.record_check('failed (HTTP 401)')
        output = []
        recover_profile(self.store, read=lambda _: '0', write=output.append)
        self.assertIn('[default/current] | failed (HTTP 401) @', '\n'.join(output))
        self.store.record_check('passed')
        self.assertEqual(self.store.connection_check('tested')['status'], 'passed')
        save_key(config, 'second-key')
        self.assertEqual(self.store.connection_check('tested')['status'], 'untested')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"LOOPER_HOME": self.tmp.name})
        self.env.start()
        self.store = ProviderStore(Path(self.tmp.name) / "profiles.sqlite", load_config())

    def tearDown(self):
        self.store.close()
        self.env.stop()
        self.tmp.cleanup()

    def wizard(self, answers, **kwargs):
        with patch("loop_robot.terminal.setup.build_opener", side_effect=OSError("offline test")):
            return quick_setup(self.store, read=Mock(side_effect=answers),
                               secret=lambda prompt: "test-only", write=lambda text: None, **kwargs)

    def test_model_menu_limits_each_company_and_keeps_manual_ids(self):
        models = [{'id': company + '-' + str(i), 'company': company,
                   'date': '2026-09-{:02d}'.format(20-i)}
                  for company in ('Alibaba', 'DeepSeek', 'Unknown') for i in range(12)]
        for choice, expected in (('11', 'DeepSeek-0'), ('Alibaba-11', 'Alibaba-11')):
            output = []
            with patch('loop_robot.terminal.setup.discover_models', return_value=models):
                name = quick_setup(self.store,
                    read=Mock(side_effect=['https://menu.example/v1', '', choice]),
                    secret=lambda _: 'test-menu-key', write=output.append)
            rows = [line for line in output if ' | 2026-' in line]
            self.assertEqual(len(rows), 30)
            self.assertTrue(rows[10].startswith('  11. DeepSeek-0'))
            self.assertFalse(any('Alibaba-10 |' in line for line in rows))
            self.assertEqual(self.store.get(name)['model'], expected)

    def test_default_two_fields_persist(self):
        with patch("loop_robot.terminal.setup.discover_models", return_value=[]) as discover:
            name = self.wizard(["", "", ""])
            discover.assert_called_once()
        config = self.store.get(name)
        self.assertEqual(config["protocol"], "openai")
        self.assertEqual(config["model"], "gpt-6-astra")
        self.assertEqual(saved_key(config), "test-only")
        self.assertEqual(self.store.selected()["master"], name)
        self.assertEqual(self.store.selected()["expert"], self.store.selected()["master"])
        self.assertNotIn("test-only", json.dumps(self.store.list()))

    def test_custom_discovery_and_advanced(self):
        with patch("loop_robot.terminal.setup.discover_models", return_value=[{"id": "vendor-model", "company": "Unknown", "date": "Unknown"}]):
            name = self.wizard(["https://custom.example/v1", "", ""])
        self.assertEqual(self.store.get(name)["model"], "vendor-model")
        name = self.wizard(["https://custom.example/v2", "2", "explicit-model"])
        self.assertEqual(self.store.get(name)["protocol"], "openai-responses")

    def test_custom_gpt6_uses_explicit_endpoint_and_preserves_profiles(self):
        before = {item["name"]: self.store.get(item["name"]) for item in self.store.list()}
        with patch("loop_robot.terminal.setup.discover_models", return_value=[]) as discover:
            name = self.wizard(["https://gateway.example/v1", "2", "gpt-6-astra"])
            discover.assert_called_once()
        config = self.store.get(name)
        self.assertEqual(config["base_url"], "https://gateway.example/v1")
        self.assertEqual(config["protocol"], "openai-responses")
        self.assertEqual(config["model"], "gpt-6-astra")
        self.assertEqual(saved_key(config), "test-only")
        self.assertIsNone(saved_key({**config, "base_url": "https://api.openai.com/v1"}))
        remaining = [self.store.get(item["name"]) for item in self.store.list()]
        for old_config in before.values():
            self.assertIn(old_config, remaining)

    def test_cancel_invalid_and_failed_discovery(self):
        before = self.store.selected()
        self.assertIsNone(self.wizard(["0"]))
        with self.assertRaises(ValueError):
            self.wizard(["http://remote.example/v1"])
        with patch("loop_robot.terminal.setup.discover_models", side_effect=ValueError("Unavailable")):
            self.assertIsNone(self.wizard(["https://custom.example/v1", "", "", ""]))
        self.assertEqual(before, self.store.selected())
        self.assertFalse((Path(self.tmp.name) / "credentials.json").exists())

    def test_startup_gate(self):
        app = Mock()
        with patch("loop_robot.terminal.setup.check_connection") as check, patch("loop_robot.terminal.setup.recover_profile") as wizard:
            self.assertTrue(ensure_setup(app, False))
            check.assert_not_called()
            wizard.assert_not_called()
            self.assertTrue(ensure_setup(app, True))
            check.assert_called_once_with(app.client)
            wizard.assert_not_called()
        with patch("loop_robot.terminal.setup.check_connection", side_effect=RuntimeError("bad key")), patch("loop_robot.terminal.setup.recover_profile", return_value=None):
            self.assertFalse(ensure_setup(app, True))
            app.apply_profiles.assert_not_called()
        with patch("loop_robot.terminal.setup.check_connection", side_effect=[RuntimeError("bad URL"), None]) as check, patch("loop_robot.terminal.setup.recover_profile", return_value="new") as wizard:
            self.assertTrue(ensure_setup(app, True))
            app.apply_profiles.assert_called_once()
            self.assertEqual(check.call_count, 2)
            wizard.assert_called_once_with(app.providers)

    def test_repeated_failure_requires_user_setup_and_supports_cancel(self):
        app = Mock()
        with patch("loop_robot.terminal.setup.check_connection", side_effect=RuntimeError("secret must not leak")), patch("loop_robot.terminal.setup.recover_profile", side_effect=["new", None]) as wizard, patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertFalse(ensure_setup(app, True))
            self.assertEqual(wizard.call_count, 2)
            self.assertNotIn("secret must not leak", output.getvalue())
        with patch("loop_robot.terminal.setup.check_connection", side_effect=KeyboardInterrupt):
            self.assertFalse(ensure_setup(app, True))

    def test_full_endpoint_and_protocol_selection(self):
        name = self.wizard(["https://custom.example/v1/responses", "2", "my-model"])
        self.assertEqual(self.store.get(name)['base_url'], 'https://custom.example/v1')
        self.assertEqual(self.store.get(name)['protocol'], 'openai-responses')
        name = self.wizard(["https://custom.example/v1/chat/completions", "1", "chat-model"])
        self.assertEqual(self.store.get(name)['protocol'], 'openai')
        before = self.store.selected()
        self.assertIsNone(self.wizard(["1", "0"]))
        with self.assertRaises(ValueError):
            self.wizard(["1", "unsupported"])
        self.assertEqual(self.store.selected(), before)

    def test_connection_uses_selected_endpoint_without_tools_or_history(self):
        for protocol, endpoint in [('openai', '/chat/completions'), ('openai-responses', '/responses')]:
            client = QwenClient({**load_config()['llm'], 'protocol': protocol, 'base_url': 'https://gateway.example/v1'})
            client.key = 'probe-secret'
            payload = ({'choices': [{'message': {'content': 'OK'}}]} if protocol == 'openai' else
                       {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'OK'}]}]})
            with patch('loop_robot.terminal.llm.build_opener') as opener:
                opener.return_value.open.side_effect = lambda *args, **kwargs: io.BytesIO(json.dumps(payload).encode())
                check_connection(client)
                initial = opener.return_value.open.call_args_list[0]
                request = initial.args[0]
                self.assertEqual(request.full_url, 'https://gateway.example/v1' + endpoint)
                body = json.loads(request.data)
                self.assertNotIn('tools', body)
                self.assertFalse(body['stream'])
                self.assertEqual(initial.kwargs['timeout'], client.config['timeout_s'])
                self.assertEqual(opener.return_value.open.call_count, 2)
                self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 10)
                self.assertEqual(request.get_header('Authorization'), 'Bearer probe-secret')
                self.assertEqual(client.config['timeout_s'], 60)
            with patch('loop_robot.terminal.setup.QwenClient.complete', return_value={'content': ''}), patch('loop_robot.terminal.setup.discover_models', return_value=[]):
                with self.assertRaisesRegex(RuntimeError, 'no text'):
                    check_connection(client)

    def test_startup_accepts_alternative_model_without_changing_selection(self):
        client = QwenClient({**load_config()['llm'], 'model': 'bad-model'})
        client.key = 'test-secret'
        original = dict(client.config)
        calls = []
        def complete(probe, messages, tools):
            calls.append((dict(probe.config), probe.key, messages, tools))
            if probe.config['model'] != 'working-chat':
                raise ModelAPIError('HTTP 404', status=404)
            return {'content': 'OK'}
        with patch('loop_robot.terminal.setup.discover_models', return_value=[{'id': m} for m in ['bad-model', 'embedding', 'broken-chat', 'working-chat']]), patch.object(QwenClient, 'complete', complete):
            self.assertEqual(check_connection(client), 'unknown')
        self.assertEqual(client.config, original)
        self.assertEqual([c[0]['model'] for c in calls], ['bad-model', 'broken-chat', 'working-chat'])
        for config, key, messages, tools in calls:
            self.assertEqual(config['base_url'], original['base_url'])
            self.assertEqual(config.get('protocol', 'openai'), original.get('protocol', 'openai'))
            self.assertEqual(key, 'test-secret')
            self.assertEqual(tools, [])
            self.assertEqual(messages, [{'role': 'user', 'content': 'Reply with OK only.'}])

    def test_startup_alternatives_are_bounded_and_auth_failure_skips_discovery(self):
        client = QwenClient(load_config()['llm'])
        client.key = 'test-secret'
        with patch('loop_robot.terminal.setup.discover_models', return_value=[{'id': 'chat-' + str(i)} for i in range(8)]) as catalog, patch.object(QwenClient, 'complete', side_effect=ModelAPIError('HTTP 404', status=404)) as complete:
            with self.assertRaises(ModelAPIError):
                check_connection(client)
            self.assertEqual(complete.call_count, 4)
            catalog.assert_called_once()
        with patch('loop_robot.terminal.setup.discover_models') as catalog, patch.object(QwenClient, 'complete', side_effect=ModelAPIError('HTTP 401', status=401)):
            with self.assertRaises(ModelAPIError):
                check_connection(client)
            catalog.assert_not_called()

    def test_discovery_transport(self):
        response = io.BytesIO(b'{"data":[{"id":"chat-b"},{"id":"chat-a"}]}')
        with patch("loop_robot.terminal.setup.build_opener") as opener:
            opener.return_value.open.return_value = response
            result = discover_models({"base_url": "https://example.com/v1"}, "test")
            self.assertEqual([item["id"] for item in result], ["chat-a", "chat-b"])
            request = opener.return_value.open.call_args[0][0]
            self.assertEqual(request.full_url, "https://example.com/v1/models")
            self.assertEqual(request.get_method(), "GET")

    def test_responses_tool_roundtrip(self):
        config = {**load_config()["llm"], "protocol": "openai-responses"}
        client = QwenClient(config)
        client.key = "test"
        output = [{"type": "reasoning", "id": "r1", "summary": [], "encrypted_content": "opaque"},
                  {"type": "function_call", "id": "f1", "call_id": "c1", "name": "status", "arguments": "{}"}]
        first = io.BytesIO(json.dumps({"status": "completed", "output": output}).encode())
        second = io.BytesIO(json.dumps({"status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "Done"}]}]}).encode())
        schema = [{"type": "function", "function": {"name": "status", "parameters": {"type": "object", "properties": {}}}}]
        with patch("loop_robot.terminal.llm.build_opener") as opener:
            opener.return_value.open.side_effect = [first, second]
            self.assertEqual(ChatAgent(client, schema, lambda n, a: {"ok": True}).reply("check"), "Done")
            request = opener.return_value.open.call_args[0][0]
            self.assertTrue(request.full_url.endswith("/responses"))
            body = json.loads(request.data)
            self.assertFalse(body["store"])
            self.assertIn(output[0], body["input"])
            self.assertEqual(body["input"][-1]["type"], "function_call_output")
            self.assertEqual(body["input"][-1]["call_id"], "c1")
            self.assertEqual(body["tools"][0]["name"], "status")
        with self.assertRaises(ValueError):
            decode(config, {"status": "incomplete", "output": []})
        with self.assertRaises(ValueError):
            validate_provider({**config, "protocol": "unsupported"})

    def test_catalog_company_time_sort_and_malformed_entries(self):
        data = [
            {"id": "gpt-new", "created": 200},
            {"id": "claude-old", "created": 100, "owned_by": "gateway"},
            {"id": "qwen-20260901"},
            {"id": "claude-new", "created": 300},
            {"id": "gpt-undated", "created": "invalid"},
            {"id": "gpt-old", "created": 100},
            {"id": "claude-new", "created": 200},
            {"id": "custom", "owned_by": "Acme", "release_date": "2026-09-02"},
            {"id": "unknown"}, {"id": "bad\nID"}, {"id": 123}, {}, None,
        ]
        with patch("loop_robot.terminal.setup.build_opener") as opener:
            opener.return_value.open.return_value = io.BytesIO(json.dumps({"data": data}).encode())
            result = discover_models({"base_url": "https://gateway.example/v1"}, "private-key")
        self.assertEqual([m["id"] for m in result], ["custom", "qwen-20260901", "claude-new",
                         "claude-old", "gpt-new", "gpt-old", "gpt-undated", "unknown"])
        self.assertEqual(result[1]["date"], "2026-09-01")
        self.assertEqual(result[2]["timestamp"], 300)
        self.assertEqual(result[-2]["date"], "Unknown")

    def test_selection_limits_models_and_reprompts_bad_number(self):
        models = [{"id": "model-{}".format(i), "company": "Acme", "date": "Unknown"} for i in range(45)]
        output = []
        with patch("loop_robot.terminal.setup.discover_models", return_value=models):
            name = quick_setup(self.store, read=Mock(side_effect=["c", "https://gateway.example/v1", "1", "99", "10"]),
                               secret=lambda _: "private-key", write=output.append)
        self.assertEqual(self.store.get(name)["model"], "model-9")
        self.assertIn("  10. model-9 | Unknown", output)
        self.assertNotIn("  11. model-10 | Unknown", output)
        self.assertNotIn("private-key", "\n".join(output))

    def test_catalog_cancel_does_not_save_key_or_profile(self):
        before = self.store.list()
        with patch("loop_robot.terminal.setup.discover_models", return_value=[{"id": "gpt-test", "company": "OpenAI", "date": "Unknown"}]):
            self.assertIsNone(self.wizard(["1", "2", "0"]))
        self.assertEqual(self.store.list(), before)
        self.assertFalse((Path(self.tmp.name) / "credentials.json").exists())

    def test_discovery_errors_are_sanitized(self):
        for response in (b'not-json', b'{"data": {}}', b'x' * (1024 * 1024 + 1)):
            with patch("loop_robot.terminal.setup.build_opener") as opener:
                opener.return_value.open.return_value = io.BytesIO(response)
                with self.assertRaisesRegex(ValueError, "Model discovery unavailable"):
                    discover_models({"base_url": "https://gateway.example/v1"}, "private-key")
        with patch("loop_robot.terminal.setup.build_opener", side_effect=OSError("private-key")):
            with self.assertRaises(ValueError) as error:
                discover_models({"base_url": "https://gateway.example/v1"}, "private-key")
            self.assertNotIn("private-key", str(error.exception))
