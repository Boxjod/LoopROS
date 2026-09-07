import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from loop_robot.toolchain.robot_engineering import current_to_torque,pid_trial
from loop_robot.toolchain.robot_model_analysis import analyze
from loop_robot.terminal.robotics import diagnose,docs,ROBOT_NAMES
from loop_robot.terminal.app import App
from loop_robot.terminal.config import load_config,ROOT

TORQUE={'current_A':2,'kt_Nm_per_A':.1,'current_basis':'iq_peak','kt_current_basis':'iq_peak','gear_ratio':10,'efficiency':.9}
PID={'kp':10,'ki':1,'kd':2,'inertia_kg_m2':.05,'damping_Nm_s_per_rad':.1,'torque_limit_Nm':2,'target_rad':1}

class EngineeringTests(unittest.TestCase):
    def test_torque_units_direction_and_missing_definitions(self):
        r=current_to_torque(TORQUE)
        self.assertAlmostEqual(r['motor_torque_Nm'],.2)
        self.assertAlmostEqual(r['output_torque_Nm'],1.8)
        self.assertFalse(r['hardware_command_sent'])
        self.assertAlmostEqual(current_to_torque({**TORQUE,'current_A':-2})['output_torque_Nm'],-1.8)
        self.assertAlmostEqual(current_to_torque({**TORQUE,'current_offset_A':.1})['motor_torque_Nm'],.19)
        for changed in ({'current_basis':'dc_bus'},{'current_basis':'phase_rms'},{'current_A':float('nan')},{'efficiency':1.5},{'gear_ratio':0}):
            with self.assertRaises(ValueError): current_to_torque({**TORQUE,**changed})
        with self.assertRaises(ValueError):current_to_torque({k:v for k,v in TORQUE.items() if k!='kt_Nm_per_A'})

    def test_pid_saturation_bounded_integrator_and_finite_step_response(self):
        r=pid_trial(PID)
        self.assertLess(abs(r['final_error_rad']),.02)
        self.assertLess(r['overshoot_rad'],.02)
        self.assertTrue(all(abs(x['torque_Nm'])<=2 for x in r['samples']))
        saturated=pid_trial({**PID,'target_rad':10000,'torque_limit_Nm':.01})
        self.assertTrue(all(row['integral_torque_Nm']==0 for row in saturated['samples']))
        no_kick=pid_trial({**PID,'kp':0,'ki':0})
        self.assertEqual(no_kick['samples'][0]['torque_Nm'],0)
        for changed in ({'dt_s':0},{'inertia_kg_m2':-1},{'kp':float('inf')}):
            with self.assertRaises(ValueError):pid_trial({**PID,**changed})

    def test_model_jacobian_finite_difference_and_dynamics_residual(self):
        import numpy as np
        import mujoco
        path=ROOT/'assets/simulation/two_joint.xml'
        model=mujoco.MjModel.from_xml_path(str(path));body=model.body(model.nbody-1).name
        q=[.2,-.3];velocity=[.1,-.1];acc=[.2,.4]
        fk=analyze(path,'kinematics',body=body,qpos=q)
        step=1e-6
        for j in range(2):
            modified=q.copy();modified[j]+=step
            other=analyze(path,'kinematics',body=body,qpos=modified)
            derivative=(np.array(other['world_position_m'])-fk['world_position_m'])/step
            np.testing.assert_allclose(derivative,np.array(fk['jacobian_linear'])[:,j],atol=1e-5)
        dynamics=analyze(path,'dynamics',qpos=q,qvel=velocity,qacc=acc)
        mass=np.array(dynamics['mass_matrix'])
        np.testing.assert_allclose(mass,mass.T)
        self.assertTrue((np.linalg.eigvalsh(mass)>0).all())
        force=mass@acc+np.array(dynamics['bias_force'])-dynamics['passive_force']-np.array(dynamics['constraints_force'])
        np.testing.assert_allclose(force,dynamics['inverse_generalized_force'],atol=1e-8)
        wrench=[1,2,3,.1,.2,.3]
        r=analyze(path,'wrench_to_joint',body=body,qpos=q,world_wrench=wrench)
        expected=np.array(fk['jacobian_linear']).T@wrench[:3]+np.array(fk['jacobian_angular']).T@wrench[3:]
        np.testing.assert_allclose(r['generalized_load'],expected)
        with self.assertRaises(ValueError):analyze(path,'kinematics',body='invented')
        with self.assertRaises(ValueError):analyze(path,'dynamics',qpos=[0])

    def test_diagnostics_do_not_claim_model_identification_or_verified_root_cause(self):
        r=diagnose('CAN bus-off; encoder timeout',transport='CAN',error_code='0x1234')
        self.assertEqual(r['verdict'],'inconclusive')
        self.assertIn('model',r['missing_context'])
        self.assertFalse(r['error_code_decoded'])
        self.assertEqual({x['category'] for x in r['findings']},{'bus_off','encoder','timeout'})

    def test_official_document_search_filters_version_and_caches(self):
        with tempfile.TemporaryDirectory() as d,patch('loop_robot.terminal.robotics.web_dispatch',return_value={'results':[{'url':'https://evil.example/manual'}]}),patch('loop_robot.terminal.robotics.request',return_value={'url':'https://control.ros.org/jazzy/','body':'<h1>PID</h1><p>antiwindup reference</p>','retrieved_at':'now'}) as fetch:
            r=docs(d,'ros2_control','PID',version='jazzy')
            self.assertIn('antiwindup',r['text'])
            fetch.assert_called_once_with('https://control.ros.org/jazzy/')
            docs(d,'ros2_control','PID',version='jazzy');self.assertEqual(fetch.call_count,1)
            with self.assertRaises(ValueError):docs(d,'ros2_control',version='../../private')

    def test_tools_permissions_and_reports_do_not_actuate(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                with patch.object(app.serial,'open',side_effect=AssertionError('no connection')),patch.object(app.viewer,'command',side_effect=AssertionError('no actuation')):
                    result=app.tool('motor_torque',TORQUE)
                    self.assertTrue(Path(result['report']).exists())
                    trial=app.tool('pid_trial',PID)
                    self.assertEqual(trial['sample_count'],3000)
                    self.assertLess(len(trial['samples_preview']),40)
                    self.assertFalse(app.tool('robot_diagnose',{'observation':'encoder timeout'})['hardware_command_sent'])
                    self.assertEqual(app.tool('robot_toolchains',{})['integration']['motor_write_drivers'],'feetech_sts3215_host_primitive; not exposed to terminal')
                app.permissions.set_rule('motor_torque','deny')
                with self.assertRaises(PermissionError):app.tool('motor_torque',TORQUE)
                app.permissions.set_mode('plan')
                with self.assertRaises(PermissionError):app.tool('pid_trial',PID)
                app.permissions.set_rule('motor_torque','allow')
                self.assertAlmostEqual(app.tool('motor_torque',TORQUE)['output_torque_Nm'],1.8)
            finally:app.close()
