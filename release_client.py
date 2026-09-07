"""Small HTTPS release client, shared by bootstrap and version checks."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener


def base_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Release URL must be HTTPS, without credentials, query or fragment")
    return value.rstrip("/")


class HTTPSRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        base_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit):
    base_url(url)
    with build_opener(HTTPSRedirect()).open(url, timeout=20) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Release response exceeds size limit")
    return data


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("Expected stable major.minor.patch version")
    return tuple(map(int, value.split(".")))


def manifest(url):
    data = json.loads(fetch(base_url(url) + "/latest.json", 16384))
    version(data["version"])
    expected = "loop_ros-" + data["version"] + "-py3-none-any.whl"
    if data.get("wheel") != expected or not re.fullmatch(r"[0-9a-f]{64}", data.get("sha256", "")):
        raise ValueError("Invalid release artifact metadata")
    return data


def check(url, current):
    data = manifest(url)
    return {"installed": current, "latest": data["version"],
            "update_available": version(data["version"]) > version(current),
            "release_url": base_url(url)}


def install(url, terminal_only=False):
    if sys.version_info < (3, 10):
        raise ValueError("Python 3.10+ with venv/pip required")
    url = base_url(url)
    data = manifest(url)
    payload = fetch(url + "/" + data["wheel"], 32 * 1024 * 1024)
    if hashlib.sha256(payload).hexdigest() != data["sha256"]:
        raise ValueError("Release SHA-256 mismatch; nothing installed")
    root = Path(os.environ.get("LOOP_HOME", str(Path.home() / ".loop"))).expanduser()
    legacy = Path.home() / ".looper"
    if not os.environ.get("LOOP_HOME") and not root.exists() and legacy.exists():
        if legacy.is_symlink() or not legacy.is_dir():
            raise ValueError("Migrate legacy home manually")
        legacy.rename(root)
    environment = root / "runtime"
    windows = os.name == "nt"
    python = environment / ("Scripts/python.exe" if windows else "bin/python")
    commands = Path.home() / ".local/bin"
    if windows:
        raise ValueError("Hosted Windows bootstrap is not yet supported; use the source PowerShell installer")
    for name in ("loop", "loop-switch"):
        link = commands / name
        if (link.exists() or link.is_symlink()) and not (link.is_symlink() and link.readlink() == python.parent / name):
            raise ValueError("Existing command left unchanged: " + str(link) + "; use a separate OS user or explicitly migrate the existing installation")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    with tempfile.TemporaryDirectory(prefix="loop-release-") as directory:
        wheel = Path(directory) / data["wheel"]
        wheel.write_bytes(payload)
        target = str(wheel) + ("" if terminal_only else "[sim]")
        subprocess.run([str(python), "-m", "pip", "install", target], check=True)
    commands.mkdir(parents=True, exist_ok=True)
    for name in ("loop", "loop-switch"):
        link = commands / name
        if not link.is_symlink():
            link.symlink_to(python.parent / name)
    record = root / "release.json"
    fd, temporary = tempfile.mkstemp(dir=root, prefix=".release-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump({"url": url}, stream)
        os.replace(temporary, record)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print('Installed Loop ROS. Add ~/.local/bin to PATH, then run loop.')


def check_main():
    from terminal.home import loop_home
    url = os.environ.get("LOOP_RELEASE_URL")
    if not url:
        record = loop_home() / "release.json"
        if record.exists():
            url = json.loads(record.read_text())["url"]
    if not url:
        raise ValueError("No release server configured. Set LOOP_RELEASE_URL to the published HTTPS base URL.")
    print(json.dumps(check(url, importlib.metadata.version("loop-ros"))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Install a verified Loop ROS release")
    parser.add_argument("--url", required=True)
    parser.add_argument("--terminal-only", action="store_true")
    options = parser.parse_args()
    try:
        install(options.url, options.terminal_only)
    except Exception as error:
        parser.exit(1, "Installation failed: " + str(error) + "\n")
