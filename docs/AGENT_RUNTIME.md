# Master 与多 Agent 运行时

2026-09-05。终端是 UI，用户对话对象固定为 **Master Agent**。Master 是宿主中的独立命名会话、不是又一个机器人控制器；本版在单后台线程中运行 Master，子任务则在独立 Python 进程运行。没有宣称 Master 本身也是独立 OS 子进程。

```text
用户终端 → Master（当前选中模型，会话上下文）
               ↓ 启动／消息／取消
          AgentRuntime（进程监管、授权、事件）
               ├─ Planner：计划，无执行工具
               ├─ Worker：MuJoCo 执行工具
               ├─ Reviewer：只分析提供的证据
               └─ Expert：当前用户配置的模型，复杂推理（与其他角色共用模型和凭据）
               ↑ 结果／失败／证据路径
             Master 继续协调或汇总
```

默认角色不是每次都全部调用：简单问题 Master 直接回答，只有可分工任务才启动子 Agent。角色可多实例；默认资源并发上限108、运行180秒/任务、4096条子任务记录/运行时；实际并发按资源余量动态准入。子 Agent 各自拥有有限聊天上下文，不继承 Master 的全部历史；输入只包含委派任务与后续显式消息。

## 通信与控制

Master 的工具：spawn_agent、agents_status、agent_result、agent_messages、send_agent、cancel_agent。返回子任务 ID 不表示完成；结果状态区分 queued/running/done/failed/cancelled/timed_out。子 Agent 的 done 表示该角色完成回复，不能等同物理任务 pass。

消息通过宿主 broker 和 Pipe 传递；sender 由宿主绑定，子 Agent 无法冒充 Master。每任务最多16条、每条2000字符，在下一次模型调用边界读取；排队确认不是已读取保证。运行中可追加，已终止任务不可续写，需要新任务携带必要结果重新委派。每个子 Agent 获得宿主分配的 agent_id，并可调用 agents_status 获取 self_id 与运行中 peers（ID、角色、状态）；用 send_agent 向同伴发消息。消息参数只接受 agent_id/message，发送者由 broker 绑定，不能再 spawn 或取消同伴；可用 agent_result 读取已知同伴的返回结果，仍经过对应权限检查。Master 与子 Agent 的消息/查询入口均经过同一权限门禁；plan 模式禁止新建子 Agent 和发送补充任务消息。

子任务完成自动注入 Master 消息箱，终端轮询显示状态并触发 Master 后续处理；一次用户交互最多8轮自动续接，不做无限自循环。Master 返回之前结果已到达时也可在工具轮次读取。Agent 输出作为数据传递，不改变工具权限。

```text
/agents
/spawn Planner 为桌面抓放制定最小计划与验收标准
/spawn Worker 运行一次已有MuJoCo双关节仿真并报告评审证据
/send <ID> 限制：本次只验证仿真，不连接真机
/result <ID>
/stop-agent <ID>
```

普通对话可直接要求“请 Planner 制定计划，随后请 Reviewer 检查计划”。串行依赖由 Master 在取得结果后启动后续任务；没有独立的通用 DAG／chain DSL。并发仅适合独立任务。定时对话保留单次独立上下文，服务端禁止调用 Agent 管理工具，不通过伪造未声明 tool name 绕过。

## 扩展方式

`~/.loop/agents.json` 是用户可信的声明式扩展入口（可由 `LOOP_HOME` 指定目录）；不存在时加载发行默认值 `configs/agents.json`。用户文件整体替代默认角色表，每个角色具有 provider、tools、prompt；provider 限 llm/expert，子任务可授予工具上限为 run_sim/generate_scene/read_file/list_files/search_files。新增角色在下次启动加载。配置不能包含可执行 Python，不能注册 shell、设备控制或递归 spawn。

例如新增一个场景角色可使用 provider=llm、tools=["generate_scene"] 和场景职责 prompt。这只是既有工具的组合，不增加驱动或仿真能力。新增真正工具需修改宿主注册表与 broker 权限，并补行为测试；运行时不会下载／执行未知扩展。

参考 [pi 官方 subagent 示例](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent/examples/extensions/subagent)：它使用独立进程与上下文，支持单任务、并行和链式委派。本项目借鉴其隔离与结果回传方式，未安装、复制或直接嵌入 pi。

[pi 扩展文档](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/extensions.md)支持工具、命令、生命周期事件等注册，也明确扩展拥有宿主权限。本版只实现受限角色扩展，未实现 pi TypeScript API、npm 插件、热重载、完整 TUI、流式事件或会话树兼容。

## 执行边界与恢复

工具授权在父进程 broker 校验，不仅靠模型 prompt。Reviewer 默认无执行工具，只能评审传入内容；需将原始结构化证据传入才能做可靠检查，不能假设它能读取任意 evidence_path。物理验收仍由现有数值 Reviewer／固定规则负责，模型裁判意见不覆盖它。

