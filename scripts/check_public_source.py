"""Reject private files in the index or outgoing Git commits before upload."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOTS = {'user_projects', 'website', 'skills', 'user_skills', 'user_tools',
                 'artifacts', 'reference', '.loop', '.looper', '.venv'}


def forbidden_paths(root, names):
    names = list(names)
    if not names:
        return []
    ignored = subprocess.run(['git', '-C', str(root), 'check-ignore', '--no-index', '-z', '--stdin'],
                             input=('\0'.join(names) + '\0').encode(), capture_output=True)
    if ignored.returncode not in (0, 1):
        raise RuntimeError('Cannot inspect source ignore rules')
    excluded = set(ignored.stdout.decode().split('\0'))
    return sorted(name for name in names if name in excluded or Path(name).parts[0] in PRIVATE_ROOTS
                  or name.startswith('toolchain/candidates/'))


def check(root=ROOT, revision=None):
    args = ['ls-tree', '-rz', '--name-only', revision] if revision else ['ls-files', '-z']
    names = subprocess.check_output(['git', '-C', str(root), *args]).decode().split('\0')
    invalid = forbidden_paths(root, filter(None, names))
    if invalid:
        raise ValueError('Private/ignored source cannot be uploaded:\n' + '\n'.join(invalid))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pre-push', action='store_true')
    args = parser.parse_args()
    check()
    if args.pre_push:
        commits = set()
        for line in sys.stdin:
            _, local, _, remote = line.split()
            if set(local) == {'0'}:
                continue
            revisions = [remote + '..' + local] if set(remote) != {'0'} else [local, '--not', '--remotes']
            commits.update(subprocess.check_output(['git', '-C', str(ROOT), 'rev-list', *revisions], text=True).splitlines())
        for revision in commits:
            check(revision=revision)
    print('Public source index/outgoing inventory passed.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
