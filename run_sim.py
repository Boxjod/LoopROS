"""Headless physics -> existing Agent Loop -> numerical Review smoke demo."""
from pathlib import Path
import json

from core.contracts import TaskSpec, record
from core.loop import Loop
from core.plugins import FeedbackMaster, NumericalReviewer
from core.store import EventStore
from toolchain.mujoco_sim import MujocoBody


def main():
    body = MujocoBody(Path(__file__).parent / "examples/two_joint.xml",
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
