"""Installed entry points; retain compatibility with the existing module layout."""
from pathlib import Path
import sys


def _bootstrap():
    root = str(Path(__file__).resolve().parent)
    if root not in sys.path:
        sys.path.insert(0, root)


def main():
    _bootstrap()
    if sys.argv[1:] in (["--check-update"], ["ros", "--check-update"]):
        from release_client import check_main
        try:
            check_main()
        except Exception as error:
            print("Update check failed: " + str(error), file=sys.stderr)
            return 1
        return 0
    from terminal.app import main as run
    return run()


def switch_main():
    _bootstrap()
    from model_switch import main as run
    return run()
