# GitHub release preparation

Target scope: Loop ROS 0.1.0 initial candidate. Version remains consistent with `pyproject.toml`; this is not a published tag.

Use the existing README, changelog, `pyproject.toml` and platform-smoke workflow as the repository entry points. Reference PhyAgentOS for clear task/execution/evidence boundaries and explicit implementation status, rather than importing its entire framework.

## Before publication

1. Confirm the GitHub owner/repository, visibility and project license. No project LICENSE has been selected in this workspace; the reference project's license does not automatically license Loop ROS.
2. Prepare a clean source inventory. Exclude runtime state, credentials, local configuration, downloaded assets and private deployment records. `.gitignore` is a baseline, not a content audit. In particular, review `docs/DEPLOYMENT.md`, `docs/RELEASES.md`, `docs/RUNBOOK.md`, website examples and scripts before including them: these currently contain workstation/server-specific records. Do not push the whole workspace.
3. Run relevant regressions and build a wheel with the existing packaging configuration. Inspect the archive contents and test installation in a clean environment. Existing CI is terminal smoke coverage, not proof of simulation/hardware support on every platform.
4. Validate the intended GPT-6 endpoint using text, tools, image input when needed, errors and cancellation. Record actual evidence; model selection alone is not validation.
5. Create the confirmed remote repository and release only after the source inventory, license and target are resolved. Upload immutable artifacts and checksums, then publish release notes. The custom HTTPS installer workflow is separate from GitHub source publication.

## Current preparation

README, changelog, GPT-6 example, simplified prompts and first-run recommendation are prepared locally. Existing user profiles and downloaded assets are preserved. The local wheel and SHA256SUMS are under `artifacts/release-candidate/`; inventory and project-external startup checks passed (existing interpreter dependencies). No Git repository, remote push, tag or GitHub release has been created by this preparation.

## Framework follow-ups

Keep one permission gate and structured receipt path. Unify capability metadata and receipt interpretation before removing redundant adapters. Weather/scene/device sentence preflights have been removed at the user’s request. Offline regressions cover model-selected tools and permission/evidence boundaries; actual model behavior still requires release evaluation. Domain units, device protocols and state validation belong in tool implementations and schemas.
