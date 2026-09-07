"""OS-specific plumbing; hardware support is separate from terminal portability."""
import os
from pathlib import Path
import queue
import select
import threading


def venv_python(root, windows=None):
    windows = os.name == "nt" if windows is None else windows
    return Path(root) / ("Scripts/python.exe" if windows else "bin/python")


def lock_terminal(stream):
    """Lock held until stream closes, including on process crash."""
    if os.name == "nt":
        import msvcrt
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise BlockingIOError("State directory is already in use") from None
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


class InputPoller:
    """Windows select() accepts sockets, not redirected stdin."""
    def __init__(self, stream, windows=None):
        self.stream = stream
        self.windows = os.name == "nt" if windows is None else windows
        self.lines = queue.Queue(maxsize=1)
        if self.windows:
            threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.stream:
                self.lines.put(line)
        finally:
            self.lines.put("")

    def poll(self, timeout=0.25):
        if self.windows:
            try:
                return self.lines.get(timeout=timeout)
            except queue.Empty:
                return None
        ready, _, _ = select.select([self.stream], [], [], timeout)
        return self.stream.readline() if ready else None
