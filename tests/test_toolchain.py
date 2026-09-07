import importlib.util
from pathlib import Path
import tempfile
import time
import unittest

from loop_robot.toolchain.ego2mujoco import template_command
from loop_robot.toolchain.resources import ModelPool, ModelSpec
from loop_robot.toolchain.ros import JointStateBuffer
from loop_robot.toolchain.trajectory import edit_trajectory, sample_trajectory


class ToolchainTests(unittest.TestCase):
    def test_trajectory_edit_sample_and_no_mutation(self):
        source = [(3, [0, 0]), (4, [0.2, 0.4])]
        edited = edit_trajectory(source, [(-1, 1)] * 2, 0.3, time_scale=2)
        self.assertEqual(edited, [(0, [0, 0]), (2, [0.2, 0.4])])
        self.assertEqual(sample_trajectory(edited, 1, [(-1, 1)] * 2, 0.3), [0.1, 0.2])
        self.assertEqual(source[0][0], 3)
        with self.assertRaises(ValueError):
            edit_trajectory(source, [(-1, 1)] * 2, 0.1)

    def test_pool_lru_and_active_protection(self):
        unloaded = []
        pool = ModelPool(10, 10)
        for name in ("policy", "reviewer"):
            pool.register(name, ModelSpec(6, 6, lambda n=name: n, unloaded.append))
        with pool.lease("policy") as model:
            self.assertEqual(model, "policy")
            with self.assertRaises(MemoryError):
                with pool.lease("reviewer"):
                    pass
            with self.assertRaises(RuntimeError):
                pool.evict("policy")
        with pool.lease("reviewer"):
            self.assertEqual(unloaded, ["policy"])
        pool.close()
        self.assertEqual(pool.usage(), (0, 0))

    def test_pool_loader_failure_and_release_on_exception(self):
        pool = ModelPool(1, 0)
        def broken():
            raise RuntimeError("load failed")
        pool.register("bad", ModelSpec(1, 0, broken, lambda x: None))
        with self.assertRaises(RuntimeError):
            with pool.lease("bad"):
                pass
        self.assertEqual(pool.usage(), (0, 0))
        pool.register("ok", ModelSpec(1, 0, lambda: 1, lambda x: None))
        with self.assertRaises(ValueError):
            with pool.lease("ok"):
                raise ValueError("inference failed")
        pool.close()

    def test_ros_reorder_invalid_and_stale(self):
        state = JointStateBuffer(["a", "b"], "arm")
        state.update(["b", "a"], [2, 1])
        self.assertEqual(state.observe()["q"], [1, 2])
        state.latest["timestamp"] -= 1
        with self.assertRaises(RuntimeError):
            state.observe()
        with self.assertRaises(ValueError):
            state.update(["a"], [1])
        with self.assertRaises(RuntimeError):
            state.observe()

    def test_ego_bridge_missing_source(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                template_command(root, "python", root + "/missing.json", root + "/out")


@unittest.skipUnless(importlib.util.find_spec("mujoco"), "optional MuJoCo not installed")
class PhysicsTests(unittest.TestCase):
    def setUp(self):
        try:
            import mujoco
        except ImportError as exc:
            self.skipTest("optional MuJoCo environment incomplete: {}".format(exc))
        from loop_robot.toolchain.mujoco_sim import MujocoBody
        self.body = MujocoBody(Path(__file__).resolve().parents[1] / "assets/simulation/two_joint.xml",
                              {"j1": "a1", "j2": "a2"})

    def test_physics_loop_and_reset(self):
        from loop_robot.core.contracts import TaskSpec
        from loop_robot.toolchain.feedback import Loop
        from loop_robot.toolchain.feedback import FeedbackMaster, NumericalReviewer
        from loop_robot.core.store import EventStore
        store = EventStore(":memory:")
        try:
            review = Loop(self.body, FeedbackMaster(), NumericalReviewer(), store).run(
                TaskSpec("test", "sim-arm", (0.3, -0.2), tolerance=0.02))
            self.assertEqual(review.verdict, "pass")
            self.assertGreater(self.body.data.time, 0)
            self.assertEqual(self.body.reset()["q"], [0, 0])
        finally:
            store.close()

    def test_expiry_does_not_advance_physics(self):
        with self.assertRaises(TimeoutError):
            self.body.execute({"body_id": "sim-arm", "calibration_version": self.body.spec.calibration_version,
                               "target": [0, 0], "expires_at": time.monotonic() - 1})
        self.assertEqual(self.body.data.time, 0)

    @unittest.skipUnless(importlib.util.find_spec("mink"), "optional Mink not installed")
    def test_mink_fk_ik(self):
        import numpy as np
        from loop_robot.toolchain.kinematics import MinkKinematics
        ik = MinkKinematics(self.body.model, "tip", {"j1": 1.0, "j2": 1.0})
        target = ik.fk([0.1, -0.1])
        q = np.zeros(2)
        initial = np.linalg.norm(ik.fk(q) - target)
        for _ in range(100):
            q = ik.step(q, target)
        self.assertLess(np.linalg.norm(ik.fk(q) - target), initial)
        self.assertTrue(np.isfinite(q).all())


if __name__ == "__main__":
    unittest.main()
