import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from loop_robot.core.processes import request
from loop_robot.toolchain.process_control import main, process
from loop_robot.terminal.process_control import run
from loop_robot.core.resources import ResourceManager


@unittest.skipUnless(sys.platform.startswith('linux') and hasattr(os, 'pidfd_open'), 'Linux pidfd required')
class ProcessControlTests(unittest.TestCase):
    def setUp(self):
        self.child = subprocess.Popen([sys.executable, '-u', '-c',
            'import socket,signal,time; signal.signal(signal.SIGINT,signal.SIG_IGN); '
            's=socket.socket();s.bind(("127.0.0.1",0));s.listen(); '
            'data=bytearray(8*1024*1024); print(s.getsockname()[1],flush=True);time.sleep(60)'],
            stdout=subprocess.PIPE, text=True)
        self.port = int(self.child.stdout.readline())

    def tearDown(self):
        if self.child.poll() is None:
            self.child.kill()
        self.child.wait(); self.child.stdout.close()

    def inspect(self):
        return main(request('inspect', {'ports': [self.port]}))

    def test_port_identity_memory_and_explicit_force(self):
        report = self.inspect()
        self.assertEqual(report['ports'][str(self.port)]['pids'], [self.child.pid])
        target = report['processes'][0]['identity']
        self.assertGreater(report['processes'][0]['rss_mb'], 8)
        self.assertGreater(report['memory']['available_ram_mb'], 0)
        first = main(request('stop', {'targets': [target], 'ports': [self.port], 'wait_s': .1}))
        self.assertFalse(first['success'])
        second = main(request('stop', {'targets': [target], 'ports': [self.port], 'mode': 'kill', 'wait_s': .3}))
        self.assertTrue(second['success'])
        self.assertEqual([s['signal'] for s in second['signals']], ['SIGKILL'])
        self.child.wait(timeout=2)

    def test_identity_mismatch_signals_nothing_and_escalation_is_bounded(self):
        target = process(self.child.pid)['identity']
        with self.assertRaisesRegex(ValueError, 'PID reused'):
            main(request('stop', {'targets': [{**target, 'start_ticks': target['start_ticks']+1}], 'mode':'kill'}))
        self.assertIsNone(self.child.poll())
        result = main(request('stop', {'targets':[target], 'ports':[self.port], 'mode':'escalate', 'wait_s':.1}))
        self.assertTrue(result['success'])
        self.assertEqual([s['signal'] for s in result['signals']], ['SIGINT','SIGTERM'])

    def test_does_not_kill_unselected_listener_or_claim_port_free(self):
        target = process(self.child.pid)['identity']
        other = socket.socket(); other.bind(('127.0.0.1',0)); other.listen()
        try:
            result = main(request('stop', {'targets':[target], 'ports':[other.getsockname()[1]], 'mode':'kill','wait_s':.2}))
            self.assertTrue(result['processes_stopped'])
            self.assertFalse(result['ports_released'])
            self.assertFalse(result['success'])
        finally:
            other.close()

    def test_broker_uses_resource_lease_and_permission_before_signal(self):
        with tempfile.TemporaryDirectory() as folder:
            monitor = Mock(); monitor.sample.return_value = {'available_ram_mb':65536,'cpu_percent':0,'cpu_cores':8,'gpus':[],'errors':[]}
            resources = ResourceManager(Path(folder)/'resources.sqlite', monitor=monitor)
            app = SimpleNamespace(resources=resources, permissions=Mock(), stop_event=threading.Event())
            result = run(app, 'process_inspect', {'ports':[self.port]})
            target = result['processes'][0]['identity']
            app.permissions.check.side_effect = PermissionError('denied')
            with self.assertRaises(PermissionError):
                run(app,'process_stop',{'targets':[target],'mode':'kill'})
            self.assertIsNone(self.child.poll())
            app.permissions.check.side_effect = None
            result = run(app,'process_stop',{'targets':[target],'ports':[self.port],'mode':'kill','wait_s':.2})
            self.assertTrue(result['success'])
            self.assertIn('resource_scope', result)
            with resources._db() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM leases').fetchone()[0],0)

    def test_pressure_does_not_block_recovery_and_ssh_uses_same_adapter(self):
        with tempfile.TemporaryDirectory() as folder:
            monitor = Mock(); monitor.sample.return_value = {'available_ram_mb':0,'cpu_percent':100,'cpu_cores':1,'gpus':[],'errors':[]}
            resources = ResourceManager(Path(folder)/'resources.sqlite', monitor=monitor)
            app = SimpleNamespace(resources=resources, permissions=Mock(), stop_event=threading.Event())
            actual_popen = subprocess.Popen
            calls = []
            def ssh_fixture(argv, **kwargs):
                calls.append(argv)
                return actual_popen([sys.executable, '-'], **kwargs)
            with patch('loop_robot.terminal.process_control.subprocess.Popen', side_effect=ssh_fixture):
                result = run(app,'process_inspect',{'host':'user@test-host','ports':[self.port]})
            self.assertEqual(calls[0][-2:], ['user@test-host', 'python3 -'])
            self.assertEqual(result['processes'][0]['identity']['pid'],self.child.pid)
            with resources._db() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM leases').fetchone()[0],0)

    def test_stop_permission_inherits_execution_rule_and_plan_blocks_it(self):
        from loop_robot.terminal.permissions import PermissionGate
        with tempfile.TemporaryDirectory() as folder:
            gate = PermissionGate(Path(folder)/'permissions.sqlite')
            self.assertEqual(gate.snapshot()['rules']['process_stop'], 'ask')
            gate.set_rule('run_python', 'allow')
            self.assertEqual(gate.snapshot()['rules']['process_stop'], 'allow')
            gate.set_mode('plan')
            with self.assertRaises(PermissionError): gate.check('process_stop', {})
            gate.set_mode('sim')
            gate.set_rule('process_stop', 'deny')
            with self.assertRaises(PermissionError): gate.check('process_stop', {})

    def test_invalid_requests_and_protected_controller(self):
        for args in ({'host':'-oProxyCommand=evil'},{'ports':[True]},{'ports':[65536]}):
            with self.assertRaises(ValueError): request('inspect',args)
        with self.assertRaisesRegex(ValueError,'protected'):
            main(request('stop',{'targets':[process(os.getpid())['identity']],'mode':'kill'}))
