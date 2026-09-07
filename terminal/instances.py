"""Lease a foreground runtime slot while keeping shared state in one directory."""
from itertools import count
from pathlib import Path
from terminal.platform_support import lock_terminal


class TerminalInstance:
    def __init__(self, state_dir):
        self.state_dir = Path(state_dir).resolve()
        self.runtime_dir = None
        self.stream = None

    def __enter__(self):
        for number in count(1):
            directory = self.state_dir if number == 1 else self.state_dir / 'terminals' / str(number)
            directory.mkdir(parents=True, exist_ok=True)
            stream = (directory / 'terminal.lock').open('a+b')
            try:
                lock_terminal(stream)
            except BlockingIOError:
                stream.close()
                continue
            except BaseException:
                stream.close()
                raise
            self.stream, self.runtime_dir = stream, directory
            return self

    def others_active(self):
        paths = [self.state_dir / 'terminal.lock', *self.state_dir.glob('terminals/*/terminal.lock')]
        for path in paths:
            if path.parent == self.runtime_dir:
                continue
            with path.open('a+b') as stream:
                try:
                    lock_terminal(stream)
                except BlockingIOError:
                    return True
        return False

    def __exit__(self, *args):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def claim_node_resource(state_dir, resource):
    """Device/profile ownership is distinct from the shared RAM/CPU budget."""
    if resource.startswith('sim:'):
        return None  # Named simulations are owned by their separate runtime slots.
    import hashlib
    directory = Path(state_dir) / 'node-resource-locks'
    directory.mkdir(parents=True, exist_ok=True)
    stream = (directory / (hashlib.sha256(resource.encode()).hexdigest() + '.lock')).open('a+b')
    try:
        lock_terminal(stream)
    except BlockingIOError:
        stream.close()
        raise ValueError('Node resource is already owned by another terminal or worker') from None
    except BaseException:
        stream.close()
        raise
    return stream
