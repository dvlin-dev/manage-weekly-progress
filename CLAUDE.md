# manage-weekly-progress

> This file is the repository-level collaboration entry point. It records only stable identity, boundaries, hard constraints, and document routing.

## Project overview

`manage-weekly-progress` is a general-purpose progress-management skill for AI IDEs / coding agents. It works in natural weekly cycles, writes through the macOS Notes app, and relies on iCloud sync, so that agents such as Codex, Claude Code, and Cursor can keep recording, reviewing, and rolling over the same weekly progress. For key milestones with explicit times, it can optionally use Reminders and Calendar for notifications.

It fits work as well as personal development, learning, and other long-running efforts; a "work log" is not the only intended scenario.

## Core sync protocol

1. `CLAUDE.md` is the repository-level main entry; `AGENTS.md` must be a symbolic link to `CLAUDE.md`.
2. `CLAUDE.md` keeps only stable context, boundaries, hard constraints, and document routing; it records no timelines.
3. `docs/design/*` holds adopted, stable product and architecture facts.
4. `docs/reference/*` holds stable collaboration rules, platform constraints, and verification procedures.
5. `docs/plans/*` holds execution-phase designs, implementation plans, and current to-dos; after completion, write still-valid facts back into `docs/design/*` or `docs/reference/*`.
6. Historical process lives in Git commits; document bodies keep only current facts and the current verification baseline.

## Product boundaries

- The MVP uses Apple Notes as the only persistent source of truth for weekly progress and relies on iCloud to sync across devices signed into the same Apple account; macOS Reminders and Calendar act only as an optional notification layer, never as a second progress store.
- A week is the independent management unit; dates are the primary recording dimension. Weekly goals and the weekly summary are auxiliary structures.
- The skill updates progress only from information the user explicitly provides or that is verifiable after a hard pre-read of local skill source dimensions and the materials actually read this turn; it does not claim to read the full history of every AI IDE automatically.
- Writes must protect content the user edited by hand; only the explicitly managed region may be modified.
- The skill may operate automatically inside Notes folders, Reminders lists, and Calendars that it created and registered itself; it must not automatically modify objects whose ownership is unclear or that the user manages.
- No cloud services, databases, or separate account systems are introduced.
- Additional storage backends may come later, but extension needs must not bloat the Apple Notes MVP.

## Document routing

- docs governance and entry: `docs/CLAUDE.md`
- Repository context: `docs/reference/repository-context.md`
- Collaboration and delivery: `docs/reference/collaboration-and-delivery.md`
- Adopted product design: `docs/design/core/weekly-progress-management.md`
- Source-dimension pre-read: `docs/plans/2026-07-20-local-skill-source-dimensions.md` and `references/source-dimensions.md`
- Initial design and handoff: `docs/plans/2026-07-16-initial-skill-design.md`

## Collaboration rules

- Conversation language follows the user's language.
- Before starting implementation, read this file, `docs/CLAUDE.md`, and the fact sources relevant to the task.
- When adding or updating a skill, follow the `skill-creator` flow: align on design first, then initialize, implement, verify, and forward-test.
- Never record unverified Apple Notes / AppleScript behavior as established fact.
- Without explicit user authorization, do not run `git commit`, `git push`, publish, or modify remote resources.
