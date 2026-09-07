# Loop ROS 终端规范

2026-09-05。产品名 **Loop ROS**，项目目录为 `LoopROS`，启动器为 `./loop`。交互终端是默认用户入口；TTY 默认使用 prompt_toolkit 主屏行内编辑器，输入随内容展开，输出保留在终端原生滚动历史、Chat Completions 流式文本／接口返回的推理内容，以及排队补充。未提供任意文件编辑或 shell Agent。

终端对话现在由 Master Agent 承接，新增子任务委派、消息、状态和取消。Master 后台请求期间仍可使用管理指令；详见 [多 Agent 规范](AGENT_RUNTIME.md)。原有对话工具之外，Master 另获 Agent 管理工具，子 Agent 和定时任务不自动继承该权限。

扩展版新增权限审批、plan/sim/real、诊断及模拟机械臂控制；完整42入口清单及与旧指令的边界见 [CONTROL_SURFACE](CONTROL_SURFACE.md)。move_sim/devices已作为受权限检查的工具注册，管理员审批指令仍不向模型开放。

## 输入、附件与任务队列（2026-09-05）

- 输入框紧跟对话输出，不固定贴底；菜单关闭、输入收缩后按实际内容高度重新绘制，避免将旧渲染高度变成空白历史。保留上下分隔线、多行输入及原生滚动历史。
- 已提交的用户消息（含排队回显）使用深灰底色与浅色文字；每行结束重置颜色，避免影响助手输出和编辑区。样式只用于显示，历史记录保存原始文本。
- 持久后台任务用 `/tasks cancel ID` 取消，用 `/tasks stop` 停止监督服务及其工作进程；任务记录保留，不回滚已执行动作。服务可由 `/tasks start` 或新任务自动启动，详见 [持久任务](TASK_RUNTIME.md)。
- 输入为空且无附件时，←/→ 在对话和当前 Session 所属的未完成任务之间切换（对话 → 任务1 → … → 对话）；右键进入第一个任务后按左键可直接退回对话，Esc 可关闭面板，均不取消任务或退出程序。没有未完成任务时再次按左/右键可关闭提示；`/tasks` 也可打开。包含 queued、running、retry_wait 与 waiting_* 状态；仅 succeeded/cancelled 自动移出，没有当前会话的未完成后台任务时显示当前前台工作记录。等待任务显示阻塞原因。↑/↓ 选择 Enter session 或 Close session，Enter 执行，Esc 关闭。其他会话及无归属历史任务不进入切换列表，记录仍保留，可用 `/tasks all` 与 `/tasks status ID` 查看；切换只改变选中项，不取消任务或将新消息发给该任务。输入非空时保留编辑功能；有候选菜单时方向键优先选择候选。
- 命令候选、左右键任务切换和 Actions 面板统一显示在输入框下分隔线之后，使用普通布局行，不使用悬浮菜单，不覆盖上方对话。候选出现时暂时使用同一提示区域；Esc 关闭候选后可继续查看 Actions。列表按可用高度显示并跟随选中项滚动。
- `/resume` 与 `/permissions` 候选为纵向列表，↑/← 上一项、↓/→ 下一项、Enter 选择，支持输入筛选，PgUp/PgDn 滚动 Actions 内容。
- `/permissions default` 恢复默认规则；`plan` 只规划；`cautious` 对所有注册动作询问；`yolo` 对所有注册动作放行并进入 sim。切换配置覆盖已有逐项规则，随后可用 allow/ask/deny ACTION 定制，面板显示 custom。配置持久化；YOLO 不增加工具、shell 或未实现的硬件驱动，也不自动执行操作。权限配置仅操作员入口可修改。
- 方向键、Home/End 编辑光标；Enter 发送，忙碌时加入 FIFO 队列；Alt-Enter 或 Ctrl-J 换行。多行粘贴保留换行，不自动提交。输入历史仅保存在当前会话内。
- 不接管鼠标，滚轮／滚动条／终端翻页快捷键用于回看；回到底部的操作由终端提供。方向键定位输入光标。无固定分栏、固定输入高度或最低窗口尺寸要求；调整尺寸后输入自动重排。回看时是否跟随新输出由终端设置决定。
- `/attach "/path/with spaces/image.png"` 添加附件，也可直接拖入图片／视频路径后按 Enter 添加，再输入说明并发送；支持带引号／转义空格的路径和本地 file:// URI。最多四个文件。`/detach` 清除待发附件。只带附件时按 Enter 也可发送。支持 PNG/JPEG/WebP/GIF；单图 ≤8 MiB，总编码附件 ≤24 MiB。图片作为数据发送给当前服务商，需要视觉模型；不自动更换模型或上传公共链接。
- 视频支持 MP4/MOV/MKV/WebM/AVI，文件 ≤100 MiB，需要本地 ffmpeg。抽取开头约30秒内每5秒一帧、最多六帧，缩放至768像素内发送；不播放原视频、不包含音轨，也不表示覆盖整段视频。Ctrl-V 或 `/paste` 从系统剪贴板添加 PNG 图片，保留正在编辑的文字；Linux 需要 Wayland 的 wl-paste 或 X11 的 xclip。Ctrl-Shift-V 仍由终端负责粘贴文字／路径。
- `/queue` 查看等待消息，`/queue clear` 清空；最多20条。附件随各自消息冻结。Esc 或 `/cancel-turn` 请求取消当前 Master 并暂停队列；`/queue resume` 恢复。Ctrl-C 在输入非空时清空输入；空输入时若有活动任务或未暂停队列，则请求停止并暂停队列，空闲或队列已暂停时保存退出；空输入 Ctrl-D 和 `/exit` 同样保存退出。取消不回滚已执行工具，阻塞请求／工具须返回或超时后才能结束；取消后不再执行后续工具。退出也会等待活动调用收尾。
- `/stop` 保留模拟停止和取消子 Agent 的含义，并在交互终端中取消当前 Master、暂停队列。`/cancel-turn` 不取消独立子 Agent，后者用 `/stop-agent ID` 管理。
- 模型异常会保留并暂停队列。对话检查点与完整事件记录保存在 state-dir 下的 `conversation.sqlite`（0600）；每次启动新建会话，通过 `/resume` 显式恢复同一服务地址／模型／协议的历史上下文、草稿与等待队列，恢复的队列暂停，需 `/queue resume` 才执行；屏幕回看容量由终端滚动缓冲配置决定，退出不清屏。磁盘事件记录另行保留；`/clear` 清除模型上下文，不删除历史事件记录。`/history` 省略媒体编码。已取消轮次的用户输入和已收到的部分输出保留在事件记录中，不作为已完成答复加入模型上下文。

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

