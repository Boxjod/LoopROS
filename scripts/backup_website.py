"""Back up explicit website sources over SSH to private storage; never publish."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--destination', default='/root/workspaces/LoopROS/website-source-backups')
    args = parser.parse_args()
    if args.host.startswith('-') or not PurePosixPath(args.destination).is_absolute() or '..' in PurePosixPath(args.destination).parts:
        parser.error('Use an explicit SSH host and absolute private destination')
    args.output.mkdir(parents=True, exist_ok=False)
    names = ['website/' + name for name in ('index.html', 'zh-CN.html', 'install.html', 'style.css', 'site.js', 'favicon.png', 'README.md', 'example.html')]
    names += ['assets/workbench/' + name for name in ('workbench.html', 'workbench.css', 'workbench.js', 'three.module.min.js', 'three.LICENSE.txt', 'THIRD_PARTY.md', 'README.md')]
    names += ['assets/logo.png', '_version.py', 'tests/website.test.cjs']
    names += ['scripts/' + name for name in ('build_website.py', 'publish_website.py', 'backup_website.py', 'validate_install_website.py')]
    manifest = {}
    for name in names:
        source = ROOT / name
        if source.is_symlink() or not source.is_file():
            raise ValueError('Missing or symlinked website source: ' + name)
        manifest[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    archive = args.output / 'website-source.tar.gz'
    with tarfile.open(archive, 'w:gz') as output:
        for name in names:
            output.add(ROOT / name, arcname=name, recursive=False)
        output.add(args.output / 'manifest.json', arcname='manifest.json')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    destination = args.destination.rstrip('/') + '/' + uuid.uuid4().hex
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', args.host]
    subprocess.run(ssh + ['umask 077 && mkdir -p -- ' + shlex.quote(destination)], check=True)
    remote = destination + '/website-source.tar.gz'
    subprocess.run(['scp', '-q', str(archive), args.host + ':' + shlex.quote(remote)], check=True)
    actual = subprocess.check_output(ssh + ['sha256sum -- ' + shlex.quote(remote)], text=True).split()[0]
    if actual != digest:
        raise ValueError('Server archive checksum differs')
    receipt = {'host': args.host, 'archive': remote, 'sha256': digest, 'files': len(names), 'remote_hash_verified': True}
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
