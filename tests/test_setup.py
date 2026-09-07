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
from terminal.setup import quick_setup, ensure_setup, discover_models
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
            name = self.wizard(["", ""])
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
            name = self.wizard(["https://custom.example/v1", ""])
        self.assertEqual(self.store.get(name)["model"], "vendor-model")
        name = self.wizard(["https://custom.example/v2", "a", "openai-responses", "explicit-model"])
        self.assertEqual(self.store.get(name)["protocol"], "openai-responses")

    def test_custom_gpt6_uses_explicit_endpoint_and_preserves_profiles(self):
        before = {item["name"]: self.store.get(item["name"]) for item in self.store.list()}
        with patch("terminal.setup.discover_models") as discover:
            name = self.wizard(["https://gateway.example/v1", "a", "openai-responses", "gpt-6-astra"])
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
            self.assertIsNone(self.wizard(["https://custom.example/v1", "", ""]))
        self.assertEqual(before, self.store.selected())
        self.assertFalse((Path(self.tmp.name) / "credentials.json").exists())

    def test_startup_gate(self):
        app = Mock()
        app.client.resolved_key.return_value = None
        with patch("terminal.setup.quick_setup", return_value=None) as wizard:
            self.assertTrue(ensure_setup(app, False))
            wizard.assert_not_called()
            self.assertFalse(ensure_setup(app, True))
        app.client.resolved_key.return_value = "test"
        with patch("terminal.setup.quick_setup") as wizard:
            self.assertTrue(ensure_setup(app, True))
            wizard.assert_not_called()
        app.client.resolved_key.return_value = None
        with patch("terminal.setup.quick_setup", return_value="new"):
            self.assertTrue(ensure_setup(app, True))
            app.apply_profiles.assert_called_once()

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
