"""Master API for persistent, supervised goals and named event triggers."""
from core.tasks import TaskStore
from terminal.task_supervisor import load_policy
from terminal.task_service import policy_path

CHECK={'type':'object','properties':{'tool':{'type':'string'},'path':{'type':'string'},'equals':{},'arguments':{'type':'object'}},'required':['tool','path','equals'],'additionalProperties':False}

def schema(name,description,properties,required=()):
    return {'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':list(required),'additionalProperties':False}}}

TASK_TOOLS=[
 schema('task_submit','将未完成目标交给持久任务监督器；checks是明确的工具回执验收条件。未满足继续反馈迭代，无验收条件不得宣称成功。',{'goal':{'type':'string'},'checks':{'type':'array','items':CHECK}},['goal']),
 schema('task_status','查询任务状态和反馈；默认只列当前 Session 任务，scope=all 显式查看历史。具体 task_id 可跨会话查询。',{'task_id':{'type':'string'},'scope':{'type':'string','enum':['session','all']}}),
 schema('task_resume','补充验收条件并唤醒等待任务，不重放原始命令。',{'task_id':{'type':'string'},'checks':{'type':'array','items':CHECK},'message':{'type':'string'}},['task_id']),
 schema('task_cancel','停止后续任务执行；不回滚已执行动作。',{'task_id':{'type':'string'}},['task_id']),
 schema('task_signal','发送已配置的事件触发器；不执行任意shell或扩大工具授权。',{'name':{'type':'string'},'payload':{'type':'object'}},['name'])]
NAMES={s['function']['name'] for s in TASK_TOOLS}


def dispatch(app,name,args):
    from terminal.task_service import start,status
    store=TaskStore(app.state_dir/'tasks.sqlite')
    if name=='task_status':
        if set(args)-{'task_id','scope'} or args.get('scope','session') not in ('session','all'): raise ValueError('task_status accepts task_id and scope=session|all')
        return {'service':status(app.state_dir), 'scope':args.get('scope','session'), 'session_id':app.session_id,
                'task':store.get(args['task_id']) if args.get('task_id') else store.list(session_id=None if args.get('scope')=='all' else app.session_id)}
    if name=='task_cancel':
        if set(args)!={'task_id'}: raise ValueError('task_id required')
        return store.cancel(args['task_id'])
    app.permissions.check('spawn_agent',{'persistent_task':name,**args})
    if name=='task_submit':
        if set(args)-{'goal','checks'}: raise ValueError('task_submit accepts goal and checks')
        spec={**args,'session_id':app.session_id,'origin':'manual','provider':[app.client.config['base_url'].rstrip('/'),app.client.config['model'],app.client.config.get('protocol','openai')]}
        result=store.submit(spec)
    elif name=='task_resume':
        if set(args)-{'task_id','checks','message'} or 'task_id' not in args: raise ValueError('task_id required')
        result=store.resume(args['task_id'],args.get('checks'),args.get('message'))
    elif name=='task_signal':
        if set(args)-{'name','payload'}: raise ValueError('Unexpected trigger fields')
        from terminal.app import TOOLS
        policy=load_policy(policy_path(app.state_dir),{t['function']['name'] for t in TOOLS})
        if not any(t['enabled'] and t['event']==args['name'] for t in policy['triggers']): raise ValueError('No enabled trigger is configured for this event')
        result={'signal_id':store.signal(args['name'],args.get('payload',{}))}
    else: raise ValueError('Unknown task tool')
    return {'task':result,'service':start(app)}


def resolve_reference(app, reference):
    """Operator titles resolve within the current conversation before history."""
    store = TaskStore(app.state_dir / 'tasks.sqlite')
    try:
        return store.get(reference)['id']
    except ValueError:
        pass
    from terminal.titles import task_title
    for tasks in (store.list(limit=None, session_id=app.session_id), store.list(limit=None)):
        matches = [task for task in tasks if task_title(task) == reference or task['spec']['goal'] == reference]
        if len(matches) == 1:
            return matches[0]['id']
        if matches:
            raise ValueError('Several tasks share this title; select the task in its conversation panel')
    raise ValueError('Task not found; choose a title from /tasks or /tasks all')
