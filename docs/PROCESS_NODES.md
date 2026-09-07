# 一个 CLI 管理本地与 Jetson 程序

进程节点用于长驻 host、推理服务、安装命令或交互程序。启动后由 Python 子进程和操作系统维持运行，不调用模型维持心跳。`/node` 命令直接执行；自然语言让 Master 安排工作仍会调用模型，外部聊天程序也可能自行使用模型。

Session 保存对话，Task 保存有目标和验收的工作，Node 持有实际运行的进程。这里不需要为每个服务创建循环推理 Task。可同时运行多个 Node，切换对话或 `/new` 不会停止它们。

0.0.3 起，普通 process Node 与 ROS Node 均正常中断退出：POSIX 发送 SIGINT，Windows 使用进程组 CTRL_BREAK。可选 stop_argv 仍先执行；本地命令尚未退出时再发送中断，不自动升级 TERM／KILL。等待超时返回 stopping，监督进程、输出句柄与资源租约保留到实际退出；关闭运行时后也继续监测尚未退出的工作进程。服务停止与电机失能分别验收。明确授权的强制信号仍使用 process_stop 的对应模式。

## 使用

`loop node` 可在没有 API 配置的情况下进入节点终端；正常 `loop` 内也可操作。先检查 `/node profiles` 中的命令，再按既有权限流程允许宿主执行：`/permissions allow run_python`。`node_start` 与 `node_command` 也经过统一门禁，plan 模式禁止启动。配置文件不是额外的执行授权。

以下名称对应本机已准备的用户配置，远端和服务尚未实测：

```text
/node profiles
/node start process robot jetson-host
/node start process act workstation-act
/node status robot
/node logs act
/node use act
logs
master
/node stop act
/node stop robot
```

OpenPI 替代流程使用 `openpi-policy`、`jetson-agent-client` 和 `loopmaster-chat`。先核对路径、依赖和启动回执，再启动依赖它们的程序。切到聊天节点后用 `send 你的问题` 发送一行，`logs` 查看输出，`master` 回到 Loop 对话。也可以使用 `/node send NAME TEXT`。此版本提供行输入和输出尾部，不是完整的嵌套终端模拟器，尚无自动依赖编排或服务就绪探测。

## 配置

配置位于 `~/.loop/processes/NAME.json`，遵从 `LOOP_HOME`。例如：

```json
{
  "description": "Local service",
  "cwd": "/absolute/project/path",
  "argv": ["./service.sh", "start"],
  "stop_argv": ["./service.sh", "stop"],
  "env": {"SERVICE_PORT": "8000"},
  "env_names": ["SERVICE_CONTROL_TOKEN"]
}
```

`argv` 直接传给进程，不隐式套 shell；需要 shell 时显式配置 `bash -lc`。SSH 配置的 `cwd` 仍是本地目录，远端目录切换放在 SSH 命令内，使用已有 SSH 认证与主机密钥。`remote: true` 标记远端状态尚未验证。

`env_names` 只写变量名；变量须在启动 Loop 前由既有凭据入口提供，缺失时启动失败。不要把凭据写入 JSON、argv 或 `send`，输入命令会被记录。子进程只继承基础环境及显式选择的变量；已知凭据环境值在输出中脱敏，这不构成任意程序输出的完整秘密检测。SSH 不自动把本机环境变量传给远端。

模型启动工具使用 `node_profiles` 返回的内容哈希，配置改变后须重新读取。同一个配置不能在同一运行时重复启动。配置属于用户文件，发行默认值不保存个人地址与凭据。

## 状态与退出

`state=running` 表示节点监督进程有心跳且尚未报告命令退出；命令已退出时主状态显示 `exited`，监督进程仍可保留以读取日志/执行停止入口。`snapshot.process_state` 和 `returncode` 表示所启动命令的状态。脚本退出 0 不证明机器人或推理服务就绪。命令退出后保留节点和输出，便于查看日志和执行 `stop_argv`；停止节点后可重新启动。

`/node stop` 先尝试 `stop_argv`（超时 4 秒），再终止仍存活的本地子进程组。SSH 断开、停止脚本返回或节点退出都不证明远端服务已停止；远端状态需要另行检查。日志接口保留有界输出尾部，停止时写入输出日志，不是无限完整终端录制。

节点归当前 CLI 所有，退出 CLI 会回收；不支持退出后保活、其他 CLI attach 或自动恢复。真实机器人动作仍须遵从已有权限和硬件验收。

