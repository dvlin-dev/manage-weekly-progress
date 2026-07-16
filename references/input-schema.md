# Capture input schema

## Contents

- [Top-level object](#top-level-object)
- [Progress item](#progress-item)
- [Removing and completing items](#removing-and-completing-items)
- [Examples](#examples)

## Top-level object

Pass one UTF-8 JSON object to `capture --input`.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `date` | `YYYY-MM-DD` | yes | Local date whose daily section receives the update. |
| `goals` | item array | no | Weekly goals. |
| `completed` | item array | no | Facts completed on `date`. |
| `next` | item array | no | Open next actions for `date`. |
| `blocked` | item array | no | Current blockers for `date`. |
| `follow_up` | item array | no | Week-level follow-ups. |
| `summary` | string array | no | Week-level summary facts. |
| `remove` | removal array | no | Exact items to remove from one managed section. |

Unknown fields, empty text, naive datetimes, arrays with invalid members, and payloads over 1 MB are rejected. Identical duplicates of the same normalized text are de-duplicated; duplicates that disagree on `key`, `due_at`, `end_at`, or `kind` are rejected as ambiguous.

## Progress item

Use a string for an undated item:

```json
"Finish login module"
```

Use an object when time or identity is needed:

```json
{
  "text": "Add login tests",
  "key": "login-tests",
  "due_at": "2026-07-17T18:00:00+08:00",
  "kind": "reminder"
}
```

| Field | Required | Rules |
| --- | --- | --- |
| `text` | yes | Non-empty; whitespace is normalized; maximum 2,000 characters. Text containing a managed region marker (`⟦manage-weekly-progress:…⟧`) or ending with managed timing metadata (`⟨reminder/calendar/time: ...; key: ...⟩`) is rejected to protect the note structure. |
| `key` | no | Stable identity using 1–128 letters, digits, `.`, `:`, `_`, or `-`. A deterministic key is derived from section and text when omitted. |
| `due_at` | no | ISO 8601 datetime with timezone offset. Never infer it from vague language such as “later” or “this week.” |
| `end_at` | no | ISO 8601 datetime later than `due_at`; requires `due_at`. |
| `kind` | no | `auto`, `reminder`, `calendar`, or `none`. `calendar` requires `end_at`. |

Routing rules:

- No `due_at`, or `kind: none`: Notes only.
- `due_at` without `end_at`: managed Reminder.
- `due_at` plus `end_at`: managed Calendar event.
- Notifications are created only for `goals`, `next`, and `follow_up`.

Update rules when the same normalized text already exists in the section:

- An item that supplies `due_at` or a non-`auto` `kind` replaces the stored timing and kind.
- An item without `due_at` and with default `kind` keeps the stored key, times, and kind, so re-capturing a known fact never orphans its notification.
- To clear a stored time, remove the item and re-add it without time in the same capture.

The Note displays exact notification times and the stable key in a visible suffix so Apple Notes remains the progress source of truth and notification identity survives rollover.

## Removing and completing items

Remove only an exact normalized text from one section:

```json
{
  "section": "next",
  "text": "Add login tests"
}
```

For daily sections (`completed`, `next`, `blocked`), removal applies to the supplied top-level `date`. For week-level sections (`goals`, `follow_up`), it applies to the week.

To finish an item with a managed notification, use the same stable key in `completed` and remove the open entry:

```json
{
  "date": "2026-07-17",
  "completed": [{"text": "Add login tests", "key": "login-tests"}],
  "remove": [{"section": "next", "text": "Add login tests"}]
}
```

This completes a matching managed Reminder and deletes a matching managed Calendar event. Missing matches are ignored; ambiguous matches stop the affected operation.

## Examples

Record progress and one explicit deadline:

```json
{
  "date": "2026-07-16",
  "completed": ["Finish login module"],
  "next": [
    {
      "text": "Add login tests",
      "key": "login-tests",
      "due_at": "2026-07-17T18:00:00+08:00"
    },
    "Improve login UX"
  ],
  "blocked": []
}
```

Record an explicit review time range:

```json
{
  "date": "2026-07-16",
  "follow_up": [
    {
      "text": "Weekly review",
      "key": "weekly-review-2026-w29",
      "kind": "calendar",
      "due_at": "2026-07-17T16:00:00+08:00",
      "end_at": "2026-07-17T16:30:00+08:00"
    }
  ]
}
```
