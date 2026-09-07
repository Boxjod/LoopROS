# Changelog

## 0.1.0 — release preparation (2026-09-07)

Initial candidate scope: conversational coding, evidence-based feedback loops, persistent tasks, Loop Nodes, carrier routing, experience notes and optional robotics tools.

- Consolidate base, robotics and result prompts into general goal/execution/evidence contracts.
- Recommend GPT-6 Astra in first-run setup using the existing Responses adapter; add a custom API example. Preserve existing profiles and providers.
- Replace outdated README claims with a capability and implementation-boundary table.
- Document GitHub preparation and the PhyAgentOS design reference.

Additional coding-first cleanup: remove phrase-specific preflights, appended robotics prompts, automatic state injection, forced domain replies and implicit task handoff. Keep 21 default tools, three explicit specialist toolsets, session memory and registered domain tools.

Known follow-ups: Responses streaming/output-budget controls and live GPT-6 validation are pending. Public repository, license selection and release publication are not complete.
