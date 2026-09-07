"""Operator commands, intentionally unavailable as model-callable admin tools."""
import importlib.util
import json
from pathlib import Path
import sys

CONTROL_COMMANDS = {
    "/permissions": "[default|plan|cautious|yolo] Profiles; [allow|ask|deny action] Edit a rule",
    "/requests": "Inspect pending approvals and exact arguments",
    "/approve": "ID Approve once; /approve reject ID to reject",
    "/mode": "[plan|sim|real] Show or change execution mode",
    "/plan": "Enter planning-only mode",
    "/tools": "List tools and permission rules",
    "/doctor": "Inspect Python and optional modules; no device connections",
    "/config": "[TARGET] Inspect settings; set TARGET JSON changes configuration without exposing keys",
    "/context": "Show cumulative tokens, context capacity and compaction budget",
    "/history": "Show in-memory conversation history",
    "/compact": "Reduce the model window; preserve complete session history",
    "/robot": "Inspect the simulation body and joint limits",
    "/devices": "Discover local serial ports; Linux also lists USB/camera/input nodes",
    "/joints": "Read the current simulated joint state",
    "/move": "q1 q2 Move simulated joints in radians and review",
    "/home": "Move simulated joints to zero and review",
    "/stop": "Stop simulation and cancel subagents; NOT a hardware E-stop",
    "/commands": "Count and list all slash commands",
}
BASE_COMMANDS = "/tools /skills /after /agents /agent-messages /cancel /clear /complex /every /exit /expert-key /fast /help /jobs /key /model /policy /quit /result /scene /send /shortcuts /sim /spawn /status /stop-agent /switch /viewer /node /models /model-load".split()


def operator_command(app, command, tail):
    dump = lambda value: json.dumps(value, ensure_ascii=False)
    if command == "/commands":
        names = sorted(set(BASE_COMMANDS) | set(CONTROL_COMMANDS))
        return dump({"entries": len(names), "aliases": {"/quit": "/exit", "/shortcuts": "/help", "/plan": "/mode plan"}, "commands": names})
    if command == "/permissions":
        parts = tail.split()
        if parts:
            if len(parts) == 1 and parts[0] in ('default', 'plan', 'ask', 'cautious', 'yolo'):
                app.permissions.set_profile(parts[0])
                app.enforce_node_permissions()
                return dump(app.permissions.snapshot())
            if len(parts) != 2:
                raise ValueError("Usage: /permissions allow|ask|deny action")
            app.permissions.set_rule(parts[1], parts[0])
            app.enforce_node_permissions()
            if parts[0] == "allow" and parts[1] in ("move_sim", "run_sim"):
                app.motion_stop.clear()
        return dump(app.permissions.snapshot())
    if command == "/requests":
        return dump(app.permissions.requests())
    if command == "/approve":
        parts = tail.split()
        if len(parts) == 2 and parts[0] == "reject":
            app.permissions.reject(parts[1])
            return "Rejected. No action executed."
        if len(parts) != 1:
            raise ValueError("Usage: /approve ID or /approve reject ID")
        return dump(app.permissions.approve(parts[0], app.tool))
    if command in ("/mode", "/plan"):
        if command == "/plan" or tail.strip():
            app.permissions.set_mode("plan" if command == "/plan" else tail.strip())
            app.enforce_node_permissions()
        return dump(app.permissions.snapshot())
    if command == "/tools":
        return dump({"tools": [t["function"]["name"] for t in app.agent.tools], "permissions": app.permissions.snapshot()})
    if command == "/doctor":
        import platform
        return dump({"python": sys.version.split()[0], "executable": sys.executable,
                     "product": "Loop ROS", "full_name": "Loop Robot Operating System",
                     "os": platform.system(), "release": platform.release(), "machine": platform.machine(),
                     "linux_serial_adapter": sys.platform.startswith("linux"),
                     "modules_found_not_import_tested": {n: bool(importlib.util.find_spec(n)) for n in ("mujoco", "mink", "rclpy", "genesis")}})
    if command == "/config" and tail.strip():
        from loop_robot.terminal.settings import read, update, TARGETS
        parts = tail.strip().split(maxsplit=2)
        if len(parts) == 1 and parts[0] in TARGETS:
            return dump(read(app, parts[0]))
        if len(parts) == 3 and parts[0] == 'set' and parts[1] in TARGETS:
            return dump(update(app, parts[1], json.loads(parts[2])))
        raise ValueError('Usage: /config TARGET or /config set TARGET JSON')
    if command == "/config":
        return dump({"master": app.client.config, "expert": app.expert.config,
                     "mode": app.permissions.snapshot()["mode"]})
    if command == "/context":
        from loop_robot.terminal.context_window import select
        return dump({**select(app.agent.history, app.agent.history_message_limit)[2],
                     **getattr(app.agent, 'context_report', {}),
                     'context_window': app.client.config.get('context_window'),
                     'token_usage': getattr(app.agent, 'token_usage', {}),
                     'usage_scope': 'current session, reported successful model requests; missing usage is not zero'})
    if command == "/history":
        history = []
        for message in app.agent.history:
            record = dict(message)
            if isinstance(record.get("content"), list):
                record["content"] = [part if part.get("type") == "text" else {"type": part.get("type"), "attachment": "[media omitted]"} for part in record["content"]]
            history.append(record)
        return dump(history)
    if command == "/compact":
        if tail.strip() not in ("", "reset"):
            raise ValueError("Usage: /compact [reset]")
        app.agent.context_report = {}
        if tail.strip() == "reset":
            app.agent.history_message_limit = 32
            return "Automatic model window restored for the next request. Full session history preserved."
        app.agent.history_message_limit = 8
        return "Full session history preserved. Next request uses up to 8 recent messages plus excerpts and turn records; no model request made."
    if command == "/robot":
        return dump({"body": "sim-arm", "backend": "mujoco", "joints": ["j1", "j2"],
                     "limits_rad": [[-1, 1], [-1, 1]], "real_control": False, "session_state": app.sim_body is not None})
    if command == "/devices":
        return dump(app.tool("devices", {}))
    if command == "/joints":
        with app.motion_lock:
            return dump(app.sim_body.observe() if app.sim_body is not None else {"state": "not_initialized", "hint": "/move 0 0"})
    if command in ("/move", "/home"):
        target = [0.0, 0.0] if command == "/home" else [float(x) for x in tail.split()]
        return dump(app.tool("move_sim", {"target": target}))
    if command == "/stop":
        app.motion_stop.set()
        app.viewer.close()
        app.permissions.set_rule("move_sim", "deny")
        app.permissions.set_rule("run_sim", "deny")
        app.enforce_node_permissions()
        for task in app.runtime.status()["tasks"]:
            if task["state"] == "running":
                app.runtime.cancel(task["agent_id"])
        return "Simulation stop requested; further motion denied and subagents cancelled. NOT a hardware E-stop. Resume with /permissions allow move_sim or run_sim."
    raise ValueError("unknown operator command")


