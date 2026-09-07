"""Append-only episode metadata; no device command replay on startup."""
import json
import sqlite3
import time


class EventStore:
    def __init__(self, path):
        self.connection = sqlite3.connect(str(path))
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS events "
            "(id INTEGER PRIMARY KEY, timestamp REAL, kind TEXT, payload TEXT)"
        )
        self.connection.commit()

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
