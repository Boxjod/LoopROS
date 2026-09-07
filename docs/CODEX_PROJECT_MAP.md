# 项目地图

| 任务 | 权威文件／符号 | 验证 |
| --- | --- | --- |
| Agent标题选择／消息回执／同伴结果／交互权限 | [运行时](../terminal/agents.py)、[补全](../terminal/completion.py)、[显示](../terminal/command_display.py)、[规范](AGENT_RUNTIME.md) | test_agent_terminal（真实PTY中文流式）、test_agent_interaction、test_agent_ipc、test_agents |
| 无损压缩／上下文预算／Skill资源／Reader与监管线程 | [上下文视图](../terminal/context_window.py)、[Skills](../terminal/skills.py)、[Agent运行时](../terminal/agents.py)、[改进对照](research/agent-cli-capability-upgrade.md) | test_context_window、test_skills、test_agents、test_agent_ipc、test_slash_terminal、test_steering_render |
| 厂商 CLI／harness 源码参考 | [调研与克隆记录](research/vendor-open-agent-cli.md)、[本地副本清单](../reference/Agentic/README.md) | Git origin、HEAD、工作区状态与对象完整性；未安装运行 |
| 拖动缩放终端／极矮窗口草稿／中文面板越界 | [Terminal.display_budget](../terminal/interactive.py)、[规范](TERMINAL.md) | test_resize_render：真实 PTY 多行/队列/候选/流式缩放、光标编辑与宽字符边界 |
| /resume 切换上方聊天／/new 空白显示 | [Terminal.redraw_session](../terminal/interactive.py)、[历史渲染](../terminal/session_display.py)、[约定](SESSION_MEMORY.md) | test_session_display＋test_session_render：PTY 双向切换、旧滚动记录清理、中文流式草稿及事件不重复 |
| Fast 启动提示／服务商档位检测 | [检测说明](research/fast-mode.md)、[启动检查](../terminal/setup.py)、[客户端](../terminal/llm.py)、[欢迎页](../terminal/ui.py) | test_fast_startup＋test_setup_startup＋中文流式 PTY；真实服务商未测，持久化开关未接入 |
| 源码卸载／旧副本命令清理／只读预览／用户数据保留 | [uninstall](../scripts/uninstall.py)、[说明](INSTALL.md#uninstall-a-source-installation) | test_uninstall：临时目录真实 CLI、重复卸载、命令归属、数据和链接目标保留 |
| 中英文项目介绍／README Logo | [English](../README.md)、[简体中文](../README.zh-CN.md)、[README Logo](../assets/logo.png) | 本地链接与图片引用核对 |
| 根目录分类／安装和资源路径 | [目录说明](../README.md#repository-layout)、[打包配置](../pyproject.toml)、[安装脚本](../scripts/install.py) | RUNBOOK 的目录整理验证记录 |
| Python脚本执行／stdout与退出码／执行权限 | [run_python](../terminal/python_runner.py)、[说明](PYTHON_EXECUTION.md) | test_python_runner：权限、哈希、真实输出、退出、取消、限时/限量；非沙箱 |
| 飞特总线波特率/ID探测、STS3215状态与Host控制原语 | [feetech](../toolchain/feetech.py)、[终端工具](../terminal/feetech.py)、[说明](FEETECH.md) | test_feetech：真实pyserial/PTY、回显坏帧、未知型号、取消、去重、权限；真机待验收 |
| 多载体清单／主机分配／实例绑定与请求去重 | [Deployment](../core/deployment.py)、[Carriers](../terminal/carriers.py)、[部署说明](DEPLOYMENTS.md) | test_carriers：双 MuJoCo、双 Host 隔离、旧实例拒绝、重复/丢回执、权限、目录外启动 |
| 分层记忆／每轮事实标签／经验召回／技能反馈与笔记修订 | [ExperienceStore](../core/experience.py)、[Learning](../terminal/learning.py)、[事实提取](../terminal/memory_facts.py)、[三层索引/流程固化](../core/memory_layers.py)、[最近成功与回退](../terminal/connection_memory.py)、[规范](LEARNING.md) | test_connection_memory＋test_memory_layers＋test_learning：长期习惯、三次流程固化、跨会话、真实子进程、假成功拒绝、版本冲突、停用/隔离、故障降级 |
| 当前窗口机械臂轨迹／位置IK／关窗重开面板 | [Motion](../toolchain/viewer_motion.py)、[SimulationControl](../toolchain/viewer_control.py)、[Terminal.poll_viewer](../terminal/interactive.py)、[规范](MUJOCO_CONTROL.md) | test_viewer_motion＋test_cli_edges＋test_terminal_render；X11实际关节到位 |
| 轻量对话／文件编辑／图片网址／Skills和harness热更新 | [context](../terminal/conversation_context.py)、[coding](../terminal/coding.py)、[references](../terminal/references.py)、[harness](../terminal/harness.py)、[规范](CODING_AGENT.md) | test_coding_agent＋test_files＋test_skills；真实Logo视觉调用 |
| 日常家具/GSO/Fuel下载、衣柜、鼠标拖拽 | [household_assets](../terminal/household_assets.py)、[worker](../toolchain/viewer_worker.py)、[说明](HOUSEHOLD_ASSETS.md) | test_household_assets；真实X11拖球/Control滑条/空格 |
| 已授权服务器／暂存与上线边界 | [DEPLOYMENT](DEPLOYMENT.md) | root SSH已验证；最终HTTPS域名未确定 |
| HTTPS发布／uv安装／update与回滚／版本管理 | [发布规范](RELEASES.md)、[builder](../scripts/build_release.py)、[client](../release_client.py) | test_releases＋test_updates；真实升级/回滚/卸载见 RUNBOOK；发布回执见 DEPLOYMENT |
| 双语官网／GitHub README Docs／各系统安装与单独部署 | [英文网页](../website/index.html)、[中文网页](../website/zh-CN.html)、[双语 README](../README.zh-CN.md)、[网页导出](../scripts/build_website.py)、[网页发布](../scripts/publish_website.py)、[Shell](../scripts/install.sh)、[PowerShell](../scripts/install.ps1)、[安装说明](INSTALL.md) | Shell --check、JS语法／交互检查；Windows实机待验证 |
| Loop ROS 品牌／loop ros／旧命令兼容 | [package](../pyproject.toml)、[installer](../scripts/install.py)、[App](../terminal/app.py) | test_branding＋项目外启动 |
| 旧名称清理／目录改名／环境修复／状态迁移 | [检查及处理记录](../../projects/reports/12_loopros_legacy_name_audit.md)、[home](../terminal/home.py)、[USER_HOME](USER_HOME.md) | test_branding：状态路径兼容、回滚、优先级；pip check＋项目外启动 |
| 跨平台安装与边界 | [平台规范](PLATFORMS.md)、[platform_support](../terminal/platform_support.py)、[安装](INSTALL.md) | test_platform_support；CI尚未执行 |
| MHS 调研／设备契约与技能闭环建议 | [研究报告](../../projects/reports/08_mhs_insights_for_looper.md) | 官方披露＋本地代码对照；未接入 MHS |
| 启动连接失败恢复／TLS证书／供应商与接口类型配置 | [setup](../terminal/setup.py)、[protocols](../terminal/protocols.py)、[向导](QUICK_SETUP.md) | test_model_connection＋test_setup＋test_setup_startup：本地 HTTP 401→PTY向导→Responses成功→退出 |
| 真实终端评估／JSON折叠／计算回执／异步取消 | [评估](../../projects/reports/13_terminal_harness_evaluation.md)、[App](../terminal/app.py)、[ChatAgent](../terminal/llm.py)、[显示](../terminal/tool_display.py) | test_harness_behavior＋test_stream_completion＋中文PTY；Qwen真实对话记录 |
| 电机SDK接入／全部执行授权 | [缺口与来源](../../projects/reports/14_motor_driver_integration_gap.md)、[权限](../terminal/permissions.py)、[机器人库清单](../terminal/robotics.py) | test_harness_behavior＋test_control＋test_robotics；真机型号待确认 |
| 用户全局目录／API Key／harness／Skills及换设备迁移 | [home](../terminal/home.py)、[config](../terminal/config.py)、[约定](USER_HOME.md) | test_home＋test_user_portability：地址隔离、权限、加载、保存、用户覆盖及整包迁移 |
| uv 引导／Python 3.8 安装／命令冲突备份切换／欢迎页 | [install](../scripts/install.py)、[package](../pyproject.toml)、[launcher](../launcher.py)、[UI](../terminal/ui.py)、[安装说明](INSTALL.md) | test_install＋test_platform_support；Python 3.8 引导与项目外 loop --version |
| core常驻多进程／Loop Node／终端焦点切换 | [NodeRuntime](../core/nodes.py)、[节点插件](../toolchain/node_workers.py)、[终端](../terminal/nodes.py)、[NODES](NODES.md) | test_nodes＋test_node_terminal：真实进程／MuJoCo／PTY／崩溃与回收 |
| 首问与最近问题标题／标题选择与任务显示 | [titles](../terminal/titles.py)、[SessionStore](../terminal/session.py)、[补全](../terminal/completion.py)、[终端](../terminal/interactive.py) | test_titles＋test_session_resume＋test_session_render：首末问题、重名稳定序号、标题带空格、中文 PTY 与 ID 隐藏 |
| Session 内工作记录／自编工具／调试反馈 harness | [SessionTask](../terminal/session_task.py)、[自编工具](../terminal/user_tools.py)、[工作流](../configs/workflow_harness.md)、[说明](CODING_AGENT.md) | test_task_scope：会话归属、迁移、历史与通知隔离；test_workflow_harness：实际失败→修复→验收、可移植包、/new/恢复、重复失败限制；test_session_render：中文流式 PTY |
| 修改最主要的反馈 loop | [Loop.run](../core/loop.py) | unittest |
| 会话保存／恢复／Ctrl-C退出 | [SessionStore](../terminal/session.py)、[Terminal](../terminal/interactive.py) | test_interactive：清空再退出、检查点、0600、服务地址隔离 |
| 工具JSON默认折叠／摘要耗时／详情查看 | [tool_display](../terminal/tool_display.py)、[SessionStore](../terminal/session.py)、[Terminal](../terminal/interactive.py) | test_tool_display＋test_terminal_render：摘要隐藏原文／details展开／中文并行输入 |
| 输入框下方提示与任务面板／分隔线／slash回车执行／队列预览及↑编辑／滚动／拖入媒体／剪贴板PNG | [Terminal](../terminal/interactive.py)、[SlashCompleter](../terminal/completion.py)、[操作面板与命令排版](../terminal/command_display.py)、[media](../terminal/media.py)、[read_stream](../terminal/llm.py)、[规范](TERMINAL.md) | test_interactive＋test_terminal_render（中文流式／同时输入，pyte＋PTY）；API替身 |
| CLI退格补全／纯附件／耗时slash与草稿恢复 | [Terminal](../terminal/interactive.py)、[SlashCompleter](../terminal/completion.py)、[检查记录](../../projects/reports/16_cli_interaction_review.md) | test_cli_edges＋test_completion＋test_terminal_render；80×24和40×12 PTY屏幕 |
| 默认交互入口／shortcut | [启动器](../loop)、[App](../terminal/app.py)、[终端规范](TERMINAL.md) | test_terminal＋PTY |
| 会话内修改模式／所有配置入口 | [settings](../terminal/settings.py)、[配置管理](CONTROL_SURFACE.md)、[用户目录](USER_HOME.md) | test_settings：工具循环、审批、持久化、Key 隔离、活动任务保护及各配置校验 |
| 指令计数／权限／模拟控制 | [control](../terminal/control.py)、[PermissionGate](../terminal/permissions.py)、[规范](CONTROL_SURFACE.md) | test_control＋/commands |
| Qwen API 与工具循环 | [llm](../terminal/llm.py)、[配置](../configs/config.example.json) | API 替身测试；线上未测 |
| 联网搜索／网页读取／城市天气与缺参数补问 | [web](../terminal/web.py)、[对话路由测试](../tests/test_weather_dialog.py)、[使用说明](WEB_TOOLS.md)、[工具分发](../terminal/app.py) | test_web＋test_weather_dialog；模型工具循环／换城／错误与权限；历史真实查询不等于当前模型验收 |
| API／模型配置选择、自动探测与公司/日期排序、删除与子命令补全 | [探测与向导](../terminal/setup.py)、[独立程序](../model_switch.py)、[ProviderStore](../terminal/providers.py)、[规范](MODEL_SWITCH.md) | test_setup＋test_setup_startup＋test_providers＋test_completion；本地 HTTP/PTY 模型列表与编号选择 |
| 默认桌面／MuJoCo窗口／自动补依赖 | [viewer](../terminal/viewer.py)、[窗口进程](../toolchain/viewer_worker.py)、[默认场景](../toolchain/scenes.py)、[App](../terminal/app.py) | test_viewer（过期心跳／恢复对话／能力检查）＋真实X11关窗重开；证据 artifacts/terminal/viewer/lifecycle_validation.json |
| 椅子生成／场景纠错／同路径内容更新与重载 | [scenes](../toolchain/scenes.py)、[viewer](../terminal/viewer.py)、[worker](../toolchain/viewer_worker.py)、[SCENES](SCENES.md) | test_chair_scene＋真实GUI哈希/对象核对＋椅子渲染预览 |
| 一句话场景／统一模型复杂推理 | [scenes](../toolchain/scenes.py)、[规范](SCENES.md) | test_scenes（JSON→几何反馈修正／专家失败／取消）＋真实 MuJoCo 编译与桌上支撑 |
| 定时任务 | [Scheduler](../terminal/scheduler.py) | test_terminal |
| 离线执行型 Skill／Bash／批处理／按标题选择 | [offline_skills](../terminal/offline_skills.py)、[包与快照](../toolchain/offline_skill.py)、[ProcessNode](../toolchain/process_node.py)、[说明](OFFLINE_SKILLS.md) | test_offline_skills＋test_offline_skill_terminal：无模型API、真实Bash与中文PTY、权限、哈希、快照停止；Windows端到端待测 |
| 共享资源基础层／多工作负载／动态并发 | [ResourceManager](../core/resources.py)、[HostMonitor](../toolchain/admission.py)、[接入约定](RESOURCE_RUNTIME.md)、[AgentRuntime](../terminal/agents.py)、[TaskSupervisor](../terminal/task_supervisor.py)、[配置](AGENT_RUNTIME.md) | test_resource_foundation＋test_resource_admission：共享Node／Python／模型／Agent预算、20／108额度、并发预留、资源压力与恢复、真实子进程、取消、权限与后台尝试计数 |
| Master／并行子 Agent 进程与同伴发现/通信 | [AgentRuntime](../terminal/agents.py)、[角色定义](../configs/agents.json)、[规范](AGENT_RUNTIME.md) | test_agents＋test_agent_ipc：真实并行HTTP、双向Pipe消息、身份/权限、取消回收 |
| pi0.5／ACT 服务调度 | [PolicyServices](../terminal/services.py) | 临时替身进程；实际模型未测 |
| 公共对象 | [contracts](../core/contracts.py) | unittest |
| 模拟本体／Master／评审器 | [plugins](../core/plugins.py) | unittest |
| 保存证据 | [EventStore](../core/store.py) | demo＋SQLite 检查 |
| 轨迹基础检查 | [trajectory](../toolchain/trajectory.py) | unittest |
| 轨迹编辑／插值 | [trajectory](../toolchain/trajectory.py) | test_toolchain |
| MuJoCo 物理执行／reset | [MujocoBody](../toolchain/mujoco_sim.py)、[demo](../examples/run_sim.py) | 可选环境 unittest＋run_sim |
| Ego2MuJoCo 桥接 | [ego2mujoco](../toolchain/ego2mujoco.py) | 参数检查；全流程未跑 |
| Mink FK／IK | [MinkKinematics](../toolchain/kinematics.py) | 可选环境 test_mink_fk_ik |
| ROS 只读观察 | [ros](../toolchain/ros.py) | 缓冲测试；ROS 通信未跑 |
| RAM／VRAM 模型池 | [ModelPool](../toolchain/resources.py) | 预算／活动保护／异常测试 |
| 本机网络信息／待审查通用工具 | [候选说明](../toolchain/candidates/network_discovery/README.md)、[实现](../toolchain/candidates/network_discovery/network_discovery.py) | `python -m unittest discover -s toolchain/candidates/network_discovery -q`；本机只读 ip JSON 回执 |
| 工具链接入方式与边界 | [TOOLCHAIN](TOOLCHAIN.md) | 对照测试记录 |
| 读取机械臂／Linux、Windows COM、macOS串口／USB证据 | [SerialPort](../toolchain/serial_port.py)、[跨平台发现](../toolchain/serial_discovery.py)、[list_devices](../terminal/control.py)、[设备工具测试](../tests/test_device_inventory.py)、[硬件边界](HARDWARE.md) | test_device_inventory、test_serial、test_serial_discovery：真实Linux枚举/PTY，Windows/macOS替身；型号/电机数/轴数未确认时不猜测 |
| 硬件适配范围 | [清单](../toolchain/hardware_targets.json)、[约定](HARDWARE.md) | JSON 解析；非硬件测试 |
| 运行／检查反馈 | [RUNBOOK](RUNBOOK.md)、[demo](../examples/run_demo.py) | 实际退出码与 review |
| 设计与待接入能力 | [ARCHITECTURE](ARCHITECTURE.md) | 与实现对照 |
| 自动打开／窗口实际控制／Menagerie资产 | [viewer](../terminal/viewer.py)、[控制器](../toolchain/viewer_control.py)、[资产库](../terminal/model_library.py)、[资产快照](../toolchain/model_assets.py)、[用法](MUJOCO_CONTROL.md) | test_simulator_control＋test_model_library＋真实GUI控制与网格模型加载 |
| MuJoCo版本手册／组合场景／自动搜物品／持续编辑 | [操作Agent](MUJOCO_AGENT.md)、[文档工具](../terminal/mujoco_docs.py)、[组合器](../toolchain/composition.py)、[资产库](../terminal/model_library.py) | test_composition＋test_mujoco_docs＋test_model_library；实际GUI哈希/回执 |
| Markdown粗体／跨流式片段样式 | [BoldText](../terminal/markdown.py)、[Terminal](../terminal/interactive.py) | test_terminal_render：中文并行输入及PTY粗体属性 |
| 机器人工程／电流力矩／PID／FK与动力学／故障诊断 | [规范](ROBOTICS_AGENT.md)、[工具](../terminal/robotics.py)、[数值](../toolchain/robot_engineering.py)、[模型分析](../toolchain/robot_model_analysis.py) | test_robotics：单位边界、PID饱和、Jacobian差分、动力学残差、来源/权限 |
| 显式场景工具的“只要一个”独立场景 | [scene_intent](../terminal/scene_intent.py)、[App.scene](../terminal/app.py) | test_scene_intent：单物品解析、模型选择工具、实际场景文件 |

| 历史会话选择／命名搜索导出／每轮总结／上下文预算 | [session](../terminal/session.py)、[交互入口](../terminal/interactive.py)、[turn_summary](../terminal/turn_summary.py)、[规范](SESSION_MEMORY.md) | test_session_resume：命名持久化、超过30条搜索、隔离/导出；test_session_render：真实PTY输入→命名→搜索→导出；test_interactive |

| 未完成任务持续迭代／后台监督／定时与OS事件 | [任务账本](../core/tasks.py)、[监督器](../terminal/task_supervisor.py)、[后台进程](../terminal/task_service.py)、[配置](../configs/task_runtime.json)、[使用说明](TASK_RUNTIME.md) | test_task_supervisor；真实独立进程、显式提交；历史用户模型只读验收 |

| 未完成任务按键面板（含 waiting_input）／权限配置 default-plan-cautious-yolo | [Terminal](../terminal/interactive.py)、[权限门禁](../terminal/permissions.py)、[操作入口](../terminal/control.py)、[规范](TERMINAL.md) | test_session_render：真实 PTY 切换/取消/权限菜单；test_control：配置持久化与门禁 |

| GitHub 初版准备／提示词收敛／GPT-6自定义API | [发布准备](GITHUB_RELEASE.md)、[配置](QUICK_SETUP.md)、[基础上下文](../terminal/conversation_context.py)、[Changelog](../docs/CHANGELOG.md) | test_setup、test_coding_agent、test_harness_behavior；实际GPT-6待验证 |

| 执行中追加要求／队列介入当前工具循环 | [ChatAgent](../terminal/llm.py)、[队列桥接](../terminal/interactive.py)、[终端规范](TERMINAL.md) | test_steering＋test_steering_render；安全边界/旧动作跳过/历史持久化/中文草稿 PTY |

| Slash 首页顺序／当前服务模型菜单／Fast 开关／中文补全隔离 | [补全](../terminal/completion.py)、[交互](../terminal/interactive.py)、[客户端](../terminal/llm.py)、[模型切换](MODEL_SWITCH.md) | test_slash_workflow、test_slash_terminal、test_fast_startup；实际桌面输入法选字待复测 |

| 单 CLI 管理本地／SSH 常驻程序，不轮询模型 | [ProcessNode](../toolchain/process_node.py)、[命令](../terminal/nodes.py)、[工作流](PROCESS_NODES.md) | test_process_nodes、test_process_terminal：真实本地并行进程、输入输出、停止、凭据环境隔离、中文 PTY；Jetson 启动未实测 |

| MuJoCo／Isaac 工具桥、MCP、多相机、ACT 数据与 Gym | [工作台](SIMULATION_WORKBENCH.md)、[服务](../toolchain/simulation.py)、[工具与权限入口](../terminal/simulation.py)、[MCP](../terminal/sim_mcp.py)、[Isaac host](../toolchain/sim_isaac_host.py) | test_simulation_workbench；scripts/validate_simulation_workbench.py：真实双引擎、相机与 HDF5；训练效果未验证 |

| 终端真实重排／三反引号代码块 | [交互渲染](../terminal/interactive.py)、[Markdown](../terminal/markdown.py)、[规范](TERMINAL.md) | test_resize_reflow.ResizeReflowTests（外置 xterm headless）、test_markdown_code、test_slash_terminal |
