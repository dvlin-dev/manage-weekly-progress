---
name: manage-weekly-progress
description: Manage personal weekly progress on macOS using Apple Notes as the source of truth, with optional managed Reminders and Calendar notifications for explicit times. Use when a user asks to record or update progress, goals, next steps, blockers, or follow-ups; review today or the current week; see unfinished work; roll open items into another ISO week; or create/update reminders and calendar events tied to weekly progress.
---

# Manage Weekly Progress

Keep one Apple Note per ISO week. Write only verified facts, protect content outside the managed region, and create notifications only from explicit time information.

## Locate the CLI

Resolve the directory containing this `SKILL.md` as `SKILL_DIR`, then run:

```bash
python3 "$SKILL_DIR/scripts/manage_weekly_progress.py" --help
```

Require macOS, `python3` 3.9 or newer, and `/usr/bin/osascript`.

## Check access

Run `doctor` before the first live write and when an Apple app operation fails:

```bash
python3 "$SKILL_DIR/scripts/manage_weekly_progress.py" doctor
```

Treat Notes access as required. Treat Reminders and Calendar as optional: report their failure without claiming that progress capture failed.

When the config is readable, `doctor` also returns a `context` object with `today`, `current_week`, and `current_week_title` in the effective timezone. Use these values when the user says "today" or "this week" instead of inferring dates yourself.

## Capture or update progress

1. Extract only facts explicitly supplied by the user or verifiable in the current agent context.
2. Classify facts as `goals`, `completed`, `next`, `blocked`, `follow_up`, or `summary`.
3. Include `due_at` only when the source provides a clear time. Require an ISO 8601 timezone offset.
4. Use a reminder for a deadline or action at one time. Use Calendar only when both a start and end are explicit.
5. Reuse an explicit stable `key` when updating or completing an item that owns a notification.
6. Write the JSON to a temporary file and call `capture`.

```bash
python3 "$SKILL_DIR/scripts/manage_weekly_progress.py" capture --input /tmp/weekly-progress-capture.json
```

Preview extraction without changing Apple apps:

```bash
python3 "$SKILL_DIR/scripts/manage_weekly_progress.py" capture --input /tmp/weekly-progress-capture.json --dry-run
```

When marking a notified item complete, add it to `completed` with the same `key` and remove the old open item in the same capture. This completes the managed reminder and removes the managed calendar event when present.

Read [references/input-schema.md](references/input-schema.md) before constructing nontrivial input, updates, removals, or notification times.

## Review a week

Use ISO `YYYY-Www` weeks. Review is read-only and does not initialize a missing folder:

```bash
python3 "$SKILL_DIR/scripts/manage_weekly_progress.py" review --week 2026-W29
```

Summarize the returned structured state. Do not infer work from unrelated notes or other IDE histories.

## Roll open items forward

Review the source week first. Confirm from the available facts that the open goals, next steps, blockers, and follow-ups are still relevant, then run:

```bash
python3 "$SKILL_DIR/scripts/manage_weekly_progress.py" rollover --from-week 2026-W29 --to-week 2026-W30
```

Never roll completed items. Keep the source week unchanged except for a managed summary recording the rollover.

## Configure preferences

Keep ISO weeks Monday through Sunday. Use the Mac system timezone by default. Change local preferences only when the user asks:

```bash
python3 "$SKILL_DIR/scripts/manage_weekly_progress.py" configure \
  --timezone Asia/Shanghai \
  --notes-folder-name "Weekly Progress" \
  --reminders-list-name "Weekly Progress" \
  --calendar-name "Weekly Progress"
```

Changing a managed container name clears its recorded ownership identifier and creates a new managed container on the next relevant write; it does not delete the old container.

## Enforce safety

- Modify only containers recorded in the local ownership config.
- Never adopt an existing container by name alone. Create a collision-safe managed name instead.
- Re-read Notes before writing and verify the stored body after writing.
- Modify only content between the visible managed markers. Preserve all content outside them byte-for-byte when composing the update.
- Stop on duplicate weekly-note titles, duplicate notification markers, missing owned objects, malformed markers, or corrupt config.
- Do not bypass macOS permission prompts.
- Do not interpret notification failure as Notes write failure; surface notification errors separately.
- Read [references/platform-behavior.md](references/platform-behavior.md) when diagnosing permissions, Notes HTML, ownership, Calendar sync, or cleanup behavior.
