import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from core.nodes import NodeRuntime
from toolchain.node_workers import definitions
from toolchain.process_node import read_profile, config


def wait_for(predicate):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.03)
    raise AssertionError('Process node did not reach expected state')


@unittest.skipUnless(os.name == 'posix', 'PTY requires POSIX')
class ProcessNodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'LOOP_HOME': str(self.root/'home'), 'EXAMPLE_CONTROL_TOKEN':'fixture-private-value', 'EXAMPLE_API_KEY':'unrelated-key'})
        self.env.start()
        (self.root/'home/processes').mkdir(parents=True)
        self.nodes = NodeRuntime(definitions(), self.root/'nodes')

    def tearDown(self):
        self.nodes.close()
        self.env.stop()
        self.tmp.cleanup()

    def profile(self, name, script, **extra):
        (self.root/'home/processes'/f'{name}.json').write_text(json.dumps({'argv':[sys.executable,'-u','-c',script], 'cwd':str(self.root), **extra}))
        return {'profile':name, 'expected_sha256':read_profile(name)['sha256']}

    def test_parallel_interactive_processes_and_owned_cleanup(self):
        for name in ('one','two'):
            spec = self.profile(name, 'print("READY", flush=True); print("ECHO=" + input(), flush=True); import time; time.sleep(60)')
            self.nodes.start(name, 'process', spec)
        for name in ('one','two'):
            wait_for(lambda: 'READY' in self.nodes.status(name)['snapshot'].get('output_tail',''))
        pids = [self.nodes.status(n)['snapshot']['pid'] for n in ('one','two')]
        request = self.nodes.command('one','send',{'text':'中文调试'})
        wait_for(lambda: any(r.get('command_id') == request['command_id'] for r in self.nodes.status('one')['results']))
        wait_for(lambda: 'ECHO=中文调试' in self.nodes.status('one')['snapshot'].get('output_tail',''))
        self.assertNotIn('中文调试', self.nodes.status('two')['snapshot']['output_tail'])
        for name, pid in zip(('one','two'),pids):
            self.assertFalse(self.nodes.stop(name)['process_alive'])
            with self.assertRaises(ProcessLookupError):
                os.kill(pid,0)

    def test_environment_redaction_and_exited_process_not_readiness(self):
        spec = self.profile('envcheck', 'import os; print(os.environ["EXAMPLE_CONTROL_TOKEN"]); print("NO_API=" + str("EXAMPLE_API_KEY" not in os.environ))', env_names=['EXAMPLE_CONTROL_TOKEN'])
        self.nodes.start('envcheck','process',spec)
        wait_for(lambda: self.nodes.status('envcheck')['snapshot'].get('process_state') == 'exited')
        snapshot = self.nodes.status('envcheck')['snapshot']
        self.assertIn('[redacted]',snapshot['output_tail'])
        self.assertIn('NO_API=True',snapshot['output_tail'])
        self.assertEqual(snapshot['readiness'],'not_verified')
        self.assertFalse(snapshot['model_polling'])
        self.nodes.stop('envcheck')
        self.assertNotIn('fixture-private-value', Path(self.nodes.status('envcheck')['output_log']).read_text())

    def test_profile_hash_resource_and_stop_recipe(self):
        spec = self.profile('service', 'import time; time.sleep(60)', stop_argv=[sys.executable,'-c', 'from pathlib import Path; Path("stopped").write_text("yes")'])
        with self.assertRaises(ValueError):
            config({**spec,'expected_sha256':'old'})
        self.nodes.start('service','process',spec)
        wait_for(lambda:self.nodes.status('service')['state']=='running')
        with self.assertRaises(ValueError):
            self.nodes.start('duplicate','process',spec)
        self.nodes.stop('service')
        self.assertEqual((self.root/'stopped').read_text(),'yes')

    def test_inline_credentials_rejected(self):
        with self.assertRaises(ValueError):
            self.profile('invalid','print(1)',env={'CONTROL_TOKEN':'private'})

    def test_app_permissions_and_revocation(self):
        from terminal.app import App
        from terminal.config import load_config
        spec = self.profile('gated', 'print("READY", flush=True); import time; time.sleep(60)')
        with patch.dict(os.environ, {'LOOP_TASK_AUTOSTART': '0'}):
            app = App(load_config(), self.root/'appstate')
        try:
            args = {'name': 'gated', 'kind': 'process', 'config': spec}
            with self.assertRaises(PermissionError):
                app.tool('node_start', args)
            app.permissions.set_rule('run_python', 'allow')
            app.tool('node_start', args)
            wait_for(lambda: app.nodes.status('gated')['state'] == 'running')
            self.assertTrue(app.nodes.status('gated')['process_alive'])
            app.permissions.set_rule('run_python', 'deny')
            app.enforce_node_permissions()
            self.assertFalse(app.nodes.status('gated')['process_alive'])
        finally:
            app.close()
