"""Small HTTPS release client, shared by bootstrap and version checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import shutil
import uuid
import zipfile
import importlib
import shlex
import sqlite3
from contextlib import ExitStack
if __package__:
    from .install_support import ensure_uv, venv_python, windows_launcher, backup_launcher, configure_path
    from .release_runtime import maintenance, managed_home, _lock, runtime_directories, state_startup
    from .release_manifest import validate_manifest, version
    from ._version import __version__
else:  # Standalone HTTPS bootstrap and retained update controller.
    from install_support import ensure_uv, venv_python, windows_launcher, backup_launcher, configure_path
    from release_runtime import maintenance, managed_home, _lock, runtime_directories, state_startup
    from release_manifest import validate_manifest, version
    from _version import __version__
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener


def base_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Release URL must be HTTPS, without credentials, query or fragment")
    return value.rstrip("/")


class HTTPSRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        base_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit):
    base_url(url)
    curl = shutil.which('curl')
    if curl:
        # curl can use the host's configured CA bundle (including enterprise proxies).
        with tempfile.TemporaryDirectory(prefix='loop-download-') as directory:
            destination = Path(directory) / 'response'
            result = subprocess.run([curl, '--fail', '--silent', '--show-error', '--location',
                                     '--proto', '=https', '--proto-redir', '=https', '--max-time', '20',
                                     '--max-filesize', str(limit), '--output', str(destination), url],
                                    capture_output=True, text=True, timeout=25)
            if result.returncode:
                raise ValueError('Release download failed: ' + result.stderr.strip())
            with destination.open('rb') as stream:
                data = stream.read(limit + 1)
    else:
        with build_opener(HTTPSRedirect()).open(url, timeout=20) as response:
            data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Release response exceeds size limit')
    return data


def manifest(url, target_version=None):
    suffix = "/latest.json"
    if target_version:
        version(target_version)
        suffix = "/versions/" + target_version + suffix
    data = json.loads(fetch(base_url(url) + suffix, 16384))
    return validate_manifest(data, target_version)


def check(url, current):
    data = manifest(url)
    return {"installed": current, "latest": data["version"],
            "update_available": version(data["version"]) > version(current),
            "release_url": base_url(url)}


NAMES = ('loop', 'loop-switch', 'looper', 'looper-switch')
DEFAULT_URL = 'https://loopmaster.box2ai.com/LoopROS'


def user_home():
    if managed_home() is not None:
        return managed_home()
    return Path(os.environ.get('LOOP_HOME') or os.environ.get('LOOPER_HOME') or
                str(Path.home() / '.loop')).expanduser().resolve()


def read_record(root):
    path = root / 'release.json'
    return json.loads(path.read_text()) if path.is_file() else {}


def atomic_json(path, data):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.release-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def release_url(root, explicit=None):
    url = explicit or os.environ.get('LOOP_RELEASE_URL') or read_record(root).get('url') or DEFAULT_URL
    if not url:
        raise ValueError('No release server configured. Set LOOP_RELEASE_URL to the published HTTPS base URL.')
    return base_url(url)


def snapshot(record):
    return {key: record[key] for key in ('version', 'environment', 'terminal_only', 'state_dir', 'url', 'state_schema', 'state_backup') if key in record}


def smoke(environment, expected):
    # All App state is temporary; offline status must not start tasks or devices.
    with tempfile.TemporaryDirectory(prefix='loop-smoke-') as directory:
        env = dict(os.environ, LOOP_HOME=directory, LOOP_STATE_DIR=directory,
                   XDG_STATE_HOME=directory, LOOP_TASK_AUTOSTART='0')
        command = [str(venv_python(environment)), '-I', '-c',
                   'import importlib.metadata; from loop_robot.launcher import _bootstrap; _bootstrap(); '
                   'import loop_robot.terminal.app, loop_robot.model_switch; '
                   'import loop_robot.core.resources, loop_robot.core.memory_layers; '
                   'print(importlib.metadata.version("loop-ros"))']
        result = subprocess.run(command, env=env, cwd=directory, capture_output=True, text=True, timeout=60, check=True)
        if result.stdout.strip() != expected:
            raise ValueError('Candidate version smoke check failed: ' + result.stdout.strip())
        subprocess.run([str(venv_python(environment)), '-I', '-m', 'loop_robot', '--once', '/status'],
                       env=env, cwd=directory, capture_output=True, text=True, timeout=60, check=True)


DISPATCHER = '''"""Stable release dispatcher; selection is an atomic release.json record."""
import json, os, pathlib, sys
root = pathlib.Path(__file__).resolve().parent
record = json.loads((root / 'release.json').read_text())
environment = pathlib.Path(record['environment'])
if record.get('state_dir'):
    os.environ.setdefault('LOOP_STATE_DIR', record['state_dir'])
os.environ.setdefault('LOOP_HOME', str(root))
name = sys.argv[1]
if name not in ('loop', 'loop-switch', 'looper', 'looper-switch'):
    raise SystemExit('Unknown Loop ROS launcher')
args = sys.argv[2:]
update_args = args[1:] if args[:1] in (['ros'], ['robot']) else args
if name in ('loop', 'looper') and (update_args[:1] == ['update'] or update_args == ['--check-update']):
    python = root / 'updater' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    options = ['--check'] if update_args == ['--check-update'] else update_args[1:]
    os.execv(str(python), [str(python), str(root / 'release-control.pyz')] + options)
program = environment / ('Scripts' if os.name == 'nt' else 'bin') / (name + ('.exe' if os.name == 'nt' else ''))
os.execv(str(program), [str(program)] + args)
'''


def write_control(root):
    fd, temporary = tempfile.mkstemp(dir=root, prefix='.control-', suffix='.pyz')
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('__main__.py', """import sys
from pathlib import Path
import release_client
release_client.managed_home = lambda: Path(sys.argv[0]).resolve().parent
try:
    raise SystemExit(release_client.update_main(sys.argv[1:]))
