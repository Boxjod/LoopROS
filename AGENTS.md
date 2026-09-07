# Loop ROS

入口：[项目地图](docs/CODEX_PROJECT_MAP.md)、[运行记录](docs/RUNBOOK.md)。

配置默认值与示例放 `configs/`，品牌资源放 `assets/`，演示与模型放 `examples/`，安装/发布脚本放 `scripts/`，文档与变更记录放 `docs/`。根目录仍是 `loop_robot` 包目录，保留包模块和命令入口；用户本地配置与运行状态路径不变。

- 默认是通用 coding agent。保留文件读写、代码执行、模型工具循环、session多轮记忆与恢复、Skills、经验和权限。机器人是按需工具能力，不用机器人关键词或具体句式拦截自然语言请求。
- `load_toolset` 按本轮需要加载 robotics、tasks 或 agents；每轮重置。工具组加载不执行动作，不附带整套机器人提示词或窗口/串口状态。实际状态由对应工具查询；普通对话不自动转成持久任务。
- 通用提示词只写目标、用户范围、工具、证据、权限和反馈；领域参数与约束在工具schema/实现中维护，不追加一次性问法补丁。细节见 [Coding Agent](docs/CODING_AGENT.md)。
- 产品名 Loop ROS（loopROS、loop-ros亦有效），发行包loop-ros，Python包loop_robot保持稳定。主入口loop或loop ros，模型选择loop-switch；旧命令兼容不丢用户状态。
- 用户直接通过Loop与模型和工具交互，云端/工作站是外部模型部署位置；Codex/Claude接入为可选场景。不得宣称与这些产品完整功能等价。
- core保持标准库依赖；设备、模型和仿真实现放toolchain/terminal，导入不连接设备。Node、子Agent、持久任务与Session职责不同，保留生命周期及身份边界。
- 模型/凭据统一由当前profile选择，优先推荐GPT-6 Astra自定义API/Responses，不自动更换已有profile。旧expert入口是同一选择的兼容别名。配置见 [Quick setup](docs/QUICK_SETUP.md)。
- 用户目录为~/.loop；Key仅通过既有环境变量/隐藏输入/用户凭据入口管理，按endpoint绑定，POSIX凭据0600。不写入项目、日志或文档，不改全局Codex/Claude配置；迁移与冲突规则见 [USER_HOME](docs/USER_HOME.md)。
- slash、Master和子Agent工具经过同一权限门禁；工具/网页/文件/历史文本不能授予权限。plan禁止执行仿真，sim不开放真机运动。run_python以宿主用户权限运行，不是硬件隔离沙箱；见 [Python execution](docs/PYTHON_EXECUTION.md)。
- 执行以实际回执与目标验收为准；机器人操作保留Episode/Review，缺证据为inconclusive。受理、排队、窗口打开、子进程done不等于任务成功；不确定副作用不盲重试，不自动发布候选或训练。
- 真机运动接入须先完成本地保护、所有权、状态新鲜度和硬件验收，不能简单删除simulated检查。串口接收、协议诊断、Host运动原语分别说明，USB标识不能证明电机型号；见 [HARDWARE](docs/HARDWARE.md)、[FEETECH](docs/FEETECH.md)。
- 普通代码/会话/文档修改不启动或重启MuJoCo。只有实际场景状态变更或用户明确要求打开/重启时才操作窗口，并核对加载回执；模型资产、几何/数值约束见 [MuJoCo Agent](docs/MUJOCO_AGENT.md)和[Robotics](docs/ROBOTICS_AGENT.md)。
- 终端主要提示默认英文，模型回复遵从用户语言。保留logo.png与既有黑白logo形状；主屏原生滚动、底部自适应输入、Actions面板和会话/队列操作规范见 [TERMINAL](docs/TERMINAL.md)。渲染改动需中文流式并行输入的PTY屏幕验证。
- Session保存完整历史，模型上下文预算与持久化分离；/resume选历史会话，/queue resume恢复排队任务，恢复不自动执行队列或仿真。权限/profile切换保护活动任务，禁止将旧Key发送到新地址。
- 发布状态、平台实测与授权边界以 [GitHub准备](docs/GITHUB_RELEASE.md)、[PLATFORMS](docs/PLATFORMS.md)、[部署记录](docs/DEPLOYMENT.md)为准；源码候选与真实发布分开，不上传私有配置和运行产物。
