# ROS 2 为主、ROS 1 兼容的运行接入

2026-09-08。实现入口：[ros_node.py](../toolchain/ros_node.py)、[ros_host.py](../toolchain/ros_host.py)、[Node 工具](../terminal/nodes.py)。这是可运行的传感器／原生包接入层；跨机器 Agent 对话协议、导航控制器与具体硬件驱动仍由对应工程提供。

## 架构与依赖

```text
Loop Agent → node_start / node_status / node_command / node_stop
                    ↓ PermissionGate + NodeRuntime + App.resources
               ROS Node 管理进程
                 ├─ 独立 ROS host：rclpy（默认）或 rospy
                 └─ 可选原生前台程序：ros2 launch / roslaunch / 厂商包
```

ROS SDK 按需在独立 host 导入。Loop 使用自己的 Python ≥3.10，host 可使用 ROS 工作区的 Python ≥3.8，已实测 Noetic Python 3.8。导入 Loop 不连接 ROS。两种适配器输出同一摘要，不依赖 ros1_bridge；这不自动桥接两个 ROS 网络或转换自定义消息。

Node 接入既有资源准入、运行槽、跨终端资源归属和权限撤销。相同 launch／显式环境／版本组合有相同资源标识，防止重复启动同一配置；它不是驱动级设备独占。现有 Node 预算覆盖这一工作负载的准入，ROS host、原生算法、DDS、消息反序列化及子进程的独立 RAM／GPU 成本尚无精确估算。不要把摘要限长当成底层驱动资源上限。

## 使用

先在启动 Loop 的 shell 中 source 对应 ROS 发行版和工作区，再启动 `loop`。配置里的 `python` 必须能导入该环境的 `rclpy` 或 `rospy`。也可通过 `env` 显式给每个 Node 设置 ROS 环境变量、Python／动态库路径、ROS_DOMAIN_ID 或 ROS_MASTER_URI，让两个版本使用独立环境。不会自动安装 ROS、自动启动 ROS 1 master 或搜索机器人地址。

按实际 topic 修改并保存个人配置到 `~/.loop/ros/`，或机器人项目目录。发行示例：

- [ROS 2 多模态观察](../configs/ros/ros2-observer.example.json)
- [ROS 1 观察](../configs/ros/ros1-observer.example.json)
- [ROS 2 SLAM Toolbox 启动与观察](../configs/ros/ros2-slam.example.json)

Loop 内执行：

```text
/node start ros sensors ~/.loop/ros/robot.json
/node status sensors
/node export_map sensors map
/node status sensors
/node stop sensors
```

同样可由 Agent 调用 `node_start(kind="ros", config=...)`，无需特定自然语言句式。启动返回后常驻采样不占用模型循环；`node_command(action="export_map", arguments={"name":"map"})` 返回 command_id，随后检查同 ID 的 result。启动和导出复用 `node_start`／`node_command` 门禁，运行外部解释器／程序还要求 `run_python=allow`；plan 保持禁止执行。此权限是宿主代码执行权限，不提供硬件隔离。

`launch` 可省略以只订阅已有程序。设置时仅接受显式 `argv` 与绝对 `cwd`，直接启动前台子进程；环境由 ROS Node 提供，不自动拼 shell、source 或增加后台符号。SLAM 示例需要本机安装 slam_toolbox、实际 `/scan` 与 `/odom`、适用的 TF 和参数；按设备调整 `slam_params_file`。ROS 1 可把 launch.argv 换成现有 ROS 1 包的 roslaunch 命令，观测接口不变。算法仍在原生包中运行。

运行时向 host 和可选程序的进程组发送 SIGINT（Windows 为 CTRL_BREAK），不自动升级 TERM／KILL。超时 Node 保持 `stopping`、进程与资源归属，不报告已停；再次查询／停止可等待正常退出。未退出的 ROS Node 使用非 daemon worker，关闭 CLI 可能继续等待，不能靠退出绕过停止回执。配置中的启动器也必须遵守设备停止约定：第三方 roslaunch 等内部对子节点的停止策略由其自身控制。进程退出不证明电机失能。这个 Node 用于管理本机前台进程，不用 SSH 命令退出推断远端已停止。

