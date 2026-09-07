"""SQLite provider profiles and one active model (legacy slot names remain aliases). No stored keys."""
import json
import hashlib
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sqlite3

from loop_robot.terminal.config import validate_provider
from loop_robot.terminal.home import saved_key


class ProviderStore:
    def __init__(self, path, config):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=5)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("CREATE TABLE IF NOT EXISTS providers (name TEXT PRIMARY KEY, config TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS selection (slot TEXT PRIMARY KEY, name TEXT NOT NULL REFERENCES providers(name))")
        self.db.execute("CREATE TABLE IF NOT EXISTS connection_checks (name TEXT PRIMARY KEY REFERENCES providers(name) ON DELETE CASCADE, fingerprint TEXT, status TEXT, checked_at TEXT)")
        with self.db:
            for slot, source in (("master", "llm"), ("expert", "llm")):
                if self.db.execute("SELECT 1 FROM selection WHERE slot=?", (slot,)).fetchone():
                    continue
                name = "default-" + slot
                encoded = json.dumps(validate_provider(config[source]))
                self.db.execute("INSERT OR IGNORE INTO providers VALUES (?,?)", (name, encoded))
                self.db.execute("INSERT OR IGNORE INTO selection VALUES (?,?)", (slot, name))
            # Preserve old profiles, but the user-selected main model is authoritative.
            self.db.execute("UPDATE selection SET name=(SELECT name FROM selection WHERE slot='master') WHERE slot='expert'")

    def get(self, name):
        row = self.db.execute("SELECT config FROM providers WHERE name=?", (name,)).fetchone()
        if row is None:
            raise ValueError("unknown provider profile")
        return validate_provider(json.loads(row[0]))

    def save(self, name, config, replace=False):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}", name):
            raise ValueError("profile name must be 1..48 letters/digits/-/_")
        encoded = json.dumps(validate_provider(config))
        with self.db:
            if replace:
                if not self.db.execute("UPDATE providers SET config=? WHERE name=?", (encoded, name)).rowcount:
                    raise ValueError("unknown provider profile")
            else:
                try:
                    self.db.execute("INSERT INTO providers VALUES (?,?)", (name, encoded))
                except sqlite3.IntegrityError:
                    raise ValueError("profile already exists; use edit") from None

    def _key(self, config):
        return saved_key(config) or os.environ.get(config['api_key_env'])

    def deduplicate(self, newest=None):
        """Keep one profile per API base URL, including profiles without keys."""
        rows = list(self.db.execute("SELECT name FROM providers ORDER BY rowid DESC"))
        if newest is not None:
            rows.sort(key=lambda row: row[0] != newest)
        seen, removed = {}, 0
        with self.db:
            for (name,) in rows:
                config = self.get(name)
                identity = config['base_url'].rstrip('/')
                winner = seen.get(identity)
                if winner is None:
                    seen[identity] = name
                    continue
                self.db.execute("UPDATE selection SET name=? WHERE name=?", (winner, name))
                self.db.execute("DELETE FROM providers WHERE name=?", (name,))
                removed += 1
        return removed

    def _fingerprint(self, config):
        payload = json.dumps(config, sort_keys=True) + '\0' + (self._key(config) or '')
        return hashlib.sha256(payload.encode()).hexdigest()

    def record_check(self, status):
        name = self.selected()['master']
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO connection_checks VALUES (?,?,?,?)",
                            (name, self._fingerprint(self.get(name)), status,
                             datetime.now(timezone.utc).isoformat(timespec='seconds')))

    def connection_check(self, name):
        row = self.db.execute("SELECT fingerprint,status,checked_at FROM connection_checks WHERE name=?", (name,)).fetchone()
        if row and row[0] == self._fingerprint(self.get(name)):
            return {'status': row[1], 'checked_at': row[2]}
        return {'status': 'untested', 'checked_at': None}

    def selected(self):
        return dict(self.db.execute("SELECT slot,name FROM selection"))

    def use(self, slot, name):
        if slot not in ("master", "expert"):
            raise ValueError("slot must be master or expert")
        with self.db:
            self.get(name)
            self.db.execute("UPDATE selection SET name=?", (name,))

    def remove(self, name):
        with self.db:
            if self.db.execute("SELECT 1 FROM selection WHERE name=?", (name,)).fetchone():
                raise ValueError("cannot delete an active profile; switch first")
            if not self.db.execute("DELETE FROM providers WHERE name=?", (name,)).rowcount:
                raise ValueError("unknown provider profile")

    def list(self):
        selected = self.selected()
        result = []
        for (name,) in self.db.execute("SELECT name FROM providers ORDER BY name"):
            config = self.get(name)
            result.append({"name": name, **config, "active_for": [k for k, v in selected.items() if v == name],
                           "key_in_environment": bool(os.environ.get(config["api_key_env"])),
                           "connection_check": self.connection_check(name)})
        return result

    def close(self):
        self.db.close()


def choose_profile(store, slot="master", read=input, write=print):
    profiles = store.list()
    for index, item in enumerate(profiles, 1):
        write("{}. {} | {} | {} {}".format(index, item["name"], item["model"], item["base_url"],
                                             "[" + ",".join(item["active_for"]) + "]" if item["active_for"] else ""))
    answer = read("Select a number (Enter to cancel): ").strip()
    if not answer:
        return None
    number = int(answer)
    if not 1 <= number <= len(profiles):
        raise ValueError("invalid selection")
    name = profiles[number - 1]["name"]
    store.use(slot, name)
    return name
