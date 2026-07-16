---
title: manage-weekly-progress initial design and handoff
scope: manage-weekly-progress
type: design
status: completed
---

# manage-weekly-progress initial design and handoff

## Goal

Design and implement a general-purpose skill distributable via skills.sh that lets AI IDEs such as Codex, Claude Code, and Cursor record, review, summarize, and roll over personal progress week by week using Apple Notes.

## Current conclusions

- The skill, directory, and GitHub repository are uniformly named `manage-weekly-progress`.
- The product is not limited to work logs; target scenarios include work, personal development, learning, meetings, and document follow-up.
- The MVP persists only to Apple Notes, writing through macOS Notes capabilities and syncing via iCloud.
- Reminders and Calendar form an optional notification layer: they are created automatically only for key milestones with explicit times, deadlines, or fixed schedules, and never act as a second progress store.
- The skill operates automatically inside managed containers it created and registered, minimizing interruptions; user objects and objects of unclear ownership are not modified by default.
- The main environment is a single Mac; multi-Mac setups use the same Apple account with iCloud Notes sync.
- The natural week is the management unit and dates are the primary organization; weekly goals and the weekly summary are auxiliary.
- MVP core actions: `capture`, `update`, `review`, and `rollover`.
- No extra server or database is built, and no automatic collection of all IDE history.

The stable design has been consolidated into `../design/core/weekly-progress-management.md`.

The overall flow prototype is [`2026-07-16-weekly-progress-flow-prototype.html`](2026-07-16-weekly-progress-flow-prototype.html), used to confirm first-run initialization, daily recording, notification routing, and the weekend review; it connects to no real Apple data.

## Implemented repository structure

```text
manage-weekly-progress/
├── SKILL.md
├── CLAUDE.md
├── AGENTS.md -> CLAUDE.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── manage_weekly_progress.py
│   ├── mwp/
│   └── applescript/
├── references/
│   ├── input-schema.md
│   └── platform-behavior.md
├── tests/
└── docs/
    ├── CLAUDE.md
    ├── AGENTS.md -> CLAUDE.md
    ├── reference/
    ├── design/core/
    └── plans/
```

The skill is implemented under `skill-creator` constraints. A Python CLI owns the model, input validation, the HTML managed region, and orchestration; three independent AppleScripts adapt Notes, Reminders, and Calendar; tests cover pure units, adapters, and the real macOS end-to-end loop.

## Progress

- [x] Confirmed target users and a product positioning not limited to work.
- [x] Chose the skill name `manage-weekly-progress`.
- [x] Chose Apple Notes + iCloud as the MVP storage.
- [x] Confirmed the primary device environment and the multi-Mac same-account scenario.
- [x] Chose a date-first note structure with weekly goals and summary as auxiliary.
- [x] Formed the first version of core capabilities and safety boundaries.
- [x] Confirmed automatic creation and registration of dedicated containers on first use, with automatic operation inside the managed space afterward.
- [x] Confirmed reminders or calendar events are auto-created only for key milestones with explicit times.
- [x] Confirmed user triggering, Monday-through-Sunday weeks, system default timezone, and configurable IANA timezone.
- [x] Verified Apple Notes body format, locating, creation, update, and cleanup behavior.
- [x] Completed error handling, idempotency, managed region, optimistic concurrency, and notification conflict strategies.
- [x] Formed the complete design and obtained user approval.
- [x] Initialized and implemented the skill structure under `skill-creator` constraints.
- [x] Wrote and tested repeatable Notes, Reminders, and Calendar operation scripts.
- [x] Completed `SKILL.md` and `agents/openai.yaml`.
- [x] Ran structure validation, unit tests, and the real-app forward test on the current Mac.
- [x] Prepared skills.sh publishing content; actual publishing awaits separate user authorization.

## Implementation conclusions

- Default week boundary is ISO Monday through Sunday, default system timezone, configurable IANA timezone.
- The first live write creates dedicated containers on demand; macOS system authorization cannot be bypassed and denial returns an actionable error.
- Notes uses visible managed markers plus optimistic concurrency validation to protect manual content; duplicate titles, malformed markers, or concurrent body changes stop safely.
- Reminders uses stable list IDs; Calendar uses a random ownership token written into the description; both sync only key milestones with explicit times.
- Explicit keys persist in visible Notes timing metadata, so rollover, update, completion, and deletion keep the same notification identity.
- Actual skills.sh publishing was not executed here and still requires explicit user authorization.

## Closed design questions

- The default container name is `Weekly Progress`, with explicit configuration allowed; renaming clears the registered ID, and the next relevant write creates a new managed container without deleting the old one.
- Same section plus normalized text drives content idempotency; explicit keys drive notification identity.
- Only facts explicitly provided by the user or verifiable in the current context are extracted; missing fields are never guessed by source type.
- The weekly summary is triggered by user request or by rollover's deterministic record, never by background monitoring.
- Duplicate Notes titles, damaged managed markers, permission failures, lost ownership, and unready sync all return structured errors.
- Same-named but unmanaged containers are never adopted; a collision-safe managed name is created instead.
