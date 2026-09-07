import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from core.nodes import NodeDefinition, NodeRuntime
from core.store import EventStore
from terminal.app import App
from terminal.config import load_config


class HeartbeatNode:
    def __init__(self, config):
        self.ticks = 0

    def tick(self):
        self.ticks += 1

    def snapshot(self):
        return {'ticks': self.ticks}

    def command(self, action, arguments, stopping):
        if action == 'crash':
            os._exit(9)
        if action == 'hang':
            time.sleep(10)
        return arguments

    def close(self):
        pass


def validate(config):
    return dict(config)


def resource(config, name):
    return config.get('resource', name)


class BrokenNode(HeartbeatNode):
    def __init__(self, config):
        raise RuntimeError('fixture startup failure')


def wait_for(predicate, timeout=6):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        value = predicate()
        if value:
            return value
        time.sleep(.03)
    raise AssertionError('Timed out waiting for node state')


def pty_receive_factory(config):
    from toolchain.node_workers import SerialReceiveNode
    original_open = os.open
    with patch('toolchain.serial_port.Path.resolve', return_value=Path('/dev/ttyACM999')), patch('toolchain.serial_port.os.open', side_effect=lambda path, flags: original_open(config['pty'], flags)):
        service = SerialReceiveNode(config)
    service.port.path = config['pty']
    return service


class NodeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = NodeRuntime({'counter': NodeDefinition(HeartbeatNode, validate, resource),
                                    'broken': NodeDefinition(BrokenNode, validate, resource)}, self.temp.name)

    def tearDown(self):
        self.runtime.close()
        self.temp.cleanup()

    def ready(self, name):
        return wait_for(lambda: self.runtime.status(name)['state'] == 'running')

    def test_two_independent_processes_resource_ownership_results_and_restart(self):
        one = self.runtime.start('arm', 'counter', {'resource': 'device-one'})
        two = self.runtime.start('camera', 'counter')
        self.ready('arm')
        self.ready('camera')
        self.assertEqual(len({one['pid'], two['pid'], os.getpid()}), 3)
        with self.assertRaises(ValueError):
            self.runtime.start('duplicate', 'counter', {'resource': 'device-one'})
        first_tick = self.runtime.status('arm')['snapshot']['ticks']
        time.sleep(.3)  # No UI poll: the supervisor independently drains heartbeats.
        self.assertGreater(self.runtime.status('arm')['snapshot']['ticks'], first_tick)
        queued = self.runtime.command('arm', 'echo', {'value': 7})
        self.assertEqual(queued['task_success'], 'not_evaluated')
        wait_for(lambda: self.runtime.status('arm')['results'])
        result = self.runtime.status('arm')['results'][-1]
        self.assertEqual(result['command_id'], queued['command_id'])
        self.assertEqual(result['result'], {'value': 7})
        self.assertFalse(self.runtime.stop('arm')['process_alive'])
        self.assertTrue(self.runtime.status('camera')['process_alive'])
        restarted = self.runtime.start('arm', 'counter', {'resource': 'device-one'})
        self.assertNotEqual(restarted['instance_id'], one['instance_id'])
        self.assertNotEqual(restarted['pid'], one['pid'])
        self.assertTrue(Path(self.temp.name, 'events.jsonl').exists())

    def test_crash_stale_heartbeat_and_forced_stop(self):
        self.runtime.start('arm', 'counter')
        self.ready('arm')
        self.runtime.command('arm', 'crash')
        wait_for(lambda: self.runtime.status('arm')['state'] == 'failed')
        self.assertEqual(self.runtime.status('arm')['results'][-1]['result']['verdict'], 'inconclusive')
        self.runtime.start('arm', 'counter')
        self.ready('arm')
        self.runtime.stale_after = .4
        self.runtime.command('arm', 'hang')
        wait_for(lambda: self.runtime.status('arm')['state'] == 'unresponsive')
        with self.assertRaises(RuntimeError):
            self.runtime.command('arm', 'echo')
        self.assertFalse(self.runtime.stop('arm')['process_alive'])
        self.assertTrue(any(e.get('forced') for e in self.runtime.logs('arm')))

    @unittest.skipUnless(__import__('sys').platform.startswith('linux'), 'Linux serial adapter')
    def test_serial_node_receives_in_child_and_detects_disconnect(self):
        import pty
        master, slave = pty.openpty()
        self.runtime.definitions['rx_fixture'] = NodeDefinition(pty_receive_factory, validate, resource)
        try:
            self.runtime.start('rx', 'rx_fixture', {'port': '/dev/ttyACM999', 'baud': 115200, 'pty': os.ttyname(slave)})
            self.ready('rx')
            os.write(master, b'fixture-frame')
            wait_for(lambda: self.runtime.status('rx')['snapshot'].get('bytes_received', 0) > 0)
            state = self.runtime.status('rx')
            self.assertEqual(state['snapshot']['latest_received']['hex'], b'fixture-frame'.hex())
            self.assertIsNone(state['snapshot']['motor_state'])
            os.close(master)
            master = None
            wait_for(lambda: self.runtime.status('rx')['state'] == 'failed')
            wait_for(lambda: not self.runtime.status('rx')['process_alive'])
            store = EventStore(state['evidence_path'])
            try:
                self.assertIn('review', [kind for kind, payload in store.events()])
            finally:
                store.close()
        finally:
            self.runtime.stop('rx')
            os.close(slave)
            if master is not None:
                os.close(master)

    def test_startup_failure_and_shutdown_reap_children(self):
        self.runtime.start('bad', 'broken')
        wait_for(lambda: self.runtime.status('bad')['state'] == 'failed')
        self.assertIn('fixture startup failure', self.runtime.status('bad')['error'])
        self.runtime.start('good', 'counter')
        self.ready('good')
        processes = [r['process'] for r in self.runtime.records.values()]
        self.runtime.close()
        self.assertFalse(any(p.is_alive() for p in processes))
        self.assertFalse(self.runtime.monitor.is_alive())


class NodeAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = App(load_config(), self.temp.name)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_actual_mujoco_move_focus_background_and_evidence(self):
        self.app.dispatch('/node start sim_arm arm')
        wait_for(lambda: self.app.nodes.status('arm')['state'] == 'running')
        self.app.dispatch('/node use arm')
        with patch.object(self.app.client, 'complete') as llm:
            command = json.loads(self.app.dispatch('move 0.3 -0.2'))
            wait_for(lambda: self.app.nodes.status('arm')['results'])
            result = self.app.nodes.status('arm')['results'][-1]
            self.assertEqual(result['command_id'], command['command_id'])
            self.assertEqual(result['result']['review']['verdict'], 'pass')
            status = json.loads(self.app.dispatch('status'))
            self.assertEqual(status['snapshot']['backend'], 'mujoco')
            self.app.dispatch('master')
            ticks = status['snapshot']['ticks']
            wait_for(lambda: self.app.nodes.status('arm')['snapshot']['ticks'] > ticks)
            llm.assert_not_called()
        self.assertEqual(self.app.node_focus, 'master')
        self.app.dispatch('/node stop arm')
        store = EventStore(status['evidence_path'])
        try:
            kinds = [kind for kind, payload in store.events()]
            self.assertIn('episode', kinds)
            self.assertIn('review', kinds)
        finally:
            store.close()

    def test_permissions_stop_existing_nodes_and_do_not_transfer_serial_approval(self):
        self.app.dispatch('/permissions deny open_serial')
        with self.assertRaises(PermissionError):
            self.app.tool('node_start', {'name': 'rx', 'kind': 'serial_rx', 'config': {'port': '/dev/ttyACM0', 'baud': 115200}})
        self.assertEqual(self.app.nodes.status()['nodes'], [])
        self.app.dispatch('/node start sim_arm arm')
        wait_for(lambda: self.app.nodes.status('arm')['state'] == 'running')
        self.app.dispatch('/plan')
        self.assertFalse(self.app.nodes.status('arm')['process_alive'])
        with self.assertRaises(PermissionError):
            self.app.dispatch('/node start sim_arm next')
        with self.assertRaises(ValueError):
            self.app.scheduled_tool('node_start', {'name': 'next', 'kind': 'sim_arm'})
        self.app.dispatch('/node logs arm')

    def test_queued_master_input_is_not_retargeted_on_focus_switch(self):
        self.app.nodes.definitions['counter'] = NodeDefinition(HeartbeatNode, validate, resource)
        self.app.nodes.start('arm', 'counter')
        wait_for(lambda: self.app.nodes.status('arm')['state'] == 'running')
        self.app.dispatch('/node use arm')
        with patch.object(self.app.agent, 'reply', return_value='Master reply') as reply:
            self.assertEqual(self.app.dispatch('queued before switch', focus='master'), 'Master reply')
            reply.assert_called_once()
            with self.assertRaises(ValueError):
                self.app.dispatch('free-form question')
