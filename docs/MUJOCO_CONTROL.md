# MuJoCo 控制与官方模型库

2026-09-05。本机 Linux / MuJoCo 3.12.0 已验证。旧 Loop 进程需重启加载代码。

## 生成和窗口状态

自然语言生成、`/scene`、Master 的 `generate_scene` 成功后自动打开窗口，已有窗口则加载新场景。若无 DISPLAY 或权限规则禁止打开，场景仍保存，返回 `viewer.window_open=false` 和具体原因。生成失败不会把旧场景冒充新结果。定时任务禁止调用这些有 GUI 副作用的生成/加载/控制工具。

`/viewer status`返回真实进程、心跳、加载摘要、暂停状态、仿真时间、qpos/qvel、执行器ctrl及限值。心跳过期或进程退出时不声称窗口打开。普通场景哈希对应XML；导入模型哈希覆盖清单中的XML、网格、纹理、许可等文件。普通打开在内容相同时复用窗口；每次场景修改和`/viewer reload`强制重启。

## 当前窗口的操作

| 命令 | 行为 |
| --- | --- |
| `/viewer`、`/viewer status`、`/viewer stop` | 打开、查询、关闭 |
| `/viewer pause`、`/viewer resume` | 暂停、继续物理推进 |
| `/viewer reset` | 恢复首个keyframe或默认状态，并暂停 |
| `/viewer step 10` | 暂停时推进10个物理步；允许1–1000步 |
| `/viewer speed 0.5` | 请求0.5倍速度；允许0.1–4，实际速度受计算能力限制 |
| `/viewer camera top` | front / back / left / right / top / isometric；按模型范围定位 |
| `/viewer actuate 0.2 -0.2` | 设置全部执行器的ctrl；长度、有限数值、模型ctrlrange均校验 |
| `/viewer reload` | 强制重新加载当前场景 |

自然语言“暂停仿真”“继续仿真”“重置仿真”“重新加载场景”直接调用控制工具。其他表达可由模型使用 `simulator_control`。

`actuate`数值单位由导入MJCF执行器定义，可能是位置、速度或力矩，不能统一称为关节角或末端坐标；没有声明控制限值的执行器拒绝控制。先查状态，设置控制值，再单步或继续。暂停时设置ctrl不会立即推进物理。`move_sim`与`/move`仍是独立离线双关节测试，不控制该窗口。

命令有唯一ID、3秒有效期和最多4秒回执等待；超时返回inconclusive，不自动重放。`artifacts/terminal/viewer/control.sqlite`记录Episode/Review；pass仅指窗口确认应用了命令，不代表到位、稳定、抓取成功。窗口状态包含最后回执以供复查。`/stop`关闭窗口；切换plan或deny窗口控制也回收窗口。基础串口与Loop Node保留。

## 官方资产入口

新增物品默认保留当前场景；资产搜索、组合、官方手册连接及新增验证见[MuJoCo操作Agent](MUJOCO_AGENT.md)。

```text
/models
/model-load dynamixel_2r
/viewer status
/viewer actuate 0.2 -0.2
/viewer step 100
/viewer camera front
```

`/models`联网列出官方 `google-deepmind/mujoco_menagerie` 中顶层具有 `scene.xml` 的模型；不是库内全部可能场景。`/model-load NAME`首次从GitHub读取固定commit的目录及文件，后续离线复用最近已校验安装。本地缓存优先复用；支持公开GitHub资产URL及场景组合，见[MuJoCo操作Agent](MUJOCO_AGENT.md)。

资产保存在状态目录`models/<name>/<commit>/`，`.loop-assets.json`保存来源、版本及SHA-256。下载核对Git blob校验值，只取所选模型的数据和文档/许可证，不执行第三方Python或shell脚本。限1500文件、总300MiB、单文件80MiB；不支持符号链接、路径越界或引擎插件。按各模型附带许可证使用，不将整个库视为统一许可。

加载前在管理Python环境编译；窗口从完整已校验的内存资产快照加载include/mesh/texture，避免相对路径丢失及旧资产混用。修改缓存文件会触发校验失败，而非悄悄加载。导入机器人初始暂停；已有窗口复用时保留当前运行状态。下载成功、编译成功、窗口打开分别报告。

实际验证模型为`dynamixel_2r`，commit `8161bba264d7fa7c99ca301e91e7fb44737676ad`，21文件、5,698,611字节、2关节、2执行器。目录中其他机器人尚未逐一下载验证。模型已支持与自然语言桌面场景组合；自动逆运动学规划、接触抓取与方块入盒评审尚未实现。

