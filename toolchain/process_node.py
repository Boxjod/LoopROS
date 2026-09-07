"""User-reviewed foreground programs in named PTYs; no model polling."""
import codecs
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import subprocess


def profile_path(name):
    from terminal.home import loop_home
    if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,47}', name):
        raise ValueError('Invalid process profile name')
    return loop_home() / 'processes' / (name + '.json')


def read_profile(name):
    path = profile_path(name)
    raw = path.read_bytes()
    if len(raw) > 32000:
        raise ValueError('Process profile exceeds 32 KiB')
    spec = json.loads(raw)
    validate_spec(spec)
    return {'name': name, 'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'spec': spec}


def validate_spec(spec):
    allowed = {'argv', 'cwd', 'env', 'env_names', 'stop_argv', 'description', 'remote'}
    if not isinstance(spec, dict) or set(spec) - allowed:
        raise ValueError('Invalid process profile fields')
    for key in ('argv', 'stop_argv'):
        value = spec.get(key, [] if key == 'stop_argv' else None)
        if not isinstance(value, list) or (key == 'argv' and not value) or len(value) > 80 or any(not isinstance(s, str) or not s or len(s) > 4000 or '\0' in s for s in value):
            raise ValueError('Expected bounded argv strings')
        if any(re.search(r'\bsk-[A-Za-z0-9]{16,}|(?:TOKEN|PASSWORD|SECRET|API_KEY)\s*=', s, re.I) for s in value):
            raise ValueError('Do not embed credentials in process arguments; use existing environment variables')
    if not isinstance(spec.get('cwd'), str) or not Path(spec['cwd']).is_absolute():
        raise ValueError('cwd must be an absolute local directory')
    env = spec.get('env', {})
    names = spec.get('env_names', [])
    if not isinstance(env, dict) or not isinstance(names, list) or len(env) + len(names) > 40:
        raise ValueError('Invalid process environment')
    for key in [*env, *names]:
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
            raise ValueError('Invalid environment variable name')
    if any(not isinstance(v, str) or '\0' in v for v in env.values()):
        raise ValueError('Environment values must be strings')
    if any(re.search(r'key|token|password|secret', key, re.I) for key in env):
        raise ValueError('Credential values belong in existing environment variables; use env_names')


def config(value):
    if isinstance(value, dict) and set(value) == {'skill', 'expected_sha256'}:
        from toolchain.offline_skill import inspect
        skill = inspect(value['skill'])
        if skill['sha256'] != value['expected_sha256']: raise ValueError('Skill changed; inspect it again')
        if not skill['supported']: raise ValueError('Skill has no entrypoint for this platform')
        return dict(value)
    if not isinstance(value, dict) or set(value) != {'profile', 'expected_sha256'}:
        raise ValueError('process requires profile and expected_sha256 from node_profiles')
    profile = read_profile(value['profile'])
    if profile['sha256'] != value['expected_sha256']:
        raise ValueError('Process profile changed; inspect it again')
    return dict(value)


def resource(value, name):
    if 'skill' in value:
        from terminal.skills import _resolve
        from terminal.home import loop_home
        return 'skill:' + str(_resolve(loop_home()/'skills',value['skill']).parent)
    return 'process-profile:' + str(profile_path(value['profile']).resolve())


class ProcessNode:
    def __init__(self, value):
        self.package = None
        if 'skill' in value:
            from toolchain.offline_skill import materialize
            self.spec, self.package = materialize(value)
            self.name = value['skill']
        else:
            profile = read_profile(value['profile'])
            if profile['sha256'] != value['expected_sha256']:
                raise ValueError('Process profile changed before launch')
            self.spec = profile['spec']
            self.name = value['profile']
        self.tail = ''
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.secrets = [v for k, v in os.environ.items() if re.search(r'key|token|password|secret', k, re.I) and v]
        self.env = {k: v for k, v in os.environ.items() if k in ('HOME', 'PATH', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TERM', 'DISPLAY', 'XAUTHORITY', 'SSH_AUTH_SOCK', 'CUDA_VISIBLE_DEVICES', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'USERPROFILE')}
        for name in self.spec.get('env_names', []):
            if name not in os.environ:
                raise ValueError('Required environment variable is missing: ' + name)
            self.env[name] = os.environ[name]
        self.env.update(self.spec.get('env', {}))
        if os.name != 'posix':
            import tempfile
            self.output_directory = tempfile.TemporaryDirectory(prefix='loop-output-')
            self.output_path = Path(self.output_directory.name)/'output'
            self.output_file = self.output_path.open('wb')
            self.output_reader = self.output_path.open('rb')
            self.offset = 0
            try:
                self.process = subprocess.Popen(self.spec['argv'], cwd=self.spec['cwd'], env=self.env,
                    stdin=subprocess.PIPE, stdout=self.output_file, stderr=self.output_file,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            except BaseException:
                self.output_file.close(); self.output_reader.close(); self.output_directory.cleanup()
                if self.package: self.package.cleanup()
                raise
            return
        import pty
        self.master, slave = pty.openpty()
        try:
            self.process = subprocess.Popen(self.spec['argv'], cwd=self.spec['cwd'], env=self.env,
                stdin=slave, stdout=slave, stderr=slave, start_new_session=True, close_fds=True)
        except Exception:
            os.close(self.master)
            if self.package: self.package.cleanup()
            raise
        finally:
            os.close(slave)

    def tick(self):
        # Bounded drain keeps the node heartbeat responsive under noisy output.
        if os.name != 'posix':
            size = os.fstat(self.output_file.fileno()).st_size
            self.output_reader.seek(max(self.offset, size - 65536))
            raw = self.output_reader.read(65536);self.offset = self.output_reader.tell()
            self.tail += self.decoder.decode(raw)
            if len(self.tail) > 65536:
                self.tail = self.tail[-32768:]
                self.tail = self.tail[min(max(map(len, self.secrets), default=0), len(self.tail)):]
            return
        for _ in range(16):
            if not select.select([self.master], [], [], 0)[0]:
                break
            try:
                raw = os.read(self.master, 4096)
            except OSError:
                break
            if not raw:
                break
            self.tail += self.decoder.decode(raw)
            if len(self.tail) > 65536:
                self.tail = self.tail[-32768:]
                self.tail = self.tail[min(max(map(len, self.secrets), default=0), len(self.tail)):]

    def output(self):
        value = self.tail
        for secret in self.secrets:
            value = value.replace(secret, '[redacted]')
            # Do not expose a credential prefix before the next read arrives.
            for length in range(min(len(secret) - 1, len(value)), 0, -1):
                if value.endswith(secret[:length]):
                    value = value[:-length]
                    break
        value = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', value)
        return ''.join(c for c in value[-8000:] if c.isprintable() or c in '\n\r\t')

    def snapshot(self):
        code = self.process.poll()
        return {'profile': self.name, 'pid': self.process.pid, 'process_state': 'running' if code is None else 'exited',
                'returncode': code, 'output_tail': self.output(), 'commands': ['send'],
                'readiness': 'not_verified', 'remote_state': 'not_verified' if self.spec.get('remote') else None,
                'model_polling': False}

    def command(self, action, arguments, stopping):
        if action != 'send' or set(arguments) != {'text'} or not isinstance(arguments['text'], str) or len(arguments['text']) > 2000:
            raise ValueError('process accepts send with text of at most 2000 characters')
        if self.process.poll() is not None:
            raise ValueError('Process has exited; inspect logs before restarting')
        raw = (arguments['text'] + '\n').encode()
        if os.name == 'posix': os.write(self.master, raw)
        else:
            self.process.stdin.write(raw); self.process.stdin.flush()
        return {'input_delivered': True, 'task_success': 'not_verified'}

    def close(self):
        if self.spec.get('stop_argv'):
            try:
                result = subprocess.run(self.spec['stop_argv'], cwd=self.spec['cwd'], env=self.env,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
                print(json.dumps({'stop_command_exit': result.returncode, 'remote_shutdown_verified': False}))
            except (OSError, subprocess.TimeoutExpired):
                print('{"stop_command_completed":false,"remote_shutdown_verified":false}')
        # Never signal an old PID after its child has exited and been reaped.
        if self.process.poll() is None:
            try:
                if os.name == 'posix': os.killpg(self.process.pid, signal.SIGTERM)
                else: subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],capture_output=True,timeout=5)
                self.process.wait(timeout=.2)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                if os.name == 'posix': os.killpg(self.process.pid, signal.SIGKILL)
                else: self.process.kill()
                self.process.wait(timeout=1)
        self.tick()
        print(self.output())
        if os.name == 'posix': os.close(self.master)
        else:
            self.output_file.close(); self.output_reader.close(); self.process.stdin.close()
            self.output_directory.cleanup()
        if self.package: self.package.cleanup()
