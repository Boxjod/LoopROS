"""Master API for persistent, supervised goals and named event triggers."""
from core.tasks import TaskStore
from terminal.task_supervisor import load_policy
from terminal.task_service import policy_path

CHECK={'type':'object','properties':{'tool':{'type':'string'},'path':{'type':'string'},'equals':{},'arguments':{'type':'object'}},'required':['tool','path','equals'],'additionalProperties':False}

def schema(name,description,properties,required=()):
    return {'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':list(required),'additionalProperties':False}}}

TASK_TOOLS=[
 schema('task_submit','将未完成目标交给持久任务监督器；checks是明确的工具回执验收条件。未满足继续反馈迭代，无验收条件不得宣称成功。',{'goal':{'type':'string'},'checks':{'type':'array','items':CHECK}},['goal']),
 schema('task_status','查询任务状态、上轮反馈及负责进程；ID为空列任务。',{'task_id':{'type':'string'}}),
 schema('task_resume','补充验收条件并唤醒等待任务，不重放原始命令。',{'task_id':{'type':'string'},'checks':{'type':'array','items':CHECK},'message':{'type':'string'}},['task_id']),
 schema('task_cancel','停止后续任务执行；不回滚已执行动作。',{'task_id':{'type':'string'}},['task_id']),
 schema('task_signal','发送已配置的事件触发器；不执行任意shell或扩大工具授权。',{'name':{'type':'string'},'payload':{'type':'object'}},['name'])]
NAMES={s['function']['name'] for s in TASK_TOOLS}


def dispatch(app,name,args):
    from terminal.task_service import start,status
    store=TaskStore(app.state_dir/'tasks.sqlite')
    if name=='task_status':
        if set(args)-{'task_id'}: raise ValueError('task_status accepts task_id only')
        return {'service':status(app.state_dir),'task':store.get(args['task_id']) if args.get('task_id') else store.list()}
    if name=='task_cancel':
        if set(args)!={'task_id'}: raise ValueError('task_id required')
        return store.cancel(args['task_id'])
    app.permissions.check('spawn_agent',{'persistent_task':name,**args})
    if name=='task_submit':
        if set(args)-{'goal','checks'}: raise ValueError('task_submit accepts goal and checks')
        spec={**args,'origin':'manual','provider':[app.client.config['base_url'].rstrip('/'),app.client.config['model'],app.client.config.get('protocol','openai')]}
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
