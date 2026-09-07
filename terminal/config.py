import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from terminal.home import initialize, loop_home, runtime_state_dir

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_DIR = runtime_state_dir(ROOT)


def user_config_file(name):
    """User-owned overrides live outside the installed package."""
    if name not in ("agents.json", "task_runtime.json"):
        raise ValueError("Unknown user configuration file")
    path = loop_home() / name
    return path if path.exists() else ROOT / "configs" / name


def validate_provider(provider):
    import re
    required = {"base_url", "model", "api_key_env", "timeout_s"}
    if not isinstance(provider, dict) or not required <= set(provider) or set(provider) - required - {"token_field", "protocol", "vision_model"}:
        raise ValueError("provider fields: base_url/model/api_key_env/timeout_s/token_field; do not store API keys")
    if "vision_model" in provider and (not isinstance(provider["vision_model"], str) or not provider["vision_model"].strip() or len(provider["vision_model"]) > 2048):
        raise ValueError("vision_model must be a nonempty model ID")
    for field in ("base_url", "model", "api_key_env"):
        if not isinstance(provider[field], str) or not provider[field] or len(provider[field]) > 2048:
            raise ValueError("invalid provider field: " + field)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", provider["api_key_env"]):
        raise ValueError("api_key_env must be an environment variable name, not a key")
    url = urlsplit(provider["base_url"])
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("base_url must have a host and no credentials, query or fragment")
    if url.scheme != "https" and not (url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1")):
        raise ValueError("use HTTPS, or HTTP on loopback only")
    if type(provider["timeout_s"]) not in (int, float) or not 1 <= provider["timeout_s"] <= 120:
        raise ValueError("LLM timeout must be 1..120 seconds")
    if provider.get("token_field", "max_tokens") not in ("max_tokens", "max_completion_tokens"):
        raise ValueError("invalid token field")
    if provider.get("protocol", "openai") not in ("openai", "openai-responses"):
        raise ValueError("Supported protocols: openai, openai-responses")
    return dict(provider)


def load_config(path=None):
    initialize()
    config = json.loads((ROOT / "configs/config.example.json").read_text())
    path = Path(path) if path else ROOT / "config.local.json"
    for source in (loop_home() / "config.json", path):
        if not source.exists():
            continue
        for key, value in json.loads(source.read_text(encoding="utf-8")).items():
            if key not in config:
                raise ValueError("unknown config section: " + key)
            config[key].update(value)
    validate_provider(config["llm"])
    config["expert"] = dict(config["llm"])  # Accept legacy files without a second provider.
    if config["scene"]["backend"] != "mujoco":
        raise ValueError("当前已验证场景后端仅 mujoco；Genesis 尚未接入")
    return config
