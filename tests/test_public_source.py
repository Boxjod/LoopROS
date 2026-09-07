import subprocess
import tempfile
from pathlib import Path
import unittest
from scripts.build_release import public_source


class PublicSourceTests(unittest.TestCase):
    def test_ignored_even_when_force_staged_and_untracked_files_never_copied(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'repo';root.mkdir()
            subprocess.run(['git','init','-q',str(root)],check=True)
            (root/'.gitignore').write_text('toolchain/candidates/\n.loop/\n/local_tool.py\n')
            files=['pyproject.toml','launcher.py','local_tool.py','toolchain/candidates/probe.py','.loop/skills/custom/SKILL.md','user_projects/private/robots/model/scripts/probe.py']
            for name in files:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('source')
            subprocess.run(['git','-C',str(root),'add','-f','--','.gitignore',*files],check=True)
            (root/'untracked.py').write_text('private')
            (root/'launcher.py').write_text('current working source')
            output=public_source(root,Path(folder)/'public')
            self.assertEqual((output/'launcher.py').read_text(),'current working source')
            for name in files[2:]+['untracked.py']:
                self.assertFalse((output/name).exists(),name)

    def test_repository_index_excludes_ignored_user_content(self):
        root = Path(__file__).resolve().parents[1]
        ignored = subprocess.check_output(
            ['git', '-C', str(root), 'ls-files', '-ci', '--exclude-standard'], text=True)
        self.assertEqual(ignored, '', 'Remove local user content from the Git index')
        tracked = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--', 'user_projects'], text=True)
        self.assertEqual(tracked, '', 'User projects must never be staged')
