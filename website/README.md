# Loop ROS introduction page

Public bundle generation, HTTPS bootstrap and update checks are now implemented; see [RELEASES](../docs/RELEASES.md). Version 0.0.1 is hosted at `https://loopmaster.box2ai.com/LoopROS` (see [DEPLOYMENT](../docs/DEPLOYMENT.md)). The existing introduction page is now deployed at that same URL. `scripts/build_website.py` exports its seven public files; release builds reuse it and exclude private workspace documents.

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
