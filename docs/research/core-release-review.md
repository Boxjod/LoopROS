# Loop ROS core、源码上传与发行审查

日期：2026-09-08。首次审查，基于当前工作区内容和 Git 索引，包含尚未提交的开发改动；不是已发布 0.0.2 的线上故障结论。

## 0.0.3 实施进度

用户已要求将上述优化落实为 0.0.3。本节记录后续实施，下面保留原始审查证据。

- 目标：修复 F1–F6，统一发行快照／校验、进程正常退出和多终端迁移保护，整理包内导入与重复证据写入，构建并验收 0.0.3 候选。
- 约束：保留原工作区改动、用户状态、既有命令、权限与资源边界；不启动设备／仿真；当前请求未要求 GitHub 推送或服务器公开发布。
- 进度：已完成本地 0.0.3 候选。原工作区及索引差异保存在 artifacts/optimization-0.0.3；新增维护模块已明确纳入索引以参与构建，未提交／推送，未改用户安装。
- F1：构建拒绝未跟踪运行源码和缺失资源，检查实际 wheel 清单并独立安装／运行 `/status`；wheel 与 bootstrap 从同一份源码复制生成。
- F2：process Node 改用 SIGINT／Windows CTRL_BREAK，禁用监督层自动强杀；超时仍保留进程、资源和监测，实际退出后回收。真实本地测试程序已验证 SIGINT 回执、停止超时及关闭 runtime 后持续跟踪。
- F3：共享运行槽枚举覆盖第二及后续终端／服务／viewer；启动与迁移共用 gate，短暂并发启动等待锁释放。
- F4：release_manifest.py 统一元数据校验，publisher 拒绝两份清单不一致；独立 bootstrap／更新控制器均携带同一校验模块。
- F5：运行源码统一使用 loop_robot 包名；模拟策略移到 toolchain/feedback.py，MockBody 移到 examples。保留 Loop、FeedbackMaster、NumericalReviewer 的兼容导出，旧更新器需要的模块名只指向同一对象，不修改 sys.path 暴露顶层包。core 行数从 1,347 降至 1,219，属于职责整理，不代表整包等比例缩小。Episode／Review 成对原子写入已复用到 Python、工程与串口回执。
- F6：两个 CI 工作流均执行源文件索引检查；本地 .githooks/pre-push 已启用，并检查待上传提交历史。私有内容即使已从最终树删除，早期待上传提交仍被拒绝。内部操作文档的内容审查和 GitHub 公共源码准备仍独立于这些路径检查，没有据此认证整个工作区可公开。

最终包：[release-0.0.3-final-candidate](../../artifacts/release-0.0.3-final-candidate/)，8 个文件；wheel 602,703 字节、149 个条目，包含 123 个 Python 模块及此前遗漏的 ROS 配置。SHA-256：`968829465025dc59fb8e11d5248cc22ce65df498fba1715a737c321d111d6f93`。旧审查漏件包及第一份开发候选均不是交付包。

验证记录（各组含重叠测试，不相加为唯一总数）：

- [core-tests.log](../../artifacts/optimization-0.0.3/core-tests.log)：113 项核心／发行／安装／进程定向回归通过。
- [runtime-tests-final.log](../../artifacts/optimization-0.0.3/runtime-tests-final.log)：328 项运行时回归通过。
- [pty-and-release-final.log](../../artifacts/optimization-0.0.3/pty-and-release-final.log)：34 项发行与真实中文 PTY 联合回归通过，覆盖双 CLI、流式草稿、工具实时回执、停止、面板滚动和 process 控制台。
- [boundary-final.log](../../artifacts/optimization-0.0.3/boundary-final.log)：8 项边界回归通过，包括关闭 runtime 后保留未退出进程、待上传历史私有文件拒绝。
- [build-final.log](../../artifacts/optimization-0.0.3/build-final.log)、[bundle-verification.json](../../artifacts/optimization-0.0.3/bundle-verification.json)：真实 wheel 新环境安装、离线 App 启动、必要模块／资源、禁止路径、bootstrap 源码一致性、shell／zipapp 和版本一致性通过。
- [upgrade-result.json](../../artifacts/optimization-0.0.3/upgrade-result.json)、[upgrade-e2e.log](../../artifacts/optimization-0.0.3/upgrade-e2e.log)：使用实际 0.0.2 wheel 中的旧更新器安装 0.0.3，回滚 0.0.2、切回 0.0.3、保留更新控制器、卸载保留配置／Skill／SQLite 数据全部通过。下载替身只读取本地真实包，uv 环境、进程与安装／回滚真实执行；不是公网发布验证。

