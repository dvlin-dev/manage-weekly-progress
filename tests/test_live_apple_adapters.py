from __future__ import annotations

import os
import time
import unittest
import uuid
from datetime import datetime, timedelta

from scripts.mwp.apple import (
    AppleConflictError,
    AppleNotFoundError,
    AppleScriptRunner,
    CalendarStore,
    NotesStore,
    ReminderStore,
    local_naive_iso,
)


@unittest.skipUnless(os.environ.get("MWP_LIVE_TEST") == "1", "set MWP_LIVE_TEST=1 for macOS app integration")
class LiveAppleAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.suffix = uuid.uuid4().hex[:8]
        runner = AppleScriptRunner(timeout=45)
        self.notes = NotesStore(runner)
        self.reminders = ReminderStore(runner)
        self.calendar = CalendarStore(runner)
        self.folder_id = None
        self.note_id = None
        self.list_id = None
        self.calendar_id = None

    def tearDown(self) -> None:
        if self.note_id and self.folder_id:
            try:
                self.notes.delete(self.folder_id, self.note_id)
            except Exception:
                pass
        if self.folder_id:
            try:
                self.notes.delete_folder(self.folder_id)
            except Exception:
                pass
        if self.list_id:
            try:
                self.reminders.delete_list(self.list_id)
            except Exception:
                pass
        if self.calendar_id:
            try:
                self.calendar.delete_calendar(self.calendar_id)
            except Exception:
                pass

    def test_notes_round_trip_preserves_outside_content_and_unique_lookup(self) -> None:
        folder = self.notes.ensure_folder("iCloud", None, f"Weekly Progress QA {self.suffix}")
        self.folder_id = folder.id
        created = self.notes.create(folder.id, f"2026-W29 QA {self.suffix}", "<div>Manual preface</div><div>managed</div>")
        self.note_id = created.id

        found = self.notes.read_unique(folder.id, f"2026-W29 QA {self.suffix}")
        self.assertEqual(found.id, created.id)
        self.assertIn("Manual preface", found.body)

        updated_body = found.body.replace("managed", "updated")
        updated = self.notes.write(folder.id, created.id, found.body, updated_body)
        self.assertIn("Manual preface", updated.body)
        self.assertIn("updated", updated.body)

        with self.assertRaises(AppleConflictError):
            self.notes.write(folder.id, created.id, found.body, updated.body)

        # A stale body differing only in letter case must also be a conflict.
        with self.assertRaises(AppleConflictError):
            self.notes.write(folder.id, created.id, updated.body.swapcase(), updated.body)

    def test_reminder_upsert_is_idempotent(self) -> None:
        managed_list = self.reminders.ensure_list(None, f"Weekly Progress QA {self.suffix}")
        self.list_id = managed_list.id
        due = (datetime.now().astimezone() + timedelta(hours=1)).replace(second=0, microsecond=0)

        first_id = self.reminders.upsert(managed_list.id, "qa-item", "Add login tests", "QA", due)
        second_id = self.reminders.upsert(managed_list.id, "qa-item", "Add login tests (updated)", "QA", due + timedelta(hours=1))

        self.assertEqual(first_id, second_id)

        # The stored due date must round-trip exactly (guards against
        # AppleScript date-component pitfalls such as month overflow). A fresh
        # osascript invocation can briefly see stale data, so poll bounded.
        expected_due = local_naive_iso(due + timedelta(hours=1))
        detail = None
        for delay in (0, 1, 2, 4, 8):
            if delay:
                time.sleep(delay)
            detail = self.reminders.read(managed_list.id, "qa-item")
            if detail and detail.due_local == expected_due:
                break
        self.assertEqual(detail.due_local, expected_due)
        self.assertFalse(detail.completed)

        self.assertEqual(self.reminders.complete(managed_list.id, "qa-item"), first_id)
        self.assertTrue(self.reminders.read(managed_list.id, "qa-item").completed)

    def test_calendar_upsert_is_idempotent_after_new_calendar_syncs(self) -> None:
        managed_calendar = self.calendar.ensure_calendar(None, f"Weekly Progress QA {self.suffix}")
        self.calendar_id = managed_calendar.id
        for delay in (0, 1, 2, 4, 8, 16):
            if delay:
                time.sleep(delay)
            try:
                if self.calendar.verify_writable(managed_calendar.id):
                    break
            except AppleNotFoundError:
                # The fresh ownership token may not be visible to a new
                # osascript invocation yet; keep waiting.
                continue
        else:
            self.fail("new managed calendar did not become writable")

        start = (datetime.now().astimezone() + timedelta(hours=2)).replace(second=0, microsecond=0)
        end = start + timedelta(minutes=30)
        first_id = self.calendar.upsert(managed_calendar.id, "qa-event", "Weekly review", "QA", start, end)
        second_id = self.calendar.upsert(managed_calendar.id, "qa-event", "Weekly review (updated)", "QA", start, end + timedelta(minutes=15))

        self.assertEqual(first_id, second_id)

        # The stored event window must round-trip exactly. A fresh osascript
        # invocation can briefly see stale event data, so poll bounded.
        expected_end = local_naive_iso(end + timedelta(minutes=15))
        detail = None
        for delay in (0, 1, 2, 4, 8):
            if delay:
                time.sleep(delay)
            detail = self.calendar.read_event(managed_calendar.id, "qa-event")
            if detail and detail.end_local == expected_end:
                break
        self.assertEqual(detail.start_local, local_naive_iso(start))
        self.assertEqual(detail.end_local, expected_end)

        self.assertEqual(self.calendar.delete_event(managed_calendar.id, "qa-event"), first_id)
        self.calendar.delete_calendar(managed_calendar.id)
        self.calendar_id = None
        with self.assertRaises(AppleNotFoundError):
            self.calendar.verify_writable(managed_calendar.id)


if __name__ == "__main__":
    unittest.main()