子 Agent 是独立进程，不是 OS 权限／文件系统沙箱；并发模型请求也不等同本地 GPU 调度。默认子 Agent 只得到所选提供商配置与启动时解析的有效 Key 快照（遵从进程 Key→环境变量→保存凭据优先级），不把 Key 写日志；进程仍继承宿主环境，不能宣称凭据完全隔离。

子任务可强制终止，但取消不回滚已经执行的工具。工具在宿主 broker 串行执行：短仿真通常迅速结束，复杂场景 API 工具可能阻塞监管轮询，执行中的宿主工具尚无独立硬中断。Master 自己的 HTTP 请求也不能立即中断；退出等待当前请求的配置超时，不再开始下一轮。没有实时性保证，不用于真机急停。

事件写 `artifacts/terminal/agents.jsonl`（启动、消息、工具与终止），记录任务、结果和证据，不记录配置／Key。完整上下文和任务恢复不持久化；终端重启不恢复或自动重放子任务。日志目前无轮转。异常退出可能留下部分工具产物，应重新检查而非直接标成功。

## 验证

40项完整环境测试通过，其中新增真实替身子进程：不同 PID、结果隔离、消息边界、并发限制、权限拒绝、取消回收、崩溃与超时。API 使用替身；未运行付费多 Agent 模型调用或真机动作。project-maintenance 同步启动说明、地图与本规范；pi 的可比能力来自上述官方仓库核对。

## 持久执行目标

一次性角色的 done 仅表示该子进程已返回。未验收目标使用独立持久任务监督器：task_submit → 每轮子进程 → 原始回执验收 → 修正或等待。定时器、OS路径事件、配置和进程所有权见 [TASK_RUNTIME](TASK_RUNTIME.md)。


## 并行调度与互相通信（2026-09-07）

Master 按需 `load_toolset(name="agents")` 后，可以连续调用多个 `spawn_agent`。返回 `running` 表示进程已启动，`queued` 表示仍在等待资源；后者不开始计时。轮询按提交顺序重新检查资源，启动前重检当前模式和 deny 规则；已批准的提交不重复要求批准。资源紧张不终止运行中的任务。排队任务可发补充消息、取消；切换模型或配置需先处理运行和排队任务。

`agents_status`／`/agents` 返回 running、queued、max_workers、resources（资源采样、共享预留数、additional_workers、effective_limit 和限制原因），以及排队任务的 waiting_reason。effective_limit 是当前采样下共享范围内的估算额度，不是性能承诺；各运行时和持久任务策略还能设更低上限。

资源配置放 `~/.loop/config.json` 的 `resources` 节，按通常配置优先级合并，下次启动生效。例如：

```json
{"resources":{"max_workers":108,"reserve_ram_mb":1024,"agent_ram_mb":256,"max_cpu_percent":85,"agent_cpu_cores":0.25,"gpu_index":0,"agent_vram_mb":0,"reserve_vram_mb":512,"max_gpu_percent":90}}
```

`max_workers` 支持1..108，也可设20。RAM使用 MemAvailable，CPU使用采样间隔的利用率（首次用 load average 近似），并考虑可读取的 cgroup v2 内存／CPU配额及 CPU affinity；NVIDIA GPU通过限时 nvidia-smi 读取，采样缓存1秒。每个活动进程另预留声明的 RAM／CPU／VRAM估算量，避免采样滞后导致短时间过量启动；这会保守地重复计入一部分已用资源。未知 RAM／CPU 时等待；未知 GPU 在请求显存预算时等待。

远程 API 子 Agent 默认 `agent_vram_mb=0`，显示本地 GPU 采样但不占用本地显存额度。需要本地 GPU 的部署应显式设置每 Agent 显存估计和 gpu_index；这是对指定物理 GPU 的准入检查，不会替模型服务分配设备，也不会合并多张卡的碎片显存。外部模型服务必须自行绑定对应设备。Jetson／非 NVIDIA GPU 缺少 nvidia-smi 时报告不可用，尚无专用遥测后端。

同一 state 目录的前台、后台通过 `resource_leases.sqlite` 原子共享预留，进程结束释放，重启时按 PID 和进程启动标识回收失效记录。不同 state 目录不共享声明额度，但均观察主机占用。这是协作式准入，不是 OS 内存硬限制；不包含服务商 RPM/TPM 限流、自适应请求费用控制或 GPU 模型加载调度。调用方仍应按模型服务配额降低 max_workers。直接使用未传 admission 的 AgentRuntime 保留静态3并发兼容行为。

在 Loop 中可直接提出：

```text
请并行启动 Planner 和 Reviewer，分别分析这个方案的实现步骤与风险；让双方通过 send_agent 交换关键约束，最后由你汇总结果和未验证项。
```