扩大回归发现并处理了直接执行 __main__.py 的兼容入口，以及已有显式延迟回答回调被提前刷新的问题；普通工具进度继续实时显示。测试同步已确认的 Alt＋↑ 编辑队列、PageUp/PageDown 滚动面板约定，并为 Mock 客户端显式提供 config 字典。初次环境缺 pyserial，改用独立 test-env 和声明的 test／feetech extras，未给用户 .venv 增装依赖；初次批量测试还包含一个误写的模块名，已纠正重跑。失败日志保留，不将其计为通过。

边界：仅 Linux 本地验证，无新增线上模型、机器人、仿真、固件刷写或服务器发布。Rust Cargo.toml／Cargo.lock 与 0.0.3 版本一致，未因版本号修改重做固件验收。

## 原始审查范围

最初审查阶段仅做本地检查，未修改实现或操作设备；停止路径当时使用替身。以下保留整改前的发现，当前状态以上面的 0.0.3 实施记录为准。

## 原始审查结论

Python core 本身较小。优先处理发行完整性、进程停止的一致性和多终端迁移保护，再整理包导入与重复的证据写入。现有职责分层有保留价值，不宜为了减少文件数合并 Session、Task、Node 或删掉资源、权限、验收机制。

当前重建候选不能发行：构建成功、版本显示正常，但执行离线 `/status` 时缺少 `toolchain.ros_node`，无法完成 App 初始化。现有 27 项定向测试全部通过，未覆盖这一产物运行路径。

## 规模与发行内容

工作区静态统计排除缓存／构建目录：

| 范围 | Python 文件 | 行数 | Python 源码字节 |
| --- | ---: | ---: | ---: |
| core | 12 | 1,347 | 69,545 |
| terminal | 64 | 10,567 | 616,284 |
| toolchain | 36 | 4,425 | 233,966 |

按现有构建入口重建的候选 wheel 为 585,792 字节，约 572 KiB。其 core 条目压缩后为 21,200 字节，约占 wheel 3.6%；assets 条目压缩后为 248,027 字节。该候选已证实漏件，数字用于判断规模，不是完整发行验收。

