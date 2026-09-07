# 大模型厂商开源 CLI 与 Agent harness

核对日期：2026-09-07。问题：有哪些模型厂商公开了类似 Codex 的 CLI 及背后的 Agent 执行实现？

## 口径与结论

这里的 harness 指模型调用循环、工具执行、上下文与会话管理等运行层，不指模型权重或评测 harness。CLI 是交互入口；公开 API SDK 不自动意味着产品执行层开源。以下为已确认的代表项目，非完整厂商名录。

| 厂商 | 官方项目与来源 | 仓库许可 | 范围 |
| --- | --- | --- | --- |
| OpenAI | [Codex CLI](https://github.com/openai/codex) | Apache-2.0 | 本地 CLI 与执行核心；仓库包含 codex-rs、SDK 等 |
| Google | [Gemini CLI](https://github.com/google-gemini/gemini-cli) | Apache-2.0 | 终端 Agent 与工具执行实现，包含文件、Shell、MCP 等能力 |
| 阿里巴巴／Qwen | [Qwen Code](https://github.com/QwenLM/qwen-code) | Apache-2.0 | 终端 coding agent 的实现 |
| 月之暗面／Moonshot AI | [Kimi Code CLI](https://github.com/MoonshotAI/kimi-cli) | Apache-2.0 | CLI 与 Agent 实现；包含 Python 包及其测试 |
| Mistral AI | [Mistral Vibe](https://github.com/mistralai/mistral-vibe) | Apache-2.0 | CLI coding agent 实现；包含 Python 工程、Skills 与 hooks |

这些项目可作为阅读 CLI 与本地 harness 的入口，但不能据此推定厂商内部训练、评测或云端运行系统全部公开。

## 容易混淆的边界

- Anthropic 的 Claude Code 有公开 GitHub 仓库，但其 [LICENSE.md](https://github.com/anthropics/claude-code/blob/main/LICENSE.md) 声明保留全部权利并适用商业服务条款，不能归为上述开源 CLI。公开仓库、SDK 或流出的代码均不能单独证明产品 harness 获得开源许可。
- OpenAI 的[官方开源组件说明](https://learn.chatgpt.com/docs/open-source)明确列出 Codex CLI、SDK 与 App Server，并将 IDE extension、Codex cloud 标为非开源。不能把 Codex CLI 开源扩大解释为整个 Codex 产品开源。
- 软件仓库的许可证与模型权重、API 服务的许可及费用是不同问题。

## 对 Loop ROS 的阅读建议（推断）

若目标是参考 Python 实现，可先读 Kimi CLI 和 Mistral Vibe；若目标是研究 Codex 本地运行架构，可从 codex-rs 入手。这里只提出源码阅读入口，不构成性能排名或直接集成结论。

## 验证状态

初次调研在线打开官方文档与上述官方仓库，核对 README／仓库许可标识及 Claude Code 许可证正文。直接获取 raw.githubusercontent.com 文件失败，使用成功读取的 GitHub 页面交叉确认。后续按用户要求补齐本地副本，状态如下。

## 2026-09-07 本地克隆交付

位置：[reference/Agentic 清单](../../reference/Agentic/README.md)。本轮新增 gemini-cli、qwen-code、kimi-cli、mistral-vibe 四个普通 Git 克隆；codex、claude-code 已存在且 origin 正确，复用原版本，未拉取或切换。

六个仓库均为非浅克隆，已核对 origin、HEAD、本地许可证、干净工作区及 `git fsck --connectivity-only`，提交哈希记录在上述清单。Claude Code 本地 LICENSE.md 同样声明保留全部权利。未安装依赖、初始化子模块、运行项目或逐文件审计执行循环。后续复用代码时应按选定版本核对 LICENSE、NOTICE 与单独许可文件。
