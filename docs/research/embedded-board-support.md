# Loop ROS 嵌入式板卡支持边界

核对日期：2026-09-08。问题：ESP32、Arduino、树莓派、香橙派、Jetson 各系列能否支持？初次仅核对源码及官方资料；后续已按用户要求新增 Rust 核心与 ESP32-C3 开发固件，详见 [Rust 端侧核心](../RUST_CORE.md)。未刷写或连接实物。

结论更新：ESP32 不限于某种编程语言；本项目采用 Arduino C++ SDK＋Rust no_std 核心。ESP32-C3 完整固件、C++ ABI 与 RISC-V／Cortex-M0+ 核心库已构建验证，具备直接请求远端模型与板上执行循环的源码实现；Wi-Fi／实际模型／控制仍待板端验收。ZeroClaw 本地快照的现有 ESP 固件是串口外设，不能将其 future 的端侧 Agent 描述当作已实现依据。官方网页现已提供分层安装步骤。

## 结论

应区分运行 Loop CLI、由 Loop 开发固件、通过协议控制设备。品牌不是兼容性单位；以具体型号、CPU 架构、系统镜像、Python 和设备协议为准。

| 板卡类别 | 可行路线（架构推断，非实测认证） | 当前边界 |
| --- | --- | --- |
| ESP32 系列 | 可作外接控制器；新增 C3 开发端侧 Agent，直接通过 Wi-Fi 调用模型 API，Rust 核心驱动工具循环 | C3 编译验证、板上联网待验收；其他 ESP 型号未适配。不能假设各型号都有 Wi-Fi/BLE |
| Arduino UNO R3、传统 Nano、Mega 等 MCU 板 | 上位机开发、编译与上传固件；板端执行控制程序 | 未完成各板型专用适配；MicroPython 不是本项目所需的完整 CPython 环境 |
| 带 Linux 的 Arduino（如 UNO Q 的 MPU 侧） | 按 Linux 主机评估 CLI | MCU 侧仍需独立协议；无板卡实测 |
| 树莓派 Linux 单板机／计算模块 | 满足依赖时在板上运行 CLI，或由外部 Loop 通过 SSH 管理程序 | 优先评估 64 位系统；旧型号、32 位系统及安装器运行时下载需逐项验证；Pico 属于 MCU 路线 |
| 香橙派 Linux 单板机 | 与 Linux 主机相同，按板型选择 Ubuntu／Debian 等镜像 | 不同 SoC、32／64 位及 GPIO／相机／NPU 驱动不能概括为全系列支持 |
| Jetson | 在兼容 JetPack/Linux 环境运行 CLI，或由外部 Loop 管理远程 Node | 不同 JetPack 的 Python／系统基础不同；CUDA、模型服务及机器人 SDK 单独验证。已有 SSH 上下文核验不等于板上 CLI 安装或服务就绪验收 |

CLI 使用远端模型 API 时，不要求板子本地运行大模型或具有 GPU；仿真、模型部署和硬件控制不是 CLI 安装成功的自动结果。继续维持轻量 core：板卡工具链与驱动按需接入，不将所有 SDK 变成默认依赖。此段为设计建议，未实现新的适配。

## 本地证据

- [打包定义](../../pyproject.toml)：运行要求 Python >=3.10；终端依赖 prompt-toolkit，仿真等为可选依赖。
- [平台记录](../PLATFORMS.md)：主要实测为 Linux x86_64，不能推广为 ARM 全系列已验证。
- [串口适配器](../../toolchain/serial_port.py)、[硬件说明](../HARDWARE.md)：已实现枚举、打开、读取、状态、关闭；内置通用串口工具没有发送接口。这不代表通过已有代码执行能力编写厂商客户端不可行。
- [进程 Node](../../toolchain/process_node.py)、[工作流](../PROCESS_NODES.md)：本地／SSH 常驻程序管理已实现；[运行记录](../RUNBOOK.md)有 Jetson SSH 上下文核验，不构成全套部署验收。

## 官方来源

- [Espressif ESP-IDF 入门](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/)：厂商固件配置、构建与刷写路线。
- [Arduino UNO R3](https://docs.arduino.cc/hardware/uno-rev3/)：ATmega328P 微控制器板。
- [Arduino UNO Q](https://www.arduino.cc/product-uno-q)：Linux MPU 与 MCU 并存，说明不能将整个 Arduino 品牌视为单一 MCU 平台。
- [Raspberry Pi OS](https://www.raspberrypi.com/documentation/computers/os.html)：32／64 位系统；[Pico／微控制器文档](https://www.raspberrypi.com/documentation/microcontrollers/)区分其 MCU 产品线。
- [Orange Pi 5 Plus 官方 Wiki](https://www.orangepi.org/orangepiwiki/index.php/Orange_Pi_5_Plus)：示例板型的 Ubuntu／Debian 等系统镜像，不能外推其他系列。
- [NVIDIA JetPack 6.0 DP](https://developer.nvidia.com/embedded/jetpack-sdk-60dp)：该版本的 Orin 范围和 Ubuntu 22.04 基础，仅用作版本差异的例证，不作为最新版推荐。

尚缺各目标板的干净安装、终端交互、退出恢复、实际连接与协议回执。对外适宜描述为“面向 Linux 主机和嵌入式控制器的可扩展接入”，不宣称所有型号开箱即用。
