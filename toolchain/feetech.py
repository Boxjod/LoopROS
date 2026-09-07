"""Feetech STS diagnostics and bounded STS3215 position commands.

No connection on import. Diagnostic requests transmit PING/READ packets, never
WRITE, broadcast, torque-enable or EEPROM changes. No arbitrary packet API.
Reference and model boundaries: docs/FEETECH.md.
"""
from dataclasses import dataclass
import importlib.util
import sys
import time
import uuid
import threading
from functools import wraps


def serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return call

BAUDRATES = (1_000_000, 500_000, 250_000, 128_000, 115_200, 57_600, 38_400, 19_200)


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in [{low}, {high}]')
    return value


def packet(motor_id, instruction, data=b''):
    integer(motor_id, 0, 253, 'motor_id')
    body = bytes((motor_id, len(data) + 2, instruction)) + data
    return b'\xff\xff' + body + bytes((~sum(body) & 255,))


def environment():
    return {'python': sys.executable, 'pyserial_available': importlib.util.find_spec('serial') is not None,
            'protocol': 'Feetech STS/SMS protocol 0', 'supported_control_model': 'sts3215',
            'baudrates': list(BAUDRATES), 'motion_enabled_in_terminal': False}


@dataclass(frozen=True)
class PositionLimits:
    """Trusted host configuration in raw ticks; not model-supplied calibration."""
    minimum: int
    maximum: int
    max_step: int
    max_speed: int

    def __post_init__(self):
        integer(self.minimum, 0, 4095, 'minimum')
        integer(self.maximum, self.minimum + 1, 4095, 'maximum')
        integer(self.max_step, 1, 4095, 'max_step')
        integer(self.max_speed, 1, 3400, 'max_speed')


class Bus:
    def __init__(self, port, baudrate=1_000_000, *, timeout=.025, transport=None):
        if baudrate not in BAUDRATES or type(baudrate) is not int:
            raise ValueError('Unsupported Feetech baudrate')
        if not isinstance(port, str) or not port or '://' in port:
            raise ValueError('A local serial port is required')
        if not .005 <= timeout <= .1:
            raise ValueError('timeout must be 0.005..0.1 seconds')
        self.port, self.baudrate, self.timeout = port, baudrate, timeout
        self.io = transport
        self.instance_id = uuid.uuid4().hex
        self.requests = {}
        self.lock = threading.RLock()

    def __enter__(self):
        if self.io is None:
            try:
                import serial
            except ImportError as exc:
                raise RuntimeError('pyserial is absent in this Python; install loop-ros[feetech]') from exc
            self.io = serial.Serial(port=None, baudrate=self.baudrate, timeout=self.timeout,
                                    write_timeout=self.timeout, exclusive=True if sys.platform != 'win32' else None)
            self.io.dtr = False
            self.io.rts = False
            self.io.port = self.port
            try:
                self.io.open()
                if sys.platform == 'linux':
                    # Match SerialPort's exclusive ownership, including native receivers.
                    import fcntl
                    import termios
                    fcntl.ioctl(self.io.fileno(), termios.TIOCEXCL)
            except BaseException:
                self.io.close()
                self.io = None
                raise
        return self

    def __exit__(self, *exc):
        if self.io is not None:
            self.io.close()
            self.io = None

    @serialized
    def _exchange(self, motor_id, instruction, data=b'', expected=0):
        if self.io is None:
            raise RuntimeError('Bus must be opened first')
        outgoing = packet(motor_id, instruction, data)
        self.io.reset_input_buffer()
        if self.io.write(outgoing) != len(outgoing):
            raise ConnectionError('Short serial write; execution is unknown, do not replay')
        deadline = time.monotonic() + self.timeout
        buffer = bytearray()
        while time.monotonic() < deadline:
            buffer.extend(self.io.read(1))
            while len(buffer) >= 4:
                if buffer[:2] != b'\xff\xff' or not 2 <= buffer[3] <= 64:
                    del buffer[0]
                    continue
                size = buffer[3] + 4
                if len(buffer) < size:
                    break
                frame = bytes(buffer[:size]); del buffer[:size]
                if frame == outgoing:  # USB half-duplex adapters may echo the request.
                    continue
                if frame[2] != motor_id or sum(frame[2:]) & 255 != 255:
                    continue
                if frame[4]:
                    raise ConnectionError(f'Motor {motor_id} error bits: 0x{frame[4]:02x}')
                if len(frame[5:-1]) != expected:
                    continue
                return frame[5:-1]
        raise TimeoutError(f'No valid status packet: port={self.port}, baud={self.baudrate}, id={motor_id}')

    def ping(self, motor_id):
        self._exchange(motor_id, 1)
        return {'id': motor_id, 'baudrate': self.baudrate, 'ping_verified': True}

    def _read(self, motor_id, address, length):
        return self._exchange(motor_id, 2, bytes((address, length)), length)

    def identify(self, motor_id):
        result = self.ping(motor_id)
        try:
            model = int.from_bytes(self._read(motor_id, 3, 2), 'little')
        except (TimeoutError, ConnectionError) as exc:
            return {**result, 'model_number': None, 'model': None,
                    'register_table_verified': False, 'model_read_error': str(exc)}
        return {**result, 'model_number': model, 'model': 'sts3215' if model == 777 else None,
                'register_table_verified': model == 777}

    @serialized
    def read_state(self, motor_id):
        result = self.identify(motor_id)
        if not result['register_table_verified']:
            return {**result, 'state_read': False, 'reason': 'Unknown model; no position register assumptions'}
        mode = self._read(motor_id, 33, 1)[0]
        torque = self._read(motor_id, 40, 1)[0]
        data = self._read(motor_id, 56, 8)
        def signed(value, bit):
            return -(value & ((1 << bit) - 1)) if value & (1 << bit) else value
        return {**result, 'state_read': True, 'mode': mode, 'torque_enabled': torque == 1,
                'position_ticks': signed(int.from_bytes(data[:2], 'little'), 15),
                'speed_raw': signed(int.from_bytes(data[2:4], 'little'), 15),
                'load_raw': signed(int.from_bytes(data[4:6], 'little'), 10),
                'voltage_V': data[6] / 10, 'temperature_C': data[7],
                'observed_monotonic': time.monotonic(), 'instance_id': self.instance_id}

    @serialized
    def move_position(self, motor_id, target, speed, *, limits, request_id):
        """Host-only primitive; terminal deliberately does not expose real motion.

        Requires torque already enabled and position mode. No retries, EEPROM
        writes or automatic torque changes. Receipt is acceptance, not arrival.
        Caller must supply its own watchdog/stop integration.
        """
        if not isinstance(limits, PositionLimits):
            raise ValueError('Trusted PositionLimits required')
        integer(target, limits.minimum, limits.maximum, 'target')
        integer(speed, 1, limits.max_speed, 'speed')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise ValueError('request_id required')
        fingerprint = (motor_id, target, speed, limits)
        if request_id in self.requests:
            old, result = self.requests[request_id]
            if old != fingerprint:
                raise ValueError('request_id reused with different parameters')
            return {**result, 'duplicate': True}
        if len(self.requests) >= 1024:
            raise RuntimeError('Session command limit reached')
        state = self.read_state(motor_id)
        if not state.get('state_read') or state['mode'] != 0 or not state['torque_enabled']:
            raise ValueError('Verified STS3215, position mode and already-enabled torque required')
        if not limits.minimum <= state['position_ticks'] <= limits.maximum or abs(target - state['position_ticks']) > limits.max_step:
            raise ValueError('Position or relative step exceeds host limits')
        result = {'request_id': request_id, 'instance_id': self.instance_id,
                  'command_accepted': False, 'task_success': 'not_evaluated', 'verdict': 'inconclusive'}
        self.requests[request_id] = (fingerprint, result)
        # Reserve request before writing; an ambiguous timeout must never replay.
        self._exchange(motor_id, 3, bytes((42,)) + target.to_bytes(2, 'little') + b'\x00\x00' + speed.to_bytes(2, 'little'))
        result['command_accepted'] = True
        return dict(result)


