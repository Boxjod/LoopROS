# Experience and continuous learning

Loop now carries execution experience across conversations and task attempts. It records tool observations, retrieves related experience, and lets the configured model revise source-linked advisory notes. This is learning through runtime memory and skills; model weights are unchanged.

## What happens automatically

1. A foreground turn with tool receipts writes a compact record to `<state-dir>/learning.sqlite`. Plain assistant prose never creates facts. A conversation without tools can now create a compact user-statement memory when it contains an IPv4 address, an SSH user@host reference, or an explicit remember/preference statement. Ordinary acknowledgements are skipped. File contents, images and diffs are excluded; configured keys and common credential forms are redacted.
2. A task attempt records its observed outcome after the supervisor finishes evaluation. `verified` requires a succeeded task, a completed worker, and a fresh evaluation of the actual receipts against explicit checks. Cancellation, errors and missing acceptance stay distinct.
3. A similar request retrieves a small set of task summaries, durable details and up to three experience records/notes into the next model call, sharing one bounded context budget. Matching uses indexed English terms, Chinese bigrams and memory tags, with connection-query synonyms and named-entity anchors; scope includes workspace, API endpoint, model and protocol. Unrelated conversation gets no recalled block. The record block is limited to 3,000 characters, with brief instructions added separately.
4. The model can use the four tools below to inspect evidence, save useful lessons, correct them, or stop recalling a note. Related experience includes a reminder to keep applicability, failures and verification steps. No extra model process or scheduled learner is started.
5. Background task attempts receive the same scoped advisory recall, within their existing 16,000-character input budget. Recall does not change their configured tools or permissions.

`verified` describes the original acceptance checks, not a claim that the lesson generalizes. A learned note remains `advisory_unverified`, even when based on successful tasks. Current environment and tool receipts override historical advice.

## Tools and examples

| Tool | Purpose |
| --- | --- |
| `experience_search(query, limit=5)` | Find matching observations and active notes; maximum ten results |
| `experience_read(id=...)` | Inspect one experience and its outcome/evidence |
| `experience_read(note=..., revision=...)` | Read latest or historical note revision |
| `experience_read(skill=...)` | Inspect recorded skill reads by exact content hash and co-occurring error/verified outcomes |
| `learning_note(name, content, source_ids, expected_revision)` | Create or revise a note using one to eight real source IDs from this scope |
| `learning_forget(name, expected_revision)` | Deactivate a note; preserve its revision history |

For example, ask Loop: “查一下之前串口连接失败的经验；核对当前情况后，把可复用的排查步骤更新到经验笔记。” The model searches first, reads the source IDs, and writes an advisory note. New notes use revision `0`; updates require the latest revision. A stale revision fails without overwriting newer work. To restore a previous note, read that revision and save its content as a new revision using the current revision number.

Skills remain in the existing `~/.loop/skills` system. Reading a skill records its name and SHA-256 in the attempt. This proves it was read, not that it caused an outcome. Repeated verified outcomes can support a skill proposal; publication still uses `skill_write` and its existing permission rule. Updating an existing skill now requires `expected_sha256` from `skill_read`; the existing atomic writer retains a backup and diff. This implementation does not automatically publish or delete skills.

## Permissions and recovery

All four learning tools use the common permission gate. Plan mode blocks note mutation. Setting either `experience_search` or `experience_read` to ask/deny disables automatic recall; explicit calls follow that action's rule. For example, `/permissions deny experience_read` stops automatic recall. Passive execution records remain local evidence, like the existing task and turn logs.

An unavailable or corrupt experience database does not prevent App startup or an ordinary reply: the context says recall is unavailable, and failed recording is reported as a learning error. It does not silently reset the database or label the user task failed. Each database operation owns its own connection; revision updates use a transaction so foreground/background writers cannot silently overwrite a note.

Complete saved conversations/tasks are not bulk-imported. On first use per scope, up to 200 recent existing user-turn experiences are locally re-extracted into durable details once, preserving their original source IDs and timestamps; no model call or automatic connection verification occurs. New completed turns and task attempts populate this store. Cross-workspace and cross-provider migration is not automatic. Retrieval is lexical, so synonyms with no shared terms can be missed. Task-worker records use the supervisor's workspace scope (currently the project root when launched by the service). Large payloads are bounded; inspect the original task/turn logs when complete evidence is needed. Credential filtering is an additional safeguard, not a general secret-classification guarantee.

Validation, source comparison and limitations: [Hermes comparison and implementation report](../../projects/reports/19_hermes_continuous_learning.md).

