# Changelog

Version numbering starts at 0.0.1. Earlier 0.1.0/0.2.0 development wheels were unpublished local candidates, not released versions.

## 0.0.3 — core and release audit (2026-09-08, candidate)

- Reject unreviewed runtime files and missing package data before building; install the actual wheel in an isolated environment and require offline App startup before exporting the bundle.
- Build wheel and bootstrap from one source snapshot; share manifest validation and reject conflicting pinned release metadata before publication.
- Use canonical loop_robot imports, retaining source commands and the older updater's import handshake. Move simulated feedback policies into toolchain and the mock body into source-only examples; append Episode/Review pairs atomically.
- Stop process Nodes with SIGINT and retain live workers/resources after a timeout. Check all terminal runtime slots during migration and serialize startup with migration checks.
- Run public-source index checks in CI and add a local pre-push inventory check covering outgoing commits.
- Preserve explicit deferred-answer callbacks while continuing to display ordinary tool progress; retain direct source __main__.py startup.

- Add a dependency-free no_std Rust execution kernel, C ABI and ESP32-C3 Arduino C++ edge-agent development port. Host/MCU builds and C++ linkage are verified; board flashing, live model calls and other MCU ports remain pending.
- Publish bilingual installation steps for Linux/ARM hosts and separate MCU development builds, with explicit validation status and private website-source backups.
- Separate CLI releases from private website source and source-only examples. Keep required simulation scenes and local workbench assets under assets; publish only the wheel, bootstrap, installers and manifests.
- Remove the four-tool-call limit per model response in stream parsing and execution; distinguish malformed JSON, incomplete streams, invalid call indices and field errors without misleading API-type advice.

## 0.0.2 — CLI sessions and execution workflow (2026-09-07)

- Support concurrent CLI terminals with isolated runtime slots and shared user state; start a fresh conversation on launch and resume history explicitly.
- Improve task/session navigation, tool output display and queued-input handling.
- Separate user statements, assistant notes and observed evidence in memory; prefer indexed local operations notebooks for recurring work.
- Simplify execution guidance, preserve the source of runtime stop messages and expose paginable Python output.
- Preserve endpoint-bound user configuration and credentials across the current configuration migration.
- Keep user-generated scripts, Skills, notebooks and runtime artifacts outside public release bundles.

The general robot start/control/stop lifecycle is not a completed hardware integration. Native macOS/Windows and real robot behavior are not established by the Linux release checks.

## 0.0.1 — initial hosted release (2026-09-07)

Initial candidate scope: conversational coding, evidence-based feedback loops, persistent tasks, Loop Nodes, carrier routing, experience notes and optional robotics tools.

- Add uv source/hosted installation, unified update/check entrypoints, verified environment activation, rollback, runtime leases, state backups and immutable publication tooling.
- Use a single version source and a tag-triggered release workflow.
- Consolidate base, robotics and result prompts into general goal/execution/evidence contracts.
- Recommend GPT-6 Astra in first-run setup using the existing Responses adapter; add a custom API example. Preserve existing profiles and providers.
- Replace outdated README claims with a capability and implementation-boundary table.
- Document GitHub preparation and the PhyAgentOS design reference.

Additional coding-first cleanup: remove phrase-specific preflights, appended robotics prompts, automatic state injection, forced domain replies and implicit task handoff. Keep 21 default tools, three explicit specialist toolsets, session memory and registered domain tools.

Known follow-ups: Responses streaming/output-budget controls and live GPT-6 validation are pending. The HTTPS 0.0.1 bundle is published; public GitHub repository/Release and license selection remain separate follow-ups.