官方依据：[Menagerie](https://github.com/google-deepmind/mujoco_menagerie)、[MuJoCo Python passive viewer](https://mujoco.readthedocs.io/en/stable/python.html#passive-viewer)。调研归档见[接入报告](../../projects/reports/11_mujoco_control_menagerie.md)。

## 验证入口

- `tests/test_simulator_control.py`：真实物理步进、控制边界、自动打开、权限/定时约束、VFS与资产完整性。
- `tests/test_model_library.py`：下载校验、离线复用、失败清理和缓存篡改拒绝。
- `artifacts/terminal/viewer/control_library_validation.json`：本机真实GUI的暂停、步进、继续、重置、重载及导入机器人运动证据；测试窗口最终关闭。

最终完整回归144项通过，包括中文流式同时输入PTY；App真实GUI自动打开、离线模型加载和控制记录验证见[RUNBOOK](RUNBOOK.md)。

## 当前窗口轨迹与退出反馈（2026-09-05）

窗口从打开变为关闭/心跳不可用时，终端主动显示独立操作面板：↑/↓ 选择 `Reopen last scene` 或 `Keep closed`，Enter 执行，Esc 收起。输入中的草稿保留，操作不进入模型对话；生成场景期间的临时关窗不会误报。运行旧代码的终端需重新启动。

`simulator_control` 新增以下动作，受原有 sim/plan 权限门禁约束：

```json
{"action":"move_joints","robot":"panda","target":[0.15,0,0,-1.5708,0,1.5708,-0.7854],"duration":2}
{"action":"move_cartesian","robot":"panda","body":"panda/hand","position":[1.4,0,1.1],"duration":3}
{"action":"stop_motion"}
```

这些是参数格式示例，实际坐标与关节目标须依据当前窗口状态选择。robot 为模型命名空间前缀，target 顺序是该机器人直接位置执行器对应的转动关节顺序；position 是指定 body 原点的世界坐标（米），不是夹爪指尖，也不约束姿态。

执行链为：读取当前模型与关节 → 位置 IK 或关节目标 → 限位与有界路径碰撞采样 → 平滑关节插值 → 当前窗口 ctrl → mj_step → 实测误差验收。支持有限位、单位齿比的直接关节位置执行器；不将力矩执行器当位置执行器。关节轨迹峰值速度上限 0.5 rad/s，必要时延长时长，最长 30 秒；等待到位额外最多 3 秒仿真时间，调用总等待最多 36 秒墙钟时间。低速仿真可能触发总超时，此时停止，不自动重发。

关节误差小于 0.04 rad、笛卡尔请求额外要求位置误差小于 0.02 m 才返回 motion.state=succeeded。运行期间显示误差；Ctrl-C 或暂停停止当前轨迹并保持当前位置，关窗返回失败，直接 actuate 会替代轨迹。命令受 ID 关联，执行回执和最终测量写入 viewer/control.sqlite。不能把“命令已接受”当“已经到位”。

这是一条局部位置轨迹链，不是全局避障规划器或完整抓取控制器：沿候选路径采样检查新碰撞，不保证连续空间无碰撞；不自动寻找绕障路线；不提供夹爪朝向、接触力闭环及物品保持/抬升验收。模型可连续检查状态、执行接近和夹爪动作，但不能将一次到位称为抓取成功。

为兼容已有组合场景，对具有 Panda 特征肘关节范围、且初始肘关节越界的零姿态进行修复；保留有效初始姿态。新组合和旧窗口加载共享该规则，避免从非法零姿态开始控制。

实测用户场景 `4fefa52cfbb5407087fd0b28f23f9290`：真实 X11 窗口中第一关节运动 0.15 rad，约 2.34 秒，最大关节误差约 0.0066 rad。原布局基座位于 (1,0,0.450)，杯子 body 位于 (2,0,0.750)；对杯子上方 (2,0,1.05) 的当前位置 IK 求解失败，残差约 0.191 m。这是当前求解器/姿态下的失败，不是全局不可达证明；需要重新规划支撑位置或目标位置，不能声称已抓取。

验证：test_viewer_motion（真实物理步进、IK、越界、碰撞、停止、关窗通知）、test_cli_edges（选择并重开）、test_terminal_render（PTY面板显示/关闭）及已有组合/窗口测试。真实窗口记录：`artifacts/terminal/viewer/motion_validation.json`。
