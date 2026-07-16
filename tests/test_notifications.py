from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.mwp.apple import AppleNotFoundError, AppleScriptError, ContainerRef
from scripts.mwp.config import AppConfig, ConfigStore
from scripts.mwp.model import CapturePayload, ProgressItem
from scripts.mwp.service import NotificationRoute, NotificationStatus, WeeklyProgressService, route_notification

from tests.test_service import MemoryNotes


START = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)
END = START + timedelta(minutes=30)


def item(**overrides: object) -> ProgressItem:
    values = {
        "section": "next",
        "text": "Add login tests",
        "key": "login-tests",
        "due_at": None,
        "end_at": None,
        "kind": "auto",
    }
    values.update(overrides)
    return ProgressItem(**values)


class MemoryReminders:
    def __init__(self, fail: bool = False) -> None:
        self.container = ContainerRef("list-1", "Weekly Progress")
        self.items: dict[str, str] = {}
        self.completed: set[str] = set()
        self.fail = fail

    def ensure_list(self, known_id: str | None, preferred_name: str) -> ContainerRef:
        if self.fail:
            raise AppleScriptError("reminders unavailable")
        return self.container

    def upsert(self, list_id: str, key: str, name: str, source: str, due_at: datetime) -> str:
        self.items[key] = name
        return f"reminder-{key}"

    def complete(self, list_id: str, key: str) -> str:
        self.completed.add(key)
        return f"reminder-{key}" if key in self.items else "MISSING"


class MemoryCalendar:
    def __init__(self) -> None:
        self.container = ContainerRef("calendar-token", "Weekly Progress")
        self.items: dict[str, str] = {}
        self.deleted: set[str] = set()

    def ensure_calendar(self, known_id: str | None, preferred_name: str) -> ContainerRef:
        return self.container

    def verify_writable(self, calendar_id: str) -> bool:
        return True

    def upsert(self, calendar_id: str, key: str, summary: str, source: str, start_at: datetime, end_at: datetime) -> str:
        self.items[key] = summary
        return f"event-{key}"

    def delete_event(self, calendar_id: str, key: str) -> str:
        self.deleted.add(key)
        return f"event-{key}" if key in self.items else "MISSING"


class LaggingTokenCalendar(MemoryCalendar):
    """Fresh ownership token stays invisible for the first verify calls."""

    def __init__(self, invisible_calls: int) -> None:
        super().__init__()
        self.invisible_calls = invisible_calls
        self.verify_calls = 0

    def verify_writable(self, calendar_id: str) -> bool:
        self.verify_calls += 1
        if self.verify_calls <= self.invisible_calls:
            raise AppleNotFoundError(f"MWP_NOT_OWNED:Calendar token:{calendar_id}")
        return True


class NotificationRoutingTests(unittest.TestCase):
    def test_route_requires_explicit_time(self) -> None:
        self.assertEqual(route_notification(item()), NotificationRoute.NONE)

    def test_route_uses_reminder_for_deadline(self) -> None:
        self.assertEqual(route_notification(item(due_at=START)), NotificationRoute.REMINDER)

    def test_route_uses_calendar_for_time_range(self) -> None:
        self.assertEqual(
            route_notification(item(due_at=START, end_at=END)),
            NotificationRoute.CALENDAR,
        )


class NotificationSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.config = ConfigStore(Path(self.temp.name) / "config.json")
        self.reminders = MemoryReminders()
        self.calendar = MemoryCalendar()
        self.service = WeeklyProgressService(
            self.config,
            MemoryNotes(),
            self.reminders,
            self.calendar,
            sleep=lambda _: None,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_repeated_sync_updates_same_managed_object(self) -> None:
        first = self.service.sync_notification(item(due_at=START), "2026-W29")
        second = self.service.sync_notification(item(due_at=START + timedelta(hours=1)), "2026-W29")

        self.assertEqual(first.external_id, second.external_id)
        self.assertEqual(len(self.reminders.items), 1)

    def test_fresh_calendar_token_lag_is_retried_until_visible(self) -> None:
        calendar = LaggingTokenCalendar(invisible_calls=2)
        service = WeeklyProgressService(
            self.config,
            MemoryNotes(),
            self.reminders,
            calendar,
            sleep=lambda _: None,
        )

        result = service.sync_notification(item(due_at=START, end_at=END), "2026-W29")

        self.assertEqual(result.status, NotificationStatus.SYNCED)
        self.assertEqual(calendar.verify_calls, 3)

    def test_recorded_calendar_token_that_stops_resolving_is_not_retried(self) -> None:
        self.config.save(AppConfig(calendar_id="calendar-token"))
        calendar = LaggingTokenCalendar(invisible_calls=99)
        service = WeeklyProgressService(
            self.config,
            MemoryNotes(),
            self.reminders,
            calendar,
            sleep=lambda _: None,
        )

        result = service.sync_notification(item(due_at=START, end_at=END), "2026-W29")

        self.assertEqual(result.status, NotificationStatus.ERROR)
        self.assertEqual(calendar.verify_calls, 1)
        self.assertIn("MWP_NOT_OWNED", result.error)

    def test_notification_failure_is_returned_not_raised(self) -> None:
        service = WeeklyProgressService(
            self.config,
            MemoryNotes(),
            MemoryReminders(fail=True),
            self.calendar,
            sleep=lambda _: None,
        )

        result = service.sync_notification(item(due_at=START), "2026-W29")

        self.assertEqual(result.status, NotificationStatus.ERROR)
        self.assertIn("unavailable", result.error)

    def test_completed_item_closes_owned_notification_without_due_time(self) -> None:
        self.config.save(
            AppConfig(
                notes_folder_id="folder-1",
                reminders_list_id="list-1",
                calendar_id="calendar-token",
            )
        )
        self.reminders.items["login-tests"] = "Add login tests"
        self.calendar.items["login-tests"] = "Add login tests"
        payload = CapturePayload.from_dict(
            {
                "date": "2026-07-16",
                "completed": [{"text": "Add login tests", "key": "login-tests"}],
            }
        )

        result = self.service.capture(payload)

        self.assertIn("login-tests", self.reminders.completed)
        self.assertIn("login-tests", self.calendar.deleted)
        self.assertEqual({item.status for item in result.notifications}, {NotificationStatus.SYNCED})

    def test_remove_only_closes_notification_using_key_stored_in_note(self) -> None:
        self.service.capture(
            CapturePayload.from_dict(
                {
                    "date": "2026-07-16",
                    "next": [
                        {
                            "text": "Add login tests",
                            "key": "login-tests",
                            "due_at": "2026-07-17T18:00:00+08:00",
                        }
                    ],
                }
            )
        )

        self.service.capture(
            CapturePayload.from_dict(
                {
                    "date": "2026-07-16",
                    "remove": [{"section": "next", "text": "Add login tests"}],
                }
            )
        )

        self.assertIn("login-tests", self.reminders.completed)


if __name__ == "__main__":
    unittest.main()
