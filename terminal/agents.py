"""Small process supervisor and broker, inspired by pi's subagent extension.

Independent contexts, explicit tool grants, bounded mailboxes; not an OS sandbox.
"""
import json
import multiprocessing
from pathlib import Path
import re
import threading
import time
import uuid

from terminal.llm import ChatAgent, QwenClient

def _schema(name, description, fields):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": {k: {"type": "string"} for k in fields},
                           "required": fields, "additionalProperties": False}}}


AGENT_TOOLS = [
    _schema("spawn_agent", "非阻塞启动已注册角色的独立进程；多个独立任务可连续启动并行运行", ["role", "task"]),
    _schema("agents_status", "查看角色、并发容量和子任务状态；子Agent可发现自己的ID和运行中同伴", []),
    _schema("agent_result", "读取子任务状态及结果，不阻塞等待", ["agent_id"]),
    _schema("send_agent", "发送补充信息到运行中子任务", ["agent_id", "message"]),
    _schema("cancel_agent", "取消子任务，不回滚已经完成的工具效果", ["agent_id"]),
]


def agent_worker(connection, definition, config, key, task, schemas):
    from release_runtime import runtime_session
    with runtime_session():
        _agent_worker(connection, definition, config, key, task, schemas)


def _agent_worker(connection, definition, config, key, task, schemas):
    client = QwenClient(config)
    client.key = key
    def inbox():
        connection.send({"type": "inbox"})
        return connection.recv()["messages"]

    def dispatch(name, arguments):
        connection.send({"type": "tool", "name": name, "arguments": arguments})
        while True:
            item = connection.recv()
            if item["type"] == "tool_result":
                return item["result"]

    try:
        identity = definition.get("agent_id")
        prompt = definition["prompt"]
        if identity:
            prompt += ("\nRuntime identity: " + identity +
                       ". Use agents_status to discover running peers and send_agent to send task data. "
                       "Messages are delivered at model boundaries, not proof of task completion. "
                       "You cannot spawn or cancel other agents.")
        agent = ChatAgent(client, schemas, dispatch, prompt, inbox)
        result = agent.reply(task)
        # If mail arrived during the last API call, process it before completion.
        for _ in range(2):
            extra = inbox()
            if not extra:
                break
            result = agent.reply("补充任务消息：\n" + "\n".join(extra))
        connection.send({"type": "result", "result": result})
    except Exception as exc:
        connection.send({"type": "error", "error": type(exc).__name__ + (": " + str(exc)[:1000] if isinstance(exc,(ValueError,RuntimeError,PermissionError)) else "")})
    finally:
        connection.close()


