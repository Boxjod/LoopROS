import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terminal.app import App
from terminal.config import load_config, validate_provider
from terminal.providers import ProviderStore, choose_profile


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = load_config()
        self.path = Path(self.temp.name) / "providers.sqlite"
        self.store = ProviderStore(self.path, self.config)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_add_edit_and_persistent_selection(self):
        spec = {**self.config["llm"], "model": "my-model"}
        self.store.save("my-model", spec)
        self.store.use("master", "my-model")
        with self.assertRaises(ValueError):
            self.store.save("my-model", spec)
        self.store.save("my-model", {**spec, "model": "updated"}, replace=True)
        other = ProviderStore(self.path, self.config)
        try:
            self.assertEqual(other.selected()["master"], "my-model")
            self.assertEqual(other.get("my-model")["model"], "updated")
            self.assertEqual(other.selected()["expert"], "my-model")
        finally:
            other.close()

    def test_advice_and_legacy_key_share_current_client(self):
        app = App(copy.deepcopy(self.config), self.temp.name)
        try:
            with patch('terminal.app.getpass.getpass', return_value='session-secret'):
                app.dispatch('/expert-key')
            self.assertEqual(app.client.key, 'session-secret')
            with patch.object(app.client, 'complete', return_value={'content': 'analysis'}) as request:
                result = app.tool('expert_advice', {'description': '复杂规划'})
            request.assert_called_once()
            self.assertEqual(result['model'], app.client.config['model'])
            app.dispatch('/model qwen-custom')
            self.assertEqual(app.expert.config['model'], 'qwen-custom')
        finally:
            app.close()

    def test_legacy_selection_migrates_without_deleting_profiles(self):
        self.store.db.execute("UPDATE selection SET name='default-expert' WHERE slot='expert'")
        self.store.db.commit()
        other = ProviderStore(self.path, self.config)
        try:
            self.assertEqual(other.selected()['expert'], other.selected()['master'])
            self.assertIsInstance(other.get('default-expert'), dict)
            other.use('expert', 'default-expert')
            self.assertEqual(other.selected()['master'], 'default-expert')
        finally:
            other.close()

    def test_remove_active_and_unknown_switch(self):
        with self.assertRaises(ValueError):
            self.store.remove("default-master")
        with self.assertRaises(ValueError):
            self.store.use("master", "missing")
        self.assertEqual(self.store.selected()["master"], "default-master")
        self.store.save("unused", self.config["llm"])
        self.store.remove("unused")
        with self.assertRaises(ValueError):
            self.store.get("unused")

    def test_no_inline_credentials_or_insecure_endpoint(self):
        for changes in ({"api_key": "secret"}, {"base_url": "https://user:secret@example.com/v1"},
                        {"base_url": "http://example.com/v1"}, {"api_key_env": "sk-actual-key"},
                        {"base_url": "https://example.com/v1?key=secret"}, {"timeout_s": float("nan")}):
            with self.assertRaises(ValueError):
                validate_provider({**self.config["llm"], **changes})

    def test_numbered_picker(self):
        lines = []
        name = choose_profile(self.store, "master", read=lambda prompt: "1", write=lines.append)
        self.assertEqual(self.store.selected()["master"], name)
        self.assertTrue(lines)
        self.assertIsNone(choose_profile(self.store, read=lambda prompt: "", write=lambda line: None))

    def test_switch_clears_context_and_separates_keys(self):
        app = App(copy.deepcopy(self.config), self.temp.name)
        try:
            self.assertIs(app.expert, app.client)
            app.client.key = "test-secret"
            app.agent.history = [{"role": "user", "content": "old private context"}]
            app.providers.save("other", {**self.config["llm"], "base_url": "https://example.com/v1"})
            app.switch_profile("master", "other")
            self.assertIsNone(app.client.key)
            self.assertEqual(app.agent.history, [])
            app.switch_profile("master", "default-master")
            self.assertEqual(app.client.key, "test-secret")
            self.assertNotIn("test-secret", json.dumps(app.providers.list()))
            app.runtime.records["fake"] = {"state": "running"}
            with self.assertRaises(ValueError):
                app.switch_profile("expert", "other")
            app.runtime.records.clear()
            self.assertEqual(app.providers.selected()["expert"], "default-master")
        finally:
            app.runtime.records.clear()
            app.close()


if __name__ == "__main__":
    unittest.main()
