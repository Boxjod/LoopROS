"""Session approval queue plus persistent action rules; not an OS sandbox."""
import json
from pathlib import Path
import sqlite3
import threading
import uuid
from contextlib import closing
from terminal.web import WEB_NAMES
from terminal.robotics import ROBOT_NAMES

ACTION_NAMES = {"simulator_control", "load_model", "node_start", "node_command", "open_serial", "read_serial", "run_sim", "move_sim", "generate_scene", "expert_advice", "spawn_agent", "policy_start", "devices", "open_simulator"}
PLAN_BLOCKED = {"simulator_control", "load_model", "node_start", "node_command", "open_serial", "read_serial", "run_sim", "move_sim", "generate_scene", "spawn_agent", "policy_start", "open_simulator"}
ACTION_NAMES |= WEB_NAMES | {"model_library", "compose_scene", "mujoco_docs"}
PLAN_BLOCKED.add("compose_scene")
ACTION_NAMES |= ROBOT_NAMES
PLAN_BLOCKED.add("pid_trial")
PLAN_BLOCKED |= {"feetech_scan", "feetech_read"}
ACTION_NAMES |= {"carrier_list", "carrier_status", "carrier_start", "carrier_command", "carrier_stop"}
PLAN_BLOCKED |= {"carrier_start", "carrier_command"}
ACTION_NAMES.add("skill_write")
ACTION_NAMES.add("run_python")
PLAN_BLOCKED.add("run_python")
ACTION_NAMES |= {"experience_search", "experience_read", "learning_note", "learning_forget"}
PLAN_BLOCKED |= {"learning_note", "learning_forget"}
ACTION_NAMES |= {"read_file","read_image","read_url","list_files","search_files","write_file","edit_file","harness_read","harness_write"}
PLAN_BLOCKED |= {"write_file","edit_file","harness_write","skill_write"}


class PermissionGate:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.local = threading.local()
        self.pending = {}
        with closing(sqlite3.connect(str(self.path))) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS rules (action TEXT PRIMARY KEY, rule TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            db.execute("INSERT OR IGNORE INTO settings VALUES ('mode','sim')")

    def snapshot(self):
        with closing(sqlite3.connect(str(self.path))) as db, db:
            rules = dict(db.execute("SELECT action,rule FROM rules"))
            mode = db.execute("SELECT value FROM settings WHERE key='mode'").fetchone()[0]
        defaults = {name: 'ask' if name in ('policy_start', 'skill_write', 'harness_write', 'run_python') else 'allow' for name in sorted(ACTION_NAMES)}
        effective = {name: rules.get(name, rule) for name, rule in defaults.items()}
        profile = ('plan' if mode == 'plan' else 'yolo' if all(rule == 'allow' for rule in effective.values())
                   else 'cautious' if all(rule == 'ask' for rule in effective.values())
                   else 'default' if effective == defaults else 'custom')
        return {"mode": mode, "profile": profile, "rules": effective,
                "real_hardware": "disabled",
                "python_execution": "host_user_privileges; not sandboxed; subject to run_python rule"}

    def set_rule(self, action, rule):
        if action not in ACTION_NAMES or rule not in ("allow", "ask", "deny"):
            raise ValueError("unknown action or rule; use allow/ask/deny")
        with closing(sqlite3.connect(str(self.path))) as db, db:
            db.execute("INSERT OR REPLACE INTO rules VALUES (?,?)", (action, rule))

    def allow_available_actions(self):
        """Explicit operator authorization; not exposed as a model tool."""
        with closing(sqlite3.connect(str(self.path))) as db, db:
            db.execute("UPDATE settings SET value='sim' WHERE key='mode'")
            db.executemany("INSERT OR REPLACE INTO rules VALUES (?, 'allow')",
                           [(name,) for name in sorted(ACTION_NAMES)])
        return self.snapshot()

    def set_profile(self, profile):
        if profile == 'cautious':
            profile = 'ask'
        if profile not in ('default', 'plan', 'ask', 'yolo'):
            raise ValueError('Permission profiles: default, plan, ask, yolo')
        with closing(sqlite3.connect(str(self.path))) as db, db:
            db.execute("UPDATE settings SET value=? WHERE key='mode'", ('plan' if profile == 'plan' else 'sim',))
            db.execute('DELETE FROM rules')
            if profile in ('ask', 'yolo'):
                db.executemany('INSERT INTO rules VALUES (?,?)',
                               [(name, 'allow' if profile == 'yolo' else 'ask') for name in sorted(ACTION_NAMES)])
        return self.snapshot()

    def set_mode(self, mode):
        if mode not in ("plan", "sim"):
            raise ValueError("Only plan/sim modes are supported; real hardware is not implemented")
        with closing(sqlite3.connect(str(self.path))) as db, db:
            db.execute("UPDATE settings SET value=? WHERE key='mode'", (mode,))

    def check(self, action, args):
        if action not in ACTION_NAMES:
            raise PermissionError("Unregistered permission action")
        snapshot = self.snapshot()
        if snapshot["mode"] == "plan" and action in PLAN_BLOCKED:
            raise PermissionError("Action blocked in plan mode; use /mode sim to enable simulation")
        rule = snapshot["rules"][action]
        if rule == "deny":
            raise PermissionError("Action blocked by deny rule: " + action)
        fingerprint = json.dumps([action, args], sort_keys=True, allow_nan=False)
        if rule == "ask" and getattr(self.local, "approved", None) != fingerprint:
            with self.lock:
                if len(self.pending) >= 32:
                    raise PermissionError("Approval queue full; review /requests first")
                request_id = uuid.uuid4().hex[:10]
                self.pending[request_id] = {"action": action, "args": json.loads(json.dumps(args))}
            raise PermissionError("Approval required: inspect arguments with /requests, then /approve " + request_id + " to execute once")

    def requests(self):
        with self.lock:
            return json.loads(json.dumps(self.pending))

    def approve(self, request_id, execute):
        with self.lock:
            request = self.pending.pop(request_id)
        return self.confirmed(request["action"], request["args"], execute)

    def confirmed(self, action, args, execute):
        request = {"action": action, "args": args}
        self.local.approved = json.dumps([request["action"], request["args"]], sort_keys=True, allow_nan=False)
        try:
            # Re-check current mode and deny rules; old approval cannot override them.
            self.check(request["action"], request["args"])
            return execute(request["action"], request["args"])
        finally:
            self.local.approved = None

    def reject(self, request_id):
        with self.lock:
            self.pending.pop(request_id)
