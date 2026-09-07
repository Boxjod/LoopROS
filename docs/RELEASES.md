# Hosted installation and update checks

Implementation is ready for a static HTTPS host. Authorized target: `root@8.134.90.171`, directory `/root/workspaces/LoopROS`. Root SSH now succeeds after permission was granted. Files are staged; a valid authorized HTTPS hostname remains unresolved and no public Loop ROS URL is live. Current status: [DEPLOYMENT](DEPLOYMENT.md). The following paragraph records the earlier failed attempt, not current SSH status.

2026-09-05 read-only checks: TCP/SSH reachable, but current agent keys rejected for both root and the local default account boxjod. No matching target alias found in the current SSH config. HTTP redirects to HTTPS; the IP certificate names mingle.box2ai.com/www.mingle.box2ai.com, not the IP. A direct SNI/certificate check for mingle.box2ai.com also fails certificate expiry validation. That domain is observed certificate metadata, not an authorized deployment hostname. No remote directory was created and no existing website/configuration was changed. Obtain the correct SSH account/key alias and confirm an HTTPS hostname before publication; do not use curl -k or disable verification.

## Build a public bundle

From the project directory, with a final HTTPS URL and a fresh output directory:

```sh
.venv/bin/python scripts/build_release.py --url https://YOUR-DOMAIN/loop --output /absolute/new/release-directory
```

This builds a wheel without dependency wheels, audits known private paths, then copies only the wheel, metadata, bootstrap, website assets and selected public docs. Never upload the entire repository, .loop, config.local.json, runtime databases or the user-supplied website/example.html. The output URL is compiled into install.sh; do not change the host/path without rebuilding.

Upload the resulting files to that URL. Publish immutable versioned wheels before changing latest.json; replace metadata atomically. Do not reuse an existing version number for changed release code. Configure HTTPS and serve scripts as text/plain. Server setup, TLS and remote commands must be verified against the actual deployment destination; none has been invented here.

## End-user installation (after publication)

```sh
curl -fsSL https://YOUR-DOMAIN/loop/install.sh | sh
# API terminal only:
curl -fsSL https://YOUR-DOMAIN/loop/install.sh | sh -s -- --terminal-only
```

Replace the placeholder with the deployed URL. The script requires an existing compatible Python 3.10+ and curl; it does not replace system Python. LOOP_PYTHON selects a private interpreter. Users can download and inspect the script before running it instead of piping to sh.

The bootstrap retrieves latest.json and its wheel over HTTPS, checks SHA-256, installs in ~/.loop/runtime, and creates ~/.local/bin/loop and loop-switch. It saves only the release server URL in ~/.loop/release.json; configuration/keys are not overwritten. Explicit LOOP_HOME is honored. Existing unrelated/source-install command links are refused, not silently replaced. The existing workstation source install is not automatically migrated to hosted installation. Windows currently retains its local PowerShell installer; this hosted bootstrap is Linux/macOS only, with macOS native validation pending.

Dependencies are resolved by pip from the user's configured index; they are not bundled or hash-pinned by this release manifest. SHA-256 detects artifact mismatch; it is not an independent publisher signature and cannot protect against a compromised HTTPS release server.

## Check and apply updates

```sh
loop --check-update
# Also accepted:
loop ros --check-update
```

Checks report installed/latest stable versions and update_available as JSON, use a 20-second network timeout and never install anything. The server is read from LOOP_RELEASE_URL or ~/.loop/release.json. No server configured, malformed metadata or network failure yields a nonzero exit with an explanation. There is no hidden startup network request, background timer or automatic upgrade.

To install an update in an existing hosted runtime, exit Loop ROS and rerun the installer from the same trusted URL, keeping --terminal-only if desired. Existing configuration and runtime state are retained. Dependency changes occur within the same runtime venv; transactional upgrade/rollback is not implemented, so a failed pip update can require rerunning installation. Source installations should use their source workflow, not bypass command collision protection.

Verification: unit tests cover newer/equal/older versions, HTTPS constraints, invalid manifest/path traversal and checksum rejection before installation. Build/packaging smoke evidence is recorded in RUNBOOK. Public HTTPS deployment and actual remote curl installation remain unverified until a server is supplied.