`configs/config.example.json` 是默认配置；可用被 Git 忽略的 `config.local.json` 覆盖，或 `--config 路径`。该文件由可信用户维护，不能让聊天模型改写。HTTP 仅允许 loopback，其他地址需 HTTPS；拒绝带凭据 URL 和重定向转发认证头。

新增 Loop Switch 后：上述 llm/expert 配置作为首次导入种子，此后 providers.sqlite 的配置与槽位选择优先。用 `./loop-switch` 或 `/switch` 管理，外部修改后 `/switch reload` 生效；详细规则见 [MODEL_SWITCH](MODEL_SWITCH.md)。

对话使用有限上下文及Master 最多 8 轮工具调用及 1 轮无工具结果总结（独立 ChatAgent 默认 4 轮）。工具包含 status、run_sim、generate_scene、expert_advice，以及新增 web_search、web_fetch、web_weather；完整工具注册以 terminal/app.py 为准。联网用法和边界见 [联网工具](WEB_TOOLS.md)。仿真动作仍经过 core Loop，写 episodes.sqlite，并返回 Reviewer 结果。场景生成单独保存 scene／report，未经过物理任务成功评审。新增 /scene、/scene --complex、/complex、/expert-key 见 [场景规范](SCENES.md)。尚未提供通用机器人自然语言执行或 VLM 视觉裁判。纯对话不是物理任务，不伪造物理 Reviewer 评分。

