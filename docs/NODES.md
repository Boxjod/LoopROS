# Loop Node：常驻进程与终端切换

2026-09-05。多进程管理属于core：权威入口为 [NodeRuntime](../core/nodes.py)，终端只是管理界面。Node是带名字、职责、状态与命令接口的运行单元；当前实现一node一独立spawn进程。名字可复用，instance_id每次启动改变，PID只表示本次进程。它不是ROS 2节点，也没有DDS或ROS图发现兼容声明。

## 直接运行

`loop node`进入无需API配置的本地节点终端。已有Loop会话直接使用`/node`即可；`/switch`仍专门选择模型服务，`/node use`选择节点。

```text
/node start sim_arm arm
/node start sim_arm arm2
/node list
/node status arm
/node use arm
status
move 0.3 -0.2
status
master
/node logs arm
/node stop arm
/node stop arm2
```

启动返回starting；首次心跳后state=running才可发送命令。move返回command_id及queued，随后status中的results给出对应命令的review。达到目标的证据是review.verdict=pass，而非排队或进程存活。

切到arm后提示符显示`[arm] ❯`。普通输入支持status、move Q1 Q2、logs、stop、master；`/status`、`/joints`、`/move`、`/home`在该焦点下指向该node。其他自由文本提示切回Master，不猜测电机动作。`/node use master`或`master`切回对话。已排队的Master输入固定交给Master，切换不会把旧输入发给新节点。Master正在生成时仍可用`/node`切换和操作节点；节点没有媒体对话能力。

节点随本终端会话存活，切换焦点不停止后台节点，退出终端会回收所有节点。当前不是系统守护服务，其他终端不能attach到该运行时；不持久恢复运行进程、不自动重放或重启运动。已停止节点可用相同start命令手动重新启动，生成新的instance_id。

## 两种已实现节点

| kind | 实际行为 | 边界 |
| --- | --- | --- |
| sim_arm | 独立MuJoCo双关节模型，持续推进物理、保持控制目标、上报q/dq/接触/时间；move执行现有Loop反馈与评审 | 弧度目标；无夹爪、抓放或GUI控制；不是硬实时控制 |
| serial_rx | 独占指定串口，持续读取，报告连接状态、累计字节、最近hex与接收时间 | Linux接收适配；不发送；未知协议不能提供电机角度、健康或型号 |

明确端口与波特率后可用：

```text
/node start serial_rx motor_rx /dev/serial/by-id/你的设备别名 115200
/node use motor_rx
status
master
/node stop motor_rx
```

此例中的端口和波特率是占位与示例，不能作为未知电机默认协议。打开串口的副作用与基本接收能力见[HARDWARE](HARDWARE.md)。本次真实设备只读枚举，node串口收取以PTY验证，未运行真实电机。

## 实现与故障处理

```mermaid
flowchart LR
    T[终端：Master / Node焦点] --> R[core NodeRuntime]
    M[Master工具调用] --> R
    R <-->|有界命令 / 回执 / 心跳| A[sim_arm独立进程]
    R <-->|心跳 / 接收摘要| S[serial_rx独立进程]
    A --> E[Episode / Review]
    S --> E
```

- core仅标准库；可信工厂注册与设备实现位于[插件](../toolchain/node_workers.py)。模型不能提交shell命令或任意模块路径。现有LLM子Agent仍用AgentRuntime管理一次性推理任务，未强行迁移为设备node。
- supervisor独立线程持续收取消息；节点约200ms发布一次心跳，默认3s过期为unresponsive。判定依据包括进程存活与心跳时间，不把旧snapshot当成新观测。
- 每个节点最多一个待完成命令；命令内容上限4096字符，开始执行前检查5s有效期。未知完成结果为inconclusive。节点启动失败或异常退出显示failed；不会把内存中旧结果当成重启后结果。
- 默认最多8个活动节点、64个逻辑名字；同一资源键不能被两个节点占用。串口按解析后的设备路径去重，操作系统锁还用于排除其他串口会话；模拟节点各有独立本体。
- stop先发停止事件，等待500ms；必要时terminate、kill并回收。取消中的动作可能已经部分执行，不能承诺回滚。`/stop`停止模拟节点；`/plan`回收所有node；相关deny规则会回收受影响node。
- node_start和node_command通过统一权限门禁。serial_rx还要求open_serial/read_serial为allow；一次性串口approval不能授权常驻接收。node move要求move_sim为allow，逐命令审批使用node_command规则。定时任务不能启动、控制或停止节点。
- 生命周期和命令记录保存在state-dir/nodes/events.jsonl，内存仅保留100条近期事件；每次运行独立SQLite证据和输出.log。状态结果包含文件路径。serial_rx结束时记录Episode和inconclusive Review，不能将原始接收称作任务成功。强制退出且缺少命令回执时，supervisor追加inconclusive证据。

## 验证范围

已验证Linux真实spawn进程：并行、独占、崩溃隔离、心跳过期、强制停止、重新启动、关闭回收。真实MuJoCo完成目标并保存Episode/Review；真实PTY在子进程接收、断线并保存证据；中文流式Master同时切换节点与控制的PTY屏幕测试通过。入口为[test_nodes](../tests/test_nodes.py)、[test_node_terminal](../tests/test_node_terminal.py)。最终全量结果见[RUNBOOK](RUNBOOK.md)。未验证Windows/macOS上的节点实机运行、真机控制、跨主机通信或后台守护部署。

多载体入口：`--deployment FILE --host ID` 与 `/carrier` 在现有 NodeRuntime 上增加稳定载体身份、主机分配、当前实例校验和请求去重；节点仍由终端持有。见 [DEPLOYMENTS](DEPLOYMENTS.md)。
