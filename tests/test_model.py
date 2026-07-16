from __future__ import annotations

import unittest
from datetime import date

from scripts.mwp.model import CapturePayload, ValidationError, WeekRef, stable_key


class WeekRefTests(unittest.TestCase):
    def test_week_ref_uses_monday_and_iso_number(self) -> None:
        week = WeekRef.from_date(date(2026, 7, 16), "Asia/Shanghai")

        self.assertEqual(week.iso_key, "2026-W29")
        self.assertEqual(week.title, "2026-W29 | Weekly Progress | 07.13-07.19")
        self.assertEqual(week.start.isoformat(), "2026-07-13")
        self.assertEqual(week.end.isoformat(), "2026-07-19")

    def test_week_ref_round_trips_iso_key(self) -> None:
        week = WeekRef.from_iso_key("2026-W29")
        self.assertEqual(week.iso_key, "2026-W29")

    def test_invalid_timezone_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            WeekRef.from_date(date(2026, 7, 16), "Not/AZone")


class CapturePayloadTests(unittest.TestCase):
    def test_item_text_rejects_non_whitespace_control_characters(self) -> None:
        with self.assertRaisesRegex(ValidationError, "control"):
            CapturePayload.from_dict({"date": "2026-07-16", "next": ["unsafe\u0000text"]})

    def test_capture_rejects_due_without_timezone(self) -> None:
        with self.assertRaisesRegex(ValidationError, "timezone"):
            CapturePayload.from_dict(
                {
                    "date": "2026-07-16",
                    "next": [
                        {"text": "Add login tests", "due_at": "2026-07-17T18:00:00"}
                    ],
                }
            )

    def test_capture_normalizes_and_deduplicates_items(self) -> None:
        payload = CapturePayload.from_dict(
            {
                "date": "2026-07-16",
                "completed": ["  Finish   login module  ", "Finish login module"],
            }
        )

        self.assertEqual([item.text for item in payload.completed], ["Finish login module"])

    def test_conflicting_duplicates_of_same_text_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "conflicting duplicates"):
            CapturePayload.from_dict(
                {
                    "date": "2026-07-16",
                    "next": [
                        {"text": "Add login tests", "due_at": "2026-07-17T18:00:00+08:00"},
                        {"text": "Add login tests", "due_at": "2026-07-18T09:00:00+08:00"},
                    ],
                }
            )

    def test_explicit_key_is_preserved(self) -> None:
        payload = CapturePayload.from_dict(
            {
                "date": "2026-07-16",
                "next": [{"text": "Add login tests", "key": "login-tests"}],
            }
        )

        self.assertEqual(payload.next_items[0].key, "login-tests")

    def test_stable_key_ignores_extra_whitespace(self) -> None:
        self.assertEqual(
            stable_key("next", "Add   login tests"),
            stable_key("next", "Add login tests"),
        )

    def test_item_text_rejects_managed_region_markers(self) -> None:
        with self.assertRaisesRegex(ValidationError, "managed region markers"):
            CapturePayload.from_dict(
                {
                    "date": "2026-07-16",
                    "next": ["break the ⟦manage-weekly-progress:start:v1⟧ marker"],
                }
            )

    def test_item_text_rejects_forged_timing_metadata_suffix(self) -> None:
        with self.assertRaisesRegex(ValidationError, "timing metadata"):
            CapturePayload.from_dict(
                {
                    "date": "2026-07-16",
                    "next": ["Add login tests ⟨reminder: 2026-07-17T18:00:00+08:00; key: evil⟩"],
                }
            )

    def test_unknown_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "unknown"):
            CapturePayload.from_dict({"date": "2026-07-16", "mystery": []})

    def test_calendar_kind_requires_an_end_time(self) -> None:
        with self.assertRaisesRegex(ValidationError, "end_at"):
            CapturePayload.from_dict(
                {
                    "date": "2026-07-16",
                    "next": [
                        {
                            "text": "Weekly review",
                            "kind": "calendar",
                            "due_at": "2026-07-17T16:00:00+08:00",
                        }
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
