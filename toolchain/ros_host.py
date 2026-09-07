"""Standalone ROS 2/ROS 1 observation host (Python 3.8+, lazy ROS imports).

Also runs directly under a ROS workspace's interpreter, without importing Loop.
Only bounded summaries cross the host boundary; no publishing or motor commands.
"""
import argparse
import importlib
import json
import math
import os
from pathlib import Path
import signal
import threading
import time

TYPES = {
    'joints': ('sensor_msgs', 'JointState'),
    'force': ('geometry_msgs', 'WrenchStamped'),
    'imu': ('sensor_msgs', 'Imu'),
    'scan': ('sensor_msgs', 'LaserScan'),
    'image': ('sensor_msgs', 'Image'),
    'points': ('sensor_msgs', 'PointCloud2'),
    'odom': ('nav_msgs', 'Odometry'),
    'map': ('nav_msgs', 'OccupancyGrid'),
    'audio': ('audio_common_msgs', 'AudioData'),
    'tactile': ('std_msgs', 'Float32MultiArray'),
}


def finite(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('non-finite measurement')
    return value


def vector(value, fields=('x', 'y', 'z')):
    return [finite(getattr(value, key)) for key in fields]


def pose(value):
    return {'position_m': vector(value.position),
            'orientation_xyzw': vector(value.orientation, ('x', 'y', 'z', 'w'))}


def summarize(kind, msg):
    if kind == 'joints':
        if not msg.name or len(msg.name) != len(msg.position) or len(set(msg.name)) != len(msg.name) or len(msg.name) > 128:
            raise ValueError('invalid or oversized joint layout')
        return {'names': [str(n)[:128] for n in msg.name], 'positions': [finite(v) for v in msg.position],
                'units': 'URDF joint type: radians or metres'}
    if kind == 'force':
        return {'force_N': vector(msg.wrench.force), 'torque_Nm': vector(msg.wrench.torque)}
    if kind == 'imu':
        return {'orientation_xyzw': vector(msg.orientation, ('x', 'y', 'z', 'w')),
                'angular_velocity_rad_s': vector(msg.angular_velocity),
                'linear_acceleration_m_s2': vector(msg.linear_acceleration),
                'orientation_available': msg.orientation_covariance[0] != -1}
    if kind == 'scan':
        if len(msg.ranges) > 100000:
            raise ValueError('scan exceeds summary limit')
        valid = [float(v) for v in msg.ranges if math.isfinite(v) and msg.range_min <= v <= msg.range_max]
        return {'rays': len(msg.ranges), 'valid_rays': len(valid),
                'nearest_m': min(valid) if valid else None, 'farthest_m': max(valid) if valid else None}
    if kind == 'image':
        return {'width': msg.width, 'height': msg.height, 'encoding': str(msg.encoding)[:64],
                'bytes': len(msg.data), 'content': 'local_only'}
    if kind == 'points':
        return {'points': msg.width * msg.height, 'frame_geometry_validated': False,
                'bytes': len(msg.data), 'content': 'local_only'}
    if kind == 'odom':
        return {**pose(msg.pose.pose), 'child_frame_id': str(msg.child_frame_id)[:128],
                'linear_velocity_m_s': vector(msg.twist.twist.linear),
                'angular_velocity_rad_s': vector(msg.twist.twist.angular),
                'localization_validated': False}
    if kind == 'map':
        if msg.info.width * msg.info.height != len(msg.data) or not msg.data or len(msg.data) > 4000000 or msg.info.resolution <= 0:
            raise ValueError('invalid map dimensions')
        return {'width': msg.info.width, 'height': msg.info.height,
                'resolution_m': finite(msg.info.resolution), 'origin': pose(msg.info.origin),
                'map_quality_validated': False}
    if kind == 'audio':
        return {'bytes': len(msg.data), 'encoding': 'publisher_defined', 'content': 'local_only'}
    if kind == 'tactile':
        if len(msg.data) > 256:
            raise ValueError('tactile array exceeds 256 channels')
        return {'values': [finite(v) for v in msg.data], 'units': 'publisher_defined',
                'calibration_validated': False}
    raise ValueError('unsupported sensor kind')


class ObservationStore:
    def __init__(self, topics, version):
        self.topics, self.version = topics, version
        self.lock = threading.RLock()
        self.latest = {}
        self.maps = {}

    def receive(self, spec, msg):
        now = time.monotonic()
        with self.lock:
            old = self.latest.get(spec['name'], {})
            self.maps.pop(spec['name'], None)
            row = {'received_monotonic': now, 'received_unix': time.time(),
                   'count': old.get('count', 0) + 1}
            try:
                header = getattr(msg, 'header', None)
                stamp = getattr(header, 'stamp', None)
                row.update({'summary': summarize(spec['kind'], msg), 'error': None,
                            'frame_id': str(getattr(header, 'frame_id', ''))[:128],
                            'source_stamp': None if stamp is None else {
                                'sec': int(getattr(stamp, 'sec', getattr(stamp, 'secs', 0))),
                                'nanosec': int(getattr(stamp, 'nanosec', getattr(stamp, 'nsecs', 0)))}})
            except (ValueError, TypeError, AttributeError, IndexError) as exc:
                row['error'] = str(exc)[:300]
            self.latest[spec['name']] = row
            if spec['kind'] == 'map' and not row.get('error'):
                # One retained map across all topics bounds the optional export cache.
                self.maps.clear()
                self.maps[spec['name']] = msg

    def export_map(self, name, path):
        with self.lock:
            row = self.snapshot()['observations'].get(name)
            if not row or row['state'] != 'fresh' or name not in self.maps:
                raise ValueError('No fresh cached map for ' + str(name))
            msg = self.maps[name]
            write_snapshot(path, {'schema': 'loop.occupancy_grid.v1', 'observation': row,
                                  'data': list(msg.data)})
            return {'artifact': str(path), 'bytes': path.stat().st_size,
                    'format': 'loop.occupancy_grid.v1', 'map_quality_validated': False}

    def snapshot(self):
        with self.lock:
            observations = {}
            for spec in self.topics:
                row = self.latest.get(spec['name'])
                age = None if row is None else max(0, time.monotonic() - row['received_monotonic'])
                state = 'missing' if row is None else 'invalid' if row.get('error') else 'stale' if age > spec['max_age_s'] else 'fresh'
                observations[spec['name']] = {**(row or {}), 'topic': spec['topic'], 'kind': spec['kind'],
                    'required': spec['required'], 'state': state, 'age_s': age,
                    'clock_domain': 'ros%d' % self.version, 'source_freshness': 'not_verified'}
            required = [r for r in observations.values() if r['required']]
            return {'ros_version': self.version, 'observations': observations,
                    'readiness': 'observations_ready' if required and all(r['state'] == 'fresh' for r in required) else 'not_ready',
                    'task_success': 'not_evaluated'}


class RosHost:
    def __init__(self, config):
        self.config = config
        self.store = ObservationStore(config['topics'], config['version'])
        self.subscriptions = []
        self.node = self.context = None
        self.ros = None
        try:
            if config['version'] == 2:
                import rclpy
                from rclpy.context import Context
                from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
                self.ros = rclpy
                self.context = Context()
                rclpy.init(args=[], context=self.context)
                self.node = rclpy.create_node('loop_observer', context=self.context,
                                             use_global_arguments=False)
                for spec in config['topics']:
                    qos = QoSProfile(depth=1,
                        reliability=ReliabilityPolicy.RELIABLE if spec['qos'] != 'sensor' else ReliabilityPolicy.BEST_EFFORT,
                        durability=DurabilityPolicy.TRANSIENT_LOCAL if spec['qos'] == 'latched' else DurabilityPolicy.VOLATILE)
                    package, name = TYPES[spec['kind']]
                    cls = getattr(importlib.import_module(package + '.msg'), name)
                    self.subscriptions.append(self.node.create_subscription(cls, spec['topic'],
                        lambda msg, s=spec: self.store.receive(s, msg), qos))
            else:
                import rospy
                self.ros = rospy
                rospy.init_node('loop_observer', anonymous=True, disable_signals=True, argv=[])
                for spec in config['topics']:
                    package, name = TYPES[spec['kind']]
                    cls = getattr(importlib.import_module(package + '.msg'), name)
                    self.subscriptions.append(rospy.Subscriber(spec['topic'], cls,
                        lambda msg, s=spec: self.store.receive(s, msg), queue_size=1))
        except Exception:
            self.close()
            raise

    def tick(self):
        if self.config['version'] == 2:
            self.ros.spin_once(self.node, timeout_sec=0.02)
        elif self.ros.is_shutdown():
            raise RuntimeError('ROS 1 context shut down')

    def close(self):
        if self.config['version'] == 2:
            if self.node is not None:
                self.node.destroy_node()
                self.node = None
            if self.context is not None and self.context.ok():
                self.context.shutdown()
        elif self.ros is not None:
            for subscription in self.subscriptions:
                subscription.unregister()
            self.ros.signal_shutdown('Loop observer stopped')
        self.subscriptions = []


def write_snapshot(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')
    os.replace(str(temporary), str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    output = Path(args.output)
    stop = threading.Event()
    host = None
    try:
        host = RosHost(config)
        # Install after ROS init, which may install its own handlers.
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        while not stop.is_set():
            host.tick()
            request_path = output.with_suffix('.request.json')
            if request_path.exists():
                request = json.loads(request_path.read_text(encoding='utf-8'))
                request_path.unlink()
                try:
                    if len(request['id']) != 32 or any(c not in '0123456789abcdef' for c in request['id']):
                        raise ValueError('Invalid export request id')
                    result = host.store.export_map(request['name'], output.with_suffix('.' + request['id'] + '.map.json'))
                except (ValueError, OSError) as exc:
                    result = {'error': str(exc)[:300]}
                write_snapshot(output.with_suffix('.result.json'), {'id': request['id'], **result})
            write_snapshot(output, {**host.store.snapshot(), 'host_pid': os.getpid(),
                                    'host_updated_monotonic': time.monotonic()})
            stop.wait(0.18)
    except Exception as exc:
        write_snapshot(output, {'readiness': 'failed', 'error': type(exc).__name__ + ': ' + str(exc)[:500],
                                'host_updated_monotonic': time.monotonic()})
        raise
    finally:
        if host is not None:
            host.close()


if __name__ == '__main__':
    main()
