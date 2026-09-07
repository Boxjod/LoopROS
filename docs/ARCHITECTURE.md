# 架构与实现边界

2026-09-05。本目录是实现权威入口，研究来源保留于 [综合报告](../../projects/reports/06_loopmaster_core_landscape_and_design.md)，不复制第三方仓库或整份研究报告。

## 内核

六对象：TaskSpec、EmbodimentSpec、Capability、Episode、Review、Candidate。
四角色：Body／Environment、Policy／Master、Reviewer、Learner。当前前三者提供确定性模拟实现，Learner 仅留 Candidate 记录，不伪装训练。

Loop 顺序：验证任务与本体 → 记录任务 → 观测 → 检查必需模态 → Master 计划 → 检查范围并持久化动作意图 → 执行 → 再观测 → stop → 持久化 Episode → Reviewer → 持久化 Review → 将反馈交回 Master。pass／inconclusive 停止；fail 仅在明确 reobserve 且预算未耗尽时继续。没有隐式复位。

SQLite 记录元数据；未来视频／高频传感器存外部文件并在 Episode 引用。单个Loop仍同步执行；core/NodeRuntime现可在多个常驻进程中承载独立Loop与状态监测，终端焦点切换不影响后台执行。节点管理与边界见[NODES](NODES.md)。无恢复重放、分布式锁或 exactly-once 承诺。进程崩溃可能留下仅有 intent 的动作，禁止启动后自动重放。

单个Loop的timeout是调用边界检查；NodeRuntime增加独立进程与有界停止回收，但仍不具备真机保护，M1拒绝真实本体。后续仍需要驱动端 TTL／看门狗、控制权租约、传感器新鲜度与停止确认。Python loop 不承担硬实时保护。

## 三层与第二个 loop

1. 上下文／文本记忆：保留任务、观察、反馈；未来接网络搜索，外部内容作为数据而非执行授权。
2. Skill／代码／轨迹：用可版本化插件表达稳定流程；先测试再升级。
3. 模型权重：未来由离线 Learner 消费筛选数据，产生 LoRA／策略候选，不直接修改生产模型。

学习 loop 的目标协议：已评审 Episode → 定位失败类型 → Candidate → 仿真或已授权可复位环境的固定评测 → 旧任务回归 → 门控发布／回滚。M1 实现证据积累、候选记录和 MuJoCo 初始状态 reset；没有完整 manipulation 复位验收、留出 benchmark 或发布器，因此没有真实自进化的性能声明。

当前数值 benchmark 是关节目标达标率与最大误差；不是 manipulation 综合评分。未来 Reviewer 接 Qwen-VL 时保持结构化 verdict／metrics／evidence 引用，数值阈值由程序计算，缺少必需模态为 inconclusive。裁判与测试规约不随候选一起修改。

## 跨端与资源边界

服务器负责可选语言／视觉／策略推理及训练；Jetson／Linux 是完整 runtime 候选；ESP32／STM32 只承载后续 C/C++ endpoint 与本地保护，不运行当前 Python 内核。公共协议需要后续独立版本化；这里的 dataclass 不是已完成的 MCU wire protocol。

ModelPool 已实现单线程 RAM／VRAM 声明预算、load／unload 回调、活动租约保护和闲置 LRU 淘汰；未接实际 GPU 测量或模型后端。它不是操作系统级内存限制器。一个共享 Master 服务可服务多本体，但当前每个 Loop 绑定一个 Body，没有并发多机执行保证。

## 实施顺序

1. 当前交付：可测试的模拟反馈 loop 与证据链。
2. 已接 MuJoCo 双关节物理环境及 reset；继续增加 manipulation 接触／图像证据和冻结任务集。
3. 接一个明确型号的硬件 endpoint，在不放宽保护条件下验收。
4. 接语言／Qwen-VL Reviewer 和检索插件；再基于瓶颈接轨迹技能或训练候选。
