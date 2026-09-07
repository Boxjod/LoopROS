"""Real spawned Agent workers with concurrent local HTTP and brokered peer messages."""
from types import SimpleNamespace
import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock

from loop_robot.terminal.agents import AgentRuntime
from loop_robot.terminal.llm import QwenClient


def request_worker(pipe, definition, config, key, task, schemas):
    if task == 'wait':
        time.sleep(20)
    else:
        pipe.send({'type': 'tool', **json.loads(task)})
        pipe.send({'type': 'result', 'result': json.dumps(pipe.recv())})
    pipe.close()


class AgentIPCTests(unittest.TestCase):
    def test_parallel_workers_discover_and_message_each_other(self):
        barrier = threading.Barrier(2)
        seen = set()
        calls = []
        errors = []
        guard = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    messages = data['messages']
                    identity = re.search(r'Runtime identity: ([a-f0-9]+)', messages[0]['content']).group(1)
                    with guard:
                        first = identity not in seen
                        seen.add(identity)
                        calls.append((identity, self.headers.get('Authorization'), data))
                    if first:
                        barrier.wait(timeout=8)  # Both independent model requests must be in flight.
                    results = [json.loads(m['content']) for m in messages if m['role'] == 'tool']
                    statuses = [r for r in results if 'self_id' in r]
                    sent = any(r.get('state') == 'queued' for r in results)
                    received = any(m['role'] == 'user' and 'peer-ping' in str(m['content']) for m in messages)
                    if sent and received:
                        message = {'content': 'Peer exchange complete for ' + identity}
                    else:
                        name, args = 'agents_status', {}
                        if statuses and not sent:
                            peers = [p for p in statuses[-1]['peers'] if p['agent_id'] != identity]
                            if peers:
                                name, args = 'send_agent', {'agent_id': peers[0]['agent_id'], 'message': 'peer-ping from ' + identity}
                        message = {'content': None, 'tool_calls': [{'id': 'call-' + str(len(results)), 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}
                    payload = json.dumps({'choices': [{'message': message}]}).encode()
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except Exception as exc:
                    errors.append(type(exc).__name__)
                    self.send_error(500)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                config = {'base_url': 'http://127.0.0.1:{}/v1'.format(server.server_port), 'model': 'local-test', 'protocol': 'openai', 'api_key_env': 'LOOP_IPC_TEST_KEY', 'timeout_s': 10}
                client = QwenClient(config)
                client.key = 'local-test-key'
                definitions = {role: {'provider': 'llm', 'tools': [], 'prompt': 'Role ' + role} for role in ('Planner', 'Reviewer')}
                runtime = AgentRuntime(definitions, {'llm': client}, [], Mock(), Path(directory) / 'events.jsonl')
                try:
                    ids = [runtime.spawn(role, 'Exchange peer messages and report completion')['agent_id'] for role in definitions]
                    self.assertEqual(len({runtime.records[i]['process'].pid for i in ids}), 2)
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline and any(runtime.result(i)['state'] == 'running' for i in ids):
                        runtime.poll()
                        time.sleep(.01)
                    self.assertEqual(errors, [])
                    self.assertEqual(seen, set(ids))
                    for identity in ids:
                        result = runtime.result(identity)
                        self.assertEqual(result['state'], 'done', result)
                        self.assertIn('Peer exchange complete', result['result'])
                        self.assertFalse(runtime.records[identity]['process'].is_alive())
                    events = [json.loads(line) for line in (Path(directory) / 'events.jsonl').read_text().splitlines()]
                    mail = [e for e in events if e['kind'] == 'message']
                    self.assertEqual({(e['sender'], e['agent_id']) for e in mail}, {(ids[0], ids[1]), (ids[1], ids[0])})
                    self.assertTrue(all(auth == 'Bearer local-test-key' for _, auth, _ in calls))
                    self.assertNotIn('local-test-key', (Path(directory) / 'events.jsonl').read_text())
                    self.assertEqual(len(runtime.inbox()), 2)
                    self.assertEqual(runtime.inbox(), [])
                    runtime.dispatch.assert_not_called()
                finally:
                    runtime.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_peer_result_read_uses_broker_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            client=SimpleNamespace(config={},resolved_key=lambda:'fixture')
            roles={'Planner':{'provider':'llm','tools':[],'prompt':'test'}}
            runtime=AgentRuntime(roles,{'llm':client},[],lambda *a:None,Path(directory)/'events.jsonl',worker_target=request_worker)
            try:
                peer=runtime.spawn('Planner','wait')['agent_id']
                runtime.cancel(peer)
                target=runtime.spawn('Planner',json.dumps({'name':'agent_result','arguments':{'agent_id':peer}}))['agent_id']
                deadline=time.monotonic()+5
                while runtime.result(target)['state']=='running' and time.monotonic()<deadline:
                    runtime.poll();time.sleep(.01)
                self.assertEqual(json.loads(runtime.result(target)['result'])['result']['state'],'cancelled')
                runtime.before_tool=lambda *args: (_ for _ in ()).throw(PermissionError('denied'))
                blocked=runtime.spawn('Planner',json.dumps({'name':'agent_result','arguments':{'agent_id':peer}}))['agent_id']
                deadline=time.monotonic()+5
                while runtime.result(blocked)['state']=='running' and time.monotonic()<deadline:
                    runtime.poll();time.sleep(.01)
                self.assertEqual(json.loads(runtime.result(blocked)['result'])['result']['error'],'PermissionError')
            finally: runtime.close()

    def test_sender_binding_permissions_and_no_recursive_spawn(self):
        from loop_robot.terminal.permissions import PermissionGate
        with tempfile.TemporaryDirectory() as directory:
            client = QwenClient({'base_url': 'http://127.0.0.1:1/v1', 'model': 'fixture', 'api_key_env': 'LOOP_IPC_TEST_KEY', 'timeout_s': 1})
            client.key = 'fixture'
            roles = {'Planner': {'provider': 'llm', 'tools': [], 'prompt': 'fixture'}}
            gate = PermissionGate(Path(directory) / 'permissions.sqlite')
            runtime = AgentRuntime(roles, {'llm': client}, [], Mock(), Path(directory) / 'events.jsonl', worker_target=request_worker)
            runtime.before_tool = lambda identity, name, args: gate.check(name, args)
            try:
                receiver = runtime.spawn('Planner', 'wait')['agent_id']
                cases = [({'name': 'send_agent', 'arguments': {'agent_id': receiver, 'message': 'spoof', 'sender': 'Master'}}, 'ValueError'),
                         ({'name': 'spawn_agent', 'arguments': {'role': 'Planner', 'task': 'nested'}}, 'ValueError'),
                         ({'name': 'cancel_agent', 'arguments': {'agent_id': receiver}}, 'ValueError')]
                for request, error in cases:
                    identity = runtime.spawn('Planner', json.dumps(request))['agent_id']
                    deadline = time.monotonic() + 5
                    while runtime.result(identity)['state'] == 'running' and time.monotonic() < deadline:
                        runtime.poll()
                        time.sleep(.01)
                    result = runtime.result(identity)
                    self.assertEqual(result['state'], 'done', result)
                    self.assertIn(error, result['result'])
                gate.set_rule('send_agent', 'deny')
                identity = runtime.spawn('Planner', json.dumps({'name': 'send_agent', 'arguments': {'agent_id': receiver, 'message': 'blocked'}}))['agent_id']
                deadline = time.monotonic() + 5
                while runtime.result(identity)['state'] == 'running' and time.monotonic() < deadline:
                    runtime.poll()
                    time.sleep(.01)
                self.assertIn('PermissionError', runtime.result(identity)['result'])
                self.assertEqual(runtime.records[receiver]['pending'], [])
                self.assertEqual(runtime.result(receiver)['state'], 'running')
                runtime.dispatch.assert_not_called()
            finally:
                runtime.close()
            self.assertTrue(all(not r['process'].is_alive() for r in runtime.records.values()))

    def test_app_dispatch_uses_same_permission_gate_for_parent_and_child(self):
        import os
        from unittest.mock import patch
        from loop_robot.terminal.app import App
        from loop_robot.terminal.config import load_config
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOOP_HOME': directory + '/home'}):
            app = App(load_config(), Path(directory) / 'state')
            app.runtime.worker_target = request_worker
            try:
                app.tool('load_toolset', {'name': 'agents'})
                identity = app.tool('spawn_agent', {'role': 'Planner', 'task': 'wait'})['agent_id']
                app.permissions.set_rule('send_agent', 'deny')
                with self.assertRaises(PermissionError):
                    app.tool('send_agent', {'agent_id': identity, 'message': 'blocked'})
                with self.assertRaises(PermissionError):
                    app.runtime.before_tool(identity, 'send_agent', {'agent_id': identity, 'message': 'blocked'})
                app.permissions.set_rule('send_agent', 'allow')
                with self.assertRaises(ValueError):
                    app.tool('send_agent', {'agent_id': identity, 'message': 'spoof', 'sender': 'Reviewer'})
                self.assertEqual(app.tool('send_agent', {'agent_id': identity, 'message': 'constraint'})['state'], 'queued')
                self.assertEqual(app.tool('agents_status', {})['running'], 1)
                self.assertEqual(app.tool('cancel_agent', {'agent_id': identity})['state'], 'cancelled')
                self.assertEqual(app.tool('agents_status', {})['running'], 0)
                app.permissions.set_mode('plan')
                with self.assertRaises(PermissionError):
                    app.tool('spawn_agent', {'role': 'Planner', 'task': 'blocked'})
            finally:
                app.close()
