"""Real node processes alongside a streaming model substitute."""
import asyncio
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    from terminal.app import App
    from terminal.config import load_config
    from terminal.interactive import Terminal
    app = App(load_config(), sys.argv[1])
    terminal = Terminal(app)
    def reply(text, *args):
        for chunk in ('后台分析开始。', '节点可以独立运行。', '切换终端不会停止节点。', '后台分析完成。'):
            app.agent.on_event('answer_delta', chunk)
            time.sleep(.4)
        return '后台分析完成。'
    app.agent.reply = reply
    try:
        asyncio.run(terminal.run())
    finally:
        app.close()


if __name__ == '__main__':
    main()
