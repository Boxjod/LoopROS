"""Current and legacy commands share the canonical loop_robot package."""
from pathlib import Path
import sys


def _bootstrap(legacy=True):
    # Source checkouts may have any directory name. Register the same package
    # identity as installed wheels without exposing core/terminal as top levels.
    if 'loop_robot' not in sys.modules:
        import importlib.util
        root = Path(__file__).resolve().parent
        spec = importlib.util.spec_from_file_location('loop_robot', root / '__init__.py',
                                                     submodule_search_locations=[str(root)])
        package = importlib.util.module_from_spec(spec)
        sys.modules['loop_robot'] = package
        spec.loader.exec_module(package)
    if legacy:
        # 0.0.1/0.0.2 updater smoke imports these two names after _bootstrap().
        # Alias the canonical objects, never load a second module or add sys.path.
        from importlib import import_module
        for name in ('terminal', 'terminal.app', 'model_switch'):
            sys.modules[name] = import_module('loop_robot.' + name)


def main():
    _bootstrap(legacy=False)
    args = sys.argv[1:]
    if args[:1] in (["ros"], ["robot"]):
        args = args[1:]
    try:
        if args[:1] == ['web']:
            from loop_robot.terminal.web_workbench import main as run_web
            return run_web(args[1:])
        if args[:1] == ['mcp']:
            from loop_robot.terminal.sim_mcp import main as run_mcp
            return run_mcp(args[1:])
        if args == ["--check-update"] or args[:1] == ["update"]:
            from loop_robot.release_client import update_main
            return update_main(["--check"] if args == ["--check-update"] else args[1:])
        from loop_robot.release_runtime import runtime_session
        from loop_robot.terminal.app import main as run
        with runtime_session():
            return run()
    except (ValueError, RuntimeError, OSError) as error:
        print("Loop ROS: " + str(error), file=sys.stderr)
        return 1


def switch_main():
    _bootstrap(legacy=False)
    from loop_robot.release_runtime import runtime_session
    from loop_robot.model_switch import main as run
    try:
        with runtime_session():
            return run()
    except (ValueError, RuntimeError, OSError) as error:
        print("Loop ROS: " + str(error), file=sys.stderr)
        return 1
