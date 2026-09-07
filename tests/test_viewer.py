import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from terminal.app import App
from model_fixture import call
from terminal.config import load_config, ROOT
from terminal.viewer import SimulatorViewer
from toolchain.scenes import default_scene, compile_scene, physics_check, generate_scene


class ViewerTests(unittest.TestCase):
    def test_empty_table_custom_table_and_default_need_no_model(self):
        spec = default_scene(False)
        spec['table'] = {'size': [1.0, 0.6, 0.03], 'height': 0.75, 'color': [0.6, 0.4, 0.2, 1]}
        xml = compile_scene(spec)
        self.assertIn('table_leg_3', xml)
        self.assertIn('size="0.5 0.3 0.015"', xml)
        self.assertEqual(physics_check(xml)['physics_smoke'], 'pass')
        client = Mock()
        with tempfile.TemporaryDirectory() as d:
            result = generate_scene('生成一个桌面场景', client, client, d)
            self.assertEqual(result['model'], 'local-default')
            self.assertTrue(Path(result['scene']).exists())
            client.complete.assert_not_called()

    def test_missing_dependency_installs_fixed_packages(self):
        with tempfile.TemporaryDirectory() as d:
            viewer = SimulatorViewer(ROOT, d)
            with patch('terminal.viewer.subprocess.run', side_effect=[
                Mock(returncode=1), Mock(returncode=0), Mock(returncode=0, stdout='3.12.0\n')]) as run:
                _, version, installed = viewer.ensure_installed()
                self.assertTrue(installed)
                self.assertEqual(version, '3.12.0')
                self.assertEqual(run.call_args_list[1].args[0][-3:], ['install', 'mujoco>=3.3,<4', 'numpy>=1.26'])

    def test_no_display_never_reports_window_open(self):
        with tempfile.TemporaryDirectory() as d:
            viewer = SimulatorViewer(ROOT, d)
            with patch.object(viewer, 'ensure_installed', return_value=('python', '3.12', False)), patch.dict(os.environ, {}, clear=True):
                self.assertFalse(viewer.open(Path(d)/'scene.xml')['window_open'])
                self.assertFalse(viewer.status()['window_open'])

    def test_window_requires_readiness_and_live_process(self):
        with tempfile.TemporaryDirectory() as d:
            viewer = SimulatorViewer(ROOT, d)
            viewer.ready = Path(d)/'ready.json'
            viewer.process = Mock(pid=123)
            viewer.process.poll.return_value = None
            self.assertFalse(viewer.status()['window_open'])
            viewer.ready.write_text(json.dumps({'window_open': True, 'heartbeat': time.monotonic()}))
            self.assertTrue(viewer.status()['window_open'])
            viewer.process.poll.return_value = 1
            self.assertFalse(viewer.status()['window_open'])

    def test_stale_and_corrupt_heartbeat_never_claim_open(self):
        with tempfile.TemporaryDirectory() as d:
            viewer = SimulatorViewer(ROOT, d)
            viewer.ready = Path(d) / 'ready.json'
            viewer.process = Mock(pid=123)
            viewer.process.poll.return_value = None
            for value in ['{', 'null', '{"window_open":true}',
                          json.dumps({'window_open': True, 'heartbeat': time.monotonic() - 5}),
                          json.dumps({'window_open': False, 'heartbeat': time.monotonic()})]:
                viewer.ready.write_text(value)
                self.assertFalse(viewer.status()['window_open'])

    def test_restored_claims_do_not_implicitly_open_viewer(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                app.agent.history=[{'role':'assistant','content':'抓取demo已打开，PID 123'}]
                with patch.object(app.viewer,'open') as opened, patch.object(app.client,'complete',return_value={'content':'先检查实际状态。'}) as model:
                    self.assertEqual(app.agent.reply('是否可以模拟抓取方块？'),'先检查实际状态。')
                    opened.assert_not_called()
                    model.assert_called_once()
                with patch.object(app.viewer,'open',return_value={'window_open':True}) as opened, patch.object(app.client,'complete',side_effect=[call('load_toolset',name='robotics'),call('open_simulator'),{'content':'窗口已打开。'}]):
                    self.assertEqual(app.agent.reply('重新打开'),'窗口已打开。')
                    opened.assert_called_once()
            finally: app.close()

    def test_open_shortcut_uses_gui_and_respects_plan(self):
        with tempfile.TemporaryDirectory() as d:
            app=App(load_config(),d)
            try:
                with patch.object(app.viewer,'open',return_value={'window_open':True}) as opened, patch.object(app.client,'complete',side_effect=AssertionError('Slash uses explicit tools')):
                    app.dispatch('/viewer')
                    opened.assert_called_once()
                app.permissions.set_mode('plan')
                with self.assertRaises(PermissionError): app.dispatch('/viewer')
                with self.assertRaises(ValueError): app.scheduled_tool('open_simulator',{})
            finally: app.close()
