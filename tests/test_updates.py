import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import release_client as release
import release_runtime as runtime


class UpdateTests(unittest.TestCase):
    def metadata(self, payload=b'wheel', **changes):
        data = {'version': '0.2.0', 'wheel': 'loop_ros-0.2.0-py3-none-any.whl',
                'sha256': hashlib.sha256(payload).hexdigest(), 'state_schema': 1}
        data.update(changes)
        return json.dumps(data).encode()

    def test_schema_and_requested_version_validation(self):
        with patch.object(release, 'fetch', return_value=self.metadata(state_schema=2)):
            with self.assertRaisesRegex(ValueError, 'migration'):
                release.manifest('https://example.invalid')
        with patch.object(release, 'fetch', return_value=self.metadata()) as fetch:
            release.manifest('https://example.invalid', '0.2.0')
            self.assertEqual(fetch.call_args.args[0], 'https://example.invalid/versions/0.2.0/latest.json')
            with self.assertRaisesRegex(ValueError, 'match'):
                release.manifest('https://example.invalid', '0.3.0')

    def test_failure_keeps_record_commands_and_data(self):
        for stage in ('smoke', 'commit'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / '.loop'
                root.mkdir()
                home = Path(directory)
                command = home / '.local/bin/loop'
                command.parent.mkdir(parents=True)
                command.write_text('old command')
                old = {'version': '0.1.0', 'environment': str(root / 'old'), 'terminal_only': True, 'url': 'https://example.invalid'}
                release.atomic_json(root / 'release.json', old)
                (root / 'config.json').write_text('user config')
                with patch.object(release, 'user_home', return_value=root), \
                     patch.object(release.Path, 'home', return_value=home), \
                     patch.object(release, 'fetch', side_effect=[self.metadata(), b'wheel']), \
                     patch.object(release, 'ensure_uv', return_value='uv'), \
                     patch.object(release.subprocess, 'run', side_effect=self.fake_uv), \
                     patch.object(release, 'smoke', side_effect=RuntimeError('failed smoke') if stage == 'smoke' else None), \
                     contextlib.redirect_stdout(io.StringIO()):
                    with patch.object(release, 'atomic_json', side_effect=OSError('failed commit')) if stage == 'commit' else contextlib.nullcontext():
                        with self.assertRaisesRegex((RuntimeError, OSError), 'failed'):
                            release.install('https://example.invalid', replace_launchers=True)
                self.assertEqual(release.read_record(root), old)
                self.assertEqual(command.read_text(), 'old command')
                self.assertEqual((root / 'config.json').read_text(), 'user config')
                self.assertEqual(list((root / 'releases').iterdir()), [])

    @staticmethod
    def fake_uv(command, **kwargs):
        if command[1] == 'venv':
            environment = Path(command[-1])
            environment.mkdir(parents=True)
            (environment / 'pyvenv.cfg').write_text('fixture')
        return subprocess.CompletedProcess(command, 0)

    def test_source_update_requires_explicit_migration(self):
        with patch.object(release, 'managed_home', return_value=None), \
             patch.object(release, 'release_url', return_value='https://example.invalid'), \
             patch.object(release, 'install') as install:
            with self.assertRaisesRegex(ValueError, '--migrate'):
                release.update_main([])
            install.assert_not_called()
            release.update_main(['--migrate', '--terminal-only', '--state-dir', '/tmp/source-state'])
            self.assertEqual(install.call_args.args[1:4], (True, True, Path('/tmp/source-state')))

    def test_preserves_mode_and_rejects_downgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = {'version': '0.3.0', 'terminal_only': True}
            release.atomic_json(root / 'release.json', old)
            with patch.object(release, 'user_home', return_value=root), \
                 patch.object(release, 'fetch', side_effect=[self.metadata(), b'wheel']), \
                 patch.object(release, 'ensure_uv') as uv:
                with self.assertRaisesRegex(ValueError, 'older'):
                    release.install('https://example.invalid')
                uv.assert_not_called()
            self.assertEqual(release.read_record(root), old)

    def test_database_backup_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / 'state'
            state.mkdir()
            with sqlite3.connect(state / 'conversation.sqlite') as db:
                db.execute('create table messages (text)')
                db.execute("insert into messages values ('preserved')")
            backup = release.backup_state(root, str(state), '0.1.0')
            with sqlite3.connect(Path(backup) / 'conversation.sqlite') as db:
                self.assertEqual(db.execute('select text from messages').fetchone()[0], 'preserved')
            previous = {'version': '0.1.0', 'environment': str(root / 'old'), 'terminal_only': True, 'state_schema': 1}
            current = {'version': '0.2.0', 'environment': str(root / 'new'), 'previous': previous, 'state_schema': 1}
            release.atomic_json(root / 'release.json', current)
            with patch.object(release, 'user_home', return_value=root), patch.object(release, 'smoke'), contextlib.redirect_stdout(io.StringIO()):
                release.rollback()
            self.assertEqual(release.read_record(root)['version'], '0.1.0')
            self.assertEqual(release.read_record(root)['previous']['version'], '0.2.0')

    def test_active_runtime_blocks_update_and_crash_releases_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = ('from pathlib import Path; import release_runtime as r; import sys,time; '
                    'r.managed_home=lambda:Path(sys.argv[1]); '
                    'session=r.runtime_session(); session.__enter__(); print("ready",flush=True); time.sleep(30)')
            process = subprocess.Popen([sys.executable, '-c', code, str(root)], stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(process.stdout.readline().strip(), 'ready')
                with self.assertRaisesRegex(RuntimeError, 'active'):
                    with runtime.maintenance(root):
                        pass
            finally:
                process.terminate(); process.wait(timeout=10); process.stdout.close()
            with runtime.maintenance(root):
                pass
            self.assertEqual(list((root / 'runtime-leases').glob('*.lock')), [])

    def test_maintenance_blocks_other_updater_and_new_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with runtime.maintenance(root):
                with self.assertRaisesRegex(RuntimeError, 'Another'):
                    with runtime.maintenance(root):
                        pass
                with patch.object(runtime, 'managed_home', return_value=root):
                    with self.assertRaisesRegex(RuntimeError, 'in progress'):
                        with runtime.runtime_session():
                            pass

    def test_download_size_bound_and_https_before_subprocess(self):
        with patch.object(release.shutil, 'which', return_value='curl'), \
             patch.object(release.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'HTTPS'):
                release.fetch('http://example.invalid', 10)
            run.assert_not_called()
        def download(command, **kwargs):
            Path(command[command.index('--output') + 1]).write_bytes(b'x' * 11)
            self.assertIn('--proto-redir', command)
            return subprocess.CompletedProcess(command, 0, '', '')
        with patch.object(release.shutil, 'which', return_value='curl'), patch.object(release.subprocess, 'run', side_effect=download):
            with self.assertRaisesRegex(ValueError, 'size limit'):
                release.fetch('https://example.invalid', 10)

    def test_publisher_refuses_mutating_an_existing_version(self):
        from scripts.publish_release import deploy_local
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, target = root / 'bundle', root / 'public'
            bundle.mkdir()
            metadata = json.loads(self.metadata())
            files = {'latest.json': json.dumps(metadata).encode(),
                     'versions/0.2.0/latest.json': json.dumps(metadata).encode(),
                     metadata['wheel']: b'wheel', 'bootstrap.pyz': b'zip fixture',
                     'install.sh': b'install', 'uninstall.sh': b'uninstall',
                     'install.ps1': b'powershell'}
            for name, content in files.items():
                path = bundle / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            (bundle / 'SHA256SUMS').write_text('\n'.join(hashlib.sha256(content).hexdigest() + '  ' + name for name, content in files.items()) + '\n')
            target.mkdir()
            (target / 'index.html').write_bytes(b'existing independent website')
            deploy_local(bundle, target)
            self.assertEqual((target / 'index.html').read_bytes(), b'existing independent website')
            deploy_local(bundle, target)  # Identical publication is idempotent.
            (bundle / 'index.html').write_bytes(b'accidental website')
            sums = (bundle / 'SHA256SUMS').read_text()
            (bundle / 'SHA256SUMS').write_text(sums + hashlib.sha256(b'accidental website').hexdigest() + '  index.html\n')
            with self.assertRaisesRegex(ValueError, 'whitelist'):
                deploy_local(bundle, target)
            (bundle / 'SHA256SUMS').write_text(sums)
            (target / metadata['wheel']).write_bytes(b'different previous artifact')
            before = (target / 'latest.json').read_bytes()
            with self.assertRaisesRegex(ValueError, 'Immutable'):
                deploy_local(bundle, target)
            self.assertEqual((target / 'latest.json').read_bytes(), before)

    def test_viewer_entry_refuses_maintenance_before_starting_scene(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / 'runtime'
            environment.mkdir()
            (environment / '.loop-release-root').write_text(str(root))
            worker = Path(__file__).resolve().parents[1] / 'toolchain/viewer_worker.py'
            code = ('import sys,runpy; from pathlib import Path; '
                    'sys.prefix=sys.argv[1]; sys.path.insert(0,str(Path(sys.argv[2]).parent)); '
                    'runpy.run_path(sys.argv[2],run_name="__main__")')
            with runtime.maintenance(root):
                result = subprocess.run([sys.executable, '-c', code, str(environment), str(worker)],
                                        capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('update is in progress', result.stderr)

    def test_source_migration_checks_remaining_terminal_and_gates_new_startup(self):
        from loop_robot.terminal.instances import TerminalInstance
        with tempfile.TemporaryDirectory() as directory:
            first = TerminalInstance(directory).__enter__()
            second = TerminalInstance(directory).__enter__()
            first.__exit__()
            try:
                with contextlib.ExitStack() as stack, self.assertRaisesRegex(RuntimeError, 'Close Loop ROS'):
                    release.state_guard(stack, directory)
            finally:
                second.__exit__()
            with contextlib.ExitStack() as stack:
                release.state_guard(stack, directory)
                with self.assertRaisesRegex(RuntimeError, 'migration'):
                    with TerminalInstance(directory):
                        pass
            with TerminalInstance(directory):
                pass

    def test_source_migration_checks_service_and_viewer_in_later_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            slot = state / 'terminals/2'
            slot.mkdir(parents=True)
            with (slot / 'task_service.lock').open('a+b') as stream:
                runtime._lock(stream)
                with contextlib.ExitStack() as stack, self.assertRaisesRegex(RuntimeError, 'Close Loop ROS'):
                    release.state_guard(stack, state)
            (slot / 'viewer').mkdir()
            (slot / 'viewer/owner.json').write_text(json.dumps({'pid': os.getpid()}))
            with contextlib.ExitStack() as stack, self.assertRaisesRegex(RuntimeError, 'viewer'):
                release.state_guard(stack, state)

    def test_publisher_rejects_conflicting_pinned_manifest_before_writing(self):
        from scripts.publish_release import deploy_local
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / 'bundle'
            data = json.loads(self.metadata())
            files = {'latest.json': json.dumps(data).encode(), data['wheel']: b'wheel',
                     'versions/0.2.0/latest.json': json.dumps({**data, 'sha256': '0' * 64}).encode(),
                     'bootstrap.pyz': b'fixture', 'install.sh': b'fixture',
                     'uninstall.sh': b'fixture', 'install.ps1': b'fixture'}
            for name, payload in files.items():
                path = bundle / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            (bundle / 'SHA256SUMS').write_text(''.join(
                hashlib.sha256(payload).hexdigest() + '  ' + name + '\n' for name, payload in files.items()))
            target = Path(directory) / 'public'
            with self.assertRaisesRegex(ValueError, 'Versioned manifest differs'):
                deploy_local(bundle, target)
            self.assertFalse(target.exists())

    def test_controller_carries_manifest_validation_from_package_import(self):
        from loop_robot import release_client as packaged
        with tempfile.TemporaryDirectory() as directory:
            packaged.write_control(Path(directory))
            result = subprocess.run([sys.executable, str(Path(directory) / 'release-control.pyz'), '--help'],
                                    cwd=directory, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_concurrent_source_start_waits_for_brief_slot_acquisition(self):
        from loop_robot.terminal.instances import TerminalInstance
        with tempfile.TemporaryDirectory() as directory:
            entered = threading.Event()
            failures = []
            def start():
                try:
                    with TerminalInstance(directory):
                        entered.set()
                except Exception as error:
                    failures.append(error)
            with runtime.state_startup(directory):
                thread = threading.Thread(target=start)
                thread.start()
                time.sleep(.05)
                self.assertFalse(entered.is_set())
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
            self.assertFalse(failures)
            self.assertTrue(entered.is_set())