def list_devices(dev_root="/dev", sys_root="/sys"):
    if not sys.platform.startswith("linux") and dev_root == "/dev":
        from loop_robot.toolchain.serial_discovery import inventory
        return inventory()
    dev, sysfs = Path(dev_root), Path(sys_root)
    paths = set()
    for pattern in ("video*", "ttyUSB*", "ttyACM*", "serial/by-id/*"):
        paths.update(dev.glob(pattern))
    grouped = {}
    for path in sorted(paths):
        resolved = path.resolve()
        entry = grouped.setdefault(str(resolved), {"node": str(resolved), "aliases": [],
                                                  "present": resolved.exists(), "motor_model": None})
        if path != resolved:
            entry["aliases"].append(str(path))
    def read(path):
        try:
            return path.read_text().strip()[:256]
        except OSError:
            return None
    for entry in grouped.values():
        name = Path(entry["node"]).name
        kind = "video4linux" if name.startswith("video") else "tty"
        base = sysfs / "class" / kind / name
        interface = (base / "device").resolve()
        entry["kind"] = "video" if kind == "video4linux" else "serial"
        entry["interface"] = str(interface) if interface.exists() else None
        driver = interface / "driver"
        entry["kernel_driver"] = driver.resolve().name if driver.exists() else None
        entry["name"] = read(base / "name")
        entry["usb"] = None
        for parent in (interface, *interface.parents):
            vendor, product = read(parent / "idVendor"), read(parent / "idProduct")
            if vendor and product:
                entry["usb"] = {"vid": vendor, "pid": product, "product": read(parent / "product"),
                                "manufacturer": read(parent / "manufacturer"), "device_path": str(parent)}
                break
    usb_devices = []
    for path in sorted((sysfs / 'bus/usb/devices').glob('*')):
        vendor, product = read(path / 'idVendor'), read(path / 'idProduct')
        if vendor and product:
            usb_devices.append({'path': str(path), 'vid': vendor, 'pid': product,
                                'product': read(path / 'product'), 'manufacturer': read(path / 'manufacturer')})
    input_devices = []
    for path in sorted((sysfs / 'class/input').glob('event*')):
        input_devices.append({'node': str(dev / 'input' / path.name), 'name': read(path / 'device/name')})
    return {"device_nodes": sorted(map(str, paths)), "devices": list(grouped.values()),
            "usb_devices": usb_devices, "input_devices": input_devices, "supported": True,
            "opened": False, "identified_or_safe": False,
            "interpretation": "Aliases refer to the same node. Multiple video nodes may share one camera; group by usb.device_path. USB bridge identity and kernel driver do not identify the connected motor. No device opened or probe bytes sent."}
