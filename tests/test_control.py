import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from loop_robot.terminal.app import App
from loop_robot.terminal.config import load_config
from loop_robot.terminal.permissions import PermissionGate


class ControlTests(unittest.TestCase):
    def test_permission_profiles_and_custom_rules(self):
        gate = self.app.permissions
        self.app.dispatch('/permissions plan')
        with self.assertRaises(PermissionError): gate.check('run_sim', {})
        self.app.dispatch('/permissions yolo')
        self.assertEqual(gate.snapshot()['profile'], 'yolo')
        self.assertEqual(gate.snapshot()['mode'], 'sim')
        self.assertEqual(gate.snapshot()['real_hardware'], 'disabled')
        for action in gate.snapshot()['rules']: gate.check(action, {})
        self.app.dispatch('/permissions deny run_sim')
        self.assertEqual(gate.snapshot()['profile'], 'custom')
        with self.assertRaises(PermissionError): gate.check('run_sim', {})
        self.app.dispatch('/permissions cautious')
        with self.assertRaisesRegex(PermissionError, 'Approval required'): gate.check('devices', {})
        self.app.dispatch('/permissions default')
        self.assertEqual(gate.snapshot()['profile'], 'default')
        gate.check('devices', {})
        with self.assertRaises(PermissionError): gate.check('skill_write', {})
        with self.assertRaises(ValueError): self.app.dispatch('/permissions yolo', scheduled=True)
        self.assertEqual(PermissionGate(gate.path).snapshot()['profile'], 'default')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = App(load_config(), self.temp.name, confirm=lambda text: True)

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_inventory_and_diagnostics(self):
        data = json.loads(self.app.dispatch("/commands"))
        self.assertEqual(data["entries"], len(data["commands"]))
        self.assertIn("/fast", data["commands"])
        self.assertIn("/node", data["commands"])
        self.assertEqual(len(data["commands"]), len(set(data["commands"])))
        for command in ("/permissions", "/mode", "/tools", "/doctor", "/config", "/context", "/history", "/robot", "/joints"):
            self.assertTrue(self.app.dispatch(command))

    def test_plan_blocks_shortcuts_and_tools(self):
        self.app.dispatch("/plan")
        for command in ("/sim", "/move 0 0", "/home", "/scene 红方块", "/spawn Worker run"):
            with self.assertRaises(PermissionError):
                self.app.dispatch(command)
        with self.assertRaises(PermissionError):
            self.app.tool("run_sim", {})
        self.app.dispatch("/mode real")
        self.assertEqual(self.app.permissions.snapshot()["mode"], "real")
        self.assertEqual(self.app.permissions.snapshot()["real_hardware"], "driver_required")

    def test_ask_approve_exactly_once(self):
        self.app.dispatch("/permissions ask devices")
        with self.assertRaises(PermissionError):
            self.app.dispatch("/devices")
        request_id = next(iter(self.app.permissions.requests()))
        with patch("loop_robot.terminal.app.list_devices", return_value={"opened": False}):
            self.assertFalse(json.loads(self.app.dispatch("/approve " + request_id))["opened"])
        with self.assertRaisesRegex(ValueError, "Approval ID not found"):
            self.app.dispatch("/approve " + request_id)
        with self.assertRaises(PermissionError):
            self.app.tool("devices", {})

    def test_approval_does_not_override_deny(self):
        self.app.dispatch("/permissions ask devices")
        with self.assertRaises(PermissionError):
            self.app.dispatch("/devices")
        request_id = next(iter(self.app.permissions.requests()))
        self.app.dispatch("/permissions deny devices")
        with self.assertRaises(PermissionError):
            self.app.dispatch("/approve " + request_id)

    def test_approval_preserves_complex_scene_args(self):
        self.app.dispatch("/permissions ask generate_scene")
        with self.assertRaises(PermissionError):
            self.app.dispatch("/scene --complex 六个方块")
        request_id = next(iter(self.app.permissions.requests()))
        (Path(self.temp.name) / "scene.xml").write_text("<mujoco><worldbody/></mujoco>")
        with patch("loop_robot.toolchain.scenes.generate_scene", return_value={"scene": str(Path(self.temp.name) / "scene.xml")}) as generate:
            self.app.dispatch("/approve " + request_id)
            self.assertTrue(generate.call_args[0][-1])

    def test_persistent_rules_and_compaction(self):
        self.app.dispatch("/permissions deny spawn_agent")
        other = PermissionGate(Path(self.temp.name) / "permissions.sqlite")
        self.assertEqual(other.snapshot()["rules"]["spawn_agent"], "deny")
        self.app.agent.history = [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(12)]
        self.app.dispatch("/compact")
        self.assertEqual(len(self.app.agent.history), 12)
        self.assertEqual(self.app.agent.history_message_limit, 8)

    def test_hidden_policy_tool_requires_approval(self):
        with self.assertRaises(PermissionError):
            self.app.tool("policy_start", {"name": "act"})
        self.assertEqual(self.app.services.status()["act"], "NOT_CONFIGURED")

    def test_sim_move_home_and_stop(self):
        try:
            import mujoco
        except ImportError:
            self.skipTest("optional simulation unavailable")
        self.assertEqual(json.loads(self.app.dispatch("/move 0.2 -0.1"))["review"]["verdict"], "pass")
        self.assertAlmostEqual(json.loads(self.app.dispatch("/joints"))["q"][0], 0.2, delta=0.02)
        self.assertEqual(json.loads(self.app.dispatch("/home"))["review"]["verdict"], "pass")
        self.app.dispatch("/stop")
        with self.assertRaises(PermissionError):
            self.app.dispatch("/move 0 0")
        self.assertTrue(self.app.motion_stop.is_set())
        self.app.dispatch("/permissions allow move_sim")
        self.assertFalse(self.app.motion_stop.is_set())


if __name__ == "__main__":
    unittest.main()