## 快捷指令

| 指令 | 行为 |
| --- | --- |
| `/help`、`/shortcuts`、`快捷指令` | 帮助 |
| `/key` | 隐藏输入进程内 Key |
| `/model [模型名]` | 交互模式下列出当前 URL／Key 的模型并选择；带参数直接切换，清空当前上下文，不写配置 |
| `/fast [on\|off\|status]` | 请求 Fast／标准档或查询档位；无参数切换，当前客户端有效，实际处理档位看回执 |
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

定时任务只允许普通对话、/status、/sim，禁止 /policy、/key 及嵌套定时任务。定时对话有独立上下文，不污染交互会话。任务写入 artifacts/terminal/jobs.sqlite；只在终端运行时执行，不安装 daemon／cron。串行执行，长 API 请求会推迟 timer，不是实时调度。异常任务变为 failed，不自动重试；重启时 running 变 interrupted，等待任务到期最多补一次，不回放遗漏的每个周期。每个运行槽最多 100 个等待任务；同一 state-dir 可同时运行多个终端，各自维护定时任务，附加窗口的 jobs.sqlite 位于 terminals/<槽号>/。

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

底部状态栏的 `tasks N` 表示当前 Session 的未完成持久任务数（包含排队、运行、重试和等待），不含成功、取消或其他会话任务；`queued N` 仍表示待发送提示数量。任务数使用 SQL COUNT，在既有每秒任务轮询时刷新，绘制每帧不读取完整任务记录。

三反引号代码块：回复和历史回放显示 `Code · 语言` 标记及独立背景，保留代码换行、缩进和字面 `**`；代码内不应用粗体转换。流式输出可跨片段识别围栏。仅渲染标准三反引号块，不提供点击执行、自动审批或机器人动作入口。验证：`test_markdown_code`、`test_slash_terminal`。

2026-09-07 窗口缩放：一帧内的布局、输入框横线和底部提示使用同一个终端尺寸快照；横线右侧留一列空白，避免触及终端自动换行边界。连续改变宽度时仍保留中文草稿，缩放不清空会话历史或滚动缓冲。验证入口为 `tests/test_resize_terminal.py` 与 `tests/test_terminal_render.py`。

同日修正：上述尺寸快照与留白不足以处理终端重排。缩窄后，旧输入区的横线、队列及底部提示可能产生额外行；擦除前按旧屏幕内容修正相对游标行数，尺寸变化先清理再重绘。新增 `test_resize_reflow.ResizeReflowTests` 使用外置 `@xterm/headless` 6.0.0，覆盖实际重排与滚动历史，而非仅用 pyte 的裁剪式 resize。测试依赖通过 `XTERM_HEADLESS_MODULE` 指定，不加入产品依赖。

2026-09-07：`/` 首页最多五项，顺序为 `/model`、`/mode`、`/permissions`、`/resume`、`/help`；向下继续浏览其他命令。`/history` 不在裸 `/` 菜单展示，显式输入仍兼容。`/mode` 打开 sim／real／plan 参数选择，不自行启动仿真或硬件。`/model` 只向当前 provider 查询模型目录，按公司 A–Z、目录日期从新到旧展示，未返回列表时可手填 ID。

普通文本不启动命令补全；离开 slash 输入时清除候选并保留编辑内容。Enter 只接受仍属于当前有效补全状态的候选。中文与数字输入通过管道和真实 PTY 验证；操作系统输入法候选提交需要实际终端／输入法复测，PTY 不能模拟桌面输入法选字。

