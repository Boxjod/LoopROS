# First-run API setup

Interactive `loop` checks the selected model with one short text request before opening the conversation interface. The request has no tools or session history and uses the selected profile’s `timeout_s` socket timeout (60 seconds for setup-created profiles). If the selected model fails with a model/request error or unusable text, startup queries the same endpoint’s model catalog and tries up to three other models, excluding recognizable embedding/rerank/audio-only IDs. Each alternative uses the same URL, API type and resolved key, no tools/history, and a socket timeout capped at 10 seconds. These requests may incur provider charges. A nonempty text response from any candidate verifies API access and opens the terminal; the selected model remains unchanged, and a message identifies the working model and directs the user to `/switch`. This does not verify the selected model or tool support. HTTP 401 skips alternatives. If no candidate succeeds or discovery is unavailable, the existing recovery flow opens. A working connection skips setup. `--once`, non-TTY input and `loop node` skip this startup check and never open the wizard.

The startup banner also reports Fast availability for the selected endpoint/account/model. If the normal connection response reports `priority` or `fast`, it shows `Fast · active (provider default)`. Otherwise, startup makes at most one additional short, tool-free request with `service_tier: "priority"`, using a socket timeout capped at 10 seconds. This probe may incur provider charges. A successful text response reporting `priority` or `fast` shows `Fast · available (probe only)`; rejected, missing, downgraded or failed evidence shows `Fast · not confirmed` and still opens the terminal. This is provider-reported evidence, not an independent speed or billing audit. The probe does not change the profile or subsequent conversation requests; no local Fast toggle is provided yet. See [detection details](research/fast-mode.md).

1. Select a provider number or paste an API URL (`c` for custom).
2. Select the API type: `1` for OpenAI-compatible Chat Completions, `2` for OpenAI Responses. Enter selects `1` (Chat Completions) for every provider; choose `2` explicitly for Responses. Existing saved profiles are unchanged.
3. Enter the API key with hidden input.
4. Setup automatically queries the selected URL with the entered key. Choose a model number, press Enter for the displayed default, or type a model ID. If discovery is unavailable, enter the ID manually (preset defaults remain available).

`0` at provider/API-type/model selection, blank key input, or Ctrl-C cancels. The wizard announces local plaintext credential storage before input. Keys use the existing endpoint-bound user credential store with POSIX 0600 permissions. New profiles preserve old profiles and update the shared Master/Expert selection. The standalone wizard saves configuration without inference; interactive startup applies the saved selection and checks it again. A failed check returns to setup instead of entering an unusable conversation. Cancelling does not start the terminal or execute tasks. A saved but failed profile remains available for correction.

Session keys and explicitly configured environment keys still take precedence over saved keys. If a replacement saved key appears ineffective, remove/update the corresponding environment variable before restarting; Loop does not rewrite the user's shell environment. Endpoint changes never forward the previous endpoint's key.

Presets: OpenAI / GPT-6 Astra (recommended), Qwen Beijing/Singapore legacy endpoints, DeepSeek and Kimi Global. They provide default model IDs, not a guarantee of account access. Qwen keys are regional; workspace-specific and subscription/token-platform endpoints can be entered as custom URLs. Use API URLs, not console websites. Pasted URLs ending in `/chat/completions` or `/responses` are normalized to their base URL with API type defaulting to option 1; select option 2 explicitly for Responses.

After key entry, both preset and custom providers attempt `GET /models` at the selected URL only, using the entered key and disabling redirects (15-second socket timeout, 1 MiB response limit). Only the latest 10 valid model IDs per company are shown with continuous global selection numbers; other IDs can still be entered manually. Models are grouped by company A–Z; recognizable model families normalize company names, otherwise `owned_by` is used, with unknown companies last. Within each company, newest catalog date comes first: `released_at`, `release_date`, then `created`; absent usable metadata, an explicit YYYY-MM-DD or YYYYMMDD in the model ID is used. Unknown dates appear last, ties sort by ID. Catalog creation dates are not guaranteed release dates. The default is the preset model if listed, otherwise the first model; every selection requires user input. Invalid numbers prompt again. Empty, failed or unsupported discovery falls back to manual entry without switching endpoints. The list alone does not establish API-type, tool or vision support. Errors do not print keys or API response bodies.

## API types

- `openai` (default for all providers): Chat Completions, bearer authentication, `/chat/completions`.
- `openai-responses` (select option 2 explicitly): `/responses`, text/function tools, stateless requests with encrypted reasoning-item replay within the tool loop.
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

Current adapter limitations: Responses answers are buffered, not streamed; the default output cap is 4096 tokens (profile configurable); `/model` selection includes model-specific reasoning choices in the same menu. Stateless reasoning items and function-call outputs are preserved. These are protocol capabilities, not proof of model access or task quality. Before release, exercise text, a real file read/edit tool loop, image input when needed, cancellation, and incomplete/error responses against the intended endpoint.

