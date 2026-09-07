import argparse
import getpass
import json
from pathlib import Path
import re
import shlex
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from terminal.config import ROOT, DEFAULT_STATE_DIR, load_config, user_config_file
from terminal.ui import VERSION, welcome
from terminal.platform_support import lock_terminal, InputPoller
from terminal.home import save_key, loop_home
from terminal.setup import ensure_setup, quick_setup
from terminal.llm import ChatAgent, QwenClient
from terminal.scheduler import Scheduler
from terminal.services import PolicyServices
from terminal.agents import AgentRuntime, AGENT_TOOLS, ALLOWED_AGENT_TOOLS
from terminal.providers import ProviderStore, choose_profile
from terminal.permissions import PermissionGate, ACTION_NAMES
from terminal.control import CONTROL_COMMANDS, operator_command, list_devices
from terminal.nodes import NODE_TOOLS
from terminal.model_library import LIBRARY_TOOLS
from terminal.mujoco_docs import DOC_TOOLS
from terminal.robotics import ROBOT_TOOLS, ROBOT_NAMES
from terminal.web import WEB_TOOLS, WEB_NAMES, dispatch as web_dispatch
from terminal.skills import SKILL_TOOLS, SKILL_NAMES, tool as skills_tool
from terminal.files import FILE_TOOLS, FILE_NAMES, tool as files_tool

HELP = """Loop ROS commands
/help, /shortcuts         Show help
/details [ID]            Expand a tool result (interactive terminal)
/resume [TITLE]             Browse/select saved conversations
/history [TITLE]            View conversation and per-turn summaries
/new [GOAL]              Start a new conversation with fresh work
/rename NAME             Name the current conversation (interactive)
/sessions [QUERY]        Search saved conversations (interactive)
/export [TITLE]             Export conversation Markdown (interactive)
/queue [clear|resume]     Inspect, clear or resume queued work
/skills [list|inspect|run|status|logs|stop|save]  Select saved executable Skills offline
/node [help|list|start|use|status|move|logs|stop]  Manage persistent processes
/carrier [list|status|start|move|stop]  Route to configured local robot carriers
/key [save]              Set API key; save persists in user home
/model [name]            Show/change the session model
/fast [on|off|status]    Toggle requested Fast tier for the current client
/switch [master|expert] [profile]  Select and save a model profile
/switch list|reload      List profiles / apply external changes
/switch setup            Open URL + API key quick setup
/status                  Policy process status, not robot health
/sim                     Run the MuJoCo joint feedback loop (no GUI)
/viewer [status|stop|reload|pause|resume|reset|step N|speed X|camera VIEW|actuate VALUES]
/models                  List official Menagerie models
/model-load NAME         Download verified assets and open model (paused)
/scene description       Generate and automatically open a scene
/scene --complex description  Use the current model
/complex task            Ask the current model for advice; no physical execution
/expert-key [save]       Alias for /key; same model credentials
/agents                  List roles and subagent tasks
/spawn role task         Start an isolated subagent
/send TARGET message     Send context; choose an agent by title in the menu
/result TARGET           Inspect a subagent result
/agent-messages TARGET   Inspect message delivery receipts
/stop-agent TARGET       Cancel a subagent
/policy pi05|act status|start|stop
/after seconds task      Schedule a one-time task
/every seconds task      Schedule a repeating task
/jobs                    List legacy foreground timers
/tasks [list|all|status TITLE|cancel TITLE|resume TITLE [-- MESSAGE]|start|stop|config] Persistent task supervisor
/task [goal]             Show tasks, or submit a persistent goal (task_submit can supply acceptance)
/trigger event           Fire a configured named event
/cancel ID               Cancel a pending timer
/clear                   Clear conversation context
/exit                    Exit and stop owned policy processes
Timers run only while this terminal is open. Missed intervals are not replayed.
"""
HELP += "\n" + "\n".join(name + " " + help_text for name, help_text in CONTROL_COMMANDS.items()) + "\n"
ALIASES = {"快捷指令": "/help", "帮助": "/help", "推理状态": "/status",
           "开始PI推理": "/policy pi05 start", "开始ACT推理": "/policy act start",
           "停止PI推理": "/policy pi05 stop", "停止ACT推理": "/policy act stop"}
