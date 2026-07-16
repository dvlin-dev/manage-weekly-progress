from __future__ import annotations

import html
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Tuple

from .model import (
    END_TEXT,
    START_TEXT,
    TIMING_RE,
    CapturePayload,
    ProgressItem,
    ValidationError,
    WeekRef,
    normalize_text,
    stable_key,
)


DAY_RE = re.compile(r"^Date (\d{4}-\d{2}-\d{2})$")


class ManagedRegionError(RuntimeError):
    """Raised when a Note's managed region cannot be modified safely."""


@dataclass(frozen=True)
class DailyState:
    completed: Tuple[ProgressItem, ...] = field(default_factory=tuple)
    next_items: Tuple[ProgressItem, ...] = field(default_factory=tuple)
    blocked: Tuple[ProgressItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WeeklyState:
    week: WeekRef
    goals: Tuple[ProgressItem, ...] = field(default_factory=tuple)
    days: Dict[str, DailyState] = field(default_factory=dict)
    follow_up: Tuple[ProgressItem, ...] = field(default_factory=tuple)
    summary: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def empty(cls, week: WeekRef) -> "WeeklyState":
        return cls(week=week)


class _BlockParser(HTMLParser):
    BLOCKS = {"div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[Tuple[str, List[str]]] = []
        self.blocks: List[Tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag in self.BLOCKS:
            self.stack.append((tag, []))
        elif tag == "br" and self.stack:
            self.stack[-1][1].append(" ")

    def handle_data(self, data: str) -> None:
        for _, chunks in self.stack:
            chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            return
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                block_tag, chunks = self.stack.pop(index)
                text = " ".join("".join(chunks).split())
                if text:
                    self.blocks.append((block_tag, text))
                return


def _metadata(item: ProgressItem) -> str:
    if item.due_at is None:
        return ""
    if item.kind == "none":
        if item.end_at is not None:
            return f" ⟨time: {item.due_at.isoformat()} → {item.end_at.isoformat()}; key: {item.key}⟩"
        return f" ⟨time: {item.due_at.isoformat()}; key: {item.key}⟩"
    if item.end_at is not None or item.kind == "calendar":
        end = item.end_at.isoformat() if item.end_at else item.due_at.isoformat()
        return f" ⟨calendar: {item.due_at.isoformat()} → {end}; key: {item.key}⟩"
    return f" ⟨reminder: {item.due_at.isoformat()}; key: {item.key}⟩"


def _render_items(items: Iterable[ProgressItem]) -> str:
    values = [f"<li>{html.escape(item.text)}{html.escape(_metadata(item))}</li>" for item in items]
    return "<ul>" + "".join(values) + "</ul>" if values else ""


def render_managed_region(state: WeeklyState) -> str:
    parts = [f"<div>{START_TEXT}</div>"]
    if state.goals:
        parts.extend(("<div><b>Goals</b></div>", _render_items(state.goals)))
    if state.days:
        parts.append("<div><b>Daily Progress</b></div>")
        for day_key in sorted(state.days):
            day = state.days[day_key]
            parts.append(f"<div><b>Date {day_key}</b></div>")
            for heading, items in (
                ("Done", day.completed),
                ("Next", day.next_items),
                ("Blocked", day.blocked),
            ):
                if items:
                    parts.extend((f"<div><b>{heading}</b></div>", _render_items(items)))
    if state.follow_up:
        parts.extend(("<div><b>Follow-ups</b></div>", _render_items(state.follow_up)))
    if state.summary:
        parts.append("<div><b>Weekly Summary</b></div>")
        parts.append("<ul>" + "".join(f"<li>{html.escape(value)}</li>" for value in state.summary) + "</ul>")
    parts.append(f"<div>{END_TEXT}</div>")
    return "\n".join(parts)


def _marker_bounds(original: str) -> Optional[Tuple[int, int]]:
    start_count = original.count(START_TEXT)
    end_count = original.count(END_TEXT)
    if start_count == 0 and end_count == 0:
        return None
    if start_count != 1 or end_count != 1:
        raise ManagedRegionError("expected exactly one managed start marker and one end marker")
    start_text = original.index(START_TEXT)
    end_text = original.index(END_TEXT)
    if end_text <= start_text:
        raise ManagedRegionError("managed end marker appears before start marker")
    block_start = original.rfind("<", 0, start_text)
    close_start = original.find("</", end_text)
    block_end = original.find(">", close_start)
    if block_start < 0 or close_start < 0 or block_end < 0:
        raise ManagedRegionError("managed markers must be contained in HTML blocks")
    return block_start, block_end + 1


def merge_managed_region(original: str, state: WeeklyState) -> str:
    rendered = render_managed_region(state)
    bounds = _marker_bounds(original)
    if bounds is None:
        separator = "\n" if original else ""
        return original + separator + rendered
    start, end = bounds
    return original[:start] + rendered + original[end:]


def _parse_item(section: str, value: str) -> ProgressItem:
    match = TIMING_RE.fullmatch(value)
    due_at = None
    end_at = None
    kind = "auto"
    text = value
    if match:
        text, label, start_value, end_value, stored_key = match.groups()
        try:
            due_at = datetime.fromisoformat(start_value)
            if label == "calendar":
                kind = "calendar"
                end_at = datetime.fromisoformat(end_value or start_value)
            elif label == "time":
                kind = "none"
                end_at = datetime.fromisoformat(end_value) if end_value else None
            else:
                kind = "reminder"
        except ValueError as exc:
            raise ManagedRegionError(f"invalid timing metadata for item: {text}") from exc
    try:
        text = normalize_text(text)
    except ValidationError as exc:
        raise ManagedRegionError(f"managed region contains invalid item text: {exc}") from exc
    return ProgressItem(
        section=section,
        text=text,
        key=stored_key if match else stable_key(section, text),
        due_at=due_at,
        end_at=end_at,
        kind=kind,
    )


def parse_managed_state(body: str, week: WeekRef) -> WeeklyState:
    bounds = _marker_bounds(body)
    if bounds is None:
        return WeeklyState.empty(week)
    start, end = bounds
    parser = _BlockParser()
    parser.feed(body[start:end])

    goals: List[ProgressItem] = []
    follow_up: List[ProgressItem] = []
    summary: List[str] = []
    days: Dict[str, Dict[str, List[ProgressItem]]] = {}
    top_section: Optional[str] = None
    daily_section: Optional[str] = None
    current_day: Optional[str] = None

    for tag, value in parser.blocks:
        # Section headings and day lines are rendered as <div> blocks. A <li>
        # whose text happens to equal a heading is user data, never structure.
        if tag != "li":
            if value in {START_TEXT, END_TEXT}:
                continue
            if value == "Daily Progress":
                top_section = "daily"
                continue
            if value == "Goals":
                top_section, daily_section = "goals", None
                continue
            if value == "Follow-ups":
                top_section, daily_section = "follow_up", None
                continue
            if value == "Weekly Summary":
                top_section, daily_section = "summary", None
                continue
            day_match = DAY_RE.fullmatch(value)
            if day_match:
                top_section, current_day, daily_section = "daily", day_match.group(1), None
                days.setdefault(current_day, {"completed": [], "next": [], "blocked": []})
                continue
            if value in {"Done", "Next", "Blocked"} and top_section == "daily":
                daily_section = {"Done": "completed", "Next": "next", "Blocked": "blocked"}[value]
            continue
        if top_section == "goals":
            goals.append(_parse_item("goals", value))
        elif top_section == "follow_up":
            follow_up.append(_parse_item("follow_up", value))
        elif top_section == "summary":
            try:
                summary.append(normalize_text(value))
            except ValidationError as exc:
                raise ManagedRegionError(f"managed region contains invalid summary text: {exc}") from exc
        elif top_section == "daily" and current_day and daily_section:
            days[current_day][daily_section].append(_parse_item(daily_section, value))

    daily_states = {
        key: DailyState(
            completed=tuple(value["completed"]),
            next_items=tuple(value["next"]),
            blocked=tuple(value["blocked"]),
        )
        for key, value in days.items()
    }
    return WeeklyState(
        week=week,
        goals=tuple(goals),
        days=daily_states,
        follow_up=tuple(follow_up),
        summary=tuple(summary),
    )


def _absorb_existing(existing: ProgressItem, incoming: ProgressItem) -> ProgressItem:
    # A re-capture of the same text without any explicit timing intent must not
    # silently drop the stored notification identity or its recorded times.
    if incoming.due_at is not None or incoming.kind != "auto":
        return incoming
    key = incoming.key
    if key == stable_key(incoming.section, incoming.text):
        key = existing.key
    return replace(
        incoming,
        key=key,
        due_at=existing.due_at,
        end_at=existing.end_at,
        kind=existing.kind,
    )


def _upsert(existing: Tuple[ProgressItem, ...], incoming: Iterable[ProgressItem]) -> Tuple[ProgressItem, ...]:
    result = list(existing)
    positions = {item.text.casefold(): index for index, item in enumerate(result)}
    for item in incoming:
        identity = item.text.casefold()
        if identity in positions:
            index = positions[identity]
            result[index] = _absorb_existing(result[index], item)
        else:
            positions[identity] = len(result)
            result.append(item)
    return tuple(result)


def _remove(items: Tuple[ProgressItem, ...], text: str) -> Tuple[ProgressItem, ...]:
    identity = normalize_text(text).casefold()
    return tuple(item for item in items if item.text.casefold() != identity)


def merge_capture(state: WeeklyState, payload: CapturePayload) -> WeeklyState:
    goals = _upsert(state.goals, payload.goals)
    follow_up = _upsert(state.follow_up, payload.follow_up)
    day_key = payload.day.isoformat()
    day = state.days.get(day_key, DailyState())
    day = DailyState(
        completed=_upsert(day.completed, payload.completed),
        next_items=_upsert(day.next_items, payload.next_items),
        blocked=_upsert(day.blocked, payload.blocked),
    )

    for removal in payload.remove:
        if removal.section == "goals":
            goals = _remove(goals, removal.text)
        elif removal.section == "follow_up":
            follow_up = _remove(follow_up, removal.text)
        elif removal.section == "completed":
            day = replace(day, completed=_remove(day.completed, removal.text))
        elif removal.section == "next":
            day = replace(day, next_items=_remove(day.next_items, removal.text))
        elif removal.section == "blocked":
            day = replace(day, blocked=_remove(day.blocked, removal.text))

    days = dict(state.days)
    if day.completed or day.next_items or day.blocked:
        days[day_key] = day
    else:
        days.pop(day_key, None)
    summary = tuple(dict.fromkeys((*state.summary, *payload.summary)))
    return WeeklyState(
        week=state.week,
        goals=goals,
        days=days,
        follow_up=follow_up,
        summary=summary,
    )
