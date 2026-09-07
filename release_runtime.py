"""Cross-process maintenance and runtime leases; standard library only."""
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import uuid


def managed_home():
    marker = Path(sys.prefix) / '.loop-release-root'
    return Path(marker.read_text().strip()) if marker.is_file() else None


def _lock(stream):
    stream.seek(0)
    if os.name == 'nt':
        import msvcrt
        if not stream.read(1):
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


@contextmanager
def maintenance(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'update.lock').open('a+b') as gate:
        try:
            _lock(gate)
        except OSError:
            raise RuntimeError('Another install/update is running; retry after it finishes.') from None
        leases = root / 'runtime-leases'
        if leases.exists():
            for path in leases.glob('*.lock'):
                try:
                    with path.open('a+b') as stream:
                        _lock(stream)
                except OSError:
                    raise RuntimeError('Loop ROS is active (' + path.stem.split('-')[0]
                                       + '); close terminals, services and viewers before updating.') from None
                path.unlink(missing_ok=True)
        yield


@contextmanager
def runtime_session():
    root = managed_home()
    if root is None:
        yield
        return
    # A brief gate prevents a reader starting between maintenance checks/activation.
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'update.lock').open('a+b') as gate:
        try:
            _lock(gate)
        except OSError:
            raise RuntimeError('Loop ROS update is in progress; retry when it finishes.') from None
        leases = root / 'runtime-leases'
        leases.mkdir(exist_ok=True)
        path = leases / (str(os.getpid()) + '-' + uuid.uuid4().hex + '.lock')
        stream = path.open('a+b')
        _lock(stream)
    try:
        yield
    finally:
        stream.close()
        path.unlink(missing_ok=True)
