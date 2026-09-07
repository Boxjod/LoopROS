# Install Loop ROS

Hosted `curl` installation and `loop --check-update`: see [release instructions](RELEASES.md). The release base URL is `https://loopmaster.box2ai.com/LoopROS`; actual deployment receipts are recorded in [DEPLOYMENT](DEPLOYMENT.md).

**Loop Robot Operating System**. Commands: `loop` or `loop ros`; `loop-switch` configures providers. Legacy `loop robot`, `looper`, `looper-switch` remain compatible. Distribution: `loop-ros`; source directory: `LoopROS`; Python import: `loop_robot`, independent of the checkout directory name.

Install from this source directory; no public PyPI release is assumed. The bootstrap script accepts Python 3.8+; uv creates the Python 3.12 `.venv` used to run Loop ROS. See [platform limits](PLATFORMS.md).

## One-command source installers

After obtaining the source folder, run inside it:

| System | One command |
| --- | --- |
| Linux / macOS | `sh ./scripts/install.sh` |
| Linux / macOS, terminal only | `sh ./scripts/install.sh --terminal-only` |
| Windows 10/11, PowerShell | `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1` |
| Windows 10/11, terminal only | `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 --terminal-only` |
| Windows 7/8 or incompatible older OS | SSH to an already installed compatible host; not native installation |

Python 3.8+ is enough to launch the installer. It reuses uv from PATH or `~/.local/bin`, or downloads Astral’s official standalone installer there without editing shell profiles. uv creates `.venv` with Python 3.12, downloading that interpreter if needed, and installs dependencies with `uv pip`. System pip/venv packages are not required. Scripts do not replace system Python or request administrator access. `LOOP_PYTHON` can select an explicit interpreter path. An existing usable Python 3.10+ project venv takes precedence otherwise. Broken/older environments are preserved with an instruction to move them aside before retrying. Add `--check` for a read-only environment check; it does not test downloads. PowerShell Bypass affects only that new process, not permanent policy; inspect the local script first. Hosted uv bootstrap and update commands are documented in [RELEASES](RELEASES.md).

The [English introduction page](../website/index.html) includes platform selection and command copying. Open that file directly in a browser; no server is required. Do not expose the project root (which may contain local configuration/state) through a public file server. See [website notes](../website/README.md).

## Installed workstation

Already installed. From any directory:

```sh
loop
# Equivalent:
loop ros
```

Reinstall from the project directory with `.venv/bin/python scripts/install.py`.

## Linux

Ubuntu 22.04/24.04/25.04 with a compatible interpreter:

```sh
python3 --version
python3 scripts/install.py --check
python3 scripts/install.py
export PATH="$HOME/.local/bin:$PATH"
loop
```

Default installation includes MuJoCo/NumPy. For only the API terminal use `python3 scripts/install.py --terminal-only`. Add the PATH export to your shell startup file for persistence; the installer does not edit it. uv does not require the distribution’s `python3-venv` package.

Ubuntu 20.04 stock Python 3.8 can run `python3 scripts/install.py --terminal-only`; uv prepares the runtime without replacing `/usr/bin/python3`. On older systems, start with a Python 3.8+ bootstrap interpreter. TLS, libc and wheel compatibility still apply; use SSH below if compatible runtimes are unavailable.

## Windows 10/11 — native validation pending

Install an OS-compatible official Python, for example 3.12 with its launcher. In PowerShell inside the source directory:

```powershell
py -3.12 scripts/install.py --check
py -3.12 scripts/install.py --terminal-only
```

Open a new terminal and run `loop`. The installer adds user-level launchers to `%USERPROFILE%\.local\bin` and the user PATH, not the machine PATH. Restart the parent terminal application or sign out/in if PATH is stale. Direct fallback:

```powershell
& "$env:USERPROFILE\.local\bin\loop.cmd"
```

Rerun without `--terminal-only` for simulation, subject to compatible wheels/graphics. An existing venv is reused; selecting another Python does not migrate it. Windows 7/8 are not supported natively. Windows 8.1 is distinct from Windows 8 and remains unvalidated.

## macOS — native validation pending

Use an OS/CPU-compatible Python 3.8+ bootstrap distribution, matching Intel or Apple Silicon. Do not replace Apple's system Python:

```sh
python3 scripts/install.py --check
python3 scripts/install.py --terminal-only
export PATH="$HOME/.local/bin:$PATH"
loop
```

Rerun without `--terminal-only` for local simulation when wheels are available. The passive viewer uses `mjpython` on macOS and requires a graphical session. Python support does not imply support for all simulation/GPU dependencies.

## Legacy systems: remote terminal

Install Loop ROS on a compatible host first, then connect using an OS-compatible SSH client:

```sh
ssh -t USER@HOST '$HOME/.local/bin/loop'
```

Replace USER/HOST. On Windows 7/8, use a compatible SSH client to open a normal session, then run `~/.local/bin/loop` on the host. This is remote access, not native installation. Client security/compatibility must be checked separately. No forwarding of local USB motors, cameras or MuJoCo windows is implemented; local hardware needs a separate validated runner/transport.

