import json
import threading
import unittest
from types import SimpleNamespace

from loop_robot.terminal.llm import ChatAgent


def call(index, step):
    return {'tool_calls': [{'id': str(index), 'type': 'function',
                           'function': {'name': 'work', 'arguments': json.dumps({'step': step})}}]}


class ContinuationTests(unittest.TestCase):
    def agent(self, replies, dispatch, segments=2):
        replies = iter(replies)
        requests = []
        def complete(messages, tools):
            requests.append((list(messages), list(tools)))
            return next(replies)
        agent = ChatAgent(SimpleNamespace(config={}, complete=complete), [], dispatch)
        schema = {'type':'function', 'function':{'name':'work', 'parameters':{'type':'object'}}}
        agent.context_provider = lambda text: {'system_prompt':'Execute the authorized goal',
                                              'tools':[schema], 'max_tool_rounds':1,
                                              'max_tool_continuations':segments}
        return agent, requests

    def test_inspect_start_verify_across_segments_without_replaying(self):
        executed = []
        def dispatch(name, args):
            executed.append(args['step'])
            return {'step':args['step'], 'returncode':0}
        agent, requests = self.agent([call(1,'inspect'), call(2,'start'), call(3,'verify'), {'content':'ready'}], dispatch)
        self.assertEqual(agent.reply('Start the service and verify readiness'), 'ready')
        self.assertEqual(executed, ['inspect','start','verify'])
        self.assertEqual([len(tools) for _, tools in requests], [1,1,1,0])
        self.assertEqual(agent.token_usage['requests'], 4)
        self.assertEqual(len([m for m in requests[-1][0] if m['role']=='tool']), 3)

    def test_unchanged_calls_do_not_earn_another_segment(self):
        agent, requests = self.agent([call(1,'inspect'), call(2,'inspect'), {'content':'unfinished'}], lambda *a: {'ok':True})
        agent.reply('Inspect')
        self.assertEqual([len(tools) for _, tools in requests], [1,1,0])

    def test_old_progress_does_not_extend_a_stalled_segment(self):
        agent, requests = self.agent([call(i,'inspect') for i in range(4)] + [{'content':'unfinished'}], lambda *a: {'ok':True})
        context = agent.context_provider('Work')
        context['max_tool_rounds'] = 4
        agent.context_provider = lambda text: context
        agent.reply('Work')
        self.assertEqual([len(tools) for _, tools in requests], [1,1,1,1,0])

    def test_permission_and_safety_stops_do_not_extend(self):
        for result in ({'error':'PermissionError'}, {'stop_reason':'torque_limit'}):
            with self.subTest(result=result):
                agent, requests = self.agent([call(1,'start'), {'content':'blocked'}], lambda *a: result)
                agent.reply('Start')
                self.assertEqual([len(tools) for _, tools in requests], [1,0])

    def test_existing_worker_budget_does_not_implicitly_expand(self):
        agent, requests = self.agent([call(1,'inspect'), {'content':'unfinished'}], lambda *a: {'ok':True}, segments=0)
        agent.reply('Work')
        self.assertEqual([len(tools) for _, tools in requests], [1,0])

    def test_unlimited_foreground_keeps_tools_beyond_old_cap(self):
        executed = []
        agent, requests = self.agent(
            [call(i, 'inspect') for i in range(80)] + [{'content':'done'}],
            lambda name, args: executed.append(args) or {'ok':True})
        context = agent.context_provider('Work')
        context['max_tool_rounds'] = None
        agent.context_provider = lambda text: context
        self.assertEqual(agent.reply('Work'), 'done')
        self.assertEqual(len(executed), 80)
        self.assertTrue(all(tools for _, tools in requests))
        self.assertFalse(any('Total tool budget reached' in str(messages)
                             for messages, _ in requests))

    def test_unlimited_foreground_can_be_cancelled(self):
        stop = threading.Event()
        executed = []
        def dispatch(name, args):
            executed.append(args)
            if len(executed) == 75:
                stop.set()
            return {'ok':True}
        agent, requests = self.agent([call(i, 'inspect') for i in range(80)], dispatch)
        context = agent.context_provider('Work')
        context['max_tool_rounds'] = None
        agent.context_provider = lambda text: context
        agent.stop_event = stop
        with self.assertRaisesRegex(RuntimeError, 'stopped'):
            agent.reply('Work')
        self.assertEqual(len(executed), 75)

    def test_cancel_prevents_continuation(self):
        stop = threading.Event()
        def dispatch(*args):
            stop.set()
            return {'ok':True}
        agent, requests = self.agent([call(1,'inspect')], dispatch)
        agent.stop_event = stop
        with self.assertRaisesRegex(RuntimeError, 'stopped'):
            agent.reply('Work')
        self.assertEqual(len(requests), 1)
