import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import mujoco
import numpy as np
from toolchain.viewer_control import SimulationControl, validate

XML='''<mujoco><option gravity="0 0 0"/><worldbody><body name="arm/base"><joint name="arm/joint" axis="0 0 1" range="-90 90"/><geom type="capsule" fromto="0 0 0 .3 0 0" size=".02"/><body name="arm/hand" pos=".3 0 0"><geom size=".01"/></body></body></worldbody><actuator><position name="arm/motor" joint="arm/joint" kp="100" kv="10" ctrlrange="-1.5 1.5"/></actuator></mujoco>'''

class MotionTests(unittest.TestCase):
    def control(self,xml=XML):
        m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
        return SimulationControl(mujoco,m,d)
    def run_motion(self,c):
        for _ in range(6000):
            c.motion.tick();mujoco.mj_step(c.model,c.data)
            if not c.motion.active:break
    def test_real_physics_joint_target_and_cartesian_ik(self):
        c=self.control();c.paused=True
        result=c.apply({'action':'move_joints','robot':'arm','target':[.4],'duration':1},None)
        self.assertFalse(c.paused);self.assertEqual(result['motion']['state'],'running')
        self.run_motion(c)
        self.assertEqual(c.motion.result['state'],'succeeded');self.assertAlmostEqual(c.data.qpos[0],.4,delta=.04)
        c.apply({'action':'move_cartesian','robot':'arm','body':'arm/hand','position':[float(.3*np.cos(.7)),float(.3*np.sin(.7)),0],'duration':1},None)
        self.run_motion(c);self.assertEqual(c.motion.result['state'],'succeeded')
        self.assertLess(c.motion.result['position_error'],.02)
    def test_unreachable_and_limits_do_not_change_control(self):
        c=self.control();before=c.data.ctrl.copy()
        for command in ({'action':'move_cartesian','robot':'arm','body':'arm/hand','position':[3,0,0],'duration':1},{'action':'move_joints','robot':'arm','target':[2],'duration':1}):
            with self.assertRaises(ValueError):c.apply(command,None)
            np.testing.assert_equal(c.data.ctrl,before);self.assertIsNone(c.motion.active)
        with self.assertRaises(ValueError):validate({'action':'move_joints','robot':'arm','target':[float('nan')],'duration':1})
    def test_stop_and_pause_cancel_trajectory(self):
        c=self.control();c.apply({'action':'move_joints','robot':'arm','target':[.4],'duration':1},None)
        c.motion.tick();mujoco.mj_step(c.model,c.data)
        c.apply({'action':'pause'},None);self.assertIsNone(c.motion.active)
        self.assertEqual(c.motion.result['state'],'cancelled')
    def test_obstacle_blocks_plan(self):
        xml=XML.replace('<worldbody>','<worldbody><geom name="obstacle" pos=".2 .15 0" size=".04"/>')
        c=self.control(xml)
        with self.assertRaisesRegex(ValueError,'intersects'):
            c.apply({'action':'move_joints','robot':'arm','target':[1.2],'duration':2},None)
        self.assertIsNone(c.motion.active)
    def test_closed_window_notification_is_once_and_not_in_history(self):
        from terminal.app import App
        from terminal.config import load_config
        from terminal.interactive import Terminal
        from prompt_toolkit.application import create_app_session
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput
        with tempfile.TemporaryDirectory() as d, create_pipe_input() as inp:
            app=App(load_config(),d)
            try:
                with create_app_session(input=inp,output=DummyOutput()):
                    terminal=Terminal(app)
                terminal.viewer_was_open=True
                with patch.object(app.viewer,'status',return_value={'window_open':False,'status':'closed'}),patch.object(terminal,'append') as emit:
                    terminal.poll_viewer();terminal.poll_viewer()
                self.assertEqual(emit.call_count,1);self.assertEqual(terminal.viewer_choice,0)
                self.assertIn('Reopen',terminal.action_panel[1]);self.assertEqual(app.agent.history,[])
            finally:app.close()

    def test_manipulation_enters_tools_and_keeps_planning_after_motion_receipt(self):
        import json
        from model_fixture import call
        from terminal.app import App
        from terminal.config import load_config
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                calls=[call('load_toolset',name='robotics'),{'tool_calls':[{'id':'status','function':{'name':'simulator_status','arguments':'{}'}}]},
                       {'tool_calls':[{'id':'motion','function':{'name':'simulator_control','arguments':json.dumps({'action':'move_joints','robot':'panda','target':[0]*7,'duration':2})}}]},
                       {'content':'规划失败，需根据当前位置调整目标。'}]
                with patch.object(app.viewer,'status',return_value={'window_open':True}),patch.object(app.viewer,'command',return_value={'executed':False,'error':'Target unreachable'}) as command,patch.object(app.client,'complete',side_effect=calls) as model:
                    answer=app.agent.reply('控制机械臂抓取杯子')
                self.assertEqual(model.call_count,4)
                command.assert_called_once()
                self.assertIn('调整目标',answer)
            finally:app.close()
