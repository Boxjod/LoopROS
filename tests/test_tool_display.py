import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terminal.session import SessionStore
from terminal.tool_display import ToolDisplay


class ToolDisplayTests(unittest.TestCase):
    def test_compact_summary_and_persisted_expansion_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'conversation.sqlite'
            store = SessionStore(path)
            call = 'web_weather({"location":"天津","days":1})'
            raw = json.dumps({'current': {'temperature_2m': 26.7}, 'large': 'raw-data-'*2000})
            store.record('tool', call)
            event_id = store.record('result', raw)
            display = ToolDisplay()
            with patch('terminal.tool_display.time.monotonic', side_effect=[10, 24]):
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
