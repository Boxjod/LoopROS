# Fast 模式开启与检测

核对日期：2026-09-07。问题：服务商 URL/API Key 支持 Fast 时，LoopROS 如何使用并验证？

## 结论与边界

- OpenAI 官方支持在 Responses 或 Chat Completions 请求中设置 `service_tier: "fast"`，支持模型也可用 `"priority"`。可在官方项目 Settings → General → Project Service Tier 设置 Fast，让未指定档位的请求使用项目默认值；切换逐步生效。Fast 单价高于 Standard。
- LoopROS 当前 [配置校验](../../terminal/config.py) 不接受该字段，[协议编码](../../terminal/protocols.py) 不默认发送该字段；[客户端](../../terminal/llm.py) 已支持仅为启动探测传入 `priority`。没有持久化 Fast 开关；若上游默认开启，仍可能生效，实际用户服务商未实测。
- 自定义服务商的兼容性必须按 URL、Key 所属账号、模型、协议分别验证，不能由域名、模型名称或普通连通性推出。

## 手动检测方法（未调用真实服务商）

1. 使用当前 profile 的地址、模型和原有凭据入口，先发一条无工具、无历史的短请求，明确 `service_tier: "default"`，确认基础调用正常。
2. 保持其余参数不变，使用 `service_tier: "priority"`；服务商明确支持新名称时也可使用 `"fast"`。Responses 的示例请求体：`{"model":"当前模型ID","input":"只回复 OK","service_tier":"priority","stream":false,"store":false,"max_output_tokens":128}`。token 上限包含推理，耗尽不等于不支持 Fast。
3. 检查原始响应中的 `service_tier`。官方 API 参考说明 Fast/priority 请求返回 priority；Fast 指南至少明确 GPT-5.6 及更早模型如此。其他模型或第三方返回 fast 时，按该服务商文档核对其含义。返回 default 表示本次使用标准档，不能仅此判定永久不支持（官方可能降档）。缺失字段或仅 HTTP 200 为无法确认。
4. 明确拒绝档位参数表示当前请求组合不可用；401/403/429、超时、余额问题需要单独诊断，不能一概归为 Fast 不支持。第三方可能忽略或回显参数，需用服务商请求记录或账单中的档位交叉验证。
5. 若评估加速收益，多次交错比较同模型、同推理设置的普通/Fast 请求，观察首 token 延迟与输出速率；一次耗时不能证明支持。检测产生模型调用费用，不更改长期默认配置。

## 2026-09-07：启动提示已接入

用户要求启动时提示 Fast 支持情况。[启动检查](../../terminal/setup.py) 先使用既有普通连接请求，若返回 priority/fast，欢迎页显示 `Fast · active (provider default)`，不再探测。否则最多增加一条 priority 短请求，socket 超时为 profile timeout 与 10 秒的较小值；收到有效文本及 priority/fast 回执时显示 `Fast · available (probe only)`。缺失字段、default、参数拒绝、错误或超时显示 `Fast · not confirmed`，不阻止正常进入终端。只信任固定档位枚举，不显示网关原始文本。

普通对话请求、用户配置与推理强度保持原样；非交互、--once 和 node 入口跳过检查。两种 API 均支持此检测；这是服务端自报证据，第三方真实性仍需账单或服务商日志佐证。仅支持 fast 新别名而拒绝 priority 的网关会显示未确认，不自动追加重试。

### 2026-09-07：前台运行时开关

已新增 `/fast [on|off|status]`：无参数切换，on 为 priority、off 为 default；后续前台请求采用该档位，非流式与流式回执均可记录服务端返回的档位。开关不发送探测请求，不修改 profile，不宣称服务商已支持；重建客户端后重置。之前的“没有持久化开关”仍成立，但现在已有运行时开关。模型服务端真实支持仍未实测，本轮使用本地 HTTP 替身验证两种 API 的请求与回执。

## 来源与验证状态

- [OpenAI Fast mode](https://developers.openai.com/api/docs/guides/fast-mode)：已读取，支持配置、回执、降档与计费结论。
- [OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)：已打开核对，`service_tier` 参数与实际处理档位。
- 已检查本地配置和请求路径并实现启动检测提示；验证使用本地 HTTP 替身和 PTY，真实服务商未测，未修改用户 Key 或开启长期 Fast。
