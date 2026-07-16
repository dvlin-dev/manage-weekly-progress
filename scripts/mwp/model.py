from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SECTIONS = ("goals", "completed", "next", "blocked", "follow_up")
KNOWN_CAPTURE_FIELDS = frozenset(("date", "summary", "remove", *SECTIONS))
KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
ISO_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")

START_TEXT = "⟦manage-weekly-progress:start:v1⟧"
END_TEXT = "⟦manage-weekly-progress:end:v1⟧"
TIMING_RE = re.compile(
    r"^(.*?)\s*⟨(reminder|calendar|time): (.+?)(?: → (.+?))?; key: ([A-Za-z0-9._:-]{1,128})⟩$"
)


class ValidationError(ValueError):
    """Raised when agent-provided progress data is unsafe or malformed."""


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError("item text must be a string")
    if any((ord(character) < 32 and not character.isspace()) or ord(character) == 127 for character in value):
        raise ValidationError("item text must not contain control characters")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValidationError("item text must not be empty")
    if len(normalized) > 2000:
        raise ValidationError("item text must not exceed 2000 characters")
    if START_TEXT in normalized or END_TEXT in normalized:
        raise ValidationError("item text must not contain managed region markers")
    if TIMING_RE.fullmatch(normalized):
        raise ValidationError("item text must not end with managed timing metadata")
    return normalized


def stable_key(section: str, text: str) -> str:
    normalized = normalize_text(text).casefold()
    digest = hashlib.sha256(f"{section}\0{normalized}".encode("utf-8")).hexdigest()
    return digest[:20]


def parse_aware_datetime(value: Any, field_name: str) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field_name} must be a valid ISO 8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{field_name} must include a timezone offset")
    return parsed


@dataclass(frozen=True)
class WeekRef:
    start: date
    end: date
    iso_year: int
    iso_week: int

    @classmethod
    def from_date(cls, day: date, timezone_name: str = "system") -> "WeekRef":
        if timezone_name != "system":
            try:
                ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError as exc:
                raise ValidationError(f"unknown timezone: {timezone_name}") from exc
        iso = day.isocalendar()
        start = day - timedelta(days=iso.weekday - 1)
        return cls(start=start, end=start + timedelta(days=6), iso_year=iso.year, iso_week=iso.week)

    @classmethod
    def from_iso_key(cls, value: str) -> "WeekRef":
        match = ISO_WEEK_RE.fullmatch(value)
        if not match:
            raise ValidationError("week must use YYYY-Www format")
        year, week = (int(part) for part in match.groups())
        try:
            monday = date.fromisocalendar(year, week, 1)
        except ValueError as exc:
            raise ValidationError(f"invalid ISO week: {value}") from exc
        return cls.from_date(monday)

    @property
    def iso_key(self) -> str:
        return f"{self.iso_year:04d}-W{self.iso_week:02d}"

    @property
    def title(self) -> str:
        return f"{self.iso_key} | Weekly Progress | {self.start:%m.%d}-{self.end:%m.%d}"


@dataclass(frozen=True)
class ProgressItem:
    section: str
    text: str
    key: str
    due_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    kind: str = "auto"

    @classmethod
    def from_value(cls, section: str, value: Union[str, Mapping[str, Any]]) -> "ProgressItem":
        if isinstance(value, str):
            data: Dict[str, Any] = {"text": value}
        elif isinstance(value, Mapping):
            data = dict(value)
        else:
            raise ValidationError(f"{section} items must be strings or objects")

        unknown = set(data) - {"text", "key", "due_at", "end_at", "kind"}
        if unknown:
            raise ValidationError(f"unknown {section} item fields: {', '.join(sorted(unknown))}")
        text = normalize_text(data.get("text"))
        key = data.get("key") or stable_key(section, text)
        if not isinstance(key, str) or not KEY_RE.fullmatch(key):
            raise ValidationError("item key must be 1-128 letters, digits, dot, colon, underscore, or hyphen")
        kind = data.get("kind", "auto")
        if kind not in {"auto", "reminder", "calendar", "none"}:
            raise ValidationError("item kind must be auto, reminder, calendar, or none")
        due_at = parse_aware_datetime(data.get("due_at"), "due_at")
        end_at = parse_aware_datetime(data.get("end_at"), "end_at")
        if end_at is not None and due_at is None:
            raise ValidationError("end_at requires due_at")
        if kind == "calendar" and end_at is None:
            raise ValidationError("calendar items require end_at")
        if due_at is not None and end_at is not None and end_at <= due_at:
            raise ValidationError("end_at must be later than due_at")
        return cls(section=section, text=text, key=key, due_at=due_at, end_at=end_at, kind=kind)


