import io
import os
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from terminal.app import App
from terminal.config import load_config, ROOT
from terminal.llm import ChatAgent, QwenClient
from terminal.scheduler import Scheduler
from terminal.services import PolicyServices


class TerminalTests(unittest.TestCase):
    def test_config_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ,{"LOOP_HOME":root}):
                config = load_config(Path(root) / "missing")
        self.assertEqual(config["llm"]["model"], "qwen-plus")
        self.assertEqual(config["services"]["act"]["argv"], [])

    def test_qwen_transport(self):
        client = QwenClient(json.loads((ROOT / "configs/config.example.json").read_text())["llm"])
        client.key = "test-only"
        response = io.BytesIO(json.dumps({"choices": [{"message": {"role": "assistant", "content": "你好"}}]}).encode())
        with patch("terminal.llm.build_opener") as opener:
            opener.return_value.open.return_value = response
            self.assertEqual(client.complete([{"role": "user", "content": "hi"}], [])["content"], "你好")
            request = opener.return_value.open.call_args[0][0]
            self.assertTrue(request.full_url.endswith("/chat/completions"))
            self.assertEqual(json.loads(request.data)["model"], "qwen-plus")

    def test_tool_feedback_to_model(self):
        class Client:
            def __init__(self):
                self.calls = 0
            def complete(self, messages, tools):
                self.calls += 1
                if self.calls == 1:
                    return {"role": "assistant", "tool_calls": [{"id": "1", "type": "function",
                             "function": {"name": "status", "arguments": "{}"}}]}
                assert messages[-1]["role"] == "tool"
                return {"content": "已检查"}
        agent = ChatAgent(Client(), [], lambda name, args: {"act": "STOPPED"})
        self.assertEqual(agent.reply("检查"), "已检查")
        self.assertEqual(len(agent.history), 2)

    def test_final_tool_result_can_be_summarized(self):
        class Client:
            calls = 0
            def complete(self, messages, tools):
                self.calls += 1
                if self.calls <= 4:
                    return {"tool_calls": [{"id": str(self.calls), "function": {"name": "status", "arguments": "{}"}}]}
                assert not tools
                assert any(m.get("role") == "tool" and 'ready' in m['content'] for m in messages)
                return {"content": "已验证"}
        agent = ChatAgent(Client(), [{'type': 'function'}], lambda *args: {'ready': True})
        self.assertEqual(agent.reply('完成检查'), '已验证')

    def test_scene_failure_details_reach_master(self):
        from toolchain.scenes import SceneGenerationError
        class Client:
            calls = 0
            def complete(self, messages, tools):
                self.calls += 1
                if self.calls == 1:
                    return {"tool_calls": [{"id": "1", "function": {"name": "generate_scene", "arguments": "{}"}}]}
                failure = json.loads(messages[-1]['content'])
                assert failure['stage'] == 'scene_json'
                assert failure['message'] == 'Expected objects field'
                assert not failure['retryable']
                return {"content": "场景JSON未通过校验"}
        def fail(*args):
            raise SceneGenerationError({'error': 'scene_generation_failed', 'message': 'Expected objects field',
                                        'stage': 'scene_json', 'retryable': False})
        self.assertEqual(ChatAgent(Client(), [], fail).reply('方块'), '场景JSON未通过校验')

    def test_identical_terminal_failure_is_not_executed_twice(self):
        class Client:
            calls = 0
            def complete(self, messages, tools):
                self.calls += 1
                if self.calls < 3:
                    return {"tool_calls": [{"id": str(self.calls), "function": {"name": "expert_advice", "arguments": "{}"}}]}
                receipt = next(m for m in reversed(messages) if m.get('role') == 'tool')
                assert json.loads(receipt['content'])['repeated_request_skipped']
                return {"content": "专家接口不可用"}
        with patch('builtins.input'):
            from unittest.mock import Mock
            dispatch = Mock(side_effect=RuntimeError('Missing expert key'))
            self.assertEqual(ChatAgent(Client(), [], dispatch).reply('检查'), '专家接口不可用')
            dispatch.assert_called_once()

    def test_tool_loop_bounded(self):
        class Client:
            def complete(self, messages, tools):
                return {"tool_calls": [{"id": "1", "type": "function",
                         "function": {"name": "status", "arguments": "{}"}}]}
        with self.assertRaises(RuntimeError):
            ChatAgent(Client(), [], lambda n, a: {}).reply("继续")

    def test_timers_run_once_and_cancel(self):
        scheduler = Scheduler(":memory:")
        try:
            job = scheduler.add(10, "/status")
            with patch("terminal.scheduler.time.time", return_value=time.time() + 20):
                self.assertEqual(scheduler.tick(lambda text: "ok"), (job, "ok"))
                self.assertIsNone(scheduler.tick(lambda text: "duplicate"))
            second = scheduler.add(10, "hello", repeat=True)
            self.assertEqual(scheduler.cancel(second), 1)
        finally:
            scheduler.close()

    def test_timer_failure_is_not_retried(self):
        scheduler = Scheduler(":memory:")
        try:
            scheduler.add(1, "hello", repeat=True)
            def fail(text):
                raise RuntimeError("error")
            with patch("terminal.scheduler.time.time", return_value=time.time() + 5):
                scheduler.tick(fail)
                self.assertEqual(scheduler.list()[0][4], "failed")
        finally:
            scheduler.close()

    def test_commands_and_scheduled_boundaries(self):
        with tempfile.TemporaryDirectory() as root:
            app = App(load_config(), root, confirm=lambda message: False)
            try:
                self.assertIn("NOT_CONFIGURED", app.dispatch("/status"))
                self.assertIn("Cancelled", app.dispatch("开始ACT推理"))
                for command in ("/policy act start", "开始PI推理", "/key", "/every 1 hi"):
                    with self.assertRaises(ValueError):
                        app.dispatch(command, scheduled=True)
                with self.assertRaises(ValueError):
                    app.tool("shell", {})
                with self.assertRaises(ValueError):
                    app.scheduled_tool("spawn_agent", {"role": "Planner", "task": "bypass"})
                self.assertIn("Scheduled task", app.dispatch("/after 10 /status"))
            finally:
                app.close()

    def test_owned_policy_process_lifecycle(self):
        with tempfile.TemporaryDirectory() as root:
            specs = {n: {"argv": [sys.executable, "-c", "import time; time.sleep(20)"], "cwd": None}
                     for n in ("pi05", "act")}
            services = PolicyServices(specs, root)
            try:
                self.assertEqual(services.start("act")["act"], "RUNNING")
                with self.assertRaises(RuntimeError):
                    services.start("pi05")
                self.assertEqual(services.stop("act")["act"], "STOPPED")
            finally:
                services.close()


if __name__ == "__main__":
    unittest.main()
