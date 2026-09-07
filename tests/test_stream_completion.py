import io
import json
import unittest
from unittest.mock import patch
from loop_robot.terminal.llm import ChatAgent, ModelAPIError, QwenClient, read_stream


def chunk(delta, **extra):
    return b'data: ' + json.dumps({'choices': [{'delta': delta, **extra}]}).encode() + b'\n\n'


class StreamCompletionTests(unittest.TestCase):
    def client(self):
        client = QwenClient({'protocol': 'openai', 'model': 'fixture',
                             'base_url': 'https://unused.invalid/v1',
                             'api_key_env': 'LOOP_TEST_UNUSED', 'timeout_s': 1})
        client.key = 'test-placeholder'
        return client

    def test_many_fragmented_calls_execute_once_and_continue(self):
        for count in (1, 5, 12):
            with self.subTest(count=count):
                initial = [{'index': i, 'id': 'call' + str(i),
                            'function': {'name': 'work', 'arguments': '{"step":'}}
                           for i in reversed(range(count))]
                tail = [{'index': i, 'function': {'arguments': str(i) + '}'}}
                        for i in range(count)]
                stream = chunk({'tool_calls': initial}) + chunk({'tool_calls': tail})
                stream += chunk({}, finish_reason='tool_calls') + b'data: [DONE]\n\n'
                final = chunk({'content': '完成'}, finish_reason='stop') + b'data: [DONE]\n\n'
                executed = []
                agent = ChatAgent(self.client(), [],
                                  lambda name, args: executed.append(args['step']) or {'ok': True})
                agent.streaming = True
                agent.on_event = lambda *e: None
                with patch('loop_robot.terminal.llm.build_opener') as opener:
                    opener.return_value.open.side_effect = [io.BytesIO(stream), io.BytesIO(final)]
                    self.assertEqual(agent.reply('Execute each step'), '完成')
                    self.assertEqual(opener.return_value.open.call_count, 2)
                    request = opener.return_value.open.call_args.args[0]
                    messages = json.loads(request.data)['messages']
                self.assertEqual(executed, list(range(count)))
                results = [m for m in messages if m['role'] == 'tool']
                self.assertEqual([m['tool_call_id'] for m in results],
                                 ['call' + str(i) for i in range(count)])

    def test_client_reports_parse_failures_without_protocol_guess_or_retry(self):
        cases = [(b'data: {private-invalid-json}\n\n', 'invalid JSON'),
                 (b'data: [DONE]\n\n', 'without finish reason'),
                 (b'data: []\n\n', 'invalid or missing fields')]
        for index in (-1, '4', True, None):
            cases.append((chunk({'tool_calls': [{'index': index}]}), 'tool call index'))
        for stream, expected in cases:
            with self.subTest(expected=expected, stream=stream):
                with patch('loop_robot.terminal.llm.build_opener') as opener:
                    opener.return_value.open.return_value = io.BytesIO(stream)
                    with self.assertRaisesRegex(ModelAPIError, expected) as error:
                        self.client().complete([], [], on_event=lambda *e: None)
                    opener.return_value.open.assert_called_once()
                    self.assertNotIn('private', str(error.exception))
                    self.assertNotIn('Chat Completions vs', str(error.exception))

    def test_finish_reason_completes_without_waiting_for_done(self):
        class Response(io.BytesIO):
            def readline(self, limit):
                if self.tell() == len(self.getvalue()):
                    raise AssertionError('must not wait for a trailer after finish_reason')
                return super().readline(limit)
        events = []
        result = read_stream(Response(b': heartbeat\n\ndata:\n\n' + chunk({'content': '你好'}, finish_reason='stop')),
                             lambda *e: events.append(e))
        self.assertEqual(result['content'], '你好')
        self.assertEqual(events, [('answer_delta', '你好')])

    def test_partial_stream_still_fails_and_keeps_emitted_text(self):
        events = []
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            read_stream(io.BytesIO(chunk({'content': '已收到'})), lambda *e: events.append(e))
        self.assertEqual(events, [('answer_delta', '已收到')])

    def test_tool_calls_need_completed_stream(self):
        call = {'index': 0, 'id': 'call1', 'function': {'name': 'status', 'arguments': '{}'}}
        result = read_stream(io.BytesIO(chunk({'tool_calls': [call]}, finish_reason='tool_calls')), lambda *e: None)
        self.assertEqual(result['tool_calls'][0]['function']['arguments'], '{}')
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            read_stream(io.BytesIO(chunk({'tool_calls': [call]})), lambda *e: None)

    def test_plain_answer_streams_before_request_returns_with_summary_hook(self):
        events = []
        class Client:
            def complete(self, messages, tools, on_event=None, stop_event=None):
                on_event('answer_delta', '你好')
                self.assert_streamed()
                return {'content': '你好', '_streamed': True}
        client = Client()
        client.assert_streamed = lambda: self.assertIn(('answer_delta', '你好'), events)
        agent = ChatAgent(client, [], lambda *args: None)
        agent.result_summary = lambda results: None
        agent.streaming = True
        agent.on_event = lambda *e: events.append(e)
        self.assertEqual(agent.reply('你好'), '你好')
        self.assertEqual(events.count(('answer_delta', '你好')), 1)
