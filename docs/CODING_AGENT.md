# 对话、文件与可更新指令

默认对话使用通用coding提示词、21个文件/网络/Skills/经验等工具，以及当前工作目录和对应工具权限。不会因“机器人”“场景”“天气”等词触发执行或注入领域状态。模型可调用 `load_toolset` 加载 robotics、tasks 或 agents，按需可组合；每轮重置，不继承上一轮工具组。robotics不会顺带加载任务或子Agent工具，也不自动读取窗口/串口/载体状态。

自然语言统一走模型工具循环；天气/场景/设备句式拦截、领域强制回复及自动后台交接已移除。明确的slash入口继续工作；持久任务通过task_submit或/task显式提交。工具结果和领域参数校验继续保留，不用提示词代替权限。

基础session多轮记忆保留：近期用户消息和助手回复进入下一轮，完整历史与总结持久化，/resume可恢复。模型目前最多取最近8条历史消息，并在约12000字符预算内裁剪；不等于完整长会话每轮全量输入。默认不注入机器人回合摘要；主动经验检索与用户harness仍可提供附加上下文。


## 文件操作

从目标项目目录运行 `loop`；启动目录是本次 workspace_root。可直接说“读取 ./README.md 并修改第二段”，或提供绝对路径（含空格时加引号）。

| 工具 | 行为 |
| --- | --- |
| list_files / search_files | 列目录、搜索文本，限制返回数量 |
| read_file | 分页读取 UTF-8 文本并返回 sha256 |
| write_file | 创建文件；覆盖时要求 read_file 返回的当前 sha256 |
| edit_file | 唯一精确文本替换，返回 diff 与原文件备份路径 |
| read_image | 读取本地图片，将实际像素送入视觉模型请求 |
| read_url | 读取公开网页或图片 URL，重定向逐跳校验 |

写入限定在工作目录内，单文件最多 1 MiB；原文件备份在状态目录 `file-backups/`。保护凭据、内部数据库、生成目录及其他 Agent 配置。plan 模式禁止写入；工具仍经过运行时权限检查。当前能力是文件读取、搜索和编辑，不包含任意 shell 执行，也不能凭文件保存回执宣称测试通过。

一次输入可自动读取最多四个文件/网址引用，支持混合文本与图片；图片最多四张、编码内容最多 24 MiB。网页下载沿用 1 MiB 上限。模型还可继续调用工具，Master 最多八轮工具调用，再作一次无工具总结；每轮最多四个调用。引用正文作为用户数据，不能授予权限。失败会带真实错误，不编造内容。

## 视觉模型

图像以 image_url 数据内容传递，Responses 协议转换为 input_image。不会把图片仅作为路径交给模型。

当前 Qwen 文本系列 `qwen-plus` / `qwen-turbo` / `qwen-max` 遇到图片时，从同一 API 地址的模型目录选择 `qwen3-vl-plus`、`qwen3-vl-flash`、`qwen-vl-max`、`qwen-vl-plus` 中首个可用项，缓存该地址的结果。没有可用项则明确失败。请求状态显示实际视觉模型；不更改已保存文本模型、不跨服务商传递 Key。历史仍含图片的后续轮次也走视觉模型。

Provider 配置可设置可选 `vision_model` 覆盖视觉模型 ID；其他模型默认保留选择，需要模型本身支持图片。数据库已有选择优先于 config.json，不能只改全局默认就假定现有 profile 已更新。

2026-09-05 本机实测：原 qwen-plus 返回与图片不符的文字；同地址 qwen3-vl-plus 能描述 logo.png 的无限环、蓝色眼睛和右侧三条接口线，135 个流式文本片段，约 7.25 秒。此为单图检查，不是普遍视觉准确率保证。

## Skills 与 harness

可直接说“把刚才的文件整理流程写成一个 Skill”，或“读取我的 harness，把回复风格改成简洁中文”。

- skill_list / skill_read / skill_write：管理 `~/.loop/skills/<name>/SKILL.md`，生成 YAML frontmatter；目录仅加载名称和简介，按需读取正文。更新支持 expected_sha256，保存原文件备份。
- harness_read / harness_write：管理 `~/.loop/AGENTS.md` 与 `~/.loop/harness/NAME.md`。覆盖需当前 sha256，总指令上限 24000 字符。
- 默认 skill_write、harness_write 为 ask，沿用已有权限设置。Markdown 不会提升工具权限。
- Master 每次模型调用前重新加载目录和指令，同一轮工具写入后即可生效。harness 指令更新与运行中 Python 代码更新不同：编辑项目源码后需重启对应进程才加载新代码；不触发 MuJoCo 重启。

## 验证入口

`LOOP_TASK_AUTOSTART=0 .venv/bin/python -m unittest tests.test_coding_agent tests.test_files tests.test_skills tests.test_task_supervisor tests.test_providers`

多源读取、工具图片消息顺序、连续编辑、权限和路径边界、过期哈希、备份、热加载与视觉路由均有替身测试；实图结果见 `artifacts/terminal/coding_vision_validation.json`。参考来源见[pi 对照记录](../../projects/reports/17_pi_coding_agent_integration.md)。

2026-09-06 首字延迟补测：同一 logo.png、qwen3-vl-plus、全新会话，要求简短描述图形与颜色。从 agent.reply 入口计时（含文件读取与首次视觉型号发现），首个非空正文流片段 2.739 秒，完整回复 7.357 秒，126 个非空文本片段。这是单次测量，不代表平均值；证据 artifacts/terminal/vision_latency_validation.json。
