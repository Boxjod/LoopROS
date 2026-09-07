# 机器人仿真器与 Agent CLI 一体工作台

检索日期：2026-09-07。问题：是否存在类似 Cursor、左侧机器人仿真画面、右侧 Agent CLI 的工具？

## 结论与边界

已有接近的产品与开源组合；本轮没有确认某个成熟产品原生提供完全相同的左右布局及嵌入式 Agent 终端。不能据此断言市场空白。仅核对官方网页与作者仓库，未安装、登录或实测界面及任务成功率。

| 候选 | 已公开能力 | 与需求的距离 |
| --- | --- | --- |
| Principia Agent | 自然语言生成机器人场景、物理配置、控制代码与实验验证；官网列出 Isaac Sim、MuJoCo、Genesis，以及本地 CLI 和云端入口 | 工作流接近；同窗分屏与实际闭环质量未验证 |
| FloMotion | 三维机械设计、内置助手、浏览器物理运动仿真；桌面版通过 CLI 让外部 coding agent 操作窗口并取得截图和仿真输出 | 一体工作台接近；外部 Agent 在自己的终端运行，不能称为已确认内嵌终端。Motion 为 Beta，世界生成和强化学习标为 Coming soon |
| Isaac Sim + 社区 MCP + Cursor/Agent CLI | 作者仓库提供自然语言建场景、机器人操作、仿真和状态观察工具 | 可组合出双窗口并排工作流；不是原生统一 IDE |

NVIDIA 官方 Isaac Sim MCP 的公开工具主要检索扩展、示例、设置和开发指导，需与社区实时操控 MCP 区分。

## 来源

