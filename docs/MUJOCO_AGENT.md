# MuJoCo 操作 Agent

2026-09-05。Loop ROS 使用用户当前配置的模型处理场景、资产和控制；不按“简单/复杂”切换提供商。能力由实际工具与验证决定，不以“最懂”代替验收。

## 官方文档与模型状态

MuJoCo版本与手册信息通过工具按需查询，不再逐轮自动注入模型上下文。`mujoco_docs` 默认读已安装版本，`version="latest"` 读最新 stable；可选 topic：python、model_editing、mjcf、simulation、viewer、actuators、contacts、functions、changelog、overview。query 可搜索匹配版本的官方页面，结果只允许官方域名和对应版本路径；搜索没有可用结果时读取该主题的官方入口。缓存一天，联网失败仅在已有缓存时返回带 stale 标记的旧资料，不自动升级 MuJoCo。

2026-09-05 实际读取本机 3.12.0 Python 手册和 stable 更新日志，后者显示 **3.12.0（2026-08-20）**，与本机一致。来源：[对应 Python 手册](https://mujoco.readthedocs.io/en/3.12.0/python.html)、[最新更新日志](https://mujoco.readthedocs.io/en/stable/changelog.html)。将来 stable 可能变化，应重新调用工具，不能把本次结果当永久最新版本。

`simulator_status` 的实时证据包含模型体/几何体名称、关节类型/限位/qpos 索引/轴、执行器范围、qpos/qvel/ctrl、各刚体世界位姿、接触数量、暂停状态和心跳。文档解释接口；状态与回执证明本次实际操作。actuate 的单位由模型执行器定义，不默认当成角度或末端坐标。

## 保留场景并加入物品

自然语言 `generate_scene` 支持组合 JSON；也可以通过 `compose_scene` 明确增删移动。示例：

```json
{
  "base": "current",
  "add": [
    {"name": "table", "kind": "table"},
    {"name": "chair", "kind": "chair", "position": [-1, 0, 0]},
    {"name": "panda", "kind": "asset", "query": "franka_emika_panda", "support": "table"}
  ]
}
```

`base=current` 默认保留已有物品；`empty` 显式创建新场景。已有同名物品用 move，不能重复 add。remove 为名称列表；有受支撑物品时拒绝直接移走/移除支撑物，避免留下悬空对象。每次成功修改保存新目录，不破坏旧场景。重新启动从 scene_state.json 中恢复已校验的场景，失败的请求单独记录；修复成功会清除旧错误。

支持 table、固定 chair、双开门 wardrobe、box/sphere/cylinder 和库资产。support 指向桌面/椅面等已知水平 box 表面或 floor；默认根据实际基座碰撞几何计算 z，检查底座是否落在支撑区域内，同一支撑上的新增物品优先找空位。原始几何尺寸、代理外观与真实材料力学参数是不同概念。固定机器人安装不代表自由支撑稳定性、逆运动学或自动抓取已验证。

组合使用 MuJoCo 原生 MjSpec attachment，保留资产、关节、执行器并为名称与资产路径加独立前缀。保存统一 home keyframe；导出后再编译精确文件并做物理冒烟检查。源模型缓存不修改。`scene.xml` 和资产清单哈希供窗口加载后核对。

官方 Panda 在 0.75 米高桌面上的实际基座位置约为 z=0.75003（补偿原始碰撞网格下界），不是固定写入 0.85。源模型有 9 个关节、8 个执行器；红色自由方块增加 1 个 free joint。基础组合及连续增删移动见 `test_composition.py`。

## 自动找资产

`model_library(query=...)` 和组合资产解析先查本地校验缓存，再查官方 Menagerie；没有匹配项先搜索 Google Scanned Objects / Open Robotics Fuel，再搜索公开互联网。`load_model` 现在加入当前场景，不再替换桌椅；没有指定支撑时优先使用已有 table。重复加载同名对象可重载/移动。

支持官方 Menagerie，以及公开 GitHub blob/tree 地址指向的 MJCF XML、OBJ/STL 网格。公开入口解析到固定 commit，仅下载有界的数据与许可证文件，并核对 Git blob SHA；不执行仓库脚本。每模型限 1500 文件、300 MiB，单文件 80 MiB。官方 Fuel ZIP 支持有界下载与单刚体 OBJ/STL 转换，见 [日常物品与交互](HOUSEHOLD_ASSETS.md)。仅有展示网页、其他来源压缩包、登录下载、其他格式、越界依赖或没有可直接导入资产时，返回检索证据与具体失败原因；“互联网有该物品”不等于已可编译。网格尺寸单位/外观需要实测确认，不将导入网格当作已验证抓取模型。

## 自动重载与如实回复

场景成功生成、加入、移动或移除后强制重启窗口，保存 Episode/Review，只有新进程、心跳和内容哈希核对通过才报告成功。Linux 可按持久化 worker 身份重新连接窗口；不仅凭 PID 认领进程。2026-09-05 用户取消普通修改后自动重启约定：每次成功修改 MuJoCo 场景状态后自动重启并核对加载状态；其他代码、Agent、会话和文档修改不触发重启。显式打开/重启请求照常执行。

“生成/继续/覆盖”优先恢复实际用户场景请求，执行工具；不依据旧助手虚构的 XML 路径。场景工具完成后直接由真实结果形成摘要，避免二次模型回复把失败改写成成功。普通聊天、资产解释等尚不能因此宣称完全无幻觉。

终端将 `**文字**` 渲染为加粗，支持跨流式片段/换行/窄屏，并在输出后重置样式，不污染输入行。

## 验证和限制

- `test_composition.py`：桌椅/Panda/新物品共存、资产导出后仍含新对象、home 位姿、支撑高度、移动/删除、失败保护、恢复及权限。
- `test_model_library.py`：官方缓存校验、公开 GitHub 网格导入替身、互联网回退、路径/脚本拒绝。
- `test_mujoco_docs.py`：版本链接、缓存、官方来源筛选；文档联网读取另有实际验证。
- `test_terminal_render.py`：24/40/80 列中文流式、跨片段粗体、同时排队与编辑的 PTY 屏幕属性。
- 实际 GUI 证据：[composition_validation.json](../artifacts/terminal/viewer/composition_validation.json)、[预览](../artifacts/terminal/viewer/composition_preview.png)。预览来自同一已校验场景的渲染，不冒充窗口截图。

未实现任意 CAD/URDF 自动转换、通用 IK/抓取策略、真实材质恢复或真机动作。模型配置仍由 loop-switch 管理；窗口重启不等于已运行的旧 Python 终端自动加载新代码。

真实模型验收：用户当前 `qwen-plus` 已实际完成“保留桌椅/Panda/红方块，再加蓝色小球”的自然语言请求，最终一次候选通过编译、保存和窗口重载。记录见 [natural_language_composition.json](../artifacts/terminal/viewer/natural_language_composition.json)。首次线上验证发现 sphere 尺寸格式和新旧 JSON 提示冲突，已明确字段及尺寸约束、统一组合生成格式，并加入工具级有界纠错回归；这不代表任意自然语言和任意互联网模型都已覆盖。

窗口默认运行，空格切换暂停；双击左键选择物体后 Ctrl＋右键拖动。暂停可重新摆放自由物体，运行时施加外力。右侧 Control 控制执行器。操作和真实桌面验证见 [日常物品与交互](HOUSEHOLD_ASSETS.md)。
