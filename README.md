# Loop ROS

**Loop Robot Operating System — a coding agent with optional robotics tools.**

Loop connects a user-selected model to tools, persistent tasks and robot runtimes. Its central contract is **goal → execute → observe → review → revise**. Execution receipts and task success are recorded separately.

Version **0.1.0**, local release preparation; no public GitHub release has been published from this workspace.

## Quick start

Requires Python 3.10+. From a source checkout:

```sh
python3 install.py --terminal-only
loop
```

For the optional MuJoCo environment, use `python3 install.py`. First launch without a key opens `loop-switch`; select a provider or enter your own API base URL and hidden key. Existing profiles are retained.

**Recommended: GPT-6 Astra through your custom API or OpenAI Responses API.** Use the exact model ID exposed by your endpoint. See [GPT-6 and custom API setup](docs/QUICK_SETUP.md); configuring a model does not verify account access or tool support. Other compatible providers remain supported.

## Capabilities

| Area | Available functionality | Boundary |
| --- | --- | --- |
| Conversation and coding | Streaming on Chat Completions, files/search/edit, images/URLs, Python execution | Python runs as the host user; Responses currently returns buffered answers |
| Feedback and evidence | Bounded execution loops, Episodes, Reviews, persistent task supervision, resume/cancel | A successful tool call is not proof of the user goal |
| Runtime coordination | Master and optional child Agents, persistent Loop Nodes, carrier/instance routing | Remote carrier assignments are not connected transports |
| Memory and extension | Session history, summaries, experience retrieval, revisioned learning notes, Skills/harness | No weight training or automatic candidate release |
| Robotics tools | MuJoCo scenes/assets, window control, joint trajectories, position IK, torque/PID/model analysis | Simulated results do not establish real-world success |
| Device access | Serial enumeration/receive, Feetech scanning/status, STS3215 Host primitives | Terminal hardware motion remains gated off; hardware acceptance is separate |
| Supporting tools | Search/web/weather, scheduling, inference-service hooks, ROS read-only adapter, resource budgets | ROS communication and actual policy model backends are not end-to-end verified |
| Distribution | CLI installers, wheel build, platform smoke workflow, update-check client | Public hosting and cross-platform hardware certification are not established |

The default model context exposes 21 general tools. Specialist toolsets (robotics, tasks, agents) load only when the model requests them and reset each turn. No robot keyword routing, automatic scene/device/weather execution or implicit background task creation is used. MuJoCo, hardware adapters and policy integrations remain optional tools. All Agent roles use the currently selected model and credentials. Session history and resume remain available; model input is bounded separately from saved history.

## Architecture

```text
User ↔ Terminal / Master ↔ Model API
                 │
        Permission-gated tools
                 │
       Task / Node / Carrier runtime
                 │
       Execution → Evidence → Review
           ↑                      │
           └──── correction ──────┘
```

`core/` contains standard-library contracts, persistence and runtimes. `terminal/` connects conversation, permissions and tools. `toolchain/` supplies domain implementations and optional dependencies. Task supervision, child-Agent processes and persistent Nodes have different lifecycles.

## Documentation

- [Project map](docs/CODEX_PROJECT_MAP.md) · [Operations and verification](docs/RUNBOOK.md)
- [Installation](docs/INSTALL.md) · [Model configuration](docs/QUICK_SETUP.md) · [User configuration](docs/USER_HOME.md)
- [Persistent tasks](docs/TASK_RUNTIME.md) · [Nodes](docs/NODES.md) · [Carriers](docs/DEPLOYMENTS.md)
- [Coding and Skills](docs/CODING_AGENT.md) · [Memory and learning](docs/LEARNING.md)
- [MuJoCo control](docs/MUJOCO_CONTROL.md) · [Robotics](docs/ROBOTICS_AGENT.md) · [Feetech](docs/FEETECH.md)
- [Release preparation](docs/GITHUB_RELEASE.md) · [Changelog](CHANGELOG.md)

Use `/commands` for the current command catalog. `/resume` selects a saved session; `/queue resume` resumes queued input. `loop-switch` manages model profiles without changing global Codex or Claude settings.

## Development

```sh
python3 -m pip install -e '.[test]'
python3 -m unittest discover -s tests -v
python3 run_demo.py
```

Optional dependencies and display availability affect simulation tests. The deterministic demo writes local evidence under `artifacts/`; it does not use an LLM or control hardware. See the runbook for verified commands and limitations.

## Design reference

[PhyAgentOS](https://github.com/PhyAgentOS/PhyAgentOS-core) informs the separation of task contracts, execution, evidence and verification. Loop ROS does not implement or claim compatibility with its Forge Gateway or Skill Runtime protocol. Third-party models and assets retain their own licenses and are obtained separately.
