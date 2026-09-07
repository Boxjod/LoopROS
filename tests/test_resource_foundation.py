from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
from loop_robot.core.resources import ResourceManager, ResourceBusy
from test_resource_admission import Monitor
from loop_robot.terminal.services import PolicyServices
from loop_robot.toolchain.resources import ModelPool, ModelSpec


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.monitor = Monitor()
        self.resources = ResourceManager(self.path / 'resources.sqlite', {'max_workers':1}, self.monitor)

    def test_workloads_share_memory_but_only_agents_use_agent_slots(self):
        self.resources.inspect(acquire=True)
        with self.resources.lease('python', {'ram_mb':512}):
            snapshot = self.resources.status()
            self.assertEqual(snapshot['reservations_by_workload'], {'agent':1, 'python':1})
            self.assertEqual(snapshot['reserved_resources']['ram'], 768)
        self.assertEqual(self.resources.status()['reservations_by_workload'], {'agent':1})
        self.monitor.value['available_ram_mb'] = 1024
        with self.assertRaises(ResourceBusy):
            with self.resources.lease('python', {}): self.fail('Must not execute')

    def test_two_policy_processes_share_budget_and_release(self):
        spec = {'argv':[sys.executable, '-c', 'import time; time.sleep(20)'], 'cwd':None,
                'resources':{'ram_mb':512, 'cpu_cores':.1}}
        services = PolicyServices({'a':spec,'b':spec}, self.path / 'logs', self.resources)
        self.addCleanup(services.close)
        services.start('a'); services.start('b')
        self.assertEqual(self.resources.status()['reservations_by_workload'], {'policy_service':2})
        services.close()
        self.assertEqual(self.resources.status()['reservations_by_workload'], {})
        self.monitor.value['available_ram_mb'] = 1024
        with patch('loop_robot.terminal.services.subprocess.Popen') as launch:
            with self.assertRaises(ResourceBusy): services.start('a')
            launch.assert_not_called()

    def test_loaded_model_reserves_until_eviction_and_failure_releases(self):
        pool = ModelPool(2048 * 1048576, 0, resources=self.resources)
        pool.register('model', ModelSpec(1024 * 1048576, 0, lambda:object(), lambda value:None))
        with pool.lease('model'):
            self.assertEqual(self.resources.status()['reservations_by_workload'], {'model':1})
        self.assertEqual(self.resources.status()['reserved_resources']['ram'], 1024)
        pool.close()
        self.assertEqual(self.resources.status()['reservations_by_workload'], {})
        def fail(): raise ValueError('loader failed')
        pool.register('bad', ModelSpec(1024, 0, fail, lambda value:None))
        with self.assertRaises(ValueError):
            with pool.lease('bad'): pass
        self.assertEqual(self.resources.status()['reservations_by_workload'], {})

    def test_node_lifecycle_uses_shared_budget(self):
        from loop_robot.core.nodes import NodeDefinition, NodeRuntime
        from test_nodes import HeartbeatNode, validate, resource
        nodes = NodeRuntime({'fixture':NodeDefinition(HeartbeatNode, validate, resource)}, self.path / 'nodes', admission=self.resources)
        self.addCleanup(nodes.close)
        nodes.start('sample', 'fixture')
        self.assertEqual(self.resources.status()['reservations_by_workload'], {'node':1})
        nodes.stop('sample')
        self.assertEqual(self.resources.status()['reservations_by_workload'], {})
        self.monitor.value['available_ram_mb'] = 1024
        with self.assertRaises(ResourceBusy): nodes.start('blocked', 'fixture')
        self.assertNotIn('blocked', nodes.records)

    def test_common_tool_and_python_rejection_before_execution(self):
        from loop_robot.terminal.app import App
        from loop_robot.terminal.config import load_config
        from loop_robot.terminal.conversation_context import COMMON
        import hashlib
        app = App(load_config(), self.path / 'app')
        self.addCleanup(app.close)
        app.resources = self.resources
        app.workspace_root = self.path
        self.assertIn('resource_status', COMMON)
        self.assertIn('sample', app.tool('resource_status', {}))
        app.permissions.set_mode('plan')
        self.assertIn('sample', app.tool('resource_status', {}))
        app.permissions.set_rule('resource_status','deny')
        with self.assertRaises(PermissionError): app.tool('resource_status', {})
        app.permissions.set_mode('sim');app.permissions.set_rule('run_python', 'allow')
        script = self.path / 'test.py';script.write_text('print(123)')
        self.monitor.value['available_ram_mb'] = 1024
        with patch('loop_robot.terminal.python_runner.subprocess.Popen') as launch:
            with self.assertRaises(ResourceBusy):
                app.tool('run_python', dict(path=str(script), expected_sha256=hashlib.sha256(script.read_bytes()).hexdigest()))
            launch.assert_not_called()