Deployment-enabled sessions additionally scope experience by deployment ID, host ID and local profile fingerprint. Carrier receipts retain explicit route/instance IDs; no cross-carrier calibration transfer or fleet-wide synchronization is implied. See [DEPLOYMENTS](DEPLOYMENTS.md).

## 指定的三层结构（2026-09-07 增量）

1. **全部上下文历史**：沿用 conversation.sqlite 中完整会话历史及 tasks.sqlite 的工具事件/评审；持久化不受模型上下文预算裁剪。历史按既有 /history、/resume 与任务详情入口读取，不全量注入模型。
2. **每个 session/task 的主要信息**：learning.sqlite 的 memory_items 保存独立 session/task 摘要，包含目标、状态快照、计划、下一步和来源；不是“新建 session 就等于新建后台 task”。`experience_search` 返回 memory 项，`experience_read(id="m-…")` 可读取详细摘要。
3. **长期细节与习惯**：同库独立保存用户名、免密方式、地址、明确的偏好/爱好/习惯及标准流程，文本去重、保留最近三条来源与时间。按实体/标签检索，连接方式和偏好优先于普通任务噪声；详情不会因最近八条聊天历史被裁剪而消失。当前提取使用有限的本地规则，不宣称任意语义理解或通用知识图谱。

用户名、认证方式和使用偏好应在既有授权范围内直接复用，不因新建 task/session 而重新询问。当前明确提供的参数优先于历史默认值；例如新指令地址变化，不代表已知用户名和免密认证方式也失效。先检查现有配置或执行已授权的尝试，只有具体未解决的阻塞才问用户。主模型提交任务时应把相关参数带入目标，后台 Worker 也使用相同召回规则。记忆不授予权限、不关闭主机密钥检查，不把用户提供的免密方式当作本次已经连通。

**三次固化**：前台/后台三个独立 task 的相同步骤、精确参数和相同验收条件均被实际工具回执验证成功，才生成 procedure 记忆。一个 task 的多次重试不累计三次；步骤/参数不同不合并；仅 path/id/name 的元数据验收不参与固化。流程保留实际步骤、checks、三条来源，读取后在原权限范围复用。不自动安装 Skill、修改权限或执行流程；后续同流程失败会退出自动召回并标 needs_review。流程数量仍是证据计数，不是模型复述次数。

每轮只做本地抽取和 SQLite 索引，零额外模型请求。候选最多 6 条分层记忆（预留任务摘要位置）加 3 条经验，最终共享 3000 字符 JSON 预算，指引文字另计；详尽步骤/回执按 ID 读取。权限、工作区/模型服务隔离、脱敏和检索故障降级沿用既有机制。

## 最近成功配置与失败回退（2026-09-07）

`successful_connections` 以当前记忆范围、显式 device 标识、transport 保存最近一次实际连接验收通过的 host/username/port/method、时间和来源；召回优先级高于普通新参数陈述。失败不覆盖成功基准，旧回调重放仍使用原经验时间，不会冒充新成功。设备标识与传输类型不同则不交叉推荐。

当前参数仍优先执行。前台/后台工具循环收到明确 `connected: false` 回执后，若同设备存在不同的成功配置，附加 `memory_feedback`：失败配置、last_success、user_confirmation_required=true、automatic_retry=false。模型据此说明失败并询问是否使用上次成功配置，等待用户同意；这条逻辑只生成建议，不自行调用连接或换地址。若没有历史成功、旧配置与当前相同或证据只是普通文字，则不制造备用地址。

连接观察约定：工具结果为 `connection` 对象，或 tool_run 的 `output.connection`；必须有 device、host、transport、布尔 connected，可附 username、port、method。connected 必须由实际认证连接检查产生。前台 task 完成或后台 succeeded 且实际回执重新通过 `connection.connected == true`（tool_run 使用 `output.connection.connected`）的对应验收，才更新成功基准。请同时使用精确 tool arguments 约束目标。无关验收、端口开放、退出码 0、助手说成功均不算连接成功。旧 scripts/inspect_jetson_ssh.py 的自由文本输出没有自动回填为成功证据；新的自编连接工具需按此结构返回结果。

实现：[连接记忆](../terminal/connection_memory.py)、[索引与成功基准](../core/memory_layers.py)。这是执行→观察→判断→用户选择回退→再验证→更新运行时记忆的闭环；复用前述三次实际成功的流程固化机制，不声称自动训练模型权重。
