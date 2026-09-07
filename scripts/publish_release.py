"""Publish an audited static bundle over existing SSH access; immutable wheels, latest last."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import os
import shlex
import shutil
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_manifest import validate_manifest


def inventory(bundle):
    sums = {}
    for line in (bundle / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name:
            raise ValueError('Unsafe bundle path: ' + name)
        local = bundle / name
        if local.is_symlink() or not local.is_file() or hashlib.sha256(local.read_bytes()).hexdigest() != digest:
            raise ValueError('Bundle hash/type mismatch: ' + name)
        sums[name] = digest
    metadata = validate_manifest(json.loads((bundle / 'latest.json').read_text()))
    version = metadata['version']
    allowed = {'latest.json', 'versions/' + version + '/latest.json', 'bootstrap.pyz',
               'install.sh', 'uninstall.sh', 'install.ps1',
               'loop_ros-' + version + '-py3-none-any.whl'}
    if set(sums) != allowed:
        raise ValueError('Public bundle differs from the publication whitelist')
    if metadata['wheel'] not in sums or metadata['sha256'] != sums[metadata['wheel']]:
        raise ValueError('Manifest/wheel hash mismatch')
    pinned = validate_manifest(json.loads((bundle / 'versions' / version / 'latest.json').read_text()), version)
    if pinned != metadata:
        raise ValueError('Versioned manifest differs from latest.json')
    return metadata, sums


def deploy_local(bundle, destination):
    inventory(bundle)
    destination.mkdir(parents=True, exist_ok=True)
    import fcntl
    with (destination / '.publish.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _deploy_locked(bundle, destination)


def _deploy_locked(bundle, destination):
    metadata, sums = inventory(bundle)
    current = destination / 'latest.json'
    if current.exists():
        old = json.loads(current.read_text())
        if tuple(map(int, old['version'].split('.'))) > tuple(map(int, metadata['version'].split('.'))):
            raise ValueError('Refusing to publish an older latest version')
    for name, digest in sums.items():
        target = destination / name
        if target.is_symlink():
            raise ValueError('Refusing to replace a publication symlink: ' + name)
        if name.endswith('.whl') or name.startswith('versions/'):
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError('Immutable release already exists with different content: ' + name)
    # Validate everything before writing. Metadata switches only after all downloads exist.
    order = [name for name in sums if name != 'latest.json'] + ['SHA256SUMS', 'latest.json']
    for name in order:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name('.' + target.name + '.' + uuid.uuid4().hex)
        try:
            shutil.copyfile(bundle / name, temporary)
            temporary.chmod(0o644)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--host', help='Explicit authorized SSH destination, e.g. root@8.134.90.171')
    parser.add_argument('--destination', required=True, help='Public static directory on server')
    parser.add_argument('--staging-root', default='/root/workspaces/LoopROS/releases')
    parser.add_argument('--local', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    metadata, sums = inventory(args.bundle)
    if args.local:
        print(json.dumps(deploy_local(args.bundle, Path(args.destination))))
        return
    if not args.host or args.host.startswith('-'):
        parser.error('--host is required')
    for path in (args.destination, args.staging_root):
        if not PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts:
            parser.error('Remote paths must be absolute and contain no parent traversal')
    staging = args.staging_root.rstrip('/') + '/' + metadata['version'] + '-' + metadata['sha256'][:12]
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', args.host]
    subprocess.run(ssh + ['mkdir -p -- ' + shlex.quote(staging + '/bundle')], check=True)
    # scp copies only already-audited filenames, never the source working tree.
    for name in list(sums) + ['SHA256SUMS']:
        remote = staging + '/bundle/' + name
        subprocess.run(ssh + ['mkdir -p -- ' + shlex.quote(str(PurePosixPath(remote).parent))], check=True)
        subprocess.run(['scp', '-q', str(args.bundle / name), args.host + ':' + shlex.quote(remote)], check=True)
    helper = staging + '/publish_release.py'
    subprocess.run(['scp', '-q', str(Path(__file__).resolve()), args.host + ':' + shlex.quote(helper)], check=True)
    subprocess.run(['scp', '-q', str(Path(__file__).resolve().parents[1] / 'release_manifest.py'),
                    args.host + ':' + shlex.quote(staging + '/release_manifest.py')], check=True)
    command = ['python3', helper, '--local', '--bundle', staging + '/bundle', '--destination', args.destination]
    subprocess.run(ssh + [' '.join(shlex.quote(part) for part in command)], check=True)
    print('Published ' + metadata['version'] + '; verified server staging: ' + staging)


if __name__ == '__main__':
    main()
