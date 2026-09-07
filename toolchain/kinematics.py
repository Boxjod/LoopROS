"""Mink FK and one constrained differential IK step; never actuates a body."""
import math


class MinkKinematics:
    def __init__(self, model, frame_name, velocity_limits, solver="daqp"):
        import mink
        self.mink = mink
        self.configuration = mink.Configuration(model)
        self.frame_name = frame_name
        self.solver = solver
        if not velocity_limits or any(not math.isfinite(v) or v <= 0
                                      for v in velocity_limits.values()):
            raise ValueError("explicit positive joint velocity limits required")
        self.task = mink.FrameTask(frame_name=frame_name, frame_type="site",
                                   position_cost=1.0, orientation_cost=1.0)
        self.posture = mink.PostureTask(model, cost=0.01)
        self.limits = [mink.ConfigurationLimit(model), mink.VelocityLimit(model, velocity_limits)]

    def _update(self, q):
        import numpy as np
        q = np.asarray(q, dtype=float)
        if q.shape != (self.configuration.model.nq,) or not np.isfinite(q).all():
            raise ValueError("invalid generalized positions")
        self.configuration.update(q)

    def fk(self, q):
        self._update(q)
        return self.configuration.get_transform_frame_to_world(self.frame_name, "site").as_matrix()

    def step(self, q, target_matrix, dt=0.01):
        import numpy as np
        target = np.asarray(target_matrix, dtype=float)
        if (target.shape != (4, 4) or not np.isfinite(target).all()
                or not np.allclose(target[3], [0, 0, 0, 1])
                or not np.allclose(target[:3, :3].T @ target[:3, :3], np.eye(3), atol=1e-6)
                or not np.isclose(np.linalg.det(target[:3, :3]), 1.0)
                or not math.isfinite(dt) or dt <= 0):
            raise ValueError("invalid SE(3) target or dt")
        self._update(q)
        self.posture.set_target_from_configuration(self.configuration)
        self.task.set_target(self.mink.SE3.from_matrix(target))
        velocity = self.mink.solve_ik(self.configuration, [self.task, self.posture],
                                      dt, self.solver, limits=self.limits)
        self.configuration.integrate_inplace(velocity, dt)
        return self.configuration.q.copy()
