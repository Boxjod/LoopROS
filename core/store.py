"""Append-only episode metadata; no device command replay on startup."""
import json
import sqlite3
import time
from .contracts import record


class EventStore:
    def __init__(self, path):
        self.connection = sqlite3.connect(str(path))
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS events "
            "(id INTEGER PRIMARY KEY, timestamp REAL, kind TEXT, payload TEXT)"
        )
        self.connection.commit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def append_episode_review(self, episode, review):
        """Persist the caller's evidence and verdict together, without rejudging."""
        rows = [(time.time(), kind, json.dumps(record(value), ensure_ascii=False, allow_nan=False))
                for kind, value in (('episode', episode), ('review', review))]
        with self.connection:
            self.connection.executemany('INSERT INTO events(timestamp, kind, payload) VALUES (?, ?, ?)', rows)

    def append(self, kind, payload):
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        with self.connection:
            self.connection.execute(
                "INSERT INTO events(timestamp, kind, payload) VALUES (?, ?, ?)",
                (time.time(), kind, encoded),
            )

    def events(self):
        return [(kind, json.loads(payload)) for kind, payload in
                self.connection.execute("SELECT kind, payload FROM events ORDER BY id")]

    def close(self):
        self.connection.close()
