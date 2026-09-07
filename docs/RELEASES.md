# Loop ROS release installation and updates

The current source/candidate version is **0.0.3**, from [_version.py](../_version.py); the initial release number was **0.0.1**. `pyproject.toml` reads that value dynamically; package and CLI version displays use the same source. The last recorded hosted release is 0.0.2; see DEPLOYMENT for its exact wheel hash and validation. The 0.0.3 candidate is prepared locally and is not a server publication. Earlier 0.1.0/0.2.0 wheels were unpublished development candidates, not release history.

Release base URL: `https://loopmaster.box2ai.com/LoopROS`, on the authorized server `8.134.90.171`. DNS, certificate dates and verified HTTPS access were checked on 2026-09-07. Publication and client validation receipts are recorded in [DEPLOYMENT](DEPLOYMENT.md); do not infer deployment solely from a local build.

## Install and uninstall

```sh
curl -fsSL https://loopmaster.box2ai.com/LoopROS/install.sh | sh -s -- --terminal-only
# Optional local simulation dependencies: omit --terminal-only or specify --sim.
curl -fsSL https://loopmaster.box2ai.com/LoopROS/uninstall.sh | sh
```

The shell bootstrap accepts Python 3.8+; if none is available it prepares uv and a private Python. The shared installer uses uv to create Python 3.12 environments. No system Python replacement, root privileges or system pip is needed. Windows has `install.ps1` with Python 3.8+; native Windows/macOS execution is not yet validated. Installations preserve configuration, Skills and runtime data. Uninstall preserves state backups, launcher backups and uv too.

Conflicting global commands are preserved unless `--replace-launchers` explicitly requests backup and replacement. All four current/legacy command names are installed. Source uninstall remains `python3 scripts/uninstall.py`; it also recognizes managed release wrappers, but only deletes the source `.venv`. Use the hosted uninstall script to remove managed environments.

## Update commands

```sh
loop update --check
loop --check-update
loop ros update --check
loop update
loop update --version 0.0.1
loop update --rollback
```

All source, installed and `python -m loop_robot` entrypoints share the same dispatcher. Checks only fetch metadata; there is no background update or startup network request. Stable major.minor.patch versions are supported; previews/channels are intentionally not provided. Explicit version selection downloads the immutable version manifest and refuses implicit downgrades. Rollback selects the retained previous runtime; it does **not** roll user data back in time.

Source/unmanaged installations require explicit migration:

```sh
loop update --migrate --terminal-only
# If a custom state directory was used:
loop update --migrate --terminal-only --state-dir /absolute/path/to/state
```

Migration retains the source tree and its state directory and backs up existing command launchers. It does not git pull, overwrite local edits or automatically uninstall the old source environment. For managed releases, terminal-only/simulation choice and selected state directory persist in `release.json`; `--sim` / `--terminal-only` intentionally change dependency selection.

## Activation, data and failure handling

Managed environments live under `~/.loop/releases/<version>-<id>` (or explicit LOOP_HOME), alongside a separate `updater` interpreter and stable dispatcher. A verified wheel is installed into a fresh environment, followed by isolated package/import/version smoke checks. Only afterward is `release.json` replaced atomically. Previous environments are retained. Installation, smoke or pre-activation failures leave the old active record unchanged; incomplete candidates from a hard crash are inactive and are not automatically executed. Initial launcher migration also makes backups; interrupted first installation may require rerunning bootstrap.

An installation-wide maintenance lock prevents concurrent updates. Running terminals, model-switch commands, supervisors, Agents, Nodes and viewers in managed releases hold runtime leases. An update refuses while they are active, and new launch attempts refuse during maintenance. Source migration also checks the selected terminal/service locks and recorded viewer ownership. No processes are killed or hardware actions started by updating.

Top-level SQLite state databases are backed up using SQLite's backup API before activation, under private `state-backups/`. Current state schema is 1; unsupported schema changes and incompatible rollback are refused. Configuration and model/scene assets remain in their original locations; this is not a full user-directory backup. Custom external writers and older unmanaged processes are outside managed leases; close them before migration. Runtime rollback is for compatible schema versions and preserves current data.

Downloads require verified HTTPS, including redirects, and the wheel must match manifest SHA-256. curl is used when available for host CA configuration; otherwise Python HTTPS verification applies. SHA-256 is integrity checking against the trusted release server, not a separate publisher signature. Dependency wheels are resolved by uv from configured indexes; they are not bundled or hash-pinned by this manifest.

## Build and publish

```sh
.venv/bin/python scripts/build_release.py --url https://loopmaster.box2ai.com/LoopROS --output /absolute/new/public-bundle
python3 scripts/publish_release.py --bundle /absolute/new/public-bundle --host root@8.134.90.171 --destination /www/wwwroot/loopmaster.box2ai.com/LoopROS
```

The builder uses uv, audits wheel inventory, and exports only the wheel, metadata, standalone bootstrap zipapp, platform scripts. Website files and examples are excluded from wheel and release source snapshots. Only required default scenes (`assets/simulation`) and local workbench assets (`assets/workbench`, including its license) ship as runtime resources. Website source stays outside Git and is backed up privately on the server; website publishing is a separate operation. Private project deployment/runbook documents are not included. The publisher checks an explicit file whitelist and all checksums locally and on the server, stages under `/root/workspaces/LoopROS/releases`, refuses overwriting changed versioned artifacts, and publishes `latest.json` last. Never republish changed code with the same released version number. No existing website root or nginx/TLS configuration needs replacement.

