# First-run API setup

Interactive `loop` checks the selected model with one short text request before opening the conversation interface. The request has no tools or session history and uses the selected profile’s `timeout_s` socket timeout (60 seconds for setup-created profiles). Missing keys, authentication/network failures and unusable text responses open the shared Loop Switch setup wizard. A working connection skips setup. `--once`, non-TTY input and `loop node` skip this startup check and never open the wizard.

The startup banner also reports Fast availability for the selected endpoint/account/model. If the normal connection response reports `priority` or `fast`, it shows `Fast · active (provider default)`. Otherwise, startup makes at most one additional short, tool-free request with `service_tier: "priority"`, using a socket timeout capped at 10 seconds. This probe may incur provider charges. A successful text response reporting `priority` or `fast` shows `Fast · available (probe only)`; rejected, missing, downgraded or failed evidence shows `Fast · not confirmed` and still opens the terminal. This is provider-reported evidence, not an independent speed or billing audit. The probe does not change the profile or subsequent conversation requests; no local Fast toggle is provided yet. See [detection details](research/fast-mode.md).

1. Select a provider number or paste an API URL (`c` for custom).
2. Select the API type: `1` for OpenAI-compatible Chat Completions, `2` for OpenAI Responses. Enter keeps the displayed default.
3. Enter the API key with hidden input.
4. Setup automatically queries the selected URL with the entered key. Choose a model number, press Enter for the displayed default, or type a model ID. If discovery is unavailable, enter the ID manually (preset defaults remain available).

`0` at provider/API-type/model selection, blank key input, or Ctrl-C cancels. The wizard announces local plaintext credential storage before input. Keys use the existing endpoint-bound user credential store with POSIX 0600 permissions. New profiles preserve old profiles and update the shared Master/Expert selection. The standalone wizard saves configuration without inference; interactive startup applies the saved selection and checks it again. A failed check returns to setup instead of entering an unusable conversation. Cancelling does not start the terminal or execute tasks. A saved but failed profile remains available for correction.

Session keys and explicitly configured environment keys still take precedence over saved keys. If a replacement saved key appears ineffective, remove/update the corresponding environment variable before restarting; Loop does not rewrite the user's shell environment. Endpoint changes never forward the previous endpoint's key.

Presets: OpenAI / GPT-6 Astra (recommended), Qwen Beijing/Singapore legacy endpoints, DeepSeek and Kimi Global. They provide default model IDs, not a guarantee of account access. Qwen keys are regional; workspace-specific and subscription/token-platform endpoints can be entered as custom URLs. Use API URLs, not console websites. Pasted URLs ending in `/chat/completions` or `/responses` are normalized to their base URL and suggest the corresponding API type; the user can still select the type explicitly.

After key entry, both preset and custom providers attempt `GET /models` at the selected URL only, using the entered key and disabling redirects (15-second socket timeout, 1 MiB response limit). All returned valid model IDs are shown with global selection numbers, grouped by company A–Z; recognizable model families normalize company names, otherwise `owned_by` is used, with unknown companies last. Within each company, newest catalog date comes first: `released_at`, `release_date`, then `created`; absent usable metadata, an explicit YYYY-MM-DD or YYYYMMDD in the model ID is used. Unknown dates appear last, ties sort by ID. Catalog creation dates are not guaranteed release dates. The default is the preset model if listed, otherwise the first model; every selection requires user input. Invalid numbers prompt again. Empty, failed or unsupported discovery falls back to manual entry without switching endpoints. The list alone does not establish API-type, tool or vision support. Errors do not print keys or API response bodies.

## API types

- `openai` (default for custom and non-OpenAI URLs): Chat Completions, bearer authentication, `/chat/completions`.
- `openai-responses` (default for the OpenAI preset): `/responses`, text/function tools, stateless requests with encrypted reasoning-item replay within the tool loop.
- Native Anthropic Messages, Gemini and Azure-specific authentication are not implemented; use a supported compatible gateway. Unknown protocols are rejected.

`/switch setup` reopens the wizard in the terminal. `loop-switch` now opens quick setup by default. `loop-switch setup expert` is a legacy alias for configuring the same current model; `loop-switch --advanced` opens the previous full profile manager. Existing add/edit/list/pick/use/remove/check commands remain. Use `/switch reload` after an external switch. Protocol changes do not alter endpoint-bound credential identity.

2026-09-07: setup, provider, home and terminal tests plus a real PTY/local HTTP startup test passed. The PTY test covers HTTP 401 → provider/API-type selection → hidden new key → Responses probe → terminal entry and exit. Tests also cover cancellation, repeated failure, empty responses and noninteractive bypass. No live provider/account access was tested.

## Official references checked 2026-09-05

- [Qwen regional endpoints](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)
- [DeepSeek API and model IDs](https://api-docs.deepseek.com/)
- [Kimi quickstart](https://platform.kimi.ai/docs/guide/kimi-k2-6-quickstart)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1)

## Recommended GPT-6 / custom API configuration

Official model ID: `gpt-6-astra`. A custom gateway may expose a different alias; enter the ID actually provided by that gateway. In `loop-switch`, paste the base URL, choose API type `2` (Responses), enter the hidden key and enter the model ID. Custom endpoints retain Chat Completions as their compatibility default until explicitly changed. Do not append `/responses` to the base URL.

A complete key-free example is [config.gpt6.example.json](../configs/config.gpt6.example.json). For a fresh state directory it can be passed with `loop --config /path/to/config.gpt6.example.json`; supply `OPENAI_API_KEY` through the environment. Existing selected profiles take priority: use `loop-switch` to change an existing installation. Never place a key in a configuration example.

The OpenAI preset selects Responses; if a custom gateway supports only Chat Completions, explicitly choose `openai` and verify its token-field requirements. Loop does not send credentials to a fallback endpoint. All roles share the selected model.

Current adapter limitations: Responses answers are buffered, not streamed; output is capped at 4096 tokens and reasoning effort is not configurable. Stateless reasoning items and function-call outputs are preserved. These are protocol capabilities, not proof of model access or task quality. Before release, exercise text, a real file read/edit tool loop, image input when needed, cancellation, and incomplete/error responses against the intended endpoint.

Sources checked 2026-09-07: [GPT-6 Astra model](https://developers.openai.com/api/docs/models/gpt-6-astra), [official model guidance](https://developers.openai.com/api/docs/guides/latest-model). This preparation does not claim a live GPT-6 API test.


## Connection diagnostics

Startup reports sanitized diagnostics for HTTP status, TLS certificate verification, DNS failure, timeout and incompatible response formats. Server error bodies and credentials are never printed. A connection failure does not necessarily mean the key or API type is wrong.

Some standalone Python builds reference an OpenSSL CA path from their build machine. When Python has no CA certificates or default trust paths, Loop tries an existing OS CA bundle for model requests and model discovery. TLS verification and hostname checks stay enabled. Explicit `SSL_CERT_FILE`/`SSL_CERT_DIR` and working default trust stores remain authoritative. Fix invalid server certificates or operator CA configuration instead of disabling verification.

2026-09-07 local verification: the selected custom endpoint with `gpt-5.6-sol` and Chat Completions failed before HTTP with `SSLCertVerificationError` (missing local issuer). Python's default trust store contained zero CAs; the system bundle supplied 147. After the fallback fix, the same saved model/endpoint/key passed the short text check in 2.76 seconds. This checks text access only, not all tools or account capabilities. Restart an already-running Loop process to load the fix.
