import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from loop_robot.terminal.token_budget import fit, record, estimate, status
from loop_robot.terminal.protocols import encode
from loop_robot.terminal.config import validate_provider
from loop_robot.terminal.llm import ChatAgent, read_stream
from loop_robot.terminal.session import SessionStore


class TokenBudgetTests(unittest.TestCase):
    def test_usage_both_protocols_and_missing_are_distinct(self):
        state = record({}, {'prompt_tokens': 100, 'completion_tokens': 25})
        state = record(state, {'input_tokens': 50, 'output_tokens': 10})
        state = record(state, None)
        self.assertEqual(state['total_tokens'], 185)
        self.assertEqual(state['unreported_requests'], 1)
        self.assertFalse(state['last_request_reported'])
        self.assertEqual(state['last_usage']['input_tokens'], 50)

    def test_usage_after_finish_reason_is_read(self):
        chunks = [{'choices': [{'delta': {'content': '中文'}, 'finish_reason': 'stop'}]},
                  {'choices': [], 'usage': {'prompt_tokens': 123, 'completion_tokens': 4}}]
        stream = b''.join(b'data: ' + json.dumps(c).encode() + b'\n\n' for c in chunks) + b'data: [DONE]\n'
        result = read_stream(io.BytesIO(stream), lambda *a: None, wait_usage=True)
        self.assertEqual(result['_usage']['prompt_tokens'], 123)
        self.assertEqual(result['content'], '中文')

    def test_compact_preserves_current_corrections_system_and_tool_pairs(self):
        messages = [{'role': 'system', 'content': 'live state'}]
        for i in range(10):
            messages += [{'role': 'user', 'content': 'old ' + str(i) + '中' * 500},
                         {'role': 'assistant', 'content': 'unverified reply'}]
        messages += [{'role': 'user', 'content': 'current goal'},
                     {'role': 'user', 'content': 'correction'}]
        for i in range(6):
            messages += [{'role': 'assistant', 'tool_calls': [{'id': str(i), 'type': 'function', 'function': {'name': 'read', 'arguments': '{}'}}]},
                         {'role': 'tool', 'tool_call_id': str(i), 'content': 'receipt ' + 'x' * 2000}]
        original = copy.deepcopy(messages)
        compact, report = fit({'context_window': 9000, 'max_output_tokens': 1000}, messages, [], 'current goal')
        self.assertEqual(messages, original)
        self.assertIs(compact[0], messages[0])  # live evidence refresh reference survives
        self.assertTrue(any(m.get('content') == 'current goal' for m in compact))
        self.assertTrue(any(m.get('content') == 'correction' for m in compact))
        self.assertEqual(compact[-1]['tool_call_id'], '5')
        calls = {c['id'] for m in compact for c in m.get('tool_calls', [])}
        results = {m['tool_call_id'] for m in compact if m['role'] == 'tool'}
        self.assertEqual(calls, results)
        self.assertLessEqual(report['estimated_input_tokens'], report['input_limit'])
        self.assertGreater(report['compacted_messages'], 0)

    def test_oversized_current_input_never_sent_or_silently_truncated(self):
        calls = []
        client = SimpleNamespace(config={'context_window': 6000, 'max_output_tokens': 1000}, complete=lambda *a: calls.append(a))
        agent = ChatAgent(client, [], lambda *a: None)
        with self.assertRaisesRegex(ValueError, 'Context budget exceeded'):
            agent.reply('中' * 4000)
        self.assertEqual(calls, [])

    def test_agent_counts_each_tool_round_once_and_keeps_history(self):
        responses = iter([
            {'role': 'assistant', 'tool_calls': [{'id': '1', 'type': 'function', 'function': {'name': 'read', 'arguments': '{}'}}], '_usage': {'input_tokens': 100, 'output_tokens': 20}},
            {'content': 'done', '_usage': {'input_tokens': 150, 'output_tokens': 10}}])
        client = SimpleNamespace(complete=lambda *a: next(responses))
        executed = []
        agent = ChatAgent(client, [], lambda *a: executed.append(a) or {'ok': True})
        self.assertEqual(agent.reply('read once'), 'done')
        self.assertEqual(len(executed), 1)
        self.assertEqual(agent.token_usage['total_tokens'], 280)
        self.assertEqual(agent.token_usage['requests'], 2)

    def test_persistence_and_output_budget(self):
        config = {'model': 'local', 'base_url': 'https://example.com', 'api_key_env': 'KEY', 'timeout_s': 30,
                  'context_window': 32000, 'max_output_tokens': 2000, 'compact_threshold': .75}
        validate_provider(config)
        for protocol, field in [('openai', 'max_tokens'), ('openai-responses', 'max_output_tokens')]:
            _, body = encode({**config, 'protocol': protocol}, [{'role': 'user', 'content': 'hi', '_usage': {}}], [])
            self.assertEqual(body[field], 2000)
            self.assertNotIn('_usage', json.dumps(body))
        with tempfile.TemporaryDirectory() as d:
            store = SessionStore(Path(d) / 'session.sqlite')
            state = record({}, {'prompt_tokens': 80, 'completion_tokens': 20})
            store.save(config, [], [], token_usage=state, history_message_limit=8)
            saved = store.load(config)
            self.assertEqual(saved['token_usage'], state)
            self.assertEqual(saved['history_message_limit'], 8)
            store.close()

    def test_unknown_capacity_and_schema_cost(self):
        messages = [{'role': 'user', 'content': 'hi'}]
        _, report = fit({}, messages, [])
        self.assertIsNone(report['context_window'])
        self.assertGreater(estimate({}, messages, [{'description': 'x' * 1000}]), estimate({}, messages, []) + 900)
        for change in ({'context_window': True}, {'compact_threshold': 1}, {'context_window': 4096}, {'stream_usage': 'yes'}):
            with self.assertRaises(ValueError):
                validate_provider({'model': 'x', 'base_url': 'https://example.com', 'api_key_env': 'KEY', 'timeout_s': 30, **change})

    def test_unknown_window_does_not_block_large_fixed_schema_or_drop_short_history(self):
        source = [{'role': 'system', 'content': 'x' * 40000},
                  {'role': 'user', 'content': 'previous goal'},
                  {'role': 'assistant', 'content': 'previous answer'},
                  {'role': 'user', 'content': 'continue'}]
        messages, report = fit({}, source, [], 'continue')
        self.assertEqual(messages, source)
        self.assertIsNone(report['context_window'])

    def test_reported_context_and_estimated_status_are_distinct(self):
        agent = SimpleNamespace(client=SimpleNamespace(config={'context_window': 10000}),
                                context_report={'estimated_input_tokens': 3000}, token_usage={})
        self.assertIn('Context ~3,000/10,000 30%', status(agent))
        agent.context_report['last_reported_context_tokens'] = 1200
        agent.token_usage = {'total_tokens': 5000, 'unreported_requests': 1}
        self.assertIn('Tokens 5,000+', status(agent))
        self.assertIn('Context 1,200/10,000 12%', status(agent))

    def test_usage_trailer_timeout_keeps_completed_answer_without_replay(self):
        class Response:
            def __init__(self):
                self.first = True
            def readline(self, limit):
                if self.first:
                    self.first = False
                    return b'data: {"choices":[{"delta":{"content":"done"},"finish_reason":"stop"}]}\n'
                raise TimeoutError('missing trailer')
        result = read_stream(Response(), lambda *a: None, wait_usage=True)
        self.assertEqual(result['content'], 'done')
        self.assertNotIn('_usage', result)