The release builder requires Python 3.11+ for standard-library TOML parsing (the normal source installer prepares 3.12). Runtime Python 3.10+ and the 3.8+ bootstrap remain supported. New runtime files must be explicitly reviewed into the index; the builder refuses untracked runtime source and missing declared data. It installs the actual wheel into a fresh environment and runs package imports and offline `--once /status` in a temporary user/state directory before exporting any bundle. Wheel and bootstrap bytes come from the same copied source snapshot. The publisher validates both latest manifests and requires identical contents.

For Git source preparation, run `python3 scripts/check_public_source.py`. This workspace uses `.githooks/pre-push` via the repository-local `core.hooksPath`; the hook checks the index and outgoing commits for ignored/private user content. New checkouts may enable it with `git config --local core.hooksPath .githooks` after inspecting any existing hook configuration. These path checks do not certify the contents of internal deployment/research records; public source preparation remains separate from the wheel whitelist.

Source migration checks the root runtime and every `terminals/*` slot, including terminal/service locks and viewer ownership. New terminal/service startup shares the state migration gate, so it cannot acquire a slot while migration holds that gate. Existing managed runtime leases remain independent and authoritative for installed releases.

The [tag workflow](../.github/workflows/release.yml) checks `v<version>` against the single version source, runs release regressions, builds the bundle and attaches public artifacts to a GitHub Release on a tag event. It is configured, not an executed GitHub run; no repository/tag is created automatically by local builds. Server upload remains the explicit publisher command using existing SSH authorization.

## Validation

See [RUNBOOK](RUNBOOK.md) for actual test counts and public download receipts. Local tests cover metadata/HTTPS/hash rejection, atomic activation failure, preserved state/options, cross-process locks, stale leases, rollback and immutable publication. Real package install/upgrade/rollback/uninstall is checked using isolated homes. Windows/macOS logic is not a native validation claim.

---

The following audit records the previous implementation and is superseded by the current behavior above.

## Historical audit before the 0.0.1 implementation — 2026-09-07

Question: are version management, updates and `loop update` complete? **No.** There is a stable-version check and a hosted installation prototype; an integrated update command and release lifecycle are missing. This is a local source review, not a new deployment verification or authorization to implement/publish.

| Area | Verified implementation / gap | Source |
| --- | --- | --- |
| Version management | `0.1.0` is separately defined in package metadata, package `__version__` and UI VERSION. No local Git tags were listed; only a platform smoke workflow exists, without tag-driven publication or version consistency enforcement. | [pyproject](../pyproject.toml), [package](../__init__.py), [UI](../terminal/ui.py), [CI](../.github/workflows/platform-smoke.yml) |
| `loop update` | Not implemented; positional CLI choices are ros/robot/node. Installed-entrypoint invocation returned exit 2 with invalid choice. | [launcher](../launcher.py), [CLI](../terminal/app.py) |
| Update checks | Installed launcher supports `--check-update` and `ros --check-update`; reports stable major.minor.patch comparison via latest.json. An isolated home without a release URL returned exit 1 with an actionable configuration error. Source `loop` and module `__main__` bypass this launcher; source `--check-update` returned exit 2. | [client](../release_client.py), [source entry](../loop), [module entry](../__main__.py) |
| Artifact delivery | Wheel, latest.json, SHA-256 check, HTTPS-only fetch and size/time limits exist. Hosted reinstall directly modifies one runtime using pip. No staged environment switch, health-check activation, automatic rollback, update lock or active-process coordination exists in this path. | [builder](../scripts/build_release.py), [client](../release_client.py) |
| Installer consistency | Source installation now bootstraps uv from Python 3.8 and supports launcher backup/replacement. Generated hosted bootstrap still rejects Python below 3.10, uses venv/pip and refuses conflicting source launchers. Hosted Windows installation explicitly raises an error. Build script also requires pip; the source uv flow does not seed pip. | [source installer](../scripts/install.py), [builder](../scripts/build_release.py), [client](../release_client.py) |
| Upgrade preferences | release.json stores only the release URL; terminal-only/simulation selection is not saved for future updates. Reinstall must receive the desired flag again. No version pin/channel selector, downgrade policy or state backup/migration orchestration is present in the updater. | [client](../release_client.py) |
| Public release | Existing deployment records state staging with unresolved valid HTTPS hosting. Public latest.json/wheel installation has not been verified in this audit. Documentation assertions about prior deployment are historical evidence, not a fresh network test. | [deployment](DEPLOYMENT.md) |

Validation: `PYTHONPATH=tests python3.12 -m unittest test_releases -q` passed 4 tests (comparison, manifest rejection, HTTPS validation, hash failure before installation). Direct launcher checks ran under isolated LOOP_HOME/LOOP_STATE_DIR/XDG_STATE_HOME with task autostart disabled; no server was contacted or configured. Source CLI rejection was also reproduced. Current `.venv` was absent, so tests used available Python 3.12; no environment was reinstalled. These tests do not cover a successful cross-version upgrade, interruption recovery or real remote delivery.

Suggested completion order (proposal, not implemented): (1) unify version/CLI entrypoints and record installation origin/options; (2) implement explicit update/check flow with a separately prepared runtime, smoke validation, process coordination and recoverable activation; (3) unify uv/bootstrap behavior and verify uninstall/update interactions; (4) validate immutable tagged release publication through a working HTTPS endpoint and a real old-to-new upgrade test. Keep stable-only versions unless preview channels are actually needed.