输入 `/` 自动显示命令及简短用法，继续输入按前缀筛选，例如 `/s` 匹配 `/switch`、`/status`、`/sim` 等。Tab 或 ↑/↓ 选择候选，Enter 直接执行已选命令；未选择时按前缀使用第一个匹配项，完整命令优先。例如 `/per` + Enter 执行 `/permissions`。无匹配仍按原输入处理。Esc 先关闭候选菜单，再按 Esc 才停止活动任务。输入参数、普通文本或在命令中间编辑时不弹补全。候选始终在输入框下方显示，按终端可用空间减少行数，不要求放大窗口。 输入、退格、粘贴和移回行尾都会刷新候选；Esc 关闭后保持关闭，继续编辑才重新匹配。权限与会话参数补全允许多个空格或制表符，多行草稿不触发命令补全。

流式回复：普通文本收到增量立即显示，不等待工具总结回调；收到有效 `finish_reason` 即结束读取，不继续等待 `[DONE]`。真实提前断流仍报错，已显示内容保留。失败时只有已有排队消息才暂停队列，使用 `/queue resume` 继续；没有排队消息时可直接发下一条。仿真工具的最终结果仍以实际回执总结为准。

历史会话入口：`/resume` 列表及选择菜单、`/history [ID]` 查看消息和每轮总结、`/new` 新会话。队列继续改为 `/queue resume`。持久化及上下文规则见 [SESSION_MEMORY](SESSION_MEMORY.md)。

输入区紧跟对话输出，上下使用灰色横线，宽度随终端变化。命令提示和任务/Actions区域位于输入框下方；输入框不占用菜单悬浮层。编辑窗口仅占实际输入行数，多行清空或菜单关闭后立即收缩；快捷键提示放在输入框下面，按显示宽度截短，避免在最后一列换出空行。保留原生终端滚动历史。等待消息显示在上横线上方，最多预览最近三条（窄窗口自动减少），显示队列总数；空输入时在下方提示 `↑ edit queue · ←/→ tasks`。按 ↑ 取回最近一条及附件，移出等待队列，编辑后 Enter 重新入队；取回不自动停止正在运行的任务。暂停队列用 `/queue resume` 继续，完整内容可用 `/queue` 查看。

窗口缩放时，输入区优先获得高度，流式预览、队列预览和 Actions/补全候选共用剩余空间。窗口只剩 3 行时隐藏下分隔线，2 行时再隐藏上分隔线，1 行时只保留可编辑区；放大后自动恢复。多行草稿可在输入区内部滚动，不截断实际文本。队列仅减少预览、不移除消息；隐藏流式预览不丢弃已接收输出。面板标题、队列省略号按终端显示列宽处理，避免中文和宽字符越界。尺寸变化不清空会话、不执行命令，保持原生终端滚动。


## 对话结果与工程证据

自然语言生成桌子、打开仿真器统一经过Master对话入口，工具返回记录为result事件并由界面折叠，`/details`可展开完整结果；不能绕过事件记录直接把工具JSON当助手回复。普通机器人问答优先自然语言，明确请求的JSON/代码仍可输出。

力矩计算的最终结论依据工具回执，明确条件性估算、电流/Kt口径及非实测边界。涉及电流到力矩的请求会暂缓显示模型工具前言，避免先流出未经验证的口径声明；一般问答仍保持流式输出。当前运行时权限每轮工具循环刷新；取消后迟到的工具回执继续留档，但停止后续动作和成功答复，已执行效果不会被宣称自动回滚。

真实PTY对话评估与剩余限制见[终端harness评估](../../projects/reports/13_terminal_harness_evaluation.md)。

交互 slash 结果按字段/列表排版，`/permissions`、`/mode` 按 Allow/Ask/Deny 分组，保留真实模式与硬件状态。`/permissions` 显示后可选择 ask/deny/allow，再选择动作，Enter 应用；仅浏览候选不会修改规则。非交互 dispatch 的 JSON 返回格式保留。`/resume` 会话候选支持方向键选择、Enter 直接恢复，成功后输入消息继续当前选中会话；历史总结显示可读文本。

