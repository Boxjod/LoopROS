# Master 与多 Agent 运行时

2026-09-05。终端是 UI，用户对话对象固定为 **Master Agent**。Master 是宿主中的独立命名会话、不是又一个机器人控制器；本版在单后台线程中运行 Master，子任务则在独立 Python 进程运行。没有宣称 Master 本身也是独立 OS 子进程。

```text
用户终端 → Master（Qwen，会话上下文）
               ↓ 启动／消息／取消
          AgentRuntime（进程监管、授权、事件）
               ├─ Planner：计划，无执行工具
               ├─ Worker：MuJoCo 执行工具
               ├─ Reviewer：只分析提供的证据
               └─ Expert：当前用户配置的模型，复杂推理（与其他角色共用模型和凭据）
               ↑ 结果／失败／证据路径
             Master 继续协调或汇总
```

默认角色不是每次都全部调用：简单问题 Master 直接回答，只有可分工任务才启动子 Agent。角色可多实例；默认最多3个并行子任务、180秒/任务、100个子任务/终端会话。子 Agent 各自拥有有限聊天上下文，不继承 Master 的全部历史；输入只包含委派任务与后续显式消息。

## 通信与控制

Master 的工具：spawn_agent、agents_status、agent_result、send_agent、cancel_agent。返回子任务 ID 不表示完成；结果状态区分 running/done/failed/cancelled/timed_out。子 Agent 的 done 表示该角色完成回复，不能等同物理任务 pass。

消息通过宿主 broker 和 Pipe 传递；sender 由宿主绑定，子 Agent 无法冒充 Master。每任务最多16条、每条2000字符，在下一次模型调用边界读取；排队确认不是已读取保证。运行中可追加，已终止任务不可续写，需要新任务携带必要结果重新委派。子 Agent 可用 send_agent 向已知 ID 的运行中同伴发送消息，但不能再 spawn 或取消同伴。

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

`agents.json` 是本项目可信的声明式扩展入口，每个角色具有 provider、tools、prompt；provider 限 llm/expert，子任务可授予的执行工具上限当前为 run_sim/generate_scene。新增角色在下次启动加载。配置不能包含可执行 Python，不能注册 shell、设备控制或递归 spawn。

例如新增一个场景角色可使用 provider=llm、tools=["generate_scene"] 和场景职责 prompt。这只是既有工具的组合，不增加驱动或仿真能力。新增真正工具需修改宿主注册表与 broker 权限，并补行为测试；运行时不会下载／执行未知扩展。

参考 [pi 官方 subagent 示例](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent/examples/extensions/subagent)：它使用独立进程与上下文，支持单任务、并行和链式委派。本项目借鉴其隔离与结果回传方式，未安装、复制或直接嵌入 pi。

[pi 扩展文档](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/extensions.md)支持工具、命令、生命周期事件等注册，也明确扩展拥有宿主权限。本版只实现受限角色扩展，未实现 pi TypeScript API、npm 插件、热重载、完整 TUI、流式事件或会话树兼容。

## 执行边界与恢复

工具授权在父进程 broker 校验，不仅靠模型 prompt。Reviewer 默认无执行工具，只能评审传入内容；需将原始结构化证据传入才能做可靠检查，不能假设它能读取任意 evidence_path。物理验收仍由现有数值 Reviewer／固定规则负责，模型裁判意见不覆盖它。

子 Agent 是独立进程，不是 OS 权限／文件系统沙箱；并发模型请求也不等同本地 GPU 调度。默认子 Agent 只得到所选提供商配置与进程内 Key，不把 Key 写日志；进程仍继承宿主环境，不能宣称凭据完全隔离。

子任务可强制终止，但取消不回滚已经执行的工具。工具在宿主 broker 串行执行：短仿真通常迅速结束，复杂场景 API 工具可能阻塞监管轮询，执行中的宿主工具尚无独立硬中断。Master 自己的 HTTP 请求也不能立即中断；退出等待当前请求的配置超时，不再开始下一轮。没有实时性保证，不用于真机急停。

事件写 `artifacts/terminal/agents.jsonl`（启动、消息、工具与终止），记录任务、结果和证据，不记录配置／Key。完整上下文和任务恢复不持久化；终端重启不恢复或自动重放子任务。日志目前无轮转。异常退出可能留下部分工具产物，应重新检查而非直接标成功。

## 验证

40项完整环境测试通过，其中新增真实替身子进程：不同 PID、结果隔离、消息边界、并发限制、权限拒绝、取消回收、崩溃与超时。API 使用替身；未运行付费多 Agent 模型调用或真机动作。project-maintenance 同步启动说明、地图与本规范；pi 的可比能力来自上述官方仓库核对。

## 持久执行目标

一次性角色的 done 仅表示该子进程已返回。未验收目标使用独立持久任务监督器：task_submit → 每轮子进程 → 原始回执验收 → 修正或等待。定时器、OS路径事件、配置和进程所有权见 [TASK_RUNTIME](TASK_RUNTIME.md)。
