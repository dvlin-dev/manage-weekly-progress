from __future__ import annotations

import os
import subprocess
import sys
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "manage_weekly_progress.py"


def _write_fake_osascript(directory: Path, body: str) -> Path:
    executable = directory / "fake-osascript"
    executable.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    executable.chmod(0o755)
    return executable


def _run_doctor(directory: Path, fake_body: str) -> subprocess.CompletedProcess[str]:
    fake = _write_fake_osascript(directory, fake_body)
    return subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--config",
            str(directory / "config.json"),
            "doctor",
        ],
        env={**os.environ, "MWP_OSASCRIPT": str(fake)},
        capture_output=True,
        text=True,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_help_lists_public_commands(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CLI), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("doctor", "capture", "review", "rollover"):
            self.assertIn(command, result.stdout)

    def test_capture_dry_run_reads_json_from_stdin(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CLI), "capture", "--input", "-", "--dry-run"],
            input=json.dumps(
                {
                    "date": "2026-07-16",
                    "completed": ["Finish login module"],
                    "next": [
                        {
                            "text": "Add login tests",
                            "due_at": "2026-07-17T18:00:00+08:00",
                        }
                    ],
                }
            ),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["week"], "2026-W29")
        self.assertIn("Finish login module", output["note_body"])
        self.assertEqual(output["notifications"][0]["route"], "reminder")

    def test_invalid_capture_returns_structured_error_without_traceback(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CLI), "capture", "--input", "-", "--dry-run"],
            input="{}",
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["error"]["type"], "ValidationError")
        self.assertNotIn("Traceback", result.stderr)

    def test_managed_region_error_is_handled_as_operational_failure(self) -> None:
        source = CLI.read_text(encoding="utf-8")

        self.assertIn("ManagedRegionError", source)
        self.assertIn("ConfigError, AppleScriptError, ManagedRegionError", source)

    def test_doctor_reports_ok_and_date_context_when_apps_respond(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = _run_doctor(Path(directory), "echo ok")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["ok"])
        self.assertEqual(
            {name: check["status"] for name, check in output["checks"].items()},
            {"notes": "ok", "reminders": "ok", "calendar": "ok"},
        )
        self.assertRegex(output["context"]["today"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(output["context"]["current_week"], r"^\d{4}-W\d{2}$")
        self.assertIn(output["context"]["current_week"], output["context"]["current_week_title"])

    def test_doctor_fails_when_notes_is_unavailable_but_reports_optional_apps(self) -> None:
        fake_body = (
            'case "$1" in\n'
            '  *notes*) echo "Not authorized to send Apple events. (-1743)" >&2; exit 1 ;;\n'
            "  *) echo ok ;;\n"
            "esac"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = _run_doctor(Path(directory), fake_body)

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertFalse(output["ok"])
        self.assertEqual(output["checks"]["notes"]["status"], "error")
        self.assertEqual(output["checks"]["reminders"]["status"], "ok")
        self.assertEqual(output["checks"]["calendar"]["status"], "ok")

    def test_review_missing_week_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--config",
                    str(Path(directory) / "config.json"),
                    "review",
                    "--week",
                    "2026-W29",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["found"])

    def test_configure_updates_preferences_without_initializing_apps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--config",
                    str(config_path),
                    "configure",
                    "--timezone",
                    "Asia/Shanghai",
                    "--notes-folder-name",
                    "My Progress",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            stored = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stored["timezone"], "Asia/Shanghai")
        self.assertEqual(stored["notes_folder_name"], "My Progress")
        self.assertIsNone(stored["notes_folder_id"])


if __name__ == "__main__":
    unittest.main()
