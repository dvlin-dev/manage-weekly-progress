---
title: Repository context
scope: manage-weekly-progress
status: active
---

# Repository context

## Project positioning

`manage-weekly-progress` gives different AI IDEs / coding agents one shared weekly progress workflow. Users can ask an agent in Codex, Claude Code, Cursor, or similar environments to record current progress, check this week's status, generate a review, or roll unfinished items forward.

Apple Notes is the only persistent store for progress in the MVP. The skill drives the macOS Notes app on a Mac signed into the target Apple account, iCloud handles cross-device sync, and iPhone is mainly for viewing and manual edits. For key milestones with explicit times, deadlines, or fixed schedules, the skill can use macOS Reminders or Calendar for notifications, but they never hold the full weekly progress.

## Confirmed usage environment

- The AI IDEs mainly run on one Mac.
- With multiple Macs, each device signs into the same Apple account with iCloud Notes sync enabled.
- iPhone is not required to run the skill directly.
- No extra server, database, or user-account system.
- A lightweight local config may record stable identifiers of skill-managed containers, but it must not grow into an independent data store.
- Runtime requirements: macOS, Python 3.9+, and the system `osascript`; the real end-to-end loop for Notes, Reminders, and Calendar was verified on macOS 26.2.
- Natural weeks are fixed to Monday through Sunday; the system timezone is the default and an IANA timezone can be configured.
- Local config lives at `~/Library/Application Support/manage-weekly-progress/config.json` and stores only preferences and managed-container ownership information.

## Target users

- Individuals or team members developing software with AI IDEs.
- People using AI agents to organize meeting notes, documents, study, or personal projects.
- Anyone who wants to maintain goals, progress, next steps, and blockers on a natural weekly cadence.

## Distribution status

- The repository name, skill directory name, and frontmatter `name` are all `manage-weekly-progress`.
- Skill code, metadata, platform references, automated tests, and live tests are release-ready.
- Publishing to skills.sh is an external state change and requires separate, explicit user authorization.

## Read next

- Core product design: `../design/core/weekly-progress-management.md`
- Current design status: `../plans/2026-07-16-initial-skill-design.md`
- Collaboration and delivery: `collaboration-and-delivery.md`
