"""Foreground work belongs to a conversation; task and session IDs are independent; receipts are observed by the host."""
import json
import threading
import uuid
from core.tasks import assess, validate_spec
from terminal.files import schema

TOOLS = [schema('session_task_read', 'Read this session task, plan, acceptance checks and observed tool receipts. No background execution.', {}, []),
         schema('session_task_update', 'Update this session task plan, checks, progress and next step. Completion requires checks against host-observed receipts; prose is not evidence. Goal changes must follow user direction. New messages continue this work; /new opens a new conversation with a fresh work record. Session and task IDs are distinct.',
                {'goal': {'type': 'string'}, 'plan': {'type': 'array', 'items': {'type': 'string'}},
                 'checks': {'type': 'array', 'items': {'type': 'object'}},
                 'progress': {'type': 'string'}, 'next_step': {'type': 'string'},
                 'state': {'type': 'string', 'enum': ['active', 'waiting_input', 'needs_review', 'complete']}}, [])]
NAMES = {t['function']['name'] for t in TOOLS}


class SessionTask:
    def __init__(self, data=None, identity=None, history=()):
        self.lock = threading.RLock()
        self.data = json.loads(json.dumps(data)) if data else {
            'id': uuid.uuid4().hex[:12], 'goal': '', 'plan': [], 'checks': [],
            'state': 'idle', 'progress': '', 'next_step': '', 'turn': 0, 'receipts': [], 'feedback': []}
        self.data.setdefault('session_id', identity)
        if identity:
            self.data['session_id'] = identity
            if self.data['id'] == identity:
                self.data['id'] = uuid.uuid5(uuid.NAMESPACE_URL, 'loop-foreground-task:' + identity).hex[:12]  # Stable legacy migration.
        if not self.data['goal']:
            self.data['goal'] = next((m['content'][:16000] for m in history if m.get('role') == 'user' and isinstance(m.get('content'), str)), '')
        if self.data['state'] == 'running':
            self.data['state'] = 'needs_review'
            self.data['next_step'] = 'Interrupted turn: inspect recorded effects before retrying; no automatic execution.'

    def snapshot(self, compact=False):
        with self.lock:
            data = json.loads(json.dumps(self.data))
        if compact:
            data['receipts'] = data['receipts'][-6:]
            data['feedback'] = data['feedback'][-3:]
            data.pop('last_turn', None)
            for receipt in data['receipts']:
                if isinstance(receipt['result'], dict):
                    receipt['result'] = {k: v for k, v in receipt['result'].items() if k not in ('stdout', 'stderr', 'content', 'diff', 'source')}
            while data['receipts'] and len(json.dumps(data)) > 12000:
                data['receipts'].pop(0)
        return data

    def begin(self, text):
        with self.lock:
            if not self.data['goal']:
                self.data['goal'] = text[:16000]
            self.data['latest_request'] = text[:16000]
            self.data['turn'] += 1
            self.data['state'] = 'running'

    def receipt(self, name, args, result):
        if name in NAMES:
            return
        with self.lock:
            # Bound data stored in model context; full outputs remain in tool details/reports.
            result = json.loads(json.dumps(result, ensure_ascii=False))
            if isinstance(result, dict) and len(json.dumps(result)) > 12000:
                result = {k: v for k, v in result.items() if k not in ('stdout', 'stderr', 'content', 'diff', 'data')}
                result['receipt_truncated'] = True
            if len(json.dumps(result)) > 12000:
                result = {'receipt_truncated': True, 'execution_verified': False}
            args = json.loads(json.dumps(args))
            if len(json.dumps(args)) > 4000:
                args = {k: v for k, v in args.items() if k not in ('content', 'source', 'old_text', 'new_text')}
            self.data['receipts'].append({'tool': name, 'arguments': args, 'result': result, 'turn': self.data['turn']})
            self.data['receipts'] = self.data['receipts'][-40:]
            failed = isinstance(result, dict) and (result.get('error') or result.get('returncode') not in (None, 0) or result.get('stop_reason'))
            if failed:
                self.data['feedback'].append({'tool': name, 'error': result.get('error') or result.get('stop_reason') or 'nonzero_exit',
                                             'message': str(result.get('message') or result.get('stderr') or '')[-1500:], 'turn': self.data['turn']})
                self.data['feedback'] = self.data['feedback'][-12:]
            # Any later action invalidates an earlier completion assessment.
            if self.data['state'] == 'complete':
                self.data['state'] = 'needs_review'

    def update(self, args):
        allowed = {'goal', 'plan', 'checks', 'state', 'progress', 'next_step'}
        if not isinstance(args, dict) or set(args) - allowed:
            raise ValueError('Invalid session task fields')
        with self.lock:
            for key in ('goal', 'progress', 'next_step'):
                if key in args and (not isinstance(args[key], str) or len(args[key]) > 16000):
                    raise ValueError('Task text fields must be strings of at most 16000 characters')
            if 'plan' in args and (not isinstance(args['plan'], list) or len(args['plan']) > 20 or any(not isinstance(s, str) or len(s) > 1000 for s in args['plan'])):
                raise ValueError('Plan must contain at most 20 short steps')
            if 'state' in args and args['state'] not in ('active', 'waiting_input', 'needs_review', 'complete'):
                raise ValueError('Invalid session task state')
            candidate = {**self.data, **args}
            validate_spec({'goal': candidate['goal'] or 'Session task', 'checks': candidate['checks']})
            # Reads/configuration declarations cannot be selected as automatic acceptance evidence.
            if any(c['tool'] in NAMES for c in candidate['checks']):
                raise ValueError('Task metadata cannot prove its own completion')
            current = [r for r in self.data['receipts'] if r['turn'] == self.data['turn']]
            review = assess(candidate['checks'], current)
            if candidate['state'] == 'complete' and review['verdict'] != 'pass':
                raise ValueError('Completion not verified: ' + review['reason'])
            self.data.update(args)
            self.data['review'] = review
            return self.snapshot()

    def finish(self, summary, events):
        with self.lock:
            if summary.get('error'):
                self.data['state'] = 'needs_review'
                self.data['next_step'] = summary['error']
            elif self.data['state'] == 'running':
                self.data['state'] = 'needs_review' if self.data['receipts'] else 'waiting_input'
            self.data['last_turn'] = summary
        # No background-task handoff.
        return None


def call(app, name, args):
    app.permissions.check(name, args)
    if name == 'session_task_read':
        if args:
            raise ValueError('session_task_read takes no arguments')
        return app.session_task.snapshot()
    return app.session_task.update(args)
