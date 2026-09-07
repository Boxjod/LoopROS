# 最小工具链：实现与使用

2026-09-05。原则：一个需求一个小模块，复用现有 Agent Loop；不引入第二套 Agent 框架、ROS 工作空间或训练平台。重依赖只在创建对应对象时导入。

| 组件 | 实现 | 当前验证 |
| --- | --- | --- |
| Agent Loop | 原有 `core/loop.py`，Body／Master／Reviewer 注入 | Mock 与 MuJoCo 均跑通 |
| MuJoCo | `MujocoBody`：MJCF、显式关节／执行器映射、headless stepping、observe／stop／reset | 双关节物理任务通过 |
| Ego2MuJoCo | `template_command`／`run_template`：独立解释器调用现有 CLI | 入口静态核对、参数检查；未重跑上游 pipeline |
| 轨迹 | `edit_trajectory` 时间缩放／关节偏移，`sample_trajectory` 线性插值，复用校验器 | 单元测试 |
| Mink | `MinkKinematics.fk/step`：位姿任务、姿态正则、关节与速度约束 | 真实 Mink FK／迭代 IK 测试 |
| ROS 2 | `RosJointObserver` 订阅 JointState、排序、缺失与过期检查、close | 数据缓冲实测；无 rclpy 环境，通信未测试 |
| RAM／VRAM | `ModelPool`：声明预算、租约、回调、闲置 LRU | 模拟模型加载／淘汰／异常测试，未加载真实模型 |

## 1. Agent Loop 与 MuJoCo

```python
body = MujocoBody("scene.xml", {"joint1": "position_actuator1"})
loop = Loop(body, FeedbackMaster(), NumericalReviewer(), store)
result = loop.run(task)  # task.body_id 必须匹配 body.spec.body_id
```

无 viewer、无 wall-clock sleep，不改变物理 timestep 换取速度；报告 `last_timing` 的 sim_s／wall_s。每步检查截止时间、数值和 MuJoCo 警告，出现异常进入 inconclusive。当前只接受已限位 hinge＋单位 gear 的位置执行器，拒绝把力矩控制输入当关节位置。动作从 actuator ctrl 进入动力学，不直接写 qpos 伪装执行。

本地双关节 demo：1 秒仿真推进约 0.003 秒 wall time（单次烟雾测试，非稳定性能 benchmark；不含加载、评审、渲染和训练）。没有实现 GPU／MJX 或并行 rollout，不把该数字推广到复杂场景。

reset 只回到 MJCF 默认状态；不保证物体摆放、抓取或 task-ready 后置条件。contacts 目前是观察时刻接触数，不是完整接触时序；无渲染证据，不支持视觉任务成功判定。stop 在不推进仿真的情况下改为保持当前位置，不是急停模型。实例 ID 隔离不同模型加载，尚无持久化资产／标定哈希体系。

## 2. Ego2MuJoCo 复用

本地源仓库：`/media/boxjod/File/LoopMaster/自研论文/数字孪生/Ego2MuJoCo`。已读 README、pyproject 和 CLI／模板执行入口；未改源仓库。

```python
from toolchain.ego2mujoco import template_command, run_template
command = template_command(repo, python310_to_312, segments_json, new_output_dir)
# 确认输入后显式执行：
run_template(repo, python310_to_312, segments_json, new_output_dir, timeout_s=300)
```

上游要求 Python >=3.10,<3.13；本目录仿真验证环境是 3.13，不能直接宣称兼容。桥接明确接受上游独立解释器，不安装／导入到 core。无 shell 拼接、不加 --force，拒绝已有输出目录；执行会在指定新目录写场景／视频／结果，非只读操作。

Ego2MuJoCo 模板含 gantry／夹爪／接触后置条件，与当前 hinge-only MujocoBody 并不通用：复杂上游场景走其自身 executor，不能宣称任意 scene.xml 已接入本版 Loop。CLI 成功退出不自动等于操作成功；其结果／视频转换为 Episode 和 Review 尚待实现。硬超时由 subprocess 提供，子进程派生进程的整组回收尚未实现。

## 3. 轨迹与 Mink

```python
edited = edit_trajectory(points, limits, max_speed=0.5,
                         time_scale=2.0, offset=[0.0, 0.0])
q = sample_trajectory(edited, timestamp=0.5, limits=limits, max_speed=0.5)
ik = MinkKinematics(model, "tip", {"j1": 1.0, "j2": 1.0})
T = ik.fk(q)
q_next = ik.step(q, T, dt=0.01)
```

轨迹是 `(seconds, joint_positions)` 序列；编辑生成新副本，起点归零，不改变原数据。偏移是关节空间编辑，不是跨本体／物体坐标重定向。线性插值有速度突变，现有校验不覆盖加速度、碰撞或动力学。

Mink 每次 step 只做一次微分 IK，返回完整模型 qpos；不是保证可达的终点求解器。调用方比较末端残差并限制迭代次数。速度限制需完整覆盖要控制的关节；当前未自动验证覆盖，未加入碰撞约束，未支持任意自由基座／多本体模型的认证。

## 4. ROS 2

```python
observer = RosJointObserver(node, "/robot1/joint_states", ["j1", "j2"], "robot1")
# 调用方自行创建并 spin ROS node；随后读取：
state = observer.observe()
observer.close()
```

不隐式初始化 ROS、启动节点或发布电机命令。传感器 QoS；只保留最新一帧，按配置关节名重排。过期依据本地接收 monotonic 时间；保留源时间戳但尚未验证跨机时钟、乱序／重复源消息，因此不是运动控制的安全状态源。不要把 ROS 只读观察器伪装为 simulated Body 来绕过真机禁用。

## 5. RAM／VRAM 资源池

```python
pool = ModelPool(ram_bytes=4 * 1024**3, vram_bytes=6 * 1024**3)
pool.register("reviewer", ModelSpec(ram_bytes=2 * 1024**3, vram_bytes=5 * 1024**3,
                                    load=load_reviewer, unload=unload_reviewer))
with pool.lease("reviewer") as model:
    result = model.review(evidence)
pool.close()
```

示例 load／unload 是调用方回调，不是内置模型函数。估计预算必须涵盖权重、KV、视觉输入、推理工作区和加载峰值；系统／仿真留量由调用方从总预算扣除。活跃模型绝不自动卸载；预算不足只淘汰闲置模型，仍不足即拒绝加载。

单线程协作式管理，无 nvidia-smi 监测、OS 硬限制或跨进程调度；预算是声明量而非实测。回调负责释放真实资源及部分加载失败清理，Python 外部引用可能阻止释放。`empty_cache` 不能替代模型卸载。Jetson 统一内存不能简单把 RAM 与 VRAM 预算当独立物理池。

## 来源与限制

接口依据本地源码及 [MuJoCo Python API](https://mujoco.readthedocs.io/en/stable/python.html)、[Mink 官方示例](https://github.com/kevinzakka/mink/blob/main/examples/docs/tasks_and_limits.py)、[ROS 2 rclpy 生命周期](https://docs.ros.org/en/iron/p/rclpy/api/init_shutdown.html)核对。仅依赖这些基础 API，不宣称已实现所有最新特性。

依赖版本见 [scripts/requirements-sim.txt](../scripts/requirements-sim.txt)，测试与命令见 [RUNBOOK](RUNBOOK.md)。没有真机操作、模型权重下载、训练、ROS 网络接入或上游全流程执行。
