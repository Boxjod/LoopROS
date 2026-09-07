"""Shared user-local uv bootstrap and launcher utilities (Python 3.8+)."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import urllib.request


def venv_python(root):
    return Path(root) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def windows_launcher(executable):
    path = str(executable).replace("%", "%%")
    return '@echo off\nrem Loop ROS managed launcher\nsetlocal DisableDelayedExpansion\nchcp 65001 >nul\n"{}" %*\n'.format(path)


def ensure_uv():
    """Use an existing uv or install Astral's standalone binary for this user."""
    found = shutil.which("uv")
    if found:
        return found
    target = Path.home() / ".local/bin" / ("uv.exe" if os.name == "nt" else "uv")
    if target.is_file():
        return str(target)
    print("Installing uv from https://astral.sh/uv (user directory)...", flush=True)
    suffix = ".ps1" if os.name == "nt" else ".sh"
    env = dict(os.environ, UV_INSTALL_DIR=str(target.parent), UV_NO_MODIFY_PATH="1")
    with tempfile.TemporaryDirectory(prefix="loop-uv-") as directory:
        script = Path(directory) / ("install" + suffix)
        url = "https://astral.sh/uv/install" + suffix
        curl = shutil.which("curl")
        if curl:
            subprocess.run([curl, "--fail", "--location", "--silent", "--show-error",
                            "--max-time", "60", "--output", str(script), url], check=True)
        else:
            with urllib.request.urlopen(url, timeout=60) as response:
                script.write_bytes(response.read())
        command = (["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
                   if os.name == "nt" else ["sh"])
        subprocess.run(command + [str(script)], env=env, check=True)
    if not target.is_file():
        raise SystemExit("uv installation did not produce " + str(target))
    return str(target)


def backup_launcher(path):
    index = 1
    while True:
        backup = path.with_name(path.name + ".loop-ros-backup." + str(index))
        if not backup.exists() and not backup.is_symlink():
            path.rename(backup)
            print("Previous launcher backed up: " + str(backup))
            return backup
        index += 1



def configure_path(target_dir):
    if os.name == 'nt':
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
            try:
                old, kind = winreg.QueryValueEx(key, 'Path')
            except FileNotFoundError:
                old, kind = '', winreg.REG_EXPAND_SZ
            if str(target_dir).casefold() not in [p.rstrip('\\/').casefold() for p in old.split(';')]:
                winreg.SetValueEx(key, 'Path', 0, kind, old.rstrip(';') + ';' + str(target_dir))
        print('User PATH updated. Open a new terminal to run loop.')
    elif str(target_dir) not in os.environ.get('PATH', '').split(os.pathsep):
        print('Add to your shell profile: export PATH="$HOME/.local/bin:$PATH"')
