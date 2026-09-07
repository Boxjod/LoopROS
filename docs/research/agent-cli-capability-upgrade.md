# Agent CLI 源码对照与 Loop ROS 能力补齐

日期：2026-09-07。目标：参考已下载厂商 CLI，补充上下文、对话终端、功能包、多进程／多线程／多 Agent 和稳定性。修改限 Loop ROS，保留第三方源码及用户已有配置。

## 源码证据与取舍

本轮重点阅读以下本地官方实现，版本见 [仓库清单](../../reference/Agentic/README.md)：

- [Kimi compaction](../../reference/Agentic/kimi-cli/src/kimi_cli/soul/compaction.py)：区分实际 usage 与临时估算，按窗口阈值判断压缩，保留部分近期消息。
- [Mistral compaction manager](../../reference/Agentic/mistral-vibe/vibe/core/compaction/manager.py)：在本地副本生成摘要，成功后才改变会话边界，避免失败破坏历史。
- [Mistral SkillManager](../../reference/Agentic/mistral-vibe/vibe/core/skills/manager.py)：区分技能来源、发现与目录元数据，正文按需使用。
- [Kimi subagent runner](../../reference/Agentic/kimi-cli/src/kimi_cli/subagents/runner.py)：显式区分子运行失败、取消、完成，并独立处理子 Agent 运行输出。

这些是设计依据，不是性能比较；未复制或执行第三方代码。本轮未逐项审计全部六个 CLI。Claude Code 公开仓库不据此视为完整开源 harness。

## 已实现

| 原缺口 | 当前行为 | 权威实现／验证 |
| --- | --- | --- |
| /compact 删除内存旧历史，后续保存可能丢失原文 | 仅改变模型视图，/compact reset 恢复默认，历史完整保留 | [context_window](../../terminal/context_window.py)、test_context_window、test_control、test_session_resume |
| 不论消息长短固定取8条 | 默认最多32条、12000字符等价预算，保留完整用户/助手组；较早用户请求有限摘录不作为执行证据 | [llm](../../terminal/llm.py)、test_context_window、test_coding_agent |
| /context 无法区分存档与实际模型窗口 | 显示选入、遗漏、字符预算及计量边界 | [control](../../terminal/control.py)、test_slash_terminal |
| 超长工具结果直接切 JSON 字符串；工具循环正文不断增长 | 单结果显式 JSON 截断；累计工具正文超48000字符优先缩短旧结果，保持协议配对 | context_window、test_context_window |
| Skill 配套说明与脚本不可按包展开 | skill_read 支持包内 path 与行分页，返回受限资源清单；读取不执行 | [skills](../../terminal/skills.py)、test_skills |
| Skill 自动目录无预算且读取权限不完整 | 自动目录约12000字符预算；skill_list/read 走权限，禁止目录读取时禁用自动目录注入 | skills、[conversation_context](../../terminal/conversation_context.py)、test_skills |
| 默认子 Agent 偏向仿真 | 新增 Reader，只读项目文件／列目录／搜索，继续使用共享资源和 broker 门禁 | [角色默认值](../../configs/agents.json)、[agents](../../terminal/agents.py)、test_agents、test_agent_ipc |
| 同步 broker 轮询可能占用 UI 事件循环 | 专用单监管线程处理轮询及通知锁等待，主模型线程与子 Agent 进程职责独立 | [interactive](../../terminal/interactive.py)、test_slash_terminal、test_steering_render |
| 单个子进程 IPC 可长时间占据轮询，畸形消息可能冒泡 | 每进程每次最多16条；坏消息局部失败，退出后继续排空待收结果 | agents、test_agents |
| 工具观察回调异常掩盖实际回执 | 保留原工具结果并附 observer_error，提醒不可盲重试 | agents、test_agents |

## 使用

- `/context` 查看上下文视图；`/compact` 缩为8条窗口；`/compact reset` 恢复32条。
- `skill_read {"name":"你的技能名","path":"references/guide.md","offset":1,"limit":80}` 按需读包内资料。
- 默认角色配置下可 `/spawn Reader 阅读当前项目的上下文实现，列出文件路径和具体问题`。多个 Reader 可承担独立阅读子任务。用户已有 agents.json 整体覆盖默认值，需在自己的角色配置加入 Reader 后重启，不自动覆盖定制。

