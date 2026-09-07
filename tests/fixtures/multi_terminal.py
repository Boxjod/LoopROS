"""Two real CLI terminals with an offline streaming model replacement."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from terminal.app import main
from terminal.llm import QwenClient


def complete(self, messages, tools, on_event=None, stop_event=None):
    answer = '已完成当前窗口的对话答复。'
    if on_event:
        for chunk in ['已完成', '当前窗口的', '对话答复。']:
            on_event('answer_delta', chunk)
            time.sleep(.2)
    return {'content':answer, '_streamed':bool(on_event)}


QwenClient.complete = complete
raise SystemExit(main(['node', '--state-dir', sys.argv[1]]))
