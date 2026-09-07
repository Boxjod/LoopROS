"""Read/update Loop's own Markdown instructions; no application permission writes."""
from pathlib import Path
import hashlib
import re
from loop_robot.terminal.files import schema
from loop_robot.terminal.home import loop_home
from loop_robot.terminal.coding import atomic_text

HARNESS_TOOLS = [
    schema('harness_read','Read Loop user instructions: AGENTS.md or harness/NAME.md. Omit path to list them.', {'path':{'type':'string'}}, []),
    schema('harness_write','Create/update Loop user Markdown instructions. Existing files require expected_sha256 from harness_read. Reloaded on the next model call; cannot grant permissions.', {'path':{'type':'string'}, 'content':{'type':'string'}, 'expected_sha256':{'type':'string'}}, ['path','content']),
]
HARNESS_NAMES={t['function']['name'] for t in HARNESS_TOOLS}


def target(name):
    if not isinstance(name,str) or not (name=='AGENTS.md' or re.fullmatch(r'harness/[a-zA-Z0-9_-]+\.md',name)):
        raise ValueError('Use AGENTS.md or harness/NAME.md inside Loop home')
    root=loop_home().resolve();path=(root/name).resolve()
    if not path.is_relative_to(root): raise PermissionError('Harness path escapes Loop home')
    return path


def tool(app,name,args):
    if not isinstance(args,dict) or set(args)-{'path','content','expected_sha256'}: raise ValueError('Unsupported arguments')
    if name=='harness_read' and not args:
        root=loop_home()
        return {'files': sorted({'AGENTS.md', 'harness/workflow.md'} | {str(p.relative_to(root)) for p in (root/'harness').glob('*.md')})}
    path=target(args.get('path'))
    if name=='harness_read':
        if set(args)!={'path'}: raise ValueError('harness_read takes path only')
        if args['path'] == 'harness/workflow.md' and not path.exists():
            from loop_robot.terminal.config import ROOT
            return {'path': args['path'], 'content': (ROOT / 'configs/workflow_harness.md').read_text(encoding='utf-8'),
                    'sha256': None, 'inherited_default': True}
        data=path.read_bytes()
        if len(data)>96000: raise ValueError('Harness file too large')
        return {'path':args['path'],'content':data.decode('utf-8'),'sha256':hashlib.sha256(data).hexdigest()}
    if name!='harness_write': raise ValueError('Unknown harness tool')
    content=args.get('content')
    if not isinstance(content,str): raise ValueError('content must be text')
    root=loop_home();others=[root/'AGENTS.md',*sorted((root/'harness').glob('*.md'))]
    if len(content)+sum(len(p.read_text()) for p in others if p.is_file() and p.resolve()!=path)>24000:
        raise ValueError('Combined harness limit: 24000 characters')
    return {**atomic_text(app,path,content,args.get('expected_sha256'),require_hash=True),'reload':'next model call'}
