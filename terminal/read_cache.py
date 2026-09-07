"""Per-input local read reuse, keyed by canonical path, content and page arguments."""
import copy
import hashlib
import json
from pathlib import Path

NAMES={'read_file','skill_read','python_check'}


def call(app,name,args,execute):
    if name not in NAMES or not isinstance(args,dict): return execute(name,args)
    app.permissions.check(name,args)
    try:
        if name=='skill_read':
            if set(args)-{'name','path','offset','limit'}: return execute(name,args)
            from terminal.skills import _resolve
            from terminal.home import loop_home
            root=_resolve(loop_home()/'skills',args['name']).parent
            relative=args.get('path','SKILL.md')
            if not isinstance(relative,str) or Path(relative).is_absolute() or '..' in Path(relative).parts: return execute(name,args)
            path=(root/relative).resolve()
            if not path.is_relative_to(root): return execute(name,args)
        else:
            if set(args)-({'path','offset','limit'} if name=='read_file' else {'path'}): return execute(name,args)
            from terminal.coding import resolve
            path=resolve(app,args['path'])
        from terminal.files import _denied
        if _denied(path): return execute(name,args)
        if not path.is_file() or path.stat().st_size>1024*1024: return execute(name,args)
        raw=path.read_bytes()
        normalized={k:v for k,v in args.items() if k not in ('path','name')}
        if name!='python_check':
            total=len(raw.decode('utf-8').split('\n'))
            offset=args.get('offset') or 1
            limit=args.get('limit')
            if type(offset) is not int or offset<1 or (limit is not None and (type(limit) is not int or limit<1)):
                return execute(name,args)
            normalized['offset']=offset
            normalized['limit']=min(limit if limit is not None else total,max(0,total-offset+1))
            if name=='skill_read':
                normalized['resource_dirs']=[(folder,(root/folder).stat().st_mtime_ns if (root/folder).exists() else None) for folder in ('scripts','references','assets')]
        key=(name,str(path),hashlib.sha256(raw).hexdigest(),json.dumps(normalized,sort_keys=True))
    except (OSError,ValueError,KeyError,TypeError): return execute(name,args)
    cache=getattr(app,'local_read_cache',{})
    if key in cache:
        return {**copy.deepcopy(cache[key]),'_reused':True,'reuse_reason':'Local content and read arguments unchanged in this input; use this receipt to advance.'}
    result=execute(name,args)
    if isinstance(result,dict) and not result.get('error') and result.get('valid') is not False:
        if len(cache)>=64: cache.pop(next(iter(cache)))
        cache[key]=copy.deepcopy(result)
        app.local_read_cache=cache
    return result


def receipt_available(messages, identity, result):
    """A surviving call ID is insufficient after history compaction."""
    for message in messages:
        if message.get('role') != 'tool' or message.get('tool_call_id') != identity:
            continue
        try:
            prior = json.loads(message.get('content', ''))
        except (ValueError, TypeError):
            return False
        return (isinstance(prior, dict) and not prior.get('truncated')
                and prior.get('sha256') == result.get('sha256')
                and all(prior.get(key) == result.get(key) for key in
                        ('content', 'resources', 'imports', 'valid', 'start_line', 'end_line')))
    return False