wheel 未包含 website、examples、user_projects、Rust、firmware、测试和内部部署文档。必要工作台资源约占压缩条目 181 KB，其中 Three.js 为 166,808 字节；这些资源服务于现有离线工作台，不是无调用的附件。`--terminal-only` 改变安装依赖选择，仍使用同一个 wheel，并不裁剪工作台代码。依据：[打包配置](../../pyproject.toml)、[安装依赖选择](../../release_client.py#L298)、[构建清单](../../scripts/build_release.py#L64)。

## 已确认的问题

### F1 · P1：构建静默漏掉必需文件，发布前缺少实际产物启动检查

- 位置：[public_source](../../scripts/build_release.py#L19)、[wheel 构建与审查](../../scripts/build_release.py#L58)、[发行 smoke](../../release_client.py#L129)、[Node 注册](../../toolchain/node_workers.py#L123)、[tag 工作流](../../.github/workflows/release.yml#L29)。
- 事实：public_source 只复制 Git 已跟踪、非忽略的工作区文件。当前 6 个新 Python 模块和 3 个 ROS JSON 默认配置未跟踪，却已被现有代码／package-data 引用。构建只检查禁止内容及文件名前缀，没有验证必需文件存在或 App 可初始化。
- 复现：用现有 uv 缓存离线运行正式 builder，返回 0；解压 wheel，在项目外临时目录、隔离 Python 路径和用户目录下调用安装入口。`--version` 返回 0；`--once /status` 返回 1，报 `ModuleNotFoundError: No module named 'toolchain.ros_node'`。
- 影响：仅检查源码测试、导入或版本号，可以上传一个无法启动的包。安装器现有 smoke 只导入 app/model_switch，未构造 App，也无法发现这个缺口。普通开发中的未跟踪文件本身不是错误，静默将不完整快照当合格候选才是发行问题。
- 建议：待发行维护源码明确纳入索引后，从同一快照构建；构建／发布门禁检查必需资源并在项目外运行 wheel 的离线 `/status`。不自动纳入所有未跟踪文件。tag 工作流应在构建后检查产物，而不仅在构建前测源码。

缺失清单：`core/processes.py`、`terminal/process_control.py`、`terminal/reasoning.py`、`toolchain/process_control.py`、`toolchain/ros_host.py`、`toolchain/ros_node.py`，以及 `configs/ros/` 下三个 example JSON。

### F2 · P1：普通 process Node 与 ROS Node 的停止策略不一致

- 位置：[ProcessNode.close](../../toolchain/process_node.py#L183)、[NodeDefinition 默认值](../../core/nodes.py#L18)、[process 注册](../../toolchain/node_workers.py#L129)、[NodeRuntime.stop](../../core/nodes.py#L277)。
- 事实：普通 process Node 在子进程仍运行时直接发送 SIGTERM，等待 0.2 秒后自动 SIGKILL；监督层还保留默认 `force_stop=True`。ROS Node 则明确发 SIGINT，使用 `force_stop=False`，等待退出并保留资源。
- 复现：用进程替身让第一次 wait 超时，捕获到的信号顺序为 `[SIGTERM, SIGKILL]`；未发送真实信号。
- 影响：通过推荐的 process Node 启动机器人 Host／控制客户端，再执行停止或关闭，会跳过用户要求的正常中断路径。只改子进程 close 仍不足够，监督层也可能强杀。
- 建议：将默认正常退出契约统一到 SIGINT，超时保持可跟踪状态和资源所有权；明确授权的 terminate/kill 继续由已有 process_stop 请求表达。不把进程退出当电机失能验收。
- 适用依据：[项目约定](../../AGENTS.md)中的“机器人 Host／控制客户端停止遵从用户约定”，不是新增保护要求。

### F3 · P1：源码迁移漏查第二及后续终端运行槽

- 位置：[state_guard](../../release_client.py#L253)、[TerminalInstance](../../terminal/instances.py#L13)、[源码环境 runtime_session](../../release_runtime.py#L50)。
- 事实：TerminalInstance 首窗口使用状态根目录，后续窗口使用 `terminals/N/`；迁移检查只查根 `terminal.lock`、`task_service.lock` 和 `viewer/owner.json`。源码运行没有托管 release lease 兜底。
- 复现：临时状态目录取得两个真实文件锁，关闭首窗口的锁，保留 `terminals/2/terminal.lock`；state_guard 仍允许通过。
- 影响：第一窗口已关、第二窗口仍活动时，源码迁移可能与会话／任务写入并行，违背现有更新约定。本次未执行真实迁移，未证明已发生数据损坏。
- 建议：复用统一的运行槽枚举来检查各槽终端、服务和 viewer；启动与迁移还应共享维护边界，避免单纯枚举后的启动竞态。

### F4 · P2：发布校验不核对两份版本清单的语义一致性

- 位置：[inventory](../../scripts/publish_release.py#L14)、[不可覆盖检查](../../scripts/publish_release.py#L60)、[指定版本下载](../../release_client.py#L66)。
- 事实：publisher 验证 SHA256SUMS，并核对根 latest.json 指向的 wheel；没有读取 `versions/<version>/latest.json` 来比较版本、wheel、哈希和 schema。
- 复现：构造一个所有文件哈希都正确、但版本目录清单中的 wheel 哈希不同的本地 bundle，inventory 接受。
- 影响：默认安装可能正常，而 `update --version` 失败；版本目录清单一旦发布又受不可覆盖规则保护，无法原地修正。
- 建议：在写远端之前核对两份清单完全一致，并复用一个纯数据 manifest 校验函数。当前正常 builder 会复制同一文件，此问题是 publisher 对错误 bundle 的验证缺口。

### F5 · P2：包内绝对导入依赖启动补丁，阻碍 core 独立复用

- 位置：[launcher._bootstrap](../../launcher.py#L6)、[core.loop 导入](../../core/loop.py#L5)、[memory_layers 导入](../../core/memory_layers.py#L5)。
- 事实：发行包名为 `loop_robot`，内部却大量使用顶层 `core`、`terminal`、`toolchain`；CLI 通过修改 sys.path 使这些名字可见。
- 复现：项目外直接 `from loop_robot.core.loop import Loop` 报 `No module named 'core'`。调用 bootstrap 后，同时导入 `loop_robot.core.resources` 与 `core.resources`，两者 `ResourceBusy` 类不是同一对象。
- 影响：CLI 的现有导入路径与 Python 包公开路径具有不同模块身份；嵌入 core 或混用两种路径时，异常捕获和类型判断可能失效。没有据此声称现有单一 CLI 路径的异常捕获已经出错。
- 建议：分阶段统一为相对导入或完整包名，保留既有命令入口。优先用项目外的包导入验收，无须同时搬动全部目录或修改用户状态路径。

### F6 · P2：wheel 过滤和源码上传保护未形成同一个可执行验收链

- 位置：[现有索引检查测试](../../tests/test_public_source.py#L25)、[tag 工作流测试列表](../../.github/workflows/release.yml#L31)、[平台工作流](../../.github/workflows/platform-smoke.yml)、[上传说明](../GITHUB_RELEASE.md#L9)。
- 事实：当前 `git ls-files -ci --exclude-standard`、`git ls-files -- user_projects` 和 `git ls-files -- website` 均为空。但两个 CI 工作流均未执行 test_public_source。builder 能排除强制暂存的忽略文件，并不能阻止这些文件通过 Git 提交／推送上传。
- 另一个边界：DEPLOYMENT、RUNBOOK 等内部记录仍是 tracked 文件；GitHub 上传说明也明确要求另行审查。不能用“wheel 没有内部文件”来认定整个 Git 源码都适合公开。
- 建议：复用已有索引检查加入本地提交／推送前入口和 CI，并在源码公开前拆分内部操作记录与公共操作说明。CI 在推送后执行，不能充当阻止首次敏感上传的唯一保护。未读取或改动远端，不据此认定发生过泄露。

## 可以精简的地方

以下是设计建议，未实施；按实际维护收益排序。

1. **统一重复契约，保留不同生命周期。** F2 的停止行为、F3 的运行槽枚举、F4 的 manifest 校验已有多份相近逻辑且发生分歧，值得优先收敛。资源预算、设备所有权、更新锁解决不同问题，不应合成一把锁或一张“万能账本”。
2. **把机器人参考实现移出通用 core。** [core.loop](../../core/loop.py)只接受 simulated body、检查关节目标；[core.plugins](../../core/plugins.py)包含 MockBody、NumericalReviewer、FeedbackMaster，两处反向依赖 toolchain.trajectory。可将模拟执行策略移到 toolchain，MockBody 移到测试 fixture／examples。Loop 和数值评审仍被 [App](../../terminal/app.py#L478)、[SimArmNode](../../toolchain/node_workers.py#L59) 使用，不能整组当死代码删除。共享 Episode／Review 可以保留。
3. **减少重复的证据存储样板。** [feetech](../../terminal/feetech.py#L45)、[robotics](../../terminal/robotics.py#L136)、[python_runner](../../terminal/python_runner.py#L105)等重复执行建 store、写 episode、写 review、finally close。可在现有 EventStore 中提供小型上下文／成对追加接口；调用方继续决定 verdict 和验收含义。不要合并为“退出 0 就全部成功”的通用评审。
4. **所有发行产物来自一个审查快照。** wheel 来自 public_source 临时目录，bootstrap.pyz 却直接读 [ROOT 工作文件](../../scripts/build_release.py#L80)。建议一起从保留的快照组装，避免构建期间文件变动产生混合来源。打包数据与审核清单采用明确来源和存在性校验；Git 忽略规则、wheel 规则、服务器上传规则仍各自承担不同边界，不宜互相替代。
5. **拆职责优先于继续压缩代码。** 最大的三个模块是 interactive（1,319 行）、app（1,003 行）、llm（624 行）。App 集中连接 profile、权限、Session、Agent、Task、资源和领域工具，是后续可测性整理的重点；只有出现具体修改需求时再沿已有组件拆分。本轮不建议为了文件数量重构整个应用。现有不少实现采用多语句单行，继续减少行数会增加审查成本。

目前不值得做：为了约 21 KB 的压缩 core 重写整个 Python 宿主；为了工作台约 181 KB 的压缩资源再增加一个下载／版本配套系统；将 Rust 端侧实现替换成完整 CLI。Rust 当前声明 `publish=false`、不进入 Python wheel，属于另一部署环境的开发实现。本轮只核对其构建边界，未进行 Rust 行为审查。

## 最小后续顺序与验收

1. 修正 F1，形成真实可启动候选；保留源码测试，再追加项目外 wheel 的 `/status` 与核心包导入检查。
2. 修正 F2、F3，分别验证 SIGINT 超时保留资源、首窗口关闭后的第二窗口仍阻止迁移；使用替身／本地临时进程，不需要启动机器人。
3. 修正 F4、F6，验证冲突 manifest 被拒绝、索引违规阻止本地上传准备，确认公共源码清单。
4. 再推进 F5 与证据写入整理。低收益的体积拆包暂缓，保留兼容命令与用户数据入口。

## 验证与来源

- `PYTHONPATH=tests .venv/bin/python -m unittest test_public_source test_releases test_updates test_loop -q`：27 项通过。
- 现有 uv 缓存下，以 `UV_OFFLINE=1` 调用 scripts/build_release.py；URL 使用 `https://example.invalid/LoopROS`，仅作生成模板，不联系服务器。
- wheel 运行验证使用解压后的发行文件及既有解释器依赖，启用 `-I` 并切换到临时目录；不是全新依赖环境的完整安装验收。
- [构建日志](../../artifacts/core-release-review-mivpc4ox/build.log)、[wheel 清单／包导入](../../artifacts/core-release-review-mivpc4ox/wheel-probe.json)、[CLI 与迁移锁复现](../../artifacts/core-release-review-mivpc4ox/behavior-probes.json)、[清单冲突复现](../../artifacts/core-release-review-mivpc4ox/manifest-probe.json)、[停止策略替身](../../artifacts/core-release-review-mivpc4ox/process-stop-probe.json)。artifacts 为本地忽略目录，不属于公开交付。
- 证据来源为上述当前本地源码、Git 索引和执行回执；建议与影响推断已与直接观察分开。本报告没有引用线上产品／库版本信息。
