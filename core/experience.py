"""Local experience and revisioned advisory notes. Standard library only."""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
import uuid


def terms(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    result = set(re.findall(r'[a-z0-9_]{2,}', text))
    for part in re.findall(r'[\u3400-\u9fff]+', text):
        result.update(part[i:i + 2] for i in range(len(part) - 1))
    return result - {'一下', '帮我', '请你', '这个', 'the', 'and', 'with', 'please'}


class ExperienceStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS experience(
                    id TEXT PRIMARY KEY, scope TEXT, origin TEXT, request TEXT,
                    outcome TEXT, payload TEXT, updated REAL, UNIQUE(scope,origin));
                CREATE TABLE IF NOT EXISTS lessons(
                    scope TEXT, name TEXT, revision INTEGER, content TEXT,
                    sources TEXT, active INTEGER, updated REAL, PRIMARY KEY(scope,name,revision));
                CREATE TABLE IF NOT EXISTS recall_terms(
                    scope TEXT, kind TEXT, id TEXT, term TEXT,
                    PRIMARY KEY(scope,kind,id,term));
                CREATE INDEX IF NOT EXISTS recall_lookup ON recall_terms(scope,term);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def index(self, db, scope, kind, identity, text):
        db.execute('DELETE FROM recall_terms WHERE scope=? AND kind=? AND id=?', (scope, kind, identity))
        db.executemany('INSERT INTO recall_terms VALUES(?,?,?,?)',
                       [(scope, kind, identity, term) for term in sorted(terms(text))[:1000]])

    def record(self, scope, origin, request, outcome, payload):
        if outcome not in ('observed', 'error', 'cancelled', 'verified', 'inconclusive'):
            raise ValueError('Unknown experience outcome')
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(encoded) > 32000:
            raise ValueError('Experience payload exceeds 32000 characters')
        with self.db() as db:
            identity = uuid.uuid4().hex[:16]
            db.execute('INSERT OR IGNORE INTO experience VALUES(?,?,?,?,?,?,?)',
                       (identity, scope, origin, request[:2000], outcome, encoded, time.time()))
            row = db.execute('SELECT id FROM experience WHERE scope=? AND origin=?', (scope, origin)).fetchone()
            if row['id'] == identity:
                hints = [{k: m[k] for k in ('text', 'values', 'tags') if k in m} for m in payload.get('memories', [])]
                self.index(db, scope, 'experience', identity, request[:2000] + ' ' + json.dumps(hints, ensure_ascii=False))
            return row['id']

    def read(self, scope, identity):
        with self.db() as db:
            row = db.execute('SELECT * FROM experience WHERE scope=? AND id=?', (scope, identity)).fetchone()
        if not row:
            raise ValueError('Experience not found in this workspace/provider scope')
        data = dict(row)
        data.pop('scope')
        data['payload'] = json.loads(data['payload'])
        return data

    def lesson(self, scope, name, revision=None):
        with self.db() as db:
            query = 'SELECT * FROM lessons WHERE scope=? AND name=?'
            args = [scope, name]
            if revision is not None:
                query += ' AND revision=?'
                args.append(revision)
            row = db.execute(query + ' ORDER BY revision DESC LIMIT 1', args).fetchone()
        if not row:
            raise ValueError('Learning note not found')
        return {'name': row['name'], 'revision': row['revision'], 'content': row['content'],
                'source_ids': json.loads(row['sources']), 'active': bool(row['active']),
                'status': 'advisory_unverified', 'updated': row['updated']}

    def revise(self, scope, name, content, sources, expected_revision, active=True):
        if not isinstance(name, str) or not 1 <= len(name) <= 64 or not all(c.isprintable() for c in name):
            raise ValueError('Note name must be 1..64 printable characters')
        if not isinstance(content, str) or not 1 <= len(content) <= 3000:
            raise ValueError('Note content must be 1..3000 characters')
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('expected_revision must be a nonnegative integer; use 0 to create')
        if not isinstance(sources, list) or not 1 <= len(sources) <= 8 or any(not isinstance(s, str) for s in sources):
            raise ValueError('Supply 1..8 recorded source IDs')
        evidence = [self.read(scope, source) for source in sources]
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            latest = db.execute('SELECT MAX(revision) FROM lessons WHERE scope=? AND name=?', (scope, name)).fetchone()[0] or 0
            if latest != expected_revision:
                raise ValueError('Note changed; read its current revision before updating')
            revision = latest + 1
            db.execute('INSERT INTO lessons VALUES(?,?,?,?,?,?,?)',
                       (scope, name, revision, content, json.dumps(sources), int(active), time.time()))
            self.index(db, scope, 'lesson', name, content + ' ' + ' '.join(e['request'] for e in evidence) if active else '')
        return self.lesson(scope, name, revision)

    def search(self, scope, query, limit=5):
        if not isinstance(query, str) or not 1 <= len(query) <= 2000:
            raise ValueError('Query must be 1..2000 characters')
        if type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError('Limit must be 1..10')
        tokens = sorted(terms(query))[:64]
        if not tokens:
            return []
        with self.db() as db:
            rows = db.execute('SELECT kind,id,COUNT(*) AS score FROM recall_terms WHERE scope=? AND term IN ('
                              + ','.join('?' for _ in tokens) + ''') GROUP BY kind,id ORDER BY score DESC,
                              CASE kind WHEN 'experience' THEN
                                (SELECT updated FROM experience e WHERE e.id=recall_terms.id AND e.scope=recall_terms.scope)
                              ELSE (SELECT MAX(updated) FROM lessons l WHERE l.name=recall_terms.id AND l.scope=recall_terms.scope)
                              END DESC LIMIT 100''',
                              [scope, *tokens]).fetchall()
        matches = []
        for row in rows:
            data = self.read(scope, row['id']) if row['kind'] == 'experience' else self.lesson(scope, row['id'])
            if row['score'] < min(2, len(tokens)):
                # A named entity such as Jetson is a useful anchor even when
                # the rest of the new question uses different vocabulary.
                tags = {tag.casefold() for m in data.get('payload', {}).get('memories', []) for tag in m.get('tags', [])}
                anchors = {t for t in tokens if re.fullmatch(r'[a-z][a-z0-9_]{3,}', t)}
                if not tags.intersection(anchors):
                    continue
            if row['kind'] == 'lesson' and not data['active']:
                continue
            matches.append({'kind': row['kind'], 'score': row['score'], **data})
        return sorted(matches, key=lambda r: (r['score'], r['updated']), reverse=True)[:limit]

    def skill_usage(self, scope, name):
        if not isinstance(name, str) or not 1 <= len(name) <= 64:
            raise ValueError('Skill name must be 1..64 characters')
        with self.db() as db:
            rows = db.execute("""SELECT json_extract(skill.value,'$.sha256') AS sha256,
                COUNT(DISTINCT e.id) AS reads,
                COUNT(DISTINCT CASE WHEN e.outcome='error' THEN e.id END) AS turns_with_errors,
                COUNT(DISTINCT CASE WHEN e.outcome='verified' THEN e.id END) AS verified_tasks
                FROM experience e, json_each(e.payload,'$.skills_read') skill
                WHERE e.scope=? AND json_extract(skill.value,'$.name')=?
                GROUP BY sha256 ORDER BY MAX(e.updated) DESC LIMIT 30""", (scope, name)).fetchall()
        return {'name': name, 'versions': [dict(row) for row in rows],
                'interpretation': 'Skill was read in these attempts; this does not establish causal success or failure.'}
