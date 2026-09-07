# Loop ROS 终端规范

2026-09-05。产品名 **Loop ROS**，项目目录为 `LoopROS`，启动器为 `./loop`。交互终端是默认用户入口；TTY 默认使用 prompt_toolkit 主屏行内编辑器，输入随内容展开，输出保留在终端原生滚动历史、Chat Completions 流式文本／接口返回的推理内容，以及排队补充。未提供任意文件编辑或 shell Agent。

终端对话现在由 Master Agent 承接，新增子任务委派、消息、状态和取消。Master 后台请求期间仍可使用管理指令；详见 [多 Agent 规范](AGENT_RUNTIME.md)。原有对话工具之外，Master 另获 Agent 管理工具，子 Agent 和定时任务不自动继承该权限。

扩展版新增权限审批、plan/sim、诊断及模拟机械臂控制；完整42入口清单及与旧指令的边界见 [CONTROL_SURFACE](CONTROL_SURFACE.md)。move_sim/devices已作为受权限检查的工具注册，管理员审批指令仍不向模型开放。

## 输入、附件与任务队列（2026-09-05）

- 输入框紧跟对话输出，不固定贴底；菜单关闭、输入收缩后按实际内容高度重新绘制，避免将旧渲染高度变成空白历史。保留上下分隔线、多行输入及原生滚动历史。
- 已提交的用户消息（含排队回显）使用深灰底色与浅色文字；每行结束重置颜色，避免影响助手输出和编辑区。样式只用于显示，历史记录保存原始文本。
- 持久后台任务用 `/tasks cancel ID` 取消，用 `/tasks stop` 停止监督服务及其工作进程；任务记录保留，不回滚已执行动作。服务可由 `/tasks start` 或新任务自动启动，详见 [持久任务](TASK_RUNTIME.md)。
- 输入为空且无附件时，←/→ 打开并切换当前运行任务面板；`/tasks` 也可打开。只列出 running 状态，未启动、等待、暂停和已结束任务不进入切换列表；任务停止运行后自动移出，没有运行任务时显示 No running tasks。↑/↓ 选择 View details、Cancel task，Enter 执行，Esc 关闭。历史记录仍保留，可用 `/tasks status ID` 查看；切换只改变选中项，不取消任务或将新消息发给该任务。输入非空时保留编辑功能；有候选菜单时方向键优先选择候选。
- `/resume` 与 `/permissions` 候选为纵向列表，↑/← 上一项、↓/→ 下一项、Enter 选择，支持输入筛选，PgUp/PgDn 滚动 Actions 内容。
- `/permissions default` 恢复默认规则；`plan` 只规划；`cautious` 对所有注册动作询问；`yolo` 对所有注册动作放行并进入 sim。切换配置覆盖已有逐项规则，随后可用 allow/ask/deny ACTION 定制，面板显示 custom。配置持久化；YOLO 不增加工具、shell 或未实现的硬件驱动，也不自动执行操作。权限配置仅操作员入口可修改。
- 方向键、Home/End 编辑光标；Enter 发送，忙碌时加入 FIFO 队列；Alt-Enter 或 Ctrl-J 换行。多行粘贴保留换行，不自动提交。输入历史仅保存在当前会话内。
- 不接管鼠标，滚轮／滚动条／终端翻页快捷键用于回看；回到底部的操作由终端提供。方向键定位输入光标。无固定分栏、固定输入高度或最低窗口尺寸要求；调整尺寸后输入自动重排。回看时是否跟随新输出由终端设置决定。
- `/attach "/path/with spaces/image.png"` 添加附件，也可直接拖入图片／视频路径后按 Enter 添加，再输入说明并发送；支持带引号／转义空格的路径和本地 file:// URI。最多四个文件。`/detach` 清除待发附件。只带附件时按 Enter 也可发送。支持 PNG/JPEG/WebP/GIF；单图 ≤8 MiB，总编码附件 ≤24 MiB。图片作为数据发送给当前服务商，需要视觉模型；不自动更换模型或上传公共链接。
- 视频支持 MP4/MOV/MKV/WebM/AVI，文件 ≤100 MiB，需要本地 ffmpeg。抽取开头约30秒内每5秒一帧、最多六帧，缩放至768像素内发送；不播放原视频、不包含音轨，也不表示覆盖整段视频。Ctrl-V 或 `/paste` 从系统剪贴板添加 PNG 图片，保留正在编辑的文字；Linux 需要 Wayland 的 wl-paste 或 X11 的 xclip。Ctrl-Shift-V 仍由终端负责粘贴文字／路径。
- `/queue` 查看等待消息，`/queue clear` 清空；最多20条。附件随各自消息冻结。Esc 或 `/cancel-turn` 请求取消当前 Master 并暂停队列；`/queue resume` 恢复。Ctrl-C 在输入非空时清空输入；空输入时若有活动任务或未暂停队列，则请求停止并暂停队列，空闲或队列已暂停时保存退出；空输入 Ctrl-D 和 `/exit` 同样保存退出。取消不回滚已执行工具，阻塞请求／工具须返回或超时后才能结束；取消后不再执行后续工具。退出也会等待活动调用收尾。
- `/stop` 保留模拟停止和取消子 Agent 的含义，并在交互终端中取消当前 Master、暂停队列。`/cancel-turn` 不取消独立子 Agent，后者用 `/stop-agent ID` 管理。
- 模型异常会保留并暂停队列。对话检查点与完整事件记录保存在 state-dir 下的 `conversation.sqlite`（0600）；下次同一服务地址／模型／协议启动恢复上下文、草稿与等待队列，恢复的队列暂停，需 `/queue resume` 才执行；屏幕回看容量由终端滚动缓冲配置决定，退出不清屏。磁盘事件记录另行保留；`/clear` 清除模型上下文，不删除历史事件记录。`/history` 省略媒体编码。已取消轮次的用户输入和已收到的部分输出保留在事件记录中，不作为已完成答复加入模型上下文。

