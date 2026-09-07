"""Trusted node plugins. Hardware adapters stay outside the core supervisor."""
import os
from pathlib import Path
import time
import uuid

from core.nodes import NodeDefinition


def sim_config(config):
    if not isinstance(config, dict) or config:
        raise ValueError('sim_arm takes an empty config; it uses the packaged two-joint model')
    return {}


def serial_config(config):
    if not isinstance(config, dict) or set(config) != {'port', 'baud'}:
        raise ValueError('serial_rx requires explicit port and baud')
    if not isinstance(config['port'], str) or not config['port'].startswith(('/dev/ttyUSB', '/dev/ttyACM', '/dev/serial/by-id/')):
        raise ValueError('Use a discovered USB serial path')
    if type(config['baud']) is not int or config['baud'] not in (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600):
        raise ValueError('Unsupported baud rate')
    return dict(config)


def sim_resource(config, name):
    return 'sim:' + name


def serial_resource(config, name):
    return 'serial:' + str(Path(config['port']).resolve())


class SimArmNode:
    def __init__(self, config):
        from toolchain.mujoco_sim import MujocoBody
        from core.store import EventStore
        self.body = MujocoBody(Path(__file__).resolve().parents[1] / 'examples/two_joint.xml',
                               {'j1': 'a1', 'j2': 'a2'}, body_id=config['node_name'])
        self.store = EventStore(config['evidence_path'])
        self.last_review = None
        self.ticks = 0

    def tick(self):
        for _ in range(10):
            self.body.mj.mj_step(self.body.model, self.body.data)
        if self.body.np.any(self.body.data.warning.number) or not self.body.np.isfinite(self.body.data.qpos).all():
            raise RuntimeError('Invalid simulation state')
        self.ticks += 1

    def snapshot(self):
        return {'backend': 'mujoco', 'simulated': True, 'controls_viewer': False,
                'observation': self.body.observe(), 'ticks': self.ticks, 'last_review': self.last_review,
                'commands': ['move'], 'units': 'radians'}

    def command(self, action, arguments, stopping):
        if action != 'move' or set(arguments) != {'target'}:
            raise ValueError('sim_arm supports move with target=[q1,q2] in radians')
        from core.contracts import TaskSpec, record
        from core.loop import Loop
        from core.plugins import FeedbackMaster, NumericalReviewer
        self.body.cancel_event = stopping
        review = Loop(self.body, FeedbackMaster(), NumericalReviewer(), self.store).run(
            TaskSpec(uuid.uuid4().hex, self.body.spec.body_id, tuple(arguments['target']), tolerance=.02))
        self.last_review = record(review)
        return {'review': self.last_review, 'simulated': True, 'controls_viewer': False}

    def close(self):
        self.body.stop()
        self.store.close()


class SerialReceiveNode:
    def __init__(self, config):
        from toolchain.serial_port import SerialPort
        from core.contracts import Episode
        from core.store import EventStore
        self.port = SerialPort()
        self.store = EventStore(config['evidence_path'])
        self.episode = Episode(config['instance_id'], 1, config['node_name'], 'unknown-protocol')
        self.total = 0
        self.latest = None
        self.error = None
        try:
            self.port.open(config['port'], config['baud'])
            self.episode.observations.append(self.port.status())
        except Exception as exc:
            self.error = str(exc)
            self.close()
            raise

    def tick(self):
        try:
            result = self.port.read(256, 0)
            self.total += result['bytes_read']
            if result['bytes_read']:
                self.latest = {'hex': result['hex'], 'observed_at': result['observed_at']}
        except Exception as exc:
            self.error = str(exc)
            raise

    def snapshot(self):
        return {**self.port.status(), 'bytes_received': self.total, 'latest_received': self.latest,
                'commands': [], 'motor_state': None,
                'note': 'Receive-only serial bytes are not decoded motor position or health'}

    def command(self, action, arguments, stopping):
        raise ValueError('serial_rx continuously receives; use node status for data. No write or motor commands.')

    def close(self):
        from core.contracts import Review, record
        self.episode.observations.append({'bytes_received': self.total, 'timestamp': time.monotonic()})
        self.episode.error = self.error
        try:
            self.port.close()
        finally:
            self.store.append('episode', record(self.episode))
            self.store.append('review', record(Review('inconclusive', 0,
                              self.error or 'Raw serial reception does not establish motor state or task success')))
            self.store.close()


def definitions():
    from toolchain.process_node import ProcessNode, config, resource
    return {'sim_arm': NodeDefinition(SimArmNode, sim_config, sim_resource),
            'serial_rx': NodeDefinition(SerialReceiveNode, serial_config, serial_resource),
            'process': NodeDefinition(ProcessNode, config, resource, stop_timeout_s=11 if os.name == 'nt' else 6)}