## 边界

上下文按字符和媒体项估算，不是整个模型请求 token 上限；系统提示、schema、当前输入等另计。旧要求摘录会丢细节，需要时查完整历史。窗口偏好在当前进程有效，重启恢复默认。未增加额外模型摘要请求。

功能包本轮扩展的是已有 Skills；未实现通用插件市场、安装钩子或任意第三方代码自动加载。Reader 不具备写入或执行工具。多 Agent 仍使用进程隔离与共享资源准入，宿主工具串行；单监管线程属于宿主固定开销，没有新增资源账本。长工具不能硬中断，退出可能等待；没有宣称任意线程或子进程都能安全取消。

## 验证

首轮综合专项78项通过（20.896秒），覆盖上下文、控制命令、Skills、实际子进程与 IPC、历史恢复、执行中追加输入、coding工具、CLI交互与中文流式 PTY。随后 Skill 目录预算专项12项通过；最终坏消息／公平排空与技能回归结果见 [RUNBOOK](../RUNBOOK.md)。PTY 使用本地替身模型与人为延迟的监管线程，未调用付费模型、真机或启动／重启 MuJoCo。


## 2026-09-07 追加：CLI 与 Agent 交互，以及当前完成范围

已增加按标题选目标、运行时稳定短编号、角色/收件人选完继续输入正文、动态 Agent 面板、入站消息投递回执、已知同伴结果读取。修复部分 slash Agent 命令绕过工具门禁的问题。新增功能不改变进程所有权与资源准入，也不允许同伴递归启动/取消。

不能用未经定义的百分比宣称“复刻了多少”。当前能力分层为：

| 能力 | 当前程度 | 尚未覆盖 |
| --- | --- | --- |
| 模型与工具执行 | 基础闭环已实现并有测试 | 不代表各服务商协议与功能完全一致 |
| CLI输入与会话 | 流式、草稿、队列、标题、恢复与导出已实现 | 会话分支、成熟编辑器级工作流 |
| 上下文 | 有界视图、无损缩窗与有限历史摘录 | 精确整请求token准入、模型摘要压缩 |
| 扩展 | Skills包、用户工具和角色配置 | 通用插件生态与市场 |
| 多Agent | 进程并行、消息、回执、结果、取消与资源准入 | 独立worktree、会话恢复、复杂依赖编排 |
| 稳定性 | 针对性协议、权限、并发和PTY回归 | 跨平台长期实测、任意长工具硬中断 |

这是 Loop ROS 当前代码的范围说明，不是对所有参考产品逐项跑分；测试通过只覆盖记录的行为。完整新增操作见 [Agent运行时](../AGENT_RUNTIME.md)。


## 2026-09-07 基础 CLI 体验遗漏复盘

用户指出，多窗口启动、每次启动新 Session、显式恢复历史和生成文件分类应在基础体验阶段完成，不应逐项提醒。核对既有报告：确实定向参考过 Kimi／Mistral 的压缩、Skills 与子 Agent 生命周期，不能说完全没有阅读；但这不足以证明 CLI 基础流程已对齐。之前保留整状态目录独占锁、启动自动恢复检查点，测试也曾把自动恢复旧历史当成预期，说明测试覆盖并未替代产品行为验收。

本次会话已落实工具总轮次调整、用户生成代码分类与发行排除、多终端共享状态且会话独占，以及每次启动新 Session／显式 /resume；具体实现和验证分别见 CODING_AGENT、GENERATED_CODE、TERMINAL、SESSION_MEMORY 和 RUNBOOK。此处是对本地记录的复核，不是新增上游运行评测，也不据已通过专项测试宣称全部 CLI 体验已对齐。

后续参考以用户完整操作流程建立“参考行为／Loop 约定／实现入口／直接验证／未覆盖项”的对应关系，先核对启动、并发、输入、取消、保存、退出、重启与恢复，再评估高级能力；验收预期遵循已确认的用户行为要求，不把旧实现自动当成正确标准。多 Agent 并发与多个 CLI 窗口并发分别验收。
