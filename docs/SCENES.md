# 一句话生成场景与复杂任务路由

2026-09-05。默认后端 MuJoCo，复用项目已验证的安装；core 仍不在 import 时强制加载物理引擎。Genesis 本次只参考其场景／实体分层，不安装、不标记为已支持。

## 当前场景组合

2026-09-05：机器人网格与关节通过资产组合器加入已有场景，不再走旧刚体JSON的限制。`compose_scene`支持保留现有物品、增删移动、自动找模型和支撑面定位；每次成功修改强制重启MuJoCo。官方文档连接与具体格式见[MuJoCo操作Agent](MUJOCO_AGENT.md)。以下桌面刚体/固定预设仍作兼容入口。

## 终端用法

启动 `./loop`，用 `/key` 设置 Qwen Key，然后：

```text
/scene 桌面左边放一个红色方块，右边放一个蓝色小球
```

也可直接用自然语言要求生成场景，由 Qwen 调用 `generate_scene`。快捷指令更确定，不依赖对话模型是否选择工具。

复杂场景与推理使用当前已配置的模型和 Key，无需单独配置：

```text
/scene --complex 在桌面上排列六个不同颜色的方块，彼此不重叠，左右对称
/complex 分析双机械臂协作抓取的任务分解与验收条件
```

后者只提供专家建议，不生成机器人动作。普通对话的 Agent 也可以通过 expert_advice 请求专家，保留用户任务文本，不开放代码／设备执行工具。

所有任务统一使用用户当前选择的模型。`expert_advice`、`/complex`、`/scene --complex` 保留入口名，均复用当前模型；`/expert-key` 是 `/key` 的兼容别名。

## 默认值与真实窗口

用户未提供参数时自行补合理默认值／合理随机值，写入assumptions随场景保存以复现，不询问额外确认。`生成一个桌面场景`／`生成桌面场景`直接走本地默认桌子＋方块；`生成一个桌子`／`生成一张桌子`生成空桌，不依赖Qwen或Expert。

`启动仿真器`、`打开仿真器`、`启动软件`或`/viewer`实际打开MuJoCo桌面窗口，使用最近生成的场景，无成功场景时自动创建默认场景。`/viewer status`查询真实进程／窗口状态，`/viewer stop`关闭本终端窗口。生成文件与打开窗口是两个不同结果；run_sim明确返回offline_joint_test、opens_window=false，不代表桌面或GUI。

缺MuJoCo时用固定包名在项目虚拟环境／管理的运行环境安装，不执行模型拼接的命令。Linux GLFW窗口需要可访问的DISPLAY；无显示或窗口创建失败返回window_open=false，不谎称打开。启动只有在子进程创建窗口并同步成功、且仍存活时才返回true。退出交互终端会关闭其拥有的窗口。plan／deny规则仍生效，定时聊天不能打开窗口。

## 最小流水线

描述 → Qwen 或指定专家 → JSON SceneSpec → 数值／结构／范围检查 → 程序生成 MJCF → MuJoCo 编译 → 250 步物理烟雾检查 → 归档。JSON／几何／物理校验失败时，把前次候选和具体报错送回同一模型修正，单次生成最多3次模型请求（含专家路由），每次保持原始要求。允许完整JSON代码围栏，不从任意正文中猜取对象。

旧输出中的 needs_expert=true 不再触发提供商切换，仍须通过几何和 unsupported 校验。API不可用、未支持能力、取消不作盲目重试。桌子由编译器创建，模型通过table配置桌子、objects配置桌上刚体；0.15m方块放于0.75m桌面时中心z=0.825。当前 API 可能计费；定时对话只能调用推理咨询，不能生成场景或打开窗口；显式定时 slash 指令白名单仍只开放 /status、/sim。

当前 SceneSpec：默认1.2×0.8m、桌面高度0.75m的实体桌子（带桌腿）＋0..20个自由刚体；可选table字段指定size=[长,宽,厚]、height和color，空桌面合法；box、sphere、cylinder，支持尺寸、世界位置、RGBA、质量。只支持轴对齐初始物体。验证初始工作区、有限数值、名称及包围盒不重叠；禁止模型提供 include、插件、路径、Python 或 shell。

旧刚体JSON不接受外部资产；组合JSON通过受控资产库导入机器人并保留场景，见[MuJoCo控制与模型库](MUJOCO_CONTROL.md)。超出范围的铰接抽屉、软体、绳索、液体、网格物体必须报告 unsupported，模型不能突破尚未实现的模拟能力。尺寸与代理假设保存在报告，不承诺任意一句话都能忠实实现。

