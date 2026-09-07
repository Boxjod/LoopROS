# First-run API setup

Interactive `loop` opens the shared Loop Switch wizard when Master has no session, environment or saved key. This happens before timers start. Configured users skip it; `--once` and non-TTY input never open it. A present but expired key is not detected automatically.

1. Select a provider number or paste an API base URL (`c` for custom).
2. Enter the API key with hidden input.
3. Press Enter to save defaults, or `a` for advanced model/protocol settings.

`0` or Ctrl-C cancels. The wizard announces local plaintext credential storage before input. Keys use the existing endpoint-bound user credential store with POSIX 0600 permissions. New profiles use endpoint-specific environment variable names, preserve old profiles and update the shared Master/Expert selection, and select the newly saved profile. No inference request is sent during setup.

Presets: OpenAI / GPT-6 Astra (recommended), Qwen Beijing/Singapore legacy endpoints, DeepSeek and Kimi Global. They provide default model IDs, not a guarantee of account access. Qwen keys are regional; workspace-specific and subscription/token-platform endpoints can be entered as custom URLs. URLs must be API base URLs, not console websites or full chat/completions paths.

For custom platforms without a known model, setup attempts `GET /models` at the selected URL only, using the entered key and disabling redirects. A single model is selected automatically. Multiple models or failed discovery require an explicit model ID; the list alone does not establish tool support. There is no universal model default for arbitrary platforms. Errors do not print keys or API response bodies.

## Advanced options

- `openai` (default for custom and non-OpenAI URLs): Chat Completions, bearer authentication, `/chat/completions`.
- `openai-responses` (default for the OpenAI preset): `/responses`, text/function tools, stateless requests with encrypted reasoning-item replay within the tool loop.
- Native Anthropic Messages, Gemini and Azure-specific authentication are not implemented; use a supported compatible gateway. Unknown protocols are rejected.

`/switch setup` reopens the wizard in the terminal. `loop-switch` now opens quick setup by default. `loop-switch setup expert` is a legacy alias for configuring the same current model; `loop-switch --advanced` opens the previous full profile manager. Existing add/edit/list/pick/use/remove/check commands remain. Use `/switch reload` after an external switch. Protocol changes do not alter endpoint-bound credential identity.

65 tests passed: setup defaults/custom discovery, cancellation, startup gating, secret isolation and Responses tool/reasoning replay. Real PTY first-run cancellation was verified with isolated state. No live API authentication/inference was tested.

## Official references checked 2026-09-05

- [Qwen regional endpoints](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)
- [DeepSeek API and model IDs](https://api-docs.deepseek.com/)
- [Kimi quickstart](https://platform.kimi.ai/docs/guide/kimi-k2-6-quickstart)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1)

## Recommended GPT-6 / custom API configuration

Official model ID: `gpt-6-astra`. A custom gateway may expose a different alias; enter the ID actually provided by that gateway. In `loop-switch`, paste the base URL, enter the hidden key, select `a`, choose `openai-responses` and enter the model ID. Custom endpoints retain Chat Completions as their compatibility default until explicitly changed. Do not append `/responses` to the base URL.

A complete key-free example is [config.gpt6.example.json](../config.gpt6.example.json). For a fresh state directory it can be passed with `loop --config /path/to/config.gpt6.example.json`; supply `OPENAI_API_KEY` through the environment. Existing selected profiles take priority: use `loop-switch` to change an existing installation. Never place a key in a configuration example.

The OpenAI preset selects Responses; if a custom gateway supports only Chat Completions, explicitly choose `openai` and verify its token-field requirements. Loop does not send credentials to a fallback endpoint. All roles share the selected model.

Current adapter limitations: Responses answers are buffered, not streamed; output is capped at 4096 tokens and reasoning effort is not configurable. Stateless reasoning items and function-call outputs are preserved. These are protocol capabilities, not proof of model access or task quality. Before release, exercise text, a real file read/edit tool loop, image input when needed, cancellation, and incomplete/error responses against the intended endpoint.

Sources checked 2026-09-07: [GPT-6 Astra model](https://developers.openai.com/api/docs/models/gpt-6-astra), [official model guidance](https://developers.openai.com/api/docs/guides/latest-model). This preparation does not claim a live GPT-6 API test.
