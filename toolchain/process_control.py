"""Standalone Linux process/port/RSS adapter; can be sent to an SSH host on stdin."""
import json
import os
from pathlib import Path
import signal
import sys
import time


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def process(pid):
    try:
        root = Path('/proc') / str(pid)
        raw = (root / 'stat').read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        return {'identity': {'pid': pid, 'start_ticks': int(fields[19]), 'boot_id': boot_id()},
                'name': (root / 'comm').read_text().strip(), 'state': fields[0], 'ppid': int(fields[1]),
                'uid': root.stat().st_uid, 'rss_mb': int(fields[21]) * os.sysconf('SC_PAGE_SIZE') / 1048576}
    except PermissionError:
        raise RuntimeError('Process identity is inaccessible; exit cannot be verified') from None
    except (OSError, ValueError, IndexError):
        return None


def memory():
    try:
        rows = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        return {name: int(rows[key].split()[0]) / 1024 for name, key in
                (('total_ram_mb', 'MemTotal'), ('available_ram_mb', 'MemAvailable'))}
    except (OSError, ValueError, KeyError):
        return {'available_ram_mb': None}


def inspect(ports, pids):
    inodes, bindings, errors = {}, {str(p): [] for p in ports}, []
    for table in ('tcp', 'tcp6'):
        try:
            for line in (Path('/proc/net') / table).read_text().splitlines()[1:]:
                row = line.split()
                port = int(row[1].rsplit(':', 1)[1], 16)
                if port in ports and row[3] == '0A':
                    inodes.setdefault(row[9], []).append(port)
                    bindings[str(port)].append(row[9])
        except (OSError, ValueError, IndexError):
            errors.append('Cannot fully inspect ' + table)
    owners = {inode: [] for inode in inodes}
    records = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        pid = int(path.name)
        found = set()
        if inodes:
            try:
                for fd in (path / 'fd').iterdir():
                    try:
                        link = os.readlink(fd)
                    except OSError:
                        continue
                    if link.startswith('socket:[') and link[8:-1] in inodes:
                        inode = link[8:-1]
                        owners[inode].append(pid)
                        found.update(inodes[inode])
            except OSError:
                pass
        if pid in pids or found or not ports and not pids:
            row = process(pid)
            if row:
                row['ports'] = sorted(found)
                records.append(row)
    port_status = {port: {'listening': bool(ids), 'pids': sorted({p for i in ids for p in owners[i]}),
                          'owners_known': all(owners[i] for i in ids)} for port, ids in bindings.items()}
    records.sort(key=lambda r: -r['rss_mb'])
    return {'observed_at': time.time(), 'processes': records[:64], 'truncated': len(records) > 64,
            'ports': port_status, 'memory': memory(), 'errors': errors,
            'scope': 'Linux host, current network namespace; RSS is per process, not additive physical usage'}


def alive(target):
    row = process(target['pid'])
    return bool(row and row['identity'] == target and row['state'] != 'Z')


def stop(spec):
    targets, ports = spec['targets'], spec['ports']
    before = inspect(ports, [t['pid'] for t in targets])
    protected = {1}
    current = process(os.getpid())
    while current and current['identity']['pid'] not in protected:
        protected.add(current['identity']['pid'])
        current = process(current['ppid'])
    handles, attempts = [], []
    try:
        # Verify every target before the first signal. PID handles prevent reuse races.
        for target in targets:
            row = process(target['pid'])
            if target['boot_id'] != boot_id() or target['pid'] in protected:
                raise ValueError('Host identity mismatch or protected controlling process')
            if row is None:
                continue
            if row['identity'] != target:
                raise ValueError('PID reused; inspect again before stopping')
            if row['state'] == 'Z':
                continue
            if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
                raise RuntimeError('Stopping requires Linux pidfd support and Python 3.9+ on the target')
            try:
                fd = os.pidfd_open(target['pid'])
            except ProcessLookupError:
                continue
            handles.append((target, fd))
            row = process(target['pid'])
            if row and row['identity'] != target:
                raise ValueError('PID changed during inspection')
        for name in spec['signals']:
            for target, fd in handles:
                if not alive(target):
                    continue
                try:
                    signal.pidfd_send_signal(fd, getattr(signal, name))
                    attempts.append({'pid': target['pid'], 'signal': name, 'sent': True})
                except ProcessLookupError:
                    pass
            deadline = time.monotonic() + spec['wait_s']
            while any(alive(t) for t in targets) and time.monotonic() < deadline:
                time.sleep(.05)
            if not any(alive(t) for t in targets):
                break
        after = inspect(ports, [t['pid'] for t in targets])
        remaining = [t for t in targets if alive(t)]
        released = not after['errors'] and all(not p['listening'] for p in after['ports'].values())
        return {'before': before, 'after': after, 'signals': attempts, 'remaining': remaining,
                'processes_stopped': not remaining, 'ports_released': released,
                'success': not remaining and released,
                'hardware_state': 'not_verified', 'children_stopped': 'not_verified'}
    finally:
        for _, fd in handles:
            os.close(fd)


def main(spec):
    if not sys.platform.startswith('linux'):
        return {'supported': False, 'error': 'Linux /proc required; no signals sent'}
    if spec['action'] == 'inspect':
        return inspect(spec['ports'], spec['pids'])
    return stop(spec)
