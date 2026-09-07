"""SQLite provider profiles and one active model (legacy slot names remain aliases). No stored keys."""
import json
import os
from pathlib import Path
import re
import sqlite3

from terminal.config import validate_provider


class ProviderStore:
    def __init__(self, path, config):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=5)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("CREATE TABLE IF NOT EXISTS providers (name TEXT PRIMARY KEY, config TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS selection (slot TEXT PRIMARY KEY, name TEXT NOT NULL REFERENCES providers(name))")
        with self.db:
            for slot, source in (("master", "llm"), ("expert", "llm")):
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
                           "key_in_environment": bool(os.environ.get(config["api_key_env"]))})
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
