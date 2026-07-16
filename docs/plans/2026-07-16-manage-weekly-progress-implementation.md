---
title: manage-weekly-progress implementation plan
scope: manage-weekly-progress
type: implementation
status: completed
---

# manage-weekly-progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` when explicitly authorized, otherwise execute inline task-by-task with TDD. Track every step with checkbox syntax.

**Goal:** Deliver a complete skill distributable via skills.sh that manages Apple Notes weekly progress directly on macOS and syncs Reminders and Calendar for explicit times.

**Architecture:** A Python 3 standard-library CLI implements input validation, the weekly model, HTML managed-region merging, and orchestration; three independent AppleScript adapters access Notes, Reminders, and Calendar. Apple Notes is the only progress source of truth; local JSON stores only managed-container identifiers and user preferences; reminder and calendar objects stay idempotent through managed containers and body markers.

**Tech Stack:** Python 3.9+ standard library, `osascript`, AppleScript, `unittest`, macOS Notes / Reminders / Calendar.

## Global Constraints

- Natural weeks default to ISO Monday through Sunday; the system timezone is the default, with an IANA timezone override in config.
- Apple Notes is the only progress source of truth; Reminders and Calendar carry only key milestones with explicit times.
- Only containers and objects the skill created and registered are modified automatically; stop when ownership is unclear.
- Notes writes must re-read first; replace only the content between `⟦manage-weekly-progress:start:v1⟧` and `⟦manage-weekly-progress:end:v1⟧`.
- A newly created calendar must be verified writable with retries; never fall back to writing another user calendar while it is not ready.
- No third-party Python dependencies, cloud services, databases, or account systems.
- Without explicit user authorization, never commit, push, or publish.

---

### Task 1: Initialize the skill skeleton and test baseline

**Files:**
- Create: `SKILL.md`
- Create: `agents/openai.yaml`
- Create: `scripts/manage_weekly_progress.py`
- Create: `scripts/mwp/__init__.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Produces: the `scripts/manage_weekly_progress.py doctor|capture|review|rollover` CLI entry.

- [x] **Step 1: Generate the standard skeleton in a temporary directory with the skill-creator initializer**

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/init_skill.py" manage-weekly-progress \
  --path /tmp/manage-weekly-progress-init \
  --resources scripts,references \
  --interface display_name="Weekly Progress for Apple Notes" \
  --interface short_description="Manage weekly progress in Apple Notes with optional reminders" \
  --interface default_prompt="Record and review my weekly progress in Apple Notes."
```

- [x] **Step 2: Write a failing CLI help test**

```python
def test_help_lists_public_commands(self):
    result = subprocess.run(
        [sys.executable, str(CLI), "--help"], capture_output=True, text=True
    )
    self.assertEqual(result.returncode, 0)
    self.assertIn("doctor", result.stdout)
    self.assertIn("capture", result.stdout)
    self.assertIn("review", result.stdout)
    self.assertIn("rollover", result.stdout)
```

- [x] **Step 3: Run the test and confirm it fails because the CLI does not exist yet**

```bash
python3 -m unittest tests.test_cli -v
```

Expected: `FAIL` or `ERROR` because the entry file or commands are undefined.

- [x] **Step 4: Add a minimal argparse entry and copy the initializer-generated metadata**

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manage-weekly-progress")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("doctor", "capture", "review", "rollover"):
        subparsers.add_parser(command)
    return parser
```

- [x] **Step 5: Re-run the test and confirm it passes**

```bash
python3 -m unittest tests.test_cli -v
```

Expected: `OK`.

### Task 2: Weekly model, input validation, and the Notes HTML managed region

**Files:**
- Create: `scripts/mwp/model.py`
- Create: `scripts/mwp/note_format.py`
- Create: `tests/test_model.py`
- Create: `tests/test_note_format.py`

**Interfaces:**
- Produces: `WeekRef.from_date(date, tz_name)`, `CapturePayload.from_dict(data)`, `parse_managed_state(body)`, `merge_managed_region(original, state)`.

- [x] **Step 1: Write failing tests for ISO week titles, duplicate merging, and invalid input**

```python
def test_week_ref_uses_monday_and_iso_number(self):
    week = WeekRef.from_date(date(2026, 7, 16), "Asia/Shanghai")
    self.assertEqual(week.iso_key, "2026-W29")
    self.assertEqual(week.title, "2026-W29 | Weekly Progress | 07.13-07.19")

