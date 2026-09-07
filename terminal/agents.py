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


ALLOWED_AGENT_TOOLS = {"run_sim", "generate_scene", "read_file", "list_files", "search_files"}

AGENT_TOOLS = [
    _schema("spawn_agent", "提交已注册角色的独立子任务；资源足够时并行启动，否则排队。用 agents_status 查看资源和等待原因", ["role", "task"]),
    _schema("agents_status", "查看角色、并发容量和子任务状态；子Agent可发现自己的ID和运行中同伴", []),
    _schema("agent_messages", "Inspect received task messages and worker-delivery receipts; delivery is not task completion", ["agent_id"]),
    _schema("agent_result", "读取子任务状态及结果，不阻塞等待", ["agent_id"]),
    _schema("send_agent", "发送补充信息到运行中或排队子任务", ["agent_id", "message"]),
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
                       "Use agent_result to read findings from known peers; their prose is not execution evidence. "
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


from core.resources import ResourceBusy


class AgentRuntime:
    def __init__(self, definitions, clients, schemas, dispatch, event_path, max_workers=3,
                 timeout_s=180, worker_target=agent_worker, admission=None):
        self.definitions = definitions
        self.clients, self.schemas, self.dispatch = clients, schemas, dispatch
        self.event_path = Path(event_path)
        self.event_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_workers, self.timeout_s = max_workers, timeout_s
        self.admission = admission
        self.before_start = None
        self.worker_target = worker_target
        self.before_tool = None
        self.after_tool = None
        self.records, self.mail, self.notifications = {}, [], []
        self.closed = False
        self.next_sequence = 1
        self.choice_cache = ()
        self.lock = threading.RLock()
        self.context = multiprocessing.get_context("spawn")

    @staticmethod
    def load_definitions(path, allowed_tools):
        specs = json.loads(Path(path).read_text())
        if not isinstance(specs, dict) or len(specs) > 20:
            raise ValueError("invalid agent registry")
        for name, spec in specs.items():
            if (not isinstance(spec, dict) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", name) or name == "Master"
                    or set(spec) != {"provider", "tools", "prompt"}
                    or spec["provider"] not in ("llm", "expert")
                    or not isinstance(spec["tools"], list)
                    or not all(isinstance(tool, str) for tool in spec["tools"])
                    or not set(spec["tools"]).issubset(allowed_tools)
                    or not isinstance(spec["prompt"], str) or len(spec["prompt"]) > 8000):
                raise ValueError("invalid agent definition: " + name)
        return specs

    def _event(self, kind, agent_id, **data):
        with self.event_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": time.time(), "kind": kind, "agent_id": agent_id, **data},
                                    ensure_ascii=False) + "\n")

    def spawn(self, role, task, queue_if_busy=True):
        with self.lock:
            if self.closed:
                raise RuntimeError("agent runtime closed")
            if role not in self.definitions or not isinstance(task, str) or not 1 <= len(task) <= 16000:
                raise ValueError("unknown role or invalid task")
            self.poll()
            if len(self.records) >= 4096:
                raise RuntimeError("Session agent record budget reached (4096)")
            agent_id = uuid.uuid4().hex[:12]
            from terminal.titles import excerpt
            record = {"reference": "@" + str(self.next_sequence), "title": excerpt(task, 48),
                      "message_log": [], "delivered": 0, "role": role, "task": task, "state": "queued", "result": None,
                      "process": None, "pipe": None, "lease": None, "started": None,
                      "tools": list(self.definitions[role]["tools"]), "messages": 0, "pending": []}
            self.next_sequence += 1
            self.records[agent_id] = record
            try:
                started = self._start(agent_id)
                if not started and (self.admission is None or not queue_if_busy):
                    raise ResourceBusy(record.get("waiting_reason", "Agent concurrency limit reached"))
            except BaseException:
                # A logging failure after launch must not orphan the process.
                if record["state"] != "running":
                    self.records.pop(agent_id, None)
                raise
            if not started:
                self._event("queued", agent_id, role=role, reason=record["waiting_reason"])
            self._refresh_choices()
            return {"agent_id": agent_id, "reference": record["reference"], "title": record["title"], "role": role, "state": record["state"],
                    **({"waiting_reason": record["waiting_reason"]} if not started else {})}

    def _start(self, agent_id):
        record = self.records[agent_id]
        if sum(r["state"] == "running" for r in self.records.values()) >= self.max_workers:
            record["waiting_reason"] = "Agent concurrency limit reached"
            return False
        token = self.admission.inspect(acquire=True) if self.admission else None
        if self.admission and token is None:
            record["waiting_reason"] = self.admission.last["reason"]
            return False
        parent = child = process = None
        try:
            if self.before_start:
                self.before_start(record["role"], record["task"])
            definition = self.definitions[record["role"]]
            client = self.clients[definition["provider"]]
            key = client.resolved_key()
            parent, child = self.context.Pipe()
            schemas = [s for s in self.schemas if s["function"]["name"] in definition["tools"]
                       and s["function"]["name"] not in {t["function"]["name"] for t in AGENT_TOOLS}]
            schemas += [s for s in AGENT_TOOLS if s["function"]["name"] in ("send_agent", "agents_status", "agent_result")]
            process = self.context.Process(target=self.worker_target,
                args=(child, {**definition, "agent_id": agent_id}, dict(client.config), key,
                      record["task"], schemas), daemon=True)
            process.start()
            if token: self.admission.bind(token, process.pid)
        except BaseException:
            if process is not None and process.pid is not None:
                if process.is_alive(): process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1)
            if parent is not None: parent.close()
            if child is not None: child.close()
            if token: self.admission.release(token)
            raise
        child.close()
        record.update(state="running", process=process, pipe=parent, lease=token,
                      started=time.monotonic())
        record.pop("waiting_reason", None)
        self._refresh_choices()
        self._event("spawn", agent_id, role=record["role"], task=record.pop("task"))
        return True

    def _finish(self, agent_id, state, result):
        record = self.records[agent_id]
        record.update(state=state, result=result)
        process = record["process"]
        if process is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            record["pipe"].close()
        if record.get("lease"):
            self.admission.release(record.pop("lease"))
        record.pop("task", None)
        record.pop("waiting_reason", None)
        for message in record["message_log"]:
            if message["delivery"] == "queued":
                message["delivery"] = "not_delivered"
        record["pending"] = []
        self._refresh_choices()
        event = {"agent_id": agent_id, "reference": record["reference"], "title": record["title"], "role": record["role"], "state": state, "result": result}
        self._event("finish", agent_id, state=state, result=result)
        self.mail.append(json.dumps(event, ensure_ascii=False))
        self.notifications.append(event)

    def send(self, agent_id, message, sender="Master"):
        with self.lock:
            if agent_id not in self.records:
                raise ValueError("unknown agent ID")
            record = self.records[agent_id]
            if record["state"] not in ("running", "queued") or not isinstance(message, str) or not 1 <= len(message) <= 2000:
                raise ValueError("agent not running or message invalid")
            if record["messages"] >= 16:
                raise RuntimeError("任务消息预算耗尽")
            record["pending"].append(sender + ": " + message)
            record["messages"] += 1
            message_id = record["reference"] + ":" + str(record["messages"])
            record["message_log"].append({"message_id": message_id, "sender": sender, "message": message,
                                          "delivery": "queued", "sent_at": time.time()})
            self._event("message", agent_id, sender=sender, text=message)
            return {"state": "queued", "delivery": "next model boundary", "message_id": message_id,
                    "reference": record["reference"], "title": record["title"]}

    def cancel(self, agent_id):
        with self.lock:
            if self.records[agent_id]["state"] in ("running", "queued"):
                self._finish(agent_id, "cancelled", "取消不回滚已执行工具")
            return self.result(agent_id)

    def result(self, agent_id):
        with self.lock:
            record = self.records[agent_id]
            return {"agent_id": agent_id, **{k: record[k] for k in ("reference", "title", "role", "state", "result")},
                    "messages_queued": sum(m["delivery"] == "queued" for m in record["message_log"]),
                    "messages_delivered": record["delivered"],
                    **({"waiting_reason": record["waiting_reason"]} if "waiting_reason" in record else {})}

    def _refresh_choices(self):
        # Immutable snapshots let completion render without waiting for a long tool lock.
        self.choice_cache = tuple({"agent_id": identity, **{k: record[k] for k in
                                  ("reference", "title", "role", "state")},
                                  **({"waiting_reason": record["waiting_reason"]} if "waiting_reason" in record else {})}
                                  for identity, record in self.records.items())

    def choices(self):
        return [dict(row) for row in self.choice_cache]

    def resolve(self, reference):
        with self.lock:
            if reference in self.records:
                return reference
            matches = [identity for identity, record in self.records.items()
                       if reference in (record['reference'], record['title'])]
            if len(matches) == 1:
                return matches[0]
            raise ValueError('Unknown or ambiguous agent. Choose a stable @number from /agents.')

    def messages(self, agent_id):
        with self.lock:
            record = self.records[agent_id]
            return {'reference': record['reference'], 'title': record['title'],
                    'messages': [{**message, 'sender_label': (self.records[message['sender']]['reference'] + ' ' +
                        self.records[message['sender']]['title']) if message['sender'] in self.records else message['sender']}
                        for message in record['message_log']],
                    'notice': 'Delivered means handed to the worker inbox, not model processing or completion.'}

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
                    for _ in range(16):
                        if not pipe.poll():
                            break
                        item = pipe.recv()
                        if not isinstance(item, dict) or not isinstance(item.get("type"), str) or item["type"] not in {"inbox", "result", "error", "tool"}:
                            self._finish(agent_id, "failed", "invalid worker protocol message")
                            break
                        if item["type"] == "inbox":
                            pipe.send({"messages": record["pending"]})
                            record["pending"] = []
                            for entry in record["message_log"]:
                                if entry["delivery"] == "queued":
                                    entry.update(delivery="delivered", delivered_at=time.time())
                                    record["delivered"] += 1
                            continue
                        if item["type"] in ("result", "error"):
                            if not isinstance(item.get(item["type"]), str):
                                self._finish(agent_id, "failed", "invalid worker result")
                                break
                            self._finish(agent_id, "done" if item["type"] == "result" else "failed",
                                         str(item.get("result", item.get("error")))[:12000])
                            break
                        if item["type"] == "tool":
                            name, args = item.get("name"), item.get("arguments")
                            if not isinstance(name, str) or not isinstance(args, dict):
                                self._finish(agent_id, "failed", "invalid worker tool request")
                                break
                            try:
                                if self.before_tool: self.before_tool(agent_id,name,args)
                                if name == "send_agent":
                                    if not isinstance(args, dict) or set(args) != {"agent_id", "message"}:
                                        raise ValueError("agent_id and message required; sender is assigned by broker")
                                    value = self.send(sender=agent_id, **args)
                                elif name == "agent_result":
                                    if set(args) != {"agent_id"}:
                                        raise ValueError("agent_id required")
                                    value = self.result(args["agent_id"])
                                elif name == "agents_status":
                                    if args != {}:
                                        raise ValueError("no arguments expected")
                                    value = {"self_id": agent_id, "peers": [
                                        {"agent_id": identity, "reference": peer["reference"], "title": peer["title"], "role": peer["role"], "state": peer["state"]}
                                        for identity, peer in self.records.items() if peer["state"] == "running"]}
                                elif name in record["tools"] and name not in {t["function"]["name"] for t in AGENT_TOOLS}:
                                    value = self.dispatch(name, args)
                                else:
                                    raise ValueError("tool permission denied")
                            except Exception as exc:
                                value = {"error": type(exc).__name__}
                                if isinstance(exc, (ValueError, RuntimeError, PermissionError)):
                                    value["message"] = str(exc)[:2000]
                            if self.after_tool:
                                try:
                                    self.after_tool(agent_id,name,args,value)
                                except Exception as exc:
                                    value = {"result": value, "observer_error": type(exc).__name__,
                                             "notice": "Tool may have completed; do not blindly retry."}
                            self._event("tool", agent_id, tool=name, result=value)
                            pipe.send({"type": "tool_result", "result": value})
                except (EOFError, BrokenPipeError, OSError):
                    if record["state"] == "running":
                        self._finish(agent_id, "failed", "worker disconnected")
                if record["state"] == "running" and not record["process"].is_alive() and not pipe.poll():
                    self._finish(agent_id, "failed", "worker exited without result")

            if not self.closed:
                for agent_id, record in list(self.records.items()):
                    if record["state"] == "queued":
                        try:
                            if not self._start(agent_id):
                                break
                        except Exception as exc:
                            self._finish(agent_id, "failed", str(exc)[:2000])

    def poll_notifications(self):
        """Collect UI notifications off the event loop, including broker lock waits."""
        self.poll()
        with self.lock:
            notifications, self.notifications = self.notifications, []
            return notifications, bool(self.mail)

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
                    "queued": sum(r["state"] == "queued" for r in self.records.values()),
                    "execution": {"agents": "spawn processes", "broker_tools": "serial", "ipc_batch_limit": 16},
                    "resources": self.admission.status() if self.admission else None,
                    "tasks": [self.result(k) for k in self.records]}

    def close(self):
        with self.lock:
            self.closed = True
            for agent_id in self.records:
                self.cancel(agent_id)