操作面板：slash 命令的结构化结果、权限设置、会话列表与历史预览显示在输入区上方的 `Actions` 面板，替换上一次面板内容，不作为 Master 回复，也不加入聊天上下文。PgUp/PgDn 滚动长内容，Esc 关闭；候选菜单打开时 Esc 先关候选。方向键/Tab 仍用于选择操作，Enter 执行。普通聊天提交后关闭面板；完整操作展示单独记录为 Operator 事件。工具调用使用 `Tool ›` 标记，实际返回、耗时与 /details 入口仍单独显示。

耗时的 `/viewer`、`/scene`、`/complex`、`/sim`、`/models` 和 `/model-load` 在后台执行，期间可编辑或排队下一条消息。结果显示在 Actions 面板；取消后迟到的结果注明取消状态，不声称已执行效果自动回滚。只附加媒体也可直接 Enter 发送；附件转换失败时保留原输入与期间新写的草稿，以换行分隔。

文件编辑、图片与网址读取、Skills／harness 热加载及视觉模型路由见 [Coding Agent](CODING_AGENT.md)。

`/new [GOAL]` 新建 Session 及独立 ID 的前台工作记录，可选目标文本只保存、不触发执行。当前会话无未完成后台任务时，`/tasks` 显示当前工作的标题、状态、目标和下一步，避免把后台列表为空误报为没有会话任务。

会话页头、/new、/resume、/sessions、任务面板与反馈显示可读标题；默认从首个及最近用户问题提取短句。会话候选直接插入标题，标题含空格可提交；重名附稳定序号。任务命令接受标题，ID 仅保留内部定位和旧命令兼容。


2026-09-07 执行中介入：普通前台消息在忙碌时仍显示在聊天下方、输入框上方的 Queued 预览；模型调用返回、工具完成后的边界由 UI 线程交给当前工具循环，合并尚未完成的目标。旧模型响应中的未执行工具计划会重新判断，多工具批次中剩余调用以 not_executed 回执配对，不重做已完成动作。正在执行的工具不被强行打断。介入后显示 Steering 回执并从队列移除，保留用户消息到完整历史及本轮经验请求，当前草稿不受影响。

队列暂停、slash 命令执行和定时任务期间不自动并入主会话；恢复仍需 /queue resume。介入不增加本轮工具轮数预算，合并文本限 16000 字符，超额或已到预算尾轮的消息保留队列待后续处理。附件随消息一起介入；↑ 编辑、/queue clear 与消费都在 UI 线程串行处理。外部模型请求及工具运行期间的介入延迟取决于该次调用何时返回，不承诺中断阻塞中的 SSH。


2026-09-07：/context 显示持久历史与当前模型窗口的字符预算；/compact 保留完整历史，仅缩小模型窗口，/compact reset 恢复默认。Agent broker 轮询与通知锁等待移入单独监管线程，避免慢轮询直接阻塞输入事件循环。PTY 验证覆盖慢监管、命令面板与中文流式期间编辑草稿；不改变原生滚动和输入框下方 Actions 面板布局。


2026-09-07 多 Agent 操作：/agents [active|all] 使用任务标题、角色和稳定 @编号展示；Actions 面板刷新状态。/spawn、/send、/result、/agent-messages、/stop-agent 支持目标／角色补全，选择角色或消息收件人后保留输入框供填写正文。/agent-messages 显示实际投递阶段，完成结果明确“Agent返回不等于目标验收”。Agent命令在后台线程运行，允许前台执行中提交独立子Agent；读取、发送、取消仍走统一权限。详见 [Agent交互](AGENT_RUNTIME.md)。

Offline executable Skills: `/skills` lists readable titles; `/skills run|inspect|status|logs|stop TITLE` selects a saved package without a model request, with title completion. `/skills save PROFILE NAME TITLE` exports a process profile. Use `loop node` when no chat API is configured; see [OFFLINE_SKILLS](OFFLINE_SKILLS.md).

## 输入框折叠标签（2026-09-07）

终端 bracketed paste 的多行文字／代码折叠为 `[Paste #1 · 20 lines]`，保持原换行和缩进；手动 Alt-Enter／Ctrl-J 换行仍正常展开编辑。图片附件在输入框中显示 `[Image #2]`，视频为 `[Video #3]`。标签按创建顺序编号，删除其他标签不改变剩余编号。标签是一个编辑单元，左右方向键跨越整个标签。