def test_capture_rejects_due_without_timezone(self):
    with self.assertRaises(ValidationError):
        CapturePayload.from_dict({"date": "2026-07-16", "next": [{"text": "Add login tests", "due_at": "2026-07-17T18:00:00"}]})
```

- [x] **Step 2: Run the model tests and confirm the expected failures**

```bash
python3 -m unittest tests.test_model -v
```

Expected: failures because the model is not implemented.

- [x] **Step 3: Implement immutable week references, capture items, and payload validation**

```python
@dataclass(frozen=True)
class ProgressItem:
    section: str
    text: str
    key: str
    due_at: datetime | None = None
    end_at: datetime | None = None

    @classmethod
    def from_value(cls, section: str, value: str | dict[str, Any]) -> "ProgressItem":
        data = {"text": value} if isinstance(value, str) else dict(value)
        text = normalize_text(data["text"])
        key = data.get("key") or stable_key(section, text)
        return cls(section, text, key, parse_aware_datetime(data.get("due_at")), parse_aware_datetime(data.get("end_at")))
```

- [x] **Step 4: Write failing tests for managed-region creation, replacement, outside-region protection, and malformed duplicate markers**

```python
def test_merge_preserves_manual_content_outside_markers(self):
    original = "<div>Manual preface</div>" + START + "<div>old content</div>" + END + "<div>Manual footer</div>"
    merged = merge_managed_region(original, sample_state())
    self.assertIn("Manual preface", merged)
    self.assertIn("Manual footer", merged)
    self.assertNotIn("old content", merged)

def test_merge_rejects_duplicate_marker_pairs(self):
    with self.assertRaises(ManagedRegionError):
        merge_managed_region(START + END + START + END, sample_state())
```

- [x] **Step 5: Implement HTMLParser-based parsing and deterministic rendering**

```python
START_TEXT = "⟦manage-weekly-progress:start:v1⟧"
END_TEXT = "⟦manage-weekly-progress:end:v1⟧"

def merge_managed_region(original: str, state: WeeklyState) -> str:
    bounds = find_single_managed_region(original)
    rendered = render_managed_region(state)
    if bounds is None:
        return original + rendered
    return original[:bounds.start] + rendered + original[bounds.end:]
```

- [x] **Step 6: Run the model and format tests and confirm they all pass**

```bash
python3 -m unittest tests.test_model tests.test_note_format -v
```

Expected: `OK`.

### Task 3: Config and AppleScript adapters

**Files:**
- Create: `scripts/mwp/config.py`
- Create: `scripts/mwp/apple.py`
- Create: `scripts/applescript/notes.applescript`
- Create: `scripts/applescript/reminders.applescript`
- Create: `scripts/applescript/calendar.applescript`
- Create: `tests/test_config.py`
- Create: `tests/test_apple_adapter.py`

**Interfaces:**
- Produces: `ConfigStore.load/save`, `AppleApps.doctor()`, `NotesStore.get_or_create_week()`, `ReminderStore.upsert()`, `CalendarStore.upsert()`.

- [x] **Step 1: Write failing tests for atomic config writes, corrupt-config rejection, and osascript error mapping**

```python
def test_save_replaces_config_atomically(self):
    store = ConfigStore(self.path)
    store.save(AppConfig(notes_folder_id="folder-1"))
    self.assertEqual(store.load().notes_folder_id, "folder-1")
    self.assertFalse(self.path.with_suffix(".tmp").exists())

