# GitHub release preparation

Current local target: Loop ROS 0.0.3 candidate. Version remains sourced from `_version.py` through `pyproject.toml`; this does not create a published tag. Historical server releases are recorded separately in DEPLOYMENT.

Use the existing README, changelog, `pyproject.toml` and platform-smoke workflow as the repository entry points. Reference PhyAgentOS for clear task/execution/evidence boundaries and explicit implementation status, rather than importing its entire framework.

## Before publication

1. Confirm the GitHub owner/repository, visibility and project license. No project LICENSE has been selected in this workspace; the reference project's license does not automatically license Loop ROS.
2. Prepare a clean source inventory. Exclude runtime state, credentials, local configuration, downloaded assets and private deployment records. `.gitignore` is a baseline, not a content audit. In particular, review `docs/DEPLOYMENT.md`, `docs/RELEASES.md`, `docs/RUNBOOK.md`, website examples and scripts before including them: these currently contain workstation/server-specific records. Do not push the whole workspace.
3. Run relevant regressions and build a wheel with the existing packaging configuration. Inspect the archive contents and test installation in a clean environment. Existing CI is terminal smoke coverage, not proof of simulation/hardware support on every platform.
4. Validate the intended GPT-6 endpoint using text, tools, image input when needed, errors and cancellation. Record actual evidence; model selection alone is not validation.
5. Create the confirmed remote repository and release only after the source inventory, license and target are resolved. Upload immutable artifacts and checksums, then publish release notes. The custom HTTPS installer workflow is separate from GitHub source publication.

## Current preparation

README, changelog, GPT-6 example, simplified prompts and first-run recommendation are prepared locally. Existing user profiles and downloaded assets are preserved. The local wheel and SHA256SUMS are under `artifacts/release-candidate/`; inventory and project-external startup checks passed (existing interpreter dependencies). The local repository exists. No new remote push, tag or GitHub Release is created by this preparation; hosted publication is recorded separately in DEPLOYMENT. The tag workflow is configured in `.github/workflows/release.yml`, not yet run on GitHub.

## Framework follow-ups

Keep one permission gate and structured receipt path. Unify capability metadata and receipt interpretation before removing redundant adapters. Weather/scene/device sentence preflights have been removed at the user’s request. Offline regressions cover model-selected tools and permission/evidence boundaries; actual model behavior still requires release evaluation. Domain units, device protocols and state validation belong in tool implementations and schemas.


## User content and unreviewed candidates

User projects (`user_projects/`), Skills/tools, toolchain/candidates, and local device scripts must remain outside Git staging and public uploads. .gitignore includes local package paths, the candidate directory, and a root-Python maintained-module allowlist. Only the three explicitly maintained simulation SKILL.md defaults are release data. Do not copy user packages back into distribution defaults.

scripts/build_release.py now builds from a temporary copy of Git-tracked, non-ignored working files. This uses current working contents, not necessarily HEAD contents; intended new public source must first be staged, while ignored content remains excluded even if force-staged. Symlinks require explicit review and are rejected by this source-copy step. This does not mark source as reviewed or publish anything. A raw build command outside this audited entry is not the public-release upload workflow.

From 0.0.3, the builder rejects untracked runtime files, missing declared data and a wheel that cannot initialize offline. CI runs test_public_source and the shared scripts/check_public_source.py index check. The repository-local pre-push hook also checks outgoing commits, so deleting a private file only from the final tree does not hide its earlier outgoing commit. Internal operational document contents still require source-publication review.

Generated-code classification and pre-commit index checks: [storage rules](GENERATED_CODE.md). Public source assembly independently excludes user_projects even when force-staged without an ignore rule.
