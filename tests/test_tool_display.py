import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from loop_robot.terminal.session import SessionStore
from loop_robot.terminal.tool_display import ToolDisplay


class ToolDisplayTests(unittest.TestCase):
    def test_python_shows_output_and_exit_without_claiming_goal_success(self):
        display = ToolDisplay()
        display.call('run_python({"path":"probe.py"})')
        summary = display.result(json.dumps({'executed': True, 'returncode': 1,
            'stdout': '已收到 3 帧\n', 'stderr': 'Traceback\nConnection failed\n'}), 42)
        self.assertIn('Process exit: 1', summary)
        self.assertEqual(display.preview, ['已收到 3 帧', 'stderr: Traceback', 'stderr: Connection failed'])
        self.assertNotIn('Executed: command', summary)
        display.call('run_python({"path":"probe.py"})')
        display.result(json.dumps({'executed': True, 'returncode': 0, 'stdout': '\n'.join(str(i) for i in range(30))}), 43)
        self.assertEqual(len(display.preview), 7)
        self.assertIn('/details 43', display.preview[-1])

    def test_registering_work_is_pending_not_execution_failure(self):
        display = ToolDisplay(); display.call('session_task_update({"state":"active"})')
        summary = display.result(json.dumps({'state': 'active', 'review': {'verdict': 'fail'}}), 1)
        self.assertIn('acceptance pending', summary)
        self.assertNotIn('fail', summary)

    def test_compact_summary_and_persisted_expansion_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'conversation.sqlite'
            store = SessionStore(path)
            call = 'web_weather({"location":"天津","days":1})'
            raw = json.dumps({'current': {'temperature_2m': 26.7}, 'large': 'raw-data-'*2000})
            store.record('tool', call)
            event_id = store.record('result', raw)
            display = ToolDisplay()
            with patch('loop_robot.terminal.tool_display.time.monotonic', side_effect=[10, 24]):
                self.assertEqual(display.call(call), 'Weather("天津")')
                summary = display.result(raw, event_id)
            self.assertIn('14.0s', summary)
            self.assertNotIn('raw-data', summary)
            self.assertLess(len(summary), 100)
            store.close()
            store = SessionStore(path)
            try:
                details = store.tool_details(event_id)
                self.assertIn(call, details)
                self.assertIn('raw-data-'*2000, details)
                self.assertEqual(details, store.tool_details())
                with self.assertRaises(ValueError):
                    store.tool_details(event_id + 100)
                # A result without a new tool call must not inherit the previous call.
                isolated = store.record('result', '{}')
                self.assertNotIn('web_weather', store.tool_details(isolated))
            finally:
                store.close()

    def test_failures_and_pending_actions_are_not_hidden_as_success(self):
        display = ToolDisplay()
        for data, expected in [({'error': 'Timeout', 'message': 'Service unavailable'}, 'Service unavailable'),
                               ({'review': {'verdict': 'fail', 'reason': 'target not reached'}}, 'fail'),
                               ({'review': {'verdict': 'inconclusive'}}, 'inconclusive'),
                               ({'window_open': False}, 'Window not confirmed'),
                               ({'state': 'queued'}, 'queued'), ({'locations': []}, 'No matching location')]:
            self.assertIn(expected, display.result(json.dumps(data), 1))
        display.call('web_search({"query":"Jetson specifications"})')
        self.assertIn('1 search · 2 results', display.result('{"results":[{},{}]}', 2))
        self.assertLess(len(display.call('tool({"payload":"' + 'x'*5000 + '"})')), 100)
