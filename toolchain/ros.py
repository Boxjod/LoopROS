"""ROS 2 read-only joint observation. Caller owns node, executor and context."""
import math
import time


class JointStateBuffer:
    def __init__(self, joint_names, body_id, max_age_s=0.5):
        self.names = tuple(joint_names)
        if (not self.names or len(set(self.names)) != len(self.names)
                or not math.isfinite(max_age_s) or max_age_s <= 0):
            raise ValueError("unique joint names and positive max_age_s required")
        self.body_id, self.max_age = body_id, max_age_s
        self.latest = None

    def update(self, names, positions, stamp=None):
        # Invalidate on malformed input rather than silently serving old state.
        self.latest = None
        if len(names) != len(positions) or len(set(names)) != len(names):
            raise ValueError("invalid JointState layout")
        values = dict(zip(names, positions))
        if any(n not in values or not math.isfinite(values[n]) for n in self.names):
            raise ValueError("missing or invalid joint position")
        self.latest = {"body_id": self.body_id, "timestamp": time.monotonic(),
                       "source_stamp": stamp, "q": [values[n] for n in self.names],
                       "modalities": ["joint_position"]}

    def observe(self):
        state = self.latest
        if state is None or time.monotonic() - state["timestamp"] > self.max_age:
            raise RuntimeError("missing or stale joint state")
        return {**state, "q": list(state["q"]), "modalities": list(state["modalities"])}


class RosJointObserver(JointStateBuffer):
    def __init__(self, node, topic, joint_names, body_id, max_age_s=0.5):
        from sensor_msgs.msg import JointState
        from rclpy.qos import qos_profile_sensor_data
        super().__init__(joint_names, body_id, max_age_s)
        self.node = node
        self.subscription = node.create_subscription(
            JointState, topic, self._receive, qos_profile_sensor_data)

    def _receive(self, message):
        try:
            self.update(message.name, message.position,
                        {"sec": message.header.stamp.sec, "nanosec": message.header.stamp.nanosec})
        except ValueError as exc:
            self.node.get_logger().warning(str(exc))

    def close(self):
        if self.subscription is not None:
            self.node.destroy_subscription(self.subscription)
            self.subscription = None
        self.latest = None
