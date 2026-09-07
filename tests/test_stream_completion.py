import io
import json
import unittest
from terminal.llm import ChatAgent, read_stream


def chunk(delta, **extra):
    return b'data: ' + json.dumps({'choices': [{'delta': delta, **extra}]}).encode() + b'\n\n'


class StreamCompletionTests(unittest.TestCase):
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