成功后写入独立目录 `artifacts/terminal/scenes/<id>/`：

- scene.json：结构化场景及假设。
- scene.xml：自包含 MJCF。
- report.json：原始描述、模型、是否升级专家、逐次校验阶段／错误及验证结果。

失败也保存独立report.json，但不写scene.xml；工具反馈包含stage、message、retryable和报告位置，不能仅将JSONDecodeError解释为用户描述有误。主对话保留4轮工具预算，另加1轮无工具总结，避免最后一轮工具成功后直接丢失结果；本轮对话相同不可重试请求不会重复执行。

结果中的 physics_smoke=pass 只代表编译并短时间推进时未触发数值警告；semantic_verdict=unverified、task_success=not_evaluated 明确保留。当前无截图／视觉语义审核、抓放控制器或完整稳定性／可达性认证；不能把“生成场景”当作“完成操作”。资产输出不覆盖已有目录。

## 与 Genesis 的关系

复用思路是“场景描述与模拟后端分离”，未来可从同一 SceneSpec 构造 Genesis entities。Genesis 官方提供 Scene/add_entity/build/step，但其 MJCF 导入并不意味着 MuJoCo 世界设置完全一致：timestep、integrator 等世界级选项需单独映射。[Genesis 入门](https://genesis-world.readthedocs.io/en/latest/user_guide/getting_started/hello_genesis.html)、[MJCF 导入限制](https://genesis-world.readthedocs.io/en/latest/api_reference/engine/entity/morph/file_morph/mjcf.html)

所以本版配置只接受 scene.backend=mujoco；不提供未经验证的 Genesis 一键切换，也不宣称其原生完成自然语言生成。

## 验证

34 项完整环境测试通过，新增真实 MuJoCo 场景编译／动力学、非法几何、重叠、未支持对象和 Qwen→GPT-6 路由测试。模型输出由测试替身提供，真实 Qwen／GPT-6 API 本次未请求；没有下载权重、连接真机或安装 Genesis。文档由 OpenAI Docs 核实 API 标识，project-maintenance 更新入口与操作规范。


## 固定椅子与加载内容核对（2026-09-05）

`生成一个椅子`／`生成一把椅子`本地生成一把固定木椅，默认不添加桌子或方块；尺寸0.45×0.45×0.85m，座高0.45m。座面、靠背、四条腿是同一固定body的六个box碰撞几何。`生成一张桌子和一把椅子`添加默认空桌，椅子在左侧地面。没有活动关节，不承诺可坐、折叠、抓取或动态家具任务。

预设采用独立受限SceneSpec：preset=chair、include_table布尔、color四维RGBA、assumptions/unsupported字符串列表、needs_expert=false。固定尺寸不可通过模型增加任意字段绕过校验；要求自定义尺寸、额外物体或活动椅子时必须声明不支持，不得静默退化成默认椅子。普通桌面SceneSpec保持兼容。

自然语言生成椅子必须实际调用工具，不由Qwen直接写成功描述。所有交互生成入口成功后自动打开或加载新场景；“没变”或明确场景纠错会按最近原始用户生成请求重新生成并加载，不要求用户再说一次打开。生成失败时保留失败状态，阻止用旧场景冒充此次请求；再次成功生成清除此状态。

查看器按实际MJCF内容SHA-256与路径决定复用：相同文件内容返回reloaded=false/reused_existing_window=true；同路径内容变化重新启动窗口进程。worker读取一次XML并以该内容编译，状态上报scene_sha256、model_bodies、model_geoms；模型不能从相同PID或相同路径推断“已重载”。这些是实际加载模型的结构证据，不等于任意语义或任务验证。

验证：[test_chair_scene](../tests/test_chair_scene.py)覆盖六个椅子部件、无附带桌/方块、SceneSpec重编译、恢复会话纠错、生成失败拦截旧场景。真实GUI验证旧方块→未变化复用→同路径写入椅子后新PID及匹配哈希/模型结构，证据[chair_reload_validation.json](../artifacts/terminal/viewer/chair_reload_validation.json)。实际已保存场景的索引：[latest_chair.json](../artifacts/terminal/viewer/latest_chair.json)。[渲染预览](../artifacts/terminal/scenes/b609148d1a9f479c91a14c8c0b827745/preview.png)已查看并核对椅子外形，测试窗口最后关闭；没有真机或付费模型API调用。
