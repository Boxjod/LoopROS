"""Shared provider setup and interactive startup connection recovery."""
import getpass
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.request import Request, build_opener

from terminal.config import validate_provider
from terminal.home import save_key
from terminal.llm import NoRedirect, QwenClient, ModelAPIError, model_https_handler

# Public endpoints, not subscriptions or guarantees of account access.
PRESETS = [
    ("OpenAI / GPT-6 Astra (recommended)", "https://api.openai.com/v1", "gpt-6-astra"),
    ("Qwen / Beijing (legacy endpoint)", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    ("Qwen / Singapore (legacy endpoint)", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    ("DeepSeek", "https://api.deepseek.com", "deepseek-v4-flash"),
    ("Kimi / Global", "https://api.moonshot.ai/v1", "kimi-k2.6"),
]


def model_company(item):
    """Normalize recognizable families/owners; gateways may report their own owner."""
    aliases = {
        "Alibaba": ("alibaba", "qwen", "qwq"),
        "Anthropic": ("anthropic", "claude"),
        "DeepSeek": ("deepseek",),
        "Google": ("google", "gemini", "gemma"),
        "Meta": ("meta", "meta-llama", "llama"),
        "Mistral AI": ("mistral", "mistralai", "mixtral", "codestral", "ministral"),
        "Moonshot AI": ("moonshot", "moonshotai", "kimi"),
        "OpenAI": ("openai", "gpt", "chatgpt", "o1", "o3", "o4"),
        "xAI": ("xai", "grok"),
        "Zhipu AI": ("zhipu", "z-ai", "glm"),
    }
    for value in (item["id"].split("/")[-1], item["id"].split("/")[0], item.get("owned_by", "")):
        if not isinstance(value, str):
            continue
        for company, prefixes in aliases.items():
            if any(re.match(re.escape(prefix) + r"(?:$|[-_. /]|\d)", value.lower()) for prefix in prefixes):
                return company
    owner = item.get("owned_by", "")
    if isinstance(owner, str) and owner.isprintable() and len(owner) <= 80 and owner.lower() not in ("", "system", "user", "organization"):
        return owner
    return "Unknown"


def model_date(item):
    """Use catalog timestamps, then explicit YYYY-MM-DD/ YYYYMMDD ID dates."""
    for field in ("released_at", "release_date", "created"):
        value = item.get(field)
        try:
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                return datetime.fromtimestamp(value, timezone.utc)
            if isinstance(value, str) and value.strip():
                if value.isdigit():
                    return datetime.fromtimestamp(int(value), timezone.utc)
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass
    for match in re.finditer(r"(?<!\d)(20\d{2})-?(\d{2})-?(\d{2})(?!\d)", item["id"]):
        try:
            return datetime(*map(int, match.groups()), tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def discover_models(config, key):
    request = Request(config["base_url"].rstrip("/") + "/models",
                      headers={"Authorization": "Bearer " + key})
    try:
        with build_opener(NoRedirect(), model_https_handler()).open(request, timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError()
        data = json.loads(raw)["data"]
        if not isinstance(data, list):
            raise ValueError()
        models = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("id")
            if not isinstance(name, str) or not name.isprintable() or not name.strip() or len(name) > 200:
                continue
            date = model_date(item)
            model = {"id": name, "company": model_company(item),
                     "date": date.strftime("%Y-%m-%d") if date else "Unknown",
                     "timestamp": date.timestamp() if date else 0}
            if name not in models or model["timestamp"] > models[name]["timestamp"]:
                models[name] = model
        return sorted(models.values(), key=lambda m: (m["company"] == "Unknown", m["company"].casefold(),
                                                      -m["timestamp"], m["id"].casefold(), m["id"]))
    except Exception:
        raise ValueError("Model discovery unavailable; enter a model ID manually.") from None


def quick_setup(store, slot="master", read=None, secret=None, write=print):
    read, secret = read or input, secret or getpass.getpass
    write("\nLoop Switch · Quick setup")
    for index, (label, url, _) in enumerate(PRESETS, 1):
        write("  {}. {}  {}".format(index, label, url))
    write("  c. Custom URL / token platform    0. Cancel")
    choice = read("Provider number or API base URL [1]: ").strip() or "1"
    if choice == "0":
        return None
    model = ""
    if choice.isdigit() and 1 <= int(choice) <= len(PRESETS):
        _, url, model = PRESETS[int(choice) - 1]
    else:
        url = read("API base URL: ").strip() if choice.lower() == "c" else choice
        model = next((m for _, u, m in PRESETS if u == url.rstrip("/")), "")
    url = url.rstrip("/")
    protocol = "openai-responses" if url == "https://api.openai.com/v1" else "openai"
    for suffix, kind in (("/chat/completions", "openai"), ("/responses", "openai-responses")):
        if url.endswith(suffix):
            url, protocol = url[:-len(suffix)], kind
            write("Full endpoint detected; using its API base URL.")
            break
    config = {"base_url": url, "model": model or "pending", "timeout_s": 60,
              "api_key_env": "LOOP_KEY_" + hashlib.sha256(url.encode()).hexdigest()[:16].upper(),
              "protocol": protocol}
    validate_provider(config)  # Reject credential URLs before asking for a secret.
    write("API type: 1. OpenAI-compatible Chat Completions  2. OpenAI Responses")
    default = "2" if protocol == "openai-responses" else "1"
    choice = read("API type [{}] (0 to cancel): ".format(default)).strip() or default
    if choice == "0":
        return None
    kinds = {"1": "openai", "2": "openai-responses", "openai": "openai", "openai-responses": "openai-responses"}
    if choice not in kinds:
        raise ValueError("Choose 1 (Chat Completions) or 2 (Responses); nothing saved")
    config["protocol"] = kinds[choice]
    write("The key will be saved locally in Loop ROS user home (plaintext, private permissions).")
    key = secret("API key (hidden; Enter to cancel): ").strip()
    if not key:
        return None
    write("Discovering models from the selected URL only (GET /models; no inference).")
    try:
        models = discover_models(config, key)
    except ValueError as exc:
        write(str(exc))
        models = []
    if models:
        write("Available models: company A-Z, newest catalog date first; unknown dates last.")
        write("Catalog listing does not verify API type or tool support.")
        company = None
        for index, item in enumerate(models, 1):
            if item["company"] != company:
                company = item["company"]
                write(company)
            write("  {}. {} | {}".format(index, item["id"], item["date"]))
        default = next((i for i, item in enumerate(models, 1) if item["id"] == model), 1)
        while True:
            choice = read("Model number or ID [{}] (0 to cancel): ".format(default)).strip()
            if choice == "0":
                return None
            if not choice or (choice.isdigit() and 1 <= int(choice) <= len(models)):
                model = models[int(choice or default) - 1]["id"]
                break
            if choice.isdigit():
                write("Choose a listed model number or enter a model ID.")
                continue
            model = choice
            break
    else:
        write("No model list available. Enter a model ID manually.")
        model = read("Model ID [{}] (0 to cancel): ".format(model or "required")).strip() or model
        if model == "0":
            return None
    if not model:
        return None
    config["model"] = model
    validate_provider(config)
    # New profile per setup: preserve existing profiles and inactive account settings.
    import uuid
    name = "setup-" + uuid.uuid4().hex[:12]
    save_key(config, key)
    store.save(name, config)
    store.use(slot, name)
    write("Saved. {} uses {} · {}. API access is not yet verified.".format("Current model", model, config["protocol"]))
    return name


def check_connection(client):
    """Check connectivity, then best-effort Fast support without changing the profile."""
    key = client.resolved_key()
    if not key:
        raise ModelAPIError("No API key configured")
    probe = QwenClient(dict(client.config))
    probe.key = key
    result = probe.complete([{"role": "user", "content": "Reply with OK only."}], [])
    if not isinstance(result, dict) or not isinstance(result.get("content"), str) or not result["content"].strip():
        raise ModelAPIError("Model returned no text; check the model ID and API type")
    if probe.last_service_tier in ('priority', 'fast'):
        return 'active'
    print('Checking Fast availability (one short request; provider charges may apply)...', flush=True)
    probe.config['timeout_s'] = min(probe.config['timeout_s'], 10)
    try:
        result = probe.complete([{"role": "user", "content": "Reply with OK only."}], [],
                                service_tier='priority')
        if (isinstance(result, dict) and isinstance(result.get('content'), str)
                and result['content'].strip() and probe.last_service_tier in ('priority', 'fast')):
            return 'available'
    except (RuntimeError, ValueError, TypeError, OSError):
        # Optional capability failures must not reopen setup or expose gateway text.
        pass
    return 'unknown'


def ensure_setup(app, interactive):
    app.startup_fast_status = None
    if not interactive:
        return True
    while True:
        try:
            print("Checking model connection (short request, no tools)...", flush=True)
            app.startup_fast_status = check_connection(app.client)
            print("Model connected.")
            return True
        except (EOFError, KeyboardInterrupt):
            print("\nConnection check cancelled.")
            return False
        except (RuntimeError, ValueError, OSError) as exc:
            # No raw exception/response text: gateways and local paths may contain secrets.
            print("Model connection failed. " + (str(exc) if isinstance(exc, ModelAPIError)
                  else "Check API URL, key, model ID and API type."))
            print("Opening Loop Switch setup. Environment keys take precedence over saved keys.")
        while True:
            try:
                name = quick_setup(app.providers)
                if name is None:
                    return False
                app.apply_profiles()
                break
            except (EOFError, KeyboardInterrupt):
                print("\nSetup cancelled.")
                return False
            except (ValueError, OSError):
                print("Setup could not be saved. Check the URL, API type and user configuration permissions.")