流式未完成行在输入上方预览；超出窗口宽度的长段会逐段写入原生滚动历史，无需等待模型换行。完整行和结束的段落也写入滚动历史。输出与输入统一重绘，避免无换行片段覆盖提示符。附件转换在后台进行，转换期间输入的下一条草稿不会被清空；失败时恢复原输入。

Chat Completions 使用 SSE 显示答复及服务端实际返回的 `reasoning_content`，也显示工具名称和结果；不推测未返回的内部推理。Responses 协议目前整轮返回。流式失败不自动重试，避免重复执行工具。参考 [prompt_toolkit 文档](https://python-prompt-toolkit.readthedocs.io/en/master/pages/full_screen_apps.html) 与 [Qwen 流式接口](https://www.alibabacloud.com/help/zh/model-studio/stream)。

非 TTY 和 `--once` 保留文本入口；上述编辑器专用命令仅在交互 UI 中提供，不计入 `/commands` 的42个后端入口。定时聊天继续使用独立上下文，排在用户队列之后。

## 启动和 API

在项目目录运行 `./loop`；启动器优先使用项目 `.venv`，不存在则用当前 Python。使用安装环境的 Python 也可 `python -m loop_robot`（Python 包名固定，与源码目录名称无关；不自动切虚拟环境）。

```bash
cd /home/boxjod/Workspace/box2net/LoopROS
./loop
```

终端输入 `/key`，隐藏输入 Key，仅存在当前进程；也支持预先配置 `DASHSCOPE_API_KEY`，或通过 `/key save` 显式保存到用户目录的凭据文件。不要把 Key 粘贴到聊天或项目配置；全局目录与安全约定见 [USER_HOME](USER_HOME.md)。默认 `qwen-plus`、北京 DashScope OpenAI-compatible endpoint；地区必须匹配 Key，国际或 Coding Plan 用户修改 base_url／model，不能直接混用服务套餐。[Qwen 官方兼容 API](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)

`config.example.json` 是默认配置；可用被 Git 忽略的 `config.local.json` 覆盖，或 `--config 路径`。该文件由可信用户维护，不能让聊天模型改写。HTTP 仅允许 loopback，其他地址需 HTTPS；拒绝带凭据 URL 和重定向转发认证头。

新增 Loop Switch 后：上述 llm/expert 配置作为首次导入种子，此后 providers.sqlite 的配置与槽位选择优先。用 `./loop-switch` 或 `/switch` 管理，外部修改后 `/switch reload` 生效；详细规则见 [MODEL_SWITCH](MODEL_SWITCH.md)。

对话使用有限上下文及Master 最多 8 轮工具调用及 1 轮无工具结果总结（独立 ChatAgent 默认 4 轮）。工具包含 status、run_sim、generate_scene、expert_advice，以及新增 web_search、web_fetch、web_weather；完整工具注册以 terminal/app.py 为准。联网用法和边界见 [联网工具](WEB_TOOLS.md)。仿真动作仍经过 core Loop，写 episodes.sqlite，并返回 Reviewer 结果。场景生成单独保存 scene／report，未经过物理任务成功评审。新增 /scene、/scene --complex、/complex、/expert-key 见 [场景规范](SCENES.md)。尚未提供通用机器人自然语言执行或 VLM 视觉裁判。纯对话不是物理任务，不伪造物理 Reviewer 评分。

## 快捷指令

| 指令 | 行为 |
| --- | --- |
| `/help`、`/shortcuts`、`快捷指令` | 帮助 |
| `/key` | 隐藏输入进程内 Key |
| `/model [模型名]` | 查看／切换对话模型；切换清空当前上下文，不写配置 |
| `/status`、`推理状态` | pi05／ACT 本终端服务状态 |
| `/sim` | MuJoCo 双关节执行与评审 |
| `/policy pi05 start`、`开始PI推理` | 确认后启动配置的 pi0.5 推理服务 |
| `/policy act start`、`开始ACT推理` | 确认后启动配置的 ACT 推理服务 |
| `/policy pi05 stop`、`停止PI推理` | 停止本终端启动的 pi0.5 服务 |
| `/policy act stop`、`停止ACT推理` | 停止本终端启动的 ACT 服务 |
| `/policy pi05 status`、`/policy act status` | 单服务状态 |
| `/after 30 /status` | 30 秒后执行一次 |
| `/every 60 /status` | 每次执行结束后间隔 60 秒再执行 |
| `/after 30 请解释刚体仿真` | 定时对话，可能产生 API 费用 |
| `/jobs`、`/cancel ID` | 任务记录／取消等待任务 |
| `/clear` | 清除本次聊天上下文 |
| `/exit`、空输入时 Ctrl-D | 关闭终端及其启动的策略服务 |

定时任务只允许普通对话、/status、/sim，禁止 /policy、/key 及嵌套定时任务。定时对话有独立上下文，不污染交互会话。任务写入 artifacts/terminal/jobs.sqlite；只在终端运行时执行，不安装 daemon／cron。串行执行，长 API 请求会推迟 timer，不是实时调度。异常任务变为 failed，不自动重试；重启时 running 变 interrupted，等待任务到期最多补一次，不回放遗漏的每个周期。最多 100 个等待任务；同一 state-dir 只运行一个终端。

## pi0.5／ACT 服务适配

当前实现是**服务生命周期调度**，不是策略动作解码或真机 rollout。`services.pi05.argv`／`services.act.argv` 默认空，真实状态显示 NOT_CONFIGURED。

配置 argv 必须是独立推理服务的前台进程参数数组；cwd 指向对应模型仓库。不要填写凭据、daemonizing shell、真机控制命令或包含 start-act-control 的旧脚本。启动前由终端明确确认，不经 shell 拼接。默认一次一个策略服务，避免未经测量的 GPU 共驻留；RUNNING 仅表示进程存活，不是模型 READY。退出时关闭本终端子进程组，不接管外部既有服务；没有健康探测、自动重启、显存测量或脱离终端运行保证。

参考旧仓库 `loopmaster_agentic/cli.py` 的交互入口、`agents/interaction_catalog.py` 的快捷指令查表、`skills/control/act_model_control/policy.py` 的服务／控制区分。旧 `loopmaster_model_servers.sh` 混有控制、切换和其他副作用，本版未直接调用。它的具体权重、设备、进程参数不凭空填入新配置。

## 验证与边界

27 项测试通过，包括 API 请求替身、工具反馈循环、周期／一次任务、失败停止、指令权限和临时替身进程启动／关闭。MuJoCo 完整测试通过；真实 Qwen API、pi0.5／ACT 权重服务及真机连接未执行。配置好 API 后具备交互调用路径，但不把 mocked API 测试说成线上联通验证。

交互会话保存在 `conversation.sqlite`；定时任务文本／结果、仿真证据、策略服务日志保存于 artifacts/terminal，应视为用户数据。日志目前无自动轮转；生产环境需另设容量策略。本版没有任意命令执行、模型自主开启进程或定时真机动作。

回复排版：助手每个连续输出块仅在开头显示 `●`，后续正文／列表缩进，空行不加标签；推理块使用 `✻`，用户输入使用 `❯`。工具调用以 `● name(arguments)` 独立显示，结果以 `↳` 跟随。保留完整行提交与未完成行统一重绘，避免再次引入输出覆盖。

MuJoCo窗口：`/viewer`打开最近场景（无场景自动生成默认桌面），`/viewer status`查询，`/viewer stop`关闭；自然语言“启动仿真器”也直接执行。仅window_open=true代表窗口已创建；/sim仍是离线关节测试。未指定场景参数时自动补合理默认值，不额外询问确认。

2026-09-05 输入优化验证：13项交互／媒体／流式测试通过，含6×24、12×40、24×80窗口的pyte＋PTY中文长段推理、同步光标插入和队列显示。剪贴板PNG读取使用进程替身验证，未读取用户实际剪贴板；媒体线上模型理解未测。


工具返回默认摘要显示：例如`● Web Search("查询词")`、`↳ 1 search · 3 results · 1.2s · /details 58`。时间为该次工具事件开始到返回的本地单调时钟差值，不固定填写。天气显示Weather与城市，网页显示Web Fetch与URL；过长参数截短。大段JSON留在conversation.sqlite，模型仍收到原有工具结果上下文，不用显示摘要替换模型证据。

`/details`查看最近一次工具完整参数和返回，`/details 58`查看对应结果ID，重启后本地记录仍可查看。这里采用原生终端滚动历史中的摘要＋按命令展开，不是鼠标点击或原地收起。错误、无地点结果、窗口未确认打开、排队中、评审fail/inconclusive继续显示关键信息。详情由用户请求时打印，不自动展开；工具自身的抓取/结果长度限制不改变。显式/status、/node status等诊断命令仍保留它们的结构化结果。

实现入口：[tool_display](../terminal/tool_display.py)、[SessionStore.tool_details](../terminal/session.py)、[Terminal.append](../terminal/interactive.py)。验证包含长结果落盘并重启读取、摘要保留失败状态、24/40/80列中文流式＋同步输入／排队的PTY显示以及/details展开。最终结果见[RUNBOOK](RUNBOOK.md)。

生成成功后自动打开MuJoCo。新增`/models`、`/model-load NAME`和`/viewer pause|resume|reset|step N|speed X|camera VIEW|actuate VALUES|reload`，见[控制与模型库](MUJOCO_CONTROL.md)。窗口控制证据在viewer/control.sqlite，独立于离线关节测试；单次指令回执不代表抓取成功。

### Slash 命令补全

输入 `/` 自动显示命令及简短用法，继续输入按前缀筛选，例如 `/s` 匹配 `/switch`、`/status`、`/sim` 等。Tab 或 ↑/↓ 选择候选，Enter 直接执行已选命令；未选择时按前缀使用第一个匹配项，完整命令优先。例如 `/per` + Enter 执行 `/permissions`。无匹配仍按原输入处理。Esc 先关闭候选菜单，再按 Esc 才停止活动任务。输入参数、普通文本或在命令中间编辑时不弹补全。菜单随终端空间显示，不要求放大窗口。 输入、退格、粘贴和移回行尾都会刷新候选；Esc 关闭后保持关闭，继续编辑才重新匹配。权限与会话参数补全允许多个空格或制表符，多行草稿不触发命令补全。

流式回复：普通文本收到增量立即显示，不等待工具总结回调；收到有效 `finish_reason` 即结束读取，不继续等待 `[DONE]`。真实提前断流仍报错，已显示内容保留。失败时只有已有排队消息才暂停队列，使用 `/queue resume` 继续；没有排队消息时可直接发下一条。仿真工具的最终结果仍以实际回执总结为准。

历史会话入口：`/resume` 列表及选择菜单、`/history [ID]` 查看消息和每轮总结、`/new` 新会话。队列继续改为 `/queue resume`。持久化及上下文规则见 [SESSION_MEMORY](SESSION_MEMORY.md)。

输入区固定在终端可用区域底部，上下使用灰色横线，宽度随终端变化。编辑窗口仅占实际输入行数，多行清空或菜单关闭后立即收缩；占位提示随宽度截短，避免在最后一列换出空行。保留原生终端滚动历史。等待消息显示在上横线上方，最多预览最近三条（窄窗口自动减少），显示队列总数；空输入提示 `Press up to edit queued messages`。按 ↑ 取回最近一条及附件，移出等待队列，编辑后 Enter 重新入队；取回不自动停止正在运行的任务。暂停队列用 `/queue resume` 继续，完整内容可用 `/queue` 查看。


## 对话结果与工程证据

自然语言生成桌子、打开仿真器统一经过Master对话入口，工具返回记录为result事件并由界面折叠，`/details`可展开完整结果；不能绕过事件记录直接把工具JSON当助手回复。普通机器人问答优先自然语言，明确请求的JSON/代码仍可输出。

力矩计算的最终结论依据工具回执，明确条件性估算、电流/Kt口径及非实测边界。涉及电流到力矩的请求会暂缓显示模型工具前言，避免先流出未经验证的口径声明；一般问答仍保持流式输出。当前运行时权限每轮工具循环刷新；取消后迟到的工具回执继续留档，但停止后续动作和成功答复，已执行效果不会被宣称自动回滚。

真实PTY对话评估与剩余限制见[终端harness评估](../../projects/reports/13_terminal_harness_evaluation.md)。

交互 slash 结果按字段/列表排版，`/permissions`、`/mode` 按 Allow/Ask/Deny 分组，保留真实模式与硬件状态。`/permissions` 显示后可选择 ask/deny/allow，再选择动作，Enter 应用；仅浏览候选不会修改规则。非交互 dispatch 的 JSON 返回格式保留。`/resume` 会话候选支持方向键选择、Enter 直接恢复，成功后输入消息继续当前选中会话；历史总结显示可读文本。

操作面板：slash 命令的结构化结果、权限设置、会话列表与历史预览显示在输入区上方的 `Actions` 面板，替换上一次面板内容，不作为 Master 回复，也不加入聊天上下文。PgUp/PgDn 滚动长内容，Esc 关闭；候选菜单打开时 Esc 先关候选。方向键/Tab 仍用于选择操作，Enter 执行。普通聊天提交后关闭面板；完整操作展示单独记录为 Operator 事件。工具调用使用 `Tool ›` 标记，实际返回、耗时与 /details 入口仍单独显示。

耗时的 `/viewer`、`/scene`、`/complex`、`/sim`、`/models` 和 `/model-load` 在后台执行，期间可编辑或排队下一条消息。结果显示在 Actions 面板；取消后迟到的结果注明取消状态，不声称已执行效果自动回滚。只附加媒体也可直接 Enter 发送；附件转换失败时保留原输入与期间新写的草稿，以换行分隔。

文件编辑、图片与网址读取、Skills／harness 热加载及视觉模型路由见 [Coding Agent](CODING_AGENT.md)。