光标紧邻标签右侧时，第一次 Backspace 高亮该标签，第二次 Backspace 删除整块；删除图片／视频标签也从待发送附件移除对应文件。两次之间移动光标或修改文字会取消选中。普通文字仍按字符退格。Ctrl-C 清空当前文字和附件；不删除源文件。

发送／排队时展开完整文字，不发送内部占位字符；每份媒体在模型输入前附带同编号说明。队列取回会重新折叠多行内容，保留媒体编号；退出恢复保存草稿标签及附件关联。输入历史保留展开文字。粘贴代码位于输入开头时，不因代码以 slash 开头就自动执行命令。

实现：[Composer](../terminal/composer.py)、[按键与提交](../terminal/interactive.py)、[会话草稿](../terminal/session.py)。PTY 验证包含中文流式并行粘贴、两次退格、多图标号、缩窄窗口与重启后手动恢复；不会读取真实系统剪贴板，测试使用本地小图片附件。

### 语义配色与修改预览

终端配色由 `terminal/colors.py` 统一：工具名按类型区分（读取青色、执行紫色、修改黄色、状态绿色）、参数暖黄、成功绿、等待／不确定黄、错误红，助手标记紫色；正文保留可读前景色。使用终端自身字体，以加粗和颜色区分语义，不替用户更换字体。颜色仅用于展示，原始对话／工具回执仍保留原文。

Python／py／python3 围栏代码使用标准库 tokenize 识别关键字、字符串、数字、注释、函数名和内置名称，采用常见编辑器配色；diff／patch 围栏增删行使用绿／红。流式不完整代码保留原文，无法识别部分回退普通代码样式，不执行代码。

文件写入回执增加 lines_added、lines_removed 和 diff_truncated。终端显示修改路径与增删行数，展开最多10行diff，每行最多180字符，超出部分提示 `/details`；完整长度仍遵从原有回执限制。旧回执缺少统计时从已有diff估算。历史回放使用同一配色和有界预览；模型／文件携带的终端控制字符不能作为颜色命令执行。

验证：test_color_output、test_color_terminal、test_markdown_code、test_session_display。真实PTY覆盖彩色Python、实际文件修改的diff、中文草稿并行输入及颜色可见性。

2026-09-08：底部只显示 `Context` 用量/容量，不显示 `Session Tokens`、空闲 `Ready` 或 `queued` 计数；附件数量仅非零显示，执行中保留 Working。粘贴提示统一为 `/paste`，不再固定显示 `Ctrl-V image`；终端自己的粘贴快捷键继续由终端处理。`~` 为请求估算，`?` 为未知。`/context` 查看详细预算，`/compact` 的窗口偏好随会话恢复。统计范围、profile字段及自动压缩边界见 [Session Memory](SESSION_MEMORY.md)。

### 工具调用折叠与本地用量估算

工具调用开始时立即在输入框上方的对话记录显示命令与时间，返回后接着显示彩色结果及代码修改预览；输入框下方不再显示工具调用进度行。连续调用结束后仍可显示 `Tools ▸ N calls` 分组摘要，记录累计耗时与本地用量。按 Ctrl-O（保留草稿）或输入 `/tools` 展开最近一组，`/tools N` 查看指定组；Actions 面板用 PgUp/PgDn 翻页，点击标题的 `[× Close]` 或 Esc 关闭，保留输入草稿。收起后重新校准鼠标坐标，支持再次按 Ctrl-O 展开。主界面不捕获鼠标，滚轮交给终端原生历史滚动；仅打开 Actions 面板时启用鼠标捕获，面板内滚轮翻阅详情。对话中的摘要和旧滚动区文本不是可点击控件。