## 数据契约

| kind | ROS 消息（两版本同名接口） | 给 Agent 的摘要 |
| --- | --- | --- |
| joints | sensor_msgs/JointState | 名称、位置；单位取决于 URDF 关节类型 |
| force | geometry_msgs/WrenchStamped | N、Nm；保留测量坐标系，不自动转系 |
| imu | sensor_msgs/Imu | 姿态、角速度、加速度、姿态是否可用 |
| scan | sensor_msgs/LaserScan | 有效光束数、最近／最远距离 |
| image | sensor_msgs/Image | 尺寸、编码、字节数，不上传像素 |
| points | sensor_msgs/PointCloud2 | 点数、字节数，不上传点云 |
| odom | nav_msgs/Odometry | 位姿、速度、父／子坐标系，不证明定位质量 |
| map | nav_msgs/OccupancyGrid | 尺寸、分辨率、原点；可导出栅格 JSON |
| audio | audio_common_msgs/AudioData | 字节数，编码由发布者定义；需另装兼容消息包 |
| tactile | std_msgs/Float32MultiArray | 最多 256 个值，单位／标定由发布者定义 |

音频／触觉是明确的传输适配，不代表已经实现语音识别、接触推理或所有厂商消息。可选 topic 的 `required:false` 只影响 readiness，消息包仍须安装。默认示例未启用 audio，避免缺少额外消息包使启动失败。

每项保留源时间戳、frame_id、本地 monotonic 接收时刻、Unix 接收时刻、接收计数、age_s 和 `missing/fresh/stale/invalid` 状态。坏帧立即取代上一帧有效状态。时钟域标注 ros1／ros2；source_freshness 固定为 not_verified，不拿本地到达新鲜度证明原始采样新鲜、时钟同步或 TF 有效。

ROS 2 队列深度为 1；`sensor` 是 best-effort/volatile，`reliable` 是 reliable/volatile，`latched` 是 reliable/transient-local（地图默认）。ROS 1 使用 queue_size=1 并由发布者的 latch 机制保留地图；qos 字段不改变 TCPROS 协议。

至少一个 required 观测存在且所有 required 观测 fresh 才返回 observations_ready；没有消息、失效、过期或 host 心跳过期均不能证明就绪。此回执仅说明配置所需消息已到达，task_success 始终 not_evaluated。TF 连通性、回环质量、地图一致性、导航效果需另行验收。

摘要通过本地原子 JSON 文件每约 0.2 秒更新；跨机器上层可以按需读取这些有来源的回执，不需要传输每帧原始数据。图像／声音／点云目前提供元数据，不保留可回放缓存。地图最多保留一个最新地图、最多 400 万栅格；export_map 仅导出 fresh 缓存，每次生成独立文件，格式 loop.occupancy_grid.v1，包含观测元数据与原始占据值数组。它不是 Nav2 的 YAML/PGM 或 SLAM Toolbox 的序列化 pose graph。

## 验证与边界

离线测试：` .venv/bin/python -m unittest tests.test_ros_runtime tests.test_nodes.NodeRuntimeTests tests.test_process_nodes -v`。覆盖双版本 API 适配夹具、QoS、时间／坏帧、新鲜度、摘要边界、独立 host、原生程序 SIGINT、超时保留归属、CLI 与权限，以及旧 Node 回归。

Noetic 原生通信：`LOOP_TEST_ROS1=1 .venv/bin/python -m unittest tests.test_ros1_integration -v`。测试创建独立 loopback master 与夹具发布者，读取真实关节／latched 地图消息、导出并核对栅格数据、正常停止并检查 PID 消失；不接既有 master 或机器人。2026-09-08 已通过。

本机没有 ROS 2 安装；rclpy 适配做了接口夹具验证，未做真实 DDS 通信。SLAM Toolbox 示例参数来自[官方 launch 文件](https://github.com/SteveMacenski/slam_toolbox/blob/ros2/launch/online_async_launch.py)，未运行算法或验证真实传感器。ROS 2 与具体机器人的部署需要后续环境实测，不能用 ROS 1 测试替代。
