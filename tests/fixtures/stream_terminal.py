"""Offline interactive process for PTY rendering tests; never calls a model API."""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from terminal.app import App
from terminal.config import load_config
from terminal.interactive import Terminal

app = App(load_config(), Path(sys.argv[1]))
app.startup_fast_status = 'available'  # Simulated capability for banner/stream PTY coverage.
viewer_fixture=Path(sys.argv[1]).parent/'viewer-state.json'
if viewer_fixture.exists():
    app.viewer.status=lambda: json.loads(viewer_fixture.read_text())
terminal = Terminal(app)


def reply(text, *args):
    if text == '你好':
        app.agent.on_event('reasoning_delta', '推理起点：' + '检查场景和任务约束。' * 25 + '推理终点。')
        app.agent.on_event('tool', 'web_search({"query":"机器人"})')
        app.agent.on_event('result', json.dumps({'results': [{'title': '机器人资料'}], 'raw': 'RAW_JSON_SHOULD_BE_FOLDED'*100}))
        for part in ('我会', '调用相应*', '*工具或*', '*委派子任务。'):
            app.agent.on_event('answer_delta', part)
            time.sleep(.3)
        return '我会调用相应工具或委派子任务。'
    answer = '已收到11。\n\n- 状态查询\n- 仿真控制\n\n可以继续补充。'
    app.agent.on_event('answer_delta', answer)
    return answer


app.agent.reply = reply
try:
    asyncio.run(terminal.run())
finally:
    app.close()
