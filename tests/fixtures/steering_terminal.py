"""Offline model/tool fixture for mid-task input in a real terminal."""
import asyncio
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from launcher import _bootstrap
_bootstrap(legacy=False)
from loop_robot.terminal.app import App
from loop_robot.terminal.config import load_config
from loop_robot.terminal.interactive import Terminal

app = App(load_config(), Path(sys.argv[1]))
count = 0


def complete(messages, tools, on_event=None, stop_event=None):
    global count
    count += 1
    if count == 1:
        if on_event:
            on_event('answer_delta', '正在连接，等待回执。')
        return {'tool_calls': [{'id': 'connect', 'type': 'function', 'function': {'name': 'list_files', 'arguments': '{}'}}]}
    assert any(m['role'] == 'user' and m['content'] == '启动 loopmaster host' for m in messages)
    return {'content': '已合并新增要求，连接只执行一次。'}


def dispatch(name, args):
    assert name == 'list_files'
    Path(sys.argv[1], 'probe-count').write_text('1')
    time.sleep(2)
    return {'ok': True}


app.client.complete = complete
app.agent.dispatch = dispatch
try:
    asyncio.run(Terminal(app).run())
finally:
    app.close()