## Setup, state and updates

Interactive startup checks the selected model with a short text request; missing/invalid access opens the provider, API-type, hidden-key and model wizard. `loop-switch setup` opens the same setup. See [Quick setup](QUICK_SETUP.md).

Configuration uses `~/.loop` (Windows: `%USERPROFILE%\.loop`). If only `.looper` exists it is renamed to `.loop` on configuration load; if both exist, `.loop` wins without merging. `LOOP_HOME` overrides this, with `LOOPER_HOME` retained for explicit legacy overrides. Saved credentials are plaintext; POSIX mode 0600 is enforced, Windows relies on the user's directory ACL. See [User home](USER_HOME.md). Existing keys and history are preserved. Installed runtime state now defaults to `loop-ros`; legacy state migration preserves a directory link for saved paths (see User home). Source checkouts retain `artifacts/terminal`.

This editable install requires keeping the source and .venv in place. Source changes load on restart. Unrelated command collisions are refused. Existing state stays in `artifacts/terminal`; use `--state-dir PATH` or `LOOP_STATE_DIR` for isolation. Two terminals cannot share the same state directory.

In a manually managed venv, `python -m pip install -e .` installs the terminal; `python -m pip install -e '.[sim]'` adds simulation. Unlike scripts/install.py, these commands do not create user PATH launchers.

## Checks

```sh
loop --version
loop ros --once /status
loop --once /doctor
loop-switch list
```

No API key is needed for these checks. `scripts/install.py --check` checks interpreter prerequisites only, not binary dependencies, graphics or hardware. `/help` lists actions; `/viewer` opens local simulation; `/after 60 /status` schedules a check while the terminal stays running; `/exit` exits.

Real hardware motion remains disabled. `/stop` is not a physical emergency stop. Timers are not OS background services. Linux clipboard-image integration needs wl-paste/xclip; other platforms can use `/attach`. See [validation records](RUNBOOK.md).


## Moving a source checkout

The checkout directory can be named `LoopROS` or another name. The installed Python package remains `loop_robot`; do not change imports to match the folder. Source launchers locate files relative to themselves. Python virtualenv launch scripts and editable installations contain absolute paths, so moving an existing `.venv` still requires repairing/recreating its launchers and reinstalling the editable package at the new location. Project-owned user command links must point to the new `.venv/bin` directory.

Scene indexes now store paths relative to the state directory and survive moves; old absolute indexes remain supported when their paths still exist. During this machine's move from `loop_robot` to `LoopROS`, the current index was converted after checking the saved scene. Historical logs retain their original paths. See [RUNBOOK](RUNBOOK.md) for verified relocation results.

uv behavior references (checked 2026-09-07): [standalone installation](https://docs.astral.sh/uv/getting-started/installation/) and [Python environments](https://docs.astral.sh/uv/pip/environments/). These document uv bootstrapping and interpreter selection; cross-platform native validation remains pending.

## Uninstall a source installation

Stop Loop ROS and its background services first. From the checkout, use system Python 3.8+: `python3 scripts/uninstall.py --check` previews removal; `python3 scripts/uninstall.py` removes this checkout’s environment and recognized Loop ROS launchers, including links to old checkouts. On Windows use `py -3`. Do not launch the uninstaller with the environment being deleted. Settings, Skills, sessions, runtime data, source, uv, shared Python and user PATH are retained. Unrelated or unverified launchers, other checkouts’ environments and launcher backups remain unchanged. See the [script](../scripts/uninstall.py) and [README](../README.md#uninstall).

## Existing launcher conflicts

The source uninstaller removes recognized Loop ROS launchers even when they point at another checkout; unrelated or unverified launchers are preserved. To switch those commands to the current checkout, run `python3 scripts/install.py --terminal-only --replace-launchers` (Windows: `py -3`). After dependencies install successfully, conflicting launcher files/symlinks are renamed to `<command>.loop-ros-backup.N` in the same user bin directory, then current launchers are created. Existing backups are preserved; real directories are refused. Other source trees and their environments/data are not removed. `--check` now validates command conflicts too, and with `--replace-launchers` previews the switch without writes. Later uninstall removes recognized Loop ROS launchers and retains backups; it does not automatically restore a previous checkout.

Uninstall recognizes POSIX Python entrypoints by a top-level import of the expected function from `loop_robot.launcher`, without executing the target. Windows recognition matches the installer’s complete marked `.cmd` format and command name. Broken links into the current checkout are removable; broken links elsewhere without verifiable ownership remain untouched.

## Managed release updates

`loop update --check` checks stable versions; `loop update` installs into a fresh environment and activates after verification; `loop update --rollback` selects the previous runtime without reverting user data. Close active terminals/services/viewers first. A source checkout requires explicit `loop update --migrate --terminal-only` (plus `--state-dir` if needed). Managed installs remember dependency selection and state location. For hosted runtime removal use the server `uninstall.sh`, not source `.venv` deletion. See [release details](RELEASES.md).
