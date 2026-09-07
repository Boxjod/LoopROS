import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from loop_robot.terminal.app import App
from loop_robot.terminal.config import ROOT, load_config
from loop_robot.terminal.instances import TerminalInstance, claim_node_resource
from loop_robot.terminal.session import SessionStore

CONFIG = {'base_url':'https://example.test', 'model':'test', 'protocol':'openai'}


class MultiTerminalTests(unittest.TestCase):
    def test_slots_reuse_only_after_release_and_real_cli_accepts_same_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)/'state'
            env = dict(os.environ, LOOP_HOME=directory+'/home', LOOP_TASK_AUTOSTART='0')
            with TerminalInstance(state) as first, TerminalInstance(state) as second:
                self.assertEqual(first.runtime_dir, state)
                self.assertEqual(second.runtime_dir, state/'terminals/2')
                self.assertTrue(first.others_active())
                result = subprocess.run([str(ROOT/'loop'), 'node', '--state-dir', str(state), '--once', '/permissions'],
                                        cwd=directory, env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn('Another terminal', result.stderr)
                self.assertTrue((state/'terminals/3/terminal.lock').exists())
            with TerminalInstance(state) as restarted:
                self.assertEqual(restarted.runtime_dir, state)
                self.assertFalse(restarted.others_active())

    def test_crashed_process_releases_runtime_and_conversation_locks(self):
        with tempfile.TemporaryDirectory() as directory:
            code = """
import sys
from pathlib import Path
from loop_robot.terminal.instances import TerminalInstance
from loop_robot.terminal.session import SessionStore
with TerminalInstance(sys.argv[1]):
    store = SessionStore(Path(sys.argv[1])/'conversation.sqlite', exclusive=True)
    store.save({'base_url':'https://example.test','model':'test','protocol':'openai'}, [], [])
    print(store.session_id, flush=True)
    sys.stdin.readline()
"""
            child = subprocess.Popen([sys.executable, '-c', code, directory], cwd=ROOT,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                identity = child.stdout.readline().strip()
                self.assertTrue(identity)
                store = SessionStore(Path(directory)/'conversation.sqlite', exclusive=True)
                try:
                    with self.assertRaisesRegex(ValueError, 'another terminal'):
                        store.resume(CONFIG, identity)
                    child.kill(); child.wait(timeout=5)
                    self.assertEqual(store.resume(CONFIG, identity)['session_id'], identity)
                    with TerminalInstance(directory) as instance:
                        self.assertEqual(instance.runtime_dir, Path(directory))
                finally:
                    store.close()
            finally:
                if child.poll() is None: child.kill()
                child.communicate(timeout=5)

    def test_shared_sessions_never_overwrite_or_mix_tool_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'conversation.sqlite'
            a, b = SessionStore(path, exclusive=True), SessionStore(path, exclusive=True)
            try:
                a.save(CONFIG, [{'role':'user','content':'窗口一'}], [], draft='草稿甲')
                first = a.session_id
                self.assertEqual(b.load(CONFIG), {})
                b.save(CONFIG, [{'role':'user','content':'窗口二'}], [], draft='草稿乙')
                second = b.session_id
                self.assertNotEqual(first, second)
                with self.assertRaisesRegex(ValueError, 'another terminal'):
                    b.resume(CONFIG, first)
                self.assertEqual(b.session_id, second)
                a.record('tool','read_file({"path":"first.txt"})')
                b.record('tool','read_file({"path":"second.txt"})')
                result_a = a.record('result','{"content":"甲"}')
                b.record('result','{"content":"乙"}')
                self.assertIn('first.txt', a.tool_details())
                self.assertNotIn('second.txt', a.tool_details(result_a))
                self.assertIn('second.txt', b.tool_details())
                self.assertEqual(a.read_session(CONFIG, first)['draft'], '草稿甲')
                self.assertEqual(a.read_session(CONFIG, second)['draft'], '草稿乙')
                a.close()
                self.assertEqual(b.resume(CONFIG, first)['history'][0]['content'], '窗口一')
            finally:
                a.close(); b.close()

    def test_app_shares_configuration_and_resources_but_isolates_runtime(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOOP_HOME':directory+'/home', 'LOOP_TASK_AUTOSTART':'0'}):
            state = Path(directory)/'state'
            with TerminalInstance(state) as first, TerminalInstance(state) as second:
                a = App(load_config(), state, runtime_dir=first.runtime_dir)
                b = App(load_config(), state, runtime_dir=second.runtime_dir)
                try:
                    a.scheduler.add(60, '/help')
                    self.assertEqual(b.scheduler.list(), [])
                    self.assertNotEqual(a.scene_dir, b.scene_dir)
                    self.assertNotEqual(a.nodes.directory, b.nodes.directory)
                    self.assertNotEqual(a.services.logs, b.services.logs)
                    self.assertEqual(a.resources.path, b.resources.path)
                    a.permissions.set_rule('run_python', 'deny')
                    self.assertEqual(b.permissions.snapshot()['rules']['run_python'], 'deny')
                    self.assertEqual(a.providers.selected(), b.providers.selected())
                    lease = claim_node_resource(state, 'process-profile:test')
                    try:
                        with self.assertRaisesRegex(ValueError, 'already owned'):
                            claim_node_resource(state, 'process-profile:test')
                    finally: lease.close()
                    lease = claim_node_resource(state, 'process-profile:test'); lease.close()
                    a.close()
                    self.assertEqual(b.dispatch('/help')[:8], 'Loop ROS')
                finally:
                    b.close()

    def test_owned_node_resource_is_released_after_stop_and_startup_failure(self):
        from loop_robot.core.nodes import NodeDefinition, NodeRuntime
        from test_nodes import HeartbeatNode, BrokenNode, validate, resource, wait_for
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            definitions = {'counter':NodeDefinition(HeartbeatNode, validate, resource),
                           'broken':NodeDefinition(BrokenNode, validate, resource)}
            claim = lambda value: claim_node_resource(root, value)
            a = NodeRuntime(definitions, root/'a', resource_claim=claim)
            b = NodeRuntime(definitions, root/'b', resource_claim=claim)
            try:
                config = {'resource':'process-profile:shared'}
                a.start('one', 'counter', config)
                wait_for(lambda: a.status('one')['state']=='running')
                with self.assertRaisesRegex(ValueError, 'already owned'):
                    b.start('two', 'counter', config)
                a.stop('one')
                b.start('two', 'counter', config)
                wait_for(lambda: b.status('two')['state']=='running')
                a.close()
                self.assertTrue(b.status('two')['process_alive'])
                b.stop('two')
                b.start('bad', 'broken', config)
                wait_for(lambda: b.records['bad']['reaped'])
                b.start('retry', 'counter', config)
                wait_for(lambda: b.status('retry')['state']=='running')
            finally:
                a.close(); b.close()
