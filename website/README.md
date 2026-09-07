# Loop ROS introduction page

Public bundle generation, HTTPS bootstrap and update checks are now implemented; see [RELEASES](../docs/RELEASES.md). Files are staged on the authorized server; public hosting awaits a valid HTTPS hostname (see [DEPLOYMENT](../docs/DEPLOYMENT.md)). The builder adjusts public asset paths without publishing private workspace files.

Open `index.html` directly in a browser. No build step, external font, analytics, CDN or server is required. Existing `example.html` is a user-provided reference and remains unchanged; it is not part of the new site.

From the project directory:

- Linux: `xdg-open website/index.html`
- macOS: `open website/index.html`
- Windows PowerShell: `Start-Process website/index.html`

The installation selector offers Linux/macOS HTTPS download-and-install commands, Windows local PowerShell, terminal-only mode and the legacy SSH route. Clipboard copy uses the browser API; if blocked (including some file:// contexts), it selects the command for manual copying. It does not execute commands or collect credentials.

The source preview targets the user-confirmed server at `https://8.134.90.171/LoopROS/install.sh` and explicitly marks download as pending. On 2026-09-05, HTTPS returned curl error 60 (certificate name mismatch); HTTP redirected to HTTPS. The release builder replaces the preview base URL in both HTML (including noscript) and JavaScript with its supplied HTTPS base URL. Default: `curl -fsSL …/install.sh | sh`; terminal-only: `curl -fsSL …/install.sh | sh -s -- --terminal-only`. A public deployment must publish a reviewed source release and package only these public assets, `logo.png` and the linked installation/platform documentation; never publish the whole working tree or user configuration. Publishing is not performed by these scripts.

Validation: `node --check website/site.js`; `node --test tests/website.test.cjs`; real local headless Chrome desktop screenshot inspected. Native PowerShell installation and macOS remain unverified.

Logo: the existing `../logo.png` uses the same infinity-robot design as [LoopMaster](https://loopmaster.ai/). The navigation renders it at 56px wide with its original aspect ratio. `favicon.png` is the original 128×128 icon downloaded from https://loopmaster.ai/favicon.png on 2026-09-05 using Chrome; the release builder includes it. The original project logo and terminal mark are preserved.
