import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from terminal.app import App
from model_fixture import call
from terminal.config import load_config
from toolchain.scenes import chair_scene, compile_scene, save_chair_scene


class ChairSceneTests(unittest.TestCase):
    def test_chair_geometry_no_unrequested_table_or_cube_and_recompilation(self):
        import mujoco
        with tempfile.TemporaryDirectory() as directory:
            result = save_chair_scene(directory)
            path = Path(result['scene'])
            xml = path.read_text()
            self.assertEqual(result['scene_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            spec = json.loads(path.with_name('scene.json').read_text())
            self.assertEqual(compile_scene(spec), xml)
            root = ET.fromstring(xml)
            geoms = root.findall('.//body[@name="chair"]/geom')
            self.assertEqual(len(geoms), 6)
            self.assertEqual(root.find('.//geom[@name="chair_back"]').get('pos'), '0 0.205 0.65')
            self.assertIsNone(root.find('.//geom[@name="table"]'))
            self.assertIsNone(root.find('.//body[@name="cube"]'))
            model = mujoco.MjModel.from_xml_string(xml)
            self.assertEqual(model.nbody, 2)
            self.assertEqual(model.ngeom, 7)
            self.assertIn('table', compile_scene(chair_scene(True)))

    def test_model_generation_and_correction_call_real_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            app=App(load_config(),directory)
            try:
                responses=[call('load_toolset',name='robotics'),call('generate_scene',description='生成一个椅子'),{'content':'场景已保存。'},call('load_toolset',name='robotics'),call('generate_scene',description='生成一个椅子'),{'content':'已重新生成。'}]
                with patch.object(app.viewer,'open',return_value={'window_open':True,'model_bodies':['chair']}) as opened, patch.object(app.client,'complete',side_effect=responses):
                    self.assertEqual(app.agent.reply('生成一个椅子'),'场景已保存。')
                    original=app.latest_scene
                    self.assertTrue(original.exists())
                    self.assertEqual(app.agent.reply('不是椅子的，请你修'),'已重新生成。')
                    self.assertNotEqual(app.latest_scene,original)
                    self.assertEqual(opened.call_count,2)
                    self.assertEqual(set(app.scene_objects()),{'chair'})
            finally: app.close()

    def test_failed_generation_does_not_open_previous_scene_as_new(self):
        with tempfile.TemporaryDirectory() as directory:
            app = App(load_config(), directory)
            try:
                app.scene('生成一个椅子')
                with patch('toolchain.scenes.generate_scene', side_effect=ValueError('unsupported requested chair')):
                    with self.assertRaises(ValueError):
                        app.scene('生成一个折叠椅')
                with patch.object(app.viewer, 'open') as opened:
                    state = app.tool('open_simulator', {})
                    self.assertFalse(state['window_open'])
                    opened.assert_not_called()
            finally:
                app.close()
