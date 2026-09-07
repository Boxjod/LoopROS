import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from loop_robot.core.tasks import TaskStore
from loop_robot.terminal.home import save_key, saved_key
from loop_robot.terminal.llm import QwenClient
from loop_robot.terminal.task_service import refresh_model


class SharedTaskCredentialsTests(unittest.TestCase):
    def test_refresh_rotation_and_endpoint_isolation(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, LOOP_HOME=folder):
            first = dict(base_url='https://one.invalid/v1', model='fixture', api_key_env='SHARED_TEST_KEY', timeout_s=10)
            second = {**first, 'base_url': 'https://two.invalid/v1'}
            selected = [first]
            providers = SimpleNamespace(selected=lambda: {'master': 'current'}, get=lambda name: dict(selected[0]))
            app = SimpleNamespace(client=QwenClient(first), providers=providers)
            supervisor = SimpleNamespace(running={}, provider=None)
            store = TaskStore(Path(folder)/'tasks.sqlite')
            task = store.submit({'goal': 'Existing operation'})
            store.update(task['id'], 'waiting_input', {'reason': 'Model credentials unavailable; configure the current provider and resume the task'})
            save_key(first, 'fixture-first')
            self.assertTrue(refresh_model(app, supervisor, store))
            self.assertEqual(store.get(task['id'])['state'], 'waiting_input')
            self.assertTrue(store.get(task['id'])['feedback']['credential_restored'])
            self.assertEqual(app.client.key, 'fixture-first')
            save_key(first, 'fixture-rotated')
            self.assertTrue(refresh_model(app, supervisor, store))
            self.assertEqual(app.client.key, 'fixture-rotated')
            selected[0] = second
            with patch.dict(os.environ, SHARED_TEST_KEY='old-endpoint-environment'):
                self.assertFalse(refresh_model(app, supervisor, store))
            self.assertIsNone(app.client.key)
            self.assertNotIn('fixture', str(store.meta('model_credentials').get('source')))
            self.assertNotIn('fixture-rotated', store.path.read_bytes().decode(errors='ignore'))
            save_key(second, 'fixture-second')
            self.assertTrue(refresh_model(app, supervisor, store))
            self.assertEqual(app.client.resolved_key(), 'fixture-second')

    def test_active_worker_keeps_its_profile_until_idle(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, LOOP_HOME=folder):
            first = dict(base_url='https://one.invalid/v1', model='first', api_key_env='TEST_KEY', timeout_s=10)
            second = {**first, 'model': 'second'}
            app = SimpleNamespace(client=QwenClient(first), providers=SimpleNamespace(
                selected=lambda: {'master': 'new'}, get=lambda name: second))
            app.client.key = 'fixture-key'
            supervisor = SimpleNamespace(running={'worker': {}}, provider=None)
            self.assertTrue(refresh_model(app, supervisor, TaskStore(Path(folder)/'tasks.sqlite')))
            self.assertEqual(app.client.config['model'], 'first')

    def test_key_command_saves_one_shared_credential(self):
        from loop_robot.terminal.app import App
        from loop_robot.terminal.config import load_config
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, LOOP_HOME=folder+'/home', LOOP_TASK_AUTOSTART='0'):
            app = App(load_config(), Path(folder)/'state')
            try:
                with patch('loop_robot.terminal.app.getpass.getpass', return_value='fixture-key'):
                    result = app.dispatch('/key')
                self.assertIn('shared by chat, agents and tasks', result)
                self.assertEqual(saved_key(app.client.config), 'fixture-key')
                with patch.dict(os.environ, {app.client.config['api_key_env']: 'stale-environment'}):
                    self.assertEqual(app.client.resolved_key(), 'fixture-key')
                self.assertIsNone(app.client.key)
                self.assertEqual((Path(folder)/'home/config.json').stat().st_mode & 0o777, 0o600)
            finally:
                app.close()
