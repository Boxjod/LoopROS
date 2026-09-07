# Loop Switch：轻量模型切换器

默认入口为供应商/URL → API类型 → 隐藏 Key → 自动探测模型并编号选择的向导；旧菜单使用 `loop-switch --advanced`。交互启动 loop 会先检查模型连接，无 Key、认证失败、网络失败或无有效文本响应时自动打开同一向导，保存后重新检查，见 [QUICK_SETUP](QUICK_SETUP.md)。

2026-09-05。参考 [CC Switch](https://github.com/farion1231/cc-switch) 的提供商配置管理与选择模式，实现项目内的小型终端程序，不复制其桌面端、多应用接管、代理或 OAuth 功能。

## 独立程序

在 LoopROS 项目目录执行：

```bash
./loop-switch
```

编号菜单支持列表、新增、编辑、切换当前模型、删除非活动配置。仅依赖 Python 标准库，无需启动模型或安装 GUI。

也支持命令模式：

```bash
./loop-switch list
./loop-switch add my-provider
./loop-switch edit my-provider
./loop-switch pick master
./loop-switch use master my-provider
./loop-switch use expert default-expert
./loop-switch remove my-provider
```

add/edit 会逐项询问 base_url、model、api_key_env、timeout_s、token_field；回车采用显示的默认值。api_key_env 填环境变量名，**不是 Key 原值**。高级 add/edit 保留手动填写；默认向导、`loop-switch setup` 与 `/switch setup` 在输入 Key 后自动查询所选地址的 `/models`，支持编号或直接输入模型 ID。

可明确发起单次连接测试：

```bash
./loop-switch check my-provider
```

check 使用指定环境变量发送简短请求，可能计费；已存配置的切换、列表和高级菜单本身不请求 API；配置向导会查询模型列表，但不逐个调用模型推理。测试返回有效消息不等于工具调用、视觉或场景能力已验证。该命令不读取另一运行终端中隐藏输入的 Key。

## Master 终端内切换

交互终端输入 `/model`，查询当前 URL 和既有 Key 对应的 `GET /models`，在输入框下方按公司 A–Z、目录日期倒序展示，↑/↓ 选择、Enter 切换；不逐个进行推理探测。查询失败时可使用 `/model MODEL_ID`。模型目录不保证工具／视觉支持，日期仅代表目录元数据。`/model` 不改变 URL、Key 或保存的 profile；更换服务商仍用 `/switch`。

`/fast` 切换当前客户端后续前台请求的档位，`/fast on` 请求 `priority`，`/fast off` 请求 `default`，`/fast status` 显示请求档位和最近响应实际回报的档位。未设置时保持服务商默认行为。此设置不写入 profile，重启或重建客户端后重置；不修改已经启动的后台 Task／Agent 请求。服务商拒绝参数时正常报告错误，不静默降档或重放；开关本身不发送推理请求、不保证加速生效。

```text
/switch
/switch expert
/switch list
/switch master my-provider
/switch expert default-expert
/switch reload
```

输入 `/switch ` 后会提示 `setup`、`list`、`reload`、`master`、`expert`，也支持子命令前缀补全。无配置名时显示编号选择器；显式名称可脚本化。选中后持久化并更新运行时客户端，清空 Master 对话上下文。Master 忙碌期间不允许切换，任何子 Agent 仍运行时也拒绝切换，不把同一任务中途改到另一模型。

独立程序修改选择后，已运行终端不会悄悄热切换；待任务结束使用 `/switch reload`，或重启终端。本版没有后台文件监控。

`/model 新模型名` 保留为仅当前会话的快速改名，不持久化、也不改变提供商地址。需要可复用配置时使用 switch。所有角色和复杂任务使用同一当前模型；旧 master/expert 槽位名是兼容别名；现有角色的工具授权不受切换影响。

## 配置与凭据规范

配置存于 `artifacts/terminal/providers.sqlite`；可用 `--state-dir` 指定其他位置。两个程序需使用同一个 state-dir 才共享选择。SQLite 事务保存变更，正在使用的配置不可删除。删除非活动配置不会删除模型、API账号或权重；没有内置撤销，需重新添加。

首次初始化从原有配置导入 default-master（默认Qwen）和 default-expert（默认GPT-6 Astra），保留原来的服务管理配置。之后 providers.sqlite 是 API 提供商及选择的权威来源，优先于 config.local.json／--config 的 llm/expert 字段；这些文件仍负责首次种子配置与其他模块配置。不会覆盖已存在的配置档案。

Key 来源优先级为会话隐藏输入、环境变量、用户显式保存的凭据；数据库和列表不保存／回显 Key。`/key save`、`/expert-key save` 支持 endpoint＋变量名绑定的本地明文保存，独立 check 也可读取。会话缓存退出即丢失；不支持系统钥匙串或加密持久化。见 [USER_HOME](USER_HOME.md)。

配置协议限定已有的 OpenAI-compatible Chat Completions；不是声明任意 Claude／Gemini 原生 API 都兼容。base_url 须含主机名，无用户名、密码、query、fragment；远程仅 HTTPS，HTTP 仅允许 loopback。token_field 可选 max_tokens／max_completion_tokens，按后端要求填写。现有模型能力和账号权限仍需实际验证。

不修改 `~/.codex`、`~/.claude` 或旧 LoopMaster 仓库，不安装反向代理、不接管 OAuth。该程序切换的是 API 服务／模型配置，不是 pi0.5／ACT 权重和 GPU 驻留；后者仍由 /policy 与资源工具链负责。

## 验证

45项完整环境测试通过，新增配置持久化、重复名称、独立槽位、活动删除保护、非法凭据URL、编号选择、上下文清空、Key跨地址隔离及活动子任务阻断测试；独立 list 与终端 /switch list 均已运行。未执行真实付费API检查。project-maintenance 同步项目入口、规范与运行地图。

2026-09-05：取消模型能力分级。旧数据库以 master 当前选择为准合并活动槽位，保留原配置供手动选择；通过任一旧槽位切换均更新统一选择。会话 Key 共用同一客户端，切换地址仍隔离凭据。

交互菜单显示：`/switch` 先输出带编号的配置名称、模型、地址与当前选择，再提示输入编号；空 Enter 取消。终端临时接管菜单时绕过异步 stdout 缓冲，确保选项在等待 `input()` 前可见，返回后恢复原输入编辑器。`/switch setup` 与 `/key` 共用这条交互命令输出路径。


## 删除保存的模型配置

在系统终端执行（不是 Loop 的聊天输入框）：

```sh
loop-switch list
loop-switch remove setup-配置ID
```

`remove` 参数是列表中的配置 `name`，不是模型 ID；同一个模型可以有多个配置。当前选中的配置不能删除，先用 `/switch master 另一个配置名` 或 `loop-switch use master 另一个配置名` 切换。若使用了自定义状态目录，独立命令也要指定同一个 `--state-dir`。删除配置记录不会删除会话历史或共享的 endpoint 凭据。此操作由用户明确指定记录后执行。

2026-09-07：配置向导自动探测覆盖预设与自定义 URL，完整展示模型列表。公司名称按 A–Z 分组（已识别系列归一到公司，其他使用接口 owned_by，未知在最后），组内按日期降序；优先 released_at/release_date/created，再尝试型号中的完整日期，无日期标 Unknown 并排在后面，同日期按 ID 排序。created 可能是目录创建时间，不保证是发布时间。编号全局连续，越界重新输入，0 取消，探测失败可手填。默认选中列表中的预设型号或首项，需用户确认输入后保存。此列表不代表 API 类型、工具或视觉能力已验证。

2026-09-07：profile可保存 `context_window`、`max_output_tokens`、`compact_threshold`、`image_token_budget`、`stream_usage`，使用既有settings profiles入口编辑；高级编辑保留这些额外字段。改变模型ID时清除旧容量；完整profile切换读取目标容量。详见 [上下文预算](SESSION_MEMORY.md)。


### Reasoning effort（2026-09-07）

`/model` 选完模型后在同一菜单选择推理档位，选择完成即关闭面板并恢复普通输入框。独立 `/reasoning` 命令已移除；完整命令为 `/model MODEL_ID EFFORT`，default 删除强度覆盖，交由供应商默认处理。设置持久保存到当前 profile，切换模型与选择档位均保留当前会话历史、摘要和 token 统计；补全只显示有依据的档位。先使用当前 URL＋API 类型＋Key 请求 `/models` 返回的明确枚举（supported_reasoning_efforts、reasoning_efforts 或 reasoning_effort.enum），只在内存缓存 5 分钟，换凭据或地址失效。不把布尔“支持推理”当成档位列表。缺少枚举时使用已核实的官方条目；自定义网关显示“未验证网关支持”。未知模型仅提供 default，不发送猜测档位。切换模型清除旧 reasoning_effort，选择后保存到当前 profile。修改沿用 profile 的活动任务保护，不更换 endpoint 或密钥。

配置字段为 `reasoning_effort`。Chat Completions 编码为顶层 reasoning_effort；Responses 编码为 reasoning.effort。未配置时完全省略。显示的是 requested 值，不证明中转接口确实采用了该强度。`/fast` 是服务等级，reasoning 是思考投入，两者不同；思考文本的显示也不是强度选择。

[官方 Reasoning 说明](https://developers.openai.com/api/docs/guides/reasoning)指出档位按模型而异，更高档位可能增加 token 与等待时间。本次测试验证配置持久化和两个协议的请求体，没有使用用户模型进行收费兼容性探测。


### 官方档位记录（2026-09-08）

| 精确模型／范围 | 档位 | 官方依据 |
| --- | --- | --- |
| gpt-6-astra | low, medium, high, xhigh, max | [OpenAI](https://developers.openai.com/api/docs/models/gpt-6-astra) |
| gpt-5.6 / gpt-5.6-sol | none, low, medium, high, xhigh, max | [OpenAI Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol) |
| gpt-5.6-terra / gpt-5.6-luna | none, low, medium, high, xhigh, max | [Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra)、[Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) |
| qwen3.8-*，Chat Completions | low, medium, xhigh | [Alibaba Cloud](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions) |

每组另有 default（省略参数，不等于 none）。Qwen 表仅列原生档位，不把官方兼容映射重复列成新档位。官方记录不是第三方网关或当前账户的兼容性验收；未匹配的别名不猜测。实现见 terminal/reasoning.py。本次只核对文档与离线测试，未对用户平台发送收费推理探测。

2026-09-08：输入框默认提示为 `Ask LoopROS to do anything about Robot`。无补全/任务操作菜单时，上下键在多行文本内移动，到首尾后回溯本会话输入历史（不混入 slash 配置命令）；Alt＋↑ 取回排队消息。模型与强度选择完成后，底部不保留模型面板、配置回执或选择用的命令草稿。
