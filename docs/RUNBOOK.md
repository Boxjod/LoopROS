# 已验证操作

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

2026-09-05 品牌统一为 **Loop ROS**：目录／Python 包 `loop_robot`，发行包 `loop-robot`。`.venv/bin/python install.py` 已安装 `loop`、`loop-switch`，修复此前指向旧目录的用户命令链接，保留 `looper`／`looper-switch` 别名。未迁移或删除凭据、会话、任务及日志。

项目外 `/tmp` 已验证 `loop --version`、`loop robot --version`、`looper --version` 均返回 `Loop ROS 0.1.0`；`loop robot --once /commands` 正常。隔离配置的真实 PTY 验证 `loop robot` 进入 Loop Switch 向导并取消退出。完整命令 `PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`：**79 项通过，无跳过**，包含中文流式输入渲染和新名称／配置兼容测试。文档链接检查通过，无付费 API 或真机调用。

2026-09-05 中文流式显示覆盖修复：根因是 `print(..., end="", flush=True)` 把未换行片段提交到 stdout，随后输入重绘覆盖原文。未完成的文字改由输入渲染器显示，完整行／轮次结束后再写入滚动历史；实时预览按字符显示宽度裁剪，不丢弃完整历史。真实 PTY 配合 pyte 屏幕模拟器验证24×6、40×12、80×24，覆盖中文分片、同时排队11、中文草稿中间插字及Ctrl-C保存退出。含渲染检查的77项测试通过，无线上模型调用。

验证命令（项目目录）：`PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest discover -s tests -q`。本次 pyte 安装在临时验证目录；若该目录已清理，可用 `.venv/bin/python -m pip install --target /tmp/looper-terminal-validation pyte` 重建。不提供 pyte 时仅屏幕模拟测试跳过；其余测试仍运行。持久回归入口为 `tests/test_terminal_render.py` 与 `tests/test_interactive.py`。

2026-09-05 交互输入升级：行内 prompt_toolkit 编辑器、Chat Completions SSE、图片／视频抽帧附件、FIFO 队列及取消后暂停。无固定分栏或最低窗口尺寸。Ctrl-C先清空非空输入，空输入时保存退出；conversation.sqlite保存上下文、草稿、等待队列和流式事件，同配置恢复，队列默认暂停。按键替身覆盖插字、多行粘贴、队列暂停恢复和后台输出保护草稿；真实 ffmpeg 合成视频抽出2帧。完整回归75项通过；真实PTY覆盖24×6、40×12、80×24、160×40及运行中缩放到32×8，均通过/queue、/exit且未切备用屏。API和模型视觉能力尚未在线验证。用法见 [TERMINAL](TERMINAL.md)。

2026-09-05 简化 Switch：完整回归 **65 项通过**；隔离 LOOPER_HOME/state 的真实 PTY 验证无 Key 自动进入向导、取消正常退出。自定义模型发现与 Responses 工具循环采用替身测试，未使用真实 Key。参见 [QUICK_SETUP](QUICK_SETUP.md)。

2026-09-05 用户全局目录增补：`.venv/bin/python -m unittest discover -s tests -q` 共 **59 项通过**。新增 LOOPER_HOME 隔离测试覆盖凭据保存、endpoint 隔离、POSIX 0600、配置覆盖、Master harness 与长度预算。初始化本机 ~/.looper 与非敏感默认规则；未写真实 Key、未调用 API。参见 [USER_HOME](USER_HOME.md)。

## Installed terminal — 2026-09-05

From the project directory, `.venv/bin/python install.py` installed editable `loop-robot==0.1.0` and user-level `loop` / `loop-switch` links. Existing configuration and runtime data were preserved.

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
python3 run_demo.py
```

成功信号：测试全部 OK；demo 输出 verdict=pass、max_joint_error_rad 约 0.1，退出码 0。demo 第一次 review 为 fail、第二次为 pass。

副作用：默认在 `artifacts/demo.sqlite` 追加事件，不覆盖历史；可以用 `--output /明确路径/demo.sqlite` 指定输出。测试使用内存 SQLite；Python 可能生成 `__pycache__`。不连接网络、机器人或 GPU，不启动后台进程。

检查证据：

```bash
python3 -c 'from core.store import EventStore; s=EventStore("artifacts/demo.sqlite"); print([(k,v) for k,v in s.events() if k=="review"]); s.close()'
```

示例只验证数值反馈闭环，不能作为物理操作成功证明。硬件与外部模型接入未验证。

## 可选物理工具链（2026-09-05）

项目 `.venv` 使用 Python 3.13，已安装并验证 MuJoCo 3.12.0／Mink 1.3.0。安装版本见 `requirements-sim.txt`，不改系统 Python 与旧仓库环境。

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python run_sim.py
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
