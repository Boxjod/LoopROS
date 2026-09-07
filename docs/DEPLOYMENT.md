# Loop ROS deployment

## Current: initial version 0.0.1 — 2026-09-07

Published the first version **0.0.1** to the authorized server `root@8.134.90.171`. Earlier 0.1.0/0.2.0 artifacts were local development candidates, never official releases. The application is distributed as a Python wheel with uv bootstrap; it is not a standalone native executable.

- Public base: `https://loopmaster.box2ai.com/LoopROS`
- Linux/macOS install: `curl -fsSL https://loopmaster.box2ai.com/LoopROS/install.sh | sh -s -- --terminal-only`
- Release metadata: `https://loopmaster.box2ai.com/LoopROS/latest.json`
- Wheel: `loop_ros-0.0.1-py3-none-any.whl`
- Wheel SHA-256: `84deb04d7000e8b69bf8f01324ce3bf88b4f023b620aa62495bccf6c662fa3f4`
- Public server directory: `/www/wwwroot/loopmaster.box2ai.com/LoopROS`
- Verified private staging: `/root/workspaces/LoopROS/releases/0.0.1-84deb04d7000/bundle`
- Local exact bundle: `artifacts/release-0.0.1-final/` (immutable published version; do not rebuild and overwrite it with changed bytes).

The domain resolves to the supplied IP and passed verified HTTPS requests. Its existing certificate is valid from 2026-07-10 through 2026-10-07; no certificate or private-key changes were made. The IP URL remains unsuitable for direct HTTPS because the certificate names the domain.

The existing vhost forwards `/` to its application. Added only `/www/server/panel/vhost/nginx/extension/loopmaster.box2ai.com/loopros-release.conf`, routing `/LoopROS/` to static release files and hiding the publication lock. `nginx -t` passed before a graceful reload. Existing application routes, Mingle configuration, website root content, root-directory permissions and running robot/simulation services were not replaced. Scripts are served as text/plain; metadata switches after the immutable wheel is available.

Validation: all eight SHA256SUMS-listed public files were downloaded via verified HTTPS and matched the local hashes (plus the published checksums file). In a temporary Linux home, real server installation bootstrapped from Python 3.8 to a uv Python 3.12 runtime, launched `Loop ROS 0.0.1` outside the project, checked latest with both `loop update --check` and `loop ros --check-update`, ran an already-current update, and uninstalled while retaining a user Skill. Details: [live receipt](../artifacts/release-validation/live-result.json), [log](../artifacts/release-validation/live-e2e.log), [publication](../artifacts/release-validation/publish.log), [nginx check](../artifacts/release-validation/nginx.log).

GitHub tag/Release workflow is configured locally but has not run; this server publication does not create a GitHub repository, tag or Release. Windows/macOS native installation and real model/hardware operations are not covered by these receipts. Subsequent source edits belong to a later version and must not mutate published 0.0.1.

## Introduction website — 2026-09-07

The full existing introduction website now replaces the minimal release index at `https://loopmaster.box2ai.com/LoopROS/`. Public files are index.html, install.html, style.css, site.js, favicon.png and logo.png. Version and links match 0.0.1; documentation links use a dedicated public guide rather than private workspace docs. The nginx location now includes CSS/JavaScript/PNG MIME types; configuration check and graceful reload passed.

Website-only publication saved old assets in private staging (path in [deployment receipt](../artifacts/website-live-20260907/deploy.log)) and updated current SHA256SUMS web entries. The immutable original release bundle remains unchanged locally; live website bytes may evolve separately. The wheel hash, latest.json, versioned manifest, bootstrap and install/uninstall scripts were verified unchanged. Live browser tests and individual HTTPS asset comparisons passed; [browser receipt](../artifacts/website-live-20260907/browser-result.json). Future release builds export this website instead of regenerating the earlier minimal index.

## Bilingual website and GitHub Docs — 2026-09-07

The official website now defaults to English (`index.html`) with a Simplified Chinese page (`zh-CN.html`). Docs links directly to `https://github.com/Boxjod/LoopROS#readme` or `https://github.com/Boxjod/LoopROS/blob/main/README.zh-CN.md`; the old install.html route redirects to the English README. Both READMEs provide Linux, macOS, Windows PowerShell, Windows CMD and legacy SSH commands. Linux installation is verified; native macOS/Windows validation remains pending.

GitHub documentation-only commit `af5ac4b` was pushed to main from an isolated worktree at `/tmp/loopros-public-docs-20260907`. Existing working-tree code was not published. Public README source instructions describe the older GitHub source snapshot; hosted 0.0.1 installation is the primary multi-platform route. Local READMEs retain instructions for the newer local source installer. The gh CLI returned 401, but the existing Git credential helper successfully pushed; no credentials were changed.

Website publication added zh-CN.html to the public whitelist. The publisher verified protected release downloads unchanged. Live Chrome checks passed for English/Chinese, default English with a Chinese browser locale, five platform selectors, terminal-only commands, Docs targets and 320/390-pixel mobile layouts without overflow or page errors. Seven HTTPS asset byte comparisons passed with curl; system Python 3.8 urllib failed its local CA lookup, so it was not used for these comparisons. Receipts: [deployment](../artifacts/website-bilingual-20260907/deploy.log), [browser/assets](../artifacts/website-bilingual-20260907/browser-result.json). JS tests passed in both languages; publishing scripts passed Python syntax checks.

## Historical deployment records (superseded by the current status above)


Updated 2026-09-05. Authorized host: `root@8.134.90.171`, SSH port 22 using existing agent keys. Root login succeeded after the user granted access. Project directory: `/root/workspaces/LoopROS`.

Status: staged, not publicly served. `staging/loopros-server-stage-20260905/` contains the generated wheel, latest.json, bootstrap.py, install.sh, public website assets and selected docs, without user credentials or runtime databases. Provisional base URL: `https://8.134.90.171/LoopROS`; unusable until TLS is resolved. Rebuild with the final authorized HTTPS hostname before publishing.

Nginx runs as www, configured under `/www/server/nginx/conf/nginx.conf` and `/www/server/panel/vhost/nginx/`. The existing Mingle vhost names both mingle.box2ai.com and 8.134.90.171. Do not replace it or remove its HTTPS redirect. `/root` is not traversable by www; do not broaden root-directory permissions to serve static files. Select a dedicated public directory or narrowly scoped serving arrangement after hostname confirmation.

No nginx configuration, existing web content, TLS certificate or services were modified. Final hostname/valid TLS remains unresolved; no curl -k / verification bypass. Server project README.md mirrors this record. Source workflow: docs/RELEASES.md. Staging copies of earlier docs describe prior state; this record supersedes them.

2026-09-05 user reconfirmed the server IP `8.134.90.171`. The website preview now shows `https://8.134.90.171/LoopROS/install.sh` with a pending-HTTPS notice. Read-only recheck: SSH succeeds; HTTP install URL returns 301 to HTTPS; HTTPS returns curl error 60, certificate subject does not match the IP. Nginx also has a separate `loopmaster.box2ai.com` vhost; that hostname has not been selected by the user for this release. No server configuration or public files changed in this check.


2026-09-07 read-only recheck: root SSH still succeeds and the staged project directory exists. HTTPS `https://8.134.90.171/LoopROS/install.sh` still fails curl error 60 (certificate hostname mismatch). Both READMEs now link the provisional server page/script and explicitly mark them unavailable. A user-selected valid HTTPS release hostname is still required; no nginx/TLS/public file changes have been made.
