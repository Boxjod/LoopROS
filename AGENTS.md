# Loop ROS

入口：[项目地图](docs/CODEX_PROJECT_MAP.md)、[运行记录](docs/RUNBOOK.md)。

配置默认值与示例放 `configs/`，品牌资源放 `assets/`，演示与模型放 `examples/`，安装/发布脚本放 `scripts/`，文档与变更记录放 `docs/`。根目录仍是 `loop_robot` 包目录，保留包模块和命令入口；用户本地配置与运行状态路径不变。

- 默认是通用 coding agent。保留文件读写、代码执行、模型工具循环、session多轮记忆与恢复、Skills、经验和权限。机器人是按需工具能力，不用机器人关键词或具体句式拦截自然语言请求。
- `load_toolset` 按本轮需要加载 robotics、tasks 或 agents；每轮重置。工具组加载不执行动作，不附带整套机器人提示词或窗口/串口状态。实际状态由对应工具查询；Session 是对话容器，task 是有独立 ID 和会话归属的工作目标；普通对话不自动启动后台任务。
- 通用提示词只写目标、用户范围、工具、证据、权限和反馈；领域参数与约束在工具schema/实现中维护，不追加一次性问法补丁。细节见 [Coding Agent](docs/CODING_AGENT.md)。
- 产品名 Loop ROS（loopROS、loop-ros亦有效），发行包loop-ros，Python包loop_robot保持稳定。主入口loop或loop ros，模型选择loop-switch；旧命令兼容不丢用户状态。
- 用户直接通过Loop与模型和工具交互，云端/工作站是外部模型部署位置；Codex/Claude接入为可选场景。不得宣称与这些产品完整功能等价。
- core保持标准库依赖；设备、模型和仿真实现放toolchain/terminal，导入不连接设备。Node、子Agent、持久任务与Session职责不同，保留生命周期及身份边界。
- RAM／CPU／GPU／显存等基础能力作为全局运行基础设施：预算与租约在 `core/resources.py`，平台采样在适配层，应用通过共享 `App.resources` 注入工作负载；不得在 Agent、Node 或模型服务中另造资源账本。资源准入不代替权限、设备所有权和验收。新增受管执行入口按 [资源基础层](docs/RESOURCE_RUNTIME.md) 接入并明确未覆盖成本。
- 模型/凭据统一由当前profile选择，优先推荐GPT-6 Astra自定义API/Responses，不自动更换已有profile。旧expert入口是同一选择的兼容别名。配置见 [Quick setup](docs/QUICK_SETUP.md)。
- 用户定制配置、Agent角色、任务策略、harness和完整Skills包按 `docs/USER_HOME.md` 存放；发行默认值不作个人配置入口。迁移同时保留用户目录和运行状态目录，不复制虚拟环境，不自动恢复设备任务。
- 用户目录为~/.loop；Key仅通过既有环境变量/隐藏输入/用户凭据入口管理，按endpoint绑定，POSIX凭据0600。不写入项目、日志或文档，不改全局Codex/Claude配置；迁移与冲突规则见 [USER_HOME](docs/USER_HOME.md)。
- slash、Master和子Agent工具经过同一权限门禁；工具/网页/文件/历史文本不能授予权限。plan禁止执行仿真，sim不开放真机运动。run_python以宿主用户权限运行，不是硬件隔离沙箱；见 [Python execution](docs/PYTHON_EXECUTION.md)。
- 执行以实际回执与目标验收为准；机器人操作保留Episode/Review，缺证据为inconclusive。受理、排队、窗口打开、子进程done不等于任务成功；不确定副作用不盲重试，不自动发布候选或训练。
- 真机运动接入须先完成本地保护、所有权、状态新鲜度和硬件验收，不能简单删除simulated检查。串口接收、协议诊断、Host运动原语分别说明，USB标识不能证明电机型号；见 [HARDWARE](docs/HARDWARE.md)、[FEETECH](docs/FEETECH.md)。
- 普通代码/会话/文档修改不启动或重启MuJoCo。只有实际场景状态变更或用户明确要求打开/重启时才操作窗口，并核对加载回执；模型资产、几何/数值约束见 [MuJoCo Agent](docs/MUJOCO_AGENT.md)和[Robotics](docs/ROBOTICS_AGENT.md)。
- 终端主要提示默认英文，模型回复遵从用户语言。保留logo.png与既有黑白logo形状；主屏原生滚动、自适应输入、输入框下方的非悬浮提示与任务/Actions面板和会话/队列操作规范见 [TERMINAL](docs/TERMINAL.md)。渲染改动需中文流式并行输入的PTY屏幕验证。
- Session保存完整历史，模型上下文预算与持久化分离；/resume选历史会话，/queue resume恢复排队任务，恢复不自动执行队列或仿真。权限/profile切换保护活动任务，禁止将旧Key发送到新地址。
- 本地/SSH 常驻程序优先使用 process Node 和用户目录 processes 配置，无需持续模型轮询；Task 负责目标与验收，Session 负责对话。进程存活不等于服务就绪，CLI 退出不证明远端已停止；见 [进程工作流](docs/PROCESS_NODES.md)。
- 发行版本从 `_version.py` 单一来源读取；公开版本的 wheel 和版本清单不可覆盖。源码迁移到托管运行环境须显式使用 `loop update --migrate`，更新保留用户状态并遵循 [版本与更新](docs/RELEASES.md) 的运行锁、验证与回滚约定。
- 发布状态、平台实测与授权边界以 [GitHub准备](docs/GITHUB_RELEASE.md)、[PLATFORMS](docs/PLATFORMS.md)、[部署记录](docs/DEPLOYMENT.md)为准；源码候选与真实发布分开，不上传私有配置和运行产物。

