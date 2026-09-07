import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from loop_robot.terminal.home import initialize, save_key, saved_key, harness_prompt, looper_home
from loop_robot.terminal.config import load_config
from loop_robot.terminal.app import App


class HomeTests(unittest.TestCase):
    def test_migrate_keys_to_url_config_without_losing_other_keys(self):
        import json
        from loop_robot.terminal.home import credential_id
        root = initialize()
        first = {'base_url':'https://first.test/v1','api_key_env':'API_KEY'}
        second = {**first,'base_url':'https://second.test/v1'}
        (root/'config.json').write_text(json.dumps({'llm':{'model':'unchanged'}}))
        old = root/'credentials.json'
        old.write_text(json.dumps({credential_id(first):'test-first',credential_id(second):'test-second'}))
        old.chmod(0o600)
        self.assertEqual(saved_key(first),'test-first')
        self.assertFalse(old.exists())
        self.assertEqual(saved_key(second),'test-second')
        self.assertIsNone(saved_key({**first,'base_url':'https://unknown.test'}))
        data = json.loads((root/'config.json').read_text())
        self.assertEqual(data['llm']['model'],'unchanged')
        self.assertEqual({e['base_url'] for e in data['endpoints']},{first['base_url'],second['base_url']})
        self.assertNotIn('endpoints',load_config(root/'absent'))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"LOOPER_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_layout_and_endpoint_binding(self):
        root = initialize()
        self.assertEqual(looper_home(), Path(self.tmp.name))
        self.assertTrue((root / "skills").is_dir())
        config = load_config()["llm"]
        save_key(config, "test-only-secret")
        self.assertEqual(saved_key(config), "test-only-secret")
        self.assertIsNone(saved_key(dict(config, base_url="https://other.example/v1")))
        if os.name != "nt":
            self.assertEqual((root / "config.json").stat().st_mode & 0o777, 0o600)

    def test_global_config_harness_and_save_command(self):
        root = initialize()
        (root / "config.json").write_text('{"llm":{"model":"test-model"}}')
        (root / "AGENTS.md").write_text("Be concise.")
        (root / "harness" / "robot.md").write_text("Confirm calibration.")
        self.assertIn("Confirm calibration.", harness_prompt())
        config = load_config(root / "missing")
        self.assertEqual(config["llm"]["model"], "test-model")
        app = App(config, root / "state")
        try:
            self.assertIn("Be concise.", app.agent.context_provider('hello')['system_prompt'])
            with patch("loop_robot.terminal.app.getpass.getpass", return_value="test-only"):
                self.assertIn("saved", app.dispatch("/key save"))
            self.assertEqual(saved_key(app.client.config), "test-only")
            with self.assertRaises(ValueError):
                app.dispatch("/key accidental-secret")
        finally:
            app.close()

    def test_harness_budget(self):
        root = initialize()
        (root / "AGENTS.md").write_text("x" * 24001)
        with self.assertRaises(ValueError):
            harness_prompt()
