"""Session approval queue plus persistent action rules; not an OS sandbox."""
import json
from pathlib import Path
import sqlite3
import threading
import uuid
from contextlib import closing
from terminal.web import WEB_NAMES
from terminal.robotics import ROBOT_NAMES
from terminal.simulation import NAMES as SIM_NAMES, READ_NAMES as SIM_READ_NAMES

ACTION_NAMES = {"simulator_control", "load_model", "node_start", "node_command", "open_serial", "read_serial", "run_sim", "move_sim", "generate_scene", "expert_advice", "spawn_agent", "policy_start", "devices", "open_simulator"}
PLAN_BLOCKED = {"simulator_control", "load_model", "node_start", "node_command", "open_serial", "read_serial", "run_sim", "move_sim", "generate_scene", "spawn_agent", "policy_start", "open_simulator"}
ACTION_NAMES |= WEB_NAMES | {"model_library", "compose_scene", "mujoco_docs"}
PLAN_BLOCKED.add("compose_scene")
ACTION_NAMES |= ROBOT_NAMES
PLAN_BLOCKED.add("pid_trial")
PLAN_BLOCKED |= {"feetech_scan", "feetech_read"}
ACTION_NAMES |= {"carrier_list", "carrier_status", "carrier_start", "carrier_command", "carrier_stop"}
PLAN_BLOCKED |= {"carrier_start", "carrier_command"}
ACTION_NAMES |= {"send_agent", "agents_status", "agent_result", "agent_messages", "cancel_agent"}
PLAN_BLOCKED.add("send_agent")
ACTION_NAMES |= {"skill_list", "skill_read", "skill_write", "session_task_read", "session_task_update"}
ACTION_NAMES |= {"skill_executables", "skill_run", "skill_export", "resource_status", "run_python", "settings_read", "settings_update"}
PLAN_BLOCKED |= {"skill_run", "skill_export", "run_python", "tool_write", "tool_run"}
ACTION_NAMES |= {"tool_read", "tool_write", "tool_run", "python_check"}
ACTION_NAMES |= {"experience_search", "experience_read", "learning_note", "learning_forget"}
PLAN_BLOCKED |= {"learning_note", "learning_forget"}
ACTION_NAMES |= {"read_file","read_image","read_url","list_files","search_files","write_file","edit_file","harness_read","harness_write"}
PLAN_BLOCKED |= {"write_file","edit_file","harness_write","skill_write"}
ACTION_NAMES |= SIM_NAMES
PLAN_BLOCKED |= SIM_NAMES - SIM_READ_NAMES - {'sim_close'}


class ApprovalPreconditionError(ValueError):
    """A verified precondition failed before any requested mutation began."""


class PermissionGate:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.local = threading.local()
        self.pending = {}
        self.approving = set()
        with closing(sqlite3.connect(str(self.path))) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS rules (action TEXT PRIMARY KEY, rule TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            db.execute("INSERT OR IGNORE INTO settings VALUES ('mode','sim')")

    def snapshot(self):
        with closing(sqlite3.connect(str(self.path))) as db, db:
            rules = dict(db.execute("SELECT action,rule FROM rules"))
            mode = db.execute("SELECT value FROM settings WHERE key='mode'").fetchone()[0]
        defaults = {name: 'ask' if name in ('skill_export', 'policy_start', 'skill_write', 'harness_write', 'run_python', 'settings_update', 'tool_write', 'tool_run', 'sim_record') else 'allow' for name in sorted(ACTION_NAMES)}
        effective = {name: rules.get(name, rule) for name, rule in defaults.items()}
        profile = ('plan' if mode == 'plan' else 'yolo' if all(rule == 'allow' for rule in effective.values())
                   else 'cautious' if all(rule == 'ask' for rule in effective.values())
                   else 'default' if effective == defaults else 'custom')
        return {"mode": mode, "profile": profile, "rules": effective,
                "real_hardware": "driver_required" if mode == "real" else "disabled",
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
        mode = {"hardware": "real"}.get(mode, mode)
        if mode not in ("plan", "sim", "real"):
            raise ValueError("Supported modes: plan, sim, real (hardware alias); hardware requires an installed validated driver")
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
            if request_id not in self.pending:
                raise ValueError('Approval ID not found or already consumed. Use /requests; if absent, submit the original request again.')
            if request_id in self.approving:
                raise ValueError('This approval is already executing; wait for its result')
            request = self.pending[request_id]
            self.approving.add(request_id)
        try:
            result = self.confirmed(request['action'], request['args'], execute)
        except ApprovalPreconditionError as exc:
            with self.lock:
                request['blocked_reason'] = str(exc)
            raise ApprovalPreconditionError(str(exc) + '. Approval ' + request_id + ' retained; resolve the blocker, then approve the same ID.') from None
        except BaseException:
            # An action may already have effects. Never turn an arbitrary error
            # into an approval that can blindly replay that action.
            with self.lock:
                self.pending.pop(request_id, None)
            raise
        else:
            with self.lock:
                self.pending.pop(request_id, None)
            return result
        finally:
            with self.lock:
                self.approving.discard(request_id)

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
            if request_id in self.approving:
                raise ValueError('This approval is already executing; rejection cannot undo it')
            if request_id not in self.pending:
                raise ValueError('Approval ID not found or already consumed. Use /requests.')
            self.pending.pop(request_id)