验证入口：[进程测试](../tests/test_process_nodes.py)、[中文 PTY 测试](../tests/test_process_terminal.py)。测试只启动本机测试进程，不连接 Jetson、安装 OpenPI 或操作机器人。

## API 不可用时的离线能力（2026-09-07 源码核对）

`loop node` 跳过聊天 API 配置向导；进入后 `/node profiles`、`/node start process NAME PROFILE`、`/node status NAME`、`/node logs NAME`、`/node stop NAME` 直接调用本地命令分发，不需要模型解析。已有配置可以重复使用，仍执行当前权限和资源准入。这里的离线指无需聊天 API；SSH目标、网络模型服务和待下载依赖仍须可达。

当前 `/task`、`/tasks resume` 和已配置 schedules／triggers 使用 TaskSupervisor 派发 LLM 子 Agent，因此不能作为 API 断连时的确定性流程执行器。历史 Task 保存的目标与回执、学习得到的 Skill 文本均不等于可直接执行的离线任务模板；带 run.json 和脚本的执行型 Skill 已支持 `/skills` 离线选择，见 [离线 Skills](OFFLINE_SKILLS.md)。未实现 API 失败后自动把自然语言映射成旧任务或自动重放历史动作。

若要实现“启动机械臂”“运行已设定任务”等短名称入口，下一步应将已核实流程固化为具名、版本化的本地配方：明确参数、顺序和依赖、就绪检查、验收与停止步骤，由固定执行器调用原工具门禁和共享资源基础层。聊天 API 可辅助生成／修改配方，执行配方本身无需 API。独立 DAG 配方执行器尚未实现；当前可把固定流程写入 Bash／批处理，并通过 `/skills run 标题` 复用 Node 执行。启动机械臂驱动／Host进程与电机使能、回零、运动分别定义，不能从历史“成功”推导本次动作已获授权或服务已经就绪。

核对入口：terminal.app.main、terminal.nodes.command、terminal.task_tools.dispatch、terminal.task_supervisor.TaskSupervisor；本次仅核对源码并补充说明，未启动机器人或远端进程。


## 内置端口、进程和内存管理（2026-09-08）

普通模型工具和 `/node` 共用内置入口，不再要求生成 SSH/Python 停止脚本：

- `process_inspect({host, ports, pids})`：host 默认 local，也可用 SSH 别名/user@hostname；按 TCP 监听端口或 PID 查询，返回每个进程的 identity（PID/启动 ticks/host boot ID）、名称、RSS、父 PID、监听端口及主机可用 RAM。未提供选择器时返回 RSS 最大的进程（最多 64 个）。不输出完整进程命令行/环境，避免将凭据带入上下文。
- `process_stop({host, targets, ports, mode, wait_s})`：targets 使用上次 inspect 的完整 identity；graceful=SIGINT，terminate=SIGTERM，kill=SIGKILL，escalate=依次 INT/TERM/KILL；每步等待默认 3 秒，上限 10 秒。明确强制 KILL 可以直接选择 kill。工具复查后返回 processes_stopped、ports_released、success 及内存前后观察。
- 离线命令：`/node inspect {"host":"local","ports":[6555,6556]}`；停止用 `/node terminate JSON`，JSON 与 process_stop 一致。不要复制示例 PID，应使用当次观察的 identity。

工具不自动杀端口的所有占用者，不随 PID 复用/服务自拉起而扩大范围；使用 pidfd 将信号固定到核对过的进程。祖先进程及 PID 1 受保护。目标进程退出但其他实例还占端口时，success=false。SIGINT 后仍存活只说明未退出，不据此猜测是否忽略信号。进程退出/端口释放均不证明设备失能、物理停止或完成运动。

process_inspect 使用独立只读门禁；process_stop 无独立配置时继承 run_python 的规则，显式 process_stop 规则优先，plan 禁止停止。审批记录绑定实际 process_stop 请求，不会误当 run_python 路径执行。Skill 不授予权限。

进程适配器目前覆盖 Linux `/proc` 的当前网络命名空间。远端通过既有 SSH 认证执行标准库脚本，不安装 SDK；停止需要目标 Linux pidfd 和 Python 3.9+。权限不可见/不支持/身份变化不伪报成功。超时或取消只终止本地控制器，远端可能已经收到信号，须 inspect 后决定后续操作；不自动重试信号。

本地用户 Skill 位于 `~/.loop/skills/process-management/SKILL.md`，不进入发行或 GitHub。测试使用临时本机进程、真实 socket 和 SSH 替身验证传输；未对机器人实测。