except Exception as error:
    raise SystemExit('Update failed: ' + str(error))
""")
            for name in ('release_client', 'install_support', 'release_runtime', 'release_manifest', '_version'):
                module = sys.modules[__name__] if name == 'release_client' else importlib.import_module(
                    (__package__ + '.' if __package__ else '') + name)
                source = module.__loader__.get_source(module.__name__)
                archive.writestr(name + '.py', source)
        os.replace(temporary, root / 'release-control.pyz')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def launcher_text(root, name):
    python = venv_python(root / 'updater')
    script = root / 'release-launcher.py'
    if os.name == 'nt':
        def quote(path):
            return str(path).replace('%', '%%')
        return ('@echo off\nrem Loop ROS managed release launcher\nsetlocal DisableDelayedExpansion\n'
                'chcp 65001 >nul\n"{}" "{}" {} %*\n').format(quote(python), quote(script), name)
    return '#!/bin/sh\n# Loop ROS managed release launcher\nexec {} {} {} "$@"\n'.format(
        shlex.quote(str(python)), shlex.quote(str(script)), shlex.quote(name))


def command_paths():
    commands = Path.home() / '.local/bin'
    return [(name, commands / (name + '.cmd' if os.name == 'nt' else name)) for name in NAMES]


def is_our_launcher(path, root, name):
    if path.is_symlink():
        target = Path(os.readlink(path))
        if not target.is_absolute():
            target = path.parent / target
        return os.path.abspath(target) == str(venv_python(root / 'runtime').parent / name)
    try:
        return path.is_file() and path.read_text(encoding='utf-8') == launcher_text(root, name)
    except (UnicodeError, OSError):
        return False


def validate_commands(root, replace):
    for name, path in command_paths():
        if path.is_dir() and not path.is_symlink():
            raise ValueError('Command destination is a directory; preserved: ' + str(path))
        if (path.exists() or path.is_symlink()) and not is_our_launcher(path, root, name) and not replace:
            raise ValueError('Existing command preserved: ' + str(path) + '; use --replace-launchers to back it up and switch.')


def write_launchers(root, replace):
    validate_commands(root, replace)
    changed = []
    try:
        for name, path in command_paths():
            path.parent.mkdir(parents=True, exist_ok=True)
            if is_our_launcher(path, root, name) and not path.is_symlink():
                continue
            backup = backup_launcher(path) if path.exists() or path.is_symlink() else None
            changed.append((path, backup))
            # No in-place write through an existing symlink.
            with path.open('x', encoding='utf-8') as stream:
                stream.write(launcher_text(root, name))
            path.chmod(0o755)
    except BaseException:
        restore_launchers(changed)
        raise
    return changed


def restore_launchers(changed):
    for path, backup in reversed(changed):
        path.unlink(missing_ok=True)
        if backup is not None:
            backup.rename(path)


def state_guard(stack, state):
    if not state:
        return
    state = Path(state)
    stack.enter_context(state_startup(state))
    for directory in runtime_directories(state):
        for name in ('terminal.lock', 'task_service.lock'):
            path = directory / name
            if path.exists():
                stream = stack.enter_context(path.open('a+b'))
                try:
                    _lock(stream)
                except OSError:
                    raise RuntimeError('Close Loop ROS and its background service before updating: ' + str(directory)) from None
        viewer_guard(directory / 'viewer/owner.json')


def viewer_guard(owner):
    if owner.is_file():
        data = json.loads(owner.read_text())
        pid = data.get('pid')
        if pid and sys.platform.startswith('linux') and data.get('started'):
            proc = Path('/proc') / str(pid)
            try:
                matches = proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19] == data['started']
                matches = matches and proc.joinpath('cmdline').read_bytes().split(b'\0')[:-1] == [str(arg).encode() for arg in data.get('argv', [])]
            except (OSError, IndexError):
                matches = False
            if not matches:
                pid = None
        if pid:
            try:
                os.kill(int(pid), 0)
            except ProcessLookupError:
                pass
            else:
                raise RuntimeError('Close the recorded viewer before migrating/updating: PID ' + str(pid))


def install(url, terminal_only=None, replace_launchers=False, state_dir=None, target_version=None):
    url = base_url(url)
    data = manifest(url, target_version)
    payload = fetch(url + '/' + data['wheel'], 32 * 1024 * 1024)
    if hashlib.sha256(payload).hexdigest() != data['sha256']:
        raise ValueError('Release SHA-256 mismatch; nothing installed')
    root = user_home()
    with maintenance(root), ExitStack() as stack:
        old = read_record(root)
        if old.get('version') and version(data['version']) < version(old['version']):
            raise ValueError('Server version is older than the installed release; use update --rollback explicitly.')
        mode = terminal_only if terminal_only is not None else old.get('terminal_only', False)
        state = str(Path(state_dir).expanduser().resolve()) if state_dir else old.get('state_dir')
        state_guard(stack, state)
        validate_commands(root, replace_launchers)
        if old.get('version') == data['version'] and old.get('terminal_only') == mode and venv_python(Path(old['environment'])).exists():
            smoke(Path(old['environment']), data['version'])
            write_launchers(root, replace_launchers)
            print('Already current: ' + data['version'])
            return old
        uv = ensure_uv()
        # Stable dispatcher interpreter does not live in the environment being replaced.
        updater = root / 'updater'
        if not venv_python(updater).exists():
            subprocess.run([uv, 'venv', '--python', '3.12', str(updater)], check=True)
        environment = root / 'releases' / (data['version'] + '-' + uuid.uuid4().hex[:12])
        environment.parent.mkdir(parents=True, exist_ok=True)
        changed = []
        try:
            subprocess.run([uv, 'venv', '--python', '3.12', str(environment)], check=True)
            with tempfile.TemporaryDirectory(prefix='loop-release-') as directory:
                wheel = Path(directory) / data['wheel']
                wheel.write_bytes(payload)
                target = str(wheel) + ('' if mode else '[sim]')
                subprocess.run([uv, 'pip', 'install', '--python', str(venv_python(environment)), target], check=True)
            smoke(environment, data['version'])
            (environment / '.loop-release-root').write_text(str(root), encoding='utf-8')
            dispatcher = root / 'release-launcher.py'
            if dispatcher.exists() and dispatcher.read_text() != DISPATCHER:
                raise ValueError('Existing release dispatcher differs; preserved: ' + str(dispatcher))
            if not dispatcher.exists():
                dispatcher.write_text(DISPATCHER, encoding='utf-8')
            write_control(root)
            backup = backup_state(root, state, old.get('version', 'source'))
            record = {'state_backup': backup, 'state_schema': 1, 'version': data['version'], 'environment': str(environment), 'url': url,
                      'terminal_only': mode, 'state_dir': state, 'previous': snapshot(old)}
            changed = write_launchers(root, replace_launchers)
            # This is the activation commit. Old environment and state stay untouched.
            atomic_json(root / 'release.json', record)
        except BaseException:
            restore_launchers(changed)
            shutil.rmtree(environment, ignore_errors=True)
            raise
        configure_path(Path.home() / '.local/bin')
        print('Installed Loop ROS ' + data['version'] + '. Run loop; previous release is retained for rollback.')
        return record


def backup_state(root, state, label):
    if not state or not Path(state).is_dir():
        return None
    databases = list(Path(state).glob('*.sqlite'))
    if not databases:
        return None
    destination = root / 'state-backups' / (label + '-' + uuid.uuid4().hex[:12])
    destination.mkdir(parents=True, mode=0o700)
    for database in databases:
        target = destination / database.name
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(target) as output:
            source.backup(output)
        target.chmod(0o600)
    return str(destination)


def uninstall_release():
    root = user_home()
    if managed_home() is not None:
        raise ValueError('Use the downloaded uninstall.sh or bootstrap.pyz with an external Python to remove the running environment.')
    with maintenance(root), ExitStack() as stack:
        record = read_record(root)
        state_guard(stack, record.get('state_dir'))
        environments = []
        releases = root / 'releases'
        if releases.is_dir() and not releases.is_symlink():
            for environment in releases.iterdir():
                marker = environment / '.loop-release-root'
                if not environment.is_symlink() and marker.is_file() and marker.read_text().strip() == str(root):
                    environments.append(environment)
        for name, path in command_paths():
            if is_our_launcher(path, root, name):
                path.unlink()
        for environment in environments:
            shutil.rmtree(environment)
        updater = root / 'updater'
        if updater.is_dir() and not updater.is_symlink() and (updater / 'pyvenv.cfg').is_file():
            shutil.rmtree(updater)
        (root / 'release.json').unlink(missing_ok=True)
        (root / 'release-launcher.py').unlink(missing_ok=True)
        (root / 'release-control.pyz').unlink(missing_ok=True)
    print('Uninstalled managed Loop ROS runtimes and commands. Configuration, state, backups and uv preserved.')


def rollback():
    root = user_home()
    with maintenance(root), ExitStack() as stack:
        current = read_record(root)
        previous = current.get('previous')
        if not previous or not previous.get('environment'):
            raise ValueError('No previous managed release is available.')
        state_guard(stack, current.get('state_dir'))
        if previous.get('state_schema', 1) != current.get('state_schema', 1):
            raise ValueError('Rollback would require a state migration; restore a compatible state backup first.')
        smoke(Path(previous['environment']), previous['version'])
        restored = dict(previous, previous=snapshot(current))
        atomic_json(root / 'release.json', restored)
        print('Rolled back runtime to ' + restored['version'] + '; user data was not rolled back.')


def check_main():
    print(json.dumps(check(release_url(user_home()), __version__)))


def update_main(argv):
    parser = argparse.ArgumentParser(prog='loop update', description='Check, install or roll back a Loop ROS release')
    parser.add_argument('--check', action='store_true', help='Check only; no installation')
    parser.add_argument('--rollback', action='store_true', help='Activate the previous verified runtime; does not roll back user data')
    parser.add_argument('--url', help='Trusted HTTPS release base URL')
    parser.add_argument('--version', dest='target_version', help='Install a specific published stable version (no implicit downgrade)')
    parser.add_argument('--migrate', action='store_true', help='Explicitly move source/legacy commands to a managed release, preserving source state')
    parser.add_argument('--replace-launchers', action='store_true', help='Back up conflicting launchers')
    parser.add_argument('--state-dir', type=Path, help='Preserve an explicitly selected runtime state directory')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--terminal-only', dest='terminal_only', action='store_const', const=True, default=None)
    modes.add_argument('--sim', dest='terminal_only', action='store_const', const=False)
    args = parser.parse_args(argv)
    if args.rollback and (args.check or args.url or args.migrate or args.terminal_only is not None or args.target_version):
        parser.error('--rollback cannot be combined with check, URL, migration or dependency changes')
    root = user_home()
    if args.rollback:
        rollback(); return 0
    url = release_url(root, args.url)
    if args.check:
        current = read_record(root).get('version', __version__) if managed_home() else __version__
        if args.target_version:
            data = manifest(url, args.target_version)
            print(json.dumps({'installed': current, 'latest': data['version'], 'update_available': version(data['version']) > version(current), 'release_url': url}))
        else:
            print(json.dumps(check(url, current)))
        return 0
    state = args.state_dir
    if managed_home() is None:
        if not args.migrate:
            raise ValueError('This is a source/unmanaged installation. Use update --migrate to switch to a release; source files remain unchanged.')
        if state is None:
            from loop_robot.terminal.config import DEFAULT_STATE_DIR
            state = DEFAULT_STATE_DIR
    install(url, args.terminal_only, args.replace_launchers or args.migrate, state, args.target_version)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Install a verified Loop ROS release')
    parser.add_argument('--url')
    parser.add_argument('--check', action='store_true', help='Read release metadata without installing')
    parser.add_argument('--uninstall', action='store_true', help='Remove managed release environments and launchers; preserve user data')
    parser.add_argument('--replace-launchers', action='store_true')
    parser.add_argument('--state-dir', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--terminal-only', dest='terminal_only', action='store_const', const=True, default=None)
    modes.add_argument('--sim', dest='terminal_only', action='store_const', const=False)
    options = parser.parse_args()
    try:
        if options.check:
            print(json.dumps(manifest(release_url(user_home(), options.url))))
        elif options.uninstall:
            uninstall_release()
        else:
            install(release_url(user_home(), options.url), options.terminal_only, options.replace_launchers, options.state_dir)
    except Exception as error:
        parser.exit(1, 'Installation failed: ' + str(error) + '\n')
