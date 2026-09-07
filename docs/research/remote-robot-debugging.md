# 工作站 Codex／Claude Code 对接机器人端 Loop ROS

日期：2026-09-08。问题：机器人安装 Loop ROS 后，如何让工作站 coding agent 读取机器人项目、调用运行能力并高效调试？本轮是源码和官方文档核对及设计方案，未安装机器人端服务、修改客户端配置或执行设备动作。

## 用户目标澄清（2026-09-08）

用户明确要求工作站 Agent 与机器人端 Agent 对话协作，由端侧 Agent 利用自身硬件知识决定本地执行，而非以 MCP 工具遥控为主要方案。下方保留早先 SSH／MCP 工具调试路线作为可选技术背景，不再作为用户目标的推荐主架构。两端协作应传递目标、约束、追问、状态和证据，机器人保留本地知识与判断；参见[端侧感知和 ROS 兼容方案](ros-sensor-agent-integration.md)。

## 早期工具调试方案

建议采用 SSH 文件／命令通道加 MCP 工具通道。工作站 coding agent 负责分析、修改和测试决策；机器人 Loop 负责设备本地执行、资源与进程所有权、任务状态、日志和验收回执。确定性调试调用直接执行工具，不要求机器人端再调用一次大模型；只有显式提交需要自主规划的 Task 才使用机器人端共享模型 profile／Key。