也可显式使用命令：

```text
/spawn Planner 分析我提供的方案，列出最小实施步骤
/spawn Reviewer 独立检查我提供的方案，列出风险与验证项
/agents
/send 实际AgentID 补充约束：只分析，不操作设备
/result 实际AgentID
/stop-agent 实际AgentID
```

角色默认工具范围仍受配置限制（Planner/Reviewer 为分析角色，Worker 的执行工具按原注册表授权）。并行指的是独立模型进程同时工作；宿主工具依然串行，不声称硬件控制或长工具也能并行，重启后不恢复这些一次性子进程。`done` 仍只表示角色返回结果。

新增 `test_agent_ipc` 使用真实 spawn 子进程、ThreadingHTTPServer 和同步屏障证明两个模型请求同时在途；两端通过实际 ChatAgent 工具循环发现彼此、双向投递消息、收取结果并回收进程。另验证发送者伪造、递归 spawn、取消同伴、通信 deny、Master/子Agent同门禁。测试不调用真实供应商或设备。

共享预算已下沉到 core.resources.ResourceManager，Agent 仅是其一个消费者；Node、Python、策略服务、模型池与统一 resource_status 接入见 [资源基础层](RESOURCE_RUNTIME.md)。


## 2026-09-07：通用阅读角色与并发监管稳定性

发行默认角色新增 Reader，授予 read_file/list_files/search_files，使用当前所选模型，可独立进程并行阅读项目。用户已有 agents.json 整体覆盖默认角色，不自动改写；需要 Reader 时按上述三个字段与工具范围加入用户角色配置。每次读取仍经过宿主权限与文件边界，Reader 没有写入或执行权限，不从助手文字推定测试通过。

终端将 broker 轮询与通知锁等待放到一个专用监管线程，主模型仍在既有单线程执行器内，子 Agent 仍是 spawn 进程。慢 broker 轮询不占用终端 asyncio 事件循环；线程间消息与启动保留 RLock。每次 poll 最多处理每个进程16条 IPC 消息，防止单个进程耗尽监管循环。畸形消息只终止对应子进程；工具观察回调异常返回原始结果加 observer_error，避免丢失已执行回执后盲重试。

宿主工具仍串行；这次没有新增并发硬件执行。监管线程是宿主固定一条控制线程，退出时等待回收；线程栈和 Python 调度成本仍属宿主未逐项计量开销，子 Agent 的准入继续使用共享 App.resources。长工具不可硬中断，退出仍可能等待工具；不宣称实时性。验证包括真实进程、多线程提交、坏消息隔离、同伴通信、Reader 工具及观察回调故障。


## 2026-09-07：CLI 与多 Agent 交互补齐

- `/agents` 或 `/agents all` 查看本运行时记录，`/agents active` 只显示 running/queued。Actions 面板按任务标题、角色与稳定 `@1`、`@2` 编号展示并刷新状态。编号在当前运行时单调分配，不随列表排序或结束重新编号；重启后不持久化。旧内部 ID 仍兼容。
- 裸 `/spawn` 打开角色选择，选择后留在输入框继续写任务；裸 `/send` 打开活动 Agent 选择，选中后继续写消息，不发送空任务或空消息。候选展示标题，实际填入稳定编号。`/result`、`/stop-agent`、`/agent-messages` 裸命令也可选目标。`/result` 与 `/agent-messages` 包括已结束记录；发送与取消候选仅包括活动记录。
- `/spawn Reader 阅读会话实现`、`/send @1 重点检查恢复边界`、`/result @1`、`/agent-messages @1`、`/stop-agent @1`。活动前台回合中也可管理或新增子 Agent；这些命令在后台线程调用，继续经过权限与资源准入。
- 每条消息有稳定 message_id；`agent_messages`／`/agent-messages` 查看目标收到的消息，区分 queued、delivered、not_delivered。delivered 仅表示已交给子进程 inbox，不代表模型已处理或任务成功。进程结束时尚未投递的消息标为 not_delivered；日志在当前运行时保留，不声称重启恢复。
- 子 Agent 可通过 agent_result 读取已知同伴的状态和结果，不获得递归 spawn、取消同伴或自批权限。结果中的助手文字仍是数据。
- 修复 slash `/agents`、`/send`、`/result`、`/stop-agent` 直接调用运行时绕过门禁的路径，统一转经 App.tool；新增消息查看同样受控。deny/ask/plan 规则不因交互入口不同而绕过；目录读取禁用时不通过补全暴露任务标题。

实际 PTY 覆盖角色选择后继续输入任务、Agent标题选择后追加消息、投递回执、完成结果与中文流式并行草稿。单元与真实进程测试覆盖固定编号、消息原文保留、未投递标记、同伴结果与拒绝权限、资源排队。尚未实现 Agent 会话恢复、独立 worktree 或依赖图编排。
