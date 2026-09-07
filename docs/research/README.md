# 技术调研索引

- [core、源码上传与发行审查及 0.0.3 整改](core-release-review.md)：候选漏件、停止／迁移保护、包导入与发布校验已整改；本地 wheel 安装、旧版更新／回滚和中文 PTY 验收通过，未公开发布。

- [ESP32／Arduino／树莓派／香橙派／Jetson 支持边界](embedded-board-support.md)：区分 Linux CLI 主机、MCU 外设与新增 Rust+C++ 端侧 Agent；[Rust 实现与验证](../RUST_CORE.md)，未宣称全系列实测。

- [机器人能力包的网站分发与复现方案](robot-capability-package-distribution.md)：显式分享、版本化下载与设备绑定，尚未实现分发服务。

- [Agent CLI 源码对照与 Loop ROS 能力补齐](agent-cli-capability-upgrade.md)

- [大模型厂商开源 CLI 与 Agent harness](vendor-open-agent-cli.md)（含 Claude Code 公开内容与许可范围核对）
- [机器人仿真器与 Agent CLI 一体工作台](robot-simulation-agent-ide.md)
- [Python CLI 性能与 C++ 迁移评估](python-cli-performance.md)
- [Fast mode 调研](fast-mode.md)
- [机器人训练库存放与 LeRobot 接入布局](training-library-layout.md)
- [Session／Task／Node 统一工作台与反馈闭环设计](session-task-node-design.md)

- [Loop ROS 沙箱接入可行性](sandbox-runtime.md)：官方机制与当前执行边界核对，设计建议，尚未实现。

- [全系统 Token 计量与节约方案](token-accounting-and-efficiency.md)：已落实三次重新规划；请求账本、后台汇总、预算、用途模型路由、语义标题与渐进检索设计分阶段落地。

- [工作站 Codex／Claude Code 对接机器人端 Loop ROS](remote-robot-debugging.md)：SSH＋MCP 调试方案；现有 MCP 仅仿真，通用常驻运行时网关待实现。

- [端侧多模态感知、ROS 1／ROS 2 与 Agent 协作](ros-sensor-agent-integration.md)：双版本观察／原生包／地图导出已落地，Noetic 回环已验收；ROS 2 DDS、真机与跨机 Agent 协作待验收／实现。
