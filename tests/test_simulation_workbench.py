import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('MUJOCO_GL','egl')
ROOT=Path(__file__).resolve().parents[1]


class SimulationTests(unittest.TestCase):
    def setUp(self):
        try: import mujoco, numpy, h5py
        except ImportError: self.skipTest('simulation/dataset extras missing')
        from loop_robot.toolchain.simulation import SimulationWorkbench
        self.temp=tempfile.TemporaryDirectory()
        self.service=SimulationWorkbench(self.temp.name)
        self.instance=self.service.call('sim_create',{'backend':'mujoco','scene':str(ROOT/'assets/simulation/simulation_workbench.xml')})['instance']

    def tearDown(self):
        if hasattr(self,'service'): self.service.close();self.temp.cleanup()

    def call(self,name,**args): return self.service.call(name,{'instance':self.instance,**args})

    def cameras(self):
        self.call('sim_camera',config={'name':'head','position':[0,0,2],'quaternion':[1,0,0,0],'width':64,'height':48})
        self.call('sim_camera',config={'name':'wrist_cam','parent':'wrist','position':[0,0,.3],'quaternion':[1,0,0,0],'width':64,'height':48})

    def test_camera_geometry_depth_and_parent_motion(self):
        import numpy as np
        self.cameras()
        first=self.call('sim_capture',cameras=['head','wrist_cam'])
        state=first['observation'];self.assertEqual(state['time'],0)
        head=first['cameras']['head']
        frame=np.load(head['arrays'])
        self.assertEqual(frame['rgb'].shape,(48,64,3));self.assertEqual(frame['segmentation'].shape,(48,64,2))
        self.assertLess(frame['depth'].min(),2)
        self.assertGreater(frame['rgb'].var(),0)
        self.assertAlmostEqual(head['intrinsics'][0][0],head['intrinsics'][1][1])
        wrist_before=np.array(first['cameras']['wrist_cam']['camera_to_world'])
        self.call('sim_step',action=[.7,.4],steps=500)
        second=self.call('sim_capture',cameras=['head','wrist_cam'])
        self.assertGreater(second['observation']['time'],0)
        self.assertFalse(np.allclose(wrist_before,second['cameras']['wrist_cam']['camera_to_world']))
        self.assertTrue(np.allclose(head['camera_to_world'],second['cameras']['head']['camera_to_world']))

    def test_record_alignment_failure_label_and_action_padding(self):
        import numpy as np,h5py
        from loop_robot.toolchain.sim_dataset import action_chunk
        self.cameras()
        self.call('sim_task',task={'name':'reach','variation':2,'seed':17,'horizon':3,
            'success':[{'kind':'position','body':'wrist','target':[3,3,3],'tolerance':.01}]})
        self.call('sim_reset',seed=17)
        initial=self.call('sim_inspect')['qpos']
        result=self.call('sim_record',actions=[[.1,.2],[.3,.4],[.5,.6]],cameras=['head','wrist_cam'],steps=5)
        self.assertFalse(result['evaluation']['success']);self.assertEqual(result['transitions'],3)
        with h5py.File(result['path'],'r') as f:
            np.testing.assert_allclose(f['observations/qpos'][0],initial)
            np.testing.assert_allclose(f['action'][:],[[.1,.2],[.3,.4],[.5,.6]])
            np.testing.assert_allclose(f['observations/qpos'][1],f['next_observations/qpos'][0])
            self.assertTrue(np.all(f['next_timestamps'][:]>f['timestamps'][:]))
            self.assertTrue(f['truncated'][-1]);self.assertFalse(f['terminated'][-1]);self.assertTrue(f.attrs['complete'])
        chunk=action_chunk(result['path'],2,4,['head'])
        self.assertEqual(chunk['is_pad'].tolist(),[False,True,True,True])
        np.testing.assert_allclose(chunk['actions'][0],[.5,.6])

    def test_bad_later_action_does_not_partially_execute(self):
        self.cameras()
        self.call('sim_task',task={'name':'exists','success':[{'kind':'exists','body':'cube'}]})
        with self.assertRaises(ValueError):
            self.call('sim_record',actions=[[0,0],[999,0]],cameras=['head'])
        self.assertEqual(self.call('sim_inspect')['time'],0)

    def test_edit_preserves_joint_state_and_unknown_instances_rejected(self):
        import numpy as np
        self.call('sim_step',action=[.4,.3],steps=100)
        previous=self.call('sim_inspect')
        self.call('sim_edit',operation='box',config={'name':'obstacle','size':[.2,.2,.2],'position':[1,0,.1]})
        now=self.call('sim_inspect')
        np.testing.assert_allclose(previous['qpos'],now['qpos'])
        self.assertEqual(previous['time'],now['time']);self.assertIn('obstacle',now['bodies'])
        with self.assertRaises(ValueError): self.service.call('sim_inspect',{'instance':'another-session'})

    def test_move_remove_and_incomplete_episode(self):
        import numpy as np
        from loop_robot.toolchain.sim_dataset import action_chunk
        self.call('sim_edit',operation='move',config={'name':'cube','position':[1,0,1]})
        np.testing.assert_allclose(self.call('sim_inspect')['bodies']['cube'],[1,0,1])
        self.cameras()
        self.call('sim_task',task={'name':'cancelled','seed':9,'success':[{'kind':'exists','body':'cube'}]})
        with self.assertRaisesRegex(ValueError,'seed'):
            self.call('sim_record',actions=[[0,0]],cameras=['head'])
        self.call('sim_reset',seed=9)
        self.service.cancelled=lambda:True
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            self.call('sim_record',actions=[[0,0]],cameras=['head'])
        partial=next(Path(self.temp.name).rglob('episode_0.hdf5'))
        with self.assertRaisesRegex(ValueError,'Incomplete'):
            action_chunk(partial,0,2,['head'])
        self.call('sim_edit',operation='remove',config={'name':'cube'})
        self.assertNotIn('cube',self.call('sim_inspect')['bodies'])

    def test_gymnasium_contract(self):
        try:
            from gymnasium.utils.env_checker import check_env
        except ImportError: self.skipTest('Gymnasium missing')
        from loop_robot.toolchain.sim_gym import SimulationEnv
        engine=self.service.entry(self.instance)['engine']
        env=SimulationEnv(engine,{'name':'reach','horizon':2,'success':[{'kind':'position','body':'wrist','target':[5,5,5],'tolerance':.1}]})
        check_env(env,skip_render_check=True)
        env.reset(seed=1)
        env.step([0,0]);result=env.step([0,0])
        self.assertFalse(result[2]);self.assertTrue(result[3])
        with self.assertRaises(RuntimeError): env.step([0,0])


