"""Startup capability evidence from actual HTTP responses, without paid API calls."""
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch

from loop_robot.terminal.llm import QwenClient, ModelAPIError
from loop_robot.terminal.setup import check_connection, ensure_setup
from loop_robot.terminal.ui import welcome


class FastStartupTests(unittest.TestCase):
    def test_http_evidence_and_normal_requests_remain_unchanged(self):
        requests = []
        scenario = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append((self.path, body, self.headers.get('Authorization')))
                fast = body.get('service_tier') == 'priority'
                rejected = fast and scenario.get('reject')
                self.send_response(400 if rejected else 200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                if rejected:
                    payload = {'error': 'private gateway text'}
                elif self.path.endswith('/responses'):
                    payload = {'status': 'completed', 'output': [
                        {'type': 'message', 'content': [{'type': 'output_text', 'text': 'OK'}]}]}
                else:
                    payload = {'choices': [{'message': {'role': 'assistant', 'content': 'OK'}}]}
                tier = scenario.get('fast' if fast else 'normal')
                if tier is not None:
                    payload['service_tier'] = tier
                self.wfile.write(json.dumps(payload).encode())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        cases = [({'normal': 'priority'}, 'active', 1),
                 ({'normal': 'fast'}, 'active', 1),
                 ({'normal': 'default', 'fast': 'priority'}, 'available', 2),
                 ({'fast': 'fast'}, 'available', 2),
                 ({'fast': 'default'}, 'unknown', 2),
                 ({}, 'unknown', 2),
                 ({'fast': 'private\x1b[31m'}, 'unknown', 2),
                 ({'reject': True}, 'unknown', 2)]
        try:
            for protocol in ('openai', 'openai-responses'):
                for spec, status, count in cases:
                    with self.subTest(protocol=protocol, spec=spec):
                        scenario.clear()
                        scenario.update(spec)
                        requests.clear()
                        config = {'base_url': 'http://127.0.0.1:{}/v1'.format(server.server_port),
                                  'model': 'fixture', 'api_key_env': 'LOOP_FAST_TEST_KEY',
                                  'protocol': protocol, 'timeout_s': 30}
                        client = QwenClient(dict(config))
                        client.key = 'test-key-never-print'
                        app = SimpleNamespace(client=client, providers=Mock())
                        with patch('sys.stdout', new_callable=io.StringIO) as output, patch('loop_robot.terminal.setup.quick_setup') as setup:
                            self.assertTrue(ensure_setup(app, True))
                            setup.assert_not_called()
                        self.assertEqual(app.startup_fast_status, status)
                        self.assertEqual(len(requests), count)
                        self.assertEqual(client.config, config)
                        self.assertNotIn('private', output.getvalue())
                        self.assertNotIn(client.key, output.getvalue())
                        self.assertNotIn('service_tier', requests[0][1])
                        if count == 2:
                            self.assertEqual(requests[1][1]['service_tier'], 'priority')
                        self.assertTrue(all('tools' not in body for _, body, _ in requests))
                        self.assertTrue(all(auth == 'Bearer ' + client.key for _, _, auth in requests))
                        endpoint = '/v1/responses' if protocol == 'openai-responses' else '/v1/chat/completions'
                        self.assertTrue(all(path == endpoint for path, _, _ in requests))
                        client.complete([{'role': 'user', 'content': 'Normal conversation'}], [])
                        self.assertNotIn('service_tier', requests[-1][1])
                scenario.clear()
                scenario.update({'fast': 'priority', 'normal': 'default'})
                client.request_service_tier = 'priority'
                client.complete([{'role':'user','content':'Fast request'}], [])
                self.assertEqual(requests[-1][1]['service_tier'], 'priority')
                self.assertEqual(client.last_service_tier, 'priority')
                client.request_service_tier = 'default'
                client.complete([{'role':'user','content':'Standard request'}], [])
                self.assertEqual(requests[-1][1]['service_tier'], 'default')
                self.assertEqual(client.last_service_tier, 'default')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_optional_timeout_does_not_fail_startup_or_change_config(self):
        client = QwenClient({'timeout_s': 30})
        client.key = 'test-key'
        timeouts = []

        def complete(probe, *args, **kwargs):
            timeouts.append(probe.config['timeout_s'])
            if kwargs.get('service_tier'):
                raise ModelAPIError('Model API timed out')
            return {'content': 'OK'}

        with patch.object(QwenClient, 'complete', complete), patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(check_connection(client), 'unknown')
        self.assertEqual(timeouts, [30, 10])
        self.assertEqual(client.config, {'timeout_s': 30})

    def test_noninteractive_skips_probes_and_stale_status(self):
        app = SimpleNamespace(startup_fast_status='active')
        with patch('loop_robot.terminal.setup.check_connection') as probe:
            self.assertTrue(ensure_setup(app, False))
            probe.assert_not_called()
        self.assertIsNone(app.startup_fast_status)

    def test_banner_uses_only_verified_status_labels(self):
        for width in (16, 40, 100):
            for status, label in [('available', 'available (probe only)'),
                                  ('active', 'active (provider default)'),
                                  ('unknown', 'not confirmed')]:
                banner = welcome('fixture', 'fixture', 'plan', width=width, fast_status=status)
                self.assertIn('Fast · ' + label, banner)
                self.assertIn('Ready.', banner)
            self.assertNotIn('Fast ·', welcome('fixture', 'fixture', 'plan', width=width))
