import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from launcher import _bootstrap
_bootstrap(legacy=False)
from loop_robot.terminal.app import App
from loop_robot.terminal.config import load_config
from loop_robot.terminal.home import loop_home
from loop_robot.terminal.interactive import Terminal

def main():
    app = App(load_config(), Path(sys.argv[1]))
    app.permissions.set_rule('run_python','allow')
    folder = loop_home()/'processes'
    folder.mkdir(exist_ok=True)
    (folder/'console.json').write_text(json.dumps({'cwd':str(folder),'argv':[sys.executable,'-u','-c',
        'print("READY",flush=True); print("CHILD="+input(),flush=True); import time; time.sleep(60)']}))
    def forbidden(*args, **kwargs):
        raise AssertionError('Process console must not call the model')
    app.client.complete = forbidden
    try:
        asyncio.run(Terminal(app).run())
    finally:
        app.close()


if __name__ == "__main__":
    main()
