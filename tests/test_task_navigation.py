import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock
from terminal.interactive import Terminal


class TaskNavigationTests(unittest.TestCase):
    def test_unfinished_count_is_scoped_and_includes_waiting(self):
        from core.tasks import TaskStore
        with tempfile.TemporaryDirectory() as folder:
            store = TaskStore(Path(folder)/'tasks.sqlite')
            for state in ('queued','running','waiting_input','retry_wait','succeeded','cancelled'):
                task = store.submit({'goal':state,'session_id':'current'})
                store.update(task['id'],state)
            store.submit({'goal':'Other session','session_id':'other'})
            self.assertEqual(store.unfinished_count('current'),4)
            self.assertEqual(store.unfinished_count('empty'),0)
    def test_empty_task_alias_lists_without_submitting_or_starting_service(self):
        import json
        import tempfile
        from unittest.mock import patch
        from terminal.app import App
        from terminal.config import load_config
        from core.tasks import TaskStore
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'LOOP_HOME': directory + '/home'}):
            app = App(load_config(), directory + '/state')
            try:
                with patch('terminal.task_service.start') as start:
                    for command in ('/task', '/task   ', '/tasks'):
                        result = json.loads(app.dispatch(command))
                        self.assertEqual(result['task'], [])
                        self.assertEqual(result['scope'], 'session')
                    start.assert_not_called()
                self.assertEqual(TaskStore(app.state_dir / 'tasks.sqlite').list(), [])
                with patch.object(app, 'tool', return_value={'submitted': True}) as tool:
                    app.dispatch('/task 连接并核验 Jetson')
                    tool.assert_called_once_with('task_submit', {'goal': '连接并核验 Jetson'})
            finally:
                app.close()

    def terminal(self, tasks):
        terminal = Terminal.__new__(Terminal)
        from types import SimpleNamespace
        from terminal.session_task import SessionTask
        terminal.app = SimpleNamespace(session_id='current', session_task=SessionTask(identity='current'), client=SimpleNamespace(config={}))
        for task in tasks:
            task['session_id'] = 'current'
        terminal.ui = Mock()
        terminal.store = Mock()
        terminal.store.title.return_value = 'Current conversation'
        terminal.task_store = Mock()
        terminal.task_store.list.return_value = tasks
        terminal.task_store.get.side_effect = lambda identity: next(t for t in tasks if t['id'] == identity)
        terminal.action_panel = None
        terminal.viewer_choice = None
        terminal.selected_task = None
        terminal.task_buttons = []
        terminal.task_action = 0
        terminal.panel_offset = 0
        return terminal

    def test_single_task_returns_to_chat_in_both_directions(self):
        terminal = self.terminal([{'id': 'one', 'state': 'running', 'spec': {'goal': 'Task'}, 'feedback': {}}])
        for back in (-1, 1):
            terminal.select_task(1)
            self.assertEqual(terminal.selected_task, 'one')
            terminal.select_task(back)
            self.assertIsNone(terminal.selected_task)
            self.assertIsNone(terminal.action_panel)
            self.assertEqual(terminal.task_buttons, [])
        terminal.task_store.cancel.assert_not_called()

    def test_no_running_tasks_can_return_without_exiting(self):
        for back in (-1, 1):
            terminal = self.terminal([])
            terminal.select_task(1)
            self.assertIn('No unfinished background tasks in this session', terminal.action_panel[1])
            terminal.select_task(back)
            self.assertIsNone(terminal.action_panel)
            self.assertIsNone(terminal.selected_task)
            terminal.ui.exit.assert_not_called()