class AgentRuntime:
    def __init__(self, definitions, clients, schemas, dispatch, event_path, max_workers=3,
                 timeout_s=180, worker_target=agent_worker):
        self.definitions = definitions
        self.clients, self.schemas, self.dispatch = clients, schemas, dispatch
        self.event_path = Path(event_path)
        self.event_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_workers, self.timeout_s = max_workers, timeout_s
        self.worker_target = worker_target
        self.before_tool = None
        self.after_tool = None
        self.records, self.mail, self.notifications = {}, [], []
        self.closed = False
        self.lock = threading.RLock()
        self.context = multiprocessing.get_context("spawn")

    @staticmethod
    def load_definitions(path, allowed_tools):
        specs = json.loads(Path(path).read_text())
        if not isinstance(specs, dict) or len(specs) > 20:
            raise ValueError("invalid agent registry")
        for name, spec in specs.items():
            if (not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", name) or name == "Master"
                    or set(spec) != {"provider", "tools", "prompt"}
                    or spec["provider"] not in ("llm", "expert")
                    or not isinstance(spec["tools"], list)
                    or not set(spec["tools"]).issubset(allowed_tools)
                    or not isinstance(spec["prompt"], str) or len(spec["prompt"]) > 8000):
                raise ValueError("invalid agent definition: " + name)
        return specs

    def _event(self, kind, agent_id, **data):
        with self.event_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": time.time(), "kind": kind, "agent_id": agent_id, **data},
                                    ensure_ascii=False) + "\n")

    def spawn(self, role, task):
        with self.lock:
            if self.closed:
                raise RuntimeError("agent runtime closed")
            if role not in self.definitions or not isinstance(task, str) or not 1 <= len(task) <= 16000:
                raise ValueError("unknown role or invalid task")
            self.poll()
            if sum(r["state"] == "running" for r in self.records.values()) >= self.max_workers:
                raise RuntimeError("子 Agent 并发上限已达{}；等待结果或取消任务".format(self.max_workers))
            if len(self.records) >= 100:
                raise RuntimeError("本会话子任务预算已达100")
            definition = self.definitions[role]
            client = self.clients[definition["provider"]]
            key = client.resolved_key()
            parent, child = self.context.Pipe()
            agent_id = uuid.uuid4().hex[:12]
            schemas = [s for s in self.schemas if s["function"]["name"] in definition["tools"]
                       and s["function"]["name"] not in {t["function"]["name"] for t in AGENT_TOOLS}]
            schemas += [s for s in AGENT_TOOLS if s["function"]["name"] in ("send_agent", "agents_status")]
            worker_definition = {**definition, "agent_id": agent_id}
            process = self.context.Process(target=self.worker_target,
                args=(child, worker_definition, dict(client.config), key, task, schemas), daemon=True)
            try:
                process.start()
            except BaseException:
                parent.close()
                child.close()
                raise
            child.close()
            self.records[agent_id] = {"role": role, "state": "running", "result": None,
                "process": process, "pipe": parent, "started": time.monotonic(),
                "tools": list(definition["tools"]), "messages": 0, "pending": []}
            self._event("spawn", agent_id, role=role, task=task)
            return {"agent_id": agent_id, "role": role, "state": "running"}

    def _finish(self, agent_id, state, result):
        record = self.records[agent_id]
        record.update(state=state, result=result)
        process = record["process"]
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
        record["pipe"].close()
        event = {"agent_id": agent_id, "role": record["role"], "state": state, "result": result}
        self._event("finish", agent_id, state=state, result=result)
        self.mail.append(json.dumps(event, ensure_ascii=False))
        self.notifications.append(event)

    def send(self, agent_id, message, sender="Master"):
        with self.lock:
            if agent_id not in self.records:
                raise ValueError("unknown agent ID")
            record = self.records[agent_id]
            if record["state"] != "running" or not isinstance(message, str) or not 1 <= len(message) <= 2000:
                raise ValueError("agent not running or message invalid")
            if record["messages"] >= 16:
                raise RuntimeError("任务消息预算耗尽")
            record["pending"].append(sender + ": " + message)
            record["messages"] += 1
            self._event("message", agent_id, sender=sender, text=message)
            return {"state": "queued", "delivery": "next model boundary"}

    def cancel(self, agent_id):
        with self.lock:
            if self.records[agent_id]["state"] == "running":
                self._finish(agent_id, "cancelled", "取消不回滚已执行工具")
            return self.result(agent_id)

    def result(self, agent_id):
        with self.lock:
            record = self.records[agent_id]
            return {"agent_id": agent_id, **{k: record[k] for k in ("role", "state", "result")}}

    def poll(self):
        with self.lock:
            for agent_id, record in list(self.records.items()):
                if record["state"] != "running":
                    continue
                if time.monotonic() - record["started"] > self.timeout_s:
                    self._finish(agent_id, "timed_out", "agent time budget exceeded")
                    continue
                pipe = record["pipe"]
                try:
                    while pipe.poll():
                        item = pipe.recv()
                        if item["type"] == "inbox":
                            pipe.send({"messages": record["pending"]})
                            record["pending"] = []
                            continue
                        if item["type"] in ("result", "error"):
                            self._finish(agent_id, "done" if item["type"] == "result" else "failed",
                                         str(item.get("result", item.get("error")))[:12000])
                            break
                        if item["type"] == "tool":
                            name, args = item["name"], item["arguments"]
                            try:
                                if self.before_tool: self.before_tool(agent_id,name,args)
                                if name == "send_agent":
                                    if not isinstance(args, dict) or set(args) != {"agent_id", "message"}:
                                        raise ValueError("agent_id and message required; sender is assigned by broker")
                                    value = self.send(sender=agent_id, **args)
                                elif name == "agents_status":
                                    if args != {}:
                                        raise ValueError("no arguments expected")
                                    value = {"self_id": agent_id, "peers": [
                                        {"agent_id": identity, "role": peer["role"], "state": peer["state"]}
                                        for identity, peer in self.records.items() if peer["state"] == "running"]}
                                elif name in record["tools"] and name not in {t["function"]["name"] for t in AGENT_TOOLS}:
                                    value = self.dispatch(name, args)
                                else:
                                    raise ValueError("tool permission denied")
                            except Exception as exc:
                                value = {"error": type(exc).__name__}
                                if isinstance(exc, (ValueError, RuntimeError, PermissionError)):
                                    value["message"] = str(exc)[:2000]
                            if self.after_tool: self.after_tool(agent_id,name,args,value)
                            self._event("tool", agent_id, tool=name, result=value)
                            pipe.send({"type": "tool_result", "result": value})
                except (EOFError, BrokenPipeError, OSError):
                    if record["state"] == "running":
                        self._finish(agent_id, "failed", "worker disconnected")
                if record["state"] == "running" and not record["process"].is_alive():
                    self._finish(agent_id, "failed", "worker exited without result")

    def inbox(self):
        self.poll()
        with self.lock:
            messages, self.mail = self.mail, []
            return messages

    def status(self):
        with self.lock:
            return {"Master": "conversation entry", "roles": list(self.definitions),
                    "max_workers": self.max_workers,
                    "running": sum(r["state"] == "running" for r in self.records.values()),
                    "tasks": [self.result(k) for k in self.records]}

    def close(self):
        with self.lock:
            self.closed = True
            for agent_id in self.records:
                self.cancel(agent_id)
