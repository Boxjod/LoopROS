# Loop ROS introduction page

Public bundle generation, HTTPS bootstrap and update checks are now implemented; see [RELEASES](../docs/RELEASES.md). Version 0.0.1 is hosted at `https://loopmaster.box2ai.com/LoopROS` (see [DEPLOYMENT](../docs/DEPLOYMENT.md)). The existing introduction page is now deployed at that same URL. `scripts/build_website.py` exports its 12 public files (including the workbench); release builds reuse it and exclude private workspace documents.

Open `index.html` directly in a browser. No build step, external font, analytics, CDN or server is required. Existing `example.html` is a user-provided reference and remains unchanged; it is not part of the new site.

From the project directory:

- Linux: `xdg-open website/index.html`
- macOS: `open website/index.html`
- Windows PowerShell: `Start-Process website/index.html`

The installation selector offers Linux/macOS HTTPS download-and-install commands, Windows hosted PowerShell download, terminal-only mode and the legacy SSH route. Clipboard copy uses the browser API; if blocked (including some file:// contexts), it selects the command for manual copying. It does not execute commands or collect credentials.

The source preview targets `https://loopmaster.box2ai.com/LoopROS/install.sh`. The server domain passed verified HTTPS and real installation on 2026-09-07. Default: `curl -fsSL …/install.sh | sh`; terminal-only: `curl -fsSL …/install.sh | sh -s -- --terminal-only`. Public release publication uses `scripts/publish_release.py`; never publish the whole working tree or user configuration.

Validation: `node --check website/site.js`; `node --test tests/website.test.cjs`; real local headless Chrome desktop screenshot inspected. Native PowerShell installation and macOS remain unverified.

Logo: the existing `../assets/logo.png` uses the same infinity-robot design as [LoopMaster](https://loopmaster.ai/). The navigation renders it at 56px wide with its original aspect ratio. `favicon.png` is the original 128×128 icon downloaded from https://loopmaster.ai/favicon.png on 2026-09-05 using Chrome; it remains part of this source preview. The original project logo and terminal mark are preserved.


Website-only deployment:

```sh
python3 scripts/build_website.py --output /absolute/new/website-bundle
python3 scripts/publish_website.py --bundle /absolute/new/website-bundle --host root@8.134.90.171 --destination /www/wwwroot/loopmaster.box2ai.com/LoopROS
```

The whitelist is index.html, zh-CN.html, install.html, style.css, site.js, favicon.png and logo.png. No project deployment/private docs or example.html are uploaded. Existing web files are backed up in private server staging; SHA256SUMS updates only the website entries. Wheel, bootstrap, install/uninstall scripts and release manifests are checked unchanged. Nginx serves CSS/JS/PNG with matching MIME types.

2026-09-07 live Chrome validation passed at 1440×1000 and 390×844: logo, page version, platform selector, terminal-only command, installation guide, no horizontal mobile overflow and no page errors. [Receipt](../artifacts/website-live-20260907/browser-result.json), [desktop](../artifacts/website-live-20260907/desktop.png), [mobile](../artifacts/website-live-20260907/mobile.png).

The default English page is `index.html`; `zh-CN.html` provides Simplified Chinese. Both link Docs directly to the corresponding GitHub README. `install.html` redirects to the English README. Installation tabs cover Linux, macOS, Windows PowerShell, Windows CMD and legacy SSH.

2026-09-07 bilingual deployment: both languages, all five platform selectors and 320/390px mobile layouts passed live Chrome verification. Seven public asset bytes matched the export via verified HTTPS. Docs READMEs are published on GitHub in commit `af5ac4b`. [Receipt](../artifacts/website-bilingual-20260907/browser-result.json).

## Visual simulation workbench (2026-09-07)

`workbench.html` adds an actual 3D layout viewer and local simulation controls. Both homepages link to it. Open through `loop web` or, from source, `.venv/bin/python -m terminal.web_workbench`, then visit `http://127.0.0.1:8768/workbench.html`. Optional `--port`, `--state-dir`, `--isaac-config` arguments select the local runtime; MuJoCo requires the sim extra, dataset recording requires h5py. `loop web --help` does not start physics.

The static exported page shows a labelled sample room and local-start instructions. The same page served by the local Python process can create actual MuJoCo/Isaac instances, build a room, import local models, select/move/remove bodies, step/reset physics, configure and capture cameras, define a position task, and record/download HDF5. The right panel is an operator control panel and receipt log; it is not an AI chat interface. Refreshing the page reconnects to the web service's existing instances; stopping that process closes its owned simulations. Instances are separate from other CLI/MCP processes and GUI windows.

MuJoCo layout uses current simulator geometry and transforms; it does not reproduce textures. Isaac layout uses available authored bounding boxes and is explicitly marked approximate; robot meshes may be absent. The camera tab displays actual, timestamped simulator snapshots, with RGB/NPZ downloads and calibration; it is not a live video stream. Reference [simulation contract](../docs/SIMULATION_WORKBENCH.md). Physics is advanced only through bounded operator actions. A room preset executes sequential additions; if one fails, completed additions remain visible and the failure is reported, without replaying the sequence automatically.

The local stdlib HTTP server listens only on loopback, validates Host/Origin and same-origin action tokens, serves only whitelisted static assets and generated artifacts, and uses the existing PermissionGate. Operator-only one-time approval is available in a separate dialog. There is no browser API to execute arbitrary Python, change model credentials or grant persistent permissions. This local service is not a public multi-user web server. The static website does not automatically connect to localhost.

The export/publish whitelist now has 12 assets: the previous seven plus `workbench.html`, `workbench.css`, `workbench.js`, `three.module.min.js`, `three.LICENSE.txt`. Source `example.html`, API code, user state and generated datasets remain outside the public export. The workbench was not deployed to the public website in this change. [Three.js source and license](THIRD_PARTY.md).
