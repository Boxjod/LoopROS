# 已验证操作

2026-09-07 启动统一新建 Session：首个窗口和附加窗口每次启动／重启均生成并保存新会话，不自动载入历史、草稿、附件、队列或旧累计用量。历史通过 /resume 显式恢复，恢复队列仍暂停；旧 checkpoint-only 记录在打开库时先归档，避免新会话第一次保存覆盖唯一历史。新会话在菜单使用前持久化，避免恢复命令补全后才出现同名空白会话而产生歧义。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_interactive test_session_resume test_multi_terminal test_multi_terminal_render test_session_render test_composer_render -q` 38 项通过，日志 artifacts/terminal/validation/fresh-session-startup.log。覆盖连续两次重启 ID 独立、旧历史／草稿／队列保留、旧检查点归档、显式恢复用量与历史、双终端中文流式输入、任务面板以及真实 PTY 重启不自动带入图片、手动恢复图片。旧自动恢复测试改为显式 /resume；任务面板测试等待 Esc 完整处理，保留原操作验收。`git diff --check` 通过；没有操作用户设备、服务或现有窗口。

2026-09-07 多个 Loop 终端共用状态目录：CLI 的整目录拒绝改为 TerminalInstance 运行槽；首槽保留原路径，其余为 terminals/<槽号>。共享 profile、权限、历史、任务、学习与资源租约；额外终端从新会话开始，当前会话用 OS 锁保护，恢复占用会话保留原窗口。获取锁后重读最新会话，工具回执按 session_id 关联，旧记录保留。定时器、Node、viewer／场景和前台日志按槽隔离，非仿真 Node 所有权锁随进程回收释放，不另造资源预算账本。部署绑定变更检查其他活动终端。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_multi_terminal test_multi_terminal_render test_session_resume test_tool_groups test_nodes.NodeRuntimeTests -q` 19 项通过；真实 CLI 第三个窗口复用相同 state-dir、两个真实 PTY 中文流式／并行草稿、同会话占用拒绝、关一个窗口后另一个继续及恢复、子进程崩溃解锁、跨运行槽 Node 重复资源拒绝／停止和启动失败后释放均通过。PTY 首次验证因键入与 Enter 同包遇到界面时序未提交，改为分开键入与提交；再次验证发现测试未清除错误后按产品行为保留的 slash 草稿，修正后通过，没有改动相关输入行为。

`PYTHONPATH=tests .venv/bin/python -m unittest test_terminal test_interactive test_session_render test_platform_support test_carriers.DeploymentTests -q` 43 项通过，日志：artifacts/terminal/validation/multi-terminal-regression.log。共 62 项相关测试通过。初始扩大回归发现一条既有工具循环测试把末条提示当 JSON 回执；改为选最后一条 role=tool 消息，仍断言重复调用被跳过且执行仅一次，单项及整组复验通过。没有变更模型循环实现。`git diff --check` 通过，已确认用户的 loop 命令加载本工作区 terminal/app.py。