def _items(section: str, values: Any) -> Tuple[ProgressItem, ...]:
    if values is None:
        return ()
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValidationError(f"{section} must be an array")
    result: List[ProgressItem] = []
    seen: Dict[str, ProgressItem] = {}
    for value in values:
        item = ProgressItem.from_value(section, value)
        identity = item.text.casefold()
        previous = seen.get(identity)
        if previous is None:
            seen[identity] = item
            result.append(item)
        elif previous != item:
            raise ValidationError(
                f"{section} contains conflicting duplicates of the same text: {item.text}"
            )
    return tuple(result)


@dataclass(frozen=True)
class RemoveItem:
    section: str
    text: str

    @classmethod
    def from_value(cls, value: Mapping[str, Any]) -> "RemoveItem":
        if not isinstance(value, Mapping):
            raise ValidationError("remove items must be objects")
        unknown = set(value) - {"section", "text"}
        if unknown:
            raise ValidationError(f"unknown remove fields: {', '.join(sorted(unknown))}")
        section = value.get("section")
        if section not in SECTIONS:
            raise ValidationError(f"remove section must be one of: {', '.join(SECTIONS)}")
        return cls(section=section, text=normalize_text(value.get("text")))


@dataclass(frozen=True)
class CapturePayload:
    day: date
    goals: Tuple[ProgressItem, ...] = field(default_factory=tuple)
    completed: Tuple[ProgressItem, ...] = field(default_factory=tuple)
    next_items: Tuple[ProgressItem, ...] = field(default_factory=tuple)
    blocked: Tuple[ProgressItem, ...] = field(default_factory=tuple)
    follow_up: Tuple[ProgressItem, ...] = field(default_factory=tuple)
    summary: Tuple[str, ...] = field(default_factory=tuple)
    remove: Tuple[RemoveItem, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CapturePayload":
        if not isinstance(data, Mapping):
            raise ValidationError("capture input must be a JSON object")
        unknown = set(data) - KNOWN_CAPTURE_FIELDS
        if unknown:
            raise ValidationError(f"unknown capture fields: {', '.join(sorted(unknown))}")
        raw_date = data.get("date")
        if not isinstance(raw_date, str):
            raise ValidationError("date is required and must use YYYY-MM-DD")
        try:
            day = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ValidationError("date must use YYYY-MM-DD") from exc

        summary_values = data.get("summary", [])
        if not isinstance(summary_values, Sequence) or isinstance(summary_values, (str, bytes)):
            raise ValidationError("summary must be an array")
        summary = tuple(dict.fromkeys(normalize_text(value) for value in summary_values))

        remove_values = data.get("remove", [])
        if not isinstance(remove_values, Sequence) or isinstance(remove_values, (str, bytes)):
            raise ValidationError("remove must be an array")

        return cls(
            day=day,
            goals=_items("goals", data.get("goals")),
            completed=_items("completed", data.get("completed")),
            next_items=_items("next", data.get("next")),
            blocked=_items("blocked", data.get("blocked")),
            follow_up=_items("follow_up", data.get("follow_up")),
            summary=summary,
            remove=tuple(RemoveItem.from_value(value) for value in remove_values),
        )

    def all_items(self) -> Iterable[ProgressItem]:
        return (*self.goals, *self.completed, *self.next_items, *self.blocked, *self.follow_up)
