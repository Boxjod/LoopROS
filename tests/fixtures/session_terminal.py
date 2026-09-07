"""Offline session UI with actual ChatAgent summary path."""
import asyncio
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from terminal.app import App
from terminal.config import load_config
from terminal.interactive import Terminal
app=App(load_config(),Path(sys.argv[1]))
def complete(messages,tools,on_event=None,stop_event=None):
    answer='已记录你的机器人问题，当前是对话答复。'
    if on_event:
        for chunk in ['已记录你的','机器人问题，','当前是对话答复。']:
            on_event('answer_delta',chunk);time.sleep(.2)
    return {'content':answer,'_streamed':bool(on_event)}
app.client.complete=complete
try: asyncio.run(Terminal(app).run())
finally: app.close()