展开后每次调用显示本地 `HH:MM:SS`、耗时、估算 token 和 `/details ID` 原始回执入口。估算仅按调用参数和结果文本的字符组成计算，不调用 API，不代表模型 tokenizer 精确结果或服务商计费，也不包含整轮上下文与回复。会话 Tokens 统计仍保存，底部不再展示。时间和估算随工具组存入本地 transcript，重启后 `/details ID` 可查；组编号只属于当前视图，切换会话后重置，历史回放暂沿用原有逐条显示。

验证：test_tool_groups、test_tool_groups_terminal；真实 PTY 覆盖连续六次调用实时写入对话、输入框下无工具进度、Ctrl-O 展开→点击关闭→再次展开→Esc 关闭及主界面释放鼠标捕获、工具颜色可见及中文草稿保留。

2026-09-07：增加 `/reasoning` 查询、档位补全和当前 profile 持久设置，`default` 恢复供应商默认；参数与服务等级区别见 [模型切换](MODEL_SWITCH.md)。中文流式输入 PTY 测试覆盖选择 high 后继续输入。


### 多终端共享状态目录（2026-09-07）

可在多个终端直接运行 `loop`，也可使用相同 `--state-dir`；无需手动复制模型配置或更换状态目录。首个可用运行槽保留原状态根目录，其他并发窗口使用 `state-dir/terminals/2/`、`3/` 等空闲槽；槽锁在退出或进程崩溃时自动释放，后续启动可复用。普通启动不会因根 `terminal.lock` 已占用而报 Another terminal 错误。

同一状态目录共享 provider/profile、权限、完整会话库、任务库、长期记忆和资源预算／租约。模型配置沿用同一入口，不复制 Key；已有窗口不自动热切到其他窗口新选的模型，权限规则仍从共享库检查。资源共享不等于设备动作授权。

各窗口独立维护当前会话、输入、前台工作、定时器、Node 进程、Agent 日志、模型服务日志、viewer 通道和场景快照。所有窗口每次启动／重启都从新会话开始；`/sessions` 与 `/resume` 能查看同一状态目录的历史。当前会话持有细粒度 OS 锁，同一会话不可同时被两个窗口编辑；占用时恢复请求保留原窗口会话和输入，关闭原会话／窗口后可恢复。锁不阻止只读浏览和导出。工具日志新增 session_id，交错回执按所属会话关联，旧无归属日志保留且仍支持显式 `/details ID`。

关闭窗口只清理它拥有的前台进程和视图；另一个窗口保持运行。Node 的串口、process profile 与执行型 Skill 资源通过状态目录下的独立所有权锁防重复启动，释放与子进程回收绑定；命名仿真仍是各窗口的独立实例。底层驱动保护和远端真实就绪验收继续适用，不把进程退出当成设备已停。

已有其他终端运行时，CLI 不允许变更 deployment 绑定；相同绑定可再次使用。后台 task service 保持原单监督器锁与共享任务库。内部 API 直接构造 App 的宿主仍负责自己的生命周期，CLI 使用 TerminalInstance 自动分配前台运行槽。

升级后需正常退出并重新打开旧版本窗口，才能使每个窗口都使用新的会话与资源占用保护；不要把旧版本与新版本混用当成已验证并发。Linux 双 PTY 已验证中文流式并行输入、独立草稿、占用拒绝、退出及恢复；Windows/macOS 原生实机未验证。

2026-09-07：展开的 Actions/工具详情正文和标题支持滚轮上下滚动；普通详情支持 ↑/↓ 逐行滚动，PgUp/PgDn 翻页。执行中的 Working 状态仍可滚动并保留中文草稿。任务操作选择与补全菜单保留原方向键功能；滚轮用于查看面板正文，点击正文不触发关闭。


