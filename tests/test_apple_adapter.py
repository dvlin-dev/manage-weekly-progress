from __future__ import annotations

import stat
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.mwp.apple import (
    RECORD_SEPARATOR,
    AppleConflictError,
    ApplePermissionError,
    AppleScriptError,
    AppleScriptRunner,
    CalendarStore,
    NotesStore,
    ReminderStore,
    local_naive_iso,
)


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, str], str]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []

    def run(self, script: str, action: str, *args: str) -> str:
        self.calls.append((script, action, args))
        return self.responses[(script, action)]


class AppleScriptRunnerTests(unittest.TestCase):
    def test_runner_removes_only_osascript_output_delimiter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "fake-osascript"
            executable.write_text("#!/bin/sh\nprintf 'value\\n\\n'\n", encoding="utf-8")
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

            result = AppleScriptRunner(executable=str(executable)).run(
                "notes.applescript", "read-note"
            )

            self.assertEqual(result, "value\n")

    def test_runner_maps_permission_denied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "fake-osascript"
            executable.write_text(
                "#!/bin/sh\necho 'Not authorized to send Apple events. (-1743)' >&2\nexit 1\n",
                encoding="utf-8",
            )
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(ApplePermissionError):
                AppleScriptRunner(executable=str(executable)).run("notes.applescript", "doctor")

    def test_runner_maps_generic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "fake-osascript"
            executable.write_text("#!/bin/sh\necho 'boom' >&2\nexit 1\n", encoding="utf-8")
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

            with self.assertRaisesRegex(AppleScriptError, "boom"):
                AppleScriptRunner(executable=str(executable)).run("notes.applescript", "doctor")

    def test_runner_maps_optimistic_write_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "fake-osascript"
            executable.write_text(
                "#!/bin/sh\necho 'MWP_CONFLICT:Note changed since read' >&2\nexit 1\n",
                encoding="utf-8",
            )
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(AppleConflictError):
                AppleScriptRunner(executable=str(executable)).run("notes.applescript", "write-note")


class StoreParsingTests(unittest.TestCase):
    def test_date_handlers_reset_day_before_assigning_month(self) -> None:
        base = Path(__file__).resolve().parents[1] / "scripts" / "applescript"
        for script in ("reminders.applescript", "calendar.applescript"):
            source = (base / script).read_text(encoding="utf-8")
            reset = source.find("set day of resultDate to 1")
            month = source.find("set month of resultDate to")
            self.assertGreater(reset, -1, script)
            self.assertLess(reset, month, f"{script} must reset day before assigning month")
            self.assertIn("MWP_INVALID_DATE", source, f"{script} must self-validate built dates")

    def test_notes_conflict_comparison_is_case_sensitive(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "scripts" / "applescript" / "notes.applescript").read_text(
            encoding="utf-8"
        )

        self.assertIn("considering case", source)
        self.assertIn("set bodyUnchanged to (currentBody is expectedBody)", source)

    def test_calendar_write_probe_is_marked_and_cleans_stale_probes(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "scripts" / "applescript" / "calendar.applescript").read_text(
            encoding="utf-8"
        )

        self.assertIn('set probeMarker to "manage-weekly-progress:probe"', source)
        self.assertIn("my matchingEventUids(targetCalendar, probeMarker)", source)
        self.assertIn("description:probeMarker", source)

    def test_calendar_delete_requires_a_unique_verified_display_name(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "scripts" / "applescript" / "calendar.applescript").read_text(
            encoding="utf-8"
        )

        self.assertIn("set namedMatches to every calendar whose name is targetName", source)
        self.assertIn('MWP_AMBIGUOUS:Calendar display name:', source)
        self.assertIn('if (description of namedTarget) is not ownershipMarker', source)

    def test_notes_store_parses_unique_note(self) -> None:
        runner = FakeRunner(
            {("notes.applescript", "read-note"): RECORD_SEPARATOR.join(("FOUND", "note-1", "<div>body</div>"))}
        )

        note = NotesStore(runner).read_unique("folder-1", "2026-W29 | Weekly Progress | 07.13-07.19")

        self.assertEqual(note.id, "note-1")
        self.assertEqual(note.body, "<div>body</div>")

    def test_notes_store_returns_none_for_missing_note(self) -> None:
        runner = FakeRunner({("notes.applescript", "read-note"): "MISSING"})
        self.assertIsNone(NotesStore(runner).read_unique("folder-1", "title"))

    def test_notes_write_passes_expected_and_new_body_files(self) -> None:
        class ReadingRunner:
            def __init__(self) -> None:
                self.expected = ""
                self.updated = ""

            def run(self, script: str, action: str, *args: str) -> str:
                self.expected = Path(args[2]).read_text(encoding="utf-8")
                self.updated = Path(args[3]).read_text(encoding="utf-8")
                return RECORD_SEPARATOR.join(("note-1", self.updated))

        runner = ReadingRunner()

        note = NotesStore(runner).write(
            "folder-1", "note-1", "<div>expected</div>", "<div>updated</div>"
        )

        self.assertEqual(runner.expected, "<div>expected</div>")
        self.assertEqual(runner.updated, "<div>updated</div>")
        self.assertEqual(note.body, "<div>updated</div>")

    def test_reminder_read_parses_detail(self) -> None:
        runner = FakeRunner(
            {
                ("reminders.applescript", "read"): RECORD_SEPARATOR.join(
                    ("FOUND", "reminder-1", "2026-07-17T18:00:00", "false")
                )
            }
        )

        detail = ReminderStore(runner).read("list-1", "item-key")

        self.assertEqual(detail.id, "reminder-1")
        self.assertEqual(detail.due_local, "2026-07-17T18:00:00")
        self.assertFalse(detail.completed)

    def test_reminder_read_returns_none_for_missing_marker(self) -> None:
        runner = FakeRunner({("reminders.applescript", "read"): "MISSING"})
        self.assertIsNone(ReminderStore(runner).read("list-1", "item-key"))

    def test_calendar_read_event_parses_detail(self) -> None:
        runner = FakeRunner(
            {
                ("calendar.applescript", "read-event"): RECORD_SEPARATOR.join(
                    ("FOUND", "event-1", "2026-07-17T16:00:00", "2026-07-17T16:30:00")
                )
            }
        )

        detail = CalendarStore(runner).read_event("calendar-1", "item-key")

        self.assertEqual(detail.id, "event-1")
        self.assertEqual(detail.start_local, "2026-07-17T16:00:00")
        self.assertEqual(detail.end_local, "2026-07-17T16:30:00")

    def test_local_naive_iso_matches_applescript_report_format(self) -> None:
        value = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)
        expected = value.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")

        self.assertEqual(local_naive_iso(value), expected)

    def test_reminder_store_passes_local_date_components(self) -> None:
        runner = FakeRunner({("reminders.applescript", "upsert"): "reminder-1"})
        due = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)

        external_id = ReminderStore(runner).upsert(
            "list-1", "item-key", "Add login tests", "source", due
        )

        self.assertEqual(external_id, "reminder-1")
        self.assertIn("2026", runner.calls[0][2])

    def test_calendar_store_rejects_inverted_time_range(self) -> None:
        runner = FakeRunner({})
        start = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)

        with self.assertRaises(ValueError):
            CalendarStore(runner).upsert(
                "calendar-1", "item-key", "Weekly review", "source", start, start
            )


if __name__ == "__main__":
    unittest.main()
