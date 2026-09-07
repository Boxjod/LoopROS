"""User overrides remain effective after copying home/state to another device."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from terminal.config import ROOT, load_config, user_config_file
from terminal.home import initialize, harness_prompt, save_key, saved_key
from terminal.skills import write, discover, read
from terminal.task_service import policy_path
from terminal.task_supervisor import load_policy
from terminal.agents import AgentRuntime
from terminal.providers import ProviderStore


class UserPortabilityTests(unittest.TestCase):
    def test_copy_home_and_state_preserves_customizations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home, state = root / 'old-home', root / 'old-state'
            with patch.dict(os.environ, {'LOOP_HOME': str(home)}):
                initialize()
                (home / 'config.json').write_text('{"llm":{"model":"portable-model"}}')
                (home / 'AGENTS.md').write_text('Portable user instructions')
                (home / 'harness/style.md').write_text('Concise replies')
                write(home / 'skills', 'portable-skill', 'Portable fixture', 'Read references/note.md')
                references = home / 'skills/portable-skill/references'
                references.mkdir()
                (references / 'note.md').write_text('Portable supporting file')
                roles = {'Portable': {'provider': 'llm', 'tools': [], 'prompt': 'User role'}}
                (home / 'agents.json').write_text(json.dumps(roles))
                shutil.copy2(ROOT / 'configs/task_runtime.json', home / 'task_runtime.json')
                config = load_config(root / 'no-project-config')
                save_key(config['llm'], 'fixture-key')
                store = ProviderStore(state / 'providers.sqlite', config)
                store.save('portable', config['llm'])
                store.use('master', 'portable')
                store.close()
            shutil.copytree(home, root / 'new-home')
            shutil.copytree(state, root / 'new-state')
            with patch.dict(os.environ, {'LOOP_HOME': str(root / 'new-home')}):
                config = load_config(root / 'no-project-config')
                self.assertEqual(config['llm']['model'], 'portable-model')
                self.assertIn('Concise replies', harness_prompt())
                self.assertEqual(discover(root / 'new-home/skills')[0]['name'], 'portable-skill')
                self.assertIn('references/note.md', read(root / 'new-home/skills', 'portable-skill'))
                self.assertTrue((root / 'new-home/skills/portable-skill/references/note.md').is_file())
                self.assertEqual(AgentRuntime.load_definitions(user_config_file('agents.json'), set()), roles)
                self.assertEqual(policy_path(root / 'new-state'), root / 'new-home/task_runtime.json')
                self.assertEqual(saved_key(config['llm']), 'fixture-key')
                self.assertIsNone(saved_key(dict(config['llm'], base_url='https://other.invalid/v1')))
                store = ProviderStore(root / 'new-state/providers.sqlite', config)
                self.assertEqual(store.selected()['master'], 'portable')
                store.close()
                from terminal.app import App
                app = App(config, root / 'new-state')
                try:
                    self.assertEqual(app.runtime.definitions, roles)
                    self.assertEqual(app.providers.selected()['master'], 'portable')
                finally:
                    app.close()

    def test_precedence_and_invalid_user_policy_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOOP_HOME': directory}):
            home = Path(directory)
            self.assertEqual(user_config_file('agents.json'), ROOT / 'configs/agents.json')
            self.assertEqual(policy_path(home / 'state'), ROOT / 'configs/task_runtime.json')
            (home / 'task_runtime.json').write_text('{}')
            with self.assertRaises(ValueError):
                load_policy(policy_path(home / 'state'), set())
            (home / 'state').mkdir()
            (home / 'state/task_runtime.json').write_text('{}')
            self.assertEqual(policy_path(home / 'state'), home / 'state/task_runtime.json')
            with self.assertRaises(ValueError):
                user_config_file('../credentials.json')
