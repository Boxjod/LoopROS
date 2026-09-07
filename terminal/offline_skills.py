"""Offline Skill commands using the existing process-node lifecycle."""
import hashlib
import json
import shlex
from terminal.skills import schema

TOOLS = [
    schema('skill_executables', 'Inspect offline executable Skills, readable titles, platform support, scripts and package hashes. Does not execute.', {}, []),
    schema('skill_run', 'Run an inspected executable Skill without an LLM. Requires current package sha256 and existing process-node permissions. Returns process acceptance, not task success.', {'name':{'type':'string'},'expected_sha256':{'type':'string'}}, ['name','expected_sha256']),
    schema('skill_export', 'On user request, save an existing process profile as a new offline Skill with Bash or batch entrypoints for this host. Does not execute or certify past success; never overwrites an existing Skill.', {'profile':{'type':'string'},'name':{'type':'string'},'title':{'type':'string'}}, ['profile','name','title']),
]
NAMES={t['function']['name'] for t in TOOLS}


def node_name(name):
    return 'skill-' + hashlib.sha256(name.encode()).hexdigest()[:16]


def tool(app, name, args):
    from toolchain.offline_skill import catalog, save_profile, inspect
    fields={'skill_executables':set(),'skill_run':{'name','expected_sha256'},'skill_export':{'profile','name','title'}}
    if not isinstance(args,dict) or set(args)!=fields[name]: raise ValueError('Invalid executable Skill arguments')
    app.permissions.check(name,args)
    if name=='skill_executables':
        return {'skills':catalog()}
    if name=='skill_export': return save_profile(args['profile'],args['name'],args['title'])
    data=inspect(args['name'])
    if data['sha256']!=args['expected_sha256']: raise ValueError('Skill changed; inspect it again')
    result=app.tool('node_start',dict(kind='process',name=node_name(args['name']),config={'skill':args['name'],'expected_sha256':args['expected_sha256']}))
    if not hasattr(app,'offline_skill_runs'): app.offline_skill_runs={}
    app.offline_skill_runs[args['name']] = data['title']
    return {'title':data['title'],'skill':args['name'],'execution':result,'task_success':'not_verified'}


def dispatch(app, tail):
    from toolchain.offline_skill import inspect, resolve
    parts=shlex.split(tail)
    if not parts or parts==['list']:
        rows=app.tool('skill_executables',{})['skills']
        return '\n'.join([r['title']+' ['+r['name']+']'+(' — unavailable: '+r['error'] if 'error' in r else ' — current platform' if r['supported'] else ' — other platform') for r in rows]) or 'No executable Skills. Use /skills save PROFILE NAME TITLE.'
    if parts[0]=='save' and len(parts)>=4:
        return json.dumps(app.tool('skill_export',dict(profile=parts[1],name=parts[2],title=' '.join(parts[3:]))),ensure_ascii=False)
    if parts[0] in ('run','inspect','status','logs','stop') and len(parts)>1:
        reference=' '.join(parts[1:])
        active=[name for name,title in getattr(app,'offline_skill_runs',{}).items() if reference in (name,title)] if parts[0] in ('status','logs','stop') else []
        if len(active)>1: raise ValueError('Several running Skills share this title; use the Skill name')
        name=active[0] if active else resolve(reference)
        if parts[0]=='inspect':
            app.permissions.check('skill_executables',{})
            return json.dumps(inspect(name),ensure_ascii=False)
        if parts[0]=='run':
            data=inspect(name)
            return json.dumps(app.tool('skill_run',dict(name=name,expected_sha256=data['sha256'])),ensure_ascii=False)
        result=app.tool('node_'+parts[0],{'name':node_name(name)})
        return json.dumps({'title':' '.join(parts[1:]),'execution':result},ensure_ascii=False)
    raise ValueError('Usage: /skills [list|inspect TITLE|run TITLE|status TITLE|logs TITLE|stop TITLE|save PROFILE NAME TITLE]')
