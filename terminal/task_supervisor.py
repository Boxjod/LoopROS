"""Supervise repeated subprocess attempts against explicit acceptance checks."""
import hashlib
import json
from pathlib import Path
import time
from core.tasks import assess, validate_spec
from terminal.agents import AgentRuntime, ResourceBusy

FEEDBACK_TOOL={'type':'function','function':{'name':'task_feedback','description':'报告本轮反馈和下一步；不能自行宣布验收成功。缺输入/外部条件时明确等待原因。','parameters':{'type':'object','properties':{'state':{'type':'string','enum':['continue','needs_input']},'reason':{'type':'string'},'next_step':{'type':'string'}},'required':['state','reason','next_step'],'additionalProperties':False}}}
PROMPT='''你是持久任务的执行子Agent。每轮依据原始目标、明确验收条件和上轮实际反馈修正方案。
工具成功或文字完成不代表目标成功；只有监督器检查原始工具回执才能判定完成。绝不编造证据。
先检查上次操作实际结果，不重复有不确定副作用的命令。没有满足全部验收条件就继续观察或换方法。
工具范围由配置和权限限制；缺少输入/权限/外部条件通过task_feedback报告needs_input及缺失项；否则报告continue和具体下一步。
不能启动更多子Agent、改配置、改权限或自行扩任务范围。最终回答不是成功凭据。'''


def load_policy(path,allowed_tools):
    data=json.loads(Path(path).read_text())
    # Accept existing files without re-enabling removed implicit task creation.
    data.pop('auto_handoff', None)
    data.pop('success_profiles', None)
    expected={'version','max_workers','attempt_timeout_s','retry_initial_s','retry_max_s','stalled_attempts','worker_tools','scheduled_tools','schedules','triggers'}
    if set(data)!=expected or data['version']!=1: raise ValueError('Invalid task_runtime.json schema')
    for key,lo,hi in [('max_workers',1,108),('attempt_timeout_s',5,3600),('retry_initial_s',1,3600),('retry_max_s',1,86400),('stalled_attempts',1,20)]:
        if type(data[key]) is not int or not lo<=data[key]<=hi: raise ValueError('Invalid '+key)
    if data['retry_max_s']<data['retry_initial_s']: raise ValueError('retry_max_s must be >= retry_initial_s')
    forbidden={'tool_read','tool_write','tool_run','python_check','session_task_read','session_task_update','settings_update','settings_read','task_submit','task_resume','task_signal','task_cancel','spawn_agent','send_agent','skill_write','policy_start','carrier_start','carrier_command','carrier_stop','feetech_scan','feetech_read','run_python'}
    for key in ('worker_tools','scheduled_tools'):
        if not isinstance(data[key],list) or len(data[key])!=len(set(data[key])) or not set(data[key])<=set(allowed_tools) or set(data[key]) & forbidden: raise ValueError('Invalid tool grants: '+key)
    if not set(data['scheduled_tools'])<=set(data['worker_tools']): raise ValueError('Scheduled grants cannot exceed worker grants')
    for group in ('schedules','triggers'):
        if not isinstance(data[group],list) or len(data[group])>100: raise ValueError('At most 100 '+group)
        seen=set()
        for entry in data[group]:
            required={'name','enabled','task','every_s' if group=='schedules' else 'event'}
            if not isinstance(entry,dict) or set(entry)!=required or type(entry['enabled']) is not bool or not isinstance(entry['name'],str) or not entry['name'] or entry['name'] in seen: raise ValueError('Invalid '+group+' entry')
            seen.add(entry['name']);validate_spec(entry['task'])
            if any(c['tool'] not in data['scheduled_tools'] for c in entry['task'].get('checks',[])): raise ValueError('Scheduled check exceeds configured grants')
            if group=='schedules' and (type(entry['every_s']) is not int or entry['every_s']<1): raise ValueError('every_s must be positive integer')
            if group=='triggers' and (not isinstance(entry['event'],str) or not 1<=len(entry['event'])<=100): raise ValueError('Invalid event name')
    return data


