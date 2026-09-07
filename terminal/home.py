"""User-owned configuration and endpoint-bound credentials; never load project secrets."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def loop_home():
    override = os.environ.get("LOOP_HOME") or os.environ.get("LOOPER_HOME")
    if override:
        return Path(override).expanduser()
    current, legacy = Path.home() / ".loop", Path.home() / ".looper"
    if not current.exists() and legacy.exists():
        if legacy.is_symlink() or not legacy.is_dir():
            raise ValueError("Legacy home is not a regular directory; migrate it to ~/.loop manually")
        legacy.rename(current)
    return current


# Retain the old import for callers upgrading from earlier releases.
looper_home = loop_home


def runtime_state_dir(root):
    override = os.environ.get("LOOP_STATE_DIR") or os.environ.get("LOOPER_STATE_DIR")
    if override:
        return Path(override).expanduser()
    if (Path(root) / "pyproject.toml").exists():
        return Path(root) / "artifacts/terminal"
    base = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    current, legacy = base / "loop-ros", base / "looper"
    if not current.exists() and legacy.exists():
        if legacy.is_symlink() or not legacy.is_dir() or current.is_symlink():
            raise ValueError("Legacy state is not a regular directory; migrate it to loop-ros manually")
        legacy.rename(current)
        try:
            # Saved scene paths may still reference the old directory.
            legacy.symlink_to(current.name, target_is_directory=True)
        except OSError:
            current.rename(legacy)
            raise ValueError("State migration needs directory symlink support; original state preserved") from None
    return current


def initialize():
    root = loop_home()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in ("harness", "skills"):
        (root / name).mkdir(mode=0o700, exist_ok=True)
    return root


def credential_id(config):
    identity = config["base_url"].rstrip("/") + "\n" + config["api_key_env"]
    return hashlib.sha256(identity.encode()).hexdigest()


def _credentials():
    path = loop_home() / "credentials.json"
    if not path.exists():
        return {}
    if path.is_symlink():
        raise ValueError("Credentials must not be a symbolic link")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise PermissionError("credentials.json must have mode 0600")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
            raise ValueError()
        return data
    except (ValueError, UnicodeError):
        raise ValueError("Invalid credentials file; contents withheld") from None


def _key_config():
    path = loop_home() / 'config.json'
    if path.is_symlink():
        raise ValueError('Config must not be a symbolic link')
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
        entries = data.get('endpoints', [])
        if not isinstance(entries, list) or any(not isinstance(e, dict) or not isinstance(e.get('api_key'), str) for e in entries):
            raise ValueError()
        return data
    except (ValueError, UnicodeError):
        raise ValueError('Invalid user config; contents withheld') from None


def saved_key(config):
    identity = credential_id(config)
    for entry in _key_config().get('endpoints', []):
        if entry.get('legacy_id') == identity:
            save_key(config, entry['api_key'])
            return entry['api_key']
        if (entry.get('base_url', '').rstrip('/') == config['base_url'].rstrip('/')
                and entry.get('api_key_env') == config['api_key_env']):
            return entry['api_key']
    key = _credentials().get(identity)
    if key:
        save_key(config, key)
    return key


def save_key(config, key):
    if not key or "\n" in key or "\r" in key:
        raise ValueError("API key must be a nonempty single line")
    root = initialize()
    data = _key_config()
    entries = data.setdefault('endpoints', [])
    # Keep unresolved legacy entries so migration never drops another profile's key.
    for identity, old_key in _credentials().items():
        if not any(e.get('legacy_id') == identity or
                   ('base_url' in e and credential_id(e) == identity) for e in entries):
            entries.append({'legacy_id': identity, 'api_key': old_key})
    identity = credential_id(config)
    entries[:] = [e for e in entries if e.get('legacy_id') != identity and
                  not ('base_url' in e and credential_id(e) == identity)]
    entries.append({'base_url': config['base_url'].rstrip('/'),
                    'api_key_env': config['api_key_env'], 'api_key': key})
    fd, temporary = tempfile.mkstemp(prefix='.config-', dir=root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / 'config.json')
        (root / 'credentials.json').unlink(missing_ok=True)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def harness_prompt():
    root = loop_home()
    paths = [root / "AGENTS.md"] + sorted((root / "harness").glob("*.md"))
    chunks = []
    size = 0
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        size += len(text)
        if size > 24000:
            raise ValueError("Global harness exceeds 24000 characters")
        chunks.append(text)
    return "\n\n".join(chunks)
