"""Headless physics -> existing Agent Loop -> numerical Review smoke demo."""
from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from launcher import _bootstrap
_bootstrap(legacy=False)

from loop_robot.core.contracts import TaskSpec, record
from loop_robot.toolchain.feedback import Loop
from loop_robot.toolchain.feedback import FeedbackMaster, NumericalReviewer
from loop_robot.core.store import EventStore
from loop_robot.toolchain.mujoco_sim import MujocoBody


def main():
    body = MujocoBody(Path(__file__).resolve().parents[1] / "assets/simulation/two_joint.xml",
                      {"j1": "a1", "j2": "a2"})
    store = EventStore(":memory:")
    try:
        result = Loop(body, FeedbackMaster(), NumericalReviewer(), store).run(
            TaskSpec("physics-demo", "sim-arm", (0.3, -0.2), tolerance=0.02))
        print(json.dumps({"review": record(result), "timing": body.last_timing}))
        return 0 if result.verdict == "pass" else 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
