import subprocess
import tempfile
from pathlib import Path
import unittest
import sys
from scripts.build_release import public_source, validate_source, expected_files
from scripts.check_public_source import check


class PublicSourceTests(unittest.TestCase):
    def test_ignored_even_when_force_staged_and_untracked_files_never_copied(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'repo';root.mkdir()
            subprocess.run(['git','init','-q',str(root)],check=True)
            (root/'.gitignore').write_text('toolchain/candidates/\n.loop/\n/local_tool.py\n')
            files=['pyproject.toml','launcher.py','local_tool.py','toolchain/candidates/probe.py','.loop/skills/custom/SKILL.md','user_projects/private/robots/model/scripts/probe.py','website/index.html','examples/demo.xml']
            for name in files:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('source')
            subprocess.run(['git','-C',str(root),'add','-f','--','.gitignore',*files],check=True)
            with self.assertRaisesRegex(ValueError, 'cannot be uploaded'):
                check(root)
            (root/'untracked.py').write_text('private')
            (root/'launcher.py').write_text('current working source')
            output=public_source(root,Path(folder)/'public')
            self.assertEqual((output/'launcher.py').read_text(),'current working source')
            for name in files[2:]+['untracked.py']:
                self.assertFalse((output/name).exists(),name)

    def test_new_runtime_module_requires_explicit_source_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', folder], check=True)
            (root / 'terminal').mkdir()
            (root / 'terminal/required.py').write_text('value = 1\n')
            with self.assertRaisesRegex(ValueError, 'terminal/required.py'):
                validate_source(root)
            subprocess.run(['git', '-C', folder, 'add', 'terminal/required.py'], check=True)
            validate_source(root)

    def test_private_content_in_earlier_outgoing_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                return subprocess.check_output(['git', '-C', folder, '-c', 'user.name=Fixture',
                    '-c', 'user.email=fixture@example.invalid', *args], text=True).strip()
            git('init', '-q')
            (root / '.gitignore').write_text('user_projects/\n')
            (root / 'user_projects').mkdir()
            (root / 'user_projects/private.py').write_text('fixture')
            git('add', '-f', '.gitignore', 'user_projects/private.py')
            git('commit', '-qm', 'Private fixture')
            previous = git('rev-parse', 'HEAD')
            git('rm', '--cached', 'user_projects/private.py')
            git('commit', '-qm', 'Clean final tree')
            check(root)
            with self.assertRaisesRegex(ValueError, 'user_projects/private.py'):
                check(root, previous)

    @unittest.skipUnless(sys.version_info >= (3, 11), 'Release builder uses Python 3.11+')
    def test_declared_resource_must_exist_in_source_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'pyproject.toml').write_text('''[tool.setuptools]
packages = ["loop_robot"]
[tool.setuptools.package-data]
loop_robot = ["configs/required.json"]
''')
            with self.assertRaisesRegex(ValueError, 'Missing declared package data'):
                expected_files(root)
            (root / 'configs').mkdir()
            (root / 'configs/required.json').write_text('{}')
            self.assertIn('loop_robot/configs/required.json', expected_files(root))

    def test_repository_index_excludes_ignored_user_content(self):
        root = Path(__file__).resolve().parents[1]
        ignored = subprocess.check_output(
            ['git', '-C', str(root), 'ls-files', '-ci', '--exclude-standard'], text=True)
        self.assertEqual(ignored, '', 'Remove local user content from the Git index')
        tracked = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--', 'user_projects'], text=True)
        self.assertEqual(tracked, '', 'User projects must never be staged')
        website = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--', 'website'], text=True)
        self.assertEqual(website, '', 'Website server source must stay outside the public index')

    def test_core_imports_use_one_package_identity_outside_project(self):
        code = '''import sys
from loop_robot.core.resources import ResourceBusy
from loop_robot.terminal.agents import ResourceBusy as AgentResourceBusy
from loop_robot.core.loop import Loop
from loop_robot.toolchain.feedback import Loop as SimulationLoop
from loop_robot.core.memory_layers import MemoryLayers
assert ResourceBusy is AgentResourceBusy
assert Loop is SimulationLoop
assert not {'core', 'terminal', 'toolchain'}.intersection(sys.modules)
'''
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=directory,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_previous_updater_bootstrap_imports_alias_canonical_modules(self):
        code = '''from loop_robot.launcher import _bootstrap
_bootstrap()
import terminal.app, model_switch
import loop_robot.terminal.app, loop_robot.model_switch
assert terminal.app is loop_robot.terminal.app
assert model_switch is loop_robot.model_switch
'''
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=directory,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
