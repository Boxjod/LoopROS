import math


def validate_target(target, limits):
    if not limits or len(target) != len(limits):
        raise ValueError("joint dimension mismatch")
    for value, (low, high) in zip(target, limits):
        if not all(math.isfinite(x) for x in (value, low, high)):
            raise ValueError("non-finite joint value or limit")
        if low >= high or not low <= value <= high:
            raise ValueError("invalid limit or target outside limits")


def validate_trajectory(points, limits, max_speed):
    """Check (time_seconds, joint_positions) samples; not collision checking."""
    if not points or not math.isfinite(max_speed) or max_speed <= 0:
        raise ValueError("nonempty trajectory and positive speed required")
    previous = None
    for timestamp, target in points:
        validate_target(target, limits)
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("invalid timestamp")
        if previous is not None:
            dt = timestamp - previous[0]
            if dt <= 0:
                raise ValueError("timestamps must increase")
            if any(abs(q - old) / dt > max_speed
                   for q, old in zip(target, previous[1])):
                raise ValueError("sample-to-sample speed exceeds limit")
        previous = (timestamp, target)
    return True


def edit_trajectory(points, limits, max_speed, *, time_scale=1.0, offset=None):
    """Joint-space offset and retiming, returning a validated independent copy."""
    if not math.isfinite(time_scale) or time_scale <= 0:
        raise ValueError("time_scale must be positive")
    validate_trajectory(points, limits, float("1e300"))
    offset = [0.0] * len(limits) if offset is None else list(offset)
    if len(offset) != len(limits) or not all(math.isfinite(x) for x in offset):
        raise ValueError("invalid offset")
    start = points[0][0]
    edited = [((t - start) * time_scale, [q + d for q, d in zip(qs, offset)])
              for t, qs in points]
    validate_trajectory(edited, limits, max_speed)
    return edited


def sample_trajectory(points, timestamp, limits, max_speed):
    """Linear interpolation; endpoints are held outside the recorded interval."""
    validate_trajectory(points, limits, max_speed)
    if not math.isfinite(timestamp):
        raise ValueError("invalid sample time")
    if timestamp <= points[0][0]:
        return list(points[0][1])
    for (t0, q0), (t1, q1) in zip(points, points[1:]):
        if timestamp <= t1:
            alpha = (timestamp - t0) / (t1 - t0)
            return [a + alpha * (b - a) for a, b in zip(q0, q1)]
    return list(points[-1][1])
