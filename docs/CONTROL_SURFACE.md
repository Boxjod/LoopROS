# 扩展版指令与权限控制面

2026-09-05。按用户“先增加功能、后面再精简”的要求扩展，保留独立小模块以便后续裁剪。

## 数量口径

权限预设：`/permissions default|plan|cautious|yolo`。default 恢复默认逐项规则，plan 禁止执行类动作，cautious 对所有注册动作询问，yolo 全部放行并切到 sim；预设覆盖已有规则，之后可继续逐项定制。YOLO 是现有工具权限配置，不提供未实现的硬件驱动或任意 shell。交互按键与任务面板见 [终端规范](TERMINAL.md)。

修改前23个 slash入口，其中 /shortcuts、/quit 为别名，21项独立功能。修改后 **41个 slash入口**，将 /shortcuts、/quit、/plan 三个明确别名合并后为 **38项功能**。子命令、参数组合、中文快捷短语、LLM工具名不重复计数。

运行 `/commands` 获取实际清单与别名；`/help` 展示操作方式。清单在 terminal/control.py，已有入口在 terminal/app.py。

| 分组 | 指令 |
| --- | --- |
| 帮助与配置 | /help、/shortcuts、/commands、/config、/doctor、/tools |
| 模型 | /key、/expert-key、/model、/switch、/complex |
| 会话 | /context、/history、/compact、/clear、/exit、/quit |
| 权限与模式 | /permissions、/requests、/approve、/mode、/plan |
| 多Agent | /agents、/spawn、/send、/result、/stop-agent |
| 定时任务 | /after、/every、/jobs、/cancel |
| 仿真与机器人 | /sim、/scene、/robot、/devices、/joints、/move、/home、/stop |
| 模型服务 | /policy、/status |

## 权限规则

```text
/permissions
/permissions ask move_sim
/move 0.2 -0.1
/requests
/approve <请求ID>
/approve reject <请求ID>
/permissions deny generate_scene
/permissions allow move_sim
/plan
/mode sim
```

可配置动作：run_sim、move_sim、generate_scene、expert_advice、spawn_agent、policy_start、devices。精确动作匹配，不支持glob、文件路径或命令参数匹配。默认除policy_start为ask之外，其余已实现动作allow；这是保持既有仿真工作流的初始策略，不等于所有工具或系统权限全开。

- allow：通过该动作权限门，仍需参数、工具授权和运行边界检查。
- ask：先阻断并记录确切参数，/requests查看后由用户/approve执行一次；模型不会自己批准。审批不会自动继续原先失败的任务链，结果由这次指令返回。
- deny：禁止。一次审批不能覆盖后来修改的deny规则。
- plan：禁止仿真推进、场景生成、启动子Agent及策略服务。对话、专家咨询、状态与设备节点只读观察仍可用；必要的会话／权限元数据仍会写盘，不是文件系统只读沙箱。
- sim：按仿真权限检查。real（hardware 别名）可在会话内选择并持久化，回执为 driver_required；切换不连接设备，现有适配器和硬件验收限制仍有效。

generate_scene权限覆盖完整场景流水线及其可能的专家升级；expert_advice仅指独立专家咨询工具，不是禁止所有GPT API流量。对话模型请求本身由API配置管理，不受这组动作规则当作通用网络防火墙拦截。

权限状态写当前state-dir下permissions.sqlite；审批请求只在进程内保留，最多32条，退出丢弃，不自动执行过期队列。权限更新自后续执行检查生效，不撤销正在执行的外部API请求。服务启动的用户确认对应一次授权；未通过用户确认的隐藏工具调用仍会进入ask。被deny或plan禁止时，确认也无效。

模型工具、slash和子Agent已授予工具都经过动作检查；子Agent还必须通过角色工具白名单。模型通过 settings_read/settings_update 管理配置；settings_update 默认 ask，沿用 /requests 和 /approve 的确切参数单次审批，用户也可用 /permissions allow settings_update 持续授权。/approve 不注册为模型工具，定时任务和持久任务不能调用配置管理工具。权限层不是OS沙箱，也不替代设备看门狗、进程隔离或驱动限位。

## 模拟机械臂控制

```text
/robot
/joints
/move 0.2 -0.1
/home
/stop
```

对象固定为两关节MuJoCo演示本体sim-arm，单位rad、范围[-1,1]。本轮增加终端会话内连续状态：/move与/home复用同一个模拟本体，不每条命令重置到初始位置。通过已有Loop执行、数值Reviewer打分，并写Episode。/joints在尚未初始化时明确返回not_initialized，不捏造观测。

/home是模拟关节零位，不是未知机械臂的真实回零流程。/devices枚举/dev/video*、ttyUSB*、ttyACM*和serial/by-id，并读取sysfs驱动/USB标识、解析别名，不打开设备、不读电机、不声称已识别本体。基础串口工具open_serial/read_serial/serial_status/close_serial见[HARDWARE](HARDWARE.md)，独立于真机运动能力。

/stop设置模拟步进取消事件、将run_sim和move_sim设为deny，并取消现有子任务；不发送真机指令，也不停止外部模型服务。恢复模拟需显式 /permissions allow move_sim 或 run_sim。该停止检查发生在物理步之间，宿主若阻塞于别的工具可能延迟响应；不能作为硬件急停。