def test_runner_maps_permission_denied(self):
    runner = AppleScriptRunner(executable=self.fake_osascript)
    with self.assertRaises(ApplePermissionError):
        runner.run("notes.applescript", "doctor")
```

- [x] **Step 2: Run the adapter tests and confirm the expected failures**

```bash
python3 -m unittest tests.test_config tests.test_apple_adapter -v
```

- [x] **Step 3: Implement atomic JSON config holding only container identifiers and preferences**

```python
DEFAULT_CONFIG = Path.home() / "Library/Application Support/manage-weekly-progress/config.json"

def save(self, config: AppConfig) -> None:
    self.path.parent.mkdir(parents=True, exist_ok=True)
    temp = self.path.with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, self.path)
```

- [x] **Step 4: Implement the parameterized AppleScriptRunner and three single-responsibility adapters**

```python
result = subprocess.run(
    [self.executable, str(script), action, *args],
    capture_output=True,
    text=True,
    timeout=self.timeout,
)
if result.returncode:
    raise map_apple_error(result.stderr)
return result.stdout.rstrip("\n")
```

- [x] **Step 5: In AppleScript, verify ownership by stable ID, re-read before write, and error on duplicate candidates**

```applescript
set candidates to every note of targetFolder whose name is noteTitle
if (count of candidates) > 1 then error "MWP_AMBIGUOUS_NOTE:" & noteTitle number 1001
```

- [x] **Step 6: Run the adapter tests and confirm they all pass**

```bash
python3 -m unittest tests.test_config tests.test_apple_adapter -v
```

### Task 4: capture, review, and rollover orchestration

**Files:**
- Create: `scripts/mwp/service.py`
- Modify: `scripts/manage_weekly_progress.py`
- Create: `tests/test_service.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 2 model/format interfaces and Task 3 Apple adapters.
- Produces: `WeeklyProgressService.capture/review/rollover` with stable JSON CLI output.

- [x] **Step 1: Write failing tests for repeated capture, ambiguous notes, review, and rollover**

```python
def test_capture_is_idempotent(self):
    payload = CapturePayload.from_dict({"date": "2026-07-16", "completed": ["Finish login module"]})
    self.service.capture(payload)
    self.service.capture(payload)
    reviewed = self.service.review("2026-W29")
    self.assertEqual([item.text for item in reviewed.completed], ["Finish login module"])

def test_rollover_copies_only_open_items(self):
    result = self.service.rollover("2026-W29", "2026-W30")
    self.assertEqual([item.text for item in result.next_items], ["Improve login UX"])
```

- [x] **Step 2: Run the service tests and confirm they fail because the service is unimplemented**

```bash
python3 -m unittest tests.test_service -v
```

- [x] **Step 3: Implement read-before-write, merge, re-read verification, and stable JSON responses**

```python
def capture(self, payload: CapturePayload) -> CaptureResult:
    week = WeekRef.from_date(payload.day, self.config.timezone)
    current = self.notes.read_unique(week.title)
    state = merge_capture(parse_managed_state(current.body), payload)
    self.notes.write(folder.id, current.id, current.body, merge_managed_region(current.body, state))
    verified = parse_managed_state(self.notes.read_by_id(current.id).body)
    return CaptureResult(week.iso_key, verified, self.sync_notifications(payload))
```

- [x] **Step 4: Restrict CLI input to UTF-8 JSON files or stdin and emit machine-readable JSON**

```bash
python3 scripts/manage_weekly_progress.py capture --input /tmp/capture.json
python3 scripts/manage_weekly_progress.py review --week 2026-W29
python3 scripts/manage_weekly_progress.py rollover --from-week 2026-W29 --to-week 2026-W30
```

- [x] **Step 5: Run the service and CLI tests and confirm they all pass**

```bash
python3 -m unittest tests.test_service tests.test_cli -v
```

### Task 5: Idempotent Reminders and Calendar sync

**Files:**
- Modify: `scripts/mwp/service.py`
- Modify: `scripts/applescript/reminders.applescript`
- Modify: `scripts/applescript/calendar.applescript`
- Create: `tests/test_notifications.py`

