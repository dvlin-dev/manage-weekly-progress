from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from scripts.mwp.apple import AppleScriptRunner, CalendarStore, NotesStore, ReminderStore
from scripts.mwp.config import AppConfig, ConfigStore
from scripts.mwp.model import CapturePayload, WeekRef
from scripts.mwp.service import NotificationStatus, WeeklyProgressService


@unittest.skipUnless(os.environ.get("MWP_LIVE_TEST") == "1", "set MWP_LIVE_TEST=1 for macOS app integration")
class LiveServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.suffix = uuid.uuid4().hex[:8]
        self.config_store = ConfigStore(Path(self.temp.name) / "config.json")
        self.config_store.save(
            AppConfig(
                notes_folder_name=f"Weekly Progress QA {self.suffix}",
                reminders_list_name=f"Weekly Progress QA {self.suffix}",
                calendar_name=f"Weekly Progress QA {self.suffix}",
            )
        )
        runner = AppleScriptRunner(timeout=45)
        self.notes = NotesStore(runner)
        self.reminders = ReminderStore(runner)
        self.calendar = CalendarStore(runner)
        self.service = WeeklyProgressService(
            self.config_store, self.notes, self.reminders, self.calendar
        )
        self.weeks: set[str] = set()

    def tearDown(self) -> None:
        try:
            config = self.config_store.load()
        except Exception:
            config = None
        if config and config.notes_folder_id:
            for week_key in self.weeks:
                try:
                    title = WeekRef.from_iso_key(week_key).title
                    note = self.notes.read_unique(config.notes_folder_id, title)
                    if note:
                        self.notes.delete(config.notes_folder_id, note.id)
                except Exception:
                    pass
            try:
                self.notes.delete_folder(config.notes_folder_id)
            except Exception:
                pass
        if config and config.reminders_list_id:
            try:
                self.reminders.delete_list(config.reminders_list_id)
            except Exception:
                pass
        if config and config.calendar_id:
            try:
                self.calendar.delete_calendar(config.calendar_id)
            except Exception:
                pass
        self.temp.cleanup()

    def test_capture_review_notifications_completion_and_rollover(self) -> None:
        start = datetime.now().astimezone() + timedelta(hours=2)
        end = start + timedelta(minutes=30)
        payload = CapturePayload.from_dict(
            {
                "date": "2026-07-16",
                "completed": ["Finish café login module"],
                "next": [
                    {
                        "text": "Add login tests",
                        "key": "qa-reminder",
                        "due_at": (start - timedelta(hours=1)).isoformat(),
                    },
                    {
                        "text": "Weekly review",
                        "key": "qa-calendar",
                        "kind": "calendar",
                        "due_at": start.isoformat(),
                        "end_at": end.isoformat(),
                    },
                    "Improve login UX",
                ],
            }
        )
        self.weeks.add("2026-W29")

        first = self.service.capture(payload)
        second = self.service.capture(payload)

        self.assertTrue(first.found)
        self.assertEqual(
            [item.external_id for item in first.notifications],
            [item.external_id for item in second.notifications],
        )
        self.assertEqual({item.status for item in second.notifications}, {NotificationStatus.SYNCED})

        reviewed = self.service.review("2026-W29")
        day = reviewed.state.days["2026-07-16"]
        self.assertEqual([item.text for item in day.completed], ["Finish café login module"])
        self.assertEqual(len(day.next_items), 3)
        self.assertIsNotNone(day.next_items[0].due_at)

        completion = self.service.capture(
            CapturePayload.from_dict(
                {
                    "date": "2026-07-16",
                    "completed": [
                        {"text": "Add login tests", "key": "qa-reminder"},
                        {"text": "Weekly review", "key": "qa-calendar"},
                    ],
                    "remove": [
                        {"section": "next", "text": "Add login tests"},
                        {"section": "next", "text": "Weekly review"},
                    ],
                }
            )
        )
        self.assertTrue(any(item.status is NotificationStatus.SYNCED for item in completion.notifications))

        self.weeks.add("2026-W30")
        rolled = self.service.rollover("2026-W29", "2026-W30")
        self.assertEqual(
            [item.text for item in rolled.state.days["2026-07-20"].next_items],
            ["Improve login UX"],
        )


if __name__ == "__main__":
    unittest.main()
