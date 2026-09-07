"""Shared provider setup and interactive startup connection recovery."""
import getpass
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.request import Request, build_opener

from loop_robot.terminal.config import validate_provider
from loop_robot.terminal.home import save_key
from loop_robot.terminal.llm import NoRedirect, QwenClient, ModelAPIError, model_https_handler

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
            from loop_robot.terminal.reasoning import metadata
            levels = metadata(item)
            if levels is not None:
                model['reasoning_efforts'] = levels
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
    write("  s. Saved profiles / reuse key")
    write("  c. Custom URL / token platform    0. Cancel")
    choice = read("Provider number or API base URL [1]: ").strip() or "1"
    if choice == "0":
        return None
    if choice.lower() == "s":
        return recover_profile(store, read=read, write=write, offer_setup=False)
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
    default = "1"
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
        counts = {}
        visible = []
        for item in models:  # Discovery already sorts each company newest first.
            company = item['company']
            counts[company] = counts.get(company, 0) + 1
            if counts[company] <= 10:
                visible.append(item)
        models = visible
        write("Available models: latest 10 per company, company A-Z; unknown dates last. Enter any model ID manually.")
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
    # Keep the latest setup for the same endpoint and credential.
    import uuid
    name = "setup-" + uuid.uuid4().hex[:12]
    save_key(config, key)
    store.save(name, config)
    store.use(slot, name)
    store.deduplicate(newest=name)
    write("Saved. {} uses {} · {}. API access is not yet verified.".format("Current model", model, config["protocol"]))
    return name


def check_connection(client):
    """Check connectivity, then best-effort Fast support without changing the profile."""
    key = client.resolved_key()
    if not key:
        raise ModelAPIError("No API key configured")
    probe = QwenClient(dict(client.config))
    probe.key = key
    try:
        result = probe.complete([{"role": "user", "content": "Reply with OK only."}], [])
        if not isinstance(result, dict) or not isinstance(result.get("content"), str) or not result["content"].strip():
            raise ModelAPIError("Model returned no text; check the model ID and API type")
    except ModelAPIError as exc:
        if exc.status not in (None, 400, 403, 404):
            raise
        if check_alternative_models(client, key):
            # Fast evidence for another model does not apply to the selected model.
            return 'unknown'
        raise
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


def check_alternative_models(client, key):
    """Verify this API with up to three catalog models, preserving user selection."""
    print('Checking other models on the same API (up to 3 short requests; provider charges may apply)...', flush=True)
    try:
        models = discover_models(client.config, key)
    except ValueError:
        return False
    candidates = [item['id'] for item in models
                  if item['id'] != client.config['model']
                  and not re.search(r'embedding|rerank|whisper|tts|transcri|dall-e', item['id'], re.I)]
    for model in candidates[:3]:
        probe = QwenClient({**client.config, 'model': model,
                            'timeout_s': min(client.config['timeout_s'], 10)})
        probe.key = key
        print('Checking API with model {}...'.format(model), flush=True)
        try:
            result = probe.complete([{'role': 'user', 'content': 'Reply with OK only.'}], [])
        except ModelAPIError as exc:
            if exc.status == 401:
                return False
            continue
        except (RuntimeError, ValueError, OSError):
            continue
        if isinstance(result, dict) and isinstance(result.get('content'), str) and result['content'].strip():
            print('API connected using {}. Selected model {} is unchanged and failed its check; use /switch to choose a working model.'.format(model, client.config['model']), flush=True)
            return True
    return False


def recover_profile(store, read=None, write=print, offer_setup=True):
    """Choose existing state before asking for new credentials; no network here."""
    read = read or input
    store.deduplicate()
    profiles = store.list()
    if not profiles:
        if offer_setup:
            return quick_setup(store)
        write('No saved profiles. Run setup to add one.')
        return None
    if offer_setup and all(item['connection_check']['status'].startswith('failed') for item in profiles):
        write('All saved profiles failed their latest connection checks. Enter a new configuration.')
        return quick_setup(store)
    write('Saved profiles (selection reuses saved credentials):')
    for index, item in enumerate(profiles, 1):
        active = ' [default/current]' if 'master' in item['active_for'] else ''
        write('  {}. {} | {} | {}{}'.format(index, item['model'], item.get('protocol', 'openai'), item['base_url'], active + ' | ' + item['connection_check']['status'] + (' @ ' + item['connection_check']['checked_at'] if item['connection_check']['checked_at'] else '')))
    while True:
        prompt = 'Profile number, r retry, n new setup, 0 cancel: ' if offer_setup else 'Profile number, r retry current, 0 cancel: '
        answer = read(prompt).strip().lower()
        if answer in ('', '0'):
            return None
        if answer == 'r':
            return store.selected()['master']
        if answer == 'n' and offer_setup:
            return quick_setup(store)
        if answer.isdigit() and 1 <= int(answer) <= len(profiles):
            name = profiles[int(answer)-1]['name']
            store.use('master', name)
            return name
        write('Choose a listed profile, r or 0.' if not offer_setup else 'Choose a listed profile, r, n or 0.')


def ensure_setup(app, interactive):
    app.startup_fast_status = None
    if not interactive:
        return True
    while True:
        try:
            print("Checking model connection (short request, no tools)...", flush=True)
            app.startup_fast_status = check_connection(app.client)
            app.providers.record_check('passed')
            print("API connection verified.")
            return True
        except (EOFError, KeyboardInterrupt):
            print("\nConnection check cancelled.")
            return False
        except (RuntimeError, ValueError, OSError) as exc:
            status = 'failed'
            if isinstance(exc, ModelAPIError):
                match = re.search(r'HTTP (\d{3})', str(exc))
                if match:
                    status += ' (HTTP ' + match.group(1) + ')'
            app.providers.record_check(status)
            # No raw exception/response text: gateways and local paths may contain secrets.
            print("Model connection failed. " + (str(exc) if isinstance(exc, ModelAPIError)
                  else "Check API URL, key, model ID and API type."))
            print("Choose a saved profile or configure a new one. Saved endpoint keys take precedence over environment keys.")
        while True:
            try:
                name = recover_profile(app.providers)
                if name is None:
                    return False
                app.apply_profiles()
                break
            except (EOFError, KeyboardInterrupt):
                print("\nSetup cancelled.")
                return False
            except (ValueError, OSError):
                print("Setup could not be saved. Check the URL, API type and user configuration permissions.")
