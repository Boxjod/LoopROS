"""Remove this source checkout's environment and owned user launchers (Python 3.8+)."""
import argparse
import ast
import re
import shlex
import os
from pathlib import Path, PureWindowsPath
import shutil
import stat

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("loop", "loop-switch", "looper", "looper-switch")


def owned_launcher(path, environment, name, windows=False):
    if path.is_symlink():
        target = Path(os.readlink(path))
        if not target.is_absolute():
            target = path.parent / target
        if os.path.abspath(target) == str(environment / "bin" / name):
            return True  # Also removes broken links into this checkout.
    if not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    if not windows and content.startswith('#!/bin/sh\n# Loop ROS managed release launcher\nexec '):
        try:
            command = shlex.split(content.split('\n', 2)[2])
        except ValueError:
            return False
        if len(command) == 5 and command[0] == 'exec' and command[3:] == [name, '$@']:
            dispatcher = Path(command[2])
            return dispatcher.name == 'release-launcher.py' and Path(command[1]) == dispatcher.parent / 'updater/bin/python'
        return False
    if windows:
        prefix = ('@echo off\nrem Loop ROS managed release launcher\nsetlocal DisableDelayedExpansion\n'
                  'chcp 65001 >nul\n')
        match = re.fullmatch(re.escape(prefix) + r'"([^"\r\n]+)" "([^"\r\n]+)" ' + re.escape(name) + r' %\*\n', content)
        if match:
            dispatcher = PureWindowsPath(match.group(2))
            return dispatcher.name == 'release-launcher.py' and PureWindowsPath(match.group(1)) == dispatcher.parent / 'updater/Scripts/python.exe'
    if windows:
        # The installer marks its .cmd wrappers; match the complete format.
        prefix = ('@echo off\nrem Loop ROS managed launcher\nsetlocal DisableDelayedExpansion\n'
                  'chcp 65001 >nul\n')
        match = re.fullmatch(re.escape(prefix) + r'"([^"\r\n]+)" %\*\n', content)
        return bool(match and PureWindowsPath(match.group(1)).name == name + ".exe")
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return False
    entrypoint = "switch_main" if name.endswith("-switch") else "main"
    # Inspect pip/uv-generated entrypoints without executing another checkout.
    return any(isinstance(node, ast.ImportFrom) and node.level == 0
               and node.module == "loop_robot.launcher"
               and any(alias.name == entrypoint for alias in node.names)
               for node in tree.body)


def uninstall(root, home, check=False):
    environment = root / ".venv"
    exists = environment.exists() or environment.is_symlink()
    linked = False
    if exists:
        info = environment.lstat()
        linked = environment.is_symlink() or bool(
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        if not linked and (not environment.is_dir() or not (environment / "pyvenv.cfg").is_file()):
            raise SystemExit("Refusing to remove an unrecognized .venv; left unchanged: " + str(environment))
    windows = os.name == "nt"
    for name in NAMES:
        path = home / ".local/bin" / (name + ".cmd" if windows else name)
        if owned_launcher(path, environment, name, windows):
            print(("Would remove: " if check else "Removing: ") + str(path))
            if not check:
                path.unlink()
        elif path.exists() or path.is_symlink():
            print("Unrelated or unverified launcher preserved: " + str(path))
    if exists:
        print(("Would remove: " if check else "Removing: ") + str(environment))
        if not check:
            if environment.is_symlink():
                environment.unlink()
            elif linked:
                environment.rmdir()  # Windows junction: preserve its target.
            else:
                shutil.rmtree(str(environment))
    print("Check complete; no changes made." if check else "Uninstall complete.")
    print("Source, user configuration, runtime data, uv and shared Python installations preserved.")


def main():
    parser = argparse.ArgumentParser(description="Uninstall Loop ROS from this source checkout")
    parser.add_argument("--check", action="store_true", help="Preview removal without changing files")
    args = parser.parse_args()
    uninstall(ROOT, Path.home(), args.check)


if __name__ == "__main__":
    try:
        main()
    except OSError as exc:
        raise SystemExit("Uninstall failed: {}. Close Loop ROS and its background services, then retry.".format(exc)) from None