本轮没有操作用户设备或现有服务；并发验证使用临时状态目录、离线模型替身与无硬件 Node，未打开 MuJoCo 窗口。Windows/macOS 原生并发未实测。旧版本终端需正常退出后重开，使所有窗口加载新的占用保护；混用旧进程不作为已验证并发。内部状态路径约定见 [终端说明](TERMINAL.md#多终端共享状态目录2026-09-07)。

2026-09-07 用户生成代码归类：根目录 33 个本地脚本和 1 份操作记录移到被忽略的 `user_projects/`，按项目与源码已明确的机器人型号分类；34 份内容逐一 SHA256 完全一致，旧回执和会话数据库不移动。根目录只剩 8 个正式 Python 包／安装／更新模块。迁移清单、旧新路径及任务索引留在本地目录，已从 Git 暂存移除用户操作记录，其他暂存改动保留。

模型上下文／默认工作流与文件 schema 指明分类位置；文件工具阻止在 Loop ROS 自身包根新建临时脚本，现有模块编辑和普通项目源码写入仍可用。根目录源码搜索跳过用户目录，显式选择项目可检索。`user_projects` 同时被 Git 忽略与发行源树独立排除，wheel 检查拒绝该目录；根 Markdown 使用维护入口白名单。详见 [存放规则](GENERATED_CODE.md)。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_coding_agent test_public_source test_tool_continuation test_python_runner -q` 28 项通过；覆盖生成路径、现有源码编辑、普通项目根写入、定向检索、强行暂存且无忽略规则的发行过滤及实际 Git 索引检查。33 个迁移脚本 AST 解析、34 个文件哈希、本地索引链接、实际源码发行快照过滤和 `git diff --check` 通过。迁移前未发现直接运行这些脚本的进程；未执行用户脚本、SSH、控制或仿真。运行中的旧 Loop 需正常退出后重开以加载文件工具／上下文新规则。

2026-09-07 取消前台工具总轮次上限：默认上下文使用 `max_tool_rounds=None`，ChatAgent 持续循环至模型答复、取消或异常，不再触发 24／72 轮预算收尾。保留显式有限调用者与后台 Worker 预算、权限门禁和重复失败处理。已运行的 Loop 进程需退出后重新启动加载；未执行轨迹或连接设备。

验证：`.venv/bin/python -m unittest discover -s tests -p 'test_tool_continuation.py'` 8 项通过，含 80 次工具调用后正常答复及第 75 次调用取消；同命令分别运行 `test_tool_groups.py`、`test_stream_completion.py`、`test_steering.py` 各 4 项通过，共 20 项。模型与工具使用替身，无真实模型费用。`git diff --check` 通过。

2026-09-07 执行中队列介入：前台新消息由 UI 线程在模型返回/工具完成边界并入当前 ChatAgent，保留原目标和实际回执，跳过旧响应中尚未执行的工具；不强制中断执行中的工具。消费后追加用户历史并保存检查点，本轮经验包含补充要求。暂停/编辑/清空/附件和文本预算保持受控，定时任务及 slash 执行不混入。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_steering test_interactive test_coding_agent -q` 36 项通过；`PYTHONPATH=tests .venv/bin/python -m unittest test_steering test_steering_render test_terminal_render.TerminalRenderTests.test_chinese_stream_queue_and_editing -q` 6 项通过，无跳过（其中 4 项已包含在前一组）。真实 PTY 验证中文连接请求期间补充启动 host，队列先显示再由当前回合消费、草稿保持，模型/工具均替身且没有实际 SSH/服务启动。首版 PTY 替身使用未注册工具被正常拒绝，修正为已注册的 list_files 替身后通过。


2026-09-07 首末问题标题与去 ID 显示：会话标题在本地从首个和最近用户问题提取短句并动态更新，手动 /rename 优先；候选直接插入可读标题，重名使用稳定序号。/new、/resume、重画页头、/sessions、任务面板与反馈采用标题；任务标题取目标与最近补充，状态/恢复/取消命令可按标题操作；导出文件名以标题开头。ID 保留内部关系及旧命令兼容，不合并同名任务。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_titles test_session_resume test_completion test_command_display test_task_navigation test_cli_edges test_interactive test_session_render -q` 44 项通过，含 40/80 列中文流式输入、标题带空格恢复、任务标题与 ID 隐藏的真实 PTY；补充任务标题命令与导出文件名后，`test_titles test_task_scope test_workflow_harness test_command_display test_session_resume` 22 项通过。没有新增模型调用，没有操作实际任务或机器人；旧 Loop 进程需重启加载。

2026-09-07 最近成功连接基准与回退建议：连接验收成功后保存 device/transport 范围内最新配置、来源和原始记录时间；新失败/旧回调不能覆盖更晚成功。前台 App 与后台 TaskSupervisor 的实际连接失败回执附加历史成功建议，要求用户确认、不自动重试；权限禁止召回时不附加。模型指引保留当前明确参数优先。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_connection_memory test_memory_layers test_learning test_coding_agent test_task_scope -q`，44 项通过，无跳过。覆盖新失败保留旧成功、新成功替换、旧回调重放、设备/范围/权限隔离、前台 tool_run 嵌套连接回执即时建议，拒绝普通文字/退出码/无关验收。仅替身回执与临时数据库；未发起实际 SSH，也未将旧自由文本日志冒充连接成功。实际接入需要连接工具按文档返回结构化回执并设置对应验收。

2026-09-07 三层记忆与免密连接习惯：新增 core/memory_layers.py，在 learning.sqlite 中独立索引 session/task 摘要与长期细节；免密方式、用户名和偏好不被新任务记录挤掉，前后台提示词要求复用已知参数，仅实际阻塞才询问。现有用户回合经验首次按范围最多提取 200 条，保留原始来源/时间。三个独立 task 的相同步骤、参数和实际验收成功后固化 procedure，重试不重复计数，后续失败标 needs_review 并停止自动召回。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_memory_layers test_learning test_coding_agent test_task_scope -q`，39 项通过，无跳过。覆盖三层来源、旧免密信息对抗 30 条新任务噪声、参数优先提示、无关问题、三次独立成功/拒绝假成功与不同参数、失败失效、前台/后台固化、旧经验一次导入、范围隔离和既有回归。用户本轮确认的 Jetson 用户名 jetson/现有免密 SSH 已存入当前模型范围的长期细节，并本地验证召回；未保存凭据、未固化任何未验证的实际设备流程、未发起 SSH 或修改权限。当前明确输入地址优先，未将示例中的新地址覆盖成固定设备默认值。


2026-09-07 Session/task 归属分离：修复左右键读取整个 STATE 下所有未完成任务。Session 保存对话，task 独立 ID 并记录 session_id；一个 Session 可提交多个任务。左右键、默认 task_status 和状态通知只看当前会话，已读游标按会话保存；`/tasks all` 显式查看其他会话/无归属历史。`/new` 切换范围，`/resume` 恢复原范围；不取消、不删除、不自动认领旧任务。tasks.sqlite 增量加列和索引；旧前台共享 ID 稳定迁移为独立 ID。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_task_scope test_task_navigation test_cli_edges test_interactive test_workflow_harness test_session_resume test_coding_agent -q`，56 项通过；`test_session_render test_task_scope test_task_navigation` 共 8 项通过，含中文流式并行输入、当前/外部/旧版任务混合的真实 PTY；任务监督器的定时/触发合并、策略校验和显式提交 3 项通过。首次 PTY 在任务取消与面板关闭竞态中使用右键查询，改为显式 `/tasks` 读取空列表后通过，左右键回对话语义保留。未操作实际用户任务或机器人；运行中的旧 Loop 需重启加载。

2026-09-07 分层记忆增量：无工具的地址/SSH/明确记忆陈述也可记录，结构化连接字段带历史观察标签，索引覆盖事实摘要与标签。保留 session/task/source/time，相关召回去重并限制 3 条/3000 字符；详细证据按需读取，无新增模型调用，原工作区/提供商/权限隔离不变。未批量导入旧历史、改设备配置或连接 Jetson。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_learning test_coding_agent -q`，29 项通过，无跳过。覆盖跨 session 实际模型请求替身、新旧地址和时间、凭据脱敏、不采信助手答复、不保存 stdout、普通闲聊跳过、无关问题不注入、权限/范围隔离、后台独立进程复用。学习测试旧客户端替身补齐 resolved_key 方法。更广的 test_workflow_harness 出现 2 项失败，原因是工作区中并行发生的 session/task 独立身份改动与旧“二者 ID 相同”断言不一致；本次未改该身份实现或这些断言。


2026-09-07 `/new` 报错与任务面板修复：移除 `/new` 禁止尾随文本的限制，支持 `/new [GOAL]`；无未完成后台任务时 `/tasks` 展示当前 Session task。裸命令及带中文目标均不调用模型或执行工具，旧历史保留。验证命令：`PYTHONPATH=tests .venv/bin/python -m unittest test_cli_edges.CliEdges.test_new_enter_with_completion_goal_and_tasks_panel test_workflow_harness.SessionTaskInteractionTests test_completion -q`，5 项通过；`PYTHONPATH=tests .venv/bin/python -m unittest test_session_render -q` 两项真实 PTY 测试通过（含中文流式输入、/new 与任务面板）。已核对用户 loop 启动器指向本项目 .venv，重启将加载当前源码。截图的 `No running tasks.` 已不是当前源码提示，旧运行进程需要退出后重启加载。

2026-09-07 任务左右键导航修正：未完成后台任务均进入切换列表，包括 queued、running、retry_wait 和 waiting_*；仅成功/取消移出。等待任务展示原因及 Resume 操作，切换不恢复执行、不改聊天消息归属。空列表提示改为 No unfinished tasks。此前本日记录中“左右键只显示 running”描述的是修复前行为。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_session_render.SessionRenderTests.test_task_buttons_and_permission_profiles -q` 通过，真实 PTY 核对等待原因、恢复/取消按钮、排队任务可达、左右返回聊天及已结束排除。`test_terminal_render.TerminalRenderTests.test_chinese_stream_queue_and_editing` 中文流式并行输入 PTY 验证通过。导航测试首次因取消后面板仍选中其他任务、测试多按一次右键返回聊天而失败，调整测试从关闭面板开始后通过。未恢复实际后台任务、修改权限或启动设备。

2026-09-07 后台任务排查与网络候选归类：只读核对任务 `5714a8b781d1` 为 waiting_input，只有 submitted/state 事件，无执行轮次；验收引用 read_file，发行后台 worker_tools 未包含此工具。当前前台会话与后台任务独立，左右键只显示 running，等待任务通过 `/tasks status ID` 查看。未扩大权限、恢复任务或发起 Jetson SSH。日志中的目标长度异常和模型格式异常尚未复现，不能仅凭通用错误消息认定协议选错。

项目根 `network_discovery.py` 迁入 `toolchain/candidates/network_discovery/`，增加 main 保护、独立 README 与测试，保留原 JSON 字段。验证：`python -m unittest discover -s toolchain/candidates/network_discovery -p 'test_*.py' -q` 三项通过；本地运行脚本，addr/route/neigh 三项退出码均 0、JSON 可解析，未保存网络采集内容。候选源码未自动上传或注册为发行工具。



2026-09-07 Session task 与工作流 harness：每个 Session 同 ID 保存目标、计划、验收、实际工具回执与失败反馈；`/new` 新建 task，`/resume` 恢复而不执行。新增可移植 tool_read/write/run 与 python_check，工具存用户 tools 目录，执行复用 Python runner；工作流默认 24 轮、两次相同失败后阻止原样重试，用户 harness 覆盖热生效。未改实际用户工具或 harness，未操作网络机器人或用户仿真窗口。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_workflow_harness test_session_resume test_coding_agent test_skills test_settings test_providers test_user_portability test_harness_behavior test_python_runner -q`，61 项通过。另 `PYTHONPATH=tests .venv/bin/python -m unittest test_interactive test_session_render test_harness_behavior test_python_runner -q`，31 项通过，包含中文流式并行输入、任务按键和恢复选择器的真实 PTY。模型调用使用替身，工具程序是真实 Python 子进程；验证失败源码→异常输出→修复→JSON 验收、跨用户目录复制运行、审批/deny/哈希、/new/恢复无执行与中断状态。首次回归发现旧 on_turn_finished 专用于后台交接，已分离 on_session_finished 回调并验证无隐式后台启动。新功能入口见 [Coding Agent](CODING_AGENT.md)。

2026-09-07 模型配置自动探测：输入 URL/API 类型与隐藏 Key 后，预设和自定义地址均查询 `/models`。按公司 A–Z 分组、组内目录日期从新到旧显示所有有效型号，支持编号/手填、越界重选、取消与探测失败回退。日期缺失标 Unknown，未把目录可见性当作能力验收。

验证（LoopROS 根目录）：`PYTHONPATH=tests .venv/bin/python -m unittest test_setup test_setup_startup test_model_connection test_providers -q`，25 项通过，无跳过。真实 PTY＋本地 HTTP 覆盖旧 Key 401 → 隐藏输入新 Key → `/models` 分组排序 → 编号选择 → Responses 连接成功 → 退出；单测覆盖列表超过 40 个、异常条目/重复 ID、时间排序与未知日期、取消不保存、错误脱敏和旧配置保留。仅隔离临时配置与本地接口，未调用线上提供商或更改用户实际配置。



2026-09-07 会话配置管理：新增 settings_read/settings_update 和 `/config set TARGET JSON`，支持 plan/sim/real（hardware 别名）、权限预设/规则、profile、用户配置、角色、任务策略与 deployment。写入复用既有权限审批；文件校验后保存并保留备份，回执区分立即应用与下次启动。未修改实际用户配置，未连接机器人、启动窗口或调用线上模型。

验证（LoopROS 根目录）：`PYTHONPATH=tests .venv/bin/python -m unittest test_settings test_providers test_user_portability test_harness_behavior test_control.ControlTests.test_permission_profiles_and_custom_rules test_control.ControlTests.test_plan_blocks_shortcuts_and_tools test_control.ControlTests.test_inventory_and_diagnostics test_control.ControlTests.test_approval_does_not_override_deny test_control.ControlTests.test_ask_approve_exactly_once -q`，30 项通过，无跳过。新增 7 项覆盖模型替身工具循环与模式回执、审批/deny、后台禁止、配置校验和备份、Key 隔离与历史保留、角色/任务/载体配置、活动任务阻断。更广回归未全通过：既有 task_supervisor 的 SimpleNamespace 客户端缺少 resolved_key，4 项错误；control 的场景测试受 MuJoCo 安装环境阻塞、模拟测试跳过。未修改这些无关实现或测试替身。运行中的旧 Loop 需重新启动一次加载新增代码；配置生效规则见 [会话配置](CONTROL_SURFACE.md)。

2026-09-05 电机驱动缺口与授权交互：明确自然语言“允许所有执行权限”直接更新现有规则，阻断定时任务改权限；SDK清单新增DYNAMIXEL/ODrive来源与安装检测，harness区分授权/安装/适配/配置，并修正DTR/RTS保证。23项相关测试通过（2.000秒）。只读发现ttyACM0，型号未知；未安装猜测的电机SDK或执行硬件通信，未改用户活动会话权限。详见[接入记录](../../projects/reports/14_motor_driver_integration_gap.md)。

2026-09-05 真实终端harness评估：5组×4轮独立PTY对话，实际模型qwen-plus；修复自然语言快捷入口直接输出JSON、嵌套失败摘要、取消后迟到结果和流式前言遮挡最终结论。当前权限每轮刷新，电流到力矩用回执给条件性结论；详情保留/details。最后全量 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`，195项通过、无跳过（43.780秒），含中文PTY和协议替身测试。测试窗口均由测试会话回收；未重启用户窗口或发送真机指令。时延、真实回答、剩余字段复述/协议示例问题见[实测报告](../../projects/reports/13_terminal_harness_evaluation.md)。旧运行终端需重新启动加载代码。

2026-09-05 机器人工程Agent：新增robot_toolchains/robot_docs/robot_diagnose/motor_torque/pid_trial/robot_model_analysis，统一权限门禁与输入/结果归档。支持电流定义/轴侧校验、PID抗积分饱和离线试验、当前模型FK/Jacobian/惯量/逆动力学及J转置力映射。官方文档含ROS2、ros2_control、MoveIt、Pinocchio、MuJoCo、Mink、电机厂商、CAN/EtherCAT入口；检索版本不冒充已安装版本。说明见[ROBOTICS_AGENT](ROBOTICS_AGENT.md)。

在LoopROS目录运行 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`：165项通过、无跳过（32.906秒）。对大矩阵返回摘要而完整矩阵留报告后，相关6项回归再次通过。真实Qwen调用motor_torque计算0.2Nm/1.8Nm；实际Panda FK/动力学与SocketCAN官方文档读取成功，[记录](../artifacts/terminal/engineering/validation.json)。首次动力学检查发现MuJoCo3.12不再有data.qM，核实新版mj_fullM签名后通过矩阵正定/对称和方程残差。未安装电机SDK、未打开串口、未发真机指令。首批真实电机型号/固件/通信信息未提供，发送驱动尚未实现。


2026-09-05 生成产物复核清理：build已不存在；移出源码egg-info、源码/测试字节码缓存和未占用的MUJOCO_LOG.TXT，共117文件、987801字节。实际venv dist-info保留，项目外loop版本、隔离/status及loop-switch通过。备份 `/tmp/loop-ros-generated-cleanup-lgp114l4/`，详见[复核报告](../../projects/reports/12_loopros_legacy_name_audit.md)。未改运行代码，未重启仿真器。core对toolchain的两处反向导入已确认，尚未实施架构修复。

2026-09-05 源码目录迁移至 `/home/boxjod/Workspace/box2net/LoopROS`：修复13个venv脚本/配置文件、4个用户命令链接；` .venv/bin/python -m pip install --no-deps -e . ` 重新生成editable映射。内部包仍为loop_robot，模型切换导入不再依赖目录名。场景索引改为相对状态目录，当前索引已迁移；外层文档链接已更新。

验证：新目录执行 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`，159项通过、无跳过（31.245秒）；项目外命令、pip check、任意名称源码副本的模型切换和改名后场景恢复通过，配置/凭据哈希与权限不变。MuJoCo新PID 2288919，窗口打开、场景哈希及15个模型主体一致，[重启证据](../artifacts/terminal/viewer/directory_relocation_validation.json)。旧进程已退出，无需强制结束。备份与限制见[迁移报告](../../projects/reports/12_loopros_legacy_name_audit.md)。未部署服务器或调用真机、模型API。

2026-09-05 MuJoCo操作Agent与持续场景编辑：`mujoco_docs`按本机版本连接官方手册，latest连接stable，缓存和来源/版本随结果保存。本机和本次官方最新稳定版均为3.12.0。`compose_scene`基于MjSpec组合保留桌椅、Panda、刚体及资产，`load_model`默认追加；资产依次查本地、官方和公开互联网，支持固定commit的公开GitHub MJCF/OBJ/STL数据导入。支持增删移动、支撑高度与占用检查，每次成功修改强制重启GUI，加载留Episode/Review；旧工具失败不再由模型编造成功。详见[操作Agent](MUJOCO_AGENT.md)。

最终项目目录 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`：**158项通过，无跳过**。覆盖真实Panda编译、序列化后新增对象仍存在、home关节/ctrl、连续添加/移动/移除、旧场景保护与恢复、官方手册版本/缓存、公开网格导入替身、权限以及24/40/80列中文流式粗体PTY测试。文档本地链接通过。真实GUI验证哈希、新PID、worker身份重连、暂停/步进/重置回执；[基础记录](../artifacts/terminal/viewer/composition_validation.json)。实际使用用户配置的qwen-plus验证自然语言保留桌椅/Panda/红方块并加入蓝球，最终一次候选成功：[线上模型记录](../artifacts/terminal/viewer/natural_language_composition.json)。本次有实际模型API请求和官方Panda约36.6MB资产下载，无训练/真机动作。

过程中发现并修复：新旧JSON格式混用、sphere尺寸错误时未继续纠错、序列化资产字典旧scene.xml覆盖新场景，以及流式粗体跨片段状态；实际生成失败候选保留在report以便复查。并非仅靠放宽unsupported限制。桌面Panda碰撞基座下界实测0.7499995m，桌面0.75m，差约-0.5微米；[定位验证](../artifacts/terminal/viewer/placement_validation.json)。这是几何摆放验证，不是动态稳定性或抓取验收。

最后保留真实窗口打开，场景包含table/chair/panda/red_cube/blue_sphere（11关节、8执行器）；[预览](../artifacts/terminal/viewer/composition_preview.png)由同一场景渲染并已查看。后续每次修改验证后自动重启MuJoCo的约定已写入AGENTS。主终端新代码在重新启动loop时加载；现有worker可通过持久化owner身份重新连接。公开任意网页/压缩包/URDF/CAD自动转换、通用IK/抓取策略未实现。


2026-09-05 旧名称与环境清理：移出 looper-m1／loop-robot 安装元数据及旧 build，修复9个环境路径文件；活动发行包仅 loop-ros，pip check 通过。保留内部 loop_robot 及旧命令兼容，新配置Key前缀为 LOOP_KEY，旧凭据绑定不变；安装状态迁移为 loop-ros 并保留历史路径链接，源码仍使用 artifacts/terminal。详情与临时回滚位置见[处理报告](../../projects/reports/12_loopros_legacy_name_audit.md)，规则见[USER_HOME](USER_HOME.md)。

验证：项目目录 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`，157项通过、无跳过（31.361秒）；新旧入口、隔离/status、loop-switch、pip/f2py/numpy-config及激活路径检查通过。用户配置3个文件内容哈希与权限保持一致。按约定重载MuJoCo，PID 2256476→2264310，窗口打开、场景哈希及14个模型主体一致，[证据](../artifacts/terminal/viewer/name_migration_validation.json)。未修改服务器、调用模型API或真机。

2026-09-05 统一任务模型：场景生成、`/complex`、Expert 角色与普通对话共用当前用户配置和客户端，不因复杂标记改用 OpenAI。旧 master/expert 选择统一以 master 为准，旧 profile 保留；`/expert-key` 为 `/key` 别名，任一槽位切换更新同一选择。当前安装的 `loop` 已核实直接加载项目源码；运行中的终端须退出并重新启动 `loop`，`/resume` 不加载代码。

验证：项目目录 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`，146 项通过，无跳过。覆盖复杂标记、旧数据库迁移、会话凭据共用、切换地址隔离、咨询与模型改名、真实 MuJoCo 编译及既有 PTY 回归；相关文档本地链接通过。首次完整回归的一条旧向导测试要求 Expert 独立选择，已更新后重跑通过。模型响应使用替身，未调用线上模型 API；未重启用户当前交互进程。机械臂与椅子组合仍超出受限场景编译器范围，本次仅修改模型配置和路由。


## MuJoCo自动打开、窗口控制与模型库（2026-09-05）

最新完整回归：项目目录运行 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`，**144项通过**（26.708秒），包括中文流式／同时输入PTY。新增自动打开、真实物理控制、VFS、下载校验／离线缓存与拒绝篡改测试。未调用付费模型API或真机。

真实GUI验证：[窗口控制与库模型](../artifacts/terminal/viewer/control_library_validation.json)覆盖暂停后时间停止、单步、六向相机、速度、继续、重置、强制重载、网格机器人加载、实际关节变化、越界拒绝。另从App入口验证自然语言场景工具自动打开、`/model-load dynamixel_2r`离线加载、指令Episode/Review、plan回收窗口：[App证据](../artifacts/terminal/viewer/app_autoload_validation.json)、[控制记录](../artifacts/terminal/viewer/app_control_validation.sqlite)。测试窗口与临时目录已回收；证据中的临时路径不用于复开。已下载模型仍保存在默认状态目录models，使用 `/model-load dynamixel_2r` 可复用。

操作与边界见[MuJoCo控制与模型库](MUJOCO_CONTROL.md)。已有Loop终端需重启加载修改；没有接入通用抓取控制器，不将执行器指令回执当作入盒成功。


2026-09-05 椅子生成与旧场景误报修复：固定chair预设包含座面、靠背、四腿，默认无桌/方块；自然语言生成椅子实际调用生成工具，已有窗口自动加载，纠错按原始用户请求重生成/加载。查看器按内容SHA-256判定复用或重载，worker回传实际body/geom及哈希；生成失败不把旧场景当新结果。

项目目录 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`：138项通过，无跳过。真实GUI验证方块场景正常打开、未变内容复用、同路径改成椅子后更换PID且哈希与六部件一致。证据[chair_reload_validation.json](../artifacts/terminal/viewer/chair_reload_validation.json)；实际保存的椅子索引[latest_chair.json](../artifacts/terminal/viewer/latest_chair.json)，MuJoCo离屏[渲染预览](../artifacts/terminal/scenes/b609148d1a9f479c91a14c8c0b827745/preview.png)已查看，确认没有桌子/方块。测试GUI最终关闭，未调用付费模型API或真机。旧Loop需重启加载代码；默认state目录下已保存最新椅子，重启后打开会按scene.json校验再加载。更多边界见[SCENES](SCENES.md)。

2026-09-05 工具返回默认折叠：Terminal对tool/result事件输出短标题、关键参数、结果摘要、实际耗时与/details ID；完整事件保存在conversation.sqlite，/details [ID]支持恢复后读取。ChatAgent显示事件不再预先截为12000字符；送模型的上下文上限仍保留。错误、无匹配、窗口未打开、queued以及review失败/不确定状态不折叠成成功。原生终端采用摘要＋详情命令，不依赖鼠标或全屏UI。见[TERMINAL](TERMINAL.md)。

最终项目目录 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`：135项通过，无跳过。新增长结果持久化/重启读取与状态摘要测试；24/40/80列PTY验证中文流式、同时编辑/排队时原始JSON默认不可见，/details后可见，草稿和正文保留。首次受影响测试仍断言旧原始JSON输出，更新为摘要及详情入口后通过。文档链接检查通过。没有线上模型或真实设备操作，重启旧Loop进程加载修改。

历史记录（2026-09-07已移除句式拦截，现走模型工具循环）：2026-09-05 天气补问与Qwen运行时约束：新增terminal/weather_dialog.py，在有web_weather工具的ChatAgent自由生成前解析常见查询、缺城市补问、疑似“背景/北京”确认、用户城市上下文与换城刷新。天气答案直接由本次工具字段排版，不让模型生成数值或来源；未找到城市询问补充，失败只报本次错误，权限拒绝保持原门禁。通用Master/Web提示同步要求缺必需信息直接问，不把缺参数说成无网络/能力。见[WEB_TOOLS](WEB_TOOLS.md)。

最终项目目录 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`：**133项通过，无跳过**。包含6项天气对话回归：缺城市、错字确认、北京→天津多行查询、同城刷新、明天、恢复错误历史、服务失败/无结果/权限、无效数值及非天气指令。首次全量暴露通用ChatAgent测试中的简化工具schema缺function字段，改为兼容读取后通过。实际联网顺序“天气怎么样→北京→天津的天气呢?换行天气怎么样”验证补问和两次独立天气查询，均返回各自地点、时间、数值与来源；未调用付费模型API。文档链接通过。没有修改Qwen权重，不宣称其他领域幻觉全部解决；旧Loop需重启加载。

2026-09-05 Loop Node核心多进程：core/nodes.py提供可信工厂注册、spawn独立进程、独立supervisor心跳收取、资源独占、命令回执、崩溃隔离、有界停止及回收；toolchain/node_workers.py提供常驻MuJoCo双关节和Linux串口接收节点。终端/node管理和焦点切换，已排队Master消息不改发；/stop、/plan与deny规则回收对应节点，退出先回收节点再等待模型请求。操作与具体边界见[NODES](NODES.md)。

最终验证：项目目录 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q` **114项通过，无跳过**。新增验证覆盖两个真实spawn进程同时运行、资源占用、crash/stale/force-stop/restart、MuJoCo关节目标pass与Episode/Review、PTY子进程串口接收/断线、Master中文流式输出时切换节点/查询/移动的PTY屏幕。首次全量因/commands旧计数42失败；更新为含/node的43后通过。最终修改后的完整回归再次通过。已安装loop入口从/tmp运行 `loop node --state-dir <临时目录>`，无需API配置，/node list与/exit成功；测试节点全部回收。文档本地链接校验通过；没有真实电机控制、付费模型API、跨主机或Windows/macOS节点实机测试。当前node随终端会话生存，不是跨终端attach或系统守护部署。

2026-09-05 用户授权后SSH重试：root@8.134.90.171登录成功；新建/root/workspaces/LoopROS，上传白名单发布包至staging/loopros-server-stage-20260905及README.md。未覆盖Mingle首页或修改nginx／TLS／其他服务。当前IP属于已有Mingle vhost，证书不匹配IP且已过期；最终HTTPS域名仍需用户确认，暂存不等于公网curl安装可用。部署权威记录[DEPLOYMENT](DEPLOYMENT.md)，按project-maintenance同步入口。

2026-09-05 服务器部署预检：用户指定8.134.90.171及/root/workspaces/LoopROS。SSH首次连接按accept-new记录主机公钥；root和默认boxjod均被拒绝(publickey)。检查当前SSH别名没有此目标。HTTP返回301到HTTPS，IP证书名称不匹配；证书所列mingle.box2ai.com直接验证又因过期失败。未创建远程目录、未上传文件、未改网站或TLS配置。准确SSH账号／密钥别名和可用HTTPS入口未确定，停止外部写入，等待用户补充。已按project-maintenance将目标与阻塞记录在[RELEASES](RELEASES.md)。

2026-09-05 HTTPS发布与更新检查：新增release_client.py、scripts/build_release.py和loop --check-update。完整106项Python测试通过，网页Node交互检查通过；实际构建wheel并安装进干净临时venv，loop --version与独立state的/status通过。生成安装脚本通过sh -n，公开JS通过node --check。测试包位于/tmp/loop-ros-release-validation-final-20260905，使用example.invalid占位域名，仅供验证、不可直接发布。服务器SSH目标、HTTPS域名和目录未提供，因此未上传／配置TLS／执行公网curl安装。检查更新不自动安装；重跑安装器升级不是事务性回滚。部署步骤与限制见[RELEASES](RELEASES.md)，按project-maintenance同步地图与安装说明。

2026-09-05 配置统一`.loop`：只有旧`.looper`时整体rename，双方存在不合并；本机原目录已迁移为`/home/boxjod/.loop`，未输出凭据。英文介绍页[website/index.html](../website/index.html)，保留用户原example.html；新增install.sh／install.ps1本地源码一键入口，尚无公网下载URL。Shell --check、完整102项Python回归通过；Chrome桌面截图已检查，网页JS交互另有Node替身检查。Windows脚本无对应运行环境，不能称为实机安装通过。遵循project-maintenance更新安装文档与地图。

2026-09-05 Loop ROS（Loop Robot Operating System）统一命名：发行包loop-ros，内部loop_robot保留；loop、loop ros及旧别名兼容。Ubuntu20.04.6 x86_64／Python3.13.14完整102项回归通过，含中文PTY；干净终端环境无MuJoCo/NumPy，以独立state成功执行/status。已安装用户loop入口。Windows／macOS平台分支已补，CI尚未执行，不能称为各系统实测。当前安装以[INSTALL](INSTALL.md)、支持范围以[PLATFORMS](PLATFORMS.md)为准，下方旧安装记录仅为历史。

2026-09-05 基础串口与设备识别：保留系统串口驱动，新增标准库SerialPort接收会话及open_serial/read_serial/serial_status/close_serial工具；不提供发送/电机运动接口。devices解析别名并读取sysfs内核驱动、USB标识与物理USB归属，Master不再把串口桥接ID当电机型号或把视频节点数当摄像头数。实际端口/USB快照见[HARDWARE](HARDWARE.md)。项目目录运行 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`：97项通过，包含真实PTY收取/限量/断线/关闭、sysfs替身、plan门禁和无猜测探测。真实外设仅枚举/sysfs读取，未打开串口或发送字节；真实电机协议未测试。运行中的旧Loop需重启加载新增工具。

2026-09-05 仿真状态与能力纠正：窗口进程每250ms原子写心跳，3秒过期，不再将一次启动记录作为持续状态；退出写window_open=false。Master每轮注入当前状态及能力，普通“打开／重新打开”和抓放请求执行程序预检，生成桌子／方块请求实际调用生成工具；旧会话不证明成功。当前编译器仍无机械臂、夹爪、抓放控制器，move_sim仅为独立双关节弧度目标。

验证：项目目录 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q` 94项通过；后续场景预检补充断言由test_viewer通过。初次从外层目录执行因导入路径错误失败，改为项目目录运行通过。真实MuJoCo3.12.0桌面使用窗口管理器Alt-F4关闭后window_open=false，重新打开获得新PID及window_open=true；证据 [lifecycle_validation.json](../artifacts/terminal/viewer/lifecycle_validation.json)。测试窗口最终关闭，临时场景已清理。底层xdotool windowclose和未聚焦Escape未触发有效关闭，不算通过证据。没有运行抓取动作或线上模型API。已启动的旧Loop进程需退出后重新启动以加载修改。

2026-09-05 默认桌面与真实GUI修复：空桌允许0个objects，自定义table尺寸／高度／颜色，桌腿实体几何；默认桌面直接本地生成。open_simulator自动检查／安装MuJoCo并启动固定窗口进程，/viewer与自然语言启动共用权限门禁，run_sim明确标为无GUI的离线关节测试。完整90项测试通过，含缺依赖安装替身、无DISPLAY、窗口就绪／进程存活判断及中文PTY。真实桌面曾成功打开默认桌子＋红方块，MuJoCo3.12.0，无需重装；启动时window_open=true且X11查到MuJoCo窗口。最终复查窗口／进程已退出，退出原因未确定，不将启动快照视为持续运行保证。启动证据：[last_manual_launch.json](../artifacts/terminal/viewer/last_manual_launch.json)，场景与report位置见该文件。

2026-09-05 场景反馈修正闭环：生成最多3次请求，将JSON解析、几何或物理校验的具体错误及候选反馈给当前模型；失败报告持久化。缺少接口、unsupported及取消不盲目重试。同一轮相同不可重试工具失败不重复执行；4轮工具调用后追加1轮无工具总结。完整85项测试通过（含pyte屏幕测试）。修正序列“无效JSON→方块z=0→正确z=0.825”由模型替身给出，真实MuJoCo编译并推进250步，方块保持桌面支撑、存在接触；真实API未调用。命令：`PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`，额外支撑断言经`tests.test_scenes`的10项检查通过。

2026-09-05 消息块排版：取消逐行 `Master ›`，助手正文每块仅首次显示 `●`，后续正文／列表缩进、空行保持空白；输入使用 `❯`，工具显示 `● name(arguments)`、结果使用 `↳`。沿用完整行写入机制。含中文多行列表、连续排队和24×6／40×12／80×24 PTY屏幕验证的完整79项测试通过，命令为 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`。

2026-09-05 品牌统一为 **Loop ROS**：目录／Python 包 `loop_robot`，发行包 `loop-robot`。`.venv/bin/python scripts/install.py` 已安装 `loop`、`loop-switch`，修复此前指向旧目录的用户命令链接，保留 `looper`／`looper-switch` 别名。未迁移或删除凭据、会话、任务及日志。

项目外 `/tmp` 已验证 `loop --version`、`loop robot --version`、`looper --version` 均返回 `Loop ROS 0.1.0`；`loop robot --once /commands` 正常。隔离配置的真实 PTY 验证 `loop robot` 进入 Loop Switch 向导并取消退出。完整命令 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`：**79 项通过，无跳过**，包含中文流式输入渲染和新名称／配置兼容测试。文档链接检查通过，无付费 API 或真机调用。

2026-09-05 中文流式显示覆盖修复：根因是 `print(..., end="", flush=True)` 把未换行片段提交到 stdout，随后输入重绘覆盖原文。未完成的文字改由输入渲染器显示，完整行／轮次结束后再写入滚动历史；实时预览按字符显示宽度裁剪，不丢弃完整历史。真实 PTY 配合 pyte 屏幕模拟器验证24×6、40×12、80×24，覆盖中文分片、同时排队11、中文草稿中间插字及Ctrl-C保存退出。含渲染检查的77项测试通过，无线上模型调用。

验证命令（项目目录）：`PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`。本次 pyte 安装在临时验证目录；若该目录已清理，可用 `.venv/bin/python -m pip install --target /tmp/looper-terminal-validation pyte` 重建。不提供 pyte 时仅屏幕模拟测试跳过；其余测试仍运行。持久回归入口为 `tests/test_terminal_render.py` 与 `tests/test_interactive.py`。

2026-09-05 交互输入升级：行内 prompt_toolkit 编辑器、Chat Completions SSE、图片／视频抽帧附件、FIFO 队列及取消后暂停。无固定分栏或最低窗口尺寸。Ctrl-C先清空非空输入，空输入时保存退出；conversation.sqlite保存上下文、草稿、等待队列和流式事件，同配置恢复，队列默认暂停。按键替身覆盖插字、多行粘贴、队列暂停恢复和后台输出保护草稿；真实 ffmpeg 合成视频抽出2帧。完整回归75项通过；真实PTY覆盖24×6、40×12、80×24、160×40及运行中缩放到32×8，均通过/queue、/exit且未切备用屏。API和模型视觉能力尚未在线验证。用法见 [TERMINAL](TERMINAL.md)。

2026-09-05 简化 Switch：完整回归 **65 项通过**；隔离 LOOPER_HOME/state 的真实 PTY 验证无 Key 自动进入向导、取消正常退出。自定义模型发现与 Responses 工具循环采用替身测试，未使用真实 Key。参见 [QUICK_SETUP](QUICK_SETUP.md)。

2026-09-05 用户全局目录增补：`.venv/bin/python -m unittest discover -s tests -q` 共 **59 项通过**。新增 LOOPER_HOME 隔离测试覆盖凭据保存、endpoint 隔离、POSIX 0600、配置覆盖、Master harness 与长度预算。初始化本机 ~/.looper 与非敏感默认规则；未写真实 Key、未调用 API。参见 [USER_HOME](USER_HOME.md)。

## Installed terminal — 2026-09-05

From the project directory, `.venv/bin/python scripts/install.py` installed editable `loop-robot==0.1.0` and user-level `loop` / `loop-switch` links. Existing configuration and runtime data were preserved.

Verified from `/tmp`: `loop --version` returns `Loop ROS 0.1.0`; `loop --help` and `loop-switch list` succeed. Interactive PTY startup displays the English welcome screen, active model names and current directory; `/exit` exits cleanly. The PTY test used an isolated `--state-dir` and did not run existing timers. No live API or hardware calls were made.

From the project directory, `.venv/bin/python -m unittest discover -s tests -v`: **56 tests passed**, including MuJoCo, Mink and three new welcome/help tests. See [INSTALL](INSTALL.md) for installation, state locations and limitations.

扩展控制面后53项测试通过；`./loop --once /commands`报告41个slash入口。/move与/home由真实MuJoCo离线测试验证，权限和操作说明见 [CONTROL_SURFACE](CONTROL_SURFACE.md)。

模型切换器增补后：完整环境45项测试通过。`./loop-switch list`、`./loop --once '/switch list'` 已验证；均不请求API。使用与数据目录见 [MODEL_SWITCH](MODEL_SWITCH.md)。

多 Agent 增补后：完整环境40项测试通过（含真实替身子进程，不调用外部API）。启动后对话对象为 Master，管理命令见 [AGENT_RUNTIME](AGENT_RUNTIME.md)。

新增场景生成与 GPT-6 路由后，完整环境 `.venv/bin/python -m unittest discover -s tests -q` 共 34 项通过。`/scene`、`/complex` 用法见 [SCENES](SCENES.md)；模型调用仅替身测试，真实 API 未运行。

## 默认交互入口

在本项目目录运行 `./loop`，输入 `/key` 后对话，`/help` 查看 shortcut。默认 Qwen，配置与边界见 [TERMINAL](TERMINAL.md)。`./loop --once /status` 可离线检查入口；`--once` 不运行定时器，也不批准启动策略进程。

2026-09-05：完整环境 27 项测试通过；`./loop --once /sim` 通过并保存证据到 artifacts/terminal/episodes.sqlite。API 使用替身验证，未调用付费 API 或启动真实策略模型。终端会创建 SQLite、锁文件和按需服务日志，不自动连接机器人。

工作目录：`/home/boxjod/Workspace/box2net/loop_robot`。Python 3.8.10，标准库，无安装步骤。

```bash
python3 -m unittest discover -s tests -v
python3 examples/run_demo.py
```

成功信号：测试全部 OK；demo 输出 verdict=pass、max_joint_error_rad 约 0.1，退出码 0。demo 第一次 review 为 fail、第二次为 pass。

副作用：默认在 `artifacts/demo.sqlite` 追加事件，不覆盖历史；可以用 `--output /明确路径/demo.sqlite` 指定输出。测试使用内存 SQLite；Python 可能生成 `__pycache__`。不连接网络、机器人或 GPU，不启动后台进程。

检查证据：

```bash
python3 -c 'from core.store import EventStore; s=EventStore("artifacts/demo.sqlite"); print([(k,v) for k,v in s.events() if k=="review"]); s.close()'
```

示例只验证数值反馈闭环，不能作为物理操作成功证明。硬件与外部模型接入未验证。

## 可选物理工具链（2026-09-05）

项目 `.venv` 使用 Python 3.13，已安装并验证 MuJoCo 3.12.0／Mink 1.3.0。安装版本见 `scripts/requirements-sim.txt`，不改系统 Python 与旧仓库环境。

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python examples/run_sim.py
```

成功信号：19 项测试全部通过，包括 MuJoCo 动力学／reset／过期动作和 Mink FK／IK；物理 demo verdict=pass，关节误差约 1e-5 rad。demo 使用内存 SQLite，不持久化物理记录；默认数值 demo 仍写 artifacts。

基础环境命令保留，缺少可选物理依赖时跳过对应测试；本机系统 Python 的已有 MuJoCo 缺 glfw，不视为可用仿真环境。完整验证以 `.venv` 为准。MuJoCo 异常时可能写 `MUJOCO_LOG.TXT`（已忽略），不启动 viewer。

ROS 数据整理与资源池用替身／纯数据测试；ROS 通信、真实 GPU 回收及 Ego2MuJoCo 全 pipeline 尚未验证，不把单元测试通过视为这些集成完成。

## 联网工具（2026-09-05）

使用说明与服务边界见 [WEB_TOOLS](WEB_TOOLS.md)。验证命令（项目目录）：

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest test_web test_terminal test_control test_agents test_setup test_providers test_home
```

52项相关测试通过，其中13项新增联网测试。最初以stdin启动聚合测试时，multiprocessing spawn无法重载`<stdin>`，改用上述模块入口后全部通过，无需修改子Agent运行时。

真实工具验证：web_fetch读取example.com成功；web_search搜索ROS2 documentation返回来源链接；web_weather查询上海/CN返回地点、Asia/Shanghai时区、当前与每日预报。天气服务数据时间为2026-09-05T18:45（返回时区）；测试仅证明服务与解析链路，不把该数据当长期有效天气。真实模型主动选工具未测；工具结果回传模型使用替身验证。

本机网络存在TUN Fake-IP DNS，HTTPS域名映射198.18.0.0/15的兼容及拒绝私有/本地地址的边界已测试。TLS校验未关闭，系统Python的证书配置未修改；使用项目`.venv`。

已确认`~/.local/bin/loop`使用项目`.venv`并加载本项目源码，入口工具列表含三项web工具；已运行的终端重启后加载。不修改用户模型Key、全局harness或服务器部署。

2026-09-05 日常家具和窗口交互：`PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q` **169 项通过**。新增 Fuel 检索/有界 ZIP/单刚体转换、双铰链衣柜、空格暂停及暂停拖拽。真实 App 生成与官方杯子/白柜下载通过；真实 X11 鼠标拖球、右侧执行器滑条和空格通过。操作、资源与限制见 [HOUSEHOLD_ASSETS](HOUSEHOLD_ASSETS.md)，原始证据见 [household_interaction.json](../artifacts/terminal/viewer/household_interaction.json)。本轮无需新依赖，无真机动作。

2026-09-05 单物体生成纠偏：完整回归 **172 项通过**（同上述 unittest 命令）。真实 `App.agent.reply` 输入“现在打开的是一个完整的场景啊我的妈,我需要的只要一个衣柜”，确认最终只含衣柜本体和左右门，两个执行器，窗口重新启动且哈希匹配。[实际对话入口验证](../artifacts/terminal/viewer/wardrobe_only_validation.json)。旧终端进程需重启才能加载入口代码；不要将 viewer reload 当成终端 reload。

### 2026-09-05 slash 补全与流式回复

输入 `/` 自动显示命令，按前缀过滤；Tab/方向键选择，Enter 先接受已选候选，再次 Enter 执行，Esc 关闭候选。复用现有 HELP 和终端编辑命令，保留普通主屏与窄窗口支持。普通聊天不再被工具结果总结回调整轮缓存；有效 finish_reason 后立即结束读取，真实截断仍失败并保留已显示内容，无待执行队列时不阻塞下一条消息。

验证：项目目录 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest tests.test_stream_completion tests.test_completion tests.test_interactive tests.test_terminal_render tests.test_scene_intent -q`，24 项通过，包含 24/40/80 列中文流式输出同时输入、补全和排队的真实 PTY 屏幕验证。流式传输使用替身，未调用用户线上模型。媒体上下文回归原先依赖固定消息索引，已改为按 user 角色查找，以兼容新增总结上下文。补全实现过程中窄屏预留菜单空间及 Esc 双层等待已验证处理。

已检查项目 viewer 所有权记录，没有可接管的活动 MuJoCo 窗口（window_open=false、pid=null）；本次无场景变更。现有交互终端需退出并重新运行 `loop` 加载修改，不强制中断用户进程。

2026-09-05 历史恢复与逐轮总结：完整 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q` **185 项通过**，包含会话隔离、完整历史、失败总结、恢复不运行队列和真实 PTY 历史选择/中文流式输入。真实当前衣柜窗口重启、内容哈希及工具总结核对通过：[运行证据](../artifacts/terminal/session_validation.json)。使用说明与根因边界见 [SESSION_MEMORY](SESSION_MEMORY.md)。没有进行模型能力 A/B 评测或额外总结模型调用。

### 2026-09-05 `/switch` 菜单先显示再读编号

修复 `patch_stdout` 将菜单文字排入事件循环、同步 `input()` 阻塞该循环而只显示编号提示的问题。交互 slash 命令在 `run_in_terminal` 接管期间使用进入编辑器前的 stdout/stderr，结束后恢复异步流式输出。

验证：`PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest tests.test_terminal_render tests.test_providers tests.test_interactive.InteractionTests -q` 中 15 项通过，新菜单 PTY 测试仅失败于把成功提示误写成 `Switched and saved`；按真实返回 `Switched:` 修正断言后，该测试单独复跑通过。共验证 16 项，包含菜单选项在读取编号前真实可见、Enter 取消、编号选择成功、退出恢复及中文流式/补全屏幕回归。测试使用临时配置，没有修改用户 provider 或调用模型。

### 2026-09-05 输入分隔线、队列编辑与直接命令补全

输入上下灰线随窗口宽度变化；等待消息在输入上方显示总数及最近最多三条，窄窗口收缩预览。空输入按↑取回最近消息和附件，回车重新入队；Ctrl-C 清空草稿，空输入时请求停止活动任务并暂停未暂停队列，内容保留。slash 按前缀匹配，Enter 直接执行所选或首个候选，完整命令优先，`/per` 可执行 `/permissions`。

验证：项目目录 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest tests.test_terminal_render tests.test_interactive.InteractionTests tests.test_completion -q`，12 项通过。覆盖 24/40/80 列真实 PTY 中的中文流式/分隔线/补全、队列预览与↑编辑、菜单编号显示和选择、快速输入 `/per` 后回车、附件取回重排。补充 Ctrl-C 暂停保留两条队列的断言后，队列编辑测试单独复跑通过。没有线上模型调用；检查时没有可接管的活动 MuJoCo 窗口。

### 2026-09-05 slash 结果排版与会话选择继续聊天

新增 terminal/command_display.py，仅在交互命令展示处将 JSON 改为可读字段/列表，权限按 allow/ask/deny 分组，非交互 dispatch 契约不变。权限命令显示后进入规则→动作两步候选，最后 Enter 才应用；已有门禁不变。修正 `/resume ` 自动填入后光标仍在开头导致候选不匹配的问题；方向键选择、Enter 恢复后显示会话标题，下一条消息使用所选历史上下文，旧队列仍暂停。历史总结改为可读文本。

验证：`PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest tests.test_command_display tests.test_completion tests.test_interactive tests.test_session_render tests.test_terminal_render -q`，25 项通过（含实际 PTY 菜单、中文流式、队列和分隔线）。补充完整权限菜单选择测试及恢复标题/总结显示后，`tests.test_interactive.InteractionTests.test_permission_menu_selects_rule_and_action tests.test_interactive.ResumeInteractionTests tests.test_command_display` 共 6 项通过。会话测试捕获下一轮模型入口参数，核实包含所选旧会话；模型用替身，权限修改仅发生在临时测试配置。没有改场景或重启用户交互进程。

### 2026-09-05 独立 Actions 面板与实际设备查询

权限/会话/历史/结构化 slash 结果转入输入区附近的 Actions 面板，支持 PgUp/PgDn、Esc、候选选择；以 Operator 事件保存，不加入聊天历史。工具调用改为独立 Tool 标记。设备查询补齐“可以检测我的电脑连接上了什么吗？”等明确请求的直接受控执行；教程/否定不自动查，权限拒绝不绕过。枚举扩展 USB 总线设备和 input 节点，回答与总结保存真实计数，长列表通过 /details 查全量，未打开设备或发送字节。

验证：`PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest tests.test_device_inventory tests.test_serial tests.test_tool_display tests.test_command_display tests.test_interactive tests.test_session_render tests.test_terminal_render -q`，35 项通过。覆盖原始用户说法、权限拒绝、设备替身目录、操作与聊天上下文隔离、菜单选择、实际 PTY 队列/中文流式/会话恢复。随后修正输入自动换行时的面板高度预算，运行 terminal_render/session_render/session_resume，除新增六行窄屏面板测试需先关闭遮挡面板的候选菜单外其余通过；该测试调整为先关闭候选再检查面板，单独复跑六行与普通窗口通过。

本机只读实测：原始用户请求经 agent.reply 调用实际 devices（模型入口设为禁止调用替身），发现 9 个 USB 项（含集线器）、3 个串口/摄像头节点、32 个输入节点；opened=false。证据：[device_inventory_validation.json](../artifacts/terminal/device_inventory_validation.json)。没有调用线上模型、发送设备指令或修改仿真场景。

2026-09-05 持久反馈任务：`LOOP_TASK_AUTOSTART=0 PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q` **223 项通过**。覆盖反馈驱动的独立子进程再执行、连续失败重规划、文字成功不能验收、等待/取消/中断保护、事件/定时去重、前台自动交接、后台通知与终端即时面板分页。真实用户配置模型通过独立后台进程调用 robot_toolchains 完成只读验收；监督进程重启后原任务 succeeded 保留，MuJoCo owner 文件不变。[运行证据](../artifacts/terminal/task_service_validation.json)、[配置与操作](TASK_RUNTIME.md)。后台监督服务已保持运行；默认定时与串口路径触发示例为关闭状态，未进行实际设备拔插测试。

2026-09-05 用户历史灰底：已提交及排队回显使用深灰底色，每行重置，原始会话文本不变。`LOOP_TASK_AUTOSTART=0 PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest tests.test_session_render tests.test_terminal_render -q`，5 项真实 PTY 测试通过，覆盖用户行灰底、Summary 默认背景、中文流式与输入/排队。停止任务命令见 docs/TERMINAL.md。本轮未停止用户后台服务或重启 MuJoCo。

### 2026-09-05 输入框固定底部并去除多余空白

PromptSession 默认将剩余渲染高度分配给输入窗口，导致菜单收起或正文缩短后输入框留白。布局改为底部对齐，输入窗口 dont_extend_height 仅占实际内容高度；使用原生主屏，不启用 alternate screen。占位提示按实际列宽裁切并预留末列，避免窄窗口提示刚好填满一行时额外换行。

验证：项目目录 `LOOP_TASK_AUTOSTART=0 PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest tests.test_terminal_render tests.test_session_render -q`，6 项通过。真实 PTY 覆盖 24/40/80 列中文流式、输入编辑、队列、补全、会话菜单；6×24 与24×100窗口额外验证面板收起、多行输入清空、SIGWINCH调整大小后输入仍在底部状态栏上方，上下分隔线紧贴实际输入。回归中将旧队列提示断言同步为当前“↑ edit queue”文案。没有调用线上模型、重启用户进程或改动仿真。

2026-09-05 任务按钮与权限预设：空输入左右切换任务，上下选择查看/继续/取消，Enter 调用既有受控命令；候选菜单纵向显示并支持四方向选择。新增 default/plan/cautious/yolo 权限预设，持久化并可继续逐项定制。`LOOP_TASK_AUTOSTART=0 PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest tests.test_terminal_render tests.test_command_display tests.test_session_render -q` 9 项通过；control/interactive/completion 29 项通过；最后按钮布局与执行绑定调整后，实际 PTY task_buttons_and_permission_profiles 再次通过。涵盖切换不执行、取消指定任务、菜单放行/询问/恢复默认、中文流式、窄屏、输入与队列。测试只使用临时状态；未更改用户当前权限、取消真实任务或重启 MuJoCo。交互终端需重开以加载新键位。

### 2026-09-05 CLI 输入与异步边界检查

退格/粘贴/Home-End 编辑刷新 slash 候选，Esc 关闭后不立即弹回；多空格参数匹配、纯附件提交、附件失败草稿恢复已修复。耗时 viewer/scene/complex/sim/models/model-load 走单工作线程，输入与取消仍可响应，操作结果保留在 Actions。非运行界面不启动会话补全任务。

复查入口：`LOOP_TASK_AUTOSTART=0 PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest tests.test_cli_edges tests.test_completion tests.test_interactive tests.test_terminal_render tests.test_session_render -q`。pyte 为 PTY 屏幕验证依赖；未安装时不要把跳过视为屏幕验证通过。真实 80×24/40×12 输入→退格→重输→Esc 的 8 份屏幕快照已核对。目录外 --help/--version/--once /status 均退出 0。本轮检查过程与最终完整回归结果见[CLI 检查记录](../../projects/reports/16_cli_interaction_review.md)。

最终完整验证：`LOOP_TASK_AUTOSTART=0 PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`，248 项通过（69.820 秒），无后台补全数据库异常；[日志](../artifacts/cli_review/full_regression.log)。

## 文件与可更新指令

从目标项目目录启动 `loop`。文件工具以该目录为写入边界；安装新版本代码后重启终端进程，之后 Skills 和 Markdown harness 更新在下一次模型调用自动加载。操作、权限和验证入口见 [CODING_AGENT](CODING_AGENT.md)。普通代码改动不重启 MuJoCo。

2026-09-05 机械臂硬件读取入口与跨平台串口：`LOOP_TASK_AUTOSTART=0 PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest tests.test_device_inventory tests.test_serial tests.test_serial_discovery tests.test_control -q` 19 项通过；platform_support/nodes 12 项通过。Linux 实际枚举发现 /dev/ttyACM0（cdc_acm，1a86:55d3），未打开、未发送；[证据](../artifacts/terminal/arm_discovery_validation.json)。Windows/macOS 已实现分支并通过替身测试，原生实物待验；电机身份查询和控制测试待明确设备协议、波特率与对应驱动。本轮未重启 MuJoCo。

## 当前窗口运动检查

轨迹参数和边界见 [MUJOCO_CONTROL](MUJOCO_CONTROL.md)。先查当前窗口 qpos/actuators/body_poses，再用 simulator_control 的 move_joints / move_cartesian；move_sim 仍不控制 GUI。测试：`LOOP_TASK_AUTOSTART=0 .venv/bin/python -m unittest tests.test_viewer_motion tests.test_simulator_control tests.test_composition tests.test_viewer tests.test_cli_edges`。PTY 检查另运行 test_terminal_render（需要 pyte）。

### 2026-09-05 左右切换仅限运行任务

任务面板仅展示 running，结束后下一次状态刷新自动移出；无运行任务显示 No running tasks，保留任务账本。同步更新 TERMINAL、TASK_RUNTIME 和 AGENTS 约定。验证：`LOOP_TASK_AUTOSTART=0 PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest tests.test_cli_edges.CliEdges.test_task_arrows_only_cycle_running_and_drop_finished_tasks tests.test_session_render.SessionRenderTests.test_task_buttons_and_permission_profiles -q`，2 项通过（含真实 PTY）。覆盖左右循环排除未运行任务、结束/取消自动移出、空列表和原记录保留。此前 CLI/会话组合 26 项中 25 项通过，旧 PTY 的 queued 可选断言按新需求更新后通过本次复验。

2026-09-05 Claude Code 会话功能对照：新增交互 /rename、/sessions、/export，resume 候选按标题匹配。首次专项测试发现 session_terminal 替身未接收新 stop_event 参数，修正后执行 `LOOP_TASK_AUTOSTART=0 PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`，271 项通过（74.919s）。包括真实 PTY 对话→命名→搜索→导出；保存/重开不丢名称、超过30条历史搜索、提供商隔离、媒体省略及导出不覆盖。出现 sqlite ResourceWarning，不影响测试通过；未将测试通过等同所有用户环境/真机验收。文档链接核对通过。2.1.88 官方 npm 入口404，未取得泄露源码；本轮按官方现行会话功能独立实现，详见 projects/reports/18_claude_cli_reference.md（项目外层）。未启动/重启 MuJoCo，旧终端需重新打开加载新命令。

### 2026-09-06 Hermes 参考与经验持续学习

新增 core/experience.py 和 terminal/learning.py，前台工具回合及后台任务尝试写入经验；按工作目录/服务配置召回，来源绑定笔记可修订/停用，技能更新强制校验内容哈希并保留备份。默认不增加训练、外部记忆服务或模型后台回顾进程；普通聊天不产生无证据经验。用法见 [LEARNING](LEARNING.md)。

项目目录：`LOOP_TASK_AUTOSTART=0 PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`，280 项通过（76.694 秒）；最终补充故障降级边界后 `tests.test_learning` 10 项通过。核心存储仅标准库。独立测试子进程确实召回历史并验收、跨 App 重建后确实召回并写笔记；模型为替身。1000 条本地合成经验 P95 约 15 ms。见[完整对照报告](../../projects/reports/19_hermes_continuous_learning.md)和[验证产物](../artifacts/learning/recall_benchmark.json)。没有改变用户运行中终端/监督服务或 MuJoCo。

### 2026-09-06 多载体与多 Host 部署配置

`loop node --deployment examples/deployments/two-hosts.json --host bench-a` 进入本地载体控制；bench-b 使用同一文件且只执行其本地分配。默认状态按部署/主机分开。`/carrier list/start/status/move/stop` 复用 NodeRuntime，控制需当前 instance_id，模型调用需 request_id；远程分配不自动联网或执行，配置加载不启动设备。见 [DEPLOYMENTS](DEPLOYMENTS.md)。

`LOOP_TASK_AUTOSTART=0 PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`：289 项通过（79.389 秒）。覆盖独立 MuJoCo 子进程的目标隔离与 Review、回执丢失和重试、旧实例拒绝、双 Host 隔离、旧 Node/权限/任务/终端回归；[日志](../artifacts/carriers/full_regression.log)。两个 Host 配置分别从 /tmp 加载 CLI，未启动设备；[入口证据](../artifacts/carriers/deployment_smoke.json)。没有测试跨机器网络或真实电机，没有重启用户现有终端、监督服务或 GUI。

飞特舵机：见 [FEETECH](FEETECH.md)。本地依赖检查用 `.venv/bin/python -m toolchain.feetech environment`，先枚举实际端口，再做协议扫描和状态读取；不运行猜测的 ASCII/PWM 诊断脚本。

2026-09-06 对话与输入框空白：取消底部对齐，CompactPrompt 按实际首选高度绘制无候选状态，避免旧渲染高度形成空白。terminal_render/session_render 7 项真实 PTY 测试通过（33.247s）；补充历史上下翻页不增加记录的断言，并复验中文流式/队列编辑及 interactive 测试，结果见 /tmp/loop-input-gap-scroll.log。覆盖窄屏、菜单关闭、输入收缩、窗口缩放；原生滚动历史在 pyte 中验证，不等于已在每种终端模拟器滚动条上实测。未重启 MuJoCo 或用户终端。

Python脚本实际执行与权限见 [PYTHON_EXECUTION](PYTHON_EXECUTION.md)。先读取脚本哈希，再用 run_python；不要以 read_file/web_fetch 或 chmod 冒充执行能力。当前用户已授权此动作，旧终端正常重启加载。


## 2026-09-07 release candidate verification

From LoopROS, `.venv/bin/python -m pip wheel . --no-deps --wheel-dir artifacts/release-candidate` succeeded using isolated build dependencies. `--no-build-isolation` failed because setuptools was absent in the runtime venv. The 0.1.0 wheel inventory has 96 entries; known private/runtime paths were excluded. Extracted-wheel `--version` and `--once /status` passed outside the source tree using the existing interpreter dependencies. This does not establish installation in a fresh dependency environment.

`test_setup` (7), `test_coding_agent` (10), `test_harness_behavior` (9), and `test_agents` (6) passed. One process cleanup ResourceWarning occurred in harness tests; the named process was no longer present afterward. No live GPT-6 call, GUI restart or hardware action was performed. See `artifacts/release-candidate/validation.json`, `SHA256SUMS` and [GitHub preparation](GITHUB_RELEASE.md).


## 2026-09-07 coding-first cleanup

`DISPLAY= LOOP_TASK_AUTOSTART=0 .venv/bin/python -m unittest discover -s tests -q` ran 297 tests. Seven stale fixture/expectation failures were corrected; `DISPLAY= LOOP_TASK_AUTOSTART=0 PYTHONPATH=tests .venv/bin/python -m unittest test_composition test_serial test_home test_terminal test_viewer_motion -q` passed all 29 tests in those modules afterward. The other 268 tests were unchanged and had passed. Full-run SQLite ResourceWarning remains recorded; see `artifacts/coding-cleanup/validation.json` and logs. Live model semantics remain unverified.

Rebuilt local 0.1.0 candidate has 94 wheel entries, excludes removed interceptors, and passes extracted-wheel startup outside the project. Checksums and inventory remain at `artifacts/release-candidate/`. No real GUI or hardware motion was performed.


## 根目录分类整理（2026-09-07）

配置默认值/示例移至 `configs/`，Logo 移至 `assets/`，演示及原有 `mjmodel.mjb` 移至 `examples/`，安装脚本和仿真依赖清单移至 `scripts/`，Changelog 移至 `docs/`。根目录仍映射为 `loop_robot` 包；现有命令入口、用户配置覆盖与状态目录保持原路径。构建旧缓存保存在 `artifacts/layout-check/previous-build/`，新增根目录 MuJoCo 输出及 pytest 缓存忽略规则。

从项目根目录验证：

- `.venv/bin/python scripts/install.py --check`、`sh scripts/install.sh --check` 通过；项目外绝对路径调用也通过。系统 `python3` 为 3.8，按预期被安装检查拒绝，验证使用项目 Python 3.13。PowerShell 仅静态核对，未运行 Windows 实测。
- `.venv/bin/python examples/run_demo.py --output artifacts/layout-check/demo.sqlite` 返回 `verdict: pass`；没有启动或重启 MuJoCo。
- `PYTHONPATH=tests .venv/bin/python -m unittest test_platform_support test_branding test_terminal test_agents test_coding_agent test_task_supervisor test_releases test_home`：55 项通过。最初从 stdin 运行的组合测试因 multiprocessing spawn 无法读取 `<stdin>` 失败，改用正式 unittest 模块入口后通过。
- `node --test tests/website.test.cjs`：1 项通过；网页 Logo 与 Windows 源码安装路径已更新。
- `.venv/bin/python -m pip wheel --no-deps --wheel-dir artifacts/layout-check/wheels .` 成功。无隔离构建因本地缺少 setuptools 未通过，标准隔离构建成功；解包核对新资源齐全、无旧根路径资源和私有状态文件，并从临时目录验证配置/Agent/任务配置读取及 `python -m loop_robot --version`。
- 修改的本地文档链接核对：新路径存在；原先指向项目外 `../../projects/reports/` 的缺失报告链接仍未修复。`git diff --check` 通过。


## 双语 README 与透明 Logo（2026-09-07）

新增根目录 `README.zh-CN.md`，与 `README.md` 互链，两份文档顶部引用 `assets/logo-transparent.png`（显示宽度 280）。保留 `assets/logo.png` 原图。使用内置 image_gen 编辑原图，肉眼核对无限环机器人、蓝色箭头、眼睛、天线与三个右侧端子；生成式编辑不保证逐像素一致。Pillow 只用于读取验证：PNG 为 RGBA，1672×941，alpha 范围 0–255，完全透明像素 1,155,325。两份 README 的本地引用全部存在，`git diff --check` 通过；未修改运行代码或启动仿真。

最终图片提示词（内置工具模式）：

> Use case: background-extraction. Edit the supplied Loop ROS logo for a repository README. Remove only the pale gray/white background, including the background visible through the infinity loops and around the antenna and circuit traces. Output a PNG with actual transparent alpha, no checkerboard painted into the image. Preserve exactly the existing infinity-shaped robot silhouette, crossing gap, dark strokes, blue arrow, blue eyes, antenna and three right-side terminals, their colors, proportions and arrangement. No redesign, no added text, no shadow, no new elements. Keep the full logo visible with a small transparent margin.


## uv 安装引导（2026-09-07）

`python3 scripts/install.py --terminal-only` 现在允许系统 Python 3.8 启动，自动准备用户级 uv，再创建 Python 3.12 `.venv` 并通过 `uv pip` 安装；已有可用 Python 3.10+ 环境复用。`--check` 不下载、不安装。已有损坏/低版本环境及非项目命令冲突均保留并报错。下载优先 curl，无 curl 时使用标准库 HTTPS；不关闭证书验证。

验证：`PYTHONPATH=tests python3 -m unittest test_install test_platform_support -q`，8 项通过。使用本机 `/usr/bin/python3` 3.8.10、临时源码副本及隔离 HOME 完成真实 terminal-only 安装；uv 选择本机 Python 3.12.9 创建全新环境，项目外 `loop --version` 返回 0.1.0，重复安装成功。另在临时用户目录实际下载 uv 0.12.10，执行版本检查和未加入 PATH 的复用检查成功。Python 运行时自动下载分支和 Windows/macOS 原生安装未实测。最初 urllib 下载遇到本机 CA 验证失败，采用官方支持的 curl 下载方式后通过。没有替换当前项目 `.venv` 或修改系统 Python。


## 用户配置归位与迁移验证（2026-09-07）

用户 Agent 注册表现读取 `LOOP_HOME/agents.json`，缺省回退发行默认；任务策略优先级为状态目录 → `LOOP_HOME/task_runtime.json` → 发行默认。配置仍经过原有校验和工具权限门禁。Skills、harness、模型选择及状态目录沿用已有存储约定，未搬动当前用户实际配置/凭据/活动状态。`docs/USER_HOME.md#device-migration` 列出各类文件和跨设备步骤，也给出显式 `LOOP_STATE_DIR=$LOOP_HOME/state` 的单目录方案。

验证命令：`PYTHONPATH=tests .venv/bin/python -m unittest test_user_portability test_home test_skills test_agents test_task_supervisor test_providers`。34 项通过；新增临时目录迁移测试覆盖完整 Skills 包、指令、全局配置、Agent加载、任务策略优先级、模型选择和凭据地址隔离。两份 README 和迁移文档的本地链接、`git diff --check` 通过。服务器只读检查见 DEPLOYMENT；IP下载链接仍因证书不匹配不可用，未执行发布或改动 nginx/TLS。


2026-09-07：按用户最新要求，中英文 README 均恢复引用原始白色背景 `assets/logo.png`；透明版本保留为未使用备选。已核对两份文档的图片引用和文件存在性。


## 源码卸载脚本（2026-09-07）

新增 `scripts/uninstall.py`，系统 Python 3.8+ 可运行；`--check` 只读预览。仅移除本源码副本 `.venv` 及匹配的用户命令，保留其他副本命令、源码、用户配置/Skills、状态数据、uv、共享 Python 与 PATH。不自动停止进程，使用前退出 Loop 与后台服务。非虚拟环境目录拒绝删除；符号链接/junction 只移除链接。

`PYTHONPATH=tests python3 -m unittest test_uninstall test_install test_platform_support -q`：12 项通过，含临时目录真实子进程执行预览、删除、重复卸载，以及用户数据/外部链接目标/其他命令保留；Windows launcher 与安装器格式匹配采用替身验证，Windows 原生删除未实测。本工作区仅执行 `python3 scripts/uninstall.py --check`；发现全局命令指向另一份 `Workspace/box2net/LoopROS`，按归属保留，未卸载当前环境。

2026-09-07：中英文 README 顶部白底 Logo 改为 `width="100%"`，与正文容器同宽，保持原图宽高比；两份图片引用及 `git diff --check` 通过。


## 卸载后旧副本命令阻挡重装（2026-09-07）

根因：用户卸载 `Workspace/LoopROS/.venv`，但全局四个入口仍指向 `Workspace/box2net/LoopROS/.venv/bin/`；卸载按归属保留，安装随后因冲突拒绝。安装器新增 `--replace-launchers`，依赖成功安装后才将冲突入口备份为 `.loop-ros-backup.N` 并切换到当前副本；默认仍保护冲突入口，报错提供可执行处理命令。`--check` 同时核对入口冲突。备份不覆盖旧备份，不移动真实目录，卸载保留备份。

验证：`PYTHONPATH=tests python3 -m unittest test_install test_uninstall test_platform_support -q`，14 项通过。覆盖只读预览、安装失败时原入口不变、成功后备份和切换、编号备份保留、卸载、目录冲突保护；新增冲突检查暴露旧测试未隔离 HOME，修正 fixture 后通过。在用户当前目录实际执行 `python3 scripts/install.py --terminal-only --replace-launchers` 成功，四个旧入口均备份为 `~/.local/bin/<name>.loop-ros-backup.1`；再次执行原命令 `python3 scripts/install.py --terminal-only` 成功。项目外 `/tmp` 执行全局 `loop --version` 返回 0.1.0，`loop-switch --help` 返回 0，四个符号链接目标均核实为当前源码 `.venv/bin`。没有删除旧项目、配置或运行数据，也没有启动仿真或后台任务。Windows 切换分支未做原生实测。


## 卸载同时清理旧副本命令（2026-09-07）

按用户纠正，卸载归属从“仅当前源码路径”调整为“确认属于 Loop ROS 的全局入口”，覆盖四个当前/旧别名。POSIX 静态解析入口脚本中的 `loop_robot.launcher` 顶层导入，Windows 匹配安装器标记及完整 cmd 模板；不执行旧入口。只删除全局入口和当前 `.venv`，不删除旧源码环境、用户数据或命令备份。其他软件及无法核实的入口保留；本项目断链可删除，其他目录不可核实的断链保留。本条替代此前“旧副本命令一律保留”的行为说明。

验证：`PYTHONPATH=tests python3 -m unittest test_uninstall test_install test_platform_support -q`，17 项通过。临时源码副本和隔离 HOME 内完成真实子进程：清理指向旧副本的四个入口 → 用 Python 3.8 运行原始 terminal-only 安装命令（不加 replace 参数）→ uv 创建 Python 3.12 环境 → 项目外 `loop --version` 返回 0.1.0；旧副本入口文件仍存在。Windows 使用模板替身验证，未原生实测。当前用户环境只执行 `--check`，四个全局入口与 `.venv` 均列为待移除，保持已安装状态。


## 启动模型连接检查与配置恢复（2026-09-07）

交互启动在进入终端前，用当前模型/凭据发起一次无工具、无历史的短文本请求，连接超时上限取当前配置与 15 秒的较小值。失败或缺 Key 时进入共享 Switch setup，直接展示供应商、API类型（Chat Completions/Responses）、隐藏 Key 和模型；支持粘贴完整接口 URL 并提取基础地址。保存后重新检查，失败再次让用户配置，取消则退出；`--once`、非 TTY 和 `loop node` 跳过检查。保留已有模型档案与凭据优先级，不更改用户环境变量，不执行模型工具或仿真。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_setup test_setup_startup test_providers test_home test_terminal`。真实 PTY 使用本地 HTTP 替身验证旧 Key 401、隐藏输入新 Key、切换 Responses、连接成功进入终端及 `/exit`。首次 PTY 测试过早发送 `/exit` 超时，修正为等待输入提示符并使用回车后通过；不涉及产品退出逻辑修改。真实供应商 API、账户权限和 Windows/macOS 实机未测。


## 模型连接误报修复（2026-09-07）

用户当前选中的自定义服务、`gpt-5.6-sol`、Chat Completions 和已有保存 Key 原样复测：原失败在 TLS 握手阶段，`SSLCertVerificationError` / verify code 20（unable to get local issuer certificate），尚未进入模型鉴权。当前无同名环境 Key 覆盖。该 Python 默认 CA 文件/目录不存在，信任库计数为 0；系统 `/etc/ssl/certs/ca-certificates.crt` 含 147 个 CA。

新增仅在默认 CA 路径/信任库均缺失且无显式证书环境覆盖时加载系统 CA 的处理，覆盖模型推理和模型列表请求；不关闭验证、不改用户 Key/URL/协议/profile。连接诊断使用受控错误类型显示 HTTP 状态、TLS、DNS、超时，不打印响应正文。启动检查不再强制缩短至 15 秒，遵从原 profile 的 timeout_s。修复后同一配置实际文本连接通过，耗时 2.76 秒。

`PYTHONPATH=tests .venv/bin/python -m unittest test_model_connection test_setup test_setup_startup test_terminal test_providers`：32 项通过；覆盖 CA 回退、显式配置保护、受控错误、真实 PTY 与本地 HTTP 恢复流程。`git diff --check` 通过。已有进程须退出后重新运行 `loop` 才能加载修改。


## 默认隐藏逐轮总结与 Switch 补全（2026-09-07）

ChatAgent 继续生成并持久化逐轮总结，但不再向终端发送 `Summary` 显示事件；`/history`、历史会话预览和导出保持原有数据。`/switch ` 增加 setup/list/reload/master/expert 子命令及前缀补全。删除配置继续使用现有系统命令 `loop-switch remove NAME`，保留当前配置删除保护，本次未删除任何用户记录。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_completion test_session_resume test_session_render test_providers`，17 项全部通过，无跳过。当前环境缺少已声明的 test 依赖 pyte，使用 uv 安装 pyte 0.8.2 后完成真实 PTY 屏幕检查：中文流式期间输入草稿、无自动 Summary、空格后显示 setup、历史总结仍可预览，以及会话操作。`git diff --check` 通过；未启动仿真。重启 Loop 后生效。


## 初始 0.0.1 版本、更新与服务器发布（2026-09-07）

按用户纠正从 0.0.1 开始；0.1.0 和本轮早期 0.2.0 均为未发布候选。版本统一到 `_version.py`，pyproject 动态读取，源码/模块/安装入口共用 launcher。`loop update` 支持检查、指定稳定版本、显式源码迁移和回滚；独立更新控制器使回滚到早期程序后仍可升级。源码与托管安装共用 uv，模式/state 记录持久化。新环境验证后才原子切换 release.json，保留旧环境及 SQLite 状态备份；后台终端/服务/Agent/Node/viewer 持有进程 lease，更新互斥且不杀进程。未知状态 schema 和隐式降级拒绝。托管卸载保留用户数据和备份。

最终相关回归：`PYTHONPATH=tests LOOP_TASK_AUTOSTART=0 .venv/bin/python -m unittest test_updates test_releases test_install test_uninstall test_platform_support test_branding test_terminal test_agents test_task_supervisor test_nodes.NodeRuntimeTests -q`，64 项通过（8.035s），[日志](../artifacts/release-validation/final-regression.log)。最初组合命令误列不存在的 test_task_service / NodeTests 名称，已纠正并完成上述实际模块验证。测试发现并修复独立 viewer 入口缺少包根搜索路径；维护锁在加载场景之前拒绝启动的子进程检查通过，没有打开/重启 GUI。

完整离线传输替身＋真实 uv/进程安装：Python 3.8 shell/zipapp → 初始 0.0.1 → 独立更新控制器 → 无变更更新 → 卸载通过；[最终 bootstrap 日志](../artifacts/release-validation/bootstrap-final.log)。另在临时 HOME 安装真实 0.0.1 包，升级到仅用于测试、未发布的合成 0.0.2 wheel，回滚、再次切换、卸载均通过，用户配置/Skill/SQLite 会话保留；[升级日志](../artifacts/release-validation/e2e-0.0.1.log)。

最终公开包 `artifacts/release-0.0.1-final/`：94 个 wheel 条目、9 个公开文件；无项目私有部署文档、运行数据库或凭据文件。`scripts/publish_release.py` 本地与远端校验白名单及 SHA256SUMS，版本化文件不同内容拒绝覆盖，并在发布锁下最后切换 latest.json。使用现有 root SSH 上传到 8.134.90.171，发布地址 `https://loopmaster.box2ai.com/LoopROS`。新增该子路径静态 nginx 配置，语法检查通过后平滑重载，原网站保留。发布目录与 wheel 哈希详见 [DEPLOYMENT](DEPLOYMENT.md)。

真实 HTTPS 验收：所有清单文件匹配，隔离 HOME 运行服务器 install.sh --terminal-only、项目外 loop --version、update --check、update 无变更更新、ros --check-update、服务器 uninstall.sh 全部成功，测试 Skill 保留。[机器可读回执](../artifacts/release-validation/live-result.json)。原系统 Python、当前用户 profile/凭据和运行状态未迁移。公网已部署0.0.1，未创建 Git tag/GitHub Release、未执行 CI、未作 Windows/macOS 原生或模型/硬件验收。


## 输入框下方提示与任务面板（2026-09-07）

命令补全候选、←/→切换任务、Actions和快捷键提示统一放在输入框下分隔线之后。移除 PromptSession 的浮动候选层，保留原补全状态与按键选择；候选列表跟随选中项滚动，按窗口高度减少行数。候选和 Actions 共用下方区域，Esc 关闭候选后恢复 Actions。主屏对话仍使用原生滚动，输入随实际内容伸缩，菜单收起不留下旧渲染高度。

最终验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_interactive test_completion test_session_render test_terminal_render`，28 项通过，42.511 秒。真实 PTY/pyte 覆盖中文流式期间编辑草稿、命令候选和任务面板位于输入框下方、任务切换/取消、历史预览、6×24窄屏、窗口缩放、Actions翻页/关闭及原生滚动。测试调整了候选与历史面板共用区域的预期，等待完整 Esc 识别时间；所有最终检查无跳过。`git diff --check` 通过，未启动或重启仿真。重启 Loop 后生效。


## 介绍网页部署到发行地址（2026-09-07）

按用户要求，将现有 website 页面发布到 `https://loopmaster.box2ai.com/LoopROS/`。保留品牌和布局，修正版本为0.0.1、Windows下载命令、公开安装指南及资源相对路径。新增 build_website/publish_website，只导出六个公开文件，远端发布锁下备份旧网页并更新网页校验值。原0.0.1 wheel/manifest/bootstrap/安装卸载脚本校验确认不变。发布构建器后续复用该网页，发布白名单增加五个网页资源。

`node --check website/site.js`、`node --test tests/website.test.cjs` 通过（平台/terminal-only/复制成功及回退），不可变发布保护测试通过，导出网页本地链接核对通过。线上六个资源HTTPS内容逐一与导出产物一致。真实 Chrome 检查桌面1440×1000和手机390×844、logo、版本、平台切换、terminal-only、公开指南均通过，没有JS页面错误或手机横向溢出；截图已人工查看。Chrome初始旧headless参数不兼容，改为新headless模式后验证成功，未操作用户浏览器窗口。nginx补齐CSS/JS/PNG响应类型，检查通过后平滑重载。

产物及回执在 `artifacts/website-live-20260907/`。仅网页更新，不重新安装用户环境、不启动仿真、不上传私有项目文档。


## 任务面板返回对话（2026-09-07）

修复左右键仅在任务之间循环的问题：导航中加入对话位置，右键进入首个任务后左键返回；经过最后一个任务也可回到对话。Esc 关闭时清除选中任务和按钮状态，不取消任务；没有运行任务的提示也可用左右键关闭。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_task_navigation`（2 项通过），`PYTHONPATH=tests .venv/bin/python -m unittest test_session_render.SessionRenderTests.test_task_buttons_and_permission_profiles`（真实 PTY 通过，7.781 秒），覆盖单任务、空任务、双任务左右返回、Esc关闭、不取消任务及原有显式取消/权限操作。`git diff --check` 通过。重启 Loop 后生效。


## 并行 Agent 调度与 IPC 验证（2026-09-07）

已有 AgentRuntime 使用 multiprocessing spawn + Pipe，默认最多3个独立进程。本次补齐子进程身份、agents_status 同伴发现、broker绑定发送者、通信权限检查、有效Key快照传递、启动失败Pipe清理和完成回执回收后的槽位复用。未改为自动持久任务或硬件并行执行；宿主工具仍串行。角色执行范围沿用原配置。

最终命令：`PYTHONPATH=tests .venv/bin/python -m unittest test_agents test_agent_ipc test_providers test_harness_behavior test_user_portability`，27项通过，1.717秒。新测试用两个真实 Agent worker/ChatAgent 进程和本地HTTP服务，通过屏障验证请求同时在途，验证同伴发现、双向send_agent和结果回收；另测试冒充sender、递归spawn、取消同伴均拒绝，Master与子Agent通信使用同一权限门禁。无真实供应商调用、仿真或设备动作。

早期额外运行的 `test_control.test_approval_preserves_complex_scene_args` 在当前缺少MuJoCo的环境未通过，其 viewer.ensure_installed 报安装依赖失败，另有一项仿真相关跳过；未为本次IPC任务补装仿真或改变该测试。相关控制权限在新增App级测试单独验证。完整仿真回归不属于上述27项通过结论。`git diff --check`通过。

### 2026-09-07 bilingual website

Export with `python3 scripts/build_website.py --output artifacts/website-bilingual-20260907` into a new output directory, then publish with `scripts/publish_website.py` as documented in [website README](../website/README.md). `node --test tests/website.test.cjs` passed for English/Chinese and all five platform commands. Live Chrome and HTTPS asset checks passed; see [deployment record](DEPLOYMENT.md#bilingual-website-and-github-docs--2026-09-07). GitHub Docs were published separately in documentation-only commit `af5ac4b`; do not push the unrelated working tree as part of website updates.


### 2026-09-07 Fast 启动提示

交互启动复用普通连接检查，读取实际 service_tier；上游默认 priority/fast 时显示 active，否则最多增加一条 priority 无工具短请求，socket 超时上限 10 秒。有效文本及优先档回执显示 available (probe only)，其他结果显示 not confirmed 并继续启动。探测可能计费，不持久化档位、不改变正常对话、不启动设备。说明见 [Quick setup](QUICK_SETUP.md) 和 [检测记录](research/fast-mode.md)。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_fast_startup test_model_connection test_setup_startup test_setup test_ui test_providers test_terminal test_terminal_render.TerminalRenderTests.test_chinese_stream_queue_and_editing -q`，45 项通过；`PYTHONPATH=tests .venv/bin/python -m unittest test_stream_completion -q`，4 项通过，无跳过。本地 HTTP 覆盖两种协议、默认 Fast、探测成功、降档、缺失/异常档位和参数拒绝；替身验证超时不阻塞正常启动。真实 PTY 验证认证失败恢复后显示提示，以及 6×24、12×40、24×80 中文流式并行输入与提示可见。首次旧测试把最后一次请求视作普通连接检查，现已分别检查普通与探测的请求次数和超时。真实服务商未调用，未改用户 profile/Key；重启当前源码的 Loop 后生效。


### 2026-09-07 /resume 同步切换聊天画面

修复恢复会话只更新上下文和 Actions 提示、上方仍保留旧会话的问题。`Terminal.redraw_session` 在成功切换后清理屏幕及支持的终端滚动记录，重画目标会话完整已保存消息；`/new` 同步显示空白会话。重画走独立 session_display，不调用模型/工具、不重复追加 transcript；保留角色、粗体、用户背景、媒体占位与工具摘要，不伪造历史工具耗时或事件 ID。会话记录仍保留在数据库，队列恢复仍暂停；失败时不清除当前显示。详见 [Session memory](SESSION_MEMORY.md)。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_session_display test_interactive test_session_render.SessionRenderTests.test_resume_replaces_visible_history_and_scrollback test_tool_display -q`，22 项通过；随后补充失败恢复与事件计数断言，运行 `PYTHONPATH=tests .venv/bin/python -m unittest test_session_render.SessionRenderTests.test_resume_replaces_visible_history_and_scrollback test_session_render.SessionRenderTests.test_stream_summary_and_resume_selector test_session_resume -q`，7 项通过，无跳过。Linux 真实 PTY/pyte 覆盖 40×12、80×24 双向切换、40 行历史及旧滚动区清理、失败保留、中文流式并行草稿、/new 清空和数据库历史不重复。沿用原生滚动、不切备用全屏。`git diff --check` 通过；Windows/macOS 实机未测。重启当前源码 Loop 后生效；未操作仿真或设备。


### 2026-09-07 /task 空参数与概念区分

空参数 `/task` 与 `/tasks` 使用同一任务列表入口，尾随空格同样处理，避免把空字符串提交为 goal。`/task 具体目标` 保持提交持久任务的原行为。Session 保存对话，Task 保存独立目标和执行状态，Worker 是执行进程；没有新增“Task 即会话”或自动创建 Session 的行为。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_task_navigation test_completion test_session_render.SessionRenderTests.test_task_buttons_and_permission_profiles -q`，7 项通过（14.610 秒），包括实际 PTY 输入 `/task` 回车显示面板；应用层验证无任务新增、无服务启动、带目标仍提交 task_submit。`git diff --check` 通过。未连接 Jetson、未操作机器人；重启当前源码 Loop 后生效。

### 2026-09-07：资源自适应 Agent 并发

- `toolchain/admission.py` 新增标准库 HostMonitor／ResourceAdmission：Linux RAM／CPU（含可读取的 cgroup v2 配额）、限时 NVIDIA GPU／VRAM采样，同一 state SQLite 原子预留，按进程身份回收。每进程成本是保守估算，不是 OS 硬限制。
- 前台 AgentRuntime 资源不足进入 queued，恢复后轮询启动；已运行任务不因资源压力被取消。后台 TaskSupervisor 保留持久队列、不虚增 attempt。`/agents` 返回资源和等待原因。默认发行并发上限108，支持1..108；用户已有低上限不覆盖。配置入口和边界见 [AGENT_RUNTIME](AGENT_RUNTIME.md)。
- 已验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_resource_admission test_agents test_agent_ipc test_task_supervisor test_settings test_task_scope test_toolchain.ToolchainTests.test_pool_lru_and_active_protection test_toolchain.ToolchainTests.test_pool_loader_failure_and_release_on_exception -q`，39项通过。包含真实替身子进程排队／恢复／取消、并发准入原子性、20／108额度、GPU缺失／利用率／单卡显存、失败回收和后台尝试计数；未执行108个真实模型请求压力测试。
- 本机只读 HostMonitor 采样成功：约54176 MiB可用 RAM、24逻辑 CPU、CPU约24.5%、GPU0约16219 MiB空闲显存／0%占用，仅代表采样当时。未连接设备或主动打开仿真。
- 扩大回归包含 test_control 时共46项：1项错误、1项跳过；错误是既有 `test_approval_preserves_complex_scene_args` 进入 viewer.ensure_installed 后报告托管环境 MuJoCo 安装失败。未为此继续安装或重启仿真。相关资源回归随后39项全通过；`git diff --check`通过。
- 本轮修改源码与发行默认值，未覆盖个人配置、未发布版本或重启正在运行的 Loop；下次启动源码入口加载新调度。

### 2026-09-07：单 CLI 的本地／SSH 进程节点

- 新增 process Node：用户 profile 与哈希指定 argv/cwd/env_names/stop_argv，独立 PTY、行输入、输出尾部和本地进程组回收；`/node profiles`、`/node start process NAME PROFILE`、`/node send` 无模型轮询。现有 NodeRuntime 持有进程，切换 Session 不停止；CLI 退出回收，不提供系统守护或跨 CLI attach。用法见 [PROCESS_NODES](PROCESS_NODES.md)。
- 本机 `~/.loop/processes/` 新建七个 0600 配置：jetson-robot、jetson-host、workstation-act、openpi-install、openpi-policy、jetson-agent-client、loopmaster-chat。保存用户提供的路径与命令；无明文凭据，无自动执行。ACT 目录存在；`/media/boxjod/File/LoopMaster/loopmaster_openpi_pi05` 在本次检查时不存在，相关三个配置须先修正路径。远端 Jetson 的目录与服务未验证；本机凭据环境不会自动转发 SSH。
- 验证命令：`PYTHONPATH=tests .venv/bin/python -m unittest test_process_nodes test_process_terminal test_nodes.NodeRuntimeTests test_nodes.NodeAppTests.test_queued_master_input_is_not_retargeted_on_focus_switch test_coding_agent test_completion -q`，28 项通过（8.924 秒）。含真实本地并行子进程、中文输入与隔离、环境脱敏、退出回收、停止脚本、配置哈希、权限拒绝与撤销、真实 PTY 新 Session 后继续操作；测试 fixture 禁止调用模型。
- 更早扩大运行 test_nodes 时有 2 项 MuJoCo 相关测试超时；当前 `.venv` 导入 mujoco 报 ModuleNotFoundError。未安装依赖或启动仿真来绕过。上述相关回归全部通过；未执行用户提供的安装、SSH 启动、模型推理或真机运动命令，尚无真实工作流端到端成功证据。


### 2026-09-07 终端窗口缩放与输入区保护

复现：多行中文草稿在终端缩到 3 行时被上下分隔线和底部提示完全挤出，原始文字仍在但屏幕不可编辑定位。修复为 Terminal.display_budget 统一分配输入、预览和面板高度；输入优先，3/2/1 行逐级隐藏下分隔线、上分隔线和底栏，放大恢复。队列与流式预览只隐藏显示，不清空数据。面板标题和队列省略号使用显示列宽，中文宽字符不越界；超窄面板以单列占位避免双宽字符撑破布局。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_resize_render test_terminal_render test_interactive test_steering_render -q`，26 项通过（47.925 秒），无跳过。新 PTY 测试从 1–40 行、12–140 列反复缩放，涵盖中文/emoji/组合字符、多行草稿、光标中间插入、队列、Actions、slash 候选、流式并行输入；既有 PTY 验证包含 6×24、12×40、24×80 窗口与原生滚动。宽字符标题使用独立显示列宽断言。`git diff --check` 通过。没有收到用户所述截图，结论限于本次可复现问题；Linux PTY 已测，其他终端模拟器及 Windows/macOS 实机未测。未重启 Loop/仿真或连接设备，重启当前源码 Loop 后加载修改。

### 2026-09-07：资源管理下沉为共享基础设施

预算、按工作负载申请、SQLite租约和释放迁入 `core/resources.py`；主机遥测适配器保留 `toolchain/admission.py`。`App.resources` 注入 Agent／TaskSupervisor／NodeRuntime／PolicyServices；run_python 执行段申请，ModelPool 支持相同共享管理器。默认工具 `resource_status` 遵从权限门禁并显示分类预留；旧构造入口和账本兼容。详见 [RESOURCE_RUNTIME](RESOURCE_RUNTIME.md)，其中明确估算成本与本地／远端覆盖边界。

验证命令：`PYTHONPATH=tests .venv/bin/python -m unittest test_resource_foundation test_resource_admission test_agents test_agent_ipc test_task_supervisor test_settings test_python_runner test_nodes.NodeRuntimeTests test_terminal.TerminalTests.test_owned_policy_process_lifecycle test_toolchain.ToolchainTests -q`，50项通过（11.321秒）。真实子进程均为本地测试替身，未运行模型权重、付费API、真机或MuJoCo窗口。`git diff --check`通过。未覆盖个人配置、发布或重启运行中的Loop。


### 2026-09-07：Slash 首页、当前服务模型菜单与 Fast

- 首页前五项为 model、mode、permissions、resume、help；history 隐藏于裸 slash 列表但保留显式兼容。model 使用现有 URL／凭据查询目录，在输入框下方选择；mode 提供 sim／real／plan，不自动启动设备。
- 新增 `/fast [on|off|status]`，当前客户端后续前台请求使用 priority／default，记录非流式与流式实际档位；不持久化、不自动探测或重放。未请求真实用户模型服务。
- 普通文本不触发 slash 补全；清除残留候选时保留草稿，Enter 校验候选仍属于当前补全状态。真实 PTY 覆盖单个汉字、中文数字草稿与流式并行输入；未取得用户具体终端／输入法信息，不能据此声称桌面输入法数字选字问题已完整复现或解决。
- 验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_slash_workflow test_slash_terminal test_fast_startup test_completion test_interactive -q`，29 项通过（14.776 秒）。回归中发现并修正候选校验对 resume 选择的影响；最终会话恢复测试通过。没有连接机器人、启动仿真或更改用户凭据；当前源码重启后加载。


### 2026-09-07：厂商 Agent CLI 参考仓库

- 工作目录：项目根；目标为 `reference/Agentic/`。对缺失目录执行 `git clone https://github.com/<组织>/<仓库>.git reference/Agentic/<仓库>`，补齐 Gemini CLI、Qwen Code、Kimi CLI、Mistral Vibe；现有 Codex 和 Claude Code 复用原版本。
- 六个仓库均通过 origin、HEAD、本地许可证、工作区状态及 `git fsck --connectivity-only` 检查；均非浅克隆。版本与来源见 [本地清单](../reference/Agentic/README.md)。
- 仅下载与验证源码，未安装或运行第三方项目。`reference/` 沿用已有 Git 忽略规则；未修改第三方源码。

## 2026-09-07：独立仿真工作台、Isaac MCP 与多相机数据验收

目录 `/home/boxjod/Workspace/LoopROS`。实现入口与复现命令见 [SIMULATION_WORKBENCH](SIMULATION_WORKBENCH.md)。已用 uv 在项目 .venv 安装可选 MuJoCo/numpy/h5py/Gymnasium/MCP 依赖；Isaac 使用 `/home/boxjod/isaacsim/python.sh`，本机版本 4.5.0，不改全局模型配置。

- `MUJOCO_GL=egl PYTHONPATH=tests .venv/bin/python -m unittest test_simulation_workbench test_skills test_coding_agent test_harness_behavior test_composition test_user_portability -q`：53 tests passed。覆盖真实 MuJoCo 渲染与深度、相机随动、动作对齐、取消后不完整数据、seed 不匹配、动作预检、任务终止、Gym、实际 MCP stdio／launcher、权限和 TCP 主线程执行。
- `scripts/validate_simulation_workbench.py` 的最终 MuJoCo 证据：[validation.json](../artifacts/simulation-workbench/mujoco-final/validation.json)；Isaac 证据：[validation.json](../artifacts/simulation-workbench/isaac-local-stage/validation.json)。均产生双相机 RGB／深度／分割、内外参和实际 HDF5。Isaac 基座 z=0.1000000015 m，关节从 0 到 0.1659903675 rad；头部相机不动、腕部相机随动，分割含 `/World/arm` 和 `/World/cube`。
- 最终 Isaac 验收修复了 importer USD 缺 defaultPrim、暂停时空帧、box extent 重复缩放和 reset 丢基座位置。原默认地面包含外部资产引用，观察到 World.reset 内 app.update 卡住；改本地程序化地面后最终脚本通过，尚不据单次通过保证任意外部资产加载稳定。之前失败的输出保留，不作为成功证据。
- 三套项目 Skills 通过 skill-creator quick_validate，已安装于 `~/.loop/skills/` 并逐字节核对；`~/.loop/processes/isaac-simulation.json` 已创建，节点启动命令详见工作台文档。节点 profile 本轮未通过 UI 启动，等价 host 命令已真实验证。验收专用 host 在结束时停止，未重启用户既有 GUI。
- 本地 `uv build --wheel --out-dir /tmp/loopros-simulation-wheel` 成功；检查新模块、Skills、URDF、MCP 模板均在 wheel 中，并从临时解包目录验证安装包 launcher 的 `mcp --help`。该 wheel 仅为本地检查，非发布版本。

边界：测试任务只检查 cube 存在，不代表抓取／强化学习收敛／ACT 模型准确率。Gym 检查提示动作未归一化、qpos 空间无限界，保留真实物理单位；训练器需要自己的归一化。未运行全量回归；本轮额外试跑现有 test_control 时，`/commands` 数量断言期望 45、实际 46，未修改这个与新增仿真工具无关的 slash 数量断言。


### 2026-09-07：参考厂商 CLI 的上下文与并发能力补齐

- 上下文按完整组最多32条／12000字符等价预算选择，旧用户请求摘录不超过2000字符；/compact 无损缩窗，/compact reset 恢复默认。工具输出显式 JSON 截断，累计工具正文48000字符预算。完整历史及原工具回执保留。
- skill_read 支持包内资源路径和行分页，读取权限与自动目录注入一致；默认 Reader 提供只读文件能力。UI broker 轮询移到单监管线程，进程 IPC 每轮公平限量、畸形消息局部失败，观察回调错误保留原始回执。
- 工作目录：项目根。`LOOP_TASK_AUTOSTART=0 PYTHONPATH=tests .venv/bin/python -m unittest test_context_window test_control test_skills test_agents test_agent_ipc test_session_resume test_steering test_coding_agent test_slash_terminal test_interactive test_steering_render -q`：78项通过（20.896秒）。期间发现旧命令数量断言与已有 /fast 不符，改为核对清单一致性；PTY断言按实际渲染的 stored messages 标签验证。
- 随后补齐 Skill 目录预算测试，test_skills 的12项通过；最终 `LOOP_TASK_AUTOSTART=0 PYTHONPATH=tests .venv/bin/python -m unittest test_agents test_agent_ipc test_skills -q`：24项通过（1.930秒），包含退出后积压消息排空、非法 type、实际进程、多线程提交与权限边界。上述测试集合有重叠，不累加为唯一用例数。
- PTY 以延迟监管替身验证 /context、/compact、/compact reset、中文流式期间追加草稿与命令菜单；未请求付费模型、设备或仿真。没有安装参考仓库依赖或修改第三方源码。重启 Loop 终端加载源码；用户已有 agents.json 继续整体覆盖默认角色。
- 设计证据、使用入口和限制见 [源码对照报告](research/agent-cli-capability-upgrade.md)。


### 2026-09-07：连续窗口缩放横线残留

- `terminal/interactive.py` 在每帧渲染期间固定终端尺寸读数，布局和分隔线使用同一快照，结束后恢复实时尺寸；分隔线右侧留一列空白，避开满宽自动换行边界。不清屏或清空滚动历史。
- 新增 `test_resize_terminal`，真实 PTY 连续 15 次宽度变化（30–120 列），检查稳定帧只有上下两条横线、宽度一致、中文草稿保留；等待 CPR 后重绘，避免把临时擦除帧误判为最终结果。同步更新既有横线边界断言。
- 验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_resize_terminal test_terminal_render test_slash_terminal -q`，7 项通过（36.734 秒），包含中文流式并行输入、紧凑窗口、菜单和连续缩放。`git diff --check` 通过。未启动真实模型服务或机器人；不同桌面终端的重排行为仍以实际运行结果为准。


### 2026-09-07：CLI 与多 Agent 操作闭环

- 新增标题/角色/稳定@编号展示，/agents active/all筛选与动态Actions面板；角色和收件人补全后继续输入任务/消息；/agent-messages展示queued/delivered/not_delivered入站回执；子Agent可读取已知同伴结果。内部ID继续兼容。
- /agents、/send、/result、/stop-agent全部转经App.tool权限，消息查看同样受控；发送保留原文空格及引号。Agent命令放后台线程并允许前台回合执行中提交独立子Agent，遵守既有资源和权限。完成通知按标题显示。
- 项目根运行 `LOOP_TASK_AUTOSTART=0 PYTHONPATH=tests .venv/bin/python -m unittest test_agent_terminal test_agent_interaction test_agents test_agent_ipc test_completion test_slash_terminal test_interactive -q`：40项通过（22.391秒）。含实际spawn进程、CLI角色/目标选择、消息投递与结果查看、中文流式并行输入PTY、deny/plan与取消门禁。
- 之后补充同伴结果拒绝权限及缓存等待原因，运行 `LOOP_TASK_AUTOSTART=0 PYTHONPATH=tests .venv/bin/python -m unittest test_agent_ipc test_agents test_resource_admission -q`：24项通过（2.901秒）。测试有重叠，不累加唯一用例数量。diff空白检查和调研本地链接通过。
- 模型使用本地替身；未调用真实供应商、真机或仿真。运行时消息回执与短编号不持久化，投递不代表模型处理或验收成功。源码与角色默认值重启Loop后加载。完成范围见 [能力对照](research/agent-cli-capability-upgrade.md)。


### 2026-09-07：真实终端重排修正与代码块渲染

- 核实本机 `~/.local/bin/loop` 指向项目 `.venv/bin/loop`，安装元数据为 editable，`loop_robot.terminal.interactive` 直接来自项目源码。当时运行的 Loop 启动晚于上一版修复，因此不能把用户反馈归因于未安装。当前新修改需重启进程，不需要重装，未强制结束用户会话。
- 使用临时安装的 `@xterm/headless` 6.0.0 重现缩到 80 列出现第三条横线；原 pyte resize 只裁剪列，未覆盖此行为。保存游标方案也未通过，已删除。最终在擦除前根据旧 UI 各行重排新增的行数修正相对游标，并覆盖未及时处理 SIGWINCH 的尺寸变化；保留每帧尺寸快照。测试同时检查历史未被清除、多行中文草稿保留。外置测试依赖不进入发行依赖。
- 验证：`XTERM_HEADLESS_MODULE=/tmp/loop-resize-xterm/node_modules/@xterm/headless PYTHONPATH=tests .venv/bin/python -m unittest test_markdown_code test_resize_reflow.ResizeReflowTests test_resize_terminal test_terminal_render test_slash_terminal test_session_display -q`，12 项通过（51.270 秒）。缩放测试在变更模拟终端与 PTY 尺寸时短暂停住测试子进程，避免两个测试端尺寸不一致造成假失败。
- 回复和历史回放新增标准三反引号代码块：语言标签、独立背景、原始缩进、代码内字面星号；支持跨流式片段。没有执行审批或机器人命令。新增代码背景 PTY 断言后修正 ANSI 色号与预览色差，最终 `PYTHONPATH=tests .venv/bin/python -m unittest test_markdown_code test_slash_terminal -q`，3 项通过（6.508 秒）。`git diff --check` 通过。


### 2026-09-07：权限切换审批被监督器拦截且 ID 丢失

- 根因：settings_update 对所有目标统一要求 supervisor 停止；PermissionGate.approve 在执行前 pop 请求，前置检查失败后 ID 已丢失。permissions 改为与直接 /mode、/permissions 一致的即时操作，其他配置保留 idle 检查。
- 新增 ApprovalPreconditionError 仅标识明确的执行前阻塞，保留该请求及原因；成功消费一次，执行中拒绝重复审批／拒绝操作；未知执行异常仍消费，避免重放有副作用的操作。无效 ID 给出可读 /requests 指引。未恢复用户旧 ID，未修改运行中权限、启动 Host 或操作电机。
- 验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_settings test_control.ControlTests.test_ask_approve_exactly_once test_control.ControlTests.test_approval_does_not_override_deny -q`，12 项通过（0.356 秒）。覆盖监督器在线时 real 切换、driver_required 状态、未打开仿真、前置阻塞无落盘／同 ID 再审批成功、重复审批与未知副作用禁止重放、deny 优先。`git diff --check` 通过。

### 2026-09-07：离线执行型 Skills

新增 `terminal/offline_skills.py` 与 `toolchain/offline_skill.py`：`/skills` 列表、按标题 inspect/run/status/logs/stop、`save PROFILE NAME TITLE` 导出当前主机 Bash／批处理；默认模型工具包含 skill_executables／skill_export／skill_run。执行复用 process Node、原权限和资源基础层，不调用聊天模型；读取普通Skill不执行。哈希覆盖包内脚本，子进程重检并复制私有快照，源包删除后仍可按原标题停止。旧前台定时器不能通过新增入口间接启动Node。

已从本机既有用户配置导出 `~/.loop/skills/{start-jetson-host,start-robot,start-act-inference,start-openpi-inference}`；没有覆盖已有包、没有把个人命令或凭据写进项目。四包均通过 `/home/boxjod/.codex/skills/.system/skill-creator/scripts/quick_validate.py` 和 `bash -n`（含存在的停止脚本）。本轮未运行这些真实启动脚本，源配置不被标记成已验收成功。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_offline_skills test_offline_skill_terminal test_process_nodes test_process_terminal test_skills test_completion test_resource_foundation -q`，33项通过（11.419秒）。覆盖真实Bash、字面参数、哈希失效、路径逃逸、重复启动、无API调用、审批闭环、包删除后快照停止、中文输入输出PTY和原进程功能。Windows平台入口校验通过，Windows进程／批处理端到端未实测。新文档本地链接与 `git diff --check` 通过。

使用与覆盖边界见 [OFFLINE_SKILLS](OFFLINE_SKILLS.md)。源码下次启动加载新命令；本轮未发布版本或重启Loop、机器人、模型服务。

## 2026-09-07：website 可视化仿真工作台

新增 `website/workbench.html`、`workbench.css`、`workbench.js` 与本地 `terminal/web_workbench.py`，入口 `loop web`。默认 `http://127.0.0.1:8768/workbench.html`，支持 `--state-dir`、`--port`、`--isaac-config`；启动网页服务本身不创建仿真。两个语言首页增加工作台链接，静态导出／发布白名单从 7 项扩为 12 项；本轮未执行公网发布。

验证：

- `MUJOCO_GL=egl PYTHONPATH=tests .venv/bin/python -m unittest test_web_workbench test_simulation_workbench -q`：13 tests passed。包含真实 HTTP、MuJoCo 几何与 PNG、plan、跨站和 Host 拦截、一次审批、文件路径限制、HDF5 下载；无执行器场景的零维 action HDF5 边界已修复并验证。HDF5 改为按帧分块并使用 LZF 压缩，避免默认自动分块给单帧图像分配大量未使用存储。
- `node --test tests/website.test.cjs`：原双语安装交互 2 tests passed；新 JS 语法检查通过。
- `.venv/bin/python tests/validate_website_workbench.py` 使用 Playwright + `/usr/bin/google-chrome`，启动隔离临时状态的本地服务，创建 10 个组成部件的房间，添加／移动 cube，创建相机并读取实际 PNG，设置任务、页面审批并下载 HDF5，检查 390px 手机无横向溢出。测试进程退出时回收自己的仿真服务。结果：[browser-result.json](../artifacts/website-workbench/browser-result.json)，[桌面](../artifacts/website-workbench/desktop.png)、[相机](../artifacts/website-workbench/camera.png)、[手机](../artifacts/website-workbench/mobile.png)。浏览器测试需额外安装 playwright；本机已在 .venv 安装，仅为开发验证。
- `scripts/build_website.py --output /tmp/loop-web-export-visual` 导出成功，导出和发布白名单一致；不包含 example.html、Python API 或数据集。本地 wheel 构建用于检查新入口和静态资源，不作发布包。

边界：此页面右侧为操作面板与回执记录，未接入 AI 聊天。MuJoCo 显示实际几何与姿态但不复制纹理；Isaac 为标注的包围盒布局，真实画面需相机快照。网页 Isaac 操作路径复用已验证工具桥，本轮浏览器端到端只使用 MuJoCo。静态公网页面只能预览及给出本地启动说明，不自动探测或控制本机仿真。预设依次执行，失败保留已完成状态且不自动重放。

本轮验收结束后，隔离测试服务已停止；保留 `http://127.0.0.1:8768/workbench.html` 本地预览服务，使用正常用户 state directory 和已有权限规则，没有自动创建仿真或修改权限。


### 2026-09-07：用户内容与未审核工具排除

- 用户要求：用户产生的Skills、用户工具和未审核通用工具不作为本项目push或上传内容。已在AGENTS、USER_HOME与GITHUB_RELEASE明确，并补齐.gitignore。三个维护型仿真SKILL.md模板使用明确发行清单；用户生成包不进入configs默认值。
- 对21个此前新加入暂存区的候选/设备脚本文件执行git rm --cached，全部保留本地文件。未改动其余已有暂存内容。根目录共21个临时Python脚本、scripts/inspect_jetson_ssh.py以及network_discovery候选整包均排除。工具名单保存在被忽略的本地 toolchain/candidates/README.md，不上传脚本内容。
- 发行构建从Git已跟踪且未被忽略的工作文件生成临时源码副本，再构建wheel，防止根目录临时.py被打包；仍沿用标准库，无新增依赖。
- 验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_public_source test_releases -q`，5项通过。实际源码副本289个文件，仅含三个维护模板，不含候选、用户目录或设备临时脚本；`git ls-files -ci --exclude-standard`为空。未运行设备脚本、构建新wheel或执行任何push/发布。既有历史发布内容本轮未远程审计或重写。


### 2026-09-07：底部 Task 数量

状态栏新增 `tasks N`，统计当前 Session 未完成持久任务，包含 waiting／retry／queued／running，排除 succeeded／cancelled 与其他 Session；与提示队列 queued 分开。启动、会话切换及既有每秒轮询刷新缓存，用 SQL COUNT 避免每帧加载任务详情。
验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_task_navigation test_slash_terminal -q`，5 项通过（7.041 秒），包括统计范围／终态过滤及真实 PTY 底栏显示。`git diff --check` 通过；未启动后台任务或机器人。


### 2026-09-07：network_discovery 审核通过

- 用户明确批准 network_discovery。将源码提升为 toolchain/network_discovery.py，专项测试移至 tests/test_network_discovery.py，使用说明移至 docs/NETWORK_DISCOVERY.md，更新项目地图和本地待审清单。
- 实现字节保持不变，SHA256 为 3047e877b8dd94b657f9e09315de2c37435b0422ab176758ef7a52e9efa6f930。`PYTHONPATH=tests .venv/bin/python -m unittest test_network_discovery -q`：3项通过，覆盖导入无命令、只读参数与环境字段、命令缺失/超时/非零退出。
- 新正式源码、测试与说明加入暂存范围，并核对发行源码副本包含该模块；其余用户包与未审脚本继续排除。当前正式通用待审候选为0，设备专项临时脚本仍未获发布审核。模块尚未注册模型工具，本轮未运行网络采集、push或发布。

## 2026-09-07：输入框粘贴与媒体折叠标签

新增 `terminal/composer.py`，接入 Terminal 的 bracketed paste、退格、输入处理器、附件和 Session 草稿存储。多行粘贴保留全文，在输入框显示 `[Paste #N · 行数 lines]`；图片／视频分别显示 `[Image #N]`／`[Video #N]`。第一次退格选中、第二次退格删除整个标签；普通文本逐字符删除。删除媒体标签同步移除待发附件，不删除源文件。

发送和排队使用展开文字，媒体携带对应编号说明；队列编辑、失败恢复、退出恢复保留数据关联。新增只在输入开头的粘贴块按普通内容处理，避免粘贴代码被识别为 slash 命令。历史保留展开文字，Ctrl-C 清空标签与附件；已提交的块和已清空内容不持续保留在内部标签表中。

验证：`test_composer` 5 项；`test_interactive` 原 18 项；`test_session_resume`、原操作面板 PTY 及 `test_composer_render` 合计另外 7 项均通过。新增 `test_interactive.InteractionTests.test_folded_code_submission_and_failed_submission_restore` 单独通过，检查缩进／换行、粘贴 slash 不执行以及超长提交失败恢复。共 31 项相关检查。初次新增用例未初始化 fixture 的 aliases，修正测试初始化后该用例通过；不是产品执行失败。

真实 PTY 使用 `tests/fixtures/stream_terminal.py` 的离线中文流式模型替身，覆盖流式期间粘贴 20 行、两次退格、多图编号与删除、100→40 列缩放、保存后真实进程重启恢复。[屏幕记录](../artifacts/composer-chips/pty-screens.json)。图片使用测试生成的小文件，不读取用户系统剪贴板、不调用外部模型、不启动仿真。普通手动多行输入和输入框下方 Actions 面板保留原行为。


### 2026-09-07：后台自动调试、验收补全与 OpenPI 路径

- 发行任务策略增加手动 Task 的文件检查、带备份编辑、Python 检查/哈希执行和 Node 工具。去除手动 worker 的 run_python/python_check 硬禁；定时/触发任务仍禁止这些执行与修改工具。仍检查既有 PermissionGate，不自动将 ask/deny 改成 allow。后台服务持续检查其拥有 Node 的权限，不关闭前台仿真窗口。
- task_feedback 可提出缺失的 checks，格式和工具范围通过后持久化并以实际回执验收，不能覆盖已有条件。缺授权的验收反馈列出 missing_tools，避免相同失败重复提交任务。规则要求在授权范围持续修复、检查现存服务、防止重复客户端，运动必须关联新鲜关节反馈。
- 验证：task_supervisor/settings/task_scope 共23项通过（6.875秒）；新增实际子进程自动修改与备份测试2项通过（1.834秒）。最终 task_supervisor + task_autonomy 共11项通过（8.103秒），包括第一轮实际 stdout=0失败，第二轮自动 edit_file 生成备份、语法检查、哈希执行 stdout=1 后成功；不能放宽已有验收，定时任务不能获得任意执行。另跑进程权限回收与自动调试回归。没有调用真实模型、SSH或机器人驱动。
- 本机 ~/.loop/processes/openpi-policy.json 的旧路径修正为 /media/boxjod/File/LoopMaster/loopmaster_robot/openpi_pi05，确认 scripts/serve_rtc_policy.py 和 checkpoints/pi05_block2_lora/block2_lora_80k/14000 均存在；备份 ~/.loop/processes/backups/openpi-policy-1788781278828157487.json，均0600，配置解析通过。没有启动服务。
- 实机安全尚未交付：未得到每关节力矩阈值/单位/标定与机器人本地停止接口，未实现或验证力矩超限自动停机。提示词规则不等于硬件保护，不能据本轮软件回归宣称机械臂可自主安全运动。现有运行监督器未重启，等待任务未自动恢复；下次监督器启动加载策略。检查了当前项目 STATE 与 ~/.loop 下的任务策略覆盖路径，本次未发现覆盖文件。

### 2026-09-07：终端语义配色、Python高亮和修改摘要

新增 terminal/colors.py 统一工具名／参数／状态／助手标记颜色；terminal/markdown.py 使用标准库 tokenize 为Python围栏代码上色，支持diff增删颜色和流式预览。文件修改回执提供实际增删行数，ToolDisplay与历史回放显示有界diff摘要，控制字符转为可见文本；原始日志保留数据。终端字体仍由用户终端设置。

验证命令：`PYTHONPATH=tests .venv/bin/python -m unittest test_color_output test_color_terminal test_markdown_code test_session_display test_coding_agent test_session_render -q`，26项通过（38.984秒）。真实PTY展示不少于六种前景色，运行实际临时文件修改、Python流式中文输出并同时输入中文草稿；历史重绘、脚本控制字符、包裹代码和回执统计均检查。先前更广的test_terminal_render运行未出现渲染错误，当时唯一失败是旧历史测试按原始ANSI字符串检查角色前缀，已改为保留文字语义检查并单独验证加粗。定点 `git diff --check` 通过。未启动仿真、设备或付费模型请求。

### 2026-09-07：会话Token统计与容量驱动自动压缩

- `terminal/token_budget.py` 统一usage归一化、按编码请求预算、整组压缩和状态栏展示；Chat Completions读取finish_reason之后的usage尾包，Responses读取input/output usage。已完成响应在usage尾包超时/断连时保留正文并标记缺报，不重放请求。编码时不外发内部usage/流式标记。
- profile增加可选窗口容量、输出预留、压缩阈值、图片预算和stream_usage；每次模型请求前读取当前配置。未知容量只显示未知并沿用本地整理，不能按猜测硬拦截现有工具定义。显式容量扣除输出预留后默认80%开始整理；当前输入/纠正、系统状态和最近工具组保留，仍超预算则明确返回减载提示。
- 终端显示前台会话累计Token及最新上下文量，`~`估算、`?`未知、`+`缺报。usage、窗口偏好和预算报告随checkpoint保存与resume恢复；新会话独立统计。未汇总子Agent/后台Task与账户账单，未追溯老会话成本。`/compact`是确定性摘录，不额外调用模型，不保证无损语义记忆。
- 初次集成发现未知容量的保守阈值会误挡较大的工具schema，并挤掉短历史；已改为按固定请求开销保留本地余量，增加回归。PTY发现压缩回执在窄行中拆开关键词，已将“Full session history preserved”放在回执开头。
- 验证：`LOOP_TASK_AUTOSTART=0 PYTHONPATH=tests .venv/bin/python -m unittest test_token_budget test_context_window test_stream_completion test_session_resume test_providers test_settings test_control test_coding_agent test_slash_terminal -q` 61项通过；随后新增实际/估算显示和未知容量回归，`test_token_budget test_stream_completion test_model_connection test_setup test_slash_terminal` 31项通过（7.174秒）；最后增加尾包超时保护，`test_token_budget test_stream_completion` 14项通过。测试批次有重叠；真实PTY验证中文流式期间输入与状态栏，协议检查使用本地桩，没有付费模型、真机或仿真启动。窗口配置方式及能力边界见 [Session Memory](SESSION_MEMORY.md)。


### 2026-09-07：自动调试预算与确定性报告

- 修复重新规划丢失停滞计数的问题；默认最多 8 次 Worker 尝试、1 次重新规划。无新证据或预算耗尽时等待，轮询不继续消耗模型；明确 resume 才开启新预算周期，累计尝试记录保留。
- 成功、取消和等待自动生成状态目录 task-reports/ID.md，状态查询返回 report_path。报告由程序汇总验收结果和账本入口，不复制任意工具输出、不额外请求模型。
- 验证：`LOOP_TASK_AUTOSTART=0 .venv/bin/python -m unittest tests.test_task_supervisor tests.test_task_autonomy tests.test_task_scope tests.test_settings -q`，28 项通过；涵盖真实子进程代码修复、停滞跨规划、模型调用前故障预算、等待不重试、恢复预算、报告权限和验收证据。
- 本次没有重启正在使用的监督器、连接设备或执行真机动作。运行中的进程需重新加载源码及策略；物理力矩保护仍需单独硬件验收。


### 2026-09-07：三次重新规划与系统 token 方案

- 依据用户要求，默认 max_replans 从 1 改为 3，max_attempts 从 8 改为 9，使三次重新规划各有一次执行验证机会；保留显式用户配置。
- 重新规划可在原来源授权内使用 read_file/search_files/web_search/web_fetch；定时来源单独使用 TaskScheduledReplanner，不能继承手动工具授权。根据具体缺口检索，不强制每轮联网。
- 验证：`LOOP_TASK_AUTOSTART=0 .venv/bin/python -m unittest tests.test_task_supervisor tests.test_task_autonomy tests.test_token_budget tests.test_task_scope -q`，30 项通过，无用户模型费用、无设备操作。
- [全系统 token 方案](research/token-accounting-and-efficiency.md) 核查当前前台统计、后台汇总缺口、请求级计量与费用公式、缓存读写、预算预留、三层记忆、搜索与 Node 分工，区分现有能力、已修改内容和待实现设计。没有重启运行中的监督器或宣称整个全局计费系统已上线。


### 2026-09-07：用途模型分层与渐进检索设计

核查 titles.py 的首末请求本地标题、agents/config 的单 llm 入口及 files.py 的行分页接口。在 [Token 方案](research/token-accounting-and-efficiency.md) 补充用途路由、轻量异步标题、强模型故障分析和名称→索引→片段检索。默认 workflow harness 增加渐进检索规则。没有将多角色描述为已上线多模型，也没有调用用户模型生成标题；用户自定义配置保持不变。

验证：unittest discover -s tests -p test_workflow_harness.py -q，6 项通过；报告本地链接与 diff 空白检查通过。首次按模块调用因测试辅助模块导入路径失败，改用项目测试发现入口后通过。


### 2026-09-07：启动请求不因分段工具预算提前交回用户

前台增加有界续接：每段 24 个工具轮次，最多续接两段；仅近期有未重复有效回执且没有权限/停止阻碍时继续，保留同轮历史与失败去重。后台不叠加续接。默认 harness 明确启动需执行入口并验收，PAUSED/SHADOW 本身不构成启动阻碍；接管和运动按原授权及保护条件处理。

验证：test_tool_continuation＋test_token_budget 共 16 项通过；unittest discover 的 test_workflow_harness 共 6 项通过。模拟检查→启动→验证跨段完成，停滞、权限/安全停止及取消不会额外续接。此前 task_supervisor 回归也通过。本轮未连接或启动 Jetson；运行中的 CLI 需重启加载源码，未强制中断用户进程。


### 2026-09-07：启动快捷复用与纠偏记忆

- 新增 skill_executables(name) 定向检查；手动 Task 默认开放技能检查/执行，定时任务禁止 skill_run。复用已检查哈希，包改变拒绝执行；外部/远端依赖版本不在包哈希保证内。
- 用户明确的“机器人启动默认独立 Task、短句沿用、失败或变更才针对性排查”偏好保存到 ~/.loop/harness/robot-startup-preference.md（0600）；已核对总 harness 未超当前容量。默认工作流与 Worker 提示同步加入快捷复用约定。
- 本地纠正/不满信号作为相关优先记忆，不作为成功、权限或人格结论；沉默不计验收成功。
- 验证：test_offline_skills、test_memory_layers、test_task_supervisor、test_task_autonomy 共 30 项通过。新测试最初把 /skills save 的名称参数写错，修正为显式 skill_export 后重新通过。未调用用户模型、未启动机器人。CLI/监督器现有进程需重新加载代码与策略。

### 2026-09-07 工具组折叠与重复读取反馈

连续工具调用汇总、底部点击和 `/tools [GROUP]` 展开、每次调用开始时间／耗时／本地文本 token 粗估、持久化 `/details` 元数据。只复用同输入内未变化的本地读取和 Python 检查，模型上下文引用已有正文；脚本与远程状态继续真实执行。组编号限当前视图，恢复历史暂保持原渲染。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_tool_groups test_tool_groups_terminal test_color_output test_color_terminal test_markdown_code test_coding_agent test_workflow_harness test_session_display -q`，34 项通过（9.031 秒）。包含真实 PTY 鼠标展开、六次调用折叠、中文并行草稿、颜色和代码预览；文件修改失效、权限重查、上下文引用及数据库重开保留指标。不使用真实模型接口、SSH 或设备；Windows/macOS 原生终端未测。


### 2026-09-07：Jetson 项目内快捷上下文

已免密 SSH 连接 jetson@192.168.1.19，主机名 yahboom；在 `/home/jetson/loopmaster/hei-rebot-lift/software/lerobot-hei-rebot-lift/.loopros/` 新建 context.json、check_context.py、README.md，目录 0700、文件 0600。新建前检查已有文件，拒绝覆盖；没有存储凭据或启动服务。

context.json 记录项目、已核实连接、robot-service/independent-host 入口以及启动脚本、两个 runner 和 pyproject.toml 的 sha256。入口只验证存在，last_verified_startup=null。检查脚本源码位于 [remote_context_check.py](../scripts/remote_context_check.py)。下次从远端项目根运行 `python3 .loopros/check_context.py`，返回变更列表及入口；身份/指纹不匹配退出 2，不自动刷新基线、不执行入口。

真实远端校验返回 identity_matches=true、tracked_files_match=true、changed=[]；current_readiness=not_checked。本地 test_remote_context 覆盖一致、内容变更、缺失、越界路径及无启动成功声明，通过。选定文件之外的依赖和实时状态尚未覆盖，已知代码变更需要扩充受影响检查后再更新记录。本地 ~/.loop/harness/robot-startup-preference.md 已备份后追加远端入口，后续读取无需遍历项目。


### 2026-09-07：重复读取空转与 reasoning 选择

- 原引用复用只检查回执 ID，压缩后可能只剩 ID 没正文。现在比对正文、版本及分页，旧内容不可用则重发当前缓存回执；缓存命中不算新进展，相同 Python 输出派生报告不算新证据。
- 只读/检查空转两轮提示换方法，六轮仍重复则无工具收尾，记录 repeated_without_new_evidence。保留当前前台 max_tool_rounds=None，不对正常执行引入固定轮数上限；现有无限执行与取消测试通过。
- 增加 `/reasoning` 查询/补全/保存当前 profile，支持 default/none/minimal/low/medium/high/xhigh/max。Chat 编码 reasoning_effort，Responses 编码 reasoning.effort；未配置不发送。模型支持能力与配置请求值区分，未收费探测、未修改用户当前模型设置。
- 验证：read_loop_reasoning、tool_groups、tool_continuation、token_budget、slash_terminal 首组 27 项通过；补充正文恢复集成测试后，read_loop_reasoning、settings、control 共 24 项通过。PTY 包含 high 选择和中文流式输入。初次测试暴露普通重复执行不应被只读收束及渲染键名带空格的问题，分别修正判断范围及测试断言后通过。未连接 Jetson 或播放轨迹。


### 2026-09-07 工具详情关闭与颜色、减少独立检查往返

- 工具详情标题新增可点击关闭入口；收起后重查终端光标位置，修正再次展开时鼠标落点失效。工具按读取/执行/修改/状态配色，错误红色；PTY 显式启用 256 色。
- run_python 内置语法编译检查，语法错误在创建子进程前返回；正常调用不再需要单独 python_check。同步默认工具说明和任务提示，不更改用户权限或机器人程序。
- 验证：`LOOP_TASK_AUTOSTART=0 .venv/bin/python -m unittest tests.test_tool_groups_terminal tests.test_tool_groups tests.test_color_output tests.test_color_terminal tests.test_python_runner tests.test_read_loop_reasoning -q`，20 项通过，含中文草稿、鼠标展开/关闭/重开和错误脚本不执行。
- 会话累计用量及计量边界见 [Token 报告](research/token-accounting-and-efficiency.md#12-2026-09-07-实际累计用量核查与本次节省措施)。已有 CLI 进程须正常退出再启动加载源码；未重启设备或执行轨迹。

补充回归：交互、任务导航和缩放共 25 项中，24 项通过；中文流式旧断言未适配彩色输出和工具延迟汇总，更新为去除颜色后验证正文、显式刷新工具组并校验时间格式，该项单独重跑通过。缩放测试早期出现过短窗口空白，后续该组通过，尚未证明间歇问题完全消失。

### 2026-09-07 每次启动重置 Session Tokens 显示

状态栏以本次进程首次载入各 Session 的 usage 为基线，只显示本次启动的新增用量与新增缺报标记；新启动和首次恢复旧 Session 均从 0 显示，同次启动切换回来继续累计。历史 usage、对话和任务记录不清空。`/context` 中 token_usage 仍是会话历史累计值。验证覆盖旧会话启动显示 0、新增计数、缺报标记、持久化历史累计、会话切换隔离及中文 PTY。

### 2026-09-07 必要修复的连续执行与运行中详情滚动

- 前台 BASE_PROMPT、后台 TaskWorker 提示和发行 workflow 明确：执行目标包含必要、范围内可恢复的软件诊断/备份修复/验证；前置条件失败只暂停依赖动作，不停止能继续的排查。真实缺失权限、输入或范围外操作仍须报告，不削弱安全检查。
- 工具详情和 Actions 正文新增滚轮处理；普通详情 ↑/↓ 逐行滚动，任务选择和补全方向键优先行为保留。滚动不受 Working 状态影响，正文点击不关闭面板。
- 验证：工具详情运行中真实 PTY（滚轮双向、↑/↓、中文草稿、关闭重开）、窄标题和任务导航 6 项通过；`PYTHONPATH=.:tests LOOP_TASK_AUTOSTART=0 .venv/bin/python -m unittest tests.test_coding_agent tests.test_workflow_harness tests.test_task_supervisor -q`，36 项通过。初次未配置 tests 导入路径导致 model_fixture 导入失败，按项目测试路径重跑通过。故障 Worker 的异常输出是测试注入。
- 这是执行策略和终端代码修复；未调用真实模型验证自主决策，未连接机器人、修改远端保护或回放轨迹。前台重新启动加载；既有后台监督器须结束活动任务后按既有流程重启加载提示，未自动中断当前任务。

### 2026-09-07 主界面原生滚动被鼠标捕获阻断

前次只验证 Actions 内部滚动，遗漏主界面因已有工具组持续启用鼠标捕获，滚轮不再交给终端原生 scrollback。本次仅在 Actions 打开时启用 mouse_support；主界面和收起后的视图释放捕获。为保留输入草稿，Ctrl-O 打开/关闭工具详情，/tools 仍有效；主界面摘要取消误导性的 click 文案和鼠标入口。

验证：工具组 PTY 与任务导航共 5 项通过，覆盖运行中主界面未发送鼠标启用序列、关闭详情后发送禁用序列、详情滚轮与方向键、中文草稿、重开和 Esc。原生历史滚动由用户终端实现，此处验证捕获协议释放，未模拟桌面终端的滚动条拖动。确认本机 loop 指向项目 .venv/bin/loop，重新打开加载源码，无需安装；未停止后台任务或操作机器人。


## 2026-09-07：重复检查、停止来源与等待任务修复

- 查明运行时停止提示曾作为 user 消息插入，导致模型把内部停止误称为用户要求；改为 system 并明确内部来源。连续两轮无进展提示具体修复，六轮停滞终止空转；前台仍无总工具轮次上限。
- 相同脚本、参数与输出不因 timeout/日志文件名变化算新进展；查询类工具不再算实际操作。大 stdout/stderr 保存可分页的文本，模型预览保留状态与路径，减少反复运行来取日志。
- needs_input 展示 worker 实际原因；缺少验收条件且无新信息的 resume 不再重新排队。当前请求显式进入上下文，旧任务不是新动作的授权来源；收紧重复承诺与排除项的反馈规则。
- 验证：`PYTHONPATH=.:tests LOOP_TASK_AUTOSTART=0 .venv/bin/python -m unittest tests.test_python_runner tests.test_context_window tests.test_read_loop_reasoning tests.test_tool_continuation tests.test_task_supervisor tests.test_task_scope tests.test_task_navigation tests.test_workflow_harness tests.test_task_autonomy tests.test_coding_agent -q`，69 项通过（14.350 秒），`git diff --check` 通过。日志：[execution-stall-regressions.log](../artifacts/terminal/validation/execution-stall-regressions.log)。包含真实本地读取→编辑→执行验证和超过64KiB输出的末尾取证；故障 Worker 堆栈为测试注入。首次回归新测试缺 system_prompt，修正测试配置后通过。
- 未调用真实模型或设备，也未重启既有 CLI/Task 服务；运行中的 Python 进程需重启加载源码。模型语义遵从与机械臂播放尚未端到端验收，不将本地回归当成机器人已运动。


## 2026-09-07：记忆来源分层与审核

用户要求与助手建议分层；新增 source_role、review_status 与历史数据权限标记，保留独立判断原则。排除明确引文/粘贴终端对话的自动偏好提取；retain 拒绝来源未知/冲突细节；召回过滤旧的未标记详情，手动检索仍保留审核状态。用户与工具相同文本分键，助手来源笔记仍未验证，原始历史不删除。此为来源结构与提取边界审核，不宣称通用语义事实审计。

验证：`PYTHONPATH=.:tests LOOP_TASK_AUTOSTART=0 .venv/bin/python -m unittest tests.test_memory_layers tests.test_learning tests.test_connection_memory tests.test_coding_agent -q`，49 项通过（2.644 秒），git diff --check 通过。覆盖引文不升级偏好、未知/冲突来源拦截、不同来源不覆盖、来源链接不使助手笔记变成事实、既有成功连接召回。首轮发现 last_success 类型未列入运行时来源导致成功基准漏召回，补全后通过。日志：[memory-source-review.log](../artifacts/terminal/validation/memory-source-review.log)。未使用真实模型或设备；运行中进程需重启加载源码。


## 2026-09-07：本地操作小本本

将用户提供的连接、Host、VR、运动学、遥操作、录制与回放命令整理到被忽略的用户项目型号 docs/OPERATIONS.md，并更新现有三级索引。命令标为用户记录待验证；历史 PID、不同用途地址、孤立参数与描述不一致分别注明，不推定凭据。通用上下文改为已知小本本直接定位相关段，未知入口才发现索引，避免把逐级读索引变成每轮仪式。

静态验证：11 段 Bash 命令通过 bash -n，本地链接全部存在，上下文模块编译通过；git check-ignore 确认笔记被忽略，git ls-files -- user_projects 为空，git diff --check 通过。未执行命令或连接设备，不把语法检查记为操作成功。笔记读取即可使用；运行中 Loop 的通用 Python 提示规则需重启加载。


## 2026-09-07：简化执行 harness

按用户要求精简默认 workflow 和个人 workflow，替换个人 AGENTS 的通用运动前校准审查条款；后台 Worker 也改为复用已知入口、遵从实际工具/驱动要求，不扩出一整套通用检查。保持权限、实际保护和真实回执验收。个人文件修改前已备份到用户目录 backups；个人操作内容未进入源码。真实 harness_prompt 读取确认新规则生效、旧条款不再加载。未执行机器人操作或自动重启任务服务。

验证：test_workflow_harness、test_coding_agent、test_task_supervisor 回归通过；git diff --check 通过。日志：[simple-harness.log](../artifacts/terminal/validation/simple-harness.log)。用户 Markdown 下一次调用热加载；Python Worker 提示须进程重启。既有任务验收与历史消息不自动改写。


### 2026-09-07 任务视图原生选择与两个操作入口

任务卡片不再启用鼠标捕获，避免左右键进入后无法选择复制。入口改为 Enter session / Close session；进入将目标、状态及最近账本事件写入原生 scrollback，关闭只返回视图，保留任务记录/执行状态。未改变 Task 身份/归属，未提供独立聊天 Session，用户消息仍由原会话处理。

`LOOP_TASK_AUTOSTART=0 .venv/bin/python -m unittest tests.test_task_navigation tests.test_tool_groups_terminal -q`，5 项通过。PTY 覆盖中文任务、两操作、鼠标捕获释放、进入正文、关闭后 queued 状态不变；未模拟桌面剪贴板操作。未连接设备或取消后台服务。


### 2026-09-07 Task 独立 Session 与手动工具目录对齐

核查 c50f7bab1e06 的真实回执：模型被告知可使用 agents_status，调用却被 TaskWorker 的工具白名单拒绝；其后把一次工具拒绝泛化成缺少所有执行能力，并以缺验收/需要输入结束。不能据此声称 run_python 或 skill_run 本身不可用。

手动 Worker 使用完整注册目录，schema 与实际分发一致；strict_tools 不再注入不可用的元工具提示，元工具也经 App.tool 的共同权限门禁。定时工具与只读重新规划保持受限；缺少验收仍不判成功。settings_read(task_runtime) 解释实际目录与旧 worker_tools 字段的区别。

SessionStore 新增 task_sessions 关联表。新 Task 建立独立会话但不切走主会话；旧会话任务启动时补齐，Enter session 可懒创建。/resume 支持恢复独立历史/草稿/队列/usage，父会话记录不改写。任务仍归属原会话，关联聊天可查看该任务；进入输出最近 20 条账本事件并恢复聊天。模型按需获得有界任务状态上下文，进入不执行/重播任务，消息也不会自动成为运行中 Worker 的指令。

验证：Task监督器/Session恢复/任务导航/workflow/中文PTY共33项通过；设置与coding及PTY27项通过；多终端6项通过。包含子进程使用不在旧列表中的 agents_status 经统一分发成功，定时 Worker 不继承该工具；独立会话的恢复、父会话隔离和provider隔离。两次测试入口错误已修正（缺 tests 导入路径或不存在的测试名）；无真实模型调用或运动验收。

运行生效：旧任务已注册聊天会话 e54a5f708d93，任务仍 waiting_input。确认监督器无 running/queued/retry_wait、无启用自动规则、子进程仅 resource_tracker 后，按现有权限检查重启监督器：PID 68331 → 952117，新心跳正常。没有恢复旧任务、启动机器人或播放轨迹。前台 CLI 仍需重新打开加载会话界面代码。
