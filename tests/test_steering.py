from collections import deque
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from terminal.llm import ChatAgent


def call(identity, name):
    return {'id': identity, 'type': 'function', 'function': {'name': name, 'arguments': '{}'}}


class SteeringTests(unittest.TestCase):
    def agent(self, complete, dispatch):
        queue = deque()
        agent = ChatAgent(SimpleNamespace(complete=complete), [], dispatch)
        def take(budget):
            if queue and len(queue[0][0]) <= budget:
                return [queue.popleft()]
            return []
        agent.take_steering = take
        return agent, queue

    def test_new_input_during_model_request_discards_stale_actions(self):
        seen = []
        def complete(messages, tools):
            seen.append(list(messages))
            if len(seen) == 1:
                queue.append(('还要启动 loopmaster host', []))
                return {'tool_calls': [call('old', 'old_plan')]}
            self.assertTrue(any(m['role'] == 'user' and m['content'] == '还要启动 loopmaster host' for m in messages))
            return {'content': '继续连接并处理新增要求'}
        dispatch = Mock()
        agent, queue = self.agent(complete, dispatch)
        recorded = Mock()
        agent.on_turn_recorded = recorded
        agent.reply('重新连接 Jetson')
        dispatch.assert_not_called()
        self.assertEqual([m['content'] for m in agent.history if m['role'] == 'user'], ['重新连接 Jetson', '还要启动 loopmaster host'])
        self.assertIn('还要启动', recorded.call_args.args[0]['request'])

    def test_new_input_between_tools_preserves_receipt_and_skips_pending_action(self):
        count = 0
        executed = []
        def complete(messages, tools):
            nonlocal count
            count += 1
            if count == 1:
                return {'tool_calls': [call('read', 'connect'), call('move', 'old_action')]}
            receipts = [m for m in messages if m['role'] == 'tool']
            self.assertEqual([m['tool_call_id'] for m in receipts], ['read', 'move'])
            self.assertIn('new_user_input', receipts[1]['content'])
            return {'content': '已连接，按新增要求继续'}
        def dispatch(name, args):
            executed.append(name)
            queue.append(('不要执行旧动作，启动 host', []))
            return {'ok': True}
        agent, queue = self.agent(complete, dispatch)
        agent.reply('连接并操作')
        self.assertEqual(executed, ['connect'])
        self.assertFalse(queue)

    def test_budget_preserves_unconsumed_queue(self):
        agent, queue = self.agent(lambda *_: {'content': 'done'}, Mock())
        queue.append(('next', []))
        agent.reply('a' * 16000)
        self.assertEqual(len(queue), 1)


class SteeringQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_pause_clear_media_and_fifo(self):
        from terminal.interactive import Terminal
        terminal = SimpleNamespace(paused=True, command_busy=False, pending_command=None, timer=None,
            app=SimpleNamespace(stop_event=SimpleNamespace(is_set=lambda: False)), ui=Mock(),
            queue=deque([('补充目标', [('photo', [{'type': 'image_url', 'image_url': {'url': 'test'}}])]), ('后续', [])]))
        self.assertEqual(await Terminal.take_queued_steering(terminal, 100), [])
        terminal.paused = False
        updates = await Terminal.take_queued_steering(terminal, 4)
        self.assertEqual(updates[0][0], '补充目标')
        self.assertEqual(updates[0][1][0]['type'], 'image_url')
        self.assertEqual(list(terminal.queue), [('后续', [])])
