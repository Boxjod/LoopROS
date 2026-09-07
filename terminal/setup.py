"""Shared first-run and standalone Switch setup; no inference requests."""
import getpass
import hashlib
import json
from urllib.request import Request, build_opener

from terminal.config import validate_provider
from terminal.home import save_key
from terminal.llm import NoRedirect

# Public endpoints, not subscriptions or guarantees of account access.
PRESETS = [
    ("OpenAI / GPT-6 Astra (recommended)", "https://api.openai.com/v1", "gpt-6-astra"),
    ("Qwen / Beijing (legacy endpoint)", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    ("Qwen / Singapore (legacy endpoint)", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    ("DeepSeek", "https://api.deepseek.com", "deepseek-v4-flash"),
    ("Kimi / Global", "https://api.moonshot.ai/v1", "kimi-k2.6"),
]


def discover_models(config, key):
    request = Request(config["base_url"].rstrip("/") + "/models",
                      headers={"Authorization": "Bearer " + key})
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError()
        ids = [item["id"] for item in json.loads(raw)["data"]]
        return sorted({name for name in ids if isinstance(name, str) and name.isprintable() and 0 < len(name) <= 200})
    except Exception:
        raise ValueError("Model discovery unavailable; enter a model ID in advanced settings.") from None


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
    if url.endswith(("/chat/completions", "/responses")):
        raise ValueError("Enter the base URL, not a full chat/completions or responses endpoint")
    config = {"base_url": url, "model": model or "pending", "timeout_s": 60,
              "api_key_env": "LOOP_KEY_" + hashlib.sha256(url.encode()).hexdigest()[:16].upper(),
              "protocol": "openai-responses" if url == "https://api.openai.com/v1" else "openai"}
    validate_provider(config)  # Reject credential URLs before asking for a secret.
    write("The key will be saved locally in Loop ROS user home (plaintext, private permissions).")
    key = secret("API key (hidden; Enter to cancel): ").strip()
    if not key:
        return None
    advanced = read("Enter to save defaults, or 'a' for advanced model/protocol: ").strip().lower()
    if advanced not in ("", "a"):
        raise ValueError("Expected Enter or a; nothing saved")
    if advanced == "a":
        config["protocol"] = read("Protocol [{}] (openai / openai-responses): ".format(config["protocol"])).strip() or config["protocol"]
        model = read("Model ID [{}]: ".format(model or "auto-discover")).strip() or model
    validate_provider(config)
    if not model:
        write("Discovering models from the selected URL only (GET /models; no inference).")
        try:
            models = discover_models(config, key)
        except ValueError as exc:
            write(str(exc))
            models = []
        if len(models) == 1:
            model = models[0]
        else:
            if models:
                write("Available model IDs: " + ", ".join(models[:40]))
            model = read("Model ID (required; Enter to cancel): ").strip()
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


def ensure_setup(app, interactive):
    if not interactive or app.client.resolved_key():
        return True
    print("No Master API key configured. Opening Loop Switch.")
    while True:
        try:
            name = quick_setup(app.providers)
            break
        except (EOFError, KeyboardInterrupt):
            print("\nSetup cancelled.")
            return False
        except (ValueError, OSError) as exc:
            print("Setup error: " + str(exc))
    if name is None:
        return False
    app.apply_profiles()
    return True
