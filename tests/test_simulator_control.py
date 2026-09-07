import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from terminal.app import App
from terminal.config import load_config
from toolchain.model_assets import snapshot
from toolchain.viewer_control import SimulationControl


class SimulatorControlTests(unittest.TestCase):
    def test_physics_pause_step_reset_actuators_and_bounds(self):
        import mujoco
        model = mujoco.MjModel.from_xml_string('<mujoco><worldbody><body><joint name="j" type="hinge"/><geom type="capsule" size=".03 .2"/></body></worldbody><actuator><position joint="j" kp="10" ctrllimited="true" ctrlrange="-1 1"/></actuator></mujoco>')
        data = mujoco.MjData(model)
        control = SimulationControl(mujoco, model, data)
        with self.assertRaises(ValueError):
            control.apply({'action': 'step', 'steps': 10}, None)
        control.apply({'action': 'pause'}, None)
        control.apply({'action': 'actuate', 'values': [.5]}, None)
        control.apply({'action': 'step', 'steps': 100}, None)
        self.assertAlmostEqual(data.time, model.opt.timestep * 100)
        self.assertGreater(data.qpos[0], 0)
        for values in ([2], [float('nan')], [0, 0], []):
            with self.assertRaises(ValueError):
                control.apply({'action': 'actuate', 'values': values}, None)
            self.assertEqual(data.ctrl[0], .5)
        control.apply({'action': 'reset'}, None)
        self.assertTrue(control.paused)
        self.assertEqual(data.time, 0)
        self.assertEqual(data.ctrl[0], 0)

    def test_autoopen_all_generation_paths_and_permission_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            app = App(load_config(), directory)
            try:
                with patch.object(app.viewer, 'open', return_value={'window_open': True, 'model_bodies': ['chair']}) as opened:
                    result = app.tool('generate_scene', {'description': '生成一个椅子'})
                    self.assertTrue(result['viewer']['window_open'])
                    opened.assert_called_once_with(app.latest_scene, force=True)
                    app.dispatch('/scene 生成一个椅子')
                    self.assertEqual(opened.call_count, 2)
                    app.permissions.set_rule('open_simulator', 'deny')
                    result = app.scene('生成一个椅子')
                    self.assertFalse(result['viewer']['window_open'])
                    self.assertTrue(Path(result['scene']).exists())
                    self.assertEqual(opened.call_count, 2)
                for tool, args in [('generate_scene', {'description': '椅子'}), ('simulator_control', {'action': 'resume'}), ('load_model', {'model': 'dynamixel_2r'})]:
                    with self.assertRaises(ValueError):
                        app.scheduled_tool(tool, args)
                app.permissions.set_mode('plan')
                for tool, args in [('simulator_control', {'action': 'resume'}), ('load_model', {'model': 'dynamixel_2r'})]:
                    with self.assertRaises(PermissionError):
                        app.tool(tool, args)
            finally:
                app.close()

    def test_vfs_includes_and_asset_integrity(self):
        import mujoco
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {'scene.xml': '<mujoco><include file="robot.xml"/></mujoco>',
                     'robot.xml': '<mujoco><worldbody><body name="robot"><geom size=".1"/></body></worldbody></mujoco>'}
            hashes = {}
            for name, xml in files.items():
                (root/name).write_text(xml)
                hashes[name] = hashlib.sha256(xml.encode()).hexdigest()
            (root/'.loop-assets.json').write_text(json.dumps({'files': hashes}))
            xml, assets, digest = snapshot(root/'scene.xml')
            self.assertEqual(mujoco.MjModel.from_xml_string(xml.decode(), assets=assets).nbody, 2)
            (root/'robot.xml').write_text(files['robot.xml'].replace('robot', 'changed'))
            with self.assertRaisesRegex(ValueError, 'checksum'):
                snapshot(root/'scene.xml')
            hashes['../outside'] = '0'
            (root/'.loop-assets.json').write_text(json.dumps({'files': hashes}))
            with self.assertRaises(ValueError):
                snapshot(root/'scene.xml')

    def test_closed_viewer_cannot_acknowledge_control(self):
        from terminal.viewer import SimulatorViewer
        with tempfile.TemporaryDirectory() as directory:
            viewer = SimulatorViewer('.', directory)
            self.assertFalse(viewer.command(action='pause')['executed'])
