"""Shared resource budgets and leases, independent of UI and device adapters."""
from contextlib import contextmanager, closing
import json
import math
import os
from pathlib import Path
import sqlite3
import uuid

class ResourceBusy(RuntimeError):
    """No resource lease was granted; the caller decides whether to queue."""


def validate_request(value):
    defaults = dict(ram_mb=256, cpu_cores=0.25, vram_mb=0, gpu_index=0)
    if not isinstance(value, dict) or set(value) - set(defaults):
        raise ValueError('Resource request fields: ram_mb/cpu_cores/vram_mb/gpu_index')
    request = {**defaults, **value}
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in request.values()):
        raise ValueError('Resource costs must be finite and nonnegative')
    if type(request['gpu_index']) is not int:
        raise ValueError('gpu_index must be an integer')
    return request


DEFAULTS = dict(max_workers=108, reserve_ram_mb=1024, agent_ram_mb=256,
                max_cpu_percent=85, agent_cpu_cores=0.25,
                gpu_index=0, agent_vram_mb=0, reserve_vram_mb=512,
                max_gpu_percent=90)


def validate_policy(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError('Unknown resource policy fields')
    policy = {**DEFAULTS, **value}
    for key, val in policy.items():
        if type(val) not in (int, float) or not math.isfinite(val) or val < 0:
            raise ValueError('Invalid resource policy: ' + key)
    for key in ('max_workers', 'gpu_index'):
        if type(policy[key]) is not int:
            raise ValueError(key + ' must be an integer')
    if not 1 <= policy['max_workers'] <= 108:
        raise ValueError('max_workers must be 1..108')
    if policy['agent_ram_mb'] < 1 or policy['agent_cpu_cores'] <= 0:
        raise ValueError('Per-agent RAM and CPU estimates must be positive')
    if any(not 1 <= policy[k] <= 100 for k in ('max_cpu_percent', 'max_gpu_percent')):
        raise ValueError('Utilization thresholds must be 1..100')
    return policy


def _identity(pid):
    try:
        # Start time prevents a reused PID from keeping an old reservation alive.
        fields = Path('/proc/{}/stat'.format(pid)).read_text().rsplit(')', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (OSError, IndexError):
        try:
            os.kill(pid, 0)
            return 'alive'
        except ProcessLookupError:
            return None
        except PermissionError:
            return 'alive'


class ResourceManager:
    def __init__(self, path, policy=None, monitor=None):
        self.policy = validate_policy(policy or {})
        if monitor is None:
            raise ValueError("A host telemetry adapter is required")
        self.monitor = monitor
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS leases (id TEXT PRIMARY KEY, pid INTEGER, identity TEXT, costs TEXT)')
        self.last = {}

    @contextmanager
    def _db(self):
        with closing(sqlite3.connect(str(self.path), timeout=5)) as db, db:
            yield db

    def _decision(self, sample, rows, request, workload):
        p = self.policy
        costs = [json.loads(row[3]) for row in rows]
        remaining = p['max_workers'] - sum(c.get('workload', 'agent') == 'agent' for c in costs) if workload == 'agent' else 1000000
        reason = 'worker ceiling'
        ram = sample['available_ram_mb']
        cpu = sample['cpu_percent']
        if ram is None or cpu is None:
            return 0, 'RAM/CPU telemetry unavailable'
        limits = [(remaining, reason),
                  (math.floor((ram - p['reserve_ram_mb'] - sum(c['ram'] for c in costs)) / request['ram_mb'] if request['ram_mb'] else remaining), 'RAM reserve'),
                  (math.floor((sample['cpu_cores'] * max(0, p['max_cpu_percent'] - cpu) / 100 - sum(c['cpu'] for c in costs)) / request['cpu_cores'] if request['cpu_cores'] else remaining), 'CPU headroom')]
        if request['vram_mb']:
            gpu = next((g for g in sample['gpus'] if g['index'] == request['gpu_index']), None)
            if gpu is None:
                return 0, 'Requested GPU telemetry unavailable'
            if gpu['gpu_percent'] >= p['max_gpu_percent']:
                return 0, 'GPU utilization'
            reserved = sum(c['vram'] for c in costs if c['gpu'] == request['gpu_index'])
            limits.append((math.floor((gpu['free_vram_mb'] - p['reserve_vram_mb'] - reserved) / request['vram_mb']), 'VRAM reserve'))
        count, reason = min(limits)
        return max(0, count), reason

    def inspect(self, acquire=False, request=None, workload='agent'):
        if not isinstance(workload, str) or not 1 <= len(workload) <= 80:
            raise ValueError('A short workload label is required')
        p = self.policy
        request = validate_request(request if request is not None else dict(
            ram_mb=p['agent_ram_mb'], cpu_cores=p['agent_cpu_cores'],
            vram_mb=p['agent_vram_mb'], gpu_index=p['gpu_index']))
        sample = self.monitor.sample()
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT * FROM leases').fetchall()
            for row in rows:
                if _identity(row[1]) != row[2]:
                    db.execute('DELETE FROM leases WHERE id=?', (row[0],))
            rows = db.execute('SELECT * FROM leases').fetchall()
            available, reason = self._decision(sample, rows, request, workload)
            counts = {}
            for row in rows:
                kind = json.loads(row[3]).get('workload', 'agent')
                counts[kind] = counts.get(kind, 0) + 1
            workers = counts.get('agent', 0)
            self.last = dict(policy=self.policy, sample=sample, reserved_workers=workers,
                             reservations_by_workload=counts, reserved_resources={
                                 k:sum(json.loads(row[3])[k] for row in rows) for k in ('ram','cpu','vram')},
                             request=request, workload=workload,
                             additional_workers=available, effective_limit=workers + available,
                             reason=reason, scope='shared runtime state directory; conservative estimates')
            if not acquire or not available:
                return None
            token = uuid.uuid4().hex
            p = self.policy
            costs = dict(ram=request['ram_mb'], cpu=request['cpu_cores'], vram=request['vram_mb'], gpu=request['gpu_index'], workload=workload)
            db.execute('INSERT INTO leases VALUES (?,?,?,?)', (token, os.getpid(), _identity(os.getpid()), json.dumps(costs)))
            return token

    def bind(self, token, pid):
        identity = _identity(pid)
        with self._db() as db:
            if identity is None:
                db.execute('DELETE FROM leases WHERE id=?', (token,))
            else:
                db.execute('UPDATE leases SET pid=?, identity=? WHERE id=?', (pid, identity, token))

    def release(self, token):
        with self._db() as db:
            db.execute('DELETE FROM leases WHERE id=?', (token,))

    def status(self):
        self.inspect()
        return self.last

    @contextmanager
    def control_lease(self):
        """Account bounded diagnostics/stop work without blocking recovery on pressure."""
        token = uuid.uuid4().hex
        costs = dict(ram=32, cpu=.05, vram=0, gpu=0, workload='process-control')
        with self._db() as db:
            db.execute('INSERT INTO leases VALUES (?,?,?,?)',
                       (token, os.getpid(), _identity(os.getpid()), json.dumps(costs)))
        try:
            yield token
        finally:
            self.release(token)

    @contextmanager
    def lease(self, workload, request=None):
        token = self.inspect(acquire=True, request=request, workload=workload)
        if token is None:
            raise ResourceBusy('Waiting for resources: ' + self.last['reason'])
        try:
            yield token
        finally:
            self.release(token)
