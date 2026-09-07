"""Persistent task and feedback ledger. No models, device code or shell evaluation."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

TERMINAL={'succeeded','cancelled'}


def validate_spec(spec):
    if not isinstance(spec,dict) or set(spec)-{'goal','checks','origin','provider'}:
        raise ValueError('Task fields: goal, checks, origin, provider')
    if not isinstance(spec.get('goal'),str) or not 1<=len(spec['goal'])<=16000:
        raise ValueError('Task requires a goal of 1..16000 characters')
    checks=spec.get('checks',[])
    if not isinstance(checks,list) or len(checks)>20: raise ValueError('At most 20 success checks')
    for check in checks:
        if not isinstance(check,dict) or not {'tool','path','equals'}<=set(check) or set(check)-{'tool','path','equals','arguments'} or not isinstance(check['tool'],str) or not isinstance(check['path'],str) or not check['path'] or len(check['path'])>200:
            raise ValueError('Each success check requires tool, dotted path, equals')
        if 'arguments' in check and not isinstance(check['arguments'],dict): raise ValueError('Check arguments must be an object')
        json.dumps(check,allow_nan=False)
    if spec.get('origin','manual') not in ('manual','handoff','schedule','trigger'):
        raise ValueError('Invalid task origin')
    return spec


def assess(checks, receipts):
    """Only parent-observed tool receipts satisfy checks, never worker prose."""
    if not checks: return {'verdict':'inconclusive','reason':'No explicit success checks; acceptance criteria required','checks':[]}
    findings=[]
    for check in checks:
        matching=[r for r in receipts if r['tool']==check['tool'] and ('arguments' not in check or r.get('arguments')==check['arguments'])]
        value=matching[-1]['result'] if matching else None
        failed=isinstance(value,dict) and bool(value.get('error'))
        for key in check['path'].split('.'):
            value=value.get(key) if isinstance(value,dict) else None
        passed=bool(matching) and not failed and type(value)==type(check['equals']) and value==check['equals']
        findings.append({**check,'observed':value,'passed':passed})
    return {'verdict':'pass' if all(c['passed'] for c in findings) else 'fail',
            'reason':'Configured success conditions verified' if all(c['passed'] for c in findings) else 'Goal checks not yet satisfied', 'checks':findings}


class TaskStore:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,spec TEXT,state TEXT,attempt INTEGER DEFAULT 0,due REAL,agent_id TEXT,feedback TEXT DEFAULT '{}',updated REAL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,task_id TEXT,kind TEXT,data TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS runtime(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS triggers(id INTEGER PRIMARY KEY,name TEXT,payload TEXT,consumed INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS schedules(name TEXT PRIMARY KEY,due REAL);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def event(self,task,kind,data):
        with self.db() as db: db.execute('INSERT INTO events(task_id,kind,data,created) VALUES(?,?,?,?)',(task,kind,json.dumps(data,ensure_ascii=False),time.time()))

    def submit(self,spec):
        validate_spec(spec);identity=uuid.uuid4().hex[:12]
        with self.db() as db:
            db.execute('INSERT INTO tasks(id,spec,state,due,updated) VALUES(?,?,?,?,?)',(identity,json.dumps(spec,ensure_ascii=False),'queued',time.time(),time.time()))
            db.execute('INSERT INTO events(task_id,kind,data,created) VALUES(?,?,?,?)',(identity,'submitted',json.dumps(spec,ensure_ascii=False),time.time()))
        return self.get(identity)

    def get(self,identity):
        with self.db() as db: row=db.execute('SELECT * FROM tasks WHERE id=?',(identity,)).fetchone()
        if not row: raise ValueError('Unknown task ID')
        result=dict(row);result['spec']=json.loads(result['spec']);result['feedback']=json.loads(result['feedback']);return result

    def list(self,limit=100):
        with self.db() as db: ids=[r[0] for r in db.execute("SELECT id FROM tasks ORDER BY updated DESC"+(" LIMIT ?" if limit is not None else ""), (limit,) if limit is not None else ())]
        return [self.get(i) for i in ids]

    def update(self,identity,state,feedback=None,delay=0,agent_id=None,attempt=None):
        with self.db() as db:
            db.execute('UPDATE tasks SET state=?,feedback=COALESCE(?,feedback),due=?,agent_id=?,attempt=COALESCE(?,attempt),updated=? WHERE id=? AND state NOT IN (\'succeeded\',\'cancelled\')',
                       (state,json.dumps(feedback,ensure_ascii=False) if feedback is not None else None,time.time()+delay,agent_id,attempt,time.time(),identity))
        self.event(identity,'state',{'state':self.get(identity)['state'],'feedback':feedback})

    def cancel(self,identity):
        self.get(identity);self.update(identity,'cancelled',{'reason':'User cancellation; executed effects are not rolled back'})
        return self.get(identity)

    def resume(self,identity,checks=None,message=None):
        task=self.get(identity)
        if task['state'] in TERMINAL: raise ValueError('Completed/cancelled tasks cannot be resumed')
        if task['state']=='running': raise ValueError('Task already running')
        if checks is not None:
            spec={**task['spec'],'checks':checks};validate_spec(spec)
            with self.db() as db: db.execute('UPDATE tasks SET spec=? WHERE id=?',(json.dumps(spec,ensure_ascii=False),identity))
        feedback=None
        if message is not None:
            if not isinstance(message,str) or not 1<=len(message)<=8000: raise ValueError('Resume message must contain 1..8000 characters')
            feedback={**task['feedback'],'new_input':message}
        self.update(identity,'queued',feedback);return self.get(identity)

    def meta(self,key,value=None):
        with self.db() as db:
            if value is not None: db.execute('INSERT OR REPLACE INTO runtime VALUES(?,?)',(key,json.dumps(value)))
            row=db.execute('SELECT value FROM runtime WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None

    def signal(self,name,payload):
        if not isinstance(name,str) or not name or len(name)>100 or len(json.dumps(payload))>8000: raise ValueError('Invalid trigger signal')
        with self.db() as db: row=db.execute('INSERT INTO triggers(name,payload) VALUES(?,?)',(name,json.dumps(payload)));return row.lastrowid

    def receipts(self,identity):
        with self.db() as db: rows=db.execute("SELECT data FROM events WHERE task_id=? AND kind='tool_result' ORDER BY id",(identity,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def history(self,identity):
        self.get(identity)
        with self.db() as db: rows=db.execute('SELECT kind,data,created FROM events WHERE task_id=? ORDER BY id DESC LIMIT 100',(identity,)).fetchall()
        return [{'kind':r['kind'],'data':json.loads(r['data']),'created':r['created']} for r in reversed(rows)]

    def notifications(self,after=0):
        with self.db() as db:
            rows=db.execute("SELECT id,task_id,data FROM events WHERE id>? AND kind='state' ORDER BY id LIMIT 50",(after,)).fetchall()
        return [{'id':r['id'],'task_id':r['task_id'],**json.loads(r['data'])} for r in rows]
