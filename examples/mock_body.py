"""Offline demo/test body; not part of the installed runtime."""
import math
import time
from loop_robot.core.contracts import Capability, EmbodimentSpec
from loop_robot.toolchain.trajectory import validate_target


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


