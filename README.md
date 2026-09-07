# Loop ROS

**English** · [简体中文](README.zh-CN.md)

**Loop Robot Operating System — a coding agent with optional robotics tools.**

Loop connects a user-selected model to tools, persistent tasks and robot runtimes. Its central contract is **goal → execute → observe → review → revise**. Execution receipts and task success are recorded separately.

Initial hosted release **0.0.1** is available on the [official website](https://loopmaster.box2ai.com/LoopROS/). GitHub source and hosted release are separate snapshots; no GitHub Release has been created.

## Installation by platform

The [website](https://loopmaster.box2ai.com/LoopROS/) defaults to English with a Simplified Chinese option; Docs links to this repository README.

Start with an OS-compatible Python 3.8+; the installer uses uv to prepare an isolated Python 3.12 runtime without replacing system Python. These commands install the terminal edition; omit `--terminal-only` to include optional simulation dependencies.

### Linux

```sh
curl -fsSL https://loopmaster.box2ai.com/LoopROS/install.sh | sh -s -- --terminal-only
```

### macOS (Intel / Apple Silicon)

```sh
curl -fsSL https://loopmaster.box2ai.com/LoopROS/install.sh | sh -s -- --terminal-only
```

### Windows 10/11 — PowerShell

```powershell
Invoke-WebRequest -Uri https://loopmaster.box2ai.com/LoopROS/install.ps1 -OutFile loop-install.ps1 -ErrorAction Stop
powershell -NoProfile -ExecutionPolicy Bypass -File .\loop-install.ps1 --terminal-only
```

### Windows 10/11 — CMD

```bat
curl.exe -fSLo loop-install.ps1 https://loopmaster.box2ai.com/LoopROS/install.ps1 && powershell -NoProfile -ExecutionPolicy Bypass -File .\loop-install.ps1 --terminal-only
```

### Older systems — SSH

On Windows 7/8 or systems unable to run the required Python, use a compatible SSH client to connect to a host with Loop ROS installed. Replace `USER` and `HOST`:

```sh
ssh -t USER@HOST '$HOME/.local/bin/loop'
```

SSH does not include local USB/camera forwarding. Linux HTTPS installation is verified; native macOS and Windows installation remains unverified. After installation, reopen the terminal and run `loop` to configure the model connection.

## Hosted updates and uninstall

```sh
loop update --check
loop update
loop update --rollback
```

Close Loop terminals and background services first. Updating retains settings and Skills; rollback switches the runtime without reverting user data.

Linux/macOS uninstall:

```sh
curl -fsSL https://loopmaster.box2ai.com/LoopROS/uninstall.sh | sh
```

User configuration, sessions and uv are retained.

## Source checkout

Requires Python 3.10+. From a source checkout:

```sh
python3 scripts/install.py --terminal-only
loop
```

For the optional MuJoCo environment, use `python3 scripts/install.py`. First launch without a key opens `loop-switch`; select a provider or enter your own API base URL and hidden key. Existing profiles are retained.

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
| Distribution | CLI installers, wheel build, platform smoke workflow, update-check client | Hosted Linux installation is verified; native macOS/Windows validation remains pending |

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

## Repository layout

- `core/`, `terminal/`, `toolchain/`: Python implementation.
- `configs/`: packaged defaults and key-free configuration examples.
- `examples/`: demos and sample models; `assets/`: brand images.
- `scripts/`: source installers, release builder and simulation requirements.
- `docs/`: project documentation and changelog; `tests/`: verification.
- `website/`: introduction page; `artifacts/`: ignored local runtime output.

The root also serves as the `loop_robot` package, so its Python modules and `loop` / `loop-switch` source launchers remain here.

## Documentation

- [Project map](docs/CODEX_PROJECT_MAP.md) · [Operations and verification](docs/RUNBOOK.md)
- [Installation](docs/INSTALL.md) · [Model configuration](docs/QUICK_SETUP.md) · [User configuration](docs/USER_HOME.md)
- [Persistent tasks](docs/TASK_RUNTIME.md) · [Nodes](docs/NODES.md) · [Carriers](docs/DEPLOYMENTS.md)
- [Coding and Skills](docs/CODING_AGENT.md) · [Memory and learning](docs/LEARNING.md)
- [MuJoCo control](docs/MUJOCO_CONTROL.md) · [Robotics](docs/ROBOTICS_AGENT.md) · [Feetech](docs/FEETECH.md)
- [Release preparation](docs/GITHUB_RELEASE.md) · [Changelog](docs/CHANGELOG.md)

Use `/commands` for the current command catalog. `/resume` selects a saved session; `/queue resume` resumes queued input. `loop-switch` manages model profiles without changing global Codex or Claude settings.

## Development

```sh
python3 -m pip install -e '.[test]'
python3 -m unittest discover -s tests -v
python3 examples/run_demo.py
```

Optional dependencies and display availability affect simulation tests. The deterministic demo writes local evidence under `artifacts/`; it does not use an LLM or control hardware. See the runbook for verified commands and limitations.

## Design reference

[PhyAgentOS](https://github.com/PhyAgentOS/PhyAgentOS-core) informs the separation of task contracts, execution, evidence and verification. Loop ROS does not implement or claim compatibility with its Forge Gateway or Skill Runtime protocol. Third-party models and assets retain their own licenses and are obtained separately.
