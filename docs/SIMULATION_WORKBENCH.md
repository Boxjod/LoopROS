# 仿真工作台、摄像头与学习数据

2026-09-07。Loop 原生 robotics 工具与 `loop mcp` 共用仿真实现、工具 schema 和 PermissionGate。MuJoCo 在工作台进程中运行；Isaac 在独立的本机 headless 进程中运行，使用其自带 Python、USD、PhysX 和 Replicator。不会接管已打开的 GUI。

## 已实现

| 能力 | 入口及边界 |
| --- | --- |
| 场景与机器人 | `sim_create`、`sim_edit`：创建实例，添加 box、MJCF/USD 机器人或资产，移动／删除已知物体；Isaac 添加资产会 reset 所属 world |
| 格式转换 | `sim_convert`：Isaac 已安装的 URDF/MJCF importer 输出新 USD；返回哈希、关节和 articulation，不能据转换成功推定动力学相等 |
| 多相机 | `sim_camera`：固定、头部、腕部或其他随体安装；`sim_capture` 保存 RGB PNG、RGB/depth/segmentation NPZ、内外参、时间、状态和场景哈希 |
| 物理与验收 | `sim_reset`、`sim_step`、`sim_task`、`sim_inspect`：有界物理步进，task/variation/seed/horizon 与可测量成功条件；没有测量依据时 inconclusive |
| 演示数据 | `sim_record`：动作前观测和多相机图像、实际下发动作、动作后关节状态、reward、terminated、truncated；不完整文件保留但 loader 拒绝 |
| 模仿学习接口 | `toolchain/sim_dataset.py` 的 `action_chunk` 提供未来动作块与 padding mask；`TemporalActions` 融合重叠预测，有效零动作不会被丢弃 |
| 强化学习接口 | `toolchain/sim_gym.py` 的 `SimulationEnv` 提供 Gymnasium reset/step、有限动作空间、图像与关节观测、奖励与终止 |
| Skills | `mujoco-scene-builder`、`isaac-scene-builder`、`simulation-learning-data`；完整包安装到用户目录，原有 Skills 保留 |

原生对话先 `load_toolset(name="robotics")`；工具组每轮按需加载。MuJoCo 的 action 是模型 actuator control，Isaac 是 joint position target，必须读取各实例的 action_space，不能假设单位或维数相同。

## 启动

源码环境可选依赖：

```bash
uv pip install --python .venv/bin/python 'mujoco>=3.3,<4' 'numpy>=1.26' 'h5py>=3.10' 'gymnasium>=1,<2' 'mcp>=1.12,<2'
.venv/bin/python scripts/install_sim_skills.py
```

发行包对应 `loop-ros[sim,mcp,learning]`。Isaac 不用普通 pip 环境启动；本机已验证 `/home/boxjod/isaacsim/python.sh`，版本 4.5.0。已建立本机用户进程配置 `~/.loop/processes/isaac-simulation.json`，可在 Loop 现有节点流程中启动：

```text
/node profiles
/node start process isaac isaac-simulation
/node logs isaac
```

就绪回执为 `Loop Isaac bridge ready`；原生工具默认读取 `~/.loop/isaac-bridge.json`。配置只在启动时生成，含本机随机端口与 token，POSIX 0600。正常停止会清理本进程生成的连接文件；异常崩溃遗留文件时，先核实进程已停止，再移走该文件。启动器不覆盖既有连接信息。`/node stop isaac` 停止该节点；退出所属 CLI 也会回收。用户目录遵从 `LOOP_HOME`，这里提供的本机 profile 使用明确绝对路径。

也可直接运行（首次启动目标连接文件必须不存在）：

```bash
/home/boxjod/isaacsim/python.sh toolchain/sim_isaac_host.py --config "$HOME/.loop/isaac-bridge.json" --port 0
```

MCP 客户端配置模板：[mcp.simulation.example.json](../configs/mcp.simulation.example.json)，入口 `loop mcp`，可选 `--state-dir` 和 `--isaac-config`。没有修改全局 Codex/Claude 配置。MCP 和原生 Loop 必须使用相同 state directory 才会共用持久权限规则。plan 不允许执行仿真；`sim_record` 默认 ask，MCP 不提供审批 UI 或自审批工具，操作者在对应 Loop 中审阅后可使用已有 `/permissions allow sim_record`，这会持久允许该动作。普通工具调用不能修改此规则。

一个 Isaac host 同时只拥有一个 stage；原生 Loop 和不同 MCP 会话不能同时抢占它。客户端 timeout 表示结果不确定，不自动重试有副作用请求。这个本机工具桥不是硬件隔离沙箱，也不支持远端公网连接。

## 相机与数据契约

相机 position 为父坐标系米制位置，quaternion 为归一化 wxyz；相机坐标为 OpenGL：+X 向右、+Y 向上、−Z 向前，像素 +u 向右、+v 向下。MuJoCo parent 使用 body 名称，Isaac 使用绝对 USD prim 路径。提供内参 K 与 camera_to_world；深度为米制 image-plane depth。MuJoCo 全部相机共享 near/far，配置不一致会拒绝。