**Interfaces:**
- Produces: `route_notification(item)`, `sync_notification(item)`; marker format `manage-weekly-progress:item:<key>`.

- [x] **Step 1: Write failing tests for no-time, deadline actions, time ranges, repeated calls, and completion linkage**

```python
def test_route_requires_explicit_time(self):
    self.assertEqual(route_notification(item(due_at=None, end_at=None)), NotificationRoute.NONE)

def test_route_uses_calendar_for_time_range(self):
    self.assertEqual(route_notification(item(due_at=START, end_at=END)), NotificationRoute.CALENDAR)

def test_repeated_sync_updates_same_managed_object(self):
    first = self.service.sync_notification(item(key="tests", due_at=START))
    second = self.service.sync_notification(item(key="tests", due_at=LATER))
    self.assertEqual(first.external_id, second.external_id)
```

- [x] **Step 2: Run the notification tests and confirm the expected failures**

```bash
python3 -m unittest tests.test_notifications -v
```

- [x] **Step 3: Implement lookup and update by body marker only inside the managed list/calendar**

```applescript
set marker to "manage-weekly-progress:item:" & itemKey
set matches to every reminder of targetList whose body contains marker
if (count of matches) > 1 then error "MWP_AMBIGUOUS_REMINDER:" & itemKey number 1002
```

- [x] **Step 4: Implement bounded retry and safe degradation for newly created calendars**

```python
for delay in (0, 1, 2, 4, 8):
    if delay:
        time.sleep(delay)
    if self.calendar.verify_writable(calendar_id):
        return calendar_id
raise AppleSyncPendingError("Calendar was created but is not writable yet; retry the command later")
```

- [x] **Step 5: Run the notification tests and confirm they all pass**

```bash
python3 -m unittest tests.test_notifications -v
```

### Task 6: Skill instructions, platform reference, and release-grade verification

**Files:**
- Modify: `SKILL.md`
- Modify: `agents/openai.yaml`
- Create: `references/input-schema.md`
- Create: `references/platform-behavior.md`
- Create: `tests/test_live_macos.py`
- Modify: `docs/design/core/weekly-progress-management.md`
- Modify: `docs/plans/2026-07-16-initial-skill-design.md`

**Interfaces:**
- Produces: a triggerable, installable, diagnosable, forward-testable complete skill.

- [x] **Step 1: Write SKILL.md, keeping the core flow concise and routing detailed references**

```markdown
1. Run `doctor` to check macOS and app permissions.
2. Build capture JSON from explicit facts; never infer dates.
3. Invoke the CLI and summarize the write result for the user.
4. Stop writing and report on ambiguity or unmanaged objects.
```

- [x] **Step 2: Document verified platform behavior and the input JSON schema**

```json
{
  "date": "2026-07-16",
  "completed": ["Finish login module"],
  "next": [{"text": "Add login tests", "key": "login-tests", "due_at": "2026-07-17T18:00:00+08:00"}]
}
```

- [x] **Step 3: Run the full unit and integration tests**

```bash
python3 -m unittest discover -s tests -v
```

Expected: all non-live tests pass with zero warnings.

- [x] **Step 4: Run structure validation**

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" .
```

Expected: `Skill is valid!`.

- [x] **Step 5: Run the cleanable macOS live loop**

```bash
MWP_LIVE_TEST=1 python3 -m unittest tests.test_live_apple_adapters tests.test_live_service -v
```

Expected: unique QA containers are created, repeated capture does not duplicate, review reads back, reminders/calendar events update by marker, rollover carries only open items, and all QA objects are cleaned up afterward.

- [x] **Step 6: Self-check docs, status, and sensitive information**

```bash
git diff --check
rg -n "TODO|TBD|FIXME|x-coredata://|x-apple-reminder://" SKILL.md agents scripts references tests docs
git status --short
```

Expected: no placeholders, no personal Apple object IDs, and only changes within this scope.