Sources checked 2026-09-07: [GPT-6 Astra model](https://developers.openai.com/api/docs/models/gpt-6-astra), [official model guidance](https://developers.openai.com/api/docs/guides/latest-model). This preparation does not claim a live GPT-6 API test.


## Connection diagnostics

Startup reports sanitized diagnostics for HTTP status, TLS certificate verification, DNS failure, timeout and incompatible response formats. Server error bodies and credentials are never printed. A connection failure does not necessarily mean the key or API type is wrong.

Some standalone Python builds reference an OpenSSL CA path from their build machine. When Python has no CA certificates or default trust paths, Loop tries an existing OS CA bundle for model requests and model discovery. TLS verification and hostname checks stay enabled. Explicit `SSL_CERT_FILE`/`SSL_CERT_DIR` and working default trust stores remain authoritative. Fix invalid server certificates or operator CA configuration instead of disabling verification.

2026-09-07 local verification: the selected custom endpoint with `gpt-5.6-sol` and Chat Completions failed before HTTP with `SSLCertVerificationError` (missing local issuer). Python's default trust store contained zero CAs; the system bundle supplied 147. After the fallback fix, the same saved model/endpoint/key passed the short text check in 2.76 seconds. This checks text access only, not all tools or account capabilities. Restart an already-running Loop process to load the fix.

Saved URLs and plaintext API keys live together in `~/.loop/config.json`, under `endpoints` (`base_url`, `api_key_env`, `api_key`). `/key` (also `/key save`) writes the shared chat/agent/task credential to this file with mode 0600; legacy credentials.json migrates on use. Keys remain omitted from settings output and model context. Restart older running CLI processes after migration.


### Startup recovery (2026-09-08)

Interactive startup checks the selected profile with one short model request. If that succeeds without confirming priority/fast tier, one optional Fast probe follows; a failed first request does not trigger the Fast probe. Each explicitly selected retry/profile repeats this sequence. Noninteractive calls skip startup probes.

Connection failure now lists saved profiles (model, API type, URL and current selection) before offering new setup. Choose a number to reuse its stored endpoint credentials, `r` to retry, `n` to create a profile, or `0`/Enter to cancel. Selection alone does not discover models or request a key; only new setup does. The selection persists through ProviderStore. Current credential order is explicit in-process key, saved endpoint key, then environment fallback; the old environment-first recovery message was incorrect and has been replaced.

Validation: test_setup, test_setup_startup, test_model_connection, test_fast_startup; saved-profile reuse without key prompt/network discovery, cancel/retry retention, and real PTY/local HTTP 401 recovery. No live provider requests were sent for these tests.

重复配置：新建配置成功及启动恢复菜单打开时，同一 API base URL 仅保留最新添加项的模型和接口配置，不再依赖 Key 是否存在或相等；默认引用随之迁移。删除的默认配置不会在重启后重建。不同 API 路径不自动视为相同服务。列表保留默认标记及带时间的实际测试状态；配置或 Key 改变后显示 untested。

### 全部配置检测失败（2026-09-08）

恢复时若所有已保存配置的最近有效检查均为 failed，直接进入新配置向导；存在 passed 或 untested 则保留选择菜单。不后台遍历付费试跑，也不删除原配置。更换 Key/配置后，旧检查失效，不据过时失败记录跳过选择。

交互启动要求所选 URL、Key、API 类型下至少一个检测模型能够完成短文本请求，不要求机器人已连接。当前模型失败时最多尝试目录内另外 3 个模型；成功后保留原模型选择，提示用户进入后通过 /switch 更换。passed 记录表示 API 短文本访问通过，不保证原模型可用；替代模型成功不作为当前模型 Fast 能力证据。旧窗口可继续使用内存中的模型/凭据，因此“旧窗口能用”不能证明磁盘当前默认配置能用。HTTP 404 表明所请求的接口或模型路由不可用，不能据此认定 URL 整体不可达或并发窗口受限。

用户所贴 qwen3.7-text-rerank 名称指向重排用途；[Alibaba 官方模型 API 类型表](https://www.alibabacloud.com/help/tc/api-gateway/ai-gateway/user-guide/managing-the-model-api)区分 rerank 专用路径与聊天接口。未对这个精确 ID 做账户兼容性验收。模型目录当前只按公司和日期展示，并不保证每个条目都适合作为聊天模型。

2026-09-08：新配置向导首屏提供 `s. Saved profiles / reuse key`。输入 s 可返回已保存地址/模型列表，复用原 Key；即使所有配置曾检测失败，也不会再次强制跳回新配置。选择不会访问模型目录或要求重输 Key，后续启动仍执行真实连接检查。
