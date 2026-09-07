import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from loop_robot.core.nodes import NodeDefinition, NodeRuntime
from loop_robot.toolchain.ros_host import ObservationStore, RosHost, summarize
from loop_robot.toolchain.ros_node import RosNode, config, resource


def wait_for(predicate, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(.03)
    raise AssertionError('ROS fixture timed out')


def spec(**extra):
    return config({'topics': [{'name': 'arm', 'topic': '/joint_states', 'kind': 'joints'}], **extra})


class SlowClose:
    def __init__(self, value): pass
    def tick(self): pass
    def snapshot(self): return {}
    def close(self): time.sleep(.4)


class RosRuntimeTests(unittest.TestCase):
    def test_validation_and_program_resource_identity(self):
        for value in ({'version': 3}, {'python': 'python'}, {'env': {'API_KEY': 'no'}},
                      {'topics': []}, {'topics': [{'name': 'x', 'topic': '/x', 'kind': 'unknown'}]},
                      {'launch': {'argv': ['ros2'], 'cwd': 'relative'}}):
            with self.assertRaises(ValueError): spec(**value)
        one = spec(launch={'argv': ['ros2', 'launch', 'slam_toolbox', 'online_async_launch.py'], 'cwd': '/tmp'})
        self.assertEqual(resource(one, 'one'), resource(one, 'two'))
        self.assertEqual(spec()['version'], 2)

    def test_receipt_age_invalid_replaces_good_and_source_clock_separate(self):
        value = spec(); store = ObservationStore(value['topics'], 2)
        self.assertEqual(store.snapshot()['readiness'], 'not_ready')
        message = NS(name=['j1'], position=[.3], header=NS(frame_id='base', stamp=NS(sec=0, nanosec=0)))
        store.receive(value['topics'][0], message)
        row = store.snapshot()['observations']['arm']
        self.assertEqual(row['source_stamp']['sec'], 0)
        self.assertEqual(row['source_freshness'], 'not_verified')
        self.assertEqual(store.snapshot()['readiness'], 'observations_ready')
        with patch('loop_robot.toolchain.ros_host.time.monotonic', return_value=time.monotonic()+10):
            self.assertEqual(store.snapshot()['observations']['arm']['state'], 'stale')
        message.position = [float('nan')]
        store.receive(value['topics'][0], message)
        self.assertEqual(store.snapshot()['observations']['arm']['state'], 'invalid')
        self.assertNotIn('summary', store.snapshot()['observations']['arm'])

    def test_summaries_are_bounded_and_semantics_explicit(self):
        scan = summarize('scan', NS(ranges=[float('inf'), float('nan'), 2., -1.], range_min=.1, range_max=10))
        self.assertEqual(scan['valid_rays'], 1)
        self.assertEqual(scan['nearest_m'], 2.)
        audio = summarize('audio', NS(data=b'x'*10000))
        self.assertLess(len(json.dumps(audio)), 150)
        with self.assertRaises(ValueError): summarize('tactile', NS(data=list(range(257))))
        vec = NS(x=1, y=2, z=3)
        self.assertEqual(summarize('force', NS(wrench=NS(force=vec, torque=vec)))['force_N'], [1,2,3])

    def test_ros1_ros2_adapter_qos_time_and_cleanup(self):
        value = spec()
        message = NS(name=['j1'], position=[.4], header=NS(frame_id='base', stamp=NS(secs=3, nsecs=4)))
        calls = []
        sub = NS(unregister=lambda: calls.append('unregister'))
        ros1 = NS(init_node=lambda *a, **k: calls.append(k),
                  Subscriber=lambda topic, cls, cb, **kw: (cb(message), sub)[1],
                  signal_shutdown=lambda reason: calls.append('shutdown'))
        modules = {'rospy': ros1, 'sensor_msgs.msg': NS(JointState=object)}
        with patch.dict(sys.modules, modules):
            host = RosHost(spec(version=1))
            self.assertEqual(host.store.snapshot()['observations']['arm']['source_stamp'], {'sec':3,'nanosec':4})
            host.close()
        self.assertIn('unregister', calls)
        qos = []
        ctx = NS(ok=lambda: True, shutdown=lambda: calls.append('context_closed'))
        node = NS(create_subscription=lambda cls, topic, cb, q: (qos.append(q), sub)[1],
                  destroy_node=lambda: calls.append('destroy'))
        ros2 = NS(init=lambda **kw: None, create_node=lambda *a, **kw: node, spin_once=lambda *a, **kw: None)
        modules = {'rclpy': ros2, 'rclpy.context': NS(Context=lambda: ctx),
                   'rclpy.qos': NS(QoSProfile=lambda **kw: kw, ReliabilityPolicy=NS(RELIABLE=1, BEST_EFFORT=2),
                                  DurabilityPolicy=NS(TRANSIENT_LOCAL=1,VOLATILE=2)),
                   'sensor_msgs.msg': NS(JointState=object), 'nav_msgs.msg': NS(OccupancyGrid=object)}
        value['topics'].append({'name':'map', 'topic':'/map', 'kind':'map', 'qos':'latched','required':True,'max_age_s':30})
        with patch.dict(sys.modules, modules):
            host = RosHost(value); host.tick(); host.close()
        self.assertEqual(qos[0]['reliability'], 2)
        self.assertEqual(qos[1]['durability'], 1)
        self.assertIn('context_closed', calls)

    def test_graceful_timeout_retains_worker_and_resource_until_exit(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = NodeRuntime({'slow':NodeDefinition(SlowClose, dict, lambda c,n:'owned', .01, False)}, root)
            try:
                runtime.start('observer','slow')
                wait_for(lambda: runtime.status('observer')['state'] == 'running')
                stopped = runtime.stop('observer')
                self.assertTrue(stopped['process_alive'])
                self.assertEqual(stopped['state'], 'stopping')
                with self.assertRaises(ValueError): runtime.start('another','slow')
                wait_for(lambda: not runtime.status('observer')['process_alive'])
                self.assertEqual(runtime.status('observer')['state'], 'stopped')
            finally: runtime.close()



    def test_admission_bind_failure_never_starts_ros_factory(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as root:
            admission=Mock()
            admission.inspect.return_value='lease'
            admission.bind.side_effect=RuntimeError('fixture bind failed')
            runtime=NodeRuntime({'ros':NodeDefinition(RosNode,config,resource,3,False)},root,admission=admission)
            try:
                with self.assertRaisesRegex(RuntimeError,'fixture bind failed'):
                    runtime.start('sensors','ros',spec())
                self.assertEqual(runtime.status()['nodes'], [])
                self.assertEqual(list(Path(root).glob('*.ros-config.json')), [])
                admission.release.assert_called_once_with('lease')
            finally: runtime.close()

    def test_node_tool_permission_gate_and_cli_config(self):
        from loop_robot.terminal import nodes
        from unittest.mock import Mock
        from threading import RLock
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'ros.json'; path.write_text(json.dumps(spec()))
            app = NS(tool=Mock(return_value={'state':'starting'}))
            nodes.dispatch(app, 'start ros sensors ' + str(path))
            self.assertEqual(app.tool.call_args.args[1]['kind'], 'ros')
            nodes.dispatch(app, 'export_map sensors map')
            self.assertEqual(app.tool.call_args.args[1]['action'], 'export_map')
            permissions=Mock(); permissions.snapshot.return_value={'rules':{'run_python':'deny'}}
            runtime=Mock(); runtime.lock=RLock()
            app=NS(nodes=runtime,permissions=permissions)
            with self.assertRaises(PermissionError):
                nodes.tool(app,'node_start',{'name':'sensors','kind':'ros','config':spec()})
            runtime.start.assert_not_called()
            permissions.snapshot.return_value={'rules':{'run_python':'allow'}}
            nodes.tool(app,'node_start',{'name':'sensors','kind':'ros','config':spec()})
            runtime.start.assert_called_once()

    def test_separate_interpreter_host_lifecycle_with_fixture_sdk(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root/'sensor_msgs').mkdir(); (root/'sensor_msgs/__init__.py').write_text('')
            (root/'sensor_msgs/msg.py').write_text('class JointState: pass\n')
            (root/'rospy.py').write_text('''from types import SimpleNamespace as S
from pathlib import Path
def init_node(*a, **k): pass
def Subscriber(topic, cls, callback, **kw):
    callback(S(name=['fixture_joint'],position=[0.5]))
    return S(unregister=lambda:None)
def is_shutdown(): return False
def signal_shutdown(reason): Path(__file__).with_suffix('.closed').write_text(reason)
''')
            program = root/'program.py'
            program.write_text("import signal,time\nfrom pathlib import Path\ndef stop(*a):\n Path(__file__).with_suffix('.closed').write_text('SIGINT')\n raise SystemExit(0)\nsignal.signal(signal.SIGINT, stop)\nwhile True: time.sleep(.05)\n")
            value = spec(version=1, env={'PYTHONPATH':str(root)},
                         launch={'argv':[sys.executable,str(program)],'cwd':str(root)})
            runtime = NodeRuntime({'ros':NodeDefinition(RosNode,config,resource,3,False)},root/'nodes')
            try:
                runtime.start('sensors','ros',value)
                wait_for(lambda: runtime.status('sensors')['snapshot'].get('readiness') == 'observations_ready')
                snapshot = runtime.status('sensors')['snapshot']
                self.assertNotEqual(snapshot['host_pid'], os.getpid())
                self.assertFalse(snapshot['model_polling'])
                self.assertFalse(runtime.stop('sensors')['process_alive'])
                self.assertTrue((root/'rospy.closed').exists())
                self.assertEqual((root/'program.closed').read_text(),'SIGINT')
            finally: runtime.close()


if __name__ == '__main__': unittest.main()
