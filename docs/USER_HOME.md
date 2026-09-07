# Loop ROS user home

All default installations use `Path.home() / ".loop"`: `/home/<user>/.loop` on Linux, `/Users/<user>/.loop` on macOS, and typically `C:\Users\<user>\.loop` on Windows. If only `.looper` exists, the first configuration load renames that directory to `.loop`, preserving contents and permissions without printing credentials. If both exist, `.loop` wins and `.looper` remains untouched; no automatic merge or overwrite occurs. A legacy symlink is not migrated automatically. Close older running versions before migration to avoid their recreating the old directory. Explicit overrides remain supported: `LOOP_HOME`, then legacy `LOOPER_HOME`; remove an old override if you want the standard `.loop` location.

```text
.loop/
  config.json        Optional global defaults, no API keys
  credentials.json   Created only by an explicit key-save command
  agents.json        Optional user Agent definitions (replaces packaged registry)
  task_runtime.json  Optional user task policy (state-specific policy takes precedence)
  AGENTS.md          Optional user instructions for Master
  harness/*.md       Additional Master instructions, sorted by filename
  skills/            SKILL.md packages; metadata discovery and tool-based read/write
```

The directory and harness/skills folders are initialized on configuration load; existing files are preserved. New installations may create the optional AGENTS.md and config.json files manually. This machine’s provider setup is recorded in the workspace docs/RUNBOOK.md; keys remain only in the user credential store and the user-managed source environment file.

## Credentials

Text tasks share the current model and credentials; image requests may use a vision model at the same endpoint (see CODING_AGENT.md); `/expert-key` is a legacy alias of `/key`. In the terminal, `/key save` or `/expert-key save` requests hidden input and saves it atomically. `/key` and `/expert-key` without `save` remain session-only. Never paste a key into chat or supply it as a command argument.

Precedence: session key → named environment variable → saved credential. Saved credentials are bound to the exact API base URL (ignoring a trailing slash) and environment-variable name, not the model name. Switching endpoints does not reuse saved credentials from the previous endpoint. Environment variables remain operator-controlled; use different variable names for unrelated providers.

Credentials are local plaintext, not encrypted or stored in an OS keychain. New POSIX home directories use mode 0700; credential files use 0600, and overly broad credential-file permissions are rejected on read. Windows requires a private user directory protected by OS ACLs; POSIX mode checks do not apply there. Do not share or commit this directory. To revoke a leaked key, revoke it with the provider; deleting a local file alone does not revoke it.

## Configuration and harness

Configuration merge order: packaged defaults → `.loop/config.json` → explicit `--config` file, or the existing project `config.local.json` when no explicit file is supplied. Existing provider database selections remain authoritative once created; edit profiles with `loop-switch` to change those values. Global defaults do not overwrite saved selections.

