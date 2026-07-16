# Verified macOS platform behavior

## Contents

- [Verification baseline](#verification-baseline)
- [Apple Notes](#apple-notes)
- [Reminders](#reminders)
- [Calendar](#calendar)
- [Permissions and errors](#permissions-and-errors)

## Verification baseline

The live integration baseline was verified on macOS 26.2 with the system Notes, Reminders, and Calendar applications. Older macOS releases are not claimed as verified until forward tests are run there.

The test suite creates uniquely named `Weekly Progress QA …` containers, verifies create/read/update/delete behavior, and removes them afterward.

## Apple Notes

- Notes accepts HTML through AppleScript `body` and returns sanitized HTML.
- Notes preserves visible marker text, surrounding manual content, lists, bold text, and the exact note title used by the workflow.
- Notes removes HTML comments, custom `data-*` attributes, element IDs, and custom link targets in the verified environment. Do not use them for identity or managed-region boundaries.
- Use visible boundary text:
  - `⟦manage-weekly-progress:start:v1⟧`
  - `⟦manage-weekly-progress:end:v1⟧`
- Treat zero or one marker pair as valid. Reject partial, reversed, or duplicate pairs.
- Timing metadata is visible and includes the stable item key, for example `⟨reminder: 2026-07-17T18:00:00+08:00; key: login-tests⟩`; reject malformed managed timing instead of rewriting it.
- Writes use optimistic concurrency: the AppleScript compares the current sanitized body with the body Python read and returns `MWP_CONFLICT` if they differ. The comparison runs inside `considering case` because AppleScript text comparison ignores letter case by default and would otherwise miss case-only manual edits.
- Apple Notes prepends the note title to a newly created body. Preserve it by replacing only the managed region on later writes.
- Require an exact unique weekly title inside the owned folder; multiple exact matches are ambiguous.

## Reminders

- Reminder lists and reminders expose stable IDs through AppleScript in the verified environment.
- Store a marker in each managed reminder body: `manage-weekly-progress:item:<key>`.
- Search only inside the owned list. Update exactly one marker match, ignore zero matches when completing, and reject multiple matches.
- Due dates are passed as local date components after Python converts the offset-aware input to the Mac system timezone.
- When building an AppleScript date from components, reset `day` to 1 before assigning `year`/`month`, then set the target day. Otherwise a current day-of-month larger than the target month's length silently overflows into the next month. This applies to Reminders and Calendar alike.
- After construction, both scripts re-check that the built date still carries the requested year, month, and day, and abort with `MWP_INVALID_DATE` on mismatch instead of storing a shifted date.
- `read` (Reminders) and `read-event` (Calendar) return the stored due/start/end values in local `YYYY-MM-DDTHH:MM:SS` form; the live suite asserts these round-trip against the requested times.

## Calendar

- Calendar `calendarIdentifier` and `id` property reads fail with AppleEvent error `-10000` on the verified macOS 26.2 environment. Do not depend on them.
- Store a random ownership token in the dedicated calendar description: `manage-weekly-progress:calendar:<token>`.
- Resolve calendar ownership by this token, not by name. Use collision-safe names only for display.
- A newly created calendar may appear before it accepts events. Verify writability by creating and deleting a marked probe event inside the owned calendar, cleaning stale probes and retrying with bounded backoff.
- The ownership token written to a new calendar's description may not be visible to the next `osascript` invocation immediately. Re-reading the description inside the same AppleScript process returns a stale cached value even after the write has persisted, so in-script confirmation is unreliable; only a fresh invocation observes the token. The service therefore retries a `MWP_NOT_OWNED` result with bounded backoff only for a token minted in the same operation; a previously recorded token that stops resolving is a hard stop.
- Store `manage-weekly-progress:item:<key>` in each managed event description. Resolve event identity from its stable `uid` only after finding the marker inside the owned calendar.
- Calendar deletion can lag after event changes. Retry bounded cleanup; never fall back to deleting a calendar by display name in production.

## Permissions and errors

- macOS can show first-use Automation or privacy prompts for each app. The skill cannot bypass them.
- Map AppleEvent permission error `-1743` to a user-actionable permission error.
- Keep Notes writes successful even when optional reminder or calendar synchronization fails. Return notification errors separately.
- Stop rather than write when ownership config is corrupt, a recorded owned object is missing, or multiple marker matches exist.
