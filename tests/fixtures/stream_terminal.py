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
    if text == '任务会话':
        terminal.task_store.submit({'goal': '检查机械臂 Host 中文任务', 'session_id': app.session_id})
        return '任务已记录。'
    if text in ('折叠', '折叠滚动'):
        app.workspace_root=Path(sys.argv[1]).parent
        (app.workspace_root/'group_sample.py').write_text('value = 42\n')
        for index in range(6):
            app.agent.on_event('tool','read_file({"path":"group_sample.py"})')
            app.agent.on_event('result',json.dumps(app.tool('read_file',{'path':'group_sample.py'})))
            time.sleep(.1)
        if text == '折叠滚动':
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline and not app.stop_event.is_set() and not (app.workspace_root / 'release-scroll').exists():
                time.sleep(.05)
        app.agent.on_event('answer_delta','读取完成，可以展开调用。')
        return '读取完成，可以展开调用。'
    if text == '配色':
        app.workspace_root = Path(sys.argv[1]).parent
        path = app.workspace_root / 'color_sample.py'
        path.write_text('value = 1\n')
        app.agent.on_event('tool', 'edit_file({"path":"color_sample.py","old_text":"value = 1","new_text":"value = 42"})')
        receipt = app.tool('edit_file', {'path':'color_sample.py','old_text':'value = 1','new_text':'value = 42'})
        app.agent.on_event('result', json.dumps(receipt))
        for part in ('修改完成。\n```python\n', 'def greet():\n', '    # 中文注释\n', '    return "你好"\n', '```\n'):
            app.agent.on_event('answer_delta', part)
            time.sleep(.25)
        return '修改完成。'
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
