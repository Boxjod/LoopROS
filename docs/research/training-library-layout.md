# 机器人训练库的存放与接入

日期：2026-09-07。问题：LeRobot 等机器人训练库应该放在哪里，如何与 LoopROS 对接？

## 建议布局（尚未创建或安装）

| 内容 | 建议位置 | 用途 |
| --- | --- | --- |
| 第三方源码 | `~/Workspace/robot-libs/lerobot/` | 独立 Git 仓库，固定经过验证的版本/commit |
| 专用 Python 环境 | 上述目录的 `.venv/`，或独立 Conda 环境 | 在训练主机上安装该版本要求的依赖，与 LoopROS 环境分离 |
| 训练项目 | `~/Workspace/robot-training/<project>/` | 保存训练配置、数据引用和实验说明；`datasets/`、`outputs/` 可放大容量磁盘并显式配置路径 |
| LoopROS 集成候选 | `LoopROS/toolchain/candidates/lerobot/` | 仅放自编适配器、说明和测试；不复制整个上游仓库；经验证后再按项目规范注册正式工具 |
| 个人调用工具 | `~/.loop/tools/lerobot_train.json` | 使用现有 tool_write/read/run 保存的 Python 工具包格式；包装器可调用独立解释器或明确配置的远程入口 |
| 操作知识 | `~/.loop/skills/lerobot/SKILL.md` | 参数、步骤、验收与排错说明，不承载第三方源码、虚拟环境或模型权重 |

这是建议布局，LoopROS 没有自动扫描 robot-libs、自动安装或自动注册 LeRobot 的现成能力。仅使用发行包时无需 clone，可直接安装到专用环境；需要修改上游或固定源码时再 clone。训练位于哪台机器，库、环境及数据路径就按那台机器配置；本机 LoopROS 可通过适配器调用远端，具体协议尚待实现。

## 与当前实现的关系

- [工具链约定](../TOOLCHAIN.md) 要求重依赖按需引入；[Ego2MuJoCo 桥接](../../toolchain/ego2mujoco.py) 已有显式 repo/解释器参数的独立环境模式，可供训练适配参考。
- [用户目录](../USER_HOME.md) 已定义工具包与 Skills 入口；现有 [run_python](../../terminal/python_runner.py) 使用 Loop 自己的解释器，因此训练包装器必须显式调用 LeRobot 环境，不能假定两者依赖相同。
- [PolicyServices](../../terminal/services.py) 管理现有 inference-only 服务，不是通用训练管理器。后台任务的工具白名单也独立于前台，不能把目录存在当作训练已接入。
- 训练适配需报告进程状态、真实日志、输出目录及 checkpoint/评估证据；创建 Task 只是记录目标，实际训练进程和成功验收另行确认。

## 来源与验证状态

- [LeRobot 官方安装文档](https://huggingface.co/docs/lerobot/main/en/installation)：已读取，提供独立环境、源码和 PyPI 安装方式；main 版本的环境/可选依赖要求不应直接套用于其他版本。
- [LeRobot 官方仓库](https://github.com/huggingface/lerobot)：官方安装文档给出的源码入口。
- 本地相关源码与文档已核对；上述目录是工程建议。未下载上游、安装依赖、创建训练环境、启动训练或接触机器人。
