"""Real terminal startup recovers from an HTTP authentication failure."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from terminal.config import ROOT


@unittest.skipUnless(os.name == 'posix', 'PTY test requires POSIX')
class StartupSetupTests(unittest.TestCase):
    def test_failed_key_opens_setup_and_rechecks_new_protocol(self):
        import pty
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append((self.path, self.headers.get('Authorization'), body))
                if self.headers.get('Authorization') == 'Bearer startup-invalid-key':
                    self.send_response(401)
                    payload = {'error': 'private response body must not be printed'}
                else:
                    self.send_response(200)
                    payload = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'OK'}]}]}
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                home = Path(directory) / 'home'
                home.mkdir()
                url = 'http://127.0.0.1:{}/v1'.format(server.server_port)
                (home / 'config.json').write_text(json.dumps({'llm': {'base_url': url, 'model': 'old-model', 'protocol': 'openai', 'api_key_env': 'LOOP_STARTUP_TEST_KEY'}}))
                master, slave = pty.openpty()
                process = subprocess.Popen([sys.executable, str(ROOT / '__main__.py'), '--state-dir', directory + '/state'],
                    stdin=slave, stdout=slave, stderr=slave, cwd=directory,
                    env=dict(os.environ, TERM='xterm-256color', LOOP_HOME=str(home), LOOP_STARTUP_TEST_KEY='startup-invalid-key', PROMPT_TOOLKIT_NO_CPR='1'))
                os.close(slave)
                output = bytearray()
                cursor = 0

                def expect(needle):
                    nonlocal cursor
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        index = output.find(needle, cursor)
                        if index >= 0:
                            cursor = index + len(needle)
                            return
                        if select.select([master], [], [], .1)[0]:
                            try:
                                data = os.read(master, 65536)
                            except OSError:
                                break
                            if not data:
                                break
                            output.extend(data)
                    self.fail('Missing terminal prompt: ' + repr(needle))

                try:
                    expect(b'Model connection failed')
                    expect(b'Provider number or API base URL')
                    os.write(master, (url + '/responses\n').encode())
                    expect(b'API type [2]')
                    os.write(master, b'2\n')
                    expect(b'API key (hidden; Enter to cancel): ')
                    os.write(master, b'startup-new-key\n')
                    expect(b'Model ID [auto-discover]: ')
                    os.write(master, b'new-model\n')
                    expect(b'Model connected.')
                    # Exit through the terminal after the startup gate succeeds.
                    expect('❯'.encode())
                    os.write(master, b'/exit\r')
                    expect(b'Session saved:')
                    process.wait(timeout=15)
                    self.assertEqual(process.returncode, 0)
                    self.assertNotIn(b'startup-new-key', output)
                    self.assertNotIn(b'private response body', output)
                    self.assertEqual([item[0] for item in requests], ['/v1/chat/completions', '/v1/responses'])
                    self.assertEqual(requests[1][1], 'Bearer startup-new-key')
                    self.assertEqual(requests[1][2]['model'], 'new-model')
                    self.assertTrue(all('tools' not in item[2] for item in requests))
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                    os.close(master)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
