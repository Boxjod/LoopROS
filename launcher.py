"""Installed entry points; retain compatibility with the existing module layout."""
from pathlib import Path
import sys


def _bootstrap():
    root = str(Path(__file__).resolve().parent)
    if root not in sys.path:
        sys.path.insert(0, root)


def main():
    _bootstrap()
    args = sys.argv[1:]
    if args[:1] in (["ros"], ["robot"]):
        args = args[1:]
    try:
        if args[:1] == ['web']:
            from terminal.web_workbench import main as run_web
            return run_web(args[1:])
        if args[:1] == ['mcp']:
            from terminal.sim_mcp import main as run_mcp
            return run_mcp(args[1:])
        if args == ["--check-update"] or args[:1] == ["update"]:
            from release_client import update_main
            return update_main(["--check"] if args == ["--check-update"] else args[1:])
        from release_runtime import runtime_session
        from terminal.app import main as run
        with runtime_session():
            return run()
    except (ValueError, RuntimeError, OSError) as error:
        print("Loop ROS: " + str(error), file=sys.stderr)
        return 1


def switch_main():
    _bootstrap()
    from release_runtime import runtime_session
    from model_switch import main as run
    try:
        with runtime_session():
            return run()
    except (ValueError, RuntimeError, OSError) as error:
        print("Loop ROS: " + str(error), file=sys.stderr)
        return 1
