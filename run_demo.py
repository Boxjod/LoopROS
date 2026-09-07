"""Run an offline feedback loop. Writes SQLite only to the selected output."""
import argparse
import json
from pathlib import Path

from core.contracts import TaskSpec, record
from core.loop import Loop
from core.plugins import FeedbackMaster, MockBody, NumericalReviewer
from core.store import EventStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/demo.sqlite")
    args = parser.parse_args()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    store = EventStore(path)
    try:
        task = TaskSpec("demo", "mock-arm", (0.4, -0.2), tolerance=0.11)
        result = Loop(MockBody(response=0.5), FeedbackMaster(),
                      NumericalReviewer(), store).run(task)
        print(json.dumps(record(result), ensure_ascii=False))
        return 0 if result.verdict == "pass" else 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
