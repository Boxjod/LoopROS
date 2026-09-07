# 对话、文件与可更新指令

默认对话使用通用coding提示词、工作流 harness、文件/网络/Skills/经验与自编工具，以及当前工作目录和对应工具权限。不会因“机器人”“场景”“天气”等词触发执行或注入领域状态。模型可调用 `load_toolset` 加载 robotics、tasks 或 agents，按需可组合；每轮重置，不继承上一轮工具组。robotics不会顺带加载任务或子Agent工具，也不自动读取窗口/串口/载体状态。

自然语言统一走模型工具循环；天气/场景/设备句式拦截、领域强制回复及自动后台交接已移除。明确的slash入口继续工作；持久任务通过task_submit或/task显式提交。工具结果和领域参数校验继续保留，不用提示词代替权限。

基础session多轮记忆保留：近期用户消息和助手回复进入下一轮，完整历史与总结持久化，/resume可恢复。模型目前按完整对话组最多取最近32条历史消息，并在约12000字符预算内裁剪；不等于完整长会话每轮全量输入。默认不注入机器人回合摘要；主动经验检索与用户harness仍可提供附加上下文。


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

一次输入可自动读取最多四个文件/网址引用，支持混合文本与图片；图片最多四张、编码内容最多 24 MiB。网页下载沿用 1 MiB 上限。模型还可继续调用工具，Master 最多二十四轮工具调用，再作一次无工具总结；每轮最多四个调用。引用正文作为用户数据，不能授予权限。失败会带真实错误，不编造内容。

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


## Session task 与工作反馈（2026-09-07）

Session 是保存对话的容器，task 是具体工作目标；一个会话可拥有多个 task，各自使用独立 ID，task 通过 session_id 记录归属。当前前台工作记录随会话保存，后台目标由 `/task` 或 task_submit 单独提交。`/new` 创建新会话和空任务，`/new 任务描述` 可同时设置目标（不会自动执行），`/resume ID` 恢复原目标、计划、验收条件、最近工具回执与错误反馈。后续输入继续推进同一任务；不因一次回复或一次工具成功自动换 task。旧历史在读取时补齐任务元数据，恢复中断回合标为 needs_review，不重放执行。

`session_task_read` 读取当前任务；`session_task_update` 维护 goal、plan、checks、progress、next_step、state。complete 必须通过针对**当前回合宿主实际观察回执**的 checks（tool、path、equals，可带 arguments），文字声明和旧回合证据不能直接完成新一轮验收。检查只证明所选条件；模型仍需使检查对应用户目标，返回码零不能证明真机动作成功。每次模型调用注入紧凑任务状态，完整历史仍独立保存；每个工具结果到达终端后保存检查点。对话未声明可验证条件时保持待输入或待检查，不冒充执行成功。

后台任务仍由 `/task`、task_submit、定时或事件入口显式提交，拥有独立监督器；手动提交记录当前会话归属，定时/事件产生的全局任务没有会话归属。新建/恢复 Session 不启动它们。前台 task 工具不授予后台任务修改会话的能力。

默认工作流位于 `configs/workflow_harness.md`，强调检查→操作→执行验证→观察错误→修正→验收。可用 `harness_read {"path":"harness/workflow.md"}` 读取默认内容；首次覆盖无需 expected_sha256，之后按当前哈希修改。用户覆盖存 `~/.loop/harness/workflow.md`，下一次模型调用生效；权限和重复失败限制由代码执行，不由 Markdown 授权。模型每轮工具预算从 8 增至 24；同一工具与同一参数失败两次后阻止原样重试，修改代码哈希或参数后可重新检查，不无限循环。

## 自编可移植工具与调试

| 工具 | 行为 |
| --- | --- |
| tool_read | 列出工具或读取指定工具的源码、说明和 sha256 |
| tool_write | 保存带说明的 Python 工具；语法错误返回行列诊断，不写文件；覆盖需当前哈希，保存备份 |
| tool_run | 执行已读取哈希对应版本；参数是 CLI 字符串，工作目录是当前 workspace，复用限时/取消/输出限制；返回真实 stdout、stderr、returncode 和报告路径；完整 stdout 是 JSON 时额外返回 output |
| python_check | 不执行、不导入地检查工作区 Python 文件，返回语法行列错误和 import 名称；不宣称依赖已安装或运行通过 |

工具包是 `~/.loop/tools/NAME.json`，包含 version=1、name、description、source。复制 tools 目录即可带到另一台 Loop 安装；源码用相对工作区路径，依赖目标环境已有标准库或依赖，不自动安装依赖。工具不会导入到 Loop 宿主进程，修改后下一次调用直接生效。

默认 tool_write/tool_run 为 ask；持续授权可使用 `/permissions allow tool_write` 和 `/permissions allow tool_run`。tool_run 使用独立执行授权，并尊重 run_python 的显式 deny；plan 禁止编写和执行工具。工具以宿主用户权限运行，继承已有 Python runner 的凭据环境过滤；它不是 OS 或硬件隔离沙箱。

验证：`PYTHONPATH=tests .venv/bin/python -m unittest test_workflow_harness test_session_resume test_coding_agent test_skills -q`；真实 Python 失败→源码修复→结构化输出验收、复制工具包运行、陈旧哈希/审批/deny、相同失败限次、harness 热更新、/new 和 /resume 无执行均有覆盖。模型选择工具使用替身，未调用线上 API。

2026-09-07 `/new` 入口修复：允许可选多词任务描述；`/tasks` 在没有未完成后台任务时显示当前 Session 的 task ID、状态与目标。裸 `/new`、补全打开后回车、带中文描述、检查点中的新 ID 与空历史均经真实 PTY 验证。运行中的旧终端需重启加载代码。

2026-09-07 任务归属修订：左右键和默认 task_status 只列当前 session_id 的未完成任务，通知也按会话过滤。`/tasks all` 显式查看历史、其他会话及无归属任务；按明确 ID 查看/恢复/取消仍可用，不自动改归属。旧任务只保留、不删除、不猜测归属；旧前台 task 与 Session 共用的 ID 会稳定迁移为独立 ID。

2026-09-07：执行中的用户追加消息可在模型/工具边界并入当前前台目标，不再必须等前一轮完全结束。新要求先用于重新判断未执行动作，已完成回执保留；介入不自动创建后台 task 或增加工具预算，见 [TERMINAL](TERMINAL.md)。


### 完整 Skill 包按需展开（2026-09-07）

skill_read 支持可选 path（包内相对路径）、offset/limit（1起始行分页），默认读取 SKILL.md。返回 references/scripts/assets 各目录最多100个直接文件的清单；深层文件按确切路径读取。读取不执行脚本，不安装依赖。越界路径、外部符号链接、凭据与内部数据库按既有文件边界拒绝；skill_list/skill_read 纳入权限表，禁止目录读取时也停止自动目录注入。用户角色和技能包保持 ~/.loop 的现有入口。

自动 Skill 目录注入有约12000字符预算，完整目录可用 skill_list 按需查阅；单个被发现 SKILL.md 限96000字节。上下文窗口、无损 /compact 与长工具回执预算见 [会话上下文](SESSION_MEMORY.md#2026-09-07无损上下文视图)。
