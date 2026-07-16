from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol, Tuple


RECORD_SEPARATOR = "\x1e"
SCRIPT_DIR = Path(__file__).resolve().parents[1] / "applescript"


class AppleScriptError(RuntimeError):
    """Base error for macOS application automation failures."""


class ApplePermissionError(AppleScriptError):
    """Raised when macOS denies automation access."""


class AppleAmbiguityError(AppleScriptError):
    """Raised when multiple candidates make a write unsafe."""


class AppleNotFoundError(AppleScriptError):
    """Raised when an owned object no longer exists."""


class AppleSyncPendingError(AppleScriptError):
    """Raised when iCloud has not made a newly created object writable yet."""


class AppleConflictError(AppleScriptError):
    """Raised when an Apple object changes after it was read."""


def _map_error(stderr: str) -> AppleScriptError:
    message = stderr.strip() or "osascript failed without an error message"
    lowered = message.casefold()
    if "-1743" in message or "not authorized" in lowered or "not permitted" in lowered:
        return ApplePermissionError(message)
    if "MWP_AMBIGUOUS" in message:
        return AppleAmbiguityError(message)
    if "MWP_NOT_FOUND" in message or "MWP_NOT_OWNED" in message:
        return AppleNotFoundError(message)
    if "MWP_SYNC_PENDING" in message:
        return AppleSyncPendingError(message)
    if "MWP_CONFLICT" in message:
        return AppleConflictError(message)
    return AppleScriptError(message)


class Runner(Protocol):
    def run(self, script: str, action: str, *args: str) -> str:
        ...


