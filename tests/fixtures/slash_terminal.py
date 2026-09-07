"""Offline model-menu and Chinese-input PTY fixture."""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from launcher import _bootstrap
_bootstrap(legacy=False)
from loop_robot.terminal.app import App
from loop_robot.terminal.config import load_config
from loop_robot.terminal.interactive import Terminal


def agent_ui_worker(pipe, definition, config, key, task, schemas):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        pipe.send({'type':'inbox'})
        messages=pipe.recv()['messages']
        if messages:
            pipe.send({'type':'result','result':task+' / '+'; '.join(messages)})
            break
        time.sleep(.05)
    pipe.close()


def main():
    root = Path(sys.argv[1])
    app = App(load_config(), root/'state')
    app.client.key = 'fixture-key'
    if os.environ.get('LOOP_AGENT_UI_FIXTURE'):
        app.runtime.worker_target=agent_ui_worker
        app.runtime.admission=None
    original_poll = app.runtime.poll_notifications
    def slow_poll():
        time.sleep(.35)
        notifications, mail = original_poll()
        if os.environ.get('LOOP_AGENT_UI_FIXTURE'):
            with app.runtime.lock:
                app.runtime.mail=[]
            mail=False
        return notifications, mail
    app.runtime.poll_notifications = slow_poll
    def reply(text, *args):
        with (root/'inputs.jsonl').open('a') as output:
            output.write(json.dumps(text, ensure_ascii=False)+'\n')
        if text == '代码示例':
            parts = ('请执行：\n', '```text\n', '/approve example-id\n', '``', '`\n', '然后继续。')
            for part in parts:
                app.agent.on_event('answer_delta', part)
                time.sleep(.15)
            return ''.join(parts)
        for part in ('中文', '流式', '反馈'):
            app.agent.on_event('answer_delta', part)
            time.sleep(.25)
        return '中文流式反馈'
    app.agent.reply = reply
    rows = [{'id':'model-a','company':'A','date':'2026-09-01'}, {'id':'model-b','company':'B','date':'Unknown','reasoning_efforts':['low','high']}]
    try:
        with patch('loop_robot.terminal.setup.discover_models', return_value=rows):
            asyncio.run(Terminal(app).run())
    finally:
        app.close()


if __name__ == '__main__':
    main()
