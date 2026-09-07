<p align="center">
  <img src="assets/logo.png" alt="Loop ROS 无限环机器人标志" width="100%">
</p>

# Loop ROS

[English](README.md) · **简体中文**

**Loop Robot Operating System —— 支持按需调用机器人工具的通用编程 Agent。**

Loop 将用户选择的模型与工具、持久任务和机器人运行时连接起来，以 **目标 → 执行 → 观察 → 评审 → 修正** 为核心流程，分别记录执行回执和任务是否成功。

初始版本 **0.0.1**。支持服务器发行包安装与更新；GitHub 发布是独立流程。

## 快速开始

Python 3.8+ 即可启动安装器；它会自动准备 uv 并创建 Python 3.12 `.venv`，已有可用的 Python 3.10+ 环境会复用。在源码根目录运行：

```sh
python3 scripts/install.py --terminal-only
loop
```

如需可选的 MuJoCo 环境，运行 `python3 scripts/install.py`。交互启动会先检查模型连接；未配置 Key 或连接失败时，自动打开 `loop-switch setup` 向导，依次选择供应商或自定义 URL、接口类型、隐藏输入 Key 和模型。保存后重新检查，连接成功再进入对话。已有配置会保留。

**推荐通过自定义 API 或 OpenAI Responses API 使用 GPT-6 Astra。** 模型 ID 以所用服务实际提供的名称为准，详见 [GPT-6 与自定义 API 配置](docs/QUICK_SETUP.md)。填写配置不代表已验证账户权限或工具调用能力；其他兼容提供商仍受支持。

如果安装提示 `Destination already exists`，希望将全局命令切换到当前源码目录时运行：

```sh
python3 scripts/install.py --terminal-only --replace-launchers
```

依赖安装成功后，原命令入口会备份为 `~/.local/bin/<命令>.loop-ros-backup.N`，再切换到本项目。旧源码副本和数据保留。追加 `--check` 可只读预览；Windows 使用 `py -3`，备份对应的 `.cmd` 入口。不加该参数时，遇到冲突会保留原命令并停止安装。

## 卸载

先退出 Loop ROS 并停止其后台服务，再在本源码目录使用系统 Python（3.8+）运行：

```sh
python3 scripts/uninstall.py --check  # 仅预览
python3 scripts/uninstall.py
```

Windows 使用 `py -3 scripts/uninstall.py`。[卸载脚本](scripts/uninstall.py) 会删除本项目的 `.venv` 和确认属于 Loop ROS 的用户级命令入口（包括指向旧源码副本的入口）；保留源码、配置、Skills、会话、运行数据、uv 和共享 Python。其他软件或无法确认归属的命令、旧副本环境及命令备份会保留。用户命令目录可能包含其他工具，因此保留 PATH 设置。若 `.venv` 是符号链接或 junction，仅移除链接；无法识别的目录会保留并报错。

## 按系统安装