TOOLS = [{"type": "function", "function": {"name": name, "description": description,
           "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}}
         for name, description in (("status", "查看 pi0.5/ACT 服务状态，不连接机器人"),
                                   ("run_sim", "只执行双关节离线测试；不创建桌面场景、不打开任何窗口"),
                                   ("open_simulator", "实际打开MuJoCo桌面窗口，加载最近场景，无场景时自动生成默认桌面；缺依赖自动安装，无需额外确认"),
                                   ("simulator_status", "查询GUI进程和window_open真实状态"),
                                   ("close_simulator", "关闭本终端打开的MuJoCo窗口"))]
TOOLS += [{"type": "function", "function": {"name": name, "description": description,
           "parameters": {"type": "object", "properties": {"description": {"type": "string"}},
                          "required": ["description"], "additionalProperties": False}}}
          for name, description in (("generate_scene", "生成桌面场景；参数未指定自动采用合理默认值、不询问确认；允许空桌、支持自定义尺寸；由当前模型处理。生成成功后自动打开窗口；以返回viewer.window_open确认实际状态"),
                                    ("expert_advice", "使用当前用户配置的模型进行复杂推理咨询，不执行动作"))]
TOOLS += [{"type": "function", "function": {"name": "move_sim", "description": "移动模拟双关节，不控制真机",
          "parameters": {"type": "object", "properties": {"target": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}},
                         "required": ["target"], "additionalProperties": False}}},
          {"type": "function", "function": {"name": "devices", "description": "只读检测本机已连接硬件：USB设备、串口/摄像头与输入节点；查询实际结果，不打开设备",
          "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}}]


for name, description, properties, required in (
    ("open_serial", "打开指定串口用于接收，须明确端口与波特率；不发送字节、不识别电机；打开端口可能改变DTR/RTS或重置设备", {"port": {"type": "string"}, "baud": {"type": "integer"}}, ["port", "baud"]),
    ("read_serial", "有界读取已打开串口，返回原始hex；未知响应不证明电机型号", {"max_bytes": {"type": "integer"}, "timeout_ms": {"type": "integer"}}, []),
    ("serial_status", "查询本终端串口连接状态，不打开设备", {}, []),
    ("close_serial", "关闭本终端串口接收会话", {}, []),
):
    TOOLS.append({"type": "function", "function": {"name": name, "description": description,
                 "parameters": {"type": "object", "properties": properties, "required": required,
                                "additionalProperties": False}}})


TOOLS.append({'type': 'function', 'function': {'name': 'simulator_control',
    'description': '控制当前真实MuJoCo窗口：暂停/继续/重置(暂停)/单步/速度/相机/强制重载/执行器控制。move_joints规划关节轨迹，move_cartesian规划body原点到世界坐标position(xyz)的IK轨迹；需robot前缀和duration秒。查询motion状态验收；stop_motion停止。actuate为ctrl单位。位置到达不证明抓取成功。',
    'parameters': {'type': 'object', 'properties': {
        'action': {'type': 'string', 'enum': ['pause', 'resume', 'reset', 'step', 'speed', 'camera', 'actuate', 'reload', 'move_joints', 'move_cartesian', 'stop_motion']},
        'steps': {'type': 'integer'}, 'value': {'type': 'number'}, 'view': {'type': 'string'},
        'robot':{'type':'string'}, 'body':{'type':'string'}, 'duration':{'type':'number'}, 'target':{'type':'array','items':{'type':'number'}}, 'position':{'type':'array','items':{'type':'number'}}, 'values': {'type': 'array', 'items': {'type': 'number'}}}, 'required': ['action'], 'additionalProperties': False}}})
TOOLS += LIBRARY_TOOLS + DOC_TOOLS + ROBOT_TOOLS
TOOLS += NODE_TOOLS
TOOLS += WEB_TOOLS
from terminal.offline_skills import TOOLS as OFFLINE_SKILL_TOOLS, NAMES as OFFLINE_SKILL_NAMES, tool as offline_skill_tool
TOOLS += SKILL_TOOLS + OFFLINE_SKILL_TOOLS
TOOLS += FILE_TOOLS
from terminal.coding import CODING_TOOLS, CODING_NAMES, tool as coding_tool
from terminal.harness import HARNESS_TOOLS, HARNESS_NAMES, tool as harness_tool
from terminal.references import REFERENCE_TOOLS
from terminal.conversation_context import CONTEXT_TOOLS, BASE_PROMPT, context as build_conversation_context
from terminal.python_runner import TOOLS as PYTHON_TOOLS
TOOLS += CODING_TOOLS + HARNESS_TOOLS + REFERENCE_TOOLS + CONTEXT_TOOLS + PYTHON_TOOLS
from terminal.task_tools import TASK_TOOLS, NAMES as TASK_NAMES
TOOLS += TASK_TOOLS
from terminal.learning import Learning, TOOLS as LEARNING_TOOLS, NAMES as LEARNING_NAMES, tool as learning_tool
TOOLS += LEARNING_TOOLS
from terminal.carriers import Carriers, TOOLS as CARRIER_TOOLS, NAMES as CARRIER_NAMES, load_bound, validate_bindings
from terminal.settings import TOOLS as SETTINGS_TOOLS, NAMES as SETTINGS_NAMES, call as settings_call
from terminal.session_task import SessionTask, TOOLS as SESSION_TASK_TOOLS, NAMES as SESSION_TASK_NAMES, call as session_task_call
from terminal.user_tools import TOOLS as USER_TOOLS, NAMES as USER_TOOL_NAMES, call as user_tool_call
from terminal.files import schema
TOOLS += [schema('resource_status', 'Read shared host RAM/CPU/GPU telemetry, resource reservations and admission limits across workloads. Does not launch work.', {}, [])]
TOOLS += CARRIER_TOOLS + SETTINGS_TOOLS + SESSION_TASK_TOOLS + USER_TOOLS
from terminal.simulation import TOOLS as SIM_TOOLS, NAMES as SIM_NAMES, call as simulation_call
TOOLS += SIM_TOOLS


class App:
    def __init__(self, config, state_dir, confirm=None, background=False):
        from toolchain.serial_port import SerialPort
        self.serial = SerialPort()
        self.config = config
        self.workspace_root = Path.cwd().resolve()
        self.active_toolsets = set()
        state_dir = Path(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir = state_dir
        self.deployment = load_bound(state_dir)
        if self.deployment:
            from toolchain.node_workers import definitions
            validate_bindings(self.deployment, definitions())
        self.permissions = PermissionGate(state_dir / "permissions.sqlite")
        self.motion_lock = threading.RLock()
        self.motion_stop = threading.Event()
        self.sim_body = None
        self.providers = ProviderStore(state_dir / "providers.sqlite", config)
        for slot, section in (("master", "llm"), ("expert", "expert")):
            config[section] = self.providers.get(self.providers.selected()[slot])
        self.key_cache = {}
        self.evidence_path = state_dir / "episodes.sqlite"
        self.scene_dir = state_dir / "scenes"
        from terminal.viewer import SimulatorViewer
        self.viewer = SimulatorViewer(ROOT, state_dir / "viewer")
        self.latest_scene = None
        self.last_scene_request = None
        self.scene_generation_error = None
        self.restore_scene_state()
        from core.resources import ResourceManager
        from toolchain.admission import HostMonitor
        self.resources = ResourceManager(state_dir / "resource_leases.sqlite", config.get("resources", {}), HostMonitor())
        self.services = PolicyServices(config["services"], state_dir / "services", resources=self.resources)
        self.scheduler = Scheduler(state_dir / "jobs.sqlite", recover=not background)
        self.client = QwenClient(config["llm"])
        self.expert = self.client  # Legacy role/tool alias; one model and credential source.
        config["expert"] = self.client.config
        definitions = AgentRuntime.load_definitions(user_config_file("agents.json"), ALLOWED_AGENT_TOOLS)
        admission = self.resources
        self.runtime = AgentRuntime(definitions, {"llm": self.client, "expert": self.expert},
                                    TOOLS + AGENT_TOOLS, self.tool, state_dir / "agents.jsonl",
                                    max_workers=admission.policy["max_workers"], admission=admission)
        # Submission already passed the permission gate; preserve that approval
        # while rechecking current mode and deny rules at delayed launch.
        self.runtime.before_start = lambda role, task: self.permissions.confirmed(
            "spawn_agent", {"role": role, "task": task}, lambda action, args: None)
        self.runtime.before_tool = lambda agent_id, name, args: self.permissions.check(name, args)
        self.stop_event = threading.Event()
        self.agent = ChatAgent(self.client, TOOLS + AGENT_TOOLS, self.tool,
                               BASE_PROMPT, self.runtime.inbox, self.stop_event)
        self.learning = Learning(state_dir / 'learning.sqlite',
            lambda: json.dumps([str(self.workspace_root), self.client.config['base_url'].rstrip('/'),
                                self.client.config['model'], self.client.config.get('protocol', 'openai')] + (self.deployment.scope() if self.deployment else [])),
            secrets=lambda: [self.client.resolved_key()],
            can_recall=lambda: all(self.permissions.snapshot()['rules'].get(name) == 'allow'
                                   for name in ('experience_search', 'experience_read')))
        self.agent.on_turn_recorded = lambda summary, events: self.learning.record_turn(
            summary, events, cancelled=self.stop_event.is_set(),
            session_id=self.session_task.data.get('session_id'), task_id=self.session_task.data['id'],
            task={k: v for k, v in self.session_task.data.items() if k in ('goal', 'state', 'plan', 'progress', 'next_step', 'checks')})
        import uuid
        self.session_id = uuid.uuid4().hex[:12]
        self.session_task = SessionTask(identity=self.session_id)
        self.agent.on_tool_result = self.observe_tool_result
        self.agent.on_session_finished = lambda summary, events: self.session_task.finish(summary, events)
        self.agent.prepare_input = self.prepare_input
        self.agent.context_provider = lambda text: build_conversation_context(self, text)
        self.agent.output_guidance = (
            "Report the result, supporting evidence, unresolved errors and next steps concisely in the user's language. "
            "Explain receipts in plain language; raw tool results are available through /details. "
            "Include paths or technical details when useful or requested."
        )
        from core.nodes import NodeRuntime
        from toolchain.node_workers import definitions
        self.nodes = NodeRuntime(definitions(), state_dir / "nodes", admission=self.resources)
        self.node_focus = "master"
        self.carriers = Carriers(self, self.deployment)
        self.confirm = confirm or (lambda message: input(message + " [y/N] ").strip().lower() == "y")

    def prepare_input(self, text, attachments):
        from terminal.references import prepare
        self.session_task.begin(text)
        self.active_toolsets.clear()  # Specialist schemas last for one turn only.
        return prepare(self, text, attachments)

    def observe_tool_result(self, name, args, result):
        # Advisory feedback is added to the actual receipt; it never retries an action.
        from terminal.connection_memory import fallback
        import sqlite3
        try:
            feedback = fallback(self.learning, result)
            if feedback:
                result['memory_feedback'] = feedback
        except (OSError, ValueError, sqlite3.Error):
            pass  # Memory availability must not mask the operation's real outcome.
        self.session_task.receipt(name, args, result)

    def enforce_node_permissions(self):
        permissions = self.permissions.snapshot()
        if permissions['mode'] == 'plan' or any(permissions['rules'][name] == 'deny' for name in ('simulator_control', 'open_simulator')):
            self.viewer.close()
        for node in self.nodes.status()['nodes']:
            if not node['process_alive']:
                continue
            dependencies = ['node_start'] + (['open_serial', 'read_serial'] if node['kind'] == 'serial_rx' else ['run_python', 'node_command'] if node['kind'] == 'process' else ['move_sim', 'node_command'])
            if permissions['mode'] == 'plan' or any(permissions['rules'][action] == 'deny' for action in dependencies):
                self.nodes.stop(node['name'])

    def tool(self, name, args):
        if name == 'resource_status':
            if args != {}: raise ValueError('No arguments expected')
            self.permissions.check(name, args)
            return self.resources.status()
        if name in USER_TOOL_NAMES:
            return user_tool_call(self, name, args)
        if name in SESSION_TASK_NAMES:
            return session_task_call(self, name, args)
        if name in SETTINGS_NAMES:
            return settings_call(self, name, args)
        if name == "run_python":
            self.permissions.check(name, args)
            from terminal.python_runner import run
            return run(self, args)
        if name in CARRIER_NAMES:
            return self.carriers.call(name, args)
        if name in LEARNING_NAMES:
            return learning_tool(self, name, args)
        if name == 'load_toolset':
            if not isinstance(args,dict) or set(args)!={'name'} or args['name'] not in ('robotics','tasks','agents'):
                raise ValueError('name must be robotics, tasks or agents')
            self.active_toolsets.add(args['name'])
            return {'loaded':args['name'], 'executes_actions':False}
        if name in CODING_NAMES | HARNESS_NAMES | FILE_NAMES | {'read_url'}:
            self.permissions.check(name,args)
            if name in CODING_NAMES: return coding_tool(self,name,args)
            if name in HARNESS_NAMES: return harness_tool(self,name,args)
            if name in FILE_NAMES: return files_tool(self,name,args)
            from terminal.references import read_url
            if not isinstance(args,dict) or set(args)!={'url'}: raise ValueError('url required')
            return read_url(args['url'])
        if name in TASK_NAMES:
            from terminal.task_tools import dispatch
            return dispatch(self,name,args)
        if name in ROBOT_NAMES:
            self.permissions.check(name,args)
            from terminal.robotics import dispatch
            return dispatch(self,name,args)
        if name in SIM_NAMES:
            return simulation_call(self,name,args)
        if name == 'mujoco_docs':
            self.permissions.check(name, args)
            from terminal.mujoco_docs import lookup
            if args.get('query'): self.permissions.check('web_search', {'query':args['query']})
            return lookup(self.state_dir / 'docs_cache', **args)
        if name == 'compose_scene':
            self.permissions.check(name, args)
            return self.compose(args)
        if name in ('model_library', 'load_model'):
            self.permissions.check(name, args)
            from terminal.model_library import catalog, search
            if name == 'model_library':
                if not isinstance(args,dict) or set(args)-{'query'}: raise ValueError('Only query is supported')
                if args.get('query'):
                    return search(self.state_dir / 'models', args['query'],before_web=lambda q:self.permissions.check('web_search',{'query':q}))
                result = catalog(); result.pop('entries'); return result
            if not isinstance(args,dict) or set(args)-{'model','name','support','position','source'} or not isinstance(args.get('model'),str):
                raise ValueError('model required; optional name/support/position/source')
            item={'kind':'asset','query':args['model'],'name':args.get('name',re.sub('[^a-z0-9_]', '_', args['model'].lower())[:40] or 'object')}
            for key in ('support','position','source'):
                if key in args: item[key]=args[key]
            if 'support' not in item:
                known=self.scene_objects()
                item['support']='table' if 'table' in known else 'floor'
            if item['name'] in self.scene_objects():
                if any(key in args for key in ('support','position')):
                    return self.compose({'move':[{k:v for k,v in item.items() if k in ('name','support','position')}]})
                return self.compose({'base':'current','add':[]})
            return self.compose({'base':'current','add':[item]})

        if name in WEB_NAMES:
            self.permissions.check(name, args)
            return web_dispatch(name, args)
        if name in {t['function']['name'] for t in NODE_TOOLS}:
            from terminal.nodes import tool
            return tool(self, name, args)
        if name in OFFLINE_SKILL_NAMES:
            return offline_skill_tool(self, name, args)
        if name in SKILL_NAMES:
            return skills_tool(self, name, args)
        if name in {"open_serial", "read_serial", "serial_status", "close_serial"}:
            allowed = {"open_serial": {"port", "baud"}, "read_serial": {"max_bytes", "timeout_ms"},
                       "serial_status": set(), "close_serial": set()}[name]
            if not isinstance(args, dict) or set(args) - allowed or (name == "open_serial" and set(args) != allowed):
                raise ValueError("Invalid serial tool arguments")
            if name in ACTION_NAMES:
                self.permissions.check(name, args)
            operation = {"open_serial": self.serial.open, "read_serial": self.serial.read,
                         "serial_status": self.serial.status, "close_serial": self.serial.close}[name]
            return operation(**args)
        if name in ACTION_NAMES and name != "generate_scene":
            self.permissions.check(name, args)
        if name == 'simulator_control':
            if args == {'action': 'reload'}:
                if self.latest_scene is None:
                    return self.tool('open_simulator', {})
                self.permissions.check('open_simulator', {})
                return self.viewer.open(self.latest_scene, force=True)
            result=self.viewer.command(**args)
            if result.get('error'):result['retryable']=False
            if args.get('action') in ('move_joints','move_cartesian') and result.get('executed'):
                import time
                def finish(motion,error=None):
                    from core.store import EventStore
                    finished={**result,'executed':error is None,'motion':motion,'review':{'verdict':'pass' if error is None else 'fail','reason':error or 'Measured motion reached tolerance; grasp not evaluated'}}
                    if error:finished['error']=error
                    store=EventStore(self.viewer.directory/'control.sqlite')
                    try:store.append('motion_result',finished);store.append('review',finished['review'])
                    finally:store.close()
                    return finished
                deadline=time.monotonic()+36
                next_progress=0
                while time.monotonic()<deadline:
                    state=self.viewer.status();motion=state.get('motion') or {}
                    if motion.get('id') and motion['id']!=result.get('id'):
                        return finish(motion,'Motion replaced by another command')
                    if time.monotonic()>=next_progress:
                        self.agent.on_event('status','Moving '+str(motion.get('robot','arm'))+' · joint error '+str(round(motion.get('max_joint_error',0),4))+' rad')
                        next_progress=time.monotonic()+1
                    if self.stop_event.is_set():
                        self.viewer.command(action='stop_motion')
                        return finish(self.viewer.status().get('motion'),'Motion cancelled')
                    if not state.get('window_open'):
                        return finish(motion,'Window closed during motion')
                    if motion.get('state')!='running':
                        return finish(motion,None if motion.get('state')=='succeeded' else motion.get('reason','Motion not completed'))
                    time.sleep(.1)
                self.viewer.command(action='stop_motion')
                return finish(self.viewer.status().get('motion'),'Motion timed out; stopped')
            return result
        if name in ("open_simulator", "simulator_status", "close_simulator"):
            if args != {}:
                raise ValueError("no arguments expected")
            if name == "simulator_status":
                return self.viewer.status()
            if name == "close_simulator":
                self.viewer.close()
                return self.viewer.status()
            if self.scene_generation_error:
                return {"window_open": False, "error": "最近的场景生成失败，不能把旧场景作为新结果打开：" + self.scene_generation_error}
            self.viewer.ensure_installed()
            if self.latest_scene is None:
                from toolchain.scenes import save_default_scene
                # Only use compiler-produced scenes; don't load arbitrary model paths.
                candidates = sorted(self.scene_dir.glob("*/scene.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                if candidates:
                    from toolchain.scenes import compile_scene, physics_check
                    spec = json.loads(candidates[0].read_text())
                    xml = compile_scene(spec)
                    physics_check(xml)
                    self.latest_scene = candidates[0].with_name("viewer_scene.xml")
                    self.latest_scene.write_text(xml)
                else:
                    self.latest_scene = Path(save_default_scene(self.scene_dir)["scene"])
            return self.viewer.open(self.latest_scene)
        if name == "policy_start":
            if set(args) != {"name"} or args["name"] not in ("pi05", "act"):
                raise ValueError("invalid policy service")
            return self.services.start(args["name"])
        if name == "move_sim":
            if not isinstance(args, dict) or set(args) != {"target"}:
                raise ValueError("target required")
            return self.move_sim(args["target"])
        if name == "spawn_agent":
            return self.runtime.spawn(**args)
        if name == "agents_status":
            if args != {}:
                raise ValueError("no arguments expected")
            return self.runtime.status()
        if name == "agent_messages":
            if not isinstance(args, dict) or set(args) != {"agent_id"}:
                raise ValueError("agent_id required")
            return self.runtime.messages(**args)
        if name == "agent_result":
            return self.runtime.result(**args)
        if name == "send_agent":
            if not isinstance(args, dict) or set(args) != {"agent_id", "message"}:
                raise ValueError("agent_id and message required; sender is assigned by broker")
            return self.runtime.send(**args)
        if name == "cancel_agent":
            return self.runtime.cancel(**args)
        if name in ("generate_scene", "expert_advice"):
            if (not isinstance(args, dict) or "description" not in args
                    or set(args) - ({"description", "complex_task"} if name == "generate_scene" else {"description"})):
                raise ValueError("description required")
            description = args["description"]
            if not isinstance(description, str) or not 1 <= len(description) <= 16000:
                raise ValueError("invalid description")
            if name == "generate_scene":
                return self.scene(description, args.get("complex_task", False))
            result = self.expert.complete([
                {"role": "system", "content": "你是机器人任务规划顾问。仅提供分析；不执行工具、不声称任务已完成。区分已知事实、假设和待验证条件。"},
                {"role": "user", "content": description}], [])
            return {"model": self.expert.config["model"], "advice": result.get("content")}
        if args != {}:
            raise ValueError("tool takes no arguments")
        if name == "status":
            return self.services.status()
        if name == "devices":
            if args != {}:
                raise ValueError("no arguments expected")
            return list_devices()
        if name == "run_sim":
            return {**self.move_sim([0.3, -0.2]), "execution": "offline_joint_test",
                    "opens_window": False, "tabletop_scene": False}
        raise ValueError("unregistered tool")

    def move_sim(self, target):
        self.viewer.ensure_installed()
        from toolchain.trajectory import validate_target
        validate_target(target, ((-1, 1), (-1, 1)))
        with self.motion_lock:
            from core.contracts import TaskSpec, record
            from core.loop import Loop
            from core.plugins import FeedbackMaster, NumericalReviewer
            from core.store import EventStore
            from toolchain.mujoco_sim import MujocoBody
            if self.sim_body is None:
                self.sim_body = MujocoBody(ROOT / "examples/two_joint.xml", {"j1": "a1", "j2": "a2"})
                self.sim_body.cancel_event = self.motion_stop
            body = self.sim_body
            store = EventStore(self.evidence_path)
            try:
                review = Loop(body, FeedbackMaster(), NumericalReviewer(), store).run(
                    TaskSpec("terminal-sim", "sim-arm", tuple(target), tolerance=0.02))
                return {"review": record(review), "evidence_path": str(self.evidence_path),
                        "execution": "offline_joint_test", "controls_viewer": False, "pick_and_place": False}
            finally:
                store.close()

    def scene(self, description, complex_task=False):
        if type(complex_task) is not bool:
            raise ValueError("complex_task must be boolean")
        self.permissions.check("generate_scene", {"description": description, "complex_task": complex_task})
        from toolchain.scenes import generate_scene
        self.viewer.ensure_installed()
        self.last_scene_request = description
        self.save_scene_state()
        try:
            from terminal.scene_intent import direct_edit
            explicit_edit = direct_edit(description)
            if explicit_edit:
                return self.publish_scene(self.build_composition(explicit_edit, description))
            simple=re.sub(r'[\s。.!！,，]','',description)
            local_kind={'生成一个椅子':'chair','生成一把椅子':'chair','椅子':'chair','生成一个桌子':'table','生成一张桌子':'table','桌子':'table'}.get(simple)
            if self.latest_scene and local_kind:
                edit={'base':'current','add':[] if local_kind in self.scene_objects() else [{'name':local_kind,'kind':local_kind,'position':[-1,0,0] if local_kind=='chair' and 'table' in self.scene_objects() else [0,0,0]}]}
                return self.publish_scene(self.build_composition(edit,description))
            result = generate_scene(description, self.client, self.expert, self.scene_dir, complex_task,
                                    stop_event=self.stop_event, on_event=self.agent.on_event,
                                    compose=lambda edit: self.build_composition(edit, description),
                                    current_context=self.scene_objects())
        except Exception as exc:
            self.scene_generation_error = str(exc)
            self.save_scene_state()
            raise
        return self.publish_scene(result)

    def scene_objects(self):
        if self.latest_scene is None: return {}
        report=self.latest_scene.with_name('report.json')
        if report.exists():
            data=json.loads(report.read_text())
            if 'objects' in data: return data['objects']
        spec=self.latest_scene.with_name('scene.json')
        if spec.exists():
            data=json.loads(spec.read_text())
            objects={obj['name']:{'kind':obj.get('shape')} for obj in data.get('objects',[])}
            if data.get('preset')=='chair': objects['chair']={'kind':'chair'}
            if data.get('preset')!='chair' or data.get('include_table'): objects['table']={'kind':'table'}
            return objects
        return {}

    def restore_scene_state(self):
        path=self.state_dir/'scene_state.json'
        if not path.exists(): return
        state=json.loads(path.read_text())
        self.last_scene_request=state.get('last_request')
        self.scene_generation_error=state.get('error')
        scene=Path(state['scene']) if state.get('scene') else None
        if scene and not scene.is_absolute():
            scene=self.state_dir/scene
        if scene and scene.resolve().is_relative_to(self.scene_dir.resolve()) and scene.exists():
            from toolchain.model_assets import snapshot
            _,_,digest=snapshot(scene)
            if digest==state.get('scene_sha256'): self.latest_scene=scene

    def save_scene_state(self):
        from toolchain.model_assets import snapshot
        digest=snapshot(self.latest_scene)[2] if self.latest_scene else None
        path=self.state_dir/'scene_state.json';temp=path.with_suffix('.tmp')
        scene=str(self.latest_scene.resolve().relative_to(self.state_dir.resolve())) if self.latest_scene else None
        temp.write_text(json.dumps({'scene':scene,'scene_sha256':digest,
                                   'last_request':self.last_scene_request,'error':self.scene_generation_error},ensure_ascii=False))
        temp.replace(path)

    def build_composition(self, edit, description=''):
        from toolchain.composition import compose
        from terminal.model_library import resolve
        def resolve_asset(query, source):
            self.permissions.check('load_model', {'model':query})
            self.permissions.check('model_library', {'query':query})
            return resolve(self.state_dir/'models',query,source,before_web=lambda q:self.permissions.check('web_search',{'query':q}))
        return compose(edit,self.scene_dir,current=self.latest_scene,resolve=resolve_asset,description=description,
                       stop_event=self.stop_event,on_event=self.agent.on_event)

    def compose(self, edit):
        self.permissions.check('generate_scene', edit)
        self.viewer.ensure_installed()
        try: result=self.build_composition(edit,self.last_scene_request or '')
        except Exception as exc:
            self.scene_generation_error=str(exc);self.save_scene_state();raise
        return self.publish_scene(result)

    def publish_scene(self, result):
        self.scene_generation_error=None
        self.latest_scene=Path(result['scene'])
        self.save_scene_state()
        try:
            self.permissions.check('open_simulator',{})
            result['viewer']=self.viewer.open(self.latest_scene,force=True)
        except Exception as exc:
            result['viewer']={'window_open':False,'error':str(exc)}
        # Preserve exact evidence rather than only the model's conversation summary.
        report=Path(result.get('report',self.latest_scene.with_name('report.json')))
        if report.exists():
            data=json.loads(report.read_text());data['viewer']=result['viewer'];report.write_text(json.dumps(data,ensure_ascii=False,indent=2))
        return result

    def scheduled_tool(self, name, args):
        if name in SETTINGS_NAMES | SESSION_TASK_NAMES | USER_TOOL_NAMES | {"skill_run", "skill_export"}: raise ValueError("Scheduled tasks cannot manage session settings, tasks or executable Skills")
        if name in CARRIER_NAMES: raise ValueError("Scheduled carrier routing is not enabled")
        if name in TASK_NAMES: raise ValueError("Legacy foreground timers cannot submit persistent tasks; use task_runtime.json schedules")
        if name in {"compose_scene", "generate_scene", "simulator_control", "load_model", "node_start", "node_command", "node_stop", "open_serial", "read_serial", "close_serial", "open_simulator", "close_simulator"} or name not in {tool["function"]["name"] for tool in TOOLS}:
            raise ValueError("Scheduled tasks cannot call agent management tools")
        return self.tool(name, args)

    def apply_profiles(self, clear_history=True):
        with self.runtime.lock:
            if any(r["state"] in ("running", "queued") for r in self.runtime.records.values()):
                raise ValueError("Wait for or cancel running subagents before switching models")
            selected = self.providers.selected()
            snapshots = {slot: self.providers.get(name) for slot, name in selected.items()}
            for slot, section, client in (("master", "llm", self.client),):
                old = (client.config["base_url"], client.config["api_key_env"])
                if client.key:
                    self.key_cache[old] = client.key
                new = snapshots[slot]
                self.config[section] = new
                client.config = new
                client.key = self.key_cache.get((new["base_url"], new["api_key_env"]))
            self.config["expert"] = self.client.config
            if clear_history:
                self.agent.history.clear(); self.agent.turn_summaries.clear()
            return selected

    def switch_profile(self, slot, name):
        with self.runtime.lock:
            if any(r["state"] in ("running", "queued") for r in self.runtime.records.values()):
                raise ValueError("Wait for or cancel running subagents before switching models")
            self.providers.use(slot, name)
            return self.apply_profiles()

    @staticmethod
    def check_scheduled(text):
        text = ALIASES.get(text.strip(), text.strip())
        if text.startswith("/") and text not in ("/status", "/sim"):
            raise ValueError("Scheduled commands allow only chat, /status and /sim")
        if len(text) > 16000:
            raise ValueError("Task text is too long")
        return text

    def dispatch(self, text, scheduled=False, focus=None):
        text = ALIASES.get(text.strip(), text.strip())
        if text.rstrip('。.!！') in ('允许所有执行权限', '允许全部执行权限', '放开所有执行权限'):
            if scheduled:
                raise PermissionError('Scheduled tasks cannot change operator permissions')
            snapshot = self.permissions.allow_available_actions()
            return ('已允许当前已实现工具的全部执行权限，并切换到执行模式（sim）。'
                    '这不会自动运行工具或使能电机。电机控制还需要接入对应型号的驱动；'
                    '请提供电机或驱动板型号及连接方式，我会先核对官方SDK和协议，再完成接入。')
        if scheduled:
            text = self.check_scheduled(text)
        if not text:
            return ""
        selected = self.node_focus if focus is None else focus
        if not scheduled and text.split()[0] == '/carrier':
            from terminal.carriers import dispatch
            return dispatch(self, text.partition(' ')[2])
        if not scheduled and text.split()[0] == '/node':
            from terminal.nodes import dispatch
            return dispatch(self, text.partition(' ')[2])
        if not scheduled and selected != 'master':
            from terminal.nodes import focused_reply
            aliases = {'/status': 'status', '/joints': 'status', '/home': 'move 0 0'}
            node_text = aliases.get(text, 'move ' + text[6:] if text.startswith('/move ') else text)
            if not node_text.startswith('/'):
                return focused_reply(self, node_text)
        if not text.startswith("/"):
            # Timers retain isolated non-supervisor context and cannot spawn agents.
            agent = ChatAgent(self.client, TOOLS, self.scheduled_tool) if scheduled else self.agent
            return agent.reply(text)
        command, _, tail = text.partition(" ")
        if command == '/models':
            if tail.strip():
                raise ValueError('Usage: /models')
            return json.dumps(self.tool('model_library', {}), ensure_ascii=False)
        if command == '/model-load':
            args = {'model': tail.strip()}
            self.agent.on_event('tool', 'load_model(' + json.dumps(args) + ')')
            result = self.tool('load_model', args)
            self.agent.on_event('result', json.dumps(result, ensure_ascii=False))
            state = result['viewer']
            return (args['model'] + ': model verified; ' +
                    ('viewer open (paused).' if state.get('window_open') and state.get('paused') else
                     'viewer open.' if state.get('window_open') else 'window not open: ' + str(state.get('error'))) +
                    '\n' + result['scene'])
        if command == "/viewer":
            parts = shlex.split(tail)
            if not parts or parts[0] in ('status', 'stop'):
                if len(parts) > 1:
                    raise ValueError('Unexpected viewer arguments')
                name = {'': 'open_simulator', 'status': 'simulator_status', 'stop': 'close_simulator'}[parts[0] if parts else '']
                return json.dumps(self.tool(name, {}), ensure_ascii=False)
            action = parts[0]
            args = {'action': action}
            if action == 'step':
                if len(parts) > 2:
                    raise ValueError('Usage: /viewer step [N]')
                args['steps'] = int(parts[1]) if len(parts) == 2 else 1
            elif action == 'speed' and len(parts) == 2:
                args['value'] = float(parts[1])
            elif action == 'camera' and len(parts) == 2:
                args['view'] = parts[1]
            elif action == 'actuate':
                args['values'] = [float(value) for value in parts[1:]]
            elif len(parts) != 1:
                raise ValueError('Invalid viewer command')
            return json.dumps(self.tool('simulator_control', args), ensure_ascii=False)
        if command in CONTROL_COMMANDS:
            return operator_command(self, command, tail)
        if command == "/switch":
            parts = shlex.split(tail)
            if parts == ["setup"]:
                if not sys.stdin.isatty():
                    raise ValueError("Quick setup requires an interactive terminal")
                with self.runtime.lock:
                    if any(r["state"] in ("running", "queued") for r in self.runtime.records.values()):
                        raise ValueError("Wait for or cancel running subagents before setup")
                    if quick_setup(self.providers):
                        self.apply_profiles()
                        return "Setup applied."
                    return "Cancelled."
            if parts == ["list"]:
                return json.dumps(self.providers.list(), ensure_ascii=False)
            if parts == ["reload"]:
                return "Applied profiles and cleared conversation context: " + json.dumps(self.apply_profiles())
            slot = parts[0] if parts else "master"
            if slot not in ("master", "expert") or len(parts) > 2:
                raise ValueError("Usage: /switch master|expert [profile] or /switch list|reload")
            if len(parts) == 2:
                return "Switched and saved: " + json.dumps(self.switch_profile(slot, parts[1]))
            if not sys.stdin.isatty():
                raise ValueError("Specify a profile name for noninteractive calls")
            with self.runtime.lock:
                if any(r["state"] in ("running", "queued") for r in self.runtime.records.values()):
                    raise ValueError("Wait for or cancel running subagents first")
                name = choose_profile(self.providers, slot)
                if name:
                    self.apply_profiles()
                return "Switched: " + name if name else "Cancelled."
        if command == "/agents":
            if tail.strip() not in ('', 'active', 'all'):
                raise ValueError('Usage: /agents [active|all]')
            value = self.tool('agents_status', {})
            if tail.strip() == 'active':
                value['tasks'] = [row for row in value['tasks'] if row['state'] in ('running','queued')]
            return json.dumps(value, ensure_ascii=False)
        if command == "/spawn":
            role, _, task = tail.partition(" ")
            return json.dumps(self.tool("spawn_agent", {"role": role, "task": task}), ensure_ascii=False)
        if command == "/send":
            target, _, message = tail.partition(" ")
            if not message.strip():
                raise ValueError('Usage: /send TARGET message')
            agent_id = self.runtime.resolve(target)
            return json.dumps(self.tool('send_agent', {'agent_id':agent_id, 'message':message}), ensure_ascii=False)
        if command in ('/result', '/stop-agent', '/agent-messages'):
            agent_id = self.runtime.resolve(tail.strip())
            tool = {'/result':'agent_result', '/stop-agent':'cancel_agent', '/agent-messages':'agent_messages'}[command]
            return json.dumps(self.tool(tool, {'agent_id':agent_id}), ensure_ascii=False)
        if command == "/skills":
            from terminal.offline_skills import dispatch
            return dispatch(self, tail)
        if command in ("/help", "/shortcuts"):
            return HELP
        if command == "/status":
            return json.dumps(self.tool("status", {}), ensure_ascii=False)
        if command == "/sim":
            return json.dumps(self.tool("run_sim", {}), ensure_ascii=False)
        if command == "/scene":
            complex_task = tail.startswith("--complex ")
            description = tail[len("--complex "):] if complex_task else tail
            return json.dumps(self.scene(description, complex_task), ensure_ascii=False)
        if command == "/complex":
            return json.dumps(self.tool("expert_advice", {"description": tail}), ensure_ascii=False)
        if command in ("/key", "/expert-key"):
            args = shlex.split(tail)
            if args not in ([], ["save"]):
                raise ValueError("Usage: /key [save]")
            self.client.key = getpass.getpass("API key (save to disk): " if args else "API key (session only): ").strip()
            if args == ["save"]:
                save_key(self.client.config, self.client.key)
                return "API key saved in Loop ROS user home."
            return "API key set in memory." if self.client.key else "No key set."
        if command == "/model":
            if tail.strip():
                with self.runtime.lock:
                    if any(r['state'] in ('running', 'queued') for r in self.runtime.records.values()):
                        raise ValueError('Wait for or cancel running subagents before changing model')
                self.config["llm"]["model"] = tail.strip()
                self.client.config['model'] = tail.strip()
                self.agent.history.clear(); self.agent.turn_summaries.clear()
            return self.config["llm"]["model"]
        if command == '/fast':
            option = tail.strip().lower()
            if option not in ('', 'on', 'off', 'status'):
                raise ValueError('Usage: /fast [on|off|status]')
            if option != 'status':
                enabled = option == 'on' or (not option and self.client.request_service_tier != 'priority')
                self.client.request_service_tier = 'priority' if enabled else 'default'
            requested = self.client.request_service_tier or 'provider default'
            return ('Fast requested tier: ' + requested + '. Last response tier: '
                    + (self.client.last_service_tier or 'not confirmed')
                    + '. Applies to subsequent foreground requests; provider support is not guaranteed.')
        if command == "/clear":
            self.agent.history.clear(); self.agent.turn_summaries.clear()
            return "Conversation context cleared."
        if command == "/policy":
            parts = shlex.split(tail)
            if len(parts) != 2 or parts[0] not in ("pi05", "act") or parts[1] not in ("start", "stop", "status"):
                raise ValueError("Usage: /policy pi05|act start|stop|status")
            name, action = parts
            if action == "status":
                return self.services.status()[name]
            if action == "start" and not self.confirm("Start configured {} inference-only service (no hardware control)?".format(name)):
                return "Cancelled."
            if action == "start":
                return json.dumps(self.permissions.confirmed("policy_start", {"name": name}, self.tool))
            return json.dumps(getattr(self.services, action)(name))
        if command == '/task':
            if tail.strip():
                return json.dumps(self.tool('task_submit',{'goal':tail}),ensure_ascii=False)
            command = '/tasks'
        if command == '/trigger':
            return json.dumps(self.tool('task_signal',{'name':tail}),ensure_ascii=False)
        if command == '/tasks':
            from terminal.task_service import start,stop,policy_path
            from core.tasks import TaskStore
            parts=tail.split();action=parts[0] if parts else 'list'
            if action in ('list','all','start','stop','config') and len(parts)<=1:
                if action=='start': result=start(self)
                elif action=='stop': result=stop(self.state_dir)
                elif action=='config': result={'path':str(policy_path(self.state_dir)),'config':json.loads(policy_path(self.state_dir).read_text())}
                else: result=self.tool('task_status',{'scope':'all'} if action=='all' else {})
            elif action in ('status','cancel','resume') and len(parts)>=2:
                from terminal.task_tools import resolve_reference
                reference = tail[len(action):].strip()
                message = None
                if action == 'resume':
                    reference, separator, message = reference.partition(' -- ')
                    if not separator:
                        message = None
                        # Preserve existing /tasks resume ID MESSAGE scripts.
                        try:
                            TaskStore(self.state_dir/'tasks.sqlite').get(parts[1])
                        except ValueError:
                            pass
                        else:
                            reference = parts[1]
                            message = ' '.join(parts[2:]) or None
                identity = resolve_reference(self, reference)
                result=self.tool({'status':'task_status','cancel':'task_cancel','resume':'task_resume'}[action],{'task_id':identity,**({'message':message} if message else {})})
                if action=='status': result['history']=TaskStore(self.state_dir/'tasks.sqlite').history(identity)
            else: raise ValueError('Usage: /tasks [list|all|status TITLE|cancel TITLE|resume TITLE [-- MESSAGE]|start|stop|config]')
            return json.dumps(result,ensure_ascii=False)
        if command in ("/after", "/every"):
            seconds, sep, task = tail.partition(" ")
            if not sep:
                raise ValueError("Usage: /after seconds task or /every seconds task")
            job = self.scheduler.add(float(seconds), self.check_scheduled(task), command == "/every")
            return "Scheduled task {}. Runs while this terminal is open; API charges may apply.".format(job)
        if command == "/jobs":
            return json.dumps(self.scheduler.list(), ensure_ascii=False)
        if command == "/cancel":
            return "Cancelled {} pending task(s).".format(self.scheduler.cancel(int(tail)))
        raise ValueError("Unknown command. Type /help")

    def close(self):
        if hasattr(self, 'simulation_workbench'):
            self.simulation_workbench.close()
        try:
            self.nodes.close()
            self.runtime.close()
            self.viewer.close()
            self.serial.close()
            self.services.close()
        finally:
            self.scheduler.close()
            self.providers.close()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="loop", description="Loop ROS · Loop Robot Operating System", epilog="Updates: loop update --check | loop update | loop update --rollback")
    parser.add_argument("entry", nargs="?", choices=("ros", "robot", "node"), help="node opens the local process console without API setup; robot is a legacy alias")
    parser.add_argument("--version", action="version", version="Loop ROS " + VERSION)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--deployment", type=Path, help="Portable carrier manifest; never starts devices automatically")
    parser.add_argument("--host", help="Local host ID in the deployment")
    parser.add_argument("--once", help="Run one prompt or command without starting timers")
    args = parser.parse_args(argv)
    deployment = None
    if args.host and not args.deployment:
        parser.error('--host requires --deployment')
    if args.deployment:
        from core.deployment import Deployment
        from toolchain.node_workers import definitions
        try:
            deployment = Deployment.load(args.deployment, args.host)
            validate_bindings(deployment, definitions())
        except (OSError, ValueError, TypeError) as exc:
            parser.error(str(exc))
    if args.state_dir is None:
        args.state_dir = DEFAULT_STATE_DIR if deployment is None else DEFAULT_STATE_DIR / 'deployments' / deployment.deployment_id / deployment.host_id
    args.state_dir.mkdir(parents=True, exist_ok=True)
    with (args.state_dir / "terminal.lock").open("a+b") as lock:
        try:
            lock_terminal(lock)
        except BlockingIOError:
            parser.error("Another terminal is using this state directory")
        if deployment:
            from terminal.carriers import bind
            try:
                bind(args.state_dir, deployment)
            except (OSError, ValueError) as exc:
                parser.error(str(exc))
        app = App(load_config(args.config), args.state_dir)
        try:
            if args.once is not None:
                # A noninteractive call must never authorize process startup by itself.
                app.confirm = lambda message: False
                print(app.dispatch(args.once))
                return 0
            if args.entry == "node":
                from terminal.nodes import HELP as NODE_HELP
                print(NODE_HELP)
            if args.entry != "node" and not ensure_setup(app, sys.stdin.isatty()):
                print("Run loop again to configure access, or use --once for offline commands.")
                return 0
            if sys.stdin.isatty() and sys.stdout.isatty():
                from terminal.interactive import run
                run(app)
                return 0
            print(welcome(app.client.config["model"], app.expert.config["model"], app.permissions.snapshot()["mode"],
                          fast_status=getattr(app, 'startup_fast_status', None)))
            executor = ThreadPoolExecutor(max_workers=1)
            pending = None
            continuations = 0
            input_poller = InputPoller(sys.stdin)
            print("You > ", end="", flush=True)
            while True:
                app.runtime.poll()
                if pending is not None and pending.done():
                    try:
                        print("\nMaster > " + pending.result())
                    except Exception as exc:
                        print("\nMaster error: " + str(exc))
                    pending = None
                    print("You > ", end="", flush=True)
                with app.runtime.lock:
                    notifications, app.runtime.notifications = app.runtime.notifications, []
                    has_mail = bool(app.runtime.mail)
                for event in notifications:
                    print("\n[{} {}] {} · {}".format(event["role"], event.get("reference", ""), event.get("title", "Agent"), event["state"]), flush=True)
                if pending is None and has_mail and continuations < 8:
                    continuations += 1
                    pending = executor.submit(app.agent.reply, "请处理新到达的子任务消息，依据证据继续协调或汇总。")
                result = None if pending else app.scheduler.tick(lambda command: app.dispatch(command, scheduled=True))
                if result:
                    print("\n[Scheduled task {}] {}\nYou > ".format(*result), end="", flush=True)
                line = input_poller.poll()
                if line is None:
                    continue
                if not line or line.strip() in ("/exit", "/quit"):
                    break
                try:
                    if not line.strip().startswith("/") and line.strip() not in ALIASES:
                        if app.node_focus != "master":
                            print("Node > " + app.dispatch(line))
                        elif pending:
                            print("Master is working. Use /agents, /send or /stop-agent to manage tasks.")
                        else:
                            continuations = 0
                            pending = executor.submit(app.dispatch, line, focus="master")
                    elif pending and line.split()[0] not in ("/node", "/agents", "/spawn", "/send", "/result", "/agent-messages", "/stop-agent", "/help", "/stop", "/permissions", "/requests", "/mode", "/plan"):
                        print("Master is busy; only task management, permissions, stop and help are available.")
                    else:
                        print("Master > " + app.dispatch(line))
                except Exception as exc:
                    print("Error: " + str(exc))
                print("You > ", end="", flush=True)
        except KeyboardInterrupt:
            print("\nInterrupted. Closing owned services and subagents.")
        finally:
            if "executor" in locals():
                app.stop_event.set()
                app.nodes.close()
                app.runtime.close()
                executor.shutdown(wait=True)
            app.close()
    return 0
