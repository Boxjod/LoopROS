"""Persistent task and feedback ledger. No models, device code or shell evaluation."""
from contextlib import contextmanager
import hashlib
import json
import os
import tempfile
from pathlib import Path
import sqlite3
import time
import uuid

TERMINAL={'succeeded','cancelled'}


def validate_spec(spec):
    if not isinstance(spec,dict) or set(spec)-{'goal','checks','origin','provider','session_id'}:
        raise ValueError('Task fields: goal, checks, origin, provider')
    if not isinstance(spec.get('goal'),str) or not 1<=len(spec['goal'])<=16000:
        raise ValueError('Task requires a goal of 1..16000 characters')
    if 'session_id' in spec and (not isinstance(spec['session_id'], str) or not 1 <= len(spec['session_id']) <= 64):
        raise ValueError('Invalid session_id')
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
            db.execute('BEGIN IMMEDIATE')
            if 'session_id' not in {r[1] for r in db.execute('PRAGMA table_info(tasks)')}:
                db.execute('ALTER TABLE tasks ADD COLUMN session_id TEXT')
            db.execute('CREATE INDEX IF NOT EXISTS tasks_session ON tasks(session_id, updated)')
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
            db.execute('INSERT INTO tasks(id,spec,state,due,updated,session_id) VALUES(?,?,?,?,?,?)',(identity,json.dumps(spec,ensure_ascii=False),'queued',time.time(),time.time(),spec.get('session_id')))
            db.execute('INSERT INTO events(task_id,kind,data,created) VALUES(?,?,?,?)',(identity,'submitted',json.dumps(spec,ensure_ascii=False),time.time()))
        return self.get(identity)

    def define_checks(self, identity, checks):
        validate_spec({'goal':'Acceptance proposal','checks':checks})
        if not checks:
            raise ValueError('Acceptance checks cannot be empty')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT spec,state FROM tasks WHERE id=?',(identity,)).fetchone()
            if not row:
                raise ValueError('Unknown task ID')
            spec = json.loads(row['spec'])
            if spec.get('checks') or row['state'] in TERMINAL:
                return False
            spec['checks'] = checks
            db.execute('UPDATE tasks SET spec=? WHERE id=?',(json.dumps(spec,ensure_ascii=False),identity))
            db.execute('INSERT INTO events(task_id,kind,data,created) VALUES(?,?,?,?)',
                       (identity,'checks_defined',json.dumps({'checks':checks},ensure_ascii=False),time.time()))
        return True

    def get(self,identity):
        with self.db() as db: row=db.execute('SELECT * FROM tasks WHERE id=?',(identity,)).fetchone()
        if not row: raise ValueError('Unknown task ID')
        result=dict(row);result['spec']=json.loads(result['spec']);result['feedback']=json.loads(result['feedback'])
        report = self.path.parent/'task-reports'/f'{identity}.md'
        if report.is_file(): result['report_path']=str(report)
        return result

    def list(self,limit=100,session_id=None):
        query = 'SELECT id FROM tasks'
        args = []
        if session_id is not None:
            query += ' WHERE session_id=?'
            args.append(session_id)
        query += ' ORDER BY updated DESC'
        if limit is not None:
            query += ' LIMIT ?'
            args.append(limit)
        with self.db() as db: ids=[r[0] for r in db.execute(query, args)]
        return [self.get(i) for i in ids]

    def unfinished_count(self, session_id):
        with self.db() as db:
            return db.execute("SELECT COUNT(*) FROM tasks WHERE session_id=? AND state NOT IN ('succeeded','cancelled')",
                              (session_id,)).fetchone()[0]

    def update(self,identity,state,feedback=None,delay=0,agent_id=None,attempt=None):
        with self.db() as db:
            db.execute('UPDATE tasks SET state=?,feedback=COALESCE(?,feedback),due=?,agent_id=?,attempt=COALESCE(?,attempt),updated=? WHERE id=? AND state NOT IN (\'succeeded\',\'cancelled\')',
                       (state,json.dumps(feedback,ensure_ascii=False) if feedback is not None else None,time.time()+delay,agent_id,attempt,time.time(),identity))
        current = self.get(identity)
        report = None
        if current['state'] in TERMINAL or current['state'].startswith('waiting_'):
            try:
                report = self.write_report(current)
            except OSError as exc:
                self.event(identity,'report_error',{'error':type(exc).__name__})
        self.event(identity,'state',{'state':current['state'],'feedback':feedback, 'report_path':report})

    def write_report(self, task):
        """Deterministic receipt summary; never copy arbitrary prompts or tool output."""
        directory = self.path.parent/'task-reports'
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = directory/f"{task['id']}.md"
        feedback = task['feedback']
        review = feedback.get('review', {})
        lines = [f"# Task {task['id']}", '', f"State: {task['state']}",
                 f"Attempts: {task['attempt']}", f"Verdict: {review.get('verdict', 'inconclusive')}", '',
                 'Acceptance evidence:', '']
        for index, check in enumerate(review.get('checks', []), 1):
            lines.append(f"- Check {index}: {'PASS' if check.get('passed') else 'NOT VERIFIED'}")
        if not review.get('checks'): lines.append('- No verified acceptance receipts.')
        reasons = {
            'stalled': 'Replanning did not improve acceptance evidence. Automatic retries paused.',
            'attempt_budget': 'Automatic attempt budget exhausted. Automatic retries paused.',
        }
        lines += ['', reasons.get(feedback.get('stop_reason'),
                  'All configured checks passed.' if task['state']=='succeeded' else
                  'Task is not complete. Inspect recorded feedback and unmet checks.'), '',
                  f"Evidence: task ledger {self.path.name}, task ID {task['id']}.",
                  'Use /tasks status with this ID for the goal, feedback and original receipts.',
                  'Waiting tasks resume only after explicit resume; this report makes no model calls.', '']
        fd, temporary = tempfile.mkstemp(prefix='.report-', dir=directory)
        try:
            with os.fdopen(fd, 'w') as stream: stream.write('\n'.join(lines))
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        return str(target)

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
        feedback={k:v for k,v in task['feedback'].items() if k not in ('needs_replan','replans','fingerprint','unchanged_attempts','stop_reason')}
        feedback['budget_start'] = task['attempt']
        if message is not None:
            if not isinstance(message,str) or not 1<=len(message)<=8000: raise ValueError('Resume message must contain 1..8000 characters')
            feedback['new_input']=message
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

    def notifications(self,after=0,session_id=None):
        with self.db() as db:
            query = "SELECT e.id,e.task_id,e.data FROM events e JOIN tasks t ON t.id=e.task_id WHERE e.id>? AND e.kind='state'"
            args = [after]
            if session_id is not None:
                query += ' AND t.session_id=?'
                args.append(session_id)
            rows=db.execute(query + ' ORDER BY e.id LIMIT 50', args).fetchall()
        return [{'id':r['id'],'task_id':r['task_id'],**json.loads(r['data'])} for r in rows]
