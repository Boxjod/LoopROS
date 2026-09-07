# Experience and continuous learning

Loop now carries execution experience across conversations and task attempts. It records tool observations, retrieves related experience, and lets the configured model revise source-linked advisory notes. This is learning through runtime memory and skills; model weights are unchanged.

## What happens automatically

1. A foreground turn with tool receipts writes a compact record to `<state-dir>/learning.sqlite`. Plain assistant prose and conversations without tool observations do not create experience. File contents, images and diffs are excluded; configured keys and common credential forms are redacted.
2. A task attempt records its observed outcome after the supervisor finishes evaluation. `verified` requires a succeeded task, a completed worker, and a fresh evaluation of the actual receipts against explicit checks. Cancellation, errors and missing acceptance stay distinct.
3. A similar request retrieves up to three records or notes into the next model call. Matching uses indexed English terms and Chinese bigrams; scope includes workspace, API endpoint, model and protocol. Unrelated conversation gets no recalled block. The record block is limited to 4,500 characters, with brief instructions added separately.
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

Existing saved conversations and tasks are not bulk-imported. New completed turns and task attempts populate this store. Cross-workspace and cross-provider migration is not automatic. Retrieval is lexical, so synonyms with no shared terms can be missed. Task-worker records use the supervisor's workspace scope (currently the project root when launched by the service). Large payloads are bounded; inspect the original task/turn logs when complete evidence is needed. Credential filtering is an additional safeguard, not a general secret-classification guarantee.

Validation, source comparison and limitations: [Hermes comparison and implementation report](../../projects/reports/19_hermes_continuous_learning.md).

Deployment-enabled sessions additionally scope experience by deployment ID, host ID and local profile fingerprint. Carrier receipts retain explicit route/instance IDs; no cross-carrier calibration transfer or fleet-wide synchronization is implied. See [DEPLOYMENTS](DEPLOYMENTS.md).
