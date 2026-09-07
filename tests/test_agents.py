import json
from pathlib import Path
import tempfile
import time
import unittest

from terminal.agents import AgentRuntime, agent_worker
from terminal.config import ROOT, load_config
from terminal.llm import QwenClient


def fake_worker(pipe, definition, config, key, task, schemas):
    if task == "wait":
        time.sleep(30)
    elif task == "mail":
        pipe.send({"type": "inbox"})
        value = pipe.recv()["messages"]
        pipe.send({"type": "result", "result": json.dumps(value)})
    elif task == "forbidden":
        pipe.send({"type": "tool", "name": "shell", "arguments": {}})
        pipe.send({"type": "result", "result": json.dumps(pipe.recv())})
    elif task == "tool":
        pipe.send({"type": "tool", "name": "run_sim", "arguments": {}})
        pipe.send({"type": "result", "result": json.dumps(pipe.recv())})
    elif task == "crash":
        pipe.close()
    else:
        pipe.send({"type": "result", "result": task})
    pipe.close()


def offline_agent_worker(*args):
    from unittest.mock import patch
    with patch("terminal.llm.QwenClient.complete", return_value={"content": "离线上下文回复"}):
        agent_worker(*args)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        config = load_config()
        clients = {key: QwenClient(config[key]) for key in ("llm", "expert")}
        definitions = AgentRuntime.load_definitions(ROOT / "configs/agents.json", {"run_sim", "generate_scene"})
        self.called = []
        def dispatch(name, args):
            self.called.append(name)
            return {"review": "pass"}
        self.runtime = AgentRuntime(definitions, clients, [], dispatch,
            Path(self.temp.name) / "events.jsonl", worker_target=fake_worker)

    def tearDown(self):
        self.runtime.close()
        self.temp.cleanup()

    def wait_result(self, agent_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.runtime.poll()
            result = self.runtime.result(agent_id)
            if result["state"] != "running":
                return result
            time.sleep(0.01)
        self.fail("worker timed out in test")

    def test_parallel_contexts_and_results(self):
        a = self.runtime.spawn("Planner", "first")["agent_id"]
        b = self.runtime.spawn("Reviewer", "second")["agent_id"]
        self.assertNotEqual(self.runtime.records[a]["process"].pid, self.runtime.records[b]["process"].pid)
        self.assertEqual(self.wait_result(a)["result"], "first")
        self.assertEqual(self.wait_result(b)["result"], "second")
        self.assertEqual(len(self.runtime.inbox()), 2)
        self.assertEqual(self.runtime.inbox(), [])

    def test_mail_delivery(self):
        a = self.runtime.spawn("Planner", "mail")["agent_id"]
        self.runtime.send(a, "补充约束")
        self.assertIn("补充约束", json.loads(self.wait_result(a)["result"])[0])

    def test_cancel_and_concurrency_limit(self):
        ids = [self.runtime.spawn("Planner", "wait")["agent_id"] for _ in range(3)]
        with self.assertRaises(RuntimeError):
            self.runtime.spawn("Planner", "excess")
        self.runtime.cancel(ids[0])
        self.assertEqual(self.runtime.result(ids[0])["state"], "cancelled")
        self.assertFalse(self.runtime.records[ids[0]]["process"].is_alive())

    def test_permissions_enforced_in_broker(self):
        a = self.runtime.spawn("Reviewer", "tool")["agent_id"]
        self.assertIn("error", self.wait_result(a)["result"])
        self.assertEqual(self.called, [])
        b = self.runtime.spawn("Worker", "tool")["agent_id"]
        self.assertIn("pass", self.wait_result(b)["result"])
        self.assertEqual(self.called, ["run_sim"])

    def test_crash_and_timeout(self):
        a = self.runtime.spawn("Planner", "crash")["agent_id"]
        self.assertEqual(self.wait_result(a)["state"], "failed")
        b = self.runtime.spawn("Planner", "wait")["agent_id"]
        self.runtime.records[b]["started"] -= 181
        self.runtime.poll()
        self.assertEqual(self.runtime.result(b)["state"], "timed_out")

    def test_registry_and_closed_runtime(self):
        self.runtime.worker_target = offline_agent_worker
        agent_id = self.runtime.spawn("Planner", "验证真正的worker握手")["agent_id"]
        self.assertEqual(self.wait_result(agent_id)["result"], "离线上下文回复")
        with self.assertRaises(ValueError):
            self.runtime.spawn("Master", "nested supervisor")
        self.runtime.close()
        with self.assertRaises(RuntimeError):
            self.runtime.spawn("Planner", "after close")


if __name__ == "__main__":
    unittest.main()
