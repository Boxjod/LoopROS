# 可交互场景与日常物品资源

2026-09-05，实测环境 MuJoCo 3.12.0。入口是 `model_library`、`load_model`、`compose_scene`；资源由上述工具按需查询和解析，不再通过全局simulation_context注入；无需用户另行粘贴链接。

## 窗口操作

- 场景默认运行。**空格**切换暂停/运行，**Backspace**恢复 home 并暂停；窗口底部显示实际状态。
- **双击鼠标左键选中物体**，底部应出现其名称；随后按住 **Ctrl＋鼠标右键拖动**。暂停时能重新摆放有 free joint 的球/杯子；运行时施加外力。Shift 切换拖动平面。普通拖动操作相机。
- 展开右侧 **Control**，在运行时拖动 `panda/actuator...` 滑条控制机械臂；`wardrobe/left_open`、`right_open` 控制两扇柜门。滑条单位遵从模型，Panda 最后一个夹爪控制范围是 0–255。
- 固定桌柜和机械臂基座不能当自由物体拖走；移动安装位置用 `compose_scene.move`。强行拖机器人关节是外力扰动，不等于末端逆运动学控制。
- Passive viewer 原生左栏 Pause/Run 在本机版本不可操作，以底部状态、空格和 Agent 控制回执为准。新启动的 Loop 终端加载新工具；已运行的旧 Python 终端不会热更新模块。

原问题：worker 对含资产场景强制暂停，未接入空格回调；暂停路径未应用动态刚体位姿扰动。现已去掉强制暂停，按键经队列在物理线程处理，继续同步 GUI，并在暂停时调用 `mjv_applyPerturbPose(..., 1)`。参照 [3.12.0 官方 Python 手册](https://mujoco.readthedocs.io/en/3.12.0/python.html#passive-viewer)。

## 来源与真实接入程度

| 来源 | 用途 | 本项目接入 |
| --- | --- | --- |
| [Google Scanned Objects](https://research.google/blog/scanned-objects-by-google-research-a-dataset-of-3d-scanned-common-household-items/) | 真实扫描小物品，OBJ/纹理；并非所有日常家具 | GoogleResearch 官方 Fuel 查询、下载、转换、缓存；实测蓝色杯子 |
| [Open Robotics Fuel](https://app.gazebosim.org/OpenRobotics) | 家具与场景物品 | 官方查询和单刚体 OBJ/STL 转换；实测 WhiteCabinet |
| [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) | 带关节/执行器机器人 | 固定 commit 的 MJCF 资产组合；实测 Panda |
| [RoboCasa](https://github.com/robocasa/robocasa) | 厨房家具与操作任务 | Agent 资源参考，尚无通用 fixture 转换器 |
| [SAPIEN / PartNet-Mobility](https://sapien.ucsd.edu/) | 带关节家具 | Agent 资源参考，尚未接入其访问凭据/URDF 转换 |

搜索顺序为本地 → Menagerie → 官方 Fuel → 公开网页。Fuel 对象按名称匹配，排除只在鞋子描述中出现 wardrobe 的误匹配。本轮 wardrobe 查询没有找到可信名称匹配，不能宣称 Google 有衣柜模型。提供 `kind="wardrobe"` 的本地双开门预设（1.2×0.6×1.8 米、两铰链、两位置执行器），明确不是扫描资产。

示例工具参数（Agent 可以直接执行）：

```json
{"query":"杯子"}
```

用于 `model_library`；用其返回的实际 `source_url` 调用 `load_model`，或组合：

```json
{"add":[{"name":"wardrobe","kind":"wardrobe","position":[1.4,0.8,0]},{"name":"mug","kind":"asset","source":"https://fuel.gazebosim.org/1.0/GoogleResearch/models/Cole_Hardware_Mug_Classic_Blue","support":"table"}]}
```

若对象已存在，使用 move 或换名称；别重复 add。

## 转换边界与证据

Fuel importer 只接受官方返回的 GoogleResearch / OpenRobotics 模型 URL；下载 ZIP 上限 80 MiB，解包总量 300 MiB/1500 项，拒绝路径越界、符号链接、重复文件。不执行压缩包脚本。SHA256 固定此次下载内容，记录上游元数据、许可证及文件摘要；这是本地完整性校验，不是作者数字签名。

目前支持单 link、单 OBJ/STL visual、identity pose。多 link、关节、非零 pose、DAE/复杂 SDF 明确报错，不把关节静默压平。扫描模型使用 MuJoCo 凸包碰撞近似，杯子的凹腔等不可据此验证；缺质量时采用 0.2 kg 假设并记录。单 PNG 贴图自动连接，未实现任意 MTL 多材质恢复。

本次由 App 工具生成的[场景与加载回执](../artifacts/terminal/household_demo.json)，包括 Panda、桌子、自由蓝球、本地铰链衣柜、Fuel 白柜和 Google 扫描杯子。旧场景保留在原目录。实际 X11 鼠标/滑条/空格和关节回执见[交互验证](../artifacts/terminal/viewer/household_interaction.json)。测试覆盖名称误匹配、ZIP 越界、SDF 拒绝边界、柜门物理运动和暂停球体位姿扰动：`tests/test_household_assets.py`。

## 单物体请求与纠错入口

`terminal/scene_intent.py` 在模型回复前识别明确操作。`生成一个衣柜`、误输入 `生产成一个衣柜`、`我需要的只要一个衣柜` 使用 `base=empty`，确定性生成双开门衣柜，保留旧场景文件但不带入其中物品；无需模型再次确认。明确 `添加/加入` 继续组合到当前场景。

`生成一个电脑/显示器/键盘/笔记本电脑` 实际调用资产解析，不允许因旧的基础形状列表直接宣布整个系统不支持。检索/转换失败仍会如实报错，不保证任意电脑资产可用、不把其他物品或简单 box 偷换成所请求模型。当前运行的旧 Loop 终端不会热更新 Python 模块，应退出后重新启动 `loop`；每次成功修改 MuJoCo 场景状态后自动重启 worker 并核对加载状态；其他修改不触发重启。
