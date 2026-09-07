"""Local conversation checkpoint and transcript, separate from credentials."""
import json
import os
from pathlib import Path
import sqlite3
import uuid
from terminal.titles import conversation_title


class SessionStore:
    def __init__(self, path, exclusive=False):
        path = Path(path)
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self.path = path
        self.exclusive = exclusive
        self._session_lock = None
        self._locked_session = None
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS checkpoint (id INTEGER PRIMARY KEY, data TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS transcript (id INTEGER PRIMARY KEY, kind TEXT, text TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if 'session_id' not in {row[1] for row in self.db.execute('PRAGMA table_info(transcript)')}:
                self.db.execute('ALTER TABLE transcript ADD COLUMN session_id TEXT')
        self.db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, provider TEXT NOT NULL, data TEXT NOT NULL, updated TEXT DEFAULT CURRENT_TIMESTAMP)')
        self.db.execute('CREATE TABLE IF NOT EXISTS session_names (id TEXT PRIMARY KEY, name TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS task_sessions (task_id TEXT PRIMARY KEY, session_id TEXT UNIQUE NOT NULL, parent_id TEXT NOT NULL)')
        # Preserve legacy checkpoint-only history before a fresh UI session saves.
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT data FROM checkpoint WHERE id=1').fetchone()
            if row:
                state = json.loads(row[0])
                if state.get('provider'):
                    if not state.get('session_id'):
                        state['session_id'] = uuid.uuid4().hex[:12]
                        self.db.execute('UPDATE checkpoint SET data=? WHERE id=1', (json.dumps(state, ensure_ascii=False),))
                    self.db.execute('INSERT OR IGNORE INTO sessions(id,provider,data) VALUES(?,?,?)',
                                    (state['session_id'], json.dumps(state['provider']), json.dumps(state, ensure_ascii=False)))
        self.session_id = None
        self.provider = None
        self.db.commit()

    def _claim(self, identity):
        if not self.exclusive or identity == self._locked_session:
            return
        import hashlib
        from terminal.platform_support import lock_terminal
        directory = self.path.parent / 'session-locks'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (hashlib.sha256(identity.encode()).hexdigest() + '.lock')
        stream = path.open('a+b')
        try:
            lock_terminal(stream)
        except BlockingIOError:
            stream.close()
            raise ValueError('This conversation is open in another terminal; choose another conversation or close it there') from None
        except BaseException:
            stream.close()
            raise
        # Acquire the destination before releasing the current conversation.
        previous = self._session_lock
        self._session_lock, self._locked_session = stream, identity
        if previous is not None:
            previous.close()

    @staticmethod
    def identity(config):
        return [config['base_url'].rstrip('/'), config['model'], config.get('protocol', 'openai')]

    def load(self, config):
        row = self.db.execute('SELECT data FROM checkpoint WHERE id=1').fetchone()
        if not row:
            return {}
        state = json.loads(row[0])
        # A provider switch must not silently forward previous provider context.
        if state.get('provider') != self.identity(config): return {}
        identity = state.get('session_id') or uuid.uuid4().hex[:12]
        try:
            self._claim(identity)
        except ValueError:
            self.new_session()
            return {}
        # Re-read after acquiring ownership: the previous writer may have saved
        # a final checkpoint while this terminal was trying to claim it.
        latest = self.db.execute('SELECT data FROM sessions WHERE id=?', (identity,)).fetchone()
        if latest:
            state = json.loads(latest[0])
        self.provider = self.identity(config)
        self.session_id = identity
        state['session_id'] = self.session_id
        return state

    def save(self, config, history, queue, draft='', attachments=(), summaries=(), task=None, composer=None, token_usage=None, context_report=None, history_message_limit=32):
        if self.provider is not None and self.provider != self.identity(config):
            self.new_session()
        self.provider = self.identity(config)
        self.session_id = self.session_id or uuid.uuid4().hex[:12]
        self._claim(self.session_id)
        from terminal.session_task import SessionTask
        task = SessionTask(task, identity=self.session_id, history=history).snapshot()
        data = {'task': task, 'session_id':self.session_id, 'summaries':list(summaries), 'provider': self.identity(config), 'history': history, 'queue': list(queue),
                'draft': draft, 'attachments': list(attachments), 'composer': composer, 'token_usage': dict(token_usage or {}),
                'context_report': dict(context_report or {}), 'history_message_limit': history_message_limit}
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO checkpoint VALUES (1, ?)',
                            (json.dumps(data, ensure_ascii=False),))
            self.db.execute('INSERT INTO sessions(id,provider,data) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=CURRENT_TIMESTAMP',
                            (self.session_id,json.dumps(self.identity(config)),json.dumps(data,ensure_ascii=False)))

    def list_sessions(self, config, query='', limit=30):
        rows=self.db.execute('SELECT id,data,updated,rowid FROM sessions WHERE provider=? ORDER BY updated DESC,rowid DESC',
                             (json.dumps(self.identity(config)),)).fetchall()
        result=[]
        for identity,raw,updated,number in rows:
            data=json.loads(raw)
            users=[m.get('content','') for m in data.get('history',[]) if m.get('role')=='user']
            title=conversation_title(data.get('history', []), data.get('task'))
            named = self.db.execute('SELECT name FROM session_names WHERE id=?', (identity,)).fetchone()
            title = named[0] if named else title
            result.append({'id':identity,'title':title[:100],'number':number,'turns':len(users),'updated':updated,
                           'task_state': data.get('task', {}).get('state', 'idle'), 'last_summary':data.get('summaries',[])[-1:]})
        from collections import Counter
        totals = Counter(row['title'] for row in result)
        for row in result:
            row['label'] = row['title'] + (' [' + str(row['number']) + ']' if totals[row['title']] > 1 else '')
        matching = {identity for identity, raw, _, _ in rows if query.casefold() in (identity + ' ' + raw).casefold()}
        result = [row for row in result if row['id'] in matching or query.casefold() in row['label'].casefold()]
        return result if limit is None else result[:limit]

    def resolve(self, config, reference):
        rows = self.list_sessions(config, limit=None)
        for row in rows:
            if reference == row['id']:
                return row['id']  # Existing command links remain valid.
        matches = [row for row in rows if reference == row['label']]
        if len(matches) == 1:
            return matches[0]['id']
        if len(matches) > 1:
            raise ValueError('Conversation titles are ambiguous; rename one before selecting it')
        matches = [row for row in rows if reference == row['title']]
        if len(matches) == 1:
            return matches[0]['id']
        if matches:
            raise ValueError('Several conversations share that title; choose a numbered title from /resume')
        raise ValueError('Conversation not found; choose a title from /resume')

    def title(self, config):
        return next((row['label'] for row in self.list_sessions(config, limit=None) if row['id'] == self.session_id), 'New conversation')

    def rename(self, config, name):
        name = name.strip()
        if not name or len(name) > 100 or not all(c.isprintable() for c in name):
            raise ValueError('Session name must be 1..100 printable characters')
        self.read_session(config, self.session_id)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO session_names VALUES (?,?)', (self.session_id, name))
        return name

    def export(self, config, identity=None):
        identity = self.resolve(config, identity or self.session_id)
        data = self.read_session(config, identity)
        title = next(row['title'] for row in self.list_sessions(config, limit=None) if row['id'] == identity)
        lines = ['# ' + title, '']
        for message in data.get('history', []):
            content = message.get('content', '')
            if not isinstance(content, str):
                content = '\n'.join(part.get('text', '[media omitted]') for part in content if isinstance(part, dict))
            lines += ['## ' + str(message.get('role', 'message')), '', content, '']
            if message.get('tool_calls'):
                lines += ['```json', json.dumps(message['tool_calls'], ensure_ascii=False, indent=2), '```', '']
        if data.get('task'):
            task = data['task']
            lines += ['## Task', '', 'State: ' + task['state'], '', task['goal'], '', *['- ' + step for step in task['plan']], '', task['progress'], '', task['next_step'], '']
        from terminal.turn_summary import display
        if data.get('summaries'):
            lines += ['## Turn summaries', ''] + [display(summary) for summary in data['summaries']]
        directory = self.path.parent / 'exports'
        directory.mkdir(mode=0o700, exist_ok=True)
        import re
        stem = re.sub(r'[\\/:*?"<>|]', '_', title).strip(' .')[:60] or 'conversation'
        path = directory / (stem + '-' + uuid.uuid4().hex[:8] + '.md')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            output.write('\n'.join(lines))
        return path.resolve()

    def read_session(self, config, identity):
        identity = self.resolve(config, identity)
        row=self.db.execute('SELECT data FROM sessions WHERE id=? AND provider=?',
                            (identity,json.dumps(self.identity(config)))).fetchone()
        if not row: raise ValueError('Session not found for the current provider/model')
        data = json.loads(row[0])
        from terminal.session_task import SessionTask
        data['task'] = SessionTask(data.get('task'), identity=identity, history=data.get('history', [])).snapshot()
        return data

    def resume(self, config, identity):
        data=self.read_session(config,identity)
        self._claim(data['session_id'])
        data = self.read_session(config, data['session_id'])
        self.session_id=data['session_id']
        self.provider=self.identity(config)
        return data

    def new_session(self):
        identity = uuid.uuid4().hex[:12]
        self._claim(identity)
        self.session_id = identity

    def task_link(self):
        row = self.db.execute('SELECT task_id,parent_id FROM task_sessions WHERE session_id=?', (self.session_id,)).fetchone()
        return {'task_id': row[0], 'parent_id': row[1]} if row else None

    def ensure_task_session(self, config, task):
        """Create a resumable conversation without switching the caller or starting work."""
        provider = self.identity(config)
        binding = task['spec'].get('provider')
        if binding and binding != provider:
            raise ValueError('Task provider differs from current profile')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT session_id FROM task_sessions WHERE task_id=?', (task['id'],)).fetchone()
            if row:
                return row[0]
            identity = uuid.uuid4().hex[:12]
            from terminal.session_task import SessionTask
            work = SessionTask(identity=identity)
            work.update({'goal':task['spec']['goal'], 'state':'active'})
            data = {'session_id':identity, 'provider':provider, 'history':[], 'queue':[],
                    'task':work.snapshot(), 'token_usage':{}, 'summaries':[]}
            self.db.execute('INSERT INTO sessions(id,provider,data) VALUES(?,?,?)',
                            (identity,json.dumps(provider),json.dumps(data,ensure_ascii=False)))
            self.db.execute('INSERT INTO task_sessions VALUES(?,?,?)',
                            (task['id'],identity,task.get('session_id') or ''))
            return identity

    def record(self, kind, text):
        with self.db:
            cursor = self.db.execute('INSERT INTO transcript(kind,text,session_id) VALUES (?,?,?)', (kind, text, self.session_id))
            return cursor.lastrowid

    def tool_details(self, event_id=None):
        if event_id is None:
            row = self.db.execute("SELECT id,text,session_id FROM transcript WHERE kind='result' AND session_id IS ? ORDER BY id DESC LIMIT 1", (self.session_id,)).fetchone()
        else:
            row = self.db.execute("SELECT id,text,session_id FROM transcript WHERE kind='result' AND id=?", (event_id,)).fetchone()
        if row is None:
            raise ValueError('No tool result found; use /details [result ID]')
        previous = self.db.execute("SELECT COALESCE(MAX(id),0) FROM transcript WHERE kind='result' AND id<? AND session_id IS ?", (row[0], row[2])).fetchone()[0]
        call = self.db.execute("SELECT text FROM transcript WHERE kind='tool' AND id>? AND id<? AND session_id IS ? ORDER BY id DESC LIMIT 1", (previous, row[0], row[2])).fetchone()
        try:
            result = json.dumps(json.loads(row[1]), ensure_ascii=False, indent=2)
        except ValueError:
            result = row[1]
        metadata=''
        for group in self.db.execute("SELECT text FROM transcript WHERE kind='tool_group' AND id>? AND session_id IS ? ORDER BY id LIMIT 100",(row[0], row[2])):
            try:
                call_row=next((c for c in json.loads(group[0]).get('calls',[]) if c.get('event_id')==row[0]),None)
            except (ValueError,TypeError): continue
            if call_row:
                metadata=call_row['time']+' · '+str(round(call_row['elapsed'],3))+'s · ~'+str(call_row['tokens'])+' local tokens (estimate, not billing)\n'
                break
        return metadata + 'Tool result #' + str(row[0]) + '\n' + (call[0] + '\n' if call else '') + result

    def close(self):
        try:
            self.db.close()
        finally:
            if self._session_lock is not None:
                self._session_lock.close()
                self._session_lock = None
                self._locked_session = None
