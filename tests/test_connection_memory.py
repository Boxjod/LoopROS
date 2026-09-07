import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from loop_robot.terminal.connection_memory import fallback
from loop_robot.terminal.learning import Learning


class ConnectionMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.learning = Learning(Path(self.tmp.name) / 'learning.sqlite', lambda: 'scope')

    def result(self, host, connected=True, device='jetson'):
        return {'connection': {'device': device, 'host': host, 'transport': 'ssh',
                'username': 'jetson', 'port': 22, 'method': 'existing-key', 'connected': connected}}

    def record(self, identity, host, connected=True, check='connection.connected'):
        task = {'id': identity, 'attempt': 1, 'state': 'succeeded' if connected else 'waiting_input',
                'spec': {'goal': '检查 Jetson 连接', 'checks': [{'tool': 'observe', 'path': check, 'equals': True}]},
                'feedback': {'worker_state': 'done', 'receipts': [
                    {'tool': 'observe', 'arguments': {'host': host}, 'result': self.result(host, connected)}]}}
        return self.learning.record_task(task)

    def test_new_failure_preserves_latest_success_and_requires_agreement(self):
        self.record('old', '192.168.1.18')
        latest = self.record('latest', '192.168.1.19')
        self.record('failed', '192.168.19.1', False)
        suggestion = fallback(self.learning, self.result('192.168.19.1', False))
        self.assertEqual(suggestion['last_success']['config']['host'], '192.168.1.19')
        self.assertEqual(suggestion['last_success']['source'], latest)
        self.assertTrue(suggestion['user_confirmation_required'])
        self.assertFalse(suggestion['automatic_retry'])
        self.assertEqual(suggestion['failed_config']['host'], '192.168.19.1')
        self.assertIsNone(fallback(self.learning, self.result('192.168.1.19', False)))
        self.assertIsNone(fallback(self.learning, self.result('192.168.19.1', True)))
        self.record('new-success', '192.168.19.1')
        self.assertEqual(self.learning.layers.last_connection('scope', 'jetson', 'ssh')['config']['host'], '192.168.19.1')

    def test_replayed_old_result_cannot_become_latest(self):
        self.record('old', '192.168.1.18')
        self.record('new', '192.168.1.19')
        self.record('old', '192.168.1.18')
        self.assertEqual(self.learning.layers.last_connection('scope', 'jetson', 'ssh')['config']['host'], '192.168.1.19')

    def test_prose_exit_zero_and_unrelated_checks_do_not_verify(self):
        self.learning.record_turn({'request': '连接 Jetson', 'answer_excerpt': 'Connection successful'},
                                 [('tool', 'run_python({})'), ('result', '{"returncode":0,"stdout":"SSH success"}')])
        self.record('unrelated', '192.168.1.19', check='ok')
        self.assertIsNone(self.learning.layers.last_connection('scope', 'jetson', 'ssh'))
        self.assertIsNone(fallback(self.learning, self.result('192.168.19.1', False)))

    def test_device_scope_and_recall_permission_isolation(self):
        self.record('a', '192.168.1.19')
        self.assertIsNone(fallback(self.learning, self.result('192.168.19.1', False, device='other-robot')))
        other = Learning(self.learning.path, lambda: 'other')
        self.assertIsNone(fallback(other, self.result('192.168.19.1', False)))
        self.learning.can_recall = lambda: False
        self.assertIsNone(fallback(self.learning, self.result('192.168.19.1', False)))

    def test_foreground_nested_output_and_immediate_feedback(self):
        from loop_robot.terminal.app import App
        result = {'returncode': 0, 'output': self.result('192.168.1.19')}
        source = self.learning.record_turn({'request': '检查 Jetson'},
            [('tool', 'tool_run({"name":"probe"})'), ('result', json.dumps(result))], task_id='front',
            task={'goal': '检查 Jetson', 'state': 'complete',
                  'checks': [{'tool': 'tool_run', 'path': 'output.connection.connected', 'equals': True}]})
        failed = {'returncode': 0, 'output': self.result('192.168.19.1', False)}
        app = SimpleNamespace(learning=self.learning, session_task=Mock())
        App.observe_tool_result(app, 'tool_run', {}, failed)
        self.assertEqual(failed['memory_feedback']['last_success']['source'], source)
        self.assertFalse(failed['memory_feedback']['automatic_retry'])
        app.session_task.receipt.assert_called_once_with('tool_run', {}, failed)
        self.assertIn('192.168.1.19', self.learning.context('Jetson'))
