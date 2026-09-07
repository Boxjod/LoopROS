"""Indexed task summaries and durable details over the local experience database."""
import hashlib
import json
import time
from core.experience import terms


class MemoryLayers:
    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS memory_items(
                    scope TEXT, id TEXT, kind TEXT, text TEXT, payload TEXT, sources TEXT,
                    updated REAL, PRIMARY KEY(scope,id));
                CREATE TABLE IF NOT EXISTS memory_terms(
                    scope TEXT, id TEXT, term TEXT, PRIMARY KEY(scope,id,term));
                CREATE INDEX IF NOT EXISTS memory_lookup ON memory_terms(scope,term);
                CREATE TABLE IF NOT EXISTS procedure_runs(
                    scope TEXT, recipe TEXT, task_id TEXT, source TEXT, verified INTEGER, updated REAL,
                    PRIMARY KEY(scope,recipe,task_id));
                CREATE TABLE IF NOT EXISTS memory_migrations(scope TEXT, version TEXT, PRIMARY KEY(scope,version));
                CREATE TABLE IF NOT EXISTS successful_connections(
                    scope TEXT, device TEXT, transport TEXT, config TEXT, source TEXT, succeeded_at REAL,
                    PRIMARY KEY(scope,device,transport));
            ''')

    def save(self, scope, kind, key, text, payload, source, updated=None):
        identity = 'm-' + hashlib.sha256((kind + ':' + key).encode()).hexdigest()[:20]
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT sources,updated FROM memory_items WHERE scope=? AND id=?', (scope, identity)).fetchone()
            if previous and updated is not None and previous['updated'] > updated:
                return identity
            sources = list(dict.fromkeys((json.loads(previous[0]) if previous else []) + [source]))[-3:]
            db.execute('INSERT OR REPLACE INTO memory_items VALUES(?,?,?,?,?,?,?)',
                       (scope, identity, kind, text[:700], json.dumps(payload, ensure_ascii=False), json.dumps(sources), updated or time.time()))
            db.execute('DELETE FROM memory_terms WHERE scope=? AND id=?', (scope, identity))
            indexed = terms(text + ' ' + ' '.join(payload.get('tags', [])))
            db.executemany('INSERT INTO memory_terms VALUES(?,?,?)', [(scope, identity, t) for t in sorted(indexed)[:120]])
        return identity

    def read(self, scope, identity):
        with self.store.db() as db:
            row = db.execute('SELECT * FROM memory_items WHERE scope=? AND id=?', (scope, identity)).fetchone()
        if not row:
            raise ValueError('Memory not found in this scope')
        return {k: json.loads(row[k]) if k in ('payload', 'sources') else row[k] for k in row.keys() if k != 'scope'}

    def search(self, scope, query, limit=6):
        tokens = sorted(terms(query))[:40]
        if not tokens:
            return []
        with self.store.db() as db:
            rows = db.execute('''SELECT m.id, COUNT(*) AS score FROM memory_terms t
                JOIN memory_items m ON m.scope=t.scope AND m.id=t.id
                WHERE t.scope=? AND t.term IN (''' + ','.join('?' for _ in tokens) + ''')
                GROUP BY m.id ORDER BY
                CASE WHEN m.kind='last_success' THEN 2 WHEN json_extract(m.payload,'$.category') IN ('connection_profile','preference') OR m.kind='procedure' THEN 1 ELSE 0 END DESC,
                score DESC,m.updated DESC LIMIT 24''', [scope, *tokens]).fetchall()
        matches = [dict(self.read(scope, row['id']), score=row['score']) for row in rows]
        # Reserve room for durable connection habits as well as task summaries.
        details = [m for m in matches if m['kind'] != 'summary'][:max(1, limit - 1)]
        summaries = [m for m in matches if m['kind'] == 'summary'][:1]
        return (details + summaries)[:limit]

    def procedure(self, scope, task, receipts, source, verified):
        steps = [{'tool': r['tool'], 'arguments': r['arguments']} for r in receipts
                 if r['tool'] != 'task_feedback' and isinstance(r.get('arguments'), dict)]
        checks = task['spec'].get('checks', [])
        if not steps or len(steps) > 8 or not checks or any(c['path'] in ('path', 'id', 'name') for c in checks):
            return
        recipe = json.dumps({'steps': steps, 'checks': checks}, sort_keys=True, ensure_ascii=False)
        if len(recipe) > 4000:
            return
        key = hashlib.sha256(recipe.encode()).hexdigest()
        with self.store.db() as db:
            # One distinct task is one execution, never count retries or duplicate callbacks.
            db.execute('INSERT OR REPLACE INTO procedure_runs VALUES(?,?,?,?,?,?)',
                       (scope, key, task['id'], source, int(verified), time.time()))
            runs = db.execute('SELECT verified,source FROM procedure_runs WHERE scope=? AND recipe=? ORDER BY updated DESC LIMIT 3', (scope, key)).fetchall()
        ready = len(runs) == 3 and all(row['verified'] for row in runs)
        if not ready:
            identity = 'm-' + hashlib.sha256(('procedure:' + key).encode()).hexdigest()[:20]
            with self.store.db() as db:
                db.execute('DELETE FROM memory_terms WHERE scope=? AND id=?', (scope, identity))
                db.execute("UPDATE memory_items SET payload=json_set(payload,'$.status','needs_review') WHERE scope=? AND id=?", (scope, identity))
            return
        for row in reversed(runs):
            self.save(scope, 'procedure', key, task['spec']['goal'],
                      {'steps': steps, 'checks': checks, 'verified_runs': 3,
                      'status': 'reusable_within_existing_permissions', 'tags': sorted(terms(task['spec']['goal']))[:20]}, row['source'])

    def connection_success(self, scope, config, source, succeeded_at=None):
        when = time.time() if succeeded_at is None else succeeded_at
        with self.store.db() as db:
            db.execute('''INSERT INTO successful_connections VALUES(?,?,?,?,?,?)
                ON CONFLICT(scope,device,transport) DO UPDATE SET config=excluded.config,
                source=excluded.source,succeeded_at=excluded.succeeded_at
                WHERE excluded.succeeded_at>successful_connections.succeeded_at''',
                (scope, config['device'].casefold(), config['transport'], json.dumps(config), source, when))
        previous = self.last_connection(scope, config['device'], config['transport'])
        self.save(scope, 'last_success', config['device'].casefold() + ':' + config['transport'],
                  'Last successful connection: ' + json.dumps(previous['config'], ensure_ascii=False),
                  {'category': 'connection_profile', 'evidence': 'connection_check_verified',
                   'succeeded_at': previous['succeeded_at'], 'config': previous['config'],
                   'tags': [config['device'], config['transport'], 'connection', '连接', '地址']},
                  previous['source'], updated=previous['succeeded_at'])

    def last_connection(self, scope, device, transport):
        with self.store.db() as db:
            row = db.execute('SELECT config,source,succeeded_at FROM successful_connections WHERE scope=? AND device=? AND transport=?',
                             (scope, device.casefold(), transport)).fetchone()
        return {'config': json.loads(row['config']), 'source': row['source'], 'succeeded_at': row['succeeded_at']} if row else None
