# Changelog

Version numbering starts at 0.0.1. Earlier 0.1.0/0.2.0 development wheels were unpublished local candidates, not released versions.

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
