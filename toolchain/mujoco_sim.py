"""Headless physics adapter for explicitly mapped, scalar position actuators."""
import math
import time
import uuid

from core.contracts import Capability, EmbodimentSpec
from toolchain.trajectory import validate_target


class MujocoBody:
    capability = Capability("mujoco_position", "1", "position")

    def __init__(self, xml_path, joint_actuators, body_id="sim-arm", steps=500):
        import mujoco
        import numpy as np
        self.mj, self.np = mujoco, np
        if not isinstance(steps, int) or steps <= 0 or not joint_actuators:
            raise ValueError("positive steps and explicit joint/actuator map required")
        self.model = mujoco.MjModel.from_xml_path(str(xml_path))
        self.data = mujoco.MjData(self.model)
        self.steps = steps
        self.qadr, self.dadr, self.aids, limits = [], [], [], []
        for joint, actuator in joint_actuators.items():
            j = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, joint)
            a = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator)
            if j < 0 or a < 0:
                raise ValueError("unknown joint or actuator")
            m = self.model
            if (int(m.jnt_type[j]) != int(mujoco.mjtJoint.mjJNT_HINGE)
                    or not m.jnt_limited[j] or m.actuator_trnid[a, 0] != j
                    or m.actuator_trntype[a] != mujoco.mjtTrn.mjTRN_JOINT
                    or m.actuator_dyntype[a] != mujoco.mjtDyn.mjDYN_NONE
                    or m.actuator_gaintype[a] != mujoco.mjtGain.mjGAIN_FIXED
                    or m.actuator_biastype[a] != mujoco.mjtBias.mjBIAS_AFFINE
                    or not np.allclose(m.actuator_gear[a], [1, 0, 0, 0, 0, 0])
                    or m.actuator_gainprm[a, 0] <= 0
                    or not np.isclose(m.actuator_biasprm[a, 1], -m.actuator_gainprm[a, 0])
                    or m.actuator_biasprm[a, 0] != 0 or m.actuator_biasprm[a, 2] > 0):
                raise ValueError("requires limited hinge joint and unit-gear position actuator")
            low, high = map(float, m.jnt_range[j])
            if m.actuator_ctrllimited[a]:
                low = max(low, float(m.actuator_ctrlrange[a, 0]))
                high = min(high, float(m.actuator_ctrlrange[a, 1]))
            if low >= high:
                raise ValueError("empty joint/control limit intersection")
            limits.append((low, high))
            self.qadr.append(int(m.jnt_qposadr[j]))
            self.dadr.append(int(m.jnt_dofadr[j]))
            self.aids.append(a)
        if len(set(self.aids)) != len(self.aids):
            raise ValueError("duplicate actuator mapping")
        self.spec = EmbodimentSpec(body_id, "mjcf-instance-" + uuid.uuid4().hex,
                                  tuple(limits), ("joint_position",))
        self.reset()

    def reset(self):
        self.mj.mj_resetData(self.model, self.data)
        self.mj.mj_forward(self.model, self.data)
        self.stop()
        return self.observe()

    def observe(self):
        return {"body_id": self.spec.body_id, "timestamp": time.monotonic(),
                "sim_time": float(self.data.time), "q": self.data.qpos[self.qadr].tolist(),
                "dq": self.data.qvel[self.dadr].tolist(), "contacts": int(self.data.ncon),
                "modalities": list(self.spec.modalities)}

    def execute(self, action):
        if (action["body_id"] != self.spec.body_id
                or action["calibration_version"] != self.spec.calibration_version):
            raise ValueError("wrong body or calibration")
        validate_target(action["target"], self.spec.limits)
        if not math.isfinite(action["expires_at"]):
            raise ValueError("invalid deadline")
        start = time.monotonic()
        warnings_before = self.data.warning.number.copy()
        self.data.ctrl[self.aids] = action["target"]
        try:
            for _ in range(self.steps):
                cancel = getattr(self, "cancel_event", None)
                if cancel is not None and cancel.is_set():
                    raise InterruptedError("simulation cancelled")
                if time.monotonic() >= action["expires_at"]:
                    raise TimeoutError("expired simulation action")
                self.mj.mj_step(self.model, self.data)
                if self.np.any(self.data.warning.number > warnings_before):
                    raise RuntimeError("MuJoCo warning; simulation evidence invalid")
                if not self.np.isfinite(self.data.qpos).all() or not self.np.isfinite(self.data.qvel).all():
                    raise RuntimeError("non-finite simulation state")
            self.last_timing = {"wall_s": time.monotonic() - start,
                                "sim_s": self.steps * self.model.opt.timestep}
        finally:
            self.stop()

    def stop(self):
        # Hold current position; no physics advances here. Not a hardware stop.
        self.data.ctrl[self.aids] = self.data.qpos[self.qadr]
