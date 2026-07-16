from __future__ import annotations

import unittest
from datetime import date

from scripts.mwp.model import CapturePayload, WeekRef
from scripts.mwp.note_format import (
    END_TEXT,
    START_TEXT,
    ManagedRegionError,
    WeeklyState,
    merge_capture,
    merge_managed_region,
    parse_managed_state,
)


class NoteFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.week = WeekRef.from_date(date(2026, 7, 16), "Asia/Shanghai")

    def test_merge_preserves_manual_content_outside_markers(self) -> None:
        original = (
            "<div>Manual preface</div>"
            f"<div>{START_TEXT}</div><div>old content</div><div>{END_TEXT}</div>"
            "<div>Manual footer</div>"
        )
        state = WeeklyState.empty(self.week)

        merged = merge_managed_region(original, state)

        self.assertIn("Manual preface", merged)
        self.assertIn("Manual footer", merged)
        self.assertNotIn("old content", merged)

    def test_merge_rejects_duplicate_marker_pairs(self) -> None:
        original = f"<div>{START_TEXT}</div><div>{END_TEXT}</div>" * 2

        with self.assertRaises(ManagedRegionError):
            merge_managed_region(original, WeeklyState.empty(self.week))

    def test_malformed_managed_timing_fails_closed(self) -> None:
        body = (
            f"<div>{START_TEXT}</div>"
            "<div><b>Follow-ups</b></div>"
            "<ul><li>Ship ⟨reminder: not-a-date; key: release⟩</li></ul>"
            f"<div>{END_TEXT}</div>"
        )

        with self.assertRaisesRegex(ManagedRegionError, "timing metadata"):
            parse_managed_state(body, self.week)

    def test_parse_render_round_trip_preserves_due_time(self) -> None:
        payload = CapturePayload.from_dict(
            {
                "date": "2026-07-16",
                "completed": ["Finish login module"],
                "next": [
                    {
                        "text": "Add login tests",
                        "key": "login-tests",
                        "due_at": "2026-07-17T18:00:00+08:00",
                    }
                ],
            }
        )
        state = merge_capture(WeeklyState.empty(self.week), payload)

        parsed = parse_managed_state(merge_managed_region("<div>Title</div>", state), self.week)

        self.assertEqual(parsed.days["2026-07-16"].completed[0].text, "Finish login module")
        self.assertEqual(
            parsed.days["2026-07-16"].next_items[0].due_at.isoformat(),
            "2026-07-17T18:00:00+08:00",
        )
        self.assertEqual(parsed.days["2026-07-16"].next_items[0].key, "login-tests")

    def test_repeated_capture_is_idempotent(self) -> None:
        payload = CapturePayload.from_dict(
            {"date": "2026-07-16", "completed": ["Finish login module"]}
        )

        once = merge_capture(WeeklyState.empty(self.week), payload)
        twice = merge_capture(once, payload)

        self.assertEqual(len(twice.days["2026-07-16"].completed), 1)

    def test_item_text_equal_to_section_heading_stays_an_item(self) -> None:
        payload = CapturePayload.from_dict(
            {
                "date": "2026-07-16",
                "goals": ["Weekly Summary", "Ship the skill"],
                "completed": ["Finish login module"],
            }
        )
        state = merge_capture(WeeklyState.empty(self.week), payload)

        parsed = parse_managed_state(merge_managed_region("", state), self.week)

        self.assertEqual([item.text for item in parsed.goals], ["Weekly Summary", "Ship the skill"])
        self.assertEqual(parsed.summary, ())
        self.assertEqual(
            [item.text for item in parsed.days["2026-07-16"].completed],
            ["Finish login module"],
        )

    def test_kind_none_with_end_time_round_trips_without_becoming_calendar(self) -> None:
        payload = CapturePayload.from_dict(
            {
                "date": "2026-07-16",
                "next": [
                    {
                        "text": "Write weekly report",
                        "key": "weekly-report",
                        "kind": "none",
                        "due_at": "2026-07-17T10:00:00+08:00",
                        "end_at": "2026-07-17T11:00:00+08:00",
                    }
                ],
            }
        )
        state = merge_capture(WeeklyState.empty(self.week), payload)

        parsed = parse_managed_state(merge_managed_region("", state), self.week)
        item = parsed.days["2026-07-16"].next_items[0]

        self.assertEqual(item.kind, "none")
        self.assertEqual(item.end_at.isoformat(), "2026-07-17T11:00:00+08:00")

    def test_recapture_without_time_preserves_stored_key_and_timing(self) -> None:
        first = CapturePayload.from_dict(
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
        second = CapturePayload.from_dict(
            {"date": "2026-07-16", "next": ["Add login tests"]}
        )

        state = merge_capture(merge_capture(WeeklyState.empty(self.week), first), second)
        item = state.days["2026-07-16"].next_items[0]

        self.assertEqual(item.key, "login-tests")
        self.assertEqual(item.due_at.isoformat(), "2026-07-17T18:00:00+08:00")

    def test_recapture_with_new_time_replaces_stored_timing(self) -> None:
        first = CapturePayload.from_dict(
            {
                "date": "2026-07-16",
                "next": [
                    {"text": "Add login tests", "due_at": "2026-07-17T18:00:00+08:00"}
                ],
            }
        )
        second = CapturePayload.from_dict(
            {
                "date": "2026-07-16",
                "next": [
                    {"text": "Add login tests", "due_at": "2026-07-18T09:00:00+08:00"}
                ],
            }
        )

        state = merge_capture(merge_capture(WeeklyState.empty(self.week), first), second)
        item = state.days["2026-07-16"].next_items[0]

        self.assertEqual(item.due_at.isoformat(), "2026-07-18T09:00:00+08:00")
        self.assertEqual(len(state.days["2026-07-16"].next_items), 1)

    def test_oversized_managed_item_fails_as_managed_region_error(self) -> None:
        body = (
            f"<div>{START_TEXT}</div>"
            "<div><b>Weekly Summary</b></div>"
            f"<ul><li>{'x' * 2001}</li></ul>"
            f"<div>{END_TEXT}</div>"
        )

        with self.assertRaisesRegex(ManagedRegionError, "summary"):
            parse_managed_state(body, self.week)

    def test_remove_deletes_only_matching_section_item(self) -> None:
        initial = CapturePayload.from_dict(
            {
                "date": "2026-07-16",
                "next": ["Improve login UX"],
                "blocked": ["Improve login UX"],
            }
        )
        remove = CapturePayload.from_dict(
            {
                "date": "2026-07-16",
                "remove": [{"section": "next", "text": "Improve login UX"}],
            }
        )

        state = merge_capture(merge_capture(WeeklyState.empty(self.week), initial), remove)

        self.assertEqual(state.days["2026-07-16"].next_items, ())
        self.assertEqual(state.days["2026-07-16"].blocked[0].text, "Improve login UX")


if __name__ == "__main__":
    unittest.main()
