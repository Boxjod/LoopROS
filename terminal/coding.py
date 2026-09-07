"""Workspace file mutations and bounded discovery, with receipts and backups."""
import difflib
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import uuid

from loop_robot.terminal.files import schema, _denied

LOCK = threading.RLock()
LIMIT = 1024 * 1024
CODING_TOOLS = [
    schema('list_files', 'List a local directory. Relative paths use the current workspace.', {'path': {'type':'string'}}, []),
    schema('search_files', 'Find literal text in workspace UTF-8 files; bounded results, skips generated/private directories.', {'query':{'type':'string'}, 'path':{'type':'string'}}, ['query']),
    schema('write_file', 'Create a UTF-8 workspace file. To replace an existing file, supply its sha256 from read_file. Returns backup and diff. For auxiliary generated scripts use user_projects/PROJECT/robots/MODEL/scripts/ (omit robots/MODEL when unknown); maintain existing application source in place.', {'path':{'type':'string'}, 'content':{'type':'string'}, 'expected_sha256':{'type':'string'}}, ['path','content']),
    schema('edit_file', 'Replace one unique exact text in a workspace file, preserving surrounding content. Returns diff and backup.', {'path':{'type':'string'}, 'old_text':{'type':'string'}, 'new_text':{'type':'string'}, 'expected_sha256':{'type':'string'}}, ['path','old_text','new_text']),
]
CODING_NAMES = {t['function']['name'] for t in CODING_TOOLS}
SKIP = {'.git','.venv','node_modules','__pycache__','artifacts','.ssh','.codex','.claude'}


def resolve(app, value='.', write=False):
    if not isinstance(value,str) or not value: raise ValueError('path must be nonempty')
    path = Path(value).expanduser()
    path = (app.workspace_root / path if not path.is_absolute() else path).resolve()
    if _denied(path): raise PermissionError('Credentials and internal state are not accessible')
    if write:
        if not path.is_relative_to(app.workspace_root): raise PermissionError('Writes must stay inside the workspace: ' + str(app.workspace_root))
        if any(part in SKIP for part in path.relative_to(app.workspace_root).parts): raise PermissionError('Protected/generated directory; choose a source file')
        from loop_robot.terminal.config import ROOT
        if (app.workspace_root.resolve() == ROOT.resolve() and path.parent == ROOT.resolve()
                and not path.exists() and path.suffix.lower() in {'.py', '.sh', '.bash', '.ps1', '.bat', '.cmd'}):
            raise ValueError('New scripts must not clutter the Loop ROS package root. '
                             'Use user_projects/PROJECT/robots/MODEL/scripts/NAME (omit robots/MODEL if unknown); '
                             'maintained product code belongs in core/, terminal/, toolchain/ or scripts/.')
        from loop_robot.terminal.home import loop_home
        if path.is_relative_to(loop_home().resolve()): raise PermissionError('Use skill_write or harness_write for Loop configuration')
    return path


def atomic_text(app, path, content, expected=None, require_hash=False):
    if not isinstance(content,str) or len(content.encode()) > LIMIT: raise ValueError('Content limit: 1 MiB')
    with LOCK:
        exists = path.exists()
        if exists and (not path.is_file() or path.stat().st_size > LIMIT): raise ValueError('Target must be a text file of at most 1 MiB')
        before = path.read_bytes() if exists else b''
        previous = hashlib.sha256(before).hexdigest() if exists else None
        if (expected is not None and expected != previous) or (exists and require_hash and expected is None):
            raise ValueError('File changed or overwrite hash missing; read it again before writing')
        old = before.decode('utf-8')
        backup = None
        if exists:
            folder=app.state_dir/'file-backups';folder.mkdir(parents=True,exist_ok=True)
            backup=folder/(uuid.uuid4().hex+'.txt');backup.write_bytes(before);backup.chmod(0o600)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.loop-write-', dir=path.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8',newline='') as stream:
                stream.write(content)
            os.chmod(temporary, path.stat().st_mode & 0o777 if exists else 0o644)
            os.replace(temporary,path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        before_lines, after_lines = old.splitlines(), content.splitlines()
        diff='\n'.join(difflib.unified_diff(before_lines,after_lines,fromfile=str(path),tofile=str(path),lineterm=''))
        changes=difflib.SequenceMatcher(a=before_lines,b=after_lines).get_opcodes()
        added=sum(j2-j1 for op,i1,i2,j1,j2 in changes if op in ('insert','replace'))
        removed=sum(i2-i1 for op,i1,i2,j1,j2 in changes if op in ('delete','replace'))
        return {'path':str(path),'written':True,'sha256':digest,'previous_sha256':previous,'backup':str(backup) if backup else None,'diff':diff[:12000],'diff_truncated':len(diff)>12000,'lines_added':added,'lines_removed':removed}


def tool(app,name,args):
    if not isinstance(args,dict): raise ValueError('arguments must be an object')
    allowed={
        'list_files':{'path'}, 'search_files':{'path','query'},
        'write_file':{'path','content','expected_sha256'},
        'edit_file':{'path','old_text','new_text','expected_sha256'},
    }
    if name not in allowed or set(args)-allowed[name]: raise ValueError('Unsupported arguments')
    path=resolve(app,args.get('path','.'),write=name in ('write_file','edit_file'))
    if name=='list_files':
        if not path.is_dir(): raise ValueError('Not a directory')
        entries=sorted(p for p in path.iterdir() if p.name not in SKIP and not _denied(p.resolve()))
        return {'path':str(path),'entries':[{'name':p.name,'directory':p.is_dir()} for p in entries[:200]],'truncated':len(entries)>200}
    if name=='search_files':
        query=args.get('query')
        if not isinstance(query,str) or not query: raise ValueError('query must be nonempty literal text')
        matches=[]; scanned=0
        roots=os.walk(path) if path.is_dir() else [(path.parent,[],[path.name])]
        for root,dirs,files in roots:
            dirs[:]=[d for d in dirs if d not in SKIP
                     and not (d == 'user_projects' and Path(root) == app.workspace_root)
                     and not (Path(root)/d).is_symlink()]
            for filename in sorted(files):
                file=Path(root)/filename; scanned+=1
                if scanned>2000: return {'matches':matches,'truncated':True}
                if file.is_symlink() or _denied(file.resolve()): continue
                try:
                    if file.stat().st_size>LIMIT: continue
                    text=file.read_text(encoding='utf-8')
                except (OSError,UnicodeError): continue
                for number,line in enumerate(text.splitlines(),1):
                    if query in line:
                        matches.append({'path':str(file),'line':number,'text':line[:1000]})
                        if len(matches)>=100: return {'matches':matches,'truncated':True}
        return {'matches':matches,'truncated':False}
    if name=='write_file': return atomic_text(app,path,args.get('content'),args.get('expected_sha256'),require_hash=True)
    with LOCK:
        if not path.is_file() or path.stat().st_size>LIMIT: raise ValueError('Read an existing text file first')
        text=path.read_bytes().decode('utf-8');old=args.get('old_text');new=args.get('new_text')
        if not isinstance(old,str) or not old or not isinstance(new,str) or text.count(old)!=1: raise ValueError('old_text must match exactly once; read a larger unique context')
        return atomic_text(app,path,text.replace(old,new,1),args.get('expected_sha256'))