Master reads AGENTS.md followed by harness/*.md before every model call, up to 24000 characters total. Master instruction edits reload without restart. These are user instructions, not executable hooks or permission grants. They do not automatically propagate to child agents or isolated timer conversations. Skills load as a name/description catalog; skill_read expands the body, and skill_write creates or updates packages. harness_read/harness_write manage Loop Markdown instructions. See [coding tools](CODING_AGENT.md).

Source checkouts retain `artifacts/terminal`. Installed packages default to `${XDG_STATE_HOME:-~/.local/state}/loop-ros`. When only the old `looper` state directory exists, it is renamed to `loop-ros`, with a `looper` directory symlink preserving saved absolute scene paths. If creating the symlink fails, migration rolls back and reports an error; close older versions before migration. If both directories already exist, `loop-ros` wins without merging or deleting the old directory. `--state-dir` / `LOOP_STATE_DIR` (legacy `LOOPER_STATE_DIR`) still apply; environment overrides bypass migration.

New setup profiles use `LOOP_KEY_<endpoint hash>`. Existing profiles keep their original key environment variable and credential binding, including `LOOPER_KEY_*`; these identifiers are compatibility data and must not be replaced without moving their credentials. The canonical Python helper is `loop_home`; `looper_home` remains an import alias.

The home/config implementation is platform-neutral. Terminal locking, input polling, venv layout and service termination now have Windows branches; macOS passive viewer uses mjpython. Linux is verified locally; Windows/macOS native OS validation is pending. Hardware, clipboard and simulation have separate limits; see [PLATFORMS](PLATFORMS.md).


## Device migration

Personal customization belongs to the Loop user directory, not the installed Python package or another product's configuration directory. Keep packaged `configs/` and `toolchain/hardware_targets.json` as release defaults; user device/deployment manifests may be stored under `~/.loop/deployments/` and selected explicitly with `--deployment FILE --host HOST_ID`. These manifests describe bindings; copying them does not connect or authorize hardware.

| Content | Authoritative location | Migration rule |
| --- | --- | --- |
| General configuration | `~/.loop/config.json` | Copy; existing explicit `--config` and project `config.local.json` still override it |
| Agent roles | `~/.loop/agents.json`, otherwise packaged `configs/agents.json` | Copy the complete registry; validation and allowed-tool limits remain in force |
| Task policy | `STATE/task_runtime.json` → `~/.loop/task_runtime.json` → packaged default | Copy user overrides; state-specific policy has priority; restart the supervisor explicitly after edits |
| User instructions | `~/.loop/AGENTS.md`, `~/.loop/harness/*.md` | Copy; reloaded on the next model call |
| Skills | `~/.loop/skills/<name>/SKILL.md` plus optional `scripts/`, `references/`, `assets/` | Copy the entire package; use relative paths for supporting files |
| Credentials | `~/.loop/credentials.json` or external environment variables | Private transfer only; POSIX 0600; environment variables must be set again on the new device |
| Model profiles and selection | `STATE/providers.sqlite` | Copy after closing Loop and loop-switch; saved selections take priority over config defaults |
| Permission settings | `STATE/permissions.sqlite` | Copy only when those same user-selected rules are intended on the new device |
| History, learning and task records | Remaining `STATE/` contents | Copy after stopping all writers; do not resume device tasks automatically |

`STATE` is the explicit `--state-dir`, otherwise `LOOP_STATE_DIR` (legacy `LOOPER_STATE_DIR`), otherwise `artifacts/terminal` for a source checkout or `${XDG_STATE_HOME:-~/.local/state}/loop-ros` for an installed package. `loop-switch --state-dir` must select the same state directory as `loop`. A user-selected `LOOP_HOME` does not implicitly move STATE.

1. On the old device, stop persistent tasks/Nodes and close Loop and loop-switch before copying SQLite databases. Record the chosen user/state paths. Copy any external `--config` or deployment files separately; they are not automatically collected.
2. Install Loop on the new device. Transfer the user directory and STATE privately, keeping directory structure, Skill supporting files and SQLite companion files together. Restore POSIX home permissions to 0700 and `credentials.json` to 0600. If the destination already has settings, keep separate backup directories and choose which copy to use; do not merge SQLite files or overwrite existing credentials blindly.
3. To keep both sets of data under one portable directory, place the transferred state in `~/.loop/state` and configure **both** variables before starting Loop or loop-switch:

   ```sh
   export LOOP_HOME="$HOME/.loop"
   export LOOP_STATE_DIR="$LOOP_HOME/state"
   ```

   PowerShell equivalent (current session):

   ```powershell
   $env:LOOP_HOME = Join-Path $HOME '.loop'
   $env:LOOP_STATE_DIR = Join-Path $env:LOOP_HOME 'state'
   ```

   Persist these variables using your shell/user environment configuration. This is an explicit migration option, not an automatic change to existing state paths.

4. Recreate the Python runtime on the new device. Do not transfer `.venv/` or `~/.loop/runtime/` as working environments; their binaries and launchers are device-specific. Preserve `release.json` only if the same release server is intended. Reconfigure API-key environment variables if used.
5. Verify `loop-switch list`, `loop --once /status`, Skills discovery and `/resume`. Check device names, deployment host IDs and external absolute paths before explicitly resuming tasks. Copying history does not make old serial ports, remote hosts, live processes or absolute asset paths valid on the new device.

2026-09-07: temporary-directory copy test verifies configuration, complete Skills, harness, Agent overrides, task-policy precedence, selected profiles and endpoint-bound credentials after relocation. No actual device configuration, credential or runtime database was moved by this change.
