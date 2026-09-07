"""Host telemetry adapter and compatibility constructor for shared resources."""
import math
import os
from pathlib import Path
import subprocess
import time
import threading
from loop_robot.core.resources import DEFAULTS, ResourceManager, validate_policy


class HostMonitor:
    def __init__(self):
        self.lock = threading.RLock()
        self.previous = None
        self.group_previous = {}
        self.cached = None
        self.sampled = -math.inf

    def sample(self):
        with self.lock:
            return self._sample()

    def _sample(self):
        now = time.monotonic()
        if self.cached is not None and now - self.sampled < 1:
            return self.cached
        result = dict(available_ram_mb=None, cpu_percent=None,
                      cpu_cores=os.cpu_count() or 1, gpus=[], errors=[])
        try:
            mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
            result['available_ram_mb'] = int(mem['MemAvailable'].split()[0]) / 1024
            ticks = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
            total, idle = sum(ticks), ticks[3] + ticks[4]
            if self.previous and total > self.previous[0]:
                result['cpu_percent'] = 100 * (1 - (idle - self.previous[1]) / (total - self.previous[0]))
            else:
                result['cpu_percent'] = min(100, 100 * os.getloadavg()[0] / result['cpu_cores'])
            self.previous = (total, idle)
            # cgroup v2 limits may be tighter than the host's resources.
            group = next((line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::')), '/')
            root = Path('/sys/fs/cgroup')
            candidate = root / group.lstrip('/')
            if '..' not in Path(group).parts and candidate.exists():
                root = candidate
            for directory in (root, *root.parents):
                if not str(directory).startswith('/sys/fs/cgroup'):
                    break
                limit = directory / 'memory.max'
                if limit.exists() and limit.read_text().strip() != 'max':
                    free = max(0, int(limit.read_text()) - int((directory / 'memory.current').read_text())) / 1048576
                    result['available_ram_mb'] = min(result['available_ram_mb'], free)
                quota = directory / 'cpu.max'
                if quota.exists():
                    amount, period = quota.read_text().split()
                    if amount != 'max':
                        cores = int(amount) / int(period)
                        result['cpu_cores'] = min(result['cpu_cores'], cores)
                        usage = dict(line.split() for line in (directory / 'cpu.stat').read_text().splitlines())
                        used = int(usage['usage_usec'])
                        previous = self.group_previous.get(str(directory))
                        if previous and now > previous[0]:
                            busy = (used - previous[1]) / ((now - previous[0]) * 10000 * cores)
                            result['cpu_percent'] = max(result['cpu_percent'], min(100, busy))
                        self.group_previous[str(directory)] = (now, used)
            if hasattr(os, 'sched_getaffinity'):
                result['cpu_cores'] = min(result['cpu_cores'], len(os.sched_getaffinity(0)))
        except (OSError, ValueError, KeyError, StopIteration):
            result['errors'].append('Host RAM/CPU telemetry unavailable or incomplete')
        try:
            output = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.free,utilization.gpu',
                                     '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=0.5, check=True)
            for row in output.stdout.splitlines():
                index, free, busy = row.split(',')
                result['gpus'].append(dict(index=int(index), free_vram_mb=float(free), gpu_percent=float(busy)))
        except (OSError, ValueError, subprocess.SubprocessError):
            result['errors'].append('NVIDIA GPU telemetry unavailable')
        self.cached, self.sampled = result, now
        return result


class ResourceAdmission(ResourceManager):
    """Compatibility name; all clients use the same core budget implementation."""
    def __init__(self, path, policy=None, monitor=None):
        super().__init__(path, policy, monitor or HostMonitor())