Codex 和 Claude Code 均支持通过命令启动 stdio MCP，以及连接远程 HTTP MCP。局域网和现有 SSH 认证场景可先以 ssh -T 转发 stdio；面向多工作站的常驻部署可再提供 Streamable HTTP，并通过 SSH 隧道访问机器人本地监听地址。SSH 转发是根据两端传输能力提出的组合方案，本轮没有进行互操作实测。[Codex 官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)、[Claude Code 官方 MCP 文档](https://code.claude.com/docs/en/mcp)。

## 当前代码能做什么

| 能力 | 当前事实 | 入口 |
| --- | --- | --- |
| 工作站 SSH 读取项目文档、文件和日志 | 可由 coding agent 的命令工具使用既有 SSH 连接；具体路径／安装位置需以目标主机为准 | 项目操作小本本、[只读上下文校验](../../scripts/remote_context_check.py) |
| 远程运行 Loop 单次诊断 | CLI 支持 --once，诊断命令在 API setup 前分发 | [app.main](../../terminal/app.py)、[安装说明](../INSTALL.md) |
| MCP | loop mcp 为 stdio 仿真服务器；没有通用文件／Task／Node／真机 API | [sim_mcp](../../terminal/sim_mcp.py)、[仿真规范](../SIMULATION_WORKBENCH.md) |
| 常驻进程、任务账本和权限 | 内部已有 Node、TaskSupervisor、PermissionGate 和共享资源层 | [进程规范](../PROCESS_NODES.md)、[任务规范](../TASK_RUNTIME.md)、[资源规范](../RESOURCE_RUNTIME.md) |
| 多客户端连接同一机器人运行时 | 通用 RPC 网关和跨客户端 attach 尚未实现；现有仿真 MCP 自己创建工作台 | 需要补充，不可把共享 state-dir 等同于共享内存进程对象 |

当前可用的只读模板，robot 为用户自己的 SSH alias，绝对路径须替换：

```bash
ssh -T robot '/absolute/path/to/loop --once /doctor'
ssh -T robot 'cat /absolute/project/docs/OPERATIONS.md'
```

源码核实支持上述 CLI 语法，未在机器人安装环境执行。--once 创建临时 CLI 生命周期，不适合用一连串 --once 命令充当跨连接常驻 Node 管理器；CLI 退出及 SSH 断开与远端服务停止不能混为一谈。

## 建议的通用网关（尚未实现）

```text
工作站 Codex / Claude Code
  ├─ SSH：读项目、取日志、传补丁、运行针对性测试
  └─ MCP（SSH stdio 或经隧道的 HTTP）
       └─ 机器人常驻 Loop Runtime
            ├─ 项目摘要和文件工具
            ├─ Task / Node / 执行日志
            ├─ Host / 推理服务 / 机器人驱动
            └─ 原 PermissionGate、资源基础层与设备所有权
```

第一批接口应覆盖：项目／版本／能力摘要；有界文件读取和搜索；带内容哈希的补丁应用；进程状态、增量日志和就绪检查；确定性命令启动／结果读取／取消；显式 Task 提交／状态／恢复。接口命名和 schema 待实现，不是已存在的 Loop 命令。

长执行应立即返回 run_id，后续读取带游标的输出；cancel 通过独立控制请求进入同一运行时，不能排在长任务后面。停止请求、收到信号、直接进程退出和机器人停止反馈分别记录。任务去重使用请求标识，重连只查询已有运行，不自动再次播放轨迹。MCP notifications 是否在客户端持续展示需要端到端验证，不能只依赖客户端特定推送特性；增量读取保留为通用入口。

网关是协议适配层，共用现有执行器、权限、资源账本与状态库，不另建一套 Task/Node 系统。多个客户端可同时读状态；同一设备的动作通过已有所有权约束协调。工具 schema 按能力加载，避免把完整历史、全部 Skills 或大段日志塞进每次模型请求。

建议增加一个简洁的机器人上下文摘要：实际主机、项目根、环境解释器、代码版本、工作目录、服务状态、相关日志入口及当前 run/task 标识。静态入口按文件哈希复用，动态状态按需读取。AGENTS.md 和 CLAUDE.md 可引用同一个操作文档，减少两套说明漂移。

## MCP 连接配置示例：仅现有仿真能力

机器人安装对应可选依赖、确认绝对路径后，可按以下形式配置。两条注册命令都是模板，本轮没有执行：

```bash
codex mcp add robot-sim -- ssh -T -o BatchMode=yes robot /absolute/path/to/loop mcp --state-dir /absolute/state-dir
claude mcp add --transport stdio robot-sim -- ssh -T -o BatchMode=yes robot /absolute/path/to/loop mcp --state-dir /absolute/state-dir
```

ssh 不分配 TTY，远端 stdout 必须只输出 MCP 协议，诊断写 stderr。当前 loop mcp 只暴露仿真工具，而且每个连接创建自己的工作台；不能用此模板宣称已能查看另一个 Loop 窗口的真机 Host 或 Task。通用网关完成后应连接统一常驻运行时，避免每个 coding agent 启动另一套设备控制进程。

## 调试闭环与凭据

一次调试优先是：读取小摘要 → 定位具体错误和源码 → 提交最小补丁 → 对比远端文件哈希／版本 → 执行针对性验证 → 读取实际 stdout、退出码和目标反馈 → 保存回执。常驻服务重启只发生在修改确需重启且已获授权时；不因每个模型问题重新启动 Host。

MCP 确定性工具本身不需要机器人端聊天 API Key。SSH 身份认证与大模型 API 凭据用途不同；工作站 Codex／Claude Code 保留自己的正常登录，不读取机器人 ~/.loop/config.json 的明文 Key。需要机器人自主规划的 Task 才复用该机器人当前 endpoint 的 Key。网关配置和脱敏状态可共享，模型上下文不包含凭据。

## 实施顺序与验收

1. 先整理 SSH alias、机器人项目操作入口、实际安装和解释器路径，验证文件读取和单次诊断。
2. 增加连接统一运行时的只读 MCP 接口，验证两种客户端读取相同设备状态和同一条日志。
3. 接入受控执行／补丁及独立取消通道，使用本地测试进程验收长任务期间可读日志、可停止、断线重连不重跑。
4. 最后接入已有真机 Host／推理流程，依据已有设备授权及回执验证；不以工具已连接代替设备验收。

本报告的已验证范围为代码入口与官方客户端配置文档。尚未实现通用网关，未连接机器人 MCP、修改全局客户端配置、安装依赖或启动仿真／真机。
