# Loop ROS

[English](README.md) · **简体中文**

**Loop Robot Operating System — 具备可选机器人工具的 coding agent。**

Loop 将用户选择的模型连接到工具、持久任务与机器人运行环境，围绕“目标 → 执行 → 观察 → 复核 → 修正”工作。执行回执与任务成功分别记录。

首个服务器发行版 **0.0.1** 已在[官网](https://loopmaster.box2ai.com/LoopROS/)提供。GitHub 源码与服务器发行版是不同快照；尚未创建 GitHub Release。

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

## 服务器发行版更新与卸载

```sh
loop update --check
loop update
loop update --rollback
```

先关闭 Loop 终端与后台服务。更新保留配置与 Skills；回滚切换程序运行环境，不回退用户数据。

Linux/macOS 卸载：

```sh
curl -fsSL https://loopmaster.box2ai.com/LoopROS/uninstall.sh | sh
```

保留用户配置、会话和 uv。

## 源码运行

当前 GitHub 源码快照需要 Python 3.10+；使用 Python 3.8 的系统请选择上面的服务器安装命令。

```sh
python3 scripts/install.py --terminal-only
loop
```

可选 MuJoCo 环境使用 `python3 scripts/install.py`。Windows 源码命令使用 `py -3`。首次启动缺少密钥时进入 `loop-switch`，选择服务商或填写自定义 API 地址与隐藏输入的密钥；已有 profile 保留。

推荐通过自定义 API 或 OpenAI Responses API 使用 GPT-6 Astra，以服务端提供的实际模型 ID 为准。配置不代表已验证账户访问权限或工具支持；其他兼容服务商仍可使用。见[模型配置](docs/QUICK_SETUP.md)。

## 功能与边界

- 对话与编程：模型对话、文件读写、搜索、图片/网址和 Python 执行；Python 使用宿主用户权限。
- 执行与反馈：Episode、Review、持久任务和恢复/取消；工具成功不等于目标达成。
- 运行协调：Master、可选子 Agent、持久 Node 与载体路由；远程载体分配不等于已接通远程传输。
- 记忆与扩展：会话、摘要、经验、Skills 与 harness；不自动训练模型权重或发布候选。
- 机器人：可选 MuJoCo 场景、轨迹、运动学与动力学工具；仿真不证明真机成功。真机运动仍受门禁约束，硬件验收独立进行。

通用模型默认暴露 21 个工具；robotics、tasks、agents 工具组按模型需要加载，并逐轮重置。普通对话不自动变成持久任务，也不自动执行机器人动作。模型上下文预算与完整会话存储分离。

## 架构与目录

`core/` 放标准库契约、持久化与运行时；`terminal/` 连接会话、权限和模型工具；`toolchain/` 提供领域实现与可选依赖。任务、子 Agent 和 Node 各有生命周期。

- `configs/`：无密钥默认配置与示例。
- `examples/`、`assets/`：演示、模型与品牌资源。
- `scripts/`：安装和发布脚本。
- `docs/`、`tests/`：文档与验证。
- `website/`：官网；`artifacts/`：被 Git 忽略的本地运行产物。

仓库根目录也是 `loop_robot` 包目录，保留 Python 模块与命令入口。

## 文档与开发

[安装](docs/INSTALL.md) · [模型配置](docs/QUICK_SETUP.md) · [用户配置](docs/USER_HOME.md) · [项目地图](docs/CODEX_PROJECT_MAP.md) · [运行记录](docs/RUNBOOK.md) · [Coding 与 Skills](docs/CODING_AGENT.md) · [机器人](docs/ROBOTICS_AGENT.md) · [变更记录](docs/CHANGELOG.md)

`/commands` 查看命令，`/resume` 选择历史会话，`/queue resume` 恢复排队输入，`loop-switch` 管理模型 profile，不修改全局 Codex/Claude 配置。

```sh
python3 -m pip install -e '.[test]'
python3 -m unittest discover -s tests -v
python3 examples/run_demo.py
```

仿真测试取决于可选依赖与显示环境。确定性演示将证据写入 `artifacts/`，不调用 LLM 或控制硬件。
