# Rust 端侧核心

本轮目标（2026-09-08）：参考本地 ZeroClaw 的主机／固件分层，为 Loop ROS 准备可编译的 Rust 端侧核心、ESP32 的 Arduino C++ 接入，以及官网平台安装说明。现有 Python CLI 不被替换；不刷写用户设备。

交付状态：Rust 核心与 C ABI 已实现；ESP32-C3 完整固件已编译并核对镜像格式及 Rust 符号；双语官网安装指南已发布并完成浏览器检查。尚未刷写设备或验证真实模型 API；没有宣称所有 ESP／Arduino 板型就绪。

参考快照：`reference/Agentic/zeroclaw` commit `4129a18ac7f8a52ab2b13095310a41090a81dbf8`。该快照的 `firmware/esp32/README.md` 明确将现有固件定义为串口外设，端侧 Wi-Fi＋LLM 属于 future；`firmware/arduino/arduino.ino` 是 C++ 固件。只参考边界与结构，不复制第三方实现。

## 实现与原有 core 的对应

| 现有语义 | Rust 入口 | 实际范围 |
| --- | --- | --- |
| Session／task 独立身份、工具回执验收 | [agent.rs](../rust/core/src/agent.rs) | 本地注册身份、权限掩码、明确的模型／工具预算、时限、取消、重复与错属回执拒绝；回答不代替执行验收 |
| TaskSpec／Embodiment／Episode／Review、执行反馈循环 | [robotics.rs](../rust/core/src/robotics.rs) | 定长关节数据、目标／模态／身份／标定检查、前后观察、停止、数值评审；保留 simulated-only 边界 |
| 资源与证据存储 | [端口定义](../rust/core/src/lib.rs) | 资源与日志由宿主注入；未来 Python 接入须复用 App.resources，不能另建跨终端账本 |
| Arduino C++ 调用 Rust | [C ABI](../rust/ffi/include/loopros_core.h)、[固件](../firmware/esp32/src/main.cpp) | 128 字节对齐上下文，板上任务循环；C++ 对接 Wi-Fi／TLS／Chat Completions 与只读设备工具 |
| SQLite、长期记忆、Skills、Node 多进程、跨终端租约、完整模型配置 | 现有 Python 宿主层 | 未移植到 MCU，不是完整 Python CLI 的等价替换；Rust host 程序仅为离线回执夹具 |

Rust `core` 无第三方依赖、`no_std` 且不分配堆；网络请求、JSON 和模型历史由 C++ 适配层管理。ESP32 端会直接请求远端模型 API，任务循环和工具执行在板上，无须另一个主机 Agent；不是在 MCU 上运行神经网络推理。

端侧当前提供 device_uptime 与 free_heap 两个只读工具。自然对话完成与 `/task uptime ...` 的实际回执验收分别报告。完整固件仅对 ESP32-C3-DevKitM-1 做了编译，其他 ESP 系列需各自 SDK 与芯片配置；RP2040/Pico 只完成 Cortex-M0+ 核心库交叉编译，传统 Arduino AVR 暂无本项目 Rust 固件。

## 构建与验证

在项目根执行：

```sh
rustup target add riscv32imc-unknown-none-elf thumbv6m-none-eabi
python3 scripts/validate_rust_core.py
pio run -d firmware/esp32 -e esp32c3
```

本机使用 Rust 1.91.1、PlatformIO 6.1.18、espressif32 6.12.0、Arduino ESP32 2.0.17、ArduinoJson 7.4.2。Python 构建工具安装在 artifacts/embedded-tools-venv，未改用户 Python CLI 环境。详细安装、配置及操作者刷写命令见 [固件 README](../firmware/esp32/README.md)。源码与空配置固件仍是本地开发候选，未公开发布为新版本。

- Rust 8 项单测、Clippy（warnings denied）、格式检查通过；主机／RISC-V／Cortex-M0+ 静态库构建通过。
- 真正 g++ 链接 Rust 静态库运行：5 次工具调用、身份拒绝、资源准入、完成与取消通过；Rust host 夹具证明文字未验收时继续工具循环。
- ESP32-C3 最终固件构建通过：静态 RAM 21084／327680 字节，应用 Flash 573648／1310720 字节；firmware.bin 为 598176 字节。静态统计不包含运行时 TLS／JSON 堆。
- `esptool image_info` 校验镜像 checksum 与 validation hash 均有效；ELF 中核对到 11 个实际链接的 loop_core_* 符号。未刷写、未联网验收、未发送电机动作。
- 构建过程修复了构建 venv 缺少 pip、配置宏与状态枚举重名、LLVM 新 RISC-V 属性与旧链接器不兼容的问题。最终在项目 `.pio/modern-tools` 隔离安装 GCC14 工具包，仅用其 ld；保留 Arduino 原 GCC8、SDK 与 libc。未删除 ISA 属性或修改第三方 SDK 源码。官方 SDK 链接脚本的 RWX LOAD 段警告保留在日志中，未关闭诊断。

回执：[核心验证](../artifacts/rust-core-validation.log)、[固件构建](../artifacts/esp32c3-build.log)、[Rust 符号](../artifacts/esp32c3-rust-symbols.txt)、[镜像检查](../artifacts/esp32c3-image-info.txt)。

## 官网与来源

[中文安装说明](https://loopmaster.box2ai.com/LoopROS/zh-CN.html#platform-guide)和[英文安装说明](https://loopmaster.box2ai.com/LoopROS/#platform-guide)已区分已验证 Linux、待原生验收平台、端侧开发版本与未适配 MCU。双语 JS 测试与真实 Chrome 本地／线上 1440、390、320 像素检查通过；发布回执证明原有 0.0.2 wheel、bootstrap、安装脚本和版本清单保持不变。源码私有备份见 [部署记录](DEPLOYMENT.md)。

官方资料核对使用 [Espressif Rust book](https://docs.espressif.com/projects/rust/book/)、[Rust RISC-V 裸机目标](https://doc.rust-lang.org/rustc/platform-support/riscv32imc-unknown-none-elf.html)、[PlatformIO espressif32 6.12.0 清单](https://github.com/platformio/platform-espressif32/blob/v6.12.0/platform.json)、[ArduinoJson 7.4.2](https://github.com/bblanchon/ArduinoJson/tree/v7.4.2)。本地参考源码仅作为结构证据，没有改动或复制第三方实现。