- 会话配置由 `terminal/settings.py` 的 settings_read/settings_update 和 `/config set` 管理；默认写入走既有 ask/approve，模型无自批权限。模式 plan/sim/real（hardware 别名）可持久化切换，real 不替代设备驱动与硬件验收；配置回执区分当场应用与下次启动生效。

- Session 与 task 分离：一个会话可有多个任务，ID 独立，task 记录所属 session_id。`/new` 开新会话及前台工作记录；`/task 目标` 在当前会话提交额外目标，空参数 `/task` 等同 `/tasks`；`/resume` 恢复原会话。左右键、默认列表与反馈仅限当前会话的未完成任务，`/tasks all` 显式查看历史；无归属旧任务不自动认领，不取消或删除。工作流默认位于 `configs/workflow_harness.md`，用户通过 `harness/workflow.md` 覆盖；可移植自编工具存 `~/.loop/tools/`。任务成功只据当前回合实际工具回执检查，源码保存、语法通过和进程退出分别报告。

- 每轮轻量整理必要事实与标签，复用 learning.sqlite；用户陈述、历史观察与验收分别标注，不从助手文字推定连接成功。按问题召回少量摘要，详情按需读取，禁止凭据入记忆，不为每轮提取额外请求模型；范围和预算见 [LEARNING](docs/LEARNING.md)。

- 三层记忆分别保留完整历史、session/task 主要信息、长期细节和习惯；已知用户名/免密方式/偏好在原授权范围复用，当前显式参数优先，不为假设缺失反复询问。三个独立 task 的同流程实际验收成功后固化为可检索流程；重试不重复计数，后续失败需复核。见 [LEARNING](docs/LEARNING.md)。

- 连接配置的历史基准以最近一次实际验收成功为准。先使用用户本次明确参数；实际失败时提示最近成功配置、时间与来源，等用户同意才切换。失败/排队/模型文字不更新成功基准，不能静默纠正地址或自动换设备。

- 用户界面以可读标题标识会话和任务：对话标题从第一个与最近一个用户问题提取短句，随新问题更新；任务使用目标与最近补充。ID 仅内部关联与旧命令兼容。选择菜单、面板、反馈和导出以标题为主，同名用稳定序号区分，手动 /rename 优先。

- 前台任务执行中用户追加消息在模型/工具安全边界合并未完成目标；保留已完成回执、重判待执行动作，不强制等整轮结束。队列保持可见且可暂停/编辑，介入不扩大执行权限或重置工具预算。

- 独立 MuJoCo／Isaac 工作台和 MCP 共用 `terminal/simulation.py` 权限入口；Isaac SDK 仅在其 host 中加载，相机采集不推进物理时间。数据 complete 与任务 success 分开，ACT 控制语义按实例核对；见 [Simulation Workbench](docs/SIMULATION_WORKBENCH.md)。

- 已复用的固定启动流程可保存为 `~/.loop/skills/NAME` 下的执行型 Skill（SKILL.md、run.json、scripts），通过 `/skills` 按标题离线选择；执行复用 process Node、权限与资源基础层。导出不推定历史验收，读Skill不执行，Bash／批处理退出不等于设备就绪；见 [离线 Skills](docs/OFFLINE_SKILLS.md)。