def scan(port, ids=None, baudrates=None, *, stop_event=None, bus_factory=Bus):
    ids = list(range(1, 21)) if ids is None else ids
    baudrates = list(BAUDRATES) if baudrates is None else baudrates
    if not isinstance(ids, list) or not 1 <= len(ids) <= 254 or len(set(ids)) != len(ids):
        raise ValueError('ids must be a unique list of 1..254 motor IDs')
    for value in ids: integer(value, 0, 253, 'id')
    if not isinstance(baudrates, list) or not baudrates or len(baudrates) > 8 or any(type(b) is not int or b not in BAUDRATES for b in baudrates):
        raise ValueError('Select at most eight documented Feetech baudrates')
    found, attempts, cancelled = [], 0, False
    started = time.monotonic()
    with bus_factory(port, baudrates[0]) as bus:
        for baud in baudrates:
            bus.io.baudrate = bus.baudrate = baud
            for motor_id in ids:
                if (stop_event and stop_event.is_set()) or time.monotonic() - started > 20:
                    cancelled = True
                    break
                attempts += 1
                try:
                    found.append(bus.identify(motor_id))
                except TimeoutError:
                    continue
            if cancelled: break
    return {'port': port, 'motors': found, 'attempts': attempts, 'ids': ids, 'baudrates': baudrates,
            'scan_complete': not cancelled, 'elapsed_s': round(time.monotonic() - started, 3),
            'register_writes': False, 'query_packets_sent': attempts > 0,
            'verdict': 'pass' if found else 'inconclusive', 'task_success': 'not_evaluated'}


def main(argv=None):
    """Standalone diagnostic CLI; no motion subcommand."""
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('environment')
    detect = commands.add_parser('scan')
    detect.add_argument('--port', required=True)
    detect.add_argument('--ids', nargs='+', type=int)
    detect.add_argument('--baudrates', nargs='+', type=int)
    read = commands.add_parser('read')
    read.add_argument('--port', required=True)
    read.add_argument('--id', required=True, type=int)
    read.add_argument('--baudrate', required=True, type=int)
    args = parser.parse_args(argv)
    try:
        if args.operation == 'environment':
            result = environment()
        elif args.operation == 'scan':
            result = scan(args.port, args.ids, args.baudrates)
        else:
            with Bus(args.port, args.baudrate) as bus:
                result = bus.read_state(args.id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('scan_complete', True) and result.get('verdict') != 'inconclusive' and result.get('state_read', True) else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({'error': type(exc).__name__, 'message': str(exc), 'verdict': 'inconclusive'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
