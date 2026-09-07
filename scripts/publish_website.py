"""Publish only exported website assets; preserve all release downloads and metadata."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
import uuid

FILES = ('index.html', 'zh-CN.html', 'install.html', 'style.css', 'site.js', 'favicon.png', 'logo.png', 'workbench.html', 'workbench.css', 'workbench.js', 'three.module.min.js', 'three.LICENSE.txt')
REMOTE = r'''import fcntl, hashlib, json, os, shutil, sys
from pathlib import Path
stage, destination = map(Path, sys.argv[1:3])
manifest = json.loads((stage/'website-manifest.json').read_text())
files = ('index.html','zh-CN.html','install.html','style.css','site.js','favicon.png','logo.png','workbench.html', 'workbench.css', 'workbench.js', 'three.module.min.js', 'three.LICENSE.txt')
if set(manifest) != set(files): raise SystemExit('Unexpected website files')
for name, digest in manifest.items():
    if hashlib.sha256((stage/name).read_bytes()).hexdigest()!=digest: raise SystemExit('Upload hash mismatch')
with (destination/'.publish.lock').open('a+b') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    metadata = json.loads((destination/'latest.json').read_text())
    protected = ['latest.json',metadata['wheel'],'bootstrap.pyz','install.sh','uninstall.sh','install.ps1','versions/'+metadata['version']+'/latest.json']
    before = {name:hashlib.sha256((destination/name).read_bytes()).hexdigest() for name in protected}
    previous = stage/'previous';previous.mkdir()
    for name in files+('SHA256SUMS',):
        path=destination/name
        if path.is_symlink(): raise SystemExit('Unexpected destination symlink')
        if path.exists(): shutil.copy2(path,previous/name)
    for name in files:
        temporary=destination/('.website-'+name)
        shutil.copyfile(stage/name,temporary);temporary.chmod(0o644)
        os.replace(temporary,destination/name)
    sums={}
    for line in (destination/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);sums[name]=digest
    sums.update(manifest)
    temporary=destination/'.website-sums'
    temporary.write_text(''.join(digest+'  '+name+'\n' for name,digest in sorted(sums.items())))
    temporary.chmod(0o644);os.replace(temporary,destination/'SHA256SUMS')
    after={name:hashlib.sha256((destination/name).read_bytes()).hexdigest() for name in protected}
    if before!=after: raise SystemExit('Release integrity changed')
print(json.dumps({'website_files':manifest,'release_version':metadata['version'],'release_downloads_unchanged':True,'backup':str(previous)}))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    if args.host.startswith('-') or not args.destination.startswith('/'):
        parser.error('Provide an SSH host and absolute destination')
    stage = '/root/workspaces/LoopROS/website/' + uuid.uuid4().hex
    manifest = {name: hashlib.sha256((args.bundle/name).read_bytes()).hexdigest() for name in FILES}
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name in FILES:
            if (args.bundle/name).is_symlink():
                raise ValueError('Refusing a source symlink')
            archive.add(args.bundle/name, arcname=name, recursive=False)
        for name, data in (('website-manifest.json',json.dumps(manifest).encode()),('deploy.py',REMOTE.encode())):
            entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o600
            archive.addfile(entry,io.BytesIO(data))
    command = 'mkdir -p ' + shlex.quote(stage) + ' && tar -xf - -C ' + shlex.quote(stage)
    subprocess.run(['ssh','-o','BatchMode=yes',args.host,command],input=stream.getvalue(),check=True)
    command = ' '.join(shlex.quote(p) for p in ('python3',stage+'/deploy.py',stage,args.destination))
    subprocess.run(['ssh','-o','BatchMode=yes',args.host,command],check=True)


if __name__ == '__main__':
    main()
