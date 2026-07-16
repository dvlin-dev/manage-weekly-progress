from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.mwp.apple import AppleScriptError, ContainerRef, NoteRef
from scripts.mwp.config import AppConfig, ConfigStore
from scripts.mwp.model import CapturePayload
from scripts.mwp.service import WeeklyProgressService


class MemoryNotes:
    def __init__(self) -> None:
        self.folder = ContainerRef("folder-1", "Weekly Progress")
        self.notes: dict[str, tuple[str, str]] = {}
        self.writes = 0

    def ensure_folder(self, account_name: str, known_id: str | None, preferred_name: str) -> ContainerRef:
        return self.folder

    def read_unique(self, folder_id: str, title: str) -> NoteRef | None:
        if title not in self.notes:
            return None
        note_id, body = self.notes[title]
        return NoteRef(note_id, body)

    def read_by_id(self, folder_id: str, note_id: str) -> NoteRef:
        for stored_id, body in self.notes.values():
            if stored_id == note_id:
                return NoteRef(stored_id, body)
        raise AssertionError("note not found")

    def create(self, folder_id: str, title: str, body: str) -> NoteRef:
        note = NoteRef(f"note-{len(self.notes) + 1}", f"<div>{title}</div>\n{body}")
        self.notes[title] = (note.id, note.body)
        return note

    def write(self, folder_id: str, note_id: str, expected_body: str, body: str) -> NoteRef:
        for title, (stored_id, stored_body) in self.notes.items():
            if stored_id == note_id:
                if stored_body != expected_body:
                    raise AssertionError("optimistic write conflict")
                self.notes[title] = (stored_id, body)
                self.writes += 1
                return NoteRef(stored_id, body)
        raise AssertionError("note not found")


class SummaryWriteFailingNotes(MemoryNotes):
    """Fails only the write that records the rollover summary."""

    def write(self, folder_id: str, note_id: str, expected_body: str, body: str) -> NoteRef:
        if "Rolled over to" in body:
            raise AppleScriptError("MWP_CONFLICT:Note changed since read")
        return super().write(folder_id, note_id, expected_body, body)


class NoopReminders:
    pass


class NoopCalendar:
    pass


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.config_store = ConfigStore(Path(self.temp.name) / "config.json")
        self.notes = MemoryNotes()
        self.service = WeeklyProgressService(
            self.config_store, self.notes, NoopReminders(), NoopCalendar(), sleep=lambda _: None
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_capture_is_idempotent(self) -> None:
        payload = CapturePayload.from_dict(
            {"date": "2026-07-16", "completed": ["Finish login module"]}
        )

        self.service.capture(payload)
        self.service.capture(payload)
        reviewed = self.service.review("2026-W29")

        self.assertEqual(
            [item.text for item in reviewed.state.days["2026-07-16"].completed],
            ["Finish login module"],
        )

    def test_capture_saves_owned_folder_id(self) -> None:
        self.service.capture(CapturePayload.from_dict({"date": "2026-07-16"}))
        self.assertEqual(self.config_store.load().notes_folder_id, "folder-1")

    def test_review_does_not_create_container_when_uninitialized(self) -> None:
        result = self.service.review("2026-W29")
        self.assertFalse(result.found)
        self.assertEqual(self.notes.notes, {})

    def test_rollover_summary_failure_reports_carried_items_and_safe_retry(self) -> None:
        notes = SummaryWriteFailingNotes()
        service = WeeklyProgressService(
            self.config_store, notes, NoopReminders(), NoopCalendar(), sleep=lambda _: None
        )
        service.capture(
            CapturePayload.from_dict({"date": "2026-07-16", "next": ["Improve login UX"]})
        )

        with self.assertRaisesRegex(AppleScriptError, "already carried to 2026-W30"):
            service.rollover("2026-W29", "2026-W30")

        target = service.review("2026-W30")
        self.assertEqual(
            [item.text for item in target.state.days["2026-07-20"].next_items],
            ["Improve login UX"],
        )

    def test_rollover_with_many_items_keeps_source_note_parseable(self) -> None:
        self.service.capture(
            CapturePayload.from_dict(
                {
                    "date": "2026-07-16",
                    "next": [f"Item {index}: {'long description ' * 22}" for index in range(20)],
                }
            )
        )

        self.service.rollover("2026-W29", "2026-W30")
        reviewed = self.service.review("2026-W29")

        self.assertEqual(len(reviewed.state.summary), 1)
        self.assertLess(len(reviewed.state.summary[0]), 600)
        self.assertIn("Rolled over to 2026-W30 (20 items)", reviewed.state.summary[0])

    def test_rollover_copies_only_open_items(self) -> None:
        self.service.capture(
            CapturePayload.from_dict(
                {
                    "date": "2026-07-16",
                    "completed": ["Finish login module"],
                    "next": ["Improve login UX"],
                    "blocked": ["Wait for design review"],
                    "follow_up": ["Sync the docs"],
                }
            )
        )

        result = self.service.rollover("2026-W29", "2026-W30")

        monday = result.state.days["2026-07-20"]
        self.assertEqual([item.text for item in monday.next_items], ["Improve login UX"])
        self.assertEqual([item.text for item in monday.blocked], ["Wait for design review"])
        self.assertEqual([item.text for item in result.state.follow_up], ["Sync the docs"])
        self.assertNotIn("Finish login module", str(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
