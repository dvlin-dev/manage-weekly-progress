---
title: Weekly progress management core design
scope: manage-weekly-progress
type: design
status: active
---

# Weekly progress management core design

## 1. Product goal

Let users maintain one shared weekly progress record across different AI IDEs / coding agents. An agent should extract explicit facts from the current context, record them into Apple Notes, and support viewing, reviewing, and cross-week rollover; for key milestones with explicit times it may optionally create reminders or calendar events.

The product is not limited to work management; it also fits personal development, learning, meeting follow-up, and any other effort that needs sustained progress.

## 2. Management cycle

- The ISO natural week (Monday through Sunday) is the independent management unit.
- The Mac system timezone is the default; an IANA timezone can be set in local config.
- Dates are the primary recording dimension.
- Daily records primarily express "done", "next", and "blocked".
- Weekly goals and the weekly summary are auxiliary structures for setting direction and closing the week.
- Each week uses one dedicated Apple Note whose title contains a stably locatable ISO week identifier and date range.

Recommended title form:

```text
2026-W29 | Weekly Progress | 07.13-07.19
```

## 3. Note structure

```markdown
# Goals
- [ ] A goal or item

# Daily Progress
## Date 2026-07-13
### Done
- Progress
### Next
- Follow-up action
### Blocked
- Blocking issue

# Follow-ups
- [ ] Later item

# Weekly Summary
- Main output
- Open issues
- Direction for next week
```

Dated records are the core; empty sections should not create noise just to complete the template.

## 4. Core capabilities

The MVP includes four capabilities:

1. `capture`: after the local skill source-dimension pre-read, extract confirmable progress from user input, the current conversation, workspace artifacts, and any other dimensions that are both available locally and actually read this turn.
2. `update`: create or update this week's note, maintaining done items, next steps, blockers, and follow-ups, and sync skill-managed reminders or calendar events by rule.
3. `review`: after the same pre-read when summarizing beyond Notes alone, summarize the day's or week's progress, unfinished items, and risks.
4. `rollover`: after the same pre-read, carry still-valid open items into the next week while preserving the source week's history.

The skill must cover requests such as:

- "Record what we just finished into this week's progress."
- "Record: login module done, next is adding tests."
- "Update this week's plan from these meeting notes."
- "What is still unfinished this week?"
- "Summarize what I did today."
- "Roll unfinished items into next week."

## 5. Data flow and platform boundaries

```text
Hard pre-read of local skill capabilities
  → Map onto fixed general source dimensions
  → User / materials actually read this turn
  → Skill extracts structured progress
  → macOS scripts re-read the target Apple Note
  → Update the skill-managed region
  → Apple Notes saves
  → iCloud syncs to devices on the same Apple account
  ↘ Key milestones with explicit times → skill-managed Reminders / Calendar
```

- Write capability runs on macOS; iOS is not required to execute the skill.
- iCloud is the sync layer and carries no business logic.
- Before capture, review, or rollover evidence work, the agent must scan locally installed skills and map them to a fixed baseline of general source dimensions (user turn, conversation, workspace artifacts, this week’s Notes, local skill descriptions, meetings, email, tasks/cards, code review/repo activity, knowledge bases, IM/group chat, local knowledge caches). Dimensions beyond the always-on set are considered only when a matching local skill or readable cache exists.
- That pre-read is orientation only: “skill present” is not “fact obtained.” Writes still require user-explicit or currently verifiable facts from materials actually read this turn.
- The skill does not automatically access other IDEs' full history; it does not hard-code one machine’s skill list or maintain a vendor-specific skill registry.
- Progress storage backends beyond Apple Notes are out of MVP scope; Reminders and Calendar are notification outlets only.
- Details live in the skill package `references/source-dimensions.md` and `docs/plans/2026-07-20-local-skill-source-dimensions.md`.

## 6. Write safety

- Re-read the target note before writing to avoid overwriting based on a stale copy.
- Submit the originally read body with each write; if the body in Apple Notes has changed, refuse the write and report a conflict.
- Modify only the explicitly marked managed region, preserving the user's manual edits elsewhere.
- Generate stable identifiers or use an equivalent deduplication mechanism so repeated execution stays as idempotent as possible.
- Create a new note when the target week is missing; stop automatic modification and report ambiguity when multiple candidate notes exist.
- On missing permissions, unavailable target account or folder, or write failure, keep the original content and return an actionable error.
- Concurrent multi-device writes can still conflict; the MVP reduces the risk with read-before-write, optimistic concurrency checks, and minimal-scope modification, without promising cross-device strong consistency.

## 7. Managed space and automatic operations

- On the first write the skill automatically creates and registers a dedicated Apple Notes folder; on the first notification it creates a dedicated Reminders list or Calendar on demand.
- Managed containers default to the name `Weekly Progress`. Ownership must be determined by a locally recorded stable identifier or a verified equivalent mechanism, never by name alone.
- Local config stores only preferences, the Notes folder ID, the Reminders list ID, and the calendar ownership token — never weekly progress; the config is an atomic JSON file readable and writable only by the current user.
- The skill may automatically create, update, complete, or cancel managed objects inside containers it created and registered, minimizing user interruptions.
- Objects created manually by the user, of unclear ownership, or living in unmanaged containers are not modified automatically by default.
- If a same-named container exists whose ownership cannot be confirmed, do not adopt its content; create a collision-safe managed name instead.
- First-use macOS authorization prompts belong to the system permission flow and cannot be bypassed; when authorization is denied, explain the missing permission and the affected capability.

## 8. Reminders and Calendar routing

- Only items with an explicit time, deadline, or fixed schedule automatically get a reminder or calendar event.
- "Next" and "follow-up" items without explicit times stay in Apple Notes only; dates are never inferred for coverage.
- Actions with a deadline that need completion at a specific time go to Reminders first; meetings, reviews, or arrangements with an explicit start time that occupy a time slot go to Calendar first.
- Reminders and Calendar objects must link back to their week, date, and source item, and stay idempotent via stable identifiers or an equivalent deduplication mechanism.
- Timed items also write their stable key into visible Notes metadata so the same notification object remains addressable across rollover, updates, and completion.
- When a source item explicitly changes, the corresponding skill-managed object may be updated automatically; similar objects managed by the user must never be modified in tandem.

## 9. Naming and presentation

- Skill, directory, and repository name: `manage-weekly-progress`.
- Keep the name generic; neither the work scenario nor the Apple Notes backend is baked into the skill name.
- The UI display name may be `Weekly Progress for Apple Notes`, making the MVP storage explicit to users.
- The skill description must state both the capabilities and the trigger scenarios, and make the Apple Notes / macOS prerequisite explicit.

## 10. Non-goals

- Automatically monitoring and collecting all AI IDE conversations.
- Building an independent cloud sync service or database.
- Multi-user collaborative editing and conflict merging.
- Building first-party adapters into project management, mail, or knowledge platforms as progress stores.
- Supporting Notion, Markdown, Google Docs, or other backends in the first version.
- Growing Reminders or Calendar into a second weekly progress, task management, or scheduling system.
- Shipping a CLI that inventories skills or maintaining a per-environment dimension→skill whitelist.
