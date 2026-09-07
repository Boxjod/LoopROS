"""ROS observation process owned and budgeted by the existing Node runtime."""
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from loop_robot.toolchain.ros_host import TYPES


ENV_NAMES = {'ROS_MASTER_URI', 'ROS_IP', 'ROS_HOSTNAME', 'ROS_DOMAIN_ID', 'ROS_LOCALHOST_ONLY',
             'RMW_IMPLEMENTATION', 'ROS_DISTRO', 'ROS_VERSION', 'ROS_PACKAGE_PATH',
             'AMENT_PREFIX_PATH', 'CMAKE_PREFIX_PATH', 'COLCON_PREFIX_PATH', 'PYTHONPATH',
             'LD_LIBRARY_PATH', 'PATH', 'CYCLONEDDS_URI', 'FASTRTPS_DEFAULT_PROFILES_FILE',
             'ROS_DISCOVERY_SERVER'}


def config(value):
    if not isinstance(value, dict) or set(value) - {'version', 'python', 'topics', 'env', 'launch'}:
        raise ValueError('ROS config accepts version, python, topics, env, launch')
    version = value.get('version', 2)
    if type(version) is not int or version not in (1, 2):
        raise ValueError('ROS version must be 1 or 2')
    python = value.get('python', sys.executable)
    if not isinstance(python, str) or not Path(python).is_absolute() or '\0' in python:
        raise ValueError('python must be an absolute interpreter path')
    env = value.get('env', {})
    if not isinstance(env, dict) or set(env) - ENV_NAMES or any(not isinstance(v, str) or len(v) > 16000 or '\0' in v for v in env.values()):
        raise ValueError('env accepts bounded ROS workspace environment variables only')
    topics = value.get('topics')
    if not isinstance(topics, list) or not 1 <= len(topics) <= 32:
        raise ValueError('Configure 1..32 explicit observation topics')
    normalized, names = [], set()
    for spec in topics:
        if not isinstance(spec, dict) or set(spec) - {'name', 'topic', 'kind', 'max_age_s', 'required', 'qos'}:
            raise ValueError('Invalid observation fields')
        name, topic, kind = spec.get('name'), spec.get('topic'), spec.get('kind')
        if not isinstance(name, str) or not name or len(name) > 64 or name in names:
            raise ValueError('Observation names must be unique bounded strings')
        if not isinstance(topic, str) or not topic.startswith('/') or len(topic) > 256 or any(c.isspace() for c in topic):
            raise ValueError('An absolute ROS topic is required')
        if kind not in TYPES:
            raise ValueError('Unsupported sensor kind; choose ' + ', '.join(TYPES))
        age = spec.get('max_age_s', 2.0)
        if isinstance(age, bool) or not isinstance(age, (float, int)) or not math.isfinite(age) or not 0 < age <= 3600:
            raise ValueError('max_age_s must be finite and in (0, 3600]')
        required = spec.get('required', True)
        qos = spec.get('qos', 'latched' if kind == 'map' else 'sensor')
        if type(required) is not bool or qos not in ('sensor', 'reliable', 'latched'):
            raise ValueError('Invalid required or qos')
        names.add(name)
        normalized.append({'name': name, 'topic': topic, 'kind': kind,
                           'max_age_s': float(age), 'required': required, 'qos': qos})
    launch = value.get('launch')
    if launch is not None:
        from loop_robot.toolchain.process_node import validate_spec
        if not isinstance(launch, dict) or set(launch) != {'argv', 'cwd'}:
            raise ValueError('launch requires explicit argv and absolute cwd')
        validate_spec(launch)
    return {'version': version, 'python': python, 'env': dict(env), 'topics': normalized, 'launch': launch}


def resource(value, name):
    # Subscriptions are receive-only; separate observer instances may share topics.
    if value.get('launch'):
        identity = {'launch': value['launch'], 'env': value['env'], 'version': value['version']}
        return 'ros-program:' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return 'ros-observer:' + name


