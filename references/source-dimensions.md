# Source dimensions

## Purpose

Before gathering evidence for `capture`, `review`, or `rollover`, expand reachable local context by reading installed skills. This is orientation, not a separate data-fetch pipeline.

## Hard pre-read

1. Discover locally visible agent skills (common skill directories for the current IDE / agent, each skill’s `SKILL.md`).
2. Read skill `description` / capability summaries enough to know what information kinds they can surface.
3. Score the fixed dimensions below as **always on**, **available on this machine**, or **unavailable**.
4. Only then collect verifiable facts and call the CLI.

Do not hard-code a specific user’s skill list. Do not treat “skill present” as “fact obtained.”

## Fixed general dimensions

| # | Dimension | Default |
| --- | --- | --- |
| 1 | Facts the user stated in this turn | Always on |
| 2 | Current conversation / session context | Always on |
| 3 | Current workspace artifacts (Git, docs, plans, open items) | Always on |
| 4 | This week’s Apple Notes weekly progress note | Always on (via this skill’s `review` / Notes access) |
| 5 | Installed local skill capability descriptions | Always on — this is the pre-read entry |
| 6 | Meetings and post-meeting materials | Only if a local skill covers it |
| 7 | Email | Only if a local skill covers it |
| 8 | Tasks / cards / issues | Only if a local skill covers it |
| 9 | Code review and repository activity | Only if a local skill covers it |
| 10 | Knowledge base / Wiki / doc platforms | Only if a local skill covers it |
| 11 | Instant messaging / group chat | Only if a local skill covers it |
| 12 | Local knowledge caches when present | Only if readable locally |

Use category names, never bake vendor product names into this baseline. Matching is by capability text in local `SKILL.md` files.

## Evidence rules

- Writes still require facts the user explicitly supplied or that are verifiable in the materials actually read this turn.
- An available dimension with no readable evidence this turn is skipped.
- Optional short user-facing note: a capability exists locally but yielded no verifiable facts this turn.
- Do not invent progress to fill empty dimensions.
- Do not promise to read every AI IDE’s full history.

## After the pre-read

Follow the normal skill flow: classify facts, call `doctor` when needed, then `capture` / `review` / `rollover`. Invoke another skill only when that skill’s own trigger rules apply and doing so is needed to verify a fact—not because the dimension was merely marked available.
