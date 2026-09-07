import time
import unittest
from dataclasses import replace

from core.contracts import TaskSpec
from core.loop import Loop
from core.plugins import FeedbackMaster, MockBody, NumericalReviewer
from core.store import EventStore
from toolchain.trajectory import validate_trajectory


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.store = EventStore(":memory:")
        self.body = MockBody()
        self.task = TaskSpec("test", "mock-arm", (0.4, -0.2))

    def tearDown(self):
        self.store.close()

    def run_loop(self, task=None, reviewer=None, master=None):
        return Loop(self.body, master or FeedbackMaster(), reviewer or NumericalReviewer(),
                    self.store).run(task or self.task)

    def test_success_records_evidence_and_candidate(self):
        self.assertEqual(self.run_loop().verdict, "pass")
        self.assertTrue(self.body.stopped)
        self.assertEqual([k for k, _ in self.store.events()],
                         ["task", "action_intent", "episode", "review", "candidate"])
        self.assertEqual(self.store.events()[-1][1]["status"], "proposed")

    def test_feedback_reaches_master(self):
        self.body.response = 0.5
        received = []

        class SpyMaster(FeedbackMaster):
            def plan(self, task, observation, previous_review):
                received.append(previous_review)
                return super().plan(task, observation, previous_review)

        result = self.run_loop(replace(self.task, tolerance=0.11), master=SpyMaster())
        self.assertEqual(result.verdict, "pass")
        self.assertEqual(received[1].verdict, "fail")
        self.assertEqual(len(received), 2)

    def test_missing_camera_blocks_visual_task_not_joint_task(self):
        result = self.run_loop(replace(self.task, required_modalities=("rgb",)))
        self.assertEqual(result.verdict, "inconclusive")
        self.assertFalse(any(k == "action_intent" for k, _ in self.store.events()))
        self.assertEqual(self.body.q, [0, 0])

    def test_wrong_body_rejected(self):
        with self.assertRaises(ValueError):
            self.run_loop(replace(self.task, body_id="other"))

    def test_real_body_rejected(self):
        self.body.spec = replace(self.body.spec, simulated=False)
        with self.assertRaises(ValueError):
            self.run_loop()

    def test_limits_and_nan_rejected(self):
        for target in ((2, 0), (float("nan"), 0), (0,)):
            with self.assertRaises(ValueError):
                self.run_loop(replace(self.task, target=target))

    def test_budget_is_bounded(self):
        self.body.response = 0.1
        self.assertEqual(self.run_loop().verdict, "fail")
        self.assertEqual(sum(k == "review" for k, _ in self.store.events()), 2)

    def test_execution_error_stops_and_reviews(self):
        def broken(action):
            raise RuntimeError("disconnected")
        self.body.execute = broken
        self.assertEqual(self.run_loop().verdict, "inconclusive")
        self.assertTrue(self.body.stopped)

    def test_reviewer_error_is_not_success(self):
        class BrokenReviewer:
            version = "broken"
            def review(self, task, episode):
                raise RuntimeError("offline")
        self.assertEqual(self.run_loop(reviewer=BrokenReviewer()).verdict, "inconclusive")

    def test_expired_and_stale_actions(self):
        action = {"body_id": "mock-arm", "calibration_version": "mock-cal-v1",
                  "target": [0, 0], "expires_at": time.monotonic() - 1}
        with self.assertRaises(ValueError):
            self.body.execute(action)
        action.update(expires_at=time.monotonic() + 5, calibration_version="old")
        with self.assertRaises(ValueError):
            self.body.execute(action)

    def test_trajectory_checks(self):
        self.assertTrue(validate_trajectory([(0, [0, 0]), (1, [0.2, 0])],
                                            self.body.spec.limits, 0.5))
        for points in ([(0, [0, 0]), (0, [0.1, 0])],
                       [(0, [0, 0]), (0.1, [0.8, 0])]):
            with self.assertRaises(ValueError):
                validate_trajectory(points, self.body.spec.limits, 0.5)


if __name__ == "__main__":
    unittest.main()
