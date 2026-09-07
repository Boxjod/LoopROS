import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from loop_robot.toolchain.admission import HostMonitor, ResourceAdmission, validate_policy
from loop_robot.terminal.agents import AgentRuntime
from test_agents import fake_worker


class Monitor:
    def __init__(self):
        self.value = dict(available_ram_mb=65536, cpu_percent=0, cpu_cores=64,
                          gpus=[dict(index=0, free_vram_mb=8192, gpu_percent=0)], errors=[])

    def sample(self):
        return dict(self.value)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.monitor = Monitor()
        self.admission = ResourceAdmission(self.path / 'leases.sqlite', monitor=self.monitor)

    def tearDown(self):
        self.temp.cleanup()

    def test_shared_ceiling_108_and_release(self):
        peer = ResourceAdmission(self.path / 'leases.sqlite', monitor=self.monitor)
        tokens = [self.admission.inspect(acquire=True) for _ in range(108)]
        self.assertTrue(all(tokens))
        self.assertIsNone(peer.inspect(acquire=True))
        self.assertEqual(peer.status()['reserved_workers'], 108)
        self.admission.release(tokens[0])
        self.assertIsNotNone(peer.inspect(acquire=True))

    def test_concurrent_admission_is_atomic(self):
        from concurrent.futures import ThreadPoolExecutor
        peer = ResourceAdmission(self.path / 'leases.sqlite', {'max_workers':20}, self.monitor)
        other = ResourceAdmission(self.path / 'leases.sqlite', {'max_workers':20}, self.monitor)
        with ThreadPoolExecutor(max_workers=8) as pool:
            tokens = list(pool.map(lambda i: (peer if i % 2 else other).inspect(acquire=True), range(40)))
        self.assertEqual(sum(token is not None for token in tokens), 20)
        self.assertEqual(peer.status()['reserved_workers'], 20)

    def test_ram_cpu_pressure_and_recovery(self):
        self.monitor.value['available_ram_mb'] = 1024
        self.assertIsNone(self.admission.inspect(acquire=True))
        self.assertEqual(self.admission.last['reason'], 'RAM reserve')
        self.monitor.value.update(available_ram_mb=65536, cpu_percent=99)
        self.assertIsNone(self.admission.inspect(acquire=True))
        self.assertEqual(self.admission.last['reason'], 'CPU headroom')
        self.monitor.value['cpu_percent'] = 0
        self.assertIsNotNone(self.admission.inspect(acquire=True))

    def test_gpu_is_explicit_and_does_not_sum_devices(self):
        self.monitor.value['gpus'] = []
        token = self.admission.inspect(acquire=True)
        self.assertIsNotNone(token)  # Remote API does not need local VRAM.
        self.admission.release(token)
        gpu = ResourceAdmission(self.path / 'leases.sqlite', {'agent_vram_mb':4096}, self.monitor)
        self.assertIsNone(gpu.inspect(acquire=True))
        self.monitor.value['gpus'] = [dict(index=i, free_vram_mb=3000, gpu_percent=0) for i in (0, 1)]
        self.assertIsNone(gpu.inspect(acquire=True))
        self.monitor.value['gpus'][0].update(free_vram_mb=8192, gpu_percent=99)
        self.assertIsNone(gpu.inspect(acquire=True))
        self.monitor.value['gpus'][0]['gpu_percent'] = 0
        self.assertIsNotNone(gpu.inspect(acquire=True))

    def test_unknown_metrics_and_dead_reservation(self):
        self.admission.inspect(acquire=True)
        with patch('loop_robot.core.resources._identity', return_value=None):
            self.assertEqual(self.admission.status()['reserved_workers'], 0)
        self.monitor.value['available_ram_mb'] = None
        self.assertIsNone(self.admission.inspect(acquire=True))
        for policy in ({'max_workers':109}, {'max_workers':True}, {'agent_cpu_cores':0}, {'agent_ram_mb':float('nan')}):
            with self.assertRaises(ValueError): validate_policy(policy)
        self.assertEqual(validate_policy({'max_workers':20})['max_workers'],20)

    def runtime(self):
        runtime = AgentRuntime({'Worker':dict(provider='llm',tools=[],prompt='')},
                               {'llm':SimpleNamespace(config={}, resolved_key=lambda:None)}, [],
                               lambda *args:None, self.path / 'agents.jsonl', max_workers=108,
                               worker_target=fake_worker, admission=self.admission)
        self.addCleanup(runtime.close)
        return runtime

    def test_real_process_queue_recovery_cancel_and_no_preemption(self):
        runtime = self.runtime()
        running = runtime.spawn('Worker', 'wait')['agent_id']
        self.monitor.value['available_ram_mb'] = 100
        queued = runtime.spawn('Worker', 'hello')['agent_id']
        self.assertEqual(runtime.result(queued)['state'], 'queued')
        self.assertIsNone(runtime.records[queued]['started'])
        self.assertTrue(runtime.records[running]['process'].is_alive())
        cancelled = runtime.spawn('Worker', 'cancel me')['agent_id']
        runtime.cancel(cancelled)
        self.assertEqual(runtime.result(cancelled)['state'], 'cancelled')
        self.monitor.value['available_ram_mb'] = 65536
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and runtime.result(queued)['state'] != 'done':
            runtime.poll()
            time.sleep(.01)
        self.assertEqual(runtime.result(queued)['result'], 'hello')
        runtime.close()
        self.assertEqual(self.admission.status()['reserved_workers'], 0)

    def test_failed_process_start_releases_reservation(self):
        runtime = self.runtime()
        with patch.object(runtime.context, 'Process') as factory:
            factory.return_value.pid = None
            factory.return_value.start.side_effect = OSError('cannot spawn')
            with self.assertRaises(OSError): runtime.spawn('Worker', 'hello')
        self.assertFalse(runtime.records)
        self.assertEqual(self.admission.status()['reserved_workers'], 0)

    def test_delayed_permission_failure_releases_reservation(self):
        runtime = self.runtime()
        self.monitor.value['available_ram_mb'] = 100
        identity = runtime.spawn('Worker', 'hello')['agent_id']
        def deny(*args):
            raise PermissionError('Mode changed')
        runtime.before_start = deny
        self.monitor.value['available_ram_mb'] = 65536
        runtime.poll()
        self.assertEqual(runtime.result(identity)['state'], 'failed')
        self.assertEqual(self.admission.status()['reserved_workers'], 0)

    def test_supervisor_wait_does_not_start_attempt(self):
        from test_task_supervisor import TaskSupervisorTests
        fixture = TaskSupervisorTests()
        fixture.setUp()
        try:
            fixture.supervisor.runtime.admission = self.admission
            identity = fixture.add('wait')
            self.monitor.value['available_ram_mb'] = 100
            fixture.supervisor.poll()
            task = fixture.store.get(identity)
            self.assertEqual((task['state'], task['attempt']), ('queued', 0))
            self.assertIn('RAM reserve', task['feedback']['resource_wait'])
            history = len(fixture.store.history(identity))
            fixture.supervisor.poll()
            self.assertEqual(len(fixture.store.history(identity)), history)
            self.monitor.value['available_ram_mb'] = 65536
            fixture.supervisor.poll()
            task = fixture.store.get(identity)
            self.assertEqual((task['state'], task['attempt']), ('running', 1))
        finally:
            fixture.tearDown()

    def test_monitor_handles_missing_gpu_and_caches(self):
        with patch('loop_robot.toolchain.admission.subprocess.run', side_effect=FileNotFoundError) as run:
            monitor = HostMonitor()
            first = monitor.sample()
            self.assertIs(first, monitor.sample())
            self.assertEqual(run.call_count, 1)
            self.assertEqual(first['gpus'], [])
            self.assertTrue(first['errors'])
