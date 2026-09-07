"""Owned serial receivers: native Linux and pySerial Windows/macOS; no transmit API."""
import os
from pathlib import Path
import select
import stat
import threading
import time
import sys
if sys.platform.startswith("linux"):
    import fcntl
    import termios
    import tty


class SerialPort:
    def __new__(cls):
        if sys.platform in ('win32', 'darwin'):
            return PortableSerialPort()
        return super().__new__(cls)

    def __init__(self):
        self.fd = None
        self.path = None
        self.baud = None
        self.original = None
        self.identity = None
        self.lock = threading.RLock()

    def status(self):
        with self.lock:
            connected = False
            if self.fd is not None:
                try:
                    node = os.stat(self.path)
                    connected = (node.st_dev, node.st_ino, node.st_rdev) == self.identity
                    poller = select.poll()
                    poller.register(self.fd, select.POLLERR | select.POLLHUP | select.POLLNVAL)
                    connected = connected and not poller.poll(0)
                except OSError:
                    pass
            return {'opened': self.fd is not None, 'connected': connected,
                    'port': self.path, 'baud': self.baud, 'mode': 'receive_only',
                    'motor_model': None, 'motor_identified': False}

    def open(self, port, baud):
        if not sys.platform.startswith("linux"):
            raise RuntimeError("Serial hardware adapter is Linux-only; terminal features remain available")
        if not isinstance(port, str) or not (port.startswith('/dev/ttyUSB') or port.startswith('/dev/ttyACM') or port.startswith('/dev/serial/by-id/')):
            raise ValueError('Use a discovered /dev/ttyUSB*, /dev/ttyACM* or /dev/serial/by-id/ port')
        if type(baud) is not int or baud not in (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600):
            raise ValueError('Unsupported baud rate')
        path = str(Path(port).resolve(strict=True))
        if not Path(path).name.startswith(('ttyUSB', 'ttyACM')) or Path(path).parent != Path('/dev'):
            raise ValueError('Port must resolve to a USB serial device')
        with self.lock:
            if self.fd is not None:
                raise ValueError('Close the existing serial session first')
            fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
            original = None
            try:
                node = os.fstat(fd)
                if not stat.S_ISCHR(node.st_mode):
                    raise ValueError('Port is not a character device')
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.ioctl(fd, termios.TIOCEXCL)
                original = termios.tcgetattr(fd)
                tty.setraw(fd, termios.TCSANOW)
                settings = termios.tcgetattr(fd)
                settings[2] |= termios.CLOCAL | termios.CREAD
                settings[2] &= ~(termios.CRTSCTS | termios.HUPCL)
                settings[4] = settings[5] = getattr(termios, 'B' + str(baud))
                termios.tcsetattr(fd, termios.TCSANOW, settings)
            except Exception:
                try:
                    if original is not None:
                        termios.tcsetattr(fd, termios.TCSANOW, original)
                except (OSError, termios.error):
                    pass
                finally:
                    os.close(fd)
                raise
            self.fd, self.path, self.baud = fd, path, baud
            self.original = original
            self.identity = (node.st_dev, node.st_ino, node.st_rdev)
            return self.status()

    def read(self, max_bytes=256, timeout_ms=200):
        if type(max_bytes) is not int or not 1 <= max_bytes <= 4096:
            raise ValueError('max_bytes must be 1..4096')
        if type(timeout_ms) is not int or not 0 <= timeout_ms <= 1000:
            raise ValueError('timeout_ms must be 0..1000')
        with self.lock:
            if not self.status()['connected']:
                raise RuntimeError('No connected serial session; explicitly reopen the port')
            ready, _, _ = select.select([self.fd], [], [], timeout_ms / 1000)
            data = b''
            if ready:
                try:
                    data = os.read(self.fd, max_bytes)
                except BlockingIOError:
                    pass
            return {**self.status(), 'bytes_read': len(data), 'hex': data.hex(),
                    'observed_at': time.time(), 'motor_identified': False}

    def close(self):
        with self.lock:
            if self.fd is not None:
                try:
                    fcntl.ioctl(self.fd, termios.TIOCNXCL)
                    termios.tcsetattr(self.fd, termios.TCSANOW, self.original)
                except (OSError, termios.error):
                    pass
                finally:
                    os.close(self.fd)
                    self.fd = None
            return self.status()


class PortableSerialPort:
    """pySerial receiver for Windows/macOS. No transmit or protocol probing API."""
    def __init__(self):
        self.handle = None
        self.path = None
        self.baud = None
        self.identity = None
        self.lock = threading.RLock()

    def _present(self):
        from toolchain.serial_discovery import inventory
        return next((item for item in inventory()['devices'] if item['node'] == self.path), None)

    def status(self):
        with self.lock:
            present = self._present() if self.handle else None
            connected = bool(self.handle and self.handle.is_open and present and present == self.identity)
            return {'opened': bool(self.handle and self.handle.is_open), 'connected': connected,
                    'port': self.path, 'baud': self.baud, 'mode': 'receive_only',
                    'motor_model': None, 'motor_identified': False}

    def open(self, port, baud):
        from toolchain.serial_discovery import inventory
        if type(baud) is not int or baud not in (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600):
            raise ValueError('Unsupported baud rate')
        entry = next((item for item in inventory()['devices'] if item['node'] == port), None)
        if not entry:
            raise ValueError('Use a discovered local serial port; URLs and arbitrary paths are not accepted')
        with self.lock:
            if self.handle:
                raise ValueError('Close the existing serial session first')
            import serial
            handle = serial.Serial(port=None, baudrate=baud, timeout=0, write_timeout=0,
                                   xonxoff=False, rtscts=False, dsrdtr=False)
            try:
                handle.dtr = False
                handle.rts = False
                if sys.platform == 'darwin':
                    handle.exclusive = True
                handle.port = port
                handle.open()
            except Exception:
                handle.close()
                raise
            self.handle, self.path, self.baud, self.identity = handle, port, baud, entry
            return self.status()

    def read(self, max_bytes=256, timeout_ms=200):
        if type(max_bytes) is not int or not 1 <= max_bytes <= 4096:
            raise ValueError('max_bytes must be 1..4096')
        if type(timeout_ms) is not int or not 0 <= timeout_ms <= 1000:
            raise ValueError('timeout_ms must be 0..1000')
        with self.lock:
            if not self.status()['connected']:
                raise RuntimeError('No connected serial session; explicitly reopen the port')
            self.handle.timeout = timeout_ms / 1000
            data = self.handle.read(max_bytes)
            return {**self.status(), 'bytes_read': len(data), 'hex': data.hex(),
                    'observed_at': time.time(), 'motor_identified': False}

    def close(self):
        with self.lock:
            if self.handle:
                try:
                    self.handle.close()
                finally:
                    self.handle = None
            return self.status()
