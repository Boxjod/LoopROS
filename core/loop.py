import math
import time
import uuid

from core.contracts import Candidate, Episode, Review, record
from toolchain.trajectory import validate_target


class Loop:
    """Bounded execute -> evidence -> review -> Master feedback loop.

    M1 intentionally admits simulated bodies only. Not a real-time controller.
    """

    def __init__(self, body, master, reviewer, store):
        self.body, self.master, self.reviewer, self.store = body, master, reviewer, store

    def run(self, task):
        if not self.body.spec.simulated:
            raise ValueError("M1 runtime only admits simulated bodies")
        if task.body_id != self.body.spec.body_id:
            raise ValueError("task/body mismatch")
        validate_target(task.target, self.body.spec.limits)
        if (not isinstance(task.max_attempts, int) or task.max_attempts < 1
                or not math.isfinite(task.timeout_s) or task.timeout_s <= 0
                or not math.isfinite(task.tolerance) or task.tolerance <= 0):
            raise ValueError("invalid task budget or tolerance")
        deadline = time.monotonic() + task.timeout_s
        session = uuid.uuid4().hex
        review = None
        self.store.append("task", {**record(task), "session_id": session,
                                   "reviewer_version": self.reviewer.version})
        for attempt in range(1, task.max_attempts + 1):
            episode = Episode(task.task_id, attempt, task.body_id,
                              self.body.spec.calibration_version)
            try:
                if time.monotonic() >= deadline:
                    raise TimeoutError("task deadline exceeded")
                before = self.body.observe()
                episode.observations.append(before)
                if not set(task.required_modalities).issubset(before.get("modalities", [])):
                    raise ValueError("required modality missing; no action admitted")
                target = self.master.plan(task, before, review)
                if target is None:
                    raise ValueError("Master declined further action")
                validate_target(target, self.body.spec.limits)
                action = {"body_id": task.body_id, "session_id": session,
                          "calibration_version": episode.calibration_version,
                          "target": target, "expires_at": deadline}
                self.store.append("action_intent", action)
                episode.actions.append(action)
                self.body.execute(action)
                episode.observations.append(self.body.observe())
                if time.monotonic() >= deadline:
                    raise TimeoutError("task deadline exceeded")
            except Exception as exc:
                episode.error = "{}: {}".format(type(exc).__name__, exc)
            finally:
                try:
                    self.body.stop()
                except Exception as exc:
                    episode.error = "stop failed: {}".format(exc)
            self.store.append("episode", record(episode))
            try:
                review = self.reviewer.review(task, episode)
                if review.verdict not in ("pass", "fail", "inconclusive"):
                    raise ValueError("invalid review verdict")
                if episode.error:
                    review = Review("inconclusive", 0.0, episode.error)
            except Exception as exc:
                review = Review("inconclusive", 0.0, "reviewer unavailable: {}".format(exc))
            self.store.append("review", record(review))
            if review.verdict != "fail" or review.next_step != "reobserve":
                break
        candidate = Candidate(uuid.uuid4().hex, "memory", "m1-baseline", task.task_id,
                              "Review evidence before changing skills or weights: " + review.reason)
        self.store.append("candidate", record(candidate))
        return review
