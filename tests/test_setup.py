import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from terminal.config import load_config, validate_provider
from terminal.home import saved_key
from terminal.providers import ProviderStore
from terminal.setup import quick_setup, ensure_setup, discover_models, check_connection
from terminal.llm import QwenClient, ChatAgent
from terminal.protocols import encode, decode


class SetupTests(unittest.TestCase):
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
        return quick_setup(self.store, read=Mock(side_effect=answers),
                           secret=lambda prompt: "test-only", write=lambda text: None, **kwargs)

    def test_default_two_fields_persist(self):
        with patch("terminal.setup.discover_models") as discover:
            name = self.wizard(["", "", ""])
            discover.assert_not_called()
        config = self.store.get(name)
        self.assertEqual(config["protocol"], "openai-responses")
        self.assertEqual(config["model"], "gpt-6-astra")
        self.assertEqual(saved_key(config), "test-only")
        self.assertEqual(self.store.selected()["master"], name)
        self.assertEqual(self.store.selected()["expert"], self.store.selected()["master"])
        self.assertNotIn("test-only", json.dumps(self.store.list()))

    def test_custom_discovery_and_advanced(self):
        with patch("terminal.setup.discover_models", return_value=["vendor-model"]):
            name = self.wizard(["https://custom.example/v1", "", ""])
        self.assertEqual(self.store.get(name)["model"], "vendor-model")
        name = self.wizard(["https://custom.example/v2", "2", "explicit-model"])
        self.assertEqual(self.store.get(name)["protocol"], "openai-responses")

    def test_custom_gpt6_uses_explicit_endpoint_and_preserves_profiles(self):
        before = {item["name"]: self.store.get(item["name"]) for item in self.store.list()}
        with patch("terminal.setup.discover_models") as discover:
            name = self.wizard(["https://gateway.example/v1", "2", "gpt-6-astra"])
            discover.assert_not_called()
        config = self.store.get(name)
        self.assertEqual(config["base_url"], "https://gateway.example/v1")
        self.assertEqual(config["protocol"], "openai-responses")
        self.assertEqual(config["model"], "gpt-6-astra")
        self.assertEqual(saved_key(config), "test-only")
        self.assertIsNone(saved_key({**config, "base_url": "https://api.openai.com/v1"}))
        for old_name, old_config in before.items():
            self.assertEqual(self.store.get(old_name), old_config)

    def test_cancel_invalid_and_failed_discovery(self):
        before = self.store.selected()
        self.assertIsNone(self.wizard(["0"]))
        with self.assertRaises(ValueError):
            self.wizard(["http://remote.example/v1"])
        with patch("terminal.setup.discover_models", side_effect=ValueError("Unavailable")):
            self.assertIsNone(self.wizard(["https://custom.example/v1", "", "", ""]))
        self.assertEqual(before, self.store.selected())
        self.assertFalse((Path(self.tmp.name) / "credentials.json").exists())

    def test_startup_gate(self):
        app = Mock()
        with patch("terminal.setup.check_connection") as check, patch("terminal.setup.quick_setup") as wizard:
            self.assertTrue(ensure_setup(app, False))
            check.assert_not_called()
            wizard.assert_not_called()
            self.assertTrue(ensure_setup(app, True))
            check.assert_called_once_with(app.client)
            wizard.assert_not_called()
        with patch("terminal.setup.check_connection", side_effect=RuntimeError("bad key")), patch("terminal.setup.quick_setup", return_value=None):
            self.assertFalse(ensure_setup(app, True))
            app.apply_profiles.assert_not_called()
        with patch("terminal.setup.check_connection", side_effect=[RuntimeError("bad URL"), None]) as check, patch("terminal.setup.quick_setup", return_value="new") as wizard:
            self.assertTrue(ensure_setup(app, True))
            app.apply_profiles.assert_called_once()
            self.assertEqual(check.call_count, 2)
            wizard.assert_called_once_with(app.providers)

    def test_repeated_failure_requires_user_setup_and_supports_cancel(self):
        app = Mock()
        with patch("terminal.setup.check_connection", side_effect=RuntimeError("secret must not leak")), patch("terminal.setup.quick_setup", side_effect=["new", None]) as wizard, patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertFalse(ensure_setup(app, True))
            self.assertEqual(wizard.call_count, 2)
            self.assertNotIn("secret must not leak", output.getvalue())
        with patch("terminal.setup.check_connection", side_effect=KeyboardInterrupt):
            self.assertFalse(ensure_setup(app, True))

    def test_full_endpoint_and_protocol_selection(self):
        name = self.wizard(["https://custom.example/v1/responses", "", "my-model"])
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
            with patch('terminal.llm.build_opener') as opener:
                opener.return_value.open.return_value = io.BytesIO(json.dumps(payload).encode())
                check_connection(client)
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.full_url, 'https://gateway.example/v1' + endpoint)
                body = json.loads(request.data)
                self.assertNotIn('tools', body)
                self.assertFalse(body['stream'])
                self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], client.config['timeout_s'])
                self.assertEqual(request.get_header('Authorization'), 'Bearer probe-secret')
                self.assertEqual(client.config['timeout_s'], 60)
            with patch('terminal.setup.QwenClient.complete', return_value={'content': ''}):
                with self.assertRaisesRegex(RuntimeError, 'no text'):
                    check_connection(client)

    def test_discovery_transport(self):
        response = io.BytesIO(b'{"data":[{"id":"chat-b"},{"id":"chat-a"}]}')
        with patch("terminal.setup.build_opener") as opener:
            opener.return_value.open.return_value = response
            result = discover_models({"base_url": "https://example.com/v1"}, "test")
            self.assertEqual(result, ["chat-a", "chat-b"])
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
        with patch("terminal.llm.build_opener") as opener:
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
