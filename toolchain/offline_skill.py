"""Executable Skill packages. Reading never executes; receipts never imply readiness."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from terminal.skills import _resolve, read, discover, _frontmatter
from terminal.home import loop_home


def package(name, platform=None):
    root = _resolve(loop_home() / 'skills', name).parent
    fields = _frontmatter(read(loop_home() / 'skills', name))
    if not fields or fields.get('name') != name or not fields.get('description'):
        raise ValueError('Valid SKILL.md name and description are required')
    manifest = root / 'run.json'
    if manifest.is_symlink() or manifest.stat().st_size > 32000:
        raise ValueError('Invalid run.json')
    raw = manifest.read_bytes()
    spec = json.loads(raw)
    if not isinstance(spec, dict) or set(spec) - {'version','title','platforms','cwd','env','env_names','remote'} or spec.get('version') != 1:
        raise ValueError('Invalid executable Skill manifest')
    if not isinstance(spec.get('title'), str) or not 1 <= len(spec['title']) <= 160 or any(ord(c)<32 for c in spec['title']):
        raise ValueError('A short readable Skill title is required')
    platforms = spec.get('platforms')
    if not isinstance(platforms, dict) or not platforms or set(platforms) - {'posix','nt'}:
        raise ValueError('Use posix/nt platform entries')
    files = {'run.json':raw, 'SKILL.md':(root/'SKILL.md').read_bytes()}
    for folder in (root/'scripts',):
        if folder.is_symlink(): raise ValueError('Skill scripts cannot be symlinks')
        for path in sorted(folder.rglob('*')):
            if path.is_symlink(): raise ValueError('Skill scripts cannot be symlinks')
            if path.is_file():
                if len(files) >= 100 or path.stat().st_size > 1024*1024: raise ValueError('Skill script package too large')
                files[str(path.relative_to(root))] = path.read_bytes()
    if sum(map(len, files.values())) > 1024*1024: raise ValueError('Skill package exceeds 1 MiB')
    for system, entry in platforms.items():
        if not isinstance(entry, dict) or not {'start'} <= set(entry) or set(entry)-{'start','stop'}:
            raise ValueError('Platform entry requires start and optional stop')
        for value in entry.values():
            if not isinstance(value,str) or Path(value).is_absolute() or '..' in Path(value).parts or value not in files or not value.startswith('scripts/'):
                raise ValueError('Entrypoints must be files under scripts/')
            if Path(value).suffix.lower() not in (('.sh',) if system == 'posix' else ('.bat','.cmd')):
                raise ValueError('Use .sh on POSIX, .bat/.cmd on Windows')
    cwd = spec.get('cwd', '.')
    if not isinstance(cwd,str) or (cwd != '.' and not Path(cwd).is_absolute()):
        raise ValueError('cwd must be . (package snapshot) or an absolute path')
    # Reuse the process environment/credential validator, without executing.
    from toolchain.process_node import validate_spec
    validate_spec(dict(argv=['skill-entry'],cwd=str(root), **{k:spec[k] for k in ('env','env_names','remote') if k in spec}))
    digest = hashlib.sha256()
    for key, value in sorted(files.items()):
        encoded = key.encode()
        digest.update(len(encoded).to_bytes(8,'big')+encoded+len(value).to_bytes(8,'big')+value)
    system = platform or os.name
    return dict(name=name,title=spec['title'],path=str(root),sha256=digest.hexdigest(),
                supported=system in platforms, platform=system, spec=spec, files=files)


def inspect(name):
    return {k:v for k,v in package(name).items() if k != 'files'}


def catalog():
    entries=[]
    for item in discover(loop_home()/'skills'):
        if not (_resolve(loop_home()/'skills',item['name']).parent/'run.json').exists(): continue
        try: entries.append(inspect(item['name']))
        except (ValueError,OSError) as exc: entries.append(dict(name=item['name'],title=item['description'],error=str(exc)))
    return entries


def resolve(title):
    entries = catalog()
    matches=[r for r in entries if title in (r['name'],r['title'])]
    if len(matches)!=1: raise ValueError('Choose one unique Skill title or name from /skills')
    return matches[0]['name']


def materialize(value):
    data = package(value['skill'])
    if data['sha256'] != value['expected_sha256']: raise ValueError('Skill changed; inspect it again')
    if not data['supported']: raise ValueError('Skill has no entrypoint for this platform')
    folder = tempfile.TemporaryDirectory(prefix='loop-skill-')
    try:
        root = Path(folder.name)
        for name, raw in data['files'].items():
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        entry=data['spec']['platforms'][os.name]
        def command(key):
            path=str(root/entry[key])
            if os.name == 'posix': return ['bash',path]
            if any(c in path for c in '%!&|<>^"\r\n'): raise ValueError('Unsafe Windows script path')
            return [os.environ.get('COMSPEC','cmd.exe'),'/d','/v:off','/c',path]
        spec={k:data['spec'][k] for k in ('env','env_names','remote') if k in data['spec']}
        spec.update(argv=command('start'),cwd=str(root) if data['spec'].get('cwd','.') == '.' else data['spec']['cwd'])
        if 'stop' in entry: spec['stop_argv']=command('stop')
        return spec, folder
    except BaseException:
        folder.cleanup();raise


def save_profile(profile_name, name, title):
    """Explicit operator export, never label an unverified profile as successful."""
    from toolchain.process_node import read_profile
    profile=read_profile(profile_name);spec=profile['spec']
    target=_resolve(loop_home()/'skills',name).parent
    if target.exists(): raise ValueError('Skill already exists; use a new name')
    if not isinstance(title,str) or not title.strip() or len(title)>160 or any(ord(c)<32 for c in title): raise ValueError('Invalid Skill title')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent,prefix='.skill-export-') as temporary:
        root=Path(temporary);(root/'scripts').mkdir()
        platforms={}
        # Export for the current host; do not pretend platform-specific commands are portable.
        suffix='.sh' if os.name=='posix' else '.cmd'
        entry={}
        for verb,key in (('start','argv'),('stop','stop_argv')):
            if not spec.get(key): continue
            argv=spec[key]
            if os.name=='posix': source='#!/usr/bin/env bash\nset -euo pipefail\nexec '+shlex.join(argv)+'\n'
            else:
                if any(any(c in arg for c in '%!&|<>^\"\r\n') for arg in argv): raise ValueError('Batch export requires arguments without cmd expansion characters')
                source='@echo off\r\nchcp 65001 >nul\r\n'+subprocess.list2cmdline(argv)+'\r\nexit /b %errorlevel%\r\n'
            relative='scripts/'+verb+suffix;(root/relative).write_bytes(source.encode('utf-8'));entry[verb]=relative
        platforms[os.name]=entry
        manifest={k:spec[k] for k in ('cwd','env','env_names','remote') if k in spec}
        manifest.update(version=1,title=title,platforms=platforms)
        (root/'run.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        (root/'SKILL.md').write_text('---\nname: '+name+'\ndescription: '+json.dumps(title,ensure_ascii=False)+'\n---\n\n'+
            'Run the saved process with `/skills run '+title+'`. Inspect `run.json` and scripts first.\n'+
            'Use `/skills status`, `/skills logs`, and `/skills stop` with this title.\n'+
            'Exported from process profile '+profile_name+'; prior task success is not inferred.\n'+
            'Process startup or exit zero does not prove robot readiness or task completion.\n')
        root.rename(target)
    return inspect(name)
