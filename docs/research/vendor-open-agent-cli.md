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

## Claude Code 公共仓库具体范围（2026-09-07 补充）

问题：`anthropics/claude-code` 里面主要哪些内容开源？

结论：应区分公开可读内容与开源授权。根 `LICENSE.md` 为保留全部权利、适用 Anthropic 商业服务条款；不是 MIT／Apache 等宽松开源许可证。此仓库公开了扩展示例、配置和维护脚本，但没有提供 Claude Code 核心 CLI 的完整可构建源码，不能通过 fork 此仓库直接构建等价产品。

本次通过 GitHub API 完整递归树核对 main 提交 `ab9b2cf7bb9e4f98ff264c07a22e46d83c29c558`（truncated=false），以及固定提交的插件 manifest。原本本地 reference/Agentic/claude-code 未更新，避免混用版本。

| 公开内容 | 实际用途 |
| --- | --- |
| plugins/ | 自定义命令、Agent 角色／工作流、Skills、Hooks；例如 feature-dev、code-review、pr-review-toolkit、frontend-design、hookify、ralph-wiggum |
| examples/hooks/ | 工具调用前后扩展示例，如 Bash 命令验证 |
| examples/settings/ | 宽松／严格／Bash sandbox 设置样例 |
| examples/gateway/、examples/mdm/ | AWS/GCP 网关部署配置与 Terraform、企业设备管理配置 |
| .devcontainer/、Script/ | 开发容器环境和启动辅助脚本 |
| .claude/commands/、.claude-plugin/ | 仓库内工作流命令、插件 marketplace 清单 |
| scripts/、.github/ | Issue 生命周期、重复问题处理与仓库自动化 |
| README、CHANGELOG、SECURITY | 安装说明、版本变化、安全报告说明 |

许可证边界：该提交递归树中只有根 LICENSE.md 被识别为许可证文件；12 个实际插件目录的 plugin.json 未声明 license 字段。frontend-design/SKILL.md 写有 `license: Complete terms in LICENSE.txt`，但该提交的树中没有配套 LICENSE.txt，因此不能据这行元数据推定 Apache/MIT 授权。未逐文件审计所有嵌入式许可声明；结论是没有确认这些扩展获得独立开源授权，而非声称任何使用都被禁止。README 仍提到 plugin-dev，但该提交树缺其目录，清单可能滞后。

对 Loop ROS 的判断：可研究这些公开扩展如何组织任务阶段、角色、验收、事件回调与迭代停止条件；直接复制或再分发前需确认对应内容的具体许可。它们展示上层配置与工作流，不等于公开底层 Agent 循环、上下文压缩、终端渲染及权限执行引擎实现。该仓库的 agent-sdk-dev 是开发辅助插件，不是完整 Agent SDK 源码。

来源：

- [仓库及 README](https://github.com/anthropics/claude-code)
- [根许可证](https://github.com/anthropics/claude-code/blob/ab9b2cf7bb9e4f98ff264c07a22e46d83c29c558/LICENSE.md)
- [插件介绍](https://github.com/anthropics/claude-code/blob/ab9b2cf7bb9e4f98ff264c07a22e46d83c29c558/plugins/README.md)
- [示例目录](https://github.com/anthropics/claude-code/tree/ab9b2cf7bb9e4f98ff264c07a22e46d83c29c558/examples)
- [frontend-design Skill 元数据](https://github.com/anthropics/claude-code/blob/ab9b2cf7bb9e4f98ff264c07a22e46d83c29c558/plugins/frontend-design/skills/frontend-design/SKILL.md)
- [完整目录树 API](https://api.github.com/repos/anthropics/claude-code/git/trees/ab9b2cf7bb9e4f98ff264c07a22e46d83c29c558?recursive=1)

验证：仅在线只读核对与项目报告归档，未安装、运行或修改 Claude Code，也未把其内容复制进 Loop ROS。