class AppleScriptRunner:
    def __init__(self, executable: Optional[str] = None, timeout: int = 30) -> None:
        # MWP_OSASCRIPT lets hermetic tests substitute the osascript binary.
        self.executable = executable or os.environ.get("MWP_OSASCRIPT", "/usr/bin/osascript")
        self.timeout = timeout

    def run(self, script: str, action: str, *args: str) -> str:
        script_path = SCRIPT_DIR / script
        try:
            result = subprocess.run(
                [self.executable, str(script_path), action, *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AppleScriptError(f"{script} {action} timed out after {self.timeout}s") from exc
        except OSError as exc:
            raise AppleScriptError(f"cannot execute {self.executable}: {exc}") from exc
        if result.returncode != 0:
            raise _map_error(result.stderr)
        # osascript appends one line-feed to its printed result. Preserve any
        # line-feed that belongs to the returned Notes HTML itself.
        return result.stdout[:-1] if result.stdout.endswith("\n") else result.stdout


@dataclass(frozen=True)
class ContainerRef:
    id: str
    name: str


@dataclass(frozen=True)
class NoteRef:
    id: str
    body: str


@dataclass(frozen=True)
class ReminderDetail:
    id: str
    due_local: Optional[str]
    completed: bool


@dataclass(frozen=True)
class EventDetail:
    id: str
    start_local: str
    end_local: str


def _split_exact(value: str, count: int) -> Tuple[str, ...]:
    parts = tuple(value.split(RECORD_SEPARATOR, count - 1))
    if len(parts) != count:
        raise AppleScriptError(f"unexpected AppleScript response: {value!r}")
    return parts


def _write_temp_text(value: str) -> tempfile.TemporaryDirectory[str]:
    directory = tempfile.TemporaryDirectory(prefix="manage-weekly-progress-")
    (Path(directory.name) / "value.txt").write_text(value, encoding="utf-8")
    return directory


def _local_components(value: datetime) -> Tuple[str, ...]:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    local = value.astimezone()
    return tuple(str(part) for part in (local.year, local.month, local.day, local.hour, local.minute, local.second))


def local_naive_iso(value: datetime) -> str:
    """Format an aware datetime the way the AppleScript adapters report stored dates."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")


class NotesStore:
    script = "notes.applescript"

    def __init__(self, runner: Runner) -> None:
        self.runner = runner

    def doctor(self) -> str:
        return self.runner.run(self.script, "doctor")

    def ensure_folder(self, account_name: str, known_id: Optional[str], preferred_name: str) -> ContainerRef:
        value = self.runner.run(self.script, "ensure-folder", account_name, known_id or "", preferred_name)
        folder_id, name = _split_exact(value, 2)
        return ContainerRef(folder_id, name)

    def read_unique(self, folder_id: str, title: str) -> Optional[NoteRef]:
        value = self.runner.run(self.script, "read-note", folder_id, title)
        if value == "MISSING":
            return None
        status, note_id, body = _split_exact(value, 3)
        if status != "FOUND":
            raise AppleScriptError(f"unexpected Notes status: {status}")
        return NoteRef(note_id, body)

    def read_by_id(self, folder_id: str, note_id: str) -> NoteRef:
        status, returned_id, body = _split_exact(
            self.runner.run(self.script, "read-by-id", folder_id, note_id), 3
        )
        if status != "FOUND":
            raise AppleNotFoundError(f"owned note no longer exists: {note_id}")
        return NoteRef(returned_id, body)

    def create(self, folder_id: str, title: str, body: str) -> NoteRef:
        directory = _write_temp_text(body)
        try:
            note_id, stored_body = _split_exact(
                self.runner.run(
                    self.script,
                    "create-note",
                    folder_id,
                    title,
                    str(Path(directory.name) / "value.txt"),
                ),
                2,
            )
            return NoteRef(note_id, stored_body)
        finally:
            directory.cleanup()

    def write(self, folder_id: str, note_id: str, expected_body: str, body: str) -> NoteRef:
        expected_directory = _write_temp_text(expected_body)
        updated_directory = _write_temp_text(body)
        try:
            returned_id, stored_body = _split_exact(
                self.runner.run(
                    self.script,
                    "write-note",
                    folder_id,
                    note_id,
                    str(Path(expected_directory.name) / "value.txt"),
                    str(Path(updated_directory.name) / "value.txt"),
                ),
                2,
            )
            return NoteRef(returned_id, stored_body)
        finally:
            expected_directory.cleanup()
            updated_directory.cleanup()

    def delete(self, folder_id: str, note_id: str) -> None:
        self.runner.run(self.script, "delete-note", folder_id, note_id)

    def delete_folder(self, folder_id: str) -> None:
        self.runner.run(self.script, "delete-folder", folder_id)


class ReminderStore:
    script = "reminders.applescript"

    def __init__(self, runner: Runner) -> None:
        self.runner = runner

    def doctor(self) -> str:
        return self.runner.run(self.script, "doctor")

    def ensure_list(self, known_id: Optional[str], preferred_name: str) -> ContainerRef:
        value = self.runner.run(self.script, "ensure-list", known_id or "", preferred_name)
        list_id, name = _split_exact(value, 2)
        return ContainerRef(list_id, name)

    def upsert(self, list_id: str, item_key: str, name: str, source: str, due_at: datetime) -> str:
        return self.runner.run(
            self.script,
            "upsert",
            list_id,
            item_key,
            name,
            source,
            *_local_components(due_at),
        )

    def read(self, list_id: str, item_key: str) -> Optional[ReminderDetail]:
        value = self.runner.run(self.script, "read", list_id, item_key)
        if value == "MISSING":
            return None
        status, reminder_id, due_local, completed = _split_exact(value, 4)
        if status != "FOUND":
            raise AppleScriptError(f"unexpected Reminders status: {status}")
        return ReminderDetail(reminder_id, due_local or None, completed == "true")

    def complete(self, list_id: str, item_key: str) -> str:
        return self.runner.run(self.script, "complete", list_id, item_key)

    def delete_list(self, list_id: str) -> None:
        self.runner.run(self.script, "delete-list", list_id)


class CalendarStore:
    script = "calendar.applescript"

    def __init__(self, runner: Runner) -> None:
        self.runner = runner

    def doctor(self) -> str:
        return self.runner.run(self.script, "doctor")

    def ensure_calendar(self, known_id: Optional[str], preferred_name: str) -> ContainerRef:
        value = self.runner.run(self.script, "ensure-calendar", known_id or "", preferred_name)
        calendar_id, name = _split_exact(value, 2)
        return ContainerRef(calendar_id, name)

    def verify_writable(self, calendar_id: str) -> bool:
        return self.runner.run(self.script, "verify-writable", calendar_id) == "true"

    def upsert(
        self,
        calendar_id: str,
        item_key: str,
        summary: str,
        source: str,
        start_at: datetime,
        end_at: datetime,
    ) -> str:
        if end_at <= start_at:
            raise ValueError("calendar end time must be later than start time")
        return self.runner.run(
            self.script,
            "upsert",
            calendar_id,
            item_key,
            summary,
            source,
            *_local_components(start_at),
            *_local_components(end_at),
        )

    def read_event(self, calendar_id: str, item_key: str) -> Optional[EventDetail]:
        value = self.runner.run(self.script, "read-event", calendar_id, item_key)
        if value == "MISSING":
            return None
        status, event_id, start_local, end_local = _split_exact(value, 4)
        if status != "FOUND":
            raise AppleScriptError(f"unexpected Calendar status: {status}")
        return EventDetail(event_id, start_local, end_local)

    def delete_event(self, calendar_id: str, item_key: str) -> str:
        return self.runner.run(self.script, "delete-event", calendar_id, item_key)

    def delete_calendar(self, calendar_id: str) -> None:
        self.runner.run(self.script, "delete-calendar", calendar_id)