Isaac 使用 `rep.orchestrator.step(delta_time=0.0)` 触发暂停时间线的采集；物理步进单独执行。RGB、深度和分割必须产生实际帧；图像统计不能证明物体可见或任务成功。语义／实例 ID 的含义以每次回执的 labels 为准，不跨引擎假设相同编号。物体遮挡、曝光质量及完整数据集质量仍需任务专属验收。

数据目录为 `datasets/TASK/variationN/INSTANCE/episode_N.hdf5`。包含 `/observations/qpos`、`/observations/images/CAMERA`、`/action`，同时扩展 qvel、深度、分割、逐帧标定和 next_observations。`complete=true` 表示采集事务完成，**不等于任务成功**；成功看 evaluation。seed 记录并要求与显式 reset 一致，目前没有自动域随机化。

参考 [Boxjod/RLBench_ACT](https://github.com/Boxjod/RLBench_ACT) 的 task/variation、head/wrist 相机、HDF5 和 action chunk 逻辑。当前采用明确的 observation[t] → issued action[t] → next_observation[t]，不照搬原采集器的下一帧 qpos 推导动作。不能将任意 MuJoCo actuator control 直接用于按关节位置训练的现成 ACT checkpoint。训练侧还需匹配机器人维数、相机名、图像归一化、动作归一化和控制频率。未移植完整 RLBench 任务库、ACT 网络训练器或 Isaac Lab 训练框架。

## 验证与限制

复现脚本主动执行独立的有界仿真，output 必须为新目录：

```bash
MUJOCO_GL=egl .venv/bin/python scripts/validate_simulation_workbench.py --backend mujoco --output artifacts/simulation-workbench/new-mujoco
.venv/bin/python scripts/validate_simulation_workbench.py --backend isaac --isaac-config "$HOME/.loop/isaac-bridge.json" --output artifacts/simulation-workbench/new-isaac
MUJOCO_GL=egl PYTHONPATH=tests .venv/bin/python -m unittest test_simulation_workbench test_skills test_coding_agent test_harness_behavior test_composition test_user_portability -q
```

53 项针对性测试通过。最终证据：[MuJoCo](../artifacts/simulation-workbench/mujoco-final/validation.json)、[Isaac](../artifacts/simulation-workbench/isaac-local-stage/validation.json)。本机已验证 MuJoCo 3.12.0 / EGL、Isaac Sim 4.5.0 / RTX 3080 Ti：实际机器人关节响应、固定／腕部相机、标定数据、HDF5 动作前后状态。验收任务仅为 cube 存在，不是抓取成功或学习收敛。官方 MCP SDK 的真实 stdio 初始化、工具发现、plan 拒绝及 MuJoCo 创建／关闭纳入测试；Isaac SDK 不在普通单元测试中假装运行。

Isaac USD authored bounds 不作为物理接触证据；不支持接触穿透查询。任意 USD 场景里的机器人尚不自动发现并接入控制，需要通过受控导入登记。新增机器人和几何需在采集前完成。当前未提供完整场景打包导出／任意运行状态恢复、GUI 内嵌窗口、自动示教规划、域随机化和训练调度；这些不影响已验证的建场景→控制→多相机采集→学习数据接口闭环。

训练侧最小接法（在项目源码目录、已安装 learning extra 的 Python 中）：

```python
from toolchain.sim_mujoco import MujocoSimulation
from toolchain.sim_gym import SimulationEnv
from toolchain.sim_dataset import action_chunk, TemporalActions

engine = MujocoSimulation('examples/simulation_workbench.xml')
env = SimulationEnv(engine, {
    'name': 'reach', 'horizon': 100,
    'success': [{'kind': 'position', 'body': 'wrist',
                 'target': [0.1, 0.1, 0.4], 'tolerance': 0.03}],
})
observation, info = env.reset(seed=7)
# 将 env 交给用户选择的 Gymnasium 兼容训练器；此示例不启动训练。
env.close()
# action_chunk(episode_path, start=0, length=32, cameras=['head', 'wrist_cam'])
# TemporalActions(action_dimension) 用于推理时融合重叠动作块。
```

Isaac 可将 `IsaacSimulationClient` 作为同一 Env 的 engine；单个 host 的一个 stage 不能直接用作多个并行环境。物理参数、任务可达性和奖励设计需在训练前按实际机器人验证。

## Website 可视化操作

`loop web` 提供本地三维工作台：场景树、物体创建／选择／位置编辑、机器人导入、关节输入与有界步进、相机配置与真实快照、任务设置及 HDF5 采集下载。默认 `http://127.0.0.1:8768/workbench.html`。详细布局与边界见 [website README](../website/README.md)。网页实例由该服务持有，刷新页面可找回仍存活的实例；不与其他 CLI/MCP 会话共享场景所有权。

网页侧审批是操作者单独点击的 API，不暴露为模型或 MCP 工具；仍经同一 PermissionGate 检查当前规则。静态网站只提供标注的样例布局，不会偷偷连接 localhost。Isaac 页面布局仅使用可用包围盒；实际渲染通过相机查看。右侧尚非自然语言 Agent 对话。