2026-09-07 Task Session：左右键任务卡片提供 Enter session / Close session，关闭鼠标捕获以支持原生选择复制。Enter session 创建或恢复绑定该 Task 的独立聊天 Session；它在 /resume 列表可见，保存自己的历史、草稿、队列和用量。进入展示最近 20 条任务账本事件并恢复聊天记录；普通聊天工具及权限门禁保持一致。Close session 返回原会话，不取消任务或推定远端停止。Task ID 与原所属 Session 保留，新聊天 Session 通过 task_sessions 关联，Task 与对话仍各自有生命周期。打开/恢复不自动运行或重播任务，向等待 Worker 补充目标使用现有 task_resume；独立会话的模型可以查询关联任务并继续处理用户请求。

2026-09-07 执行中进入 Task Session：Enter session 不再要求先清空队列或等待用户重试。记录切换目标并暂停原会话队列，请求前台在当前模型/工具返回后停止后续调用；后台持久 Task 不取消。前台回执归档后自动恢复目标会话，原草稿、附件和队列留在原会话，目标队列恢复为暂停。正在执行的阻塞调用仍需返回或超时，不强杀。原会话邮箱通知不带入新会话。若目标会话被另一窗口占用，保留原会话并报告占用。

2026-09-07 二级命令提前补全：输入 /swi 时同时显示 /switch 和 /switch setup、list、reload、master、expert 等完整候选，无需先输入空格。/node、/skills、/mode、/fast 的静态子命令采用同样行为；仅输入 / 的首页顺序不变。已有空格后的参数补全保持有效，生成候选不执行命令、不访问模型或动态会话/设备目录。

2026-09-08：run_python 回执在输入框上方显示实际退出码、停止原因及最多六行 stdout/stderr 预览，长输出保留 /details；退出零不标记目标成功。read_file 显示文件与行号，active 工作登记显示 acceptance pending，尚未执行的验收不显示为操作失败。工具调用前的模型进度文字保留，中文并行输入的 PTY 验证通过。

2026-09-08 异步工具与停止：模型工具沿用前台 worker，Node 控制台及定时 slash 同样通过 worker 执行，普通 slash 工具通过后台线程执行；隐藏 Key、模型选择和明确确认菜单保留独占终端交互。活动执行或已有队列时，独立输入“停止”／“停下”／stop 或 /cancel-turn 直接置取消事件并暂停队列，即使普通提交正在等待工具也不排队；引文、粘贴块和附件不作为控制口令。Esc（先关闭补全／面板）、Ctrl-C（先清空草稿）保持既有语义。中断不会清空旧队列，/queue resume 显式续接；不支持协作取消的调用仍需返回，不能凭异步调度宣称副作用已停止。Python 使用 SIGINT 并保留真实退出回执。

2026-09-08 前台执行中新建任务：/task 目标 与 /tasks 同样允许在已有前台工作时提交；创建独立持久 Task 和聊天 Session，不中断前台，不混入追加消息队列。普通追加消息仍作为当前工作补充，异步工具不等于自动创建 Task。验证 test_interactive.test_create_multiple_tasks_while_foreground_is_running：两个任务、独立 Session、前台 Future 保留；后台服务使用替身，未运行任务。

2026-09-08：`/model` 选择后接推理档位菜单，可 Tab/上下键选 `/reasoning` 参数。档位依据、缓存和未知能力处理见 [模型切换](MODEL_SWITCH.md)；不再补全所有可能档位。中文流式输入 PTY 验证选模型→选 high→继续输入。

2026-09-08 更新：独立 `/reasoning` 命令及补全已移除。`/model` 两步选择模型、强度，完成自动关闭菜单，恢复普通输入框且保留对话上下文。默认 placeholder 为 `Ask LoopROS to do anything about Robot`；上下键回溯用户 prompt（多行首尾触发），面板翻页保留 PageUp/PageDown，排队输入取回改为 Alt＋↑。

2026-09-08 输入占位文字采用浅灰色 `#9e9e9e`，仅在输入为空时显示；输入首个字符立即隐藏，清空后恢复，不进入提交内容。复用 PromptSession 原生 placeholder 条件；`test_slash_terminal` 的真实 PTY 验证浅灰颜色、中文输入覆盖、清空恢复和流式期间并行输入均通过。运行中的旧终端需正常退出后重新打开加载样式。
