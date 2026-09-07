"""Permission and shared-resource boundary for process diagnostics/control."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from loop_robot.core.processes import request


def run(app, name, args):
    action = 'inspect' if name == 'process_inspect' else 'stop'
    spec = request(action, args)
    app.permissions.check(name, args)
    source = (Path(__file__).resolve().parents[1] / 'toolchain/process_control.py').read_text()
    source += '\ntry:\n    result = main(json.loads(' + repr(json.dumps(spec)) + '))\nexcept (ValueError, RuntimeError) as exc:\n    result = {"error": type(exc).__name__, "message": str(exc), "success": False}\nprint(json.dumps(result))\n'
    argv = [sys.executable, '-'] if spec['host'] == 'local' else [
        'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', spec['host'], 'python3 -']
    with app.resources.control_lease():
        child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 start_new_session=os.name == 'posix')
        started = time.monotonic()
        payload = source.encode()
        try:
            while True:
                if app.stop_event.is_set():
                    raise RuntimeError('Process control cancelled; remote effects may be incomplete. Inspect before retrying.')
                if time.monotonic() - started > 50:
                    raise RuntimeError('Process control timed out; remote effects unknown. Inspect before retrying.')
                try:
                    stdout, stderr = child.communicate(input=payload, timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    payload = None
            if child.returncode:
                # Never print arbitrary SSH/python exception text containing local paths or credentials.
                raise RuntimeError('Process adapter failed (exit {}). Verify SSH authentication, Python and Linux /proc access; effects unverified.'.format(child.returncode))
            if len(stdout) > 128000:
                raise ValueError('Process report too large; narrow the PID/port selection')
            result = json.loads(stdout)
            return {'host': spec['host'], **result, 'resource_scope': 'Transient controller leased locally; external/remote services are observed, not enrolled as new leases.'}
        finally:
            if child.poll() is None:
                if os.name == 'posix':
                    os.killpg(child.pid, signal.SIGTERM)
                else:
                    child.terminate()
                try:
                    child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait(timeout=1)