尚未新增真机enable、gripper、torque、自由探索、ROS控制topic等可执行动作，原因是对应驱动、标定与停止验收未就绪；不以空壳命令冒充支持。后续可在具体型号适配完成后增加，而不改变现有权限门。

## 会话与诊断

/context显示消息与字符数，不假装精确token计数。/history读取当前内存历史。/compact只保留最近4轮并丢弃更早内容，**不是模型摘要**，不会调用API；不存在自动恢复。/config显示已验证配置字段，不显示进程内Key。/doctor只查模块可发现性及Python入口，不将发现包视为导入成功、模型联通或设备健康。

## 与Claude Code的对应与差异

借鉴其命令入口、权限模式及由宿主执行allow/ask/deny规则的思路。[Claude Code命令文档](https://code.claude.com/docs/en/commands)、[权限文档](https://code.claude.com/docs/en/permissions)

本版补齐同类的permissions、plan、context、compact、config、doctor入口，但语义以本项目文档为准；没有复制Claude Code的acceptEdits、auto、bypassPermissions、MCP、插件管理、会话树、文件回滚、精确费用统计等。Claude Code的完整指令集合会随版本、插件及Skills变化，不用一个固定总数做等价比较。

## 验证

53项完整环境测试通过，新增权限持久化、审批单次使用、deny优先、plan拦截、复杂场景审批参数保留、隐藏服务启动阻断、指令计数、会话裁剪和真实MuJoCo连续移动／归零／停止测试。无真机连接、无付费API调用。本轮使用project-maintenance维护规范与入口，保留模块化实现供后续精简。

`/node`管理常驻进程，`/node use NAME|master`切换终端目标；node焦点下的/status、/joints、/move、/home操作该节点。/stop回收模拟节点，/plan回收全部节点。完整操作见[NODES](NODES.md)。


明确用户输入“允许所有执行权限”“允许全部执行权限”或“放开所有执行权限”时，操作入口将当前已注册动作设为allow并切换sim模式。它不调用模型、不自动运行工具，不增加未实现的驱动能力；定时任务禁止修改权限。具体动作仍需已有工具与实际设备参数。


## 会话配置管理（2026-09-07）

`settings_read` / `settings_update` 始终出现在通用会话工具中，无需加载 robotics。可用自然语言要求修改配置，模型先读取目标，提交具体变更并根据回执说明生效时间。默认写操作沿用权限门禁的 ask；已有 allow 授权后直接执行。配置写入不是启动服务或运动授权。plan 允许会话配置元数据变更，执行类工具仍被禁止。

| target | 修改内容 | 生效时间 |
| --- | --- | --- |
| permissions | mode: plan/sim/real（hardware）；profile: default/plan/cautious/yolo；action/rule | 当场保存并执行既有节点权限收紧逻辑；预设仍会重置为 plan 或 sim |
| profiles | save（可 replace）、use、remove；完整 provider 参数 | 当场；保留会话历史，按 endpoint/env 隔离内存 Key |
| config | 完整替换用户 config.json；llm/expert、scene、services | 下次 Loop 启动；显式 --config 优先，已选 profile 仍权威 |
| agents | 完整角色注册表 | 当场及下次启动；保留既有角色工具范围校验 |
| task_runtime | 完整任务策略，写当前 STATE 覆盖 | 下次显式启动监督器，不自动恢复任务 |
| deployment | manifest 和 host_id | 当场绑定，无设备启动；需先停止拥有的节点，不允许跨 deployment/host 复用 STATE |

写入前校验，文件替换保留备份。permissions 使用与 `/mode`、`/permissions` 相同的即时规则，监督器在线不阻止切换；权限变化在后续工具检查生效，并回收受影响的前台 Node，不自行启动设备。其他配置仍由活动子Agent或任务监督器阻止修改，错误发生在持久化前。Harness/Skills 使用已有专用工具。Key 使用会话内 `/key save` 隐藏输入，不能作为模型工具参数；启动目录环境变量在下次启动生效，不在当前进程迁移状态。

2026-09-07：审批执行遇到明确的配置前置阻塞时保留原 ID、参数和阻塞原因，解除条件后可再次 `/approve ID`；成功后消费一次。重复并发审批会被拒绝。其他执行异常可能已有副作用，不自动保留可重放的授权；旧 ID 或已消费 ID 给出 `/requests` 指引，不再显示裸 KeyError。审批仍只存在当前进程，重启前的 ID 不可恢复。

直接用户命令也支持：

```text
/mode real
/config permissions
/config profiles
/config set permissions {"mode":"sim"}
/config set permissions {"profile":"yolo"}
/config set profiles {"operation":"use","name":"my-profile"}
```

`/config set TARGET JSON` 是用户直接管理入口；后台定时指令不可调用。配置文档采用完整替换语义，先读后改，不把未提供字段当作隐式补丁。`settings_read` 不带参数返回目标目录及其他配置入口。真实远程机器人驱动仍需按具体型号接入，不能以 real 模式或 carrier 声明冒充连接成功。