[官网](https://loopmaster.box2ai.com/LoopROS/)默认英文，可切换简体中文；Docs 对应本仓库 README。

需要兼容系统的 Python 3.8+ 引导安装，安装器通过 uv 准备独立 Python 3.12 运行环境，不替换系统 Python。以下命令安装终端版，去掉 `--terminal-only` 可安装可选仿真依赖。

### Linux

```sh
curl -fsSL https://loopmaster.box2ai.com/LoopROS/install.sh | sh -s -- --terminal-only
```

### macOS (Intel / Apple Silicon)

```sh
curl -fsSL https://loopmaster.box2ai.com/LoopROS/install.sh | sh -s -- --terminal-only
```

### Windows 10/11 — PowerShell

```powershell
Invoke-WebRequest -Uri https://loopmaster.box2ai.com/LoopROS/install.ps1 -OutFile loop-install.ps1 -ErrorAction Stop
powershell -NoProfile -ExecutionPolicy Bypass -File .\loop-install.ps1 --terminal-only
```

### Windows 10/11 — CMD

```bat
curl.exe -fSLo loop-install.ps1 https://loopmaster.box2ai.com/LoopROS/install.ps1 && powershell -NoProfile -ExecutionPolicy Bypass -File .\loop-install.ps1 --terminal-only
```

### 旧系统 — SSH

Windows 7/8 等无法运行所需 Python 的系统，通过兼容的 SSH 客户端连接已安装 Loop ROS 的主机。替换 `USER` 和 `HOST`：

```sh
ssh -t USER@HOST '$HOME/.local/bin/loop'
```

SSH 不包含本地 USB/摄像头转发。Linux HTTPS 安装已实测；macOS 与 Windows 原生安装仍待实测。安装后重新打开终端运行 `loop`，配置模型连接。

## 更新

```sh
loop update --check
loop update
loop update --rollback
```

更新前关闭 Loop 终端、后台服务与仿真窗口。新运行环境安装并验证后才切换，保留旧环境用于回滚；配置、Skills、状态和 terminal-only 选择保留。回滚只切换程序，不回退用户数据。源码安装使用 `loop update --migrate --terminal-only` 显式切换到发行版，本地源码改动不受影响。详见[版本与更新说明](docs/RELEASES.md)。

服务器发行版卸载：`curl -fsSL https://loopmaster.box2ai.com/LoopROS/uninstall.sh | sh`；保留用户数据和 uv。

## 用户配置、Skills 与换设备迁移

个人定制统一按用户目录规则存放在 `~/.loop`（Windows 为 `%USERPROFILE%\.loop`）：`config.json`、可选的 `agents.json` 和 `task_runtime.json`、`AGENTS.md`、`harness/*.md`，以及完整的 `skills/<name>/` 技能包。项目 `configs/` 保留发行默认值。可通过 `LOOP_HOME` 指定其他用户目录。

模型配置选择、权限和会话历史存放在运行状态目录，迁移时不能只复制 `~/.loop`。先停止 Loop 与后台服务，再将用户目录和状态目录一起转移到新设备；Skills 要整包复制，保留脚本和参考资料，凭据文件需私密传输并恢复权限。运行环境应在新设备重新安装，不直接复制虚拟环境。具体路径、覆盖优先级与集中到一个目录的方式见[存储规则和迁移步骤](docs/USER_HOME.md#device-migration)。

## 功能与边界

| 领域 | 已有能力 | 当前边界 |
| --- | --- | --- |
| 对话与编程 | Chat Completions 流式输出，文件搜索与编辑，图片和网址读取，Python 执行 | Python 以宿主用户权限运行；Responses 当前在响应完成后返回结果 |
| 反馈与证据 | 有界执行循环、Episode、Review、持久任务监督、恢复与取消 | 工具调用成功不代表用户目标已完成 |
| 运行协调 | Master、最多 3 个并行子 Agent、进程间消息、持久 Loop Node、载体与实例路由 | 远程载体分配尚未接入实际远程传输 |
| 记忆与扩展 | 会话历史、总结、经验检索、可修订学习笔记、Skills 与 harness | 不执行模型权重训练或自动发布候选 |
| 机器人工具 | MuJoCo 场景与资产、窗口控制、关节轨迹、位置 IK、力矩/PID/模型分析 | 仿真结果不能证明真机执行成功 |
| 设备接入 | 串口枚举与接收、飞特扫描与状态查询、STS3215 Host 控制原语 | 终端真机运动仍受门禁限制，硬件需要单独验收 |
| 辅助工具 | 搜索、网页、天气、调度、推理服务接口、ROS 只读适配、资源预算 | ROS 通信和实际策略模型后端尚未完成端到端验证 |
| 分发 | CLI 安装器、wheel 构建、跨平台基础检查工作流、更新检查客户端 | 跨平台原生实测和硬件认证需单独验收 |

默认模型上下文提供 21 个通用工具。专用工具组 `robotics`、`tasks`、`agents` 由模型按需加载，每轮重置；普通对话不会因为机器人关键词自动执行场景、设备或天气操作，也不会隐式创建后台任务。MuJoCo、硬件适配和策略集成都属于可选工具能力。各 Agent 角色统一使用当前选择的模型与凭据。完整会话历史独立保存，模型输入预算与持久化分开管理。

## 架构

```text
用户 ↔ 终端 / Master ↔ 模型 API
              │
         权限门禁下的工具
              │
       任务 / Node / 载体运行时
              │
        执行 → 证据 → 评审
         ↑              │
         └──── 修正 ────┘
```

`core/` 使用标准库实现契约、持久化和运行时；`terminal/` 连接对话、权限与工具；`toolchain/` 提供领域实现和可选依赖。任务监督、子 Agent 进程和持久 Node 分别维护自己的生命周期。

## 目录结构

- `core/`、`terminal/`、`toolchain/`：Python 实现。
- `rust/`、`firmware/`：Rust 端侧核心与 ESP32-C3 Arduino C++ 开发移植；见 [范围与构建验证](docs/RUST_CORE.md)，板上运行待验收。
- `configs/`：默认配置与不含 Key 的配置示例。
- `examples/`：仅源码开发使用的演示，不随安装包发行；`assets/`：品牌图片及仿真／本地工作台必要资源。
- `scripts/`：源码安装器、发布构建脚本和仿真依赖清单。
- `docs/`：项目文档和更新记录；`tests/`：验证。
- `website/`：本地官网源码，备份到服务器，不进入 Git／CLI 发行；`artifacts/`：不纳入版本控制的本地运行产物。
- `user_projects/`：按项目和已确认机器人型号分类的本地生成脚本与记录，不进入 Git 或发行；见[存放规则](docs/GENERATED_CODE.md)。

根目录同时作为 `loop_robot` Python 包目录，因此保留包模块及 `loop`、`loop-switch` 源码启动入口。

## 文档入口

- [项目地图](docs/CODEX_PROJECT_MAP.md) · [操作与验证记录](docs/RUNBOOK.md)
- [安装](docs/INSTALL.md) · [模型配置](docs/QUICK_SETUP.md) · [用户配置目录](docs/USER_HOME.md)
- [持久任务](docs/TASK_RUNTIME.md) · [Node](docs/NODES.md) · [载体部署](docs/DEPLOYMENTS.md)
- [编程与 Skills](docs/CODING_AGENT.md) · [记忆与学习](docs/LEARNING.md)
- [MuJoCo 控制](docs/MUJOCO_CONTROL.md) · [机器人工程](docs/ROBOTICS_AGENT.md) · [飞特电机](docs/FEETECH.md)
- [发布准备](docs/GITHUB_RELEASE.md) · [更新记录](docs/CHANGELOG.md)

使用 `/commands` 查看当前命令目录；`/resume` 选择已保存的会话，`/queue resume` 恢复排队输入。`loop-switch` 管理模型配置，不修改全局 Codex 或 Claude 设置。

## 开发与验证

```sh
python3 -m pip install -e '.[test]'
python3 -m unittest discover -s tests -v
python3 examples/run_demo.py
```

仿真测试受可选依赖和显示环境影响。离线演示会在 `artifacts/` 下写入本地证据，不调用 LLM 或控制硬件。已验证的命令与限制见运行记录。

## 设计参考

[PhyAgentOS](https://github.com/PhyAgentOS/PhyAgentOS-core) 为任务契约、执行、证据和验证的职责划分提供了参考。Loop ROS 尚未实现其 Forge Gateway 或 Skill Runtime 协议，也不宣称与其兼容。第三方模型和资产保留各自许可证，并需单独获取。

ROS 接入：支持 ROS 2／ROS 1 独立观察 host、传感器摘要、原生包常驻运行与地图导出，见 [ROS 运行接入](docs/ROS_RUNTIME.md)。Noetic 回环已测试，ROS 2 DDS 与真机仍需验收。
