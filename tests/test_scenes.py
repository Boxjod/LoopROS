import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from loop_robot.toolchain.scenes import compile_scene, generate_scene, physics_check, validate_scene


SPEC = {"objects": [
    {"name": "red_cube", "shape": "box", "size": [0.06, 0.06, 0.06],
     "position": [-0.15, 0, 0.78], "color": [1, 0, 0, 1], "mass": 0.1},
    {"name": "blue_ball", "shape": "sphere", "size": [0.03],
     "position": [0.15, 0, 0.78], "color": [0, 0, 1, 1], "mass": 0.1}],
    "assumptions": ["默认桌面高度0.75m"], "unsupported": [], "needs_expert": False}


class Client:
    def __init__(self, spec, model="qwen-plus"):
        self.spec, self.config, self.calls = spec, {"model": model}, 0
    def complete(self, messages, tools):
        self.calls += 1
        return {"content": json.dumps(self.spec)}


class SceneTests(unittest.TestCase):
    def test_compile_is_asset_free(self):
        xml = compile_scene(SPEC)
        self.assertIn('type="sphere"', xml)
        self.assertNotIn("<include", xml)
        self.assertNotIn("file=", xml)

    def test_invalid_geometry_rejected(self):
        for changes in ({"size": [float("nan"), 0.1, 0.1]}, {"name": "../x"},
                        {"position": [0, 0, 0]}, {"shape": "mesh"}):
            spec = copy.deepcopy(SPEC)
            spec["objects"][0].update(changes)
            with self.assertRaises(ValueError):
                validate_scene(spec)

    def test_overlap_and_unsupported_rejected(self):
        spec = copy.deepcopy(SPEC)
        spec["objects"][1]["position"] = spec["objects"][0]["position"]
        with self.assertRaises(ValueError):
            validate_scene(spec)
        spec = {**SPEC, "unsupported": ["articulated drawer"]}
        with self.assertRaises(ValueError):
            compile_scene(spec)

    def test_simple_route(self):
        primary, expert = Client(SPEC), Client(SPEC, "gpt-6-astra")
        with tempfile.TemporaryDirectory() as root, patch("loop_robot.toolchain.scenes.physics_check", return_value={"compiled": True}):
            result = generate_scene("红方块和蓝球", primary, expert, root)
            self.assertTrue(Path(result["scene"]).is_file())
            self.assertEqual((primary.calls, expert.calls), (1, 0))

    def test_complex_and_legacy_hint_use_current_model(self):
        for explicit in (True, False):
            primary = Client({**SPEC, "needs_expert": True})
            expert = Client(SPEC, "gpt-6-astra")
            with tempfile.TemporaryDirectory() as root, patch("loop_robot.toolchain.scenes.physics_check", return_value={}):
                result = generate_scene("复杂布局", primary, expert, root, explicit)
                self.assertFalse(result["expert_used"])
                self.assertEqual(expert.calls, 0)
                self.assertEqual(primary.calls, 1)

    def test_current_model_unsupported_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                generate_scene("抽屉", Client({**SPEC, "unsupported": ["drawer"]}), Client(SPEC), root, True)
            reports = list(Path(root).glob("*/report.json"))
            self.assertEqual(len(reports), 1)
            self.assertFalse(json.loads(reports[0].read_text())["validation"]["compiled"])
            self.assertEqual(list(Path(root).glob("*/scene.xml")), [])

    def test_real_mujoco_compilation(self):
        try:
            import mujoco
        except ImportError:
            self.skipTest("MuJoCo environment unavailable")
        result = physics_check(compile_scene(SPEC))
        self.assertEqual(result["physics_smoke"], "pass")
        self.assertEqual(result["semantic_verdict"], "unverified")

    def test_repairs_json_and_geometry_with_actual_feedback(self):
        valid = copy.deepcopy(SPEC)
        valid["objects"] = [{"name": "red_cube", "shape": "box", "size": [0.15]*3,
                             "position": [0, 0, 0.825], "color": [1, 0, 0, 1], "mass": 0.1}]
        invalid = copy.deepcopy(valid)
        invalid["objects"][0]["position"][2] = 0
        primary, expert = Client(valid), Client(valid, "expert")
        responses = [{"content": text} for text in ('not JSON', json.dumps(invalid), json.dumps(valid))]
        with tempfile.TemporaryDirectory() as root, patch.object(primary, 'complete', side_effect=responses) as complete:
            result = generate_scene('桌子上一个方块', primary, expert, root)
            self.assertEqual(result['validation']['physics_smoke'], 'pass')
            self.assertEqual(len(result['attempts']), 3)
            self.assertEqual(expert.calls, 0)
            import mujoco
            model = mujoco.MjModel.from_xml_path(result['scene'])
            data = mujoco.MjData(model)
            for _ in range(250):
                mujoco.mj_step(model, data)
            self.assertAlmostEqual(float(data.qpos[2]), 0.825, delta=0.001)
            self.assertGreater(data.ncon, 0)
            feedback = complete.call_args.args[0]
            self.assertTrue(any('scene_json' in m['content'] for m in feedback))
            self.assertTrue(any('bottom z must be >=0.75' in m['content'] for m in feedback))
            self.assertEqual(json.loads(Path(result['scene']).with_name('scene.json').read_text())['objects'], valid['objects'])

    def test_fenced_json_and_bounded_failure(self):
        from loop_robot.toolchain.scenes import parse_scene, SceneGenerationError
        self.assertEqual(parse_scene('```json\n' + json.dumps(SPEC) + '\n```'), SPEC)
        client = Client(SPEC)
        with tempfile.TemporaryDirectory() as root, patch.object(client, 'complete', return_value={'content': '{'}) as complete:
            with self.assertRaises(SceneGenerationError) as error:
                generate_scene('一个方块', client, client, root)
            self.assertEqual(complete.call_count, 3)
            self.assertEqual(error.exception.details['stage'], 'scene_json')
            self.assertFalse(error.exception.details['retryable'])
            self.assertTrue(Path(error.exception.details['report']).exists())
            self.assertEqual(list(Path(root).glob('*/scene.xml')), [])

    def test_missing_expert_and_cancellation_do_not_retry(self):
        import threading
        from loop_robot.toolchain.scenes import SceneGenerationError
        client = Client(SPEC)
        with tempfile.TemporaryDirectory() as root, patch.object(client, 'complete', side_effect=RuntimeError('Missing expert key')) as complete:
            with self.assertRaises(SceneGenerationError) as error:
                generate_scene('方块', client, client, root, True)
            self.assertEqual(complete.call_count, 1)
            self.assertEqual(error.exception.details['stage'], 'model_request')
        stop = threading.Event()
        def cancel(*args):
            stop.set()
            return {'content': '{'}
        with tempfile.TemporaryDirectory() as root, patch.object(client, 'complete', side_effect=cancel) as complete:
            with self.assertRaisesRegex(RuntimeError, 'Master stopped'):
                generate_scene('方块', client, client, root, stop_event=stop)
            self.assertEqual(complete.call_count, 1)


if __name__ == "__main__":
    unittest.main()