- [Principia Agent 官网](https://principia.cloud/agent)：产品能力与 CLI/云端入口；网页直接提取不稳定，能力依据搜索引擎收录的该官方页面。
- [FloMotion 官网](https://flomotion.app/)：工作台与桌面接入概述。
- [FloMotion 外部 Agent 指南](https://flomotion.app/article/coding-agent-of-choice)：发表于 2026-09-05，窗口与 CLI 的联动方式。
- [FloMotion Motion](https://flomotion.app/features/motion)：Beta 与 Coming soon 边界。
- [社区 Isaac Sim MCP 作者仓库](https://github.com/whats2000/isaacsim-mcp-server)：实时仿真控制与 IDE 接入。
- [NVIDIA 官方 MCP README](https://github.com/NVIDIA-Omniverse/kit-usd-agents/blob/main/source/mcp/isaacsim_mcp/README.md)：官方知识检索工具的范围。

## 对 Loop ROS 的推断

“仿真器 + Agent”已有同类方向。若评估产品定位，应进一步比较共享场景状态、修改后运行、回执反馈与纠错的实际连续体验；单凭左右分屏不足以判断差异化。本轮未修改产品代码，也未启动仿真。

## 开源状态补充（2026-09-07）

- **Principia Agent：CLI 开源，Apache-2.0。** [作者仓库](https://github.com/principia-cloud/principia-cli) 的 README 明确标注许可证，并说明基于 Cline；不能由此推定 Principia Cloud 整个平台开源。
- **FloMotion：确认官方声明桌面外壳与 CLI 开源、MIT。** [官网](https://flomotion.app/) 与[接入指南](https://flomotion.app/article/coding-agent-of-choice) 指向 [flomotion-desktop](https://github.com/flomotion-app/flomotion-desktop)。指南明确其为 Web 客户端的桌面外壳，不能视为整套 CAD、仿真及云端后端全部开源。本轮 GitHub 页面抓取失败，未独立核验该仓库 LICENSE，许可证依据官方声明。
- **社区 Isaac Sim MCP：开源，MIT。** [仓库](https://github.com/whats2000/isaacsim-mcp-server) 与 [LICENSE](https://github.com/whats2000/isaacsim-mcp-server/blob/main/LICENSE) 可访问。开源范围是 MCP 服务与仿真扩展，组合中的各工具分别判断。
- **Isaac Sim 自身也有[官方公开源码仓库](https://github.com/isaac-sim/IsaacSim)。** 仓库仍依赖 Omniverse Kit SDK、扩展与工具，不据源码公开推定全部依赖采用相同许可证。

验证状态：仅在线核对 README、官方声明与可访问的许可证页面；Principia LICENSE 原文抓取失败，其许可证由仓库 README 与官网交叉确认。未克隆、安装或运行第三方代码。

## 本地参考源码（2026-09-07）

已将四个仓库浅克隆至 [reference/Robot_CLI](../../reference/Robot_CLI/README.md)，origin、HEAD、干净工作区和 Git 对象完整性均通过检查；未下载 LFS 大对象、初始化子模块、安装依赖或运行仿真。固定提交见 [sources.json](../../reference/Robot_CLI/sources.json)。

本地源码补充核实：Principia LICENSE 为 Apache-2.0；FloMotion Desktop LICENSE 为 MIT，README 明确托管 Web 客户端闭源，消除了此前网页抓取失败造成的不确定性。

## Loop ROS 借鉴与嫁接评估（2026-09-07）

范围：对 sources.json 中四个固定提交与当前 Loop ROS 工作区作定向源码比较。上游 Skill 作为研究材料阅读，没有加载其运行指令、启动仿真或修改第三方仓库。用户问题按评估处理，本轮不实施接入。

### 已有基础与优先级

| 候选 | 上游权威入口 | Loop 现状、建议与接入方式 |
| --- | --- | --- |
| Skills 格式兼容，P0 | [Isaac 技能索引](../../reference/Robot_CLI/IsaacSim/skills/SKILLS.md) | [terminal/skills.py](../../terminal/skills.py) 已按简介发现、按需读取，但不是完整 YAML 解析。先兼容常见多行简介或在导入阶段规范化；目录包及相对引用需保留，不只复制 SKILL.md。 |
| 场景布局与资产测量，P1 | [usd-pipeline](../../reference/Robot_CLI/IsaacSim/skills/usd-pipeline/SKILL.md)、[spatial-reasoning](../../reference/Robot_CLI/IsaacSim/skills/spatial-reasoning/SKILL.md) | [composition.py](../../toolchain/composition.py) 已有 geom_bounds、surface、资产偏移/支撑放置、命名空间及序列化验证。借鉴“占位布局→测量真实资产→替换→观察→修正”流程；MuJoCo 版本调用现有工具，USD API 不直接复制到 MJCF 路径。 |
| 视觉与语义验收，P1 | [validator](../../reference/Robot_CLI/IsaacSim/skills/isaac-sim-validator/SKILL.md)、[截图脚本目录](../../reference/Robot_CLI/IsaacSim/skills/isaac-sim-remote/scripts) | compose 已编译实际序列化资产并跑 100 步 smoke，报告明确 semantic_verdict=unverified、task_success=not_evaluated。补充画面及场景关系验收：可见对象、相机视野、支撑关系、穿透、按任务指定的稳定性阈值。截图与数值回执绑定同一实例、场景哈希、仿真时刻。 |
| Isaac 实时操作，P2 | [isaac-sim-remote](../../reference/Robot_CLI/IsaacSim/skills/isaac-sim-remote/SKILL.md)、[isaacsim_send.py](../../reference/Robot_CLI/IsaacSim/skills/isaac-sim-remote/scripts/isaacsim_send.py) | 官方 Python socket 路径可作为小规模原型；需已安装运行环境及启用扩展。先 health/stage/inspect/capture，再进入创建和执行。脚本远程执行仍需 Loop 权限、实例归属、超时与实际完成回执，不能把 TCP 端口开放或异步 ACK 当任务成功。 |
| Isaac 结构化工具，P2 | [simulation handlers](../../reference/Robot_CLI/isaacsim-mcp-server/isaac.sim.mcp_extension/isaac_sim_mcp_extension/handlers/simulation.py)、[版本 adapters](../../reference/Robot_CLI/isaacsim-mcp-server/isaac.sim.mcp_extension/isaac_sim_mcp_extension/adapters) | 社区 MCP 提供 step 后选择性观察对象/关节、标注关节读数来源、API 版本适配。Loop [viewer_control.py](../../toolchain/viewer_control.py) 已暂停单步并返回 qpos/qvel/接触数/姿态；可借鉴按对象裁剪和来源标签，避免重复做已有单步能力。Isaac 作为独立可选 toolchain 后端，core 不引入 pxr/Isaac 依赖。 |
| MJCF/URDF → USD，P2 | [转换 Skill](../../reference/Robot_CLI/IsaacSim/skills/urdf-mjcf-to-usd-conversion/SKILL.md)、[articulation](../../reference/Robot_CLI/IsaacSim/skills/usd-articulation/SKILL.md) | 在安装版本核对 importer 后，把现有机器人资产转换成 Isaac 可读 USD；保存来源、单位、关节/执行器语义和转换参数。验收自由度、限位、质量/惯量、关节响应；格式成功转换不证明两个引擎动力学等价。 |
| 分层 USD 与按需加载，高级/后续 | [usd-composition-architecture](../../reference/Robot_CLI/IsaacSim/skills/usd-composition-architecture/SKILL.md) | 将几何、物理、外观拆层并使用 references/payloads/variants；便于 Agent 修改参数、复用大资产、按任务减少外观加载。适用于 Isaac 路径；不要强制重写现有 MuJoCo 场景存储。性能收益需在实际场景测量。 |
| GUI 与 CLI 一致状态，后续 | [FloMotion bridge.rs](../../reference/Robot_CLI/flomotion-desktop/src-tauri/src/app/bridge.rs)、[protocol.rs](../../reference/Robot_CLI/flomotion-desktop/src-tauri/src/ipc/protocol.rs) | 可借鉴 request ID、ready 状态、响应关联和超时清理。不能由桥接自动获得其闭源 Web 客户端的 CAD/仿真功能；也不必为了参考引入整套 Tauri/Rust。 |

### 实际验证的接入障碍

使用 Loop 自身 `terminal.skills.discover` 只读扫描 `reference/Robot_CLI/IsaacSim/skills`：发现 25 个顶层技能，其中 22 个 description 被解析成单独的 `>`。原因是 `_frontmatter` 逐行取冒号右侧，没有展开 YAML block scalar。故“文件被发现”不等于“简介可用于模型选择”。未修改解析器。

Principia 当前 checkout 内 `SKILL.md` 文件数为 0。它有通用 use_skill 机制、机器人角色和模拟器环境探测（[system_info.ts](../../reference/Robot_CLI/principia-cli/src/core/prompts/system-prompt/components/system_info.ts)），但本轮未发现可直接拿来的 MuJoCo 场景创建 Skill 包。不能将其 README 的多模拟器宣传推定成已包含专用技能。Loop 已有通用 coding agent/Skills，整体搬 Cline 派生运行时价值有限。

### 上游规则需要筛选

Isaac 技能索引注明部分 robotics-sim 内容来自 isaac-claw。公开库里的规则不自动成为 Loop 全局约定：

- validator 包含脚本 >1KB、图片 >=150KB、固定两类灯、至少 3 个机器人或 50 个资产等经验阈值，不适合作为任意用户场景的验收标准；简单正确场景可能被误判。
- spatial-reasoning 混有特定仓库布局、资产尺寸和截图字节数的经验；借鉴测量方法，不能把这些常量当通用物理事实。
- 将物体按轨迹设置 USD transform/timeSamples，或用 FixedJoint 模拟抓取，不等于通过接触物理完成导航/夹持；具体策略必须明确实现方式及验收层级。
- 不引入上游“每轮自动蒸馏/自动启动/强制换 solver”等全局行为。保留 Loop 的按需工具、已有 profile、plan/sim/real、任务成功证据与流程晋升门槛。

### 推荐最小落地顺序（方案，未实施）

1. 修正/规范化 Skill 元数据兼容，适配少量场景技能到完整包。针对真实上游多行 description、目录相对引用、重复名称和损坏元数据做验证；直接验证入口是 [test_skills.py](../../tests/test_skills.py)。
2. 先做 MuJoCo 场景工作流：复用 compose_scene/model_library/simulator_control，补充按当前实例捕获画面与任务语义检查。案例为桌上机械臂、地面障碍物、错误尺度资产；验证实际尺寸/支撑/物体数及失败修正，保护 [test_composition.py](../../tests/test_composition.py)、[test_simulator_control.py](../../tests/test_simulator_control.py) 已有边界。
3. 加可选 Isaac 工具桥，先实现创建桌面+导入机械臂+查询姿态+暂停单步+截图的闭环；固定已验证运行版本，拒绝不支持项。随后加入 MJCF/URDF 转换与资产层复用，避免一次铺满 42 个工具。
4. 有真实需求再接合成数据、深度/分割传感器与性能剖析；这是新增工作流，不随场景创建自动启动训练或收集数据。

建议技能包名称（尚未创建）：`mujoco-scene-builder`、`simulation-scene-review`、`isaac-scene-builder`；转换可先作为 Isaac 包的按需 references/scripts，达到独立工作流规模再拆包。用户定制安装位置按 [USER_HOME](../USER_HOME.md) 为 `~/.loop/skills/`，reference 保留上游原样。采用代码时逐文件保留来源及许可证；Isaac 根 LICENSE 为 Apache-2.0，额外 SDK/资产条款另列，MIT 桥接项目不覆盖依赖条款。

结论性质：代码入口、解析行为和上游规则为已核对事实；优先级与架构方案为工程判断。仅运行只读技能发现实验；未执行上游脚本、仿真、性能或跨引擎等价性测试。

## 实施补充（2026-09-07）

用户随后明确授权执行。新增 Loop 原生／MCP 共用的独立 MuJoCo、Isaac 工具桥、多相机与学习数据接口，详见 [实施与使用](../SIMULATION_WORKBENCH.md)。此前“本轮不实施／未运行仿真”描述对应前面的评估阶段；现已在本机 MuJoCo 3.12.0 和 Isaac 4.5.0 上进行有界运行验证。

新增参考 [Boxjod/RLBench_ACT](https://github.com/Boxjod/RLBench_ACT)：[数据采集器](https://github.com/Boxjod/RLBench_ACT/blob/master/RLBench/tools/dataset_generator_hdf5.py)、[ACT 数据读取](https://github.com/Boxjod/RLBench_ACT/blob/master/act/utils.py)。借鉴 task/variation、多相机 HDF5 和未来动作分块；Loop 使用明确的动作前观测／下发控制／动作后状态契约，不将下一帧关节位置无条件视为任意引擎的控制动作。当前是格式与工作流接入，不是完整 RLBench 任务库或预训练 ACT 模型兼容认证。

Isaac 相机触发依据本机官方 `standalone_examples/replicator/scene_based_sdg/scene_based_sdg.py` 和 `object_based_sdg/object_based_sdg.py` 的 `rep.orchestrator.step(delta_time=0.0)`，已验证在暂停物理时间时输出实际图像。MCP 使用[官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk) 的 stdio Server，并通过实际 ClientSession 握手测试；不复制社区任意 Python 执行桥或提供自审批工具。源代码参考目录未作修改。

## Website 实施补充（2026-09-07）

按用户后续明确请求，增加 website 可视化操作页；采用左侧场景树、中间三维布局、右侧构建／相机／数据操作面板。实际引擎通过同源本地 HTTP 服务使用原有仿真工具和权限，不把示例布局当作运行证据。当前未接入网页 AI 聊天或公网仿真服务。浏览器使用 [Three.js 官方 API](https://threejs.org/docs/) 与固定 [r160 作者源码](https://github.com/mrdoob/three.js/tree/r160)，MIT 许可证随本地浏览器模块打包，避免运行时 CDN 依赖。实现和验证见 [website README](../../website/README.md)、[RUNBOOK](../RUNBOOK.md)。
