---
title: Collaboration and delivery
scope: manage-weekly-progress
status: active
---

# Collaboration and delivery

## Working style

- Conversation language follows the user's language.
- Start every task by reading `CLAUDE.md`, `docs/CLAUDE.md`, and the relevant fact sources.
- Verify platform behavior before hardening it into design or implementation; never assume AppleScript, Notes HTML, or iCloud sync details from memory.
- Stay focused on the current phase; do not implement unaligned extension backends or automation ahead of time.
- Without explicit user authorization, the agent must not run `git commit`, `git push`, publish, or change remote resources.

## Documentation maintenance

- Content still under discussion or execution goes into `docs/plans/*`.
- Adopted facts that must be honored long-term are written back to `docs/design/*` or `docs/reference/*`.
- `CLAUDE.md` and `docs/CLAUDE.md` keep only stable entries and routing, never execution logs.
- Each piece of information has one fact source; other documents link to it.

## Skill development gate

- Create skill skeletons with the `skill-creator` initializer; do not hand-write a replacement initialization flow.
- `SKILL.md` frontmatter contains only `name` and `description`.
- Keep `SKILL.md` concise; move platform details and longer explanations into `references/` for on-demand reading.
- Use executable scripts for repetitive, error-prone Apple Notes operations, and actually run their tests.
- After implementing, run the skill validation script and forward-test with real invocation scenarios.

## Pre-delivery checklist

- Verify scripts never overwrite user content outside the managed region.
- Verify repeated invocations do not create duplicate records.
- Verify failure paths: missing target week, missing Notes permission, unavailable account/folder, and iCloud latency.
- Verify compatibility at least once each in Codex, Claude Code, and Cursor, or explicitly record the platforms not yet verified.
- Before publishing, confirm the repository contains no personal note content, Apple account information, or other sensitive data.
