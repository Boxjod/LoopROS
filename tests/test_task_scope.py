import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from core.tasks import TaskStore
from terminal.app import App
from terminal.config import load_config
from terminal.session_task import SessionTask


class TaskScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'LOOP_HOME': str(self.root / 'home'), 'LOOP_TASK_AUTOSTART': '0'})
        self.env.start()
        self.app = App(load_config(), self.root / 'state')
        self.store = TaskStore(self.app.state_dir / 'tasks.sqlite')

    def tearDown(self):
        self.app.close()
        self.env.stop()
        self.temp.cleanup()

    def test_submit_belongs_to_session_default_list_and_explicit_history(self):
        old = self.store.submit({'goal': 'legacy'})
        foreign = self.store.submit({'goal': 'foreign', 'session_id': 'another-session'})
        with patch('terminal.task_service.start', return_value={'process_alive': False}):
            own = self.app.tool('task_submit', {'goal': 'current'})['task']
            second = self.app.tool('task_submit', {'goal': 'second'})['task']
        self.assertEqual(own['session_id'], self.app.session_id)
        self.assertNotEqual(own['id'], self.app.session_id)
        self.assertNotEqual(second['id'], own['id'])
        self.assertEqual({t['id'] for t in self.app.tool('task_status', {})['task']}, {own['id'], second['id']})
        all_tasks = json.loads(self.app.dispatch('/tasks all'))['task']
        self.assertEqual({t['id'] for t in all_tasks}, {old['id'], foreign['id'], own['id'], second['id']})
        self.assertEqual(self.app.tool('task_status', {'task_id': old['id']})['task']['id'], old['id'])
        with self.assertRaises(ValueError):
            self.app.tool('task_submit', {'goal': 'spoof', 'session_id': 'another-session'})

    def test_notifications_filtered_before_limit_and_cursor_isolation(self):
        other = self.store.submit({'goal': 'other', 'session_id': 'other'})
        for _ in range(55):
            self.store.update(other['id'], 'waiting_input')
        own = self.store.submit({'goal': 'own', 'session_id': self.app.session_id})
        self.store.update(own['id'], 'waiting_input')
        events = self.store.notifications(session_id=self.app.session_id)
        self.assertEqual([e['task_id'] for e in events], [own['id']])
        self.assertEqual(self.store.notifications(events[-1]['id'], session_id=self.app.session_id), [])
        self.assertTrue(self.store.notifications(session_id='other'))

    def test_old_database_and_shared_task_identity_migrate_without_adoption(self):
        path = self.root / 'legacy.sqlite'
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY,spec TEXT,state TEXT,attempt INTEGER DEFAULT 0,due REAL,agent_id TEXT,feedback TEXT DEFAULT '{}',updated REAL)")
            db.execute("INSERT INTO tasks(id,spec,state) VALUES('legacy',?, 'waiting_input')", (json.dumps({'goal': 'keep me'}),))
        migrated = TaskStore(path)
        self.assertEqual(migrated.get('legacy')['spec']['goal'], 'keep me')
        self.assertIsNone(migrated.get('legacy')['session_id'])
        self.assertEqual(migrated.list(session_id=self.app.session_id), [])
        legacy_task = SessionTask().snapshot()
        legacy_task['id'] = 'old-session'
        converted = SessionTask(legacy_task, identity='old-session').snapshot()
        self.assertNotEqual(converted['id'], converted['session_id'])
        self.assertEqual(converted['id'], SessionTask(legacy_task, identity='old-session').snapshot()['id'])
        again = SessionTask(converted, identity='old-session').snapshot()
        self.assertEqual(converted['id'], again['id'])


class ScopeInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_and_resume_switch_task_scope_without_touching_old_work(self):
        from prompt_toolkit.application import create_app_session
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        from terminal.interactive import Terminal
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOOP_HOME': directory + '/home'}), create_pipe_input() as pipe:
            with create_app_session(input=pipe, output=DummyOutput()):
                app = App(load_config(), Path(directory) / 'state')
                ui = Terminal(app)
                try:
                    ui.checkpoint()
                    original_session = app.session_id
                    original_task = app.session_task.snapshot()['id']
                    job = ui.task_store.submit({'goal': 'first session task', 'session_id': original_session})
                    ui.select_task(1)
                    self.assertEqual(ui.selected_task, job['id'])
                    ui.input.text = '/new'
                    await ui.submit()
                    self.assertNotEqual(app.session_id, original_session)
                    self.assertNotEqual(app.session_task.snapshot()['id'], app.session_id)
                    ui.select_task()
                    self.assertIsNone(ui.selected_task)
                    self.assertNotIn(job['id'], ui.action_panel[1])
                    self.assertEqual(ui.task_store.get(job['id'])['state'], 'queued')
                    ui.input.text = '/resume ' + original_session
                    await ui.submit()
                    self.assertEqual(app.session_id, original_session)
                    self.assertEqual(app.session_task.snapshot()['id'], original_task)
                    ui.select_task(1)
                    self.assertEqual(ui.selected_task, job['id'])
                    self.assertFalse(ui.queue)
                finally:
                    ui.store.close()
                    app.close()
