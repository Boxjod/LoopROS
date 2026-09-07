# 飞特舵机包与终端诊断

2026-09-06。实现：[toolchain/feetech.py](../toolchain/feetech.py)，终端入口：[terminal/feetech.py](../terminal/feetech.py)。模块随 loop-ros 包分发，无需克隆参考项目；导入不连接设备。厂商相关逻辑不进入 core。

## 使用

在项目虚拟环境安装可选依赖：`python -m pip install '.[feetech]'`。当前 `.venv` 已实际安装 pyserial 3.5；可用 `.venv/bin/python -m toolchain.feetech environment` 检查实际解释器。安装包后模块路径为 `loop_robot.toolchain.feetech`。

终端工具：

- `devices`：枚举实际接口，USB 标识不能证明电机型号。
- `feetech_environment`：检查当前 Python 的依赖和实现边界，不访问网页证明安装。
- `feetech_scan`：指定 port，可指定 ids/baudrates。默认 ID 1–20、八档波特率，优先 1,000,000；最多 20 秒，响应取消。可显式扫描 ID 0–253，超时后按需要缩小范围继续。没有响应只否定本次范围，不否定电机存在。
- `feetech_read`：根据探测出的 port、motor_id、baudrate 读取状态。仅型号编号 777 按 STS3215 表解码；未知型号不猜位置寄存器。

自然语言请求由模型按需加载robotics工具组，先调用devices确定端口，再调用feetech_scan；不再通过“检测/执行”等句式直接启动扫描。工具调用均受权限控制，plan 和后台持久任务禁止扫描/读取，诊断报告及 Episode/Review 写入当前 state_dir/feetech。打开 receive-only 串口后需先关闭，独占端口不能被扫描器抢占。

独立 Python 诊断入口（把端口换成实际枚举值）：

```sh
.venv/bin/python -m toolchain.feetech scan --port /dev/ttyUSB0 --ids 1 2 3 --baudrates 1000000
.venv/bin/python -m toolchain.feetech read --port /dev/ttyUSB0 --id 1 --baudrate 1000000
```

独立入口向 stdout 输出真实 JSON，便于外部 host 保存；Loop 终端入口另写持久化证据。上述命令会发送二进制 PING/READ 查询字节，但不写控制寄存器、不使能、不移动。这与完全被动接收不同。不要用 `?`、`PING\r\n`、PWM 极限位置 ASCII 指令试探总线舵机。打开时请求 DTR/RTS 为低；不同操作系统/转接器可能存在打开瞬态，未做跨平台电气实测。

## 控制原语与边界

`Bus.move_position(id, target, speed, limits=PositionLimits(...), request_id=...)` 是供可信机器人 Host 集成的 STS3215 位置控制原语，不是终端模型工具。限位、步长和速度来自本机已核实配置，不能把示例当作实际机械臂标定。

它串行持有总线，现读型号、工作模式、使能和位置；仅支持已使能的位置模式。验证绝对位置与相对步长后单次发送目标位置/运行时间零/速度，不自动使能、不改 ID/波特率/EEPROM、不重试写入。同一连接中的 request_id 去重，参数冲突拒绝，回执丢失记为不确定；会话重启不提供持久化 exactly-once 保证。协议 ACK 只证明命令接受，不证明最终到位。

尚未实现整臂关节映射、可信标定导入、独立 watchdog、实体停止与到位验收，因此终端仍不开放真机运动；也未接入 carrier/node 真机工厂。调用底层控制原语的 Host 必须先补这些能力。未对用户电机做扫描或运动，本轮真实串口验证使用 Linux PTY 虚拟舵机。Windows/macOS 仅使用 pyserial 兼容路径，未做实机验证。

## 来源和差异

本地参考 `/home/boxjod/lerobot-kinematics`，commit `cc9cb4141df57315602adb6f30c80cb9a712332d`，核心参考 `lerobot_kinematics/lerobot/feetech.py`。其 `p_servo.py` 是笛卡尔视觉伺服算法，不是飞特串口驱动。没有修改参考 clone，也没有复制 NumPy/tqdm/机械臂运动学依赖。

参考采用协议 0、1 Mbps 与按寄存器读取。它的旧表将 SCS/STS 混用，不能直接推广到所有飞特型号；本实现将完整状态与控制限定到 STS3215。

交叉依据：[LeRobot Feetech 型号表](https://github.com/huggingface/lerobot/blob/main/src/lerobot/motors/feetech/tables.py)、[Feetech STS3215 产品规格](https://files.seeedstudio.com/wiki/reComputer-Jetson/lerobot/STS3215-C001-20230624.pdf)。来源不是当前连接设备的身份证据。

## 验证

`LOOP_TASK_AUTOSTART=0 PYTHONPATH=/tmp/looper-terminal-validation .venv/bin/python -m unittest tests.test_feetech -v`：真实 pyserial + PTY 协议往返，回显/坏帧拒绝、未知型号、取消、受限写入与不确定回执去重、终端权限与证据、重复网页调用拦截。pytest 或模型输出不代替硬件验收。

验证结果：相关 48 项测试通过，pip check 通过。全量首轮 295 项运行中，同一终端面板测试的两个尺寸出现时序失败；单独复跑该测试通过，首轮日志保留，不将其称为全量通过。日志在 `artifacts/feetech/`。

项目目录外已验证：`/home/boxjod/Workspace/box2net/LoopROS/.venv/bin/python -m loop_robot.toolchain.feetech environment`，因此模块调用不依赖当前目录名称。当前运行中的旧终端需正常退出后重新启动以加载新工具；不自动中断现有会话。

2026-09-06 后续：补齐 Python 执行工具和外层 `feetech_baud_scan.py` 兼容入口；详情见 [PYTHON_EXECUTION](PYTHON_EXECUTION.md)。飞特扫描后的“你帮我执行”可承接最近用户诊断请求，不依赖旧助手声称的动作。
