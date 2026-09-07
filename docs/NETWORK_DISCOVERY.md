# 本机网络发现：已审核通用模块

状态：2026-09-07 用户明确审核通过，提升为正式源码 `toolchain/network_discovery.py`，允许纳入 commit/push 与发行包。源码实现保持不变；此审核不等同于注册模型工具或授权任何设备操作。

读取 Linux 本机 IPv4 地址、路由、邻居缓存以及 `ROS_MASTER_URI`、`ROS_DISTRO` 环境变量。仅调用 `ip ... show`；不扫描网段、不发起 SSH、不启动 ROS。邻居缓存与 ROS 环境变量不能证明机器人身份或远端运行状态。原 `lan_robot_probe.py` 包含具体网段、源地址和网卡，未纳入通用候选。

要求：Python 3 标准库；运行采集需要 Linux 的 iproute2（`ip` 命令）。无需 root。导入模块不会执行采集。

在项目根执行：

```sh
python -m toolchain.network_discovery
PYTHONPATH=tests python -m unittest test_network_discovery -q
```

已安装发行包可执行 `python -m loop_robot.toolchain.network_discovery`；源码与安装包的 Python 模块名不同。

输出是 JSON。`addresses`、`routes`、`neighbors` 各保留子命令的 `stdout`、`stderr`、`returncode`，其中 `stdout` 是原始 JSON 字符串；命令不存在或超过 8 秒时该项返回 `error`，继续收集其他项。顶层进程退出码 0 表示报告已生成，采集是否成功必须检查每项回执。两个 ROS 字段缺失时为 null。

运行输出可能包含本机 IP、MAC 与网络拓扑，审查源码不需要附上实际输出。本工具不推断 Jetson 型号或机器人连接能力。

2026-09-07：本地三项 `ip` 读取成功，输出 JSON 可解析；单元测试覆盖只读参数、命令缺失、超时及导入不执行。未验证远端、ROS 节点或其他操作系统。

专项测试位于 `tests/test_network_discovery.py`。当前是可直接调用的通用模块，尚未加入模型工具 schema。