class PermissionAndBridgeTests(unittest.TestCase):
    def test_temporal_aggregation_keeps_zero_actions(self):
        import numpy as np
        from loop_robot.toolchain.sim_dataset import TemporalActions
        buffer=TemporalActions(2,decay=0)
        buffer.add(0,[[1,1],[0,0]])
        buffer.add(1,[[2,4]])
        np.testing.assert_allclose(buffer.action(1),[1,2])
        with self.assertRaises(ValueError): buffer.action(2)
        buffer.reset()
        with self.assertRaises(ValueError): buffer.action(0)

    def test_actual_tcp_transport_runs_engine_on_owner_thread(self):
        import threading
        import concurrent.futures
        from loop_robot.toolchain.sim_isaac_host import RuntimeBridge,NetworkBridge
        from loop_robot.toolchain.sim_isaac_client import IsaacSimulationClient
        owner=threading.get_ident()
        class Engine:
            def inspect(self):
                if threading.get_ident()!=owner: raise AssertionError('Wrong simulation thread')
                return {'time':1.}
            def close(self): pass
        bridge=RuntimeBridge('test-token',lambda scene=None:Engine())
        server=NetworkBridge(bridge,0)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'connection.json'
            path.write_text(json.dumps({'host':'127.0.0.1','port':server.server.server_address[1],'token':'test-token'}));path.chmod(0o600)
            def client():
                engine=IsaacSimulationClient(path)
                try:return engine.inspect()
                finally:engine.close()
            try:
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future=executor.submit(client)
                    while not future.done(): server.poll()
                    self.assertEqual(future.result(),{'time':1.})
            finally:server.close()

    def test_gate_before_simulation_and_no_self_approval(self):
        from loop_robot.terminal.permissions import PermissionGate
        from loop_robot.terminal.simulation import call_service
        class Service:
            def call(self,*args): raise AssertionError('Must not execute')
        with tempfile.TemporaryDirectory() as d:
            gate=PermissionGate(Path(d)/'gate.sqlite');gate.set_mode('plan')
            with self.assertRaises(PermissionError): call_service(Service(),gate,'sim_create',{'backend':'mujoco'})
            gate.set_mode('sim');gate.set_rule('sim_step','deny')
            with self.assertRaises(PermissionError): call_service(Service(),gate,'sim_step',{'instance':'x','action':[]})
            with self.assertRaises(PermissionError): call_service(Service(),gate,'sim_record',{'instance':'x','actions':[[]],'cameras':['head']})

    def test_rpc_auth_ownership_and_duplicate_mutation(self):
        from loop_robot.toolchain.sim_isaac_host import RuntimeBridge
        class Engine:
            def inspect(self): return {'time':0}
            def close(self): pass
        bridge=RuntimeBridge('private-token',lambda scene=None:Engine())
        with self.assertRaises(PermissionError): bridge.handle({'token':'wrong'})
        request={'token':'private-token','id':'create1','method':'create','args':{}}
        instance=bridge.handle(request)['instance']
        with self.assertRaises(ValueError): bridge.handle(request)
        with self.assertRaises(ValueError): bridge.handle({'token':'private-token','id':'read1','method':'inspect','args':{},'instance':'stale'})
        self.assertEqual(bridge.handle({'token':'private-token','id':'read2','method':'inspect','args':{},'instance':instance}),{'time':0})

    def test_numpy_transport_roundtrip(self):
        try: import numpy as np
        except ImportError: self.skipTest('numpy missing')
        from loop_robot.toolchain.sim_isaac_client import encode,decode
        source={'depth':np.array([[1.,float('inf')]],dtype=np.float32),'seg':np.array([[3]],dtype=np.uint32)}
        result=decode(json.loads(json.dumps(encode(source),allow_nan=False)))
        np.testing.assert_array_equal(source['depth'],result['depth'])
        np.testing.assert_array_equal(source['seg'],result['seg'])


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_mcp_initialize_tools_and_plan_denial(self):
        try:
            from mcp import ClientSession,StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError: self.skipTest('MCP extra missing')
        import sys
        from loop_robot.terminal.permissions import PermissionGate
        with tempfile.TemporaryDirectory() as d:
            gate=PermissionGate(Path(d)/'permissions.sqlite');gate.set_mode('plan')
            params=StdioServerParameters(command=sys.executable,args=['-c','from launcher import main; raise SystemExit(main())','mcp','--state-dir',d],cwd=str(ROOT),env={'MUJOCO_GL':'egl'})
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize()
                    names={t.name for t in (await client.list_tools()).tools}
                    self.assertIn('sim_camera',names);self.assertNotIn('approve',names)
                    reply=await client.call_tool('sim_create',{'backend':'mujoco'})
                    self.assertTrue(reply.isError)
                    self.assertIn('plan',reply.content[0].text)
                    gate.set_mode('sim')
                    result=await client.call_tool('sim_create',{'backend':'mujoco'})
                    self.assertFalse(result.isError,result)
                    instance=json.loads(result.content[0].text)['instance']
                    denied=await client.call_tool('sim_record',{'instance':instance,'actions':[[]],'cameras':['head']})
                    self.assertTrue(denied.isError)
                    self.assertIn('no approval UI',denied.content[0].text)
                    await client.call_tool('sim_close',{'instance':instance})
