"""Reference plugins: numerical reviewer and simulated joint body only."""
import math
import time

from core.contracts import Capability, EmbodimentSpec, Review
from toolchain.trajectory import validate_target


class MockBody:
    capability = Capability("mock_joint_target", "1", "position")

    def __init__(self, body_id="mock-arm", response=1.0):
        if not math.isfinite(response) or not 0 < response <= 1:
            raise ValueError("response must be in (0, 1]")
        self.spec = EmbodimentSpec(body_id, "mock-cal-v1", ((-1.0, 1.0),) * 2,
                                  ("joint_position",))
        self.q = [0.0, 0.0]
        self.response = response
        self.stopped = True

    def observe(self):
        return {"body_id": self.spec.body_id, "q": list(self.q),
                "timestamp": time.monotonic(), "modalities": list(self.spec.modalities)}

    def execute(self, action):
        if action["body_id"] != self.spec.body_id:
            raise ValueError("wrong body")
        if action["calibration_version"] != self.spec.calibration_version:
            raise ValueError("stale calibration")
        if time.monotonic() >= action["expires_at"]:
            raise ValueError("expired action")
        validate_target(action["target"], self.spec.limits)
        self.stopped = False
        self.q = [q + self.response * (target - q)
                  for q, target in zip(self.q, action["target"])]

    def stop(self):
        self.stopped = True


class NumericalReviewer:
    version = "joint-error-v1"

    def review(self, task, episode):
        if episode.error:
            return Review("inconclusive", 0.0, episode.error)
        if len(episode.observations) < 2:
            return Review("inconclusive", 0.0, "missing before/after evidence")
        for obs in episode.observations:
            if obs.get("body_id") != task.body_id:
                return Review("inconclusive", 0.0, "wrong-body evidence")
            if not set(task.required_modalities).issubset(obs.get("modalities", [])):
                return Review("inconclusive", 0.0, "required modality missing")
            q = obs.get("q", [])
            if len(q) != len(task.target) or not all(math.isfinite(x) for x in q):
                return Review("inconclusive", 0.0, "invalid joint evidence")
        error = max(abs(q - target) for q, target in
                    zip(episode.observations[-1]["q"], task.target))
        passed = error <= task.tolerance
        return Review("pass" if passed else "fail", 1.0 if passed else 0.0,
                      "target reached" if passed else "tracking error",
                      {"max_joint_error_rad": error}, "stop" if passed else "reobserve")


class FeedbackMaster:
    """Deterministic reference policy, not a language model or trained policy."""

    def plan(self, task, observation, previous_review):
        if previous_review is not None and previous_review.next_step != "reobserve":
            return None
        return list(task.target)