class TaskSupervisor:
    def __init__(self,store,policy,clients,schemas,dispatch,event_path,provider,worker_target=None,learning=None,admission=None):
        self.learning = learning
        self.store,self.policy,self.dispatch,self.provider=store,policy,dispatch,provider
        definitions={name:{'provider':'llm','tools':policy[key]+['task_feedback'],'prompt':PROMPT} for name,key in [('TaskWorker','worker_tools'),('TaskScheduled','scheduled_tools')]}
        definitions['TaskReplanner']={'provider':'llm','tools':['task_feedback'],'prompt':PROMPT+'\n本轮只重新规划：分析重复失败的根因，明确不同于上轮的下一步；不执行原始动作，不自称验收通过。'}
        options={'worker_target':worker_target} if worker_target else {}
        self.runtime=AgentRuntime(definitions,clients,schemas+[FEEDBACK_TOOL],self.tool,event_path,
                                  max_workers=policy['max_workers'],timeout_s=policy['attempt_timeout_s'],admission=admission,**options)
        self.runtime.before_tool=self.before_tool;self.runtime.after_tool=self.after_tool
        self.running={};self.round_receipts={};self.stopping=False
        for task in store.list(limit=None):
            if task['state']=='running':
                store.update(task['id'],'waiting_observation',{'reason':'Supervisor restarted during an attempt; verify prior effects before explicitly resuming'})

    def tool(self,name,args):
        if name=='task_feedback':
            if set(args)!={'state','reason','next_step'} or args['state'] not in ('continue','needs_input') or any(not isinstance(args[k],str) or len(args[k])>2000 for k in ('reason','next_step')):
                raise ValueError('Invalid task feedback')
            return {'worker_feedback':args}
        return self.dispatch(name,args)

    def before_tool(self,agent,name,args):
        identity=self.running[agent]
        if name not in self.runtime.records[agent]['tools']: raise PermissionError('Tool not granted to this task worker')
        task=self.store.get(identity)
        if task['state']=='cancelled' or self.store.meta('stop_requested'):
            raise PermissionError('Task cancelled or supervisor stopping')
        self.store.event(identity,'tool_intent',{'agent_id':agent,'tool':name,'arguments':args,'attempt':task['attempt']})

    def after_tool(self,agent,name,args,result):
        identity=self.running[agent]
        if self.learning:
            try:
                from terminal.connection_memory import fallback
                feedback = fallback(self.learning, result)
                if feedback:
                    result['memory_feedback'] = feedback
            except Exception as exc:
                self.store.event(identity, 'learning_error', {'error': type(exc).__name__})
        receipt={'agent_id':agent,'tool':name,'arguments':args,'result':result}
        self.round_receipts[agent].append(receipt)
        self.store.event(identity,'tool_result',receipt)

    def finish(self,agent):
        identity = self.running[agent]
        receipts = list(self.round_receipts[agent])
        self._finish(agent)
        if self.learning:
            try:
                self.learning.record_task(self.store.get(identity), receipts)
            except Exception as exc:
                self.store.event(identity, 'learning_error', {'error': type(exc).__name__})

    def _finish(self,agent):
        identity=self.running.pop(agent);task=self.store.get(identity)
        result=self.runtime.result(agent);receipts=self.round_receipts.pop(agent)
        review=assess(task['spec'].get('checks',[]),receipts)
        feedback={'review':review,'phase':'replan' if result['role']=='TaskReplanner' else 'execute','worker_state':result['state'],'worker_result':result['result'],
                  'receipts':receipts[-8:],'next_step':'Reobserve result and revise approach against unmet checks'}
        self.store.event(identity,'review',feedback)
        # A late result cannot complete a cancelled task, or a crashed/timed-out attempt.
        if task['state']=='cancelled': return
        intents=[e for e in self.store.history(identity) if e['kind']=='tool_intent' and e['data'].get('agent_id')==agent]
        pending_effects=len(intents)>len(receipts)
        if review['verdict']=='pass' and not pending_effects:
            self.store.update(identity,'succeeded',feedback);return
        if result['state'] in ('timed_out','failed'):
            if not intents:
                feedback['next_step']='Worker failed before any tool invocation; retry with feedback after backoff'
                delay=min(self.policy['retry_max_s'],self.policy['retry_initial_s']*2**min(task['attempt']-1,16))
                self.store.update(identity,'retry_wait',feedback,delay=delay)
            else:
                feedback['next_step']='Inspect prior tool effects before retry; worker failed or timed out'
                self.store.update(identity,'waiting_observation',feedback)
            return
        reported=[r['result']['worker_feedback'] for r in receipts if isinstance(r['result'],dict) and 'worker_feedback' in r['result']]
        denied=any(isinstance(r['result'],dict) and r['result'].get('error')=='PermissionError' for r in receipts)
        if denied or (reported and reported[-1]['state']=='needs_input'):
            feedback['next_step']=reported[-1] if reported else 'Permission or configuration required'
            self.store.update(identity,'waiting_input',feedback);return
        if result['role']=='TaskReplanner':
            feedback['next_step']='Execute a revised approach using the replanner analysis; verify all original checks again'
            feedback['previous_unmet_checks']=task['feedback'].get('review')
            self.store.update(identity,'retry_wait',feedback,delay=self.policy['retry_initial_s']);return
        if not task['spec'].get('checks'):
            feedback['next_step']='Supply explicit success checks; worker prose cannot establish success'
            self.store.update(identity,'waiting_acceptance',feedback);return
        fingerprint=hashlib.sha256(json.dumps(review,sort_keys=True).encode()).hexdigest()
        previous=task['feedback']
        repeats=previous.get('unchanged_attempts',0)+1 if previous.get('fingerprint')==fingerprint else 1
        feedback.update(fingerprint=fingerprint,unchanged_attempts=repeats)
        if repeats>=self.policy['stalled_attempts']:
            feedback['next_step']='Same unmet checks repeated; delegate a new plan before more execution'
            feedback['needs_replan']=True
        delay=min(self.policy['retry_max_s'],self.policy['retry_initial_s']*2**min(task['attempt']-1,16))
        self.store.update(identity,'retry_wait',feedback,delay=delay)

    def poll(self,launch=True):
        for agent,identity in list(self.running.items()):
            if self.store.get(identity)['state']=='cancelled': self.runtime.cancel(agent)
        self.runtime.poll()
        for agent in list(self.running):
            if self.runtime.result(agent)['state']!='running':
                self.finish(agent)
                self.runtime.records.pop(agent,None)
        self.runtime.mail.clear();self.runtime.notifications.clear()
        if not launch: return
        self.fire_events()
        for task in reversed(self.store.list(limit=None)):
            if len(self.running)>=self.policy['max_workers']: break
            if task['state'] not in ('queued','retry_wait') or task['due']>time.time(): continue
            if task['spec'].get('provider') not in (None,self.provider):
                self.store.update(task['id'],'waiting_input',{'reason':'Provider/model differs from task binding; restart service with matching configuration'});continue
            role='TaskScheduled' if task['spec'].get('origin') in ('schedule','trigger') else 'TaskWorker'
            if any(c['tool'] not in self.runtime.definitions[role]['tools'] for c in task['spec'].get('checks',[])):
                self.store.update(task['id'],'waiting_input',{'reason':'Success check requires a tool not granted by task_runtime.json'});continue
            if task['feedback'].get('needs_replan'): role='TaskReplanner'
            prompt=json.dumps({'task_id':task['id'],'goal':task['spec']['goal'],'success_checks':task['spec'].get('checks',[]),
                               'previous_feedback':task['feedback']},ensure_ascii=False)
            # Keep latest feedback, not the full recursive history, in each attempt.
            if len(prompt)>16000: prompt=json.dumps({'task_id':task['id'],'goal':task['spec']['goal'],'success_checks':task['spec'].get('checks',[]),'previous_review':task['feedback'].get('review')},ensure_ascii=False)
            if len(prompt)>16000:
                self.store.update(task['id'],'waiting_input',{'reason':'Goal and acceptance exceed per-attempt context limit; split the task without dropping constraints'})
                continue
            if self.learning:
                try:
                    recalled = self.learning.context(task['spec']['goal'], nudge=False)
                    if recalled:
                        enriched = json.dumps({**json.loads(prompt), 'related_experience': recalled}, ensure_ascii=False)
                        if len(enriched) <= 16000:
                            prompt = enriched
                except Exception as exc:
                    self.store.event(task['id'], 'learning_error', {'error': type(exc).__name__})
            try:
                spawned=self.runtime.spawn(role,prompt,queue_if_busy=False)
            except ResourceBusy as exc:
                reason = 'Waiting for resources: ' + str(exc)
                if task['feedback'].get('resource_wait') != reason:
                    self.store.update(task['id'], task['state'], {**task['feedback'], 'resource_wait': reason})
                break
            agent=spawned['agent_id'];self.running[agent]=task['id'];self.round_receipts[agent]=[]
            self.store.update(task['id'],'running',{k:v for k,v in task['feedback'].items() if k != 'resource_wait'},agent_id=agent,attempt=task['attempt']+1)
            self.store.event(task['id'],'attempt',{'agent_id':agent,'pid':self.runtime.records[agent]['process'].pid,'attempt':task['attempt']+1})

    def fire_events(self):
        # Atomic event consumption and task creation: crash cannot lose or double-fire it.
        with self.store.db() as db:
            for entry in self.policy['schedules']:
                if not entry['enabled']: continue
                db.execute('INSERT OR IGNORE INTO schedules VALUES(?,?)',(entry['name'],time.time()+entry['every_s']))
                due=db.execute('SELECT due FROM schedules WHERE name=?',(entry['name'],)).fetchone()[0]
                if due<=time.time():
                    self.enqueue_configured(db,entry,'schedule')
                    db.execute('UPDATE schedules SET due=? WHERE name=?',(time.time()+entry['every_s'],entry['name']))
            for row in db.execute('SELECT * FROM triggers WHERE consumed=0 ORDER BY id LIMIT 100').fetchall():
                for entry in self.policy['triggers']:
                    if entry['enabled'] and entry['event']==row['name']:
                        self.enqueue_configured(db,entry,'trigger')
                db.execute('UPDATE triggers SET consumed=1 WHERE id=?',(row['id'],))

    def enqueue_configured(self,db,entry,origin):
        import uuid
        # Coalesce: one outstanding task per configured rule, no overlap/backlog storm.
        key=origin+':'+entry['name']
        active=db.execute("SELECT tasks.id,tasks.state FROM tasks JOIN events ON events.task_id=tasks.id WHERE events.kind='triggered' AND json_extract(events.data,'$.rule')=? AND tasks.state NOT IN ('succeeded','cancelled')",(key,)).fetchone()
        if active:
            if origin=='trigger' and active['state'] in ('waiting_input','retry_wait'):
                db.execute("UPDATE tasks SET state='queued',due=?,updated=? WHERE id=?",(time.time(),time.time(),active['id']))
                db.execute('INSERT INTO events(task_id,kind,data,created) VALUES(?,?,?,?)',(active['id'],'event_wakeup',json.dumps({'rule':key}),time.time()))
            return
        identity=uuid.uuid4().hex[:12];spec={**entry['task'],'origin':origin,'provider':self.provider}
        db.execute('INSERT INTO tasks(id,spec,state,due,updated) VALUES(?,?,?,?,?)',(identity,json.dumps(spec,ensure_ascii=False),'queued',time.time(),time.time()))
        db.execute('INSERT INTO events(task_id,kind,data,created) VALUES(?,?,?,?)',(identity,'triggered',json.dumps({'rule':key}),time.time()))

    def close(self):
        self.runtime.close()
        for identity in self.running.values():
            self.store.update(identity,'waiting_observation',{'reason':'Supervisor stopped; inspect effects before resuming'})
