---
title: Local skill source-dimension pre-read
scope: manage-weekly-progress
type: design
status: completed
---

# Local skill source-dimension pre-read

## Goal

Before capture / review / rollover (or equivalent user intent such as “整理本周并同步备忘录”), the agent must expand what counts as reachable local context by reading installed skills—not by hard-coding one machine’s tools.

## Decision

Use a **SKILL.md-only hard pre-step** (no new CLI, no skill whitelist, no per-machine customization):

1. List locally visible skills via their `SKILL.md` descriptions.
2. Map them against a fixed baseline of **12 general source dimensions**.
3. Mark dimensions 6–12 as available only when a matching local skill (or readable local cache) exists.
4. Pre-read those skill boundaries as orientation, then extract only user-explicit or currently verifiable facts under the existing capture rules.

“Available” means “may look here,” never “already obtained facts.” Missing evidence skips the dimension; do not invent progress.

## Fixed general dimensions

1. Facts the user stated in this turn
2. Current conversation / session context
3. Current workspace artifacts (Git, docs, plans, open items)
4. This week’s Apple Notes weekly progress note
5. Installed local skill capability descriptions (hard pre-read entry)
6. Meetings and post-meeting materials
7. Email
8. Tasks / cards / issues
9. Code review and repository activity
10. Knowledge base / Wiki / doc platforms
11. Instant messaging / group chat
12. Local knowledge caches when present

## Non-goals

- Auto-fetching or auto-invoking every discovered skill
- Maintaining a dimension→skill name registry for a specific company stack
- Claiming full IDE history coverage
- New CLI commands such as `discover-sources`

## Verification baseline

- `SKILL.md` requires the pre-read before evidence gathering or writes for capture / review / rollover.
- `references/source-dimensions.md` lists the 12 dimensions and usage rules.
- Core design documents that “current agent context” is expanded by this pre-read, while write safety and fact rules stay unchanged.