class RosNode:
    def __init__(self, value):
        self.value = value
        base = Path(value['evidence_path'])
        self.output = base.with_suffix('.ros-state.json')
        self.config_path = base.with_suffix('.ros-config.json')
        self.output.unlink(missing_ok=True)
        self.output.with_suffix('.request.json').unlink(missing_ok=True)
        self.output.with_suffix('.result.json').unlink(missing_ok=True)
        self.config_path.write_text(json.dumps({k: value[k] for k in ('version', 'topics')}), encoding='utf-8')
        os.chmod(self.config_path, 0o600)
        env = {key: val for key, val in os.environ.items()
               if key in ENV_NAMES or key in ('HOME', 'USER', 'LANG', 'LC_ALL', 'SYSTEMROOT', 'TEMP', 'TMP')}
        env.update(value['env'])
        self.log = base.with_suffix('.ros.log').open('ab', buffering=0)
        try:
            self.process = subprocess.Popen([value['python'], '-u', str(Path(__file__).with_name('ros_host.py')),
                '--config', str(self.config_path), '--output', str(self.output)], env=env,
                stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
                start_new_session=os.name != 'nt',
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        except Exception:
            self.log.close()
            raise
        self.latest = {}
        self.program = None
        if value.get('launch'):
            try:
                self.program = subprocess.Popen(value['launch']['argv'], cwd=value['launch']['cwd'], env=env,
                    stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
                    start_new_session=os.name != 'nt',
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
            except Exception:
                self.close()
                raise

    def tick(self):
        try:
            if self.output.stat().st_size <= 256000:
                self.latest = json.loads(self.output.read_text(encoding='utf-8'))
            else:
                self.latest = {'readiness': 'failed', 'error': 'ROS summary exceeds 256 KB'}
        except FileNotFoundError:
            pass
        if self.program is not None and self.program.poll() is not None:
            raise RuntimeError('ROS program exited: %s; see %s' % (self.program.returncode, self.log.name))
        if self.process.poll() is not None:
            raise RuntimeError(self.latest.get('error', 'ROS host exited: %s; see %s' % (self.process.returncode, self.log.name)))

    def snapshot(self):
        state = dict(self.latest)
        age = time.monotonic() - state.get('host_updated_monotonic', 0)
        if self.process.poll() is not None or age > 3:
            state['readiness'] = 'host_unavailable'
        return {**state, 'host_pid': self.process.pid, 'ros_version': self.value['version'],
                'commands': ['export_map'], 'output_log': str(self.log.name), 'state_file': str(self.output),
                'program': None if self.program is None else {'pid': self.program.pid,
                    'returncode': self.program.poll(), 'readiness': 'not_verified'},
                'model_polling': False, 'task_success': 'not_evaluated'}

    def command(self, action, arguments, stopping):
        if action != 'export_map' or not isinstance(arguments, dict) or set(arguments) != {'name'}:
            raise ValueError('ROS node accepts export_map with an observation name')
        if not any(s['name'] == arguments['name'] and s['kind'] == 'map' for s in self.value['topics']):
            raise ValueError('Unknown map observation')
        from loop_robot.toolchain.ros_host import write_snapshot
        request_id = uuid.uuid4().hex
        write_snapshot(self.output.with_suffix('.request.json'), {'id': request_id, 'name': arguments['name']})
        deadline = time.monotonic() + 3
        while not stopping.is_set() and time.monotonic() < deadline:
            try:
                result = json.loads(self.output.with_suffix('.result.json').read_text(encoding='utf-8'))
                if result['id'] == request_id:
                    return result
            except FileNotFoundError:
                pass
            stopping.wait(.05)
        return {'verdict': 'inconclusive', 'request_id': request_id,
                'reason': 'Map export result not received; request may still complete',
                'result_file': str(self.output.with_suffix('.result.json'))}

    def close(self):
        children = [p for p in (self.program, self.process) if p is not None]
        try:
            for child in children:
                if child.poll() is None:
                    try:
                        if os.name == 'nt':
                            child.send_signal(signal.CTRL_BREAK_EVENT)
                        else:
                            os.killpg(child.pid, signal.SIGINT)
                    except ProcessLookupError:
                        pass
            # On timeout NodeRuntime retains the worker and its resource lease.
            # Signal all children before waiting; never escalate to TERM/KILL.
            for child in children:
                child.wait()
        finally:
            self.log.close()
