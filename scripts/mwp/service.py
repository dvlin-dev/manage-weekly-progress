from __future__ import annotations

import time
from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .apple import (
    AppleNotFoundError,
    AppleScriptError,
    AppleSyncPendingError,
    CalendarStore,
    ContainerRef,
    NotesStore,
    ReminderStore,
)
from .config import AppConfig, ConfigStore
from .model import CapturePayload, ProgressItem, ValidationError, WeekRef
from .note_format import DailyState, WeeklyState, merge_capture, merge_managed_region, parse_managed_state


class NotificationRoute(str, Enum):
    NONE = "none"
    REMINDER = "reminder"
    CALENDAR = "calendar"


class NotificationStatus(str, Enum):
    SKIPPED = "skipped"
    SYNCED = "synced"
    ERROR = "error"


@dataclass(frozen=True)
class NotificationResult:
    key: str
    route: NotificationRoute
    status: NotificationStatus
    external_id: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "route": self.route.value,
            "status": self.status.value,
            "external_id": self.external_id,
            "error": self.error,
        }


@dataclass(frozen=True)
class OperationResult:
    found: bool
    state: WeeklyState
    note_id: Optional[str] = None
    notifications: Tuple[NotificationResult, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "found": self.found,
            "week": self.state.week.iso_key,
            "title": self.state.week.title,
            "note_id": self.note_id,
            "state": state_to_dict(self.state),
            "notifications": [item.to_dict() for item in self.notifications],
        }


def item_to_dict(item: ProgressItem) -> Dict[str, Any]:
    return {
        "section": item.section,
        "text": item.text,
        "key": item.key,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "end_at": item.end_at.isoformat() if item.end_at else None,
        "kind": item.kind,
    }


def state_to_dict(state: WeeklyState) -> Dict[str, Any]:
    return {
        "goals": [item_to_dict(item) for item in state.goals],
        "days": {
            day: {
                "completed": [item_to_dict(item) for item in value.completed],
                "next": [item_to_dict(item) for item in value.next_items],
                "blocked": [item_to_dict(item) for item in value.blocked],
            }
            for day, value in sorted(state.days.items())
        },
        "follow_up": [item_to_dict(item) for item in state.follow_up],
        "summary": list(state.summary),
    }


def route_notification(item: ProgressItem) -> NotificationRoute:
    if item.section not in {"goals", "next", "follow_up"}:
        return NotificationRoute.NONE
    if item.due_at is None or item.kind == "none":
        return NotificationRoute.NONE
    if item.end_at is not None or item.kind == "calendar":
        return NotificationRoute.CALENDAR
    return NotificationRoute.REMINDER


def _unique_items(items: Iterable[ProgressItem]) -> Tuple[ProgressItem, ...]:
    result: List[ProgressItem] = []
    seen: set[Tuple[str, str]] = set()
    for item in items:
        identity = (item.section, item.text.casefold())
        if identity not in seen:
            seen.add(identity)
            result.append(item)
    return tuple(result)


def _items_removed_from_state(state: WeeklyState, payload: CapturePayload) -> Tuple[ProgressItem, ...]:
    found: List[ProgressItem] = []
    day = state.days.get(payload.day.isoformat(), DailyState())
    sections = {
        "goals": state.goals,
        "completed": day.completed,
        "next": day.next_items,
        "blocked": day.blocked,
        "follow_up": state.follow_up,
    }
    for removal in payload.remove:
        identity = removal.text.casefold()
        found.extend(item for item in sections[removal.section] if item.text.casefold() == identity)
    return _unique_items(found)


class WeeklyProgressService:
    def __init__(
        self,
        config_store: ConfigStore,
        notes: NotesStore,
        reminders: ReminderStore,
        calendar: CalendarStore,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config_store = config_store
        self.notes = notes
        self.reminders = reminders
        self.calendar = calendar
        self.sleep = sleep

    def _ensure_notes_folder(self, config: AppConfig) -> Tuple[AppConfig, ContainerRef]:
        folder = self.notes.ensure_folder(
            config.notes_account_name,
            config.notes_folder_id,
            config.notes_folder_name,
        )
        updated = replace(config, notes_folder_id=folder.id, notes_folder_name=folder.name)
        if updated != config:
            self.config_store.save(updated)
        return updated, folder

    def _read_or_create(self, week: WeekRef, config: AppConfig) -> Tuple[AppConfig, ContainerRef, Any, WeeklyState]:
        config, folder = self._ensure_notes_folder(config)
        note = self.notes.read_unique(folder.id, week.title)
        if note is None:
            empty = WeeklyState.empty(week)
            note = self.notes.create(folder.id, week.title, merge_managed_region("", empty))
        state = parse_managed_state(note.body, week)
        return config, folder, note, state

    def capture(self, payload: CapturePayload) -> OperationResult:
        config = self.config_store.load()
        week = WeekRef.from_date(payload.day, config.timezone)
        config, folder, note, current = self._read_or_create(week, config)
        removed_items = _items_removed_from_state(current, payload)
        updated = merge_capture(current, payload)
        merged_body = merge_managed_region(note.body, updated)
        if merged_body != note.body:
            note = self.notes.write(folder.id, note.id, note.body, merged_body)
        verified_note = self.notes.read_by_id(folder.id, note.id)
        verified = parse_managed_state(verified_note.body, week)
        notifications = tuple(
            self.sync_notification(item, week.iso_key)
            for item in payload.all_items()
            if route_notification(item) is not NotificationRoute.NONE
        )
        closed = tuple(
            result
            for item in payload.completed
            for result in self.close_notification(item)
        )
        removed = tuple(
            result
            for item in removed_items
            for result in self.close_notification(item)
        )
        return OperationResult(True, verified, note.id, notifications + closed + removed)

    def review(self, week_key: str) -> OperationResult:
        week = WeekRef.from_iso_key(week_key)
        config = self.config_store.load()
        if not config.notes_folder_id:
            return OperationResult(False, WeeklyState.empty(week))
        note = self.notes.read_unique(config.notes_folder_id, week.title)
        if note is None:
            return OperationResult(False, WeeklyState.empty(week))
        return OperationResult(True, parse_managed_state(note.body, week), note.id)

    def rollover(self, source_week_key: str, target_week_key: str) -> OperationResult:
        source = self.review(source_week_key)
        if not source.found:
            raise ValidationError(f"source week does not exist: {source_week_key}")
        target_week = WeekRef.from_iso_key(target_week_key)
        if target_week.start <= source.state.week.start:
            raise ValidationError("target week must be later than source week")
        next_items = _unique_items(
            item
            for day in source.state.days.values()
            for item in day.next_items
        )
        blocked = _unique_items(
            item
            for day in source.state.days.values()
            for item in day.blocked
        )
        payload = CapturePayload(
            day=target_week.start,
            goals=source.state.goals,
            next_items=next_items,
            blocked=blocked,
            follow_up=source.state.follow_up,
        )
        result = self.capture(payload)

        carried_text = [item.text for item in (*source.state.goals, *next_items, *blocked, *source.state.follow_up)]
        if carried_text:
            # The summary line must stay well below the 2000-character item
            # limit, or the source note could never be parsed again.
            listing = ", ".join(carried_text)
            if len(listing) > 400:
                listing = listing[:400].rstrip(", ") + "..."
            summary = f"Rolled over to {target_week.iso_key} ({len(carried_text)} items): {listing}"
            try:
                self.capture(CapturePayload(day=source.state.week.end, summary=(summary,)))
            except AppleScriptError as exc:
                raise AppleScriptError(
                    f"open items were already carried to {target_week.iso_key}, but recording "
                    f"the rollover summary in {source.state.week.iso_key} failed; rerunning "
                    f"rollover is safe and idempotent: {exc}"
                ) from exc
        return result

    def _ensure_reminder_list(self, config: AppConfig) -> Tuple[AppConfig, ContainerRef]:
        managed_list = self.reminders.ensure_list(
            config.reminders_list_id,
            config.reminders_list_name,
        )
        updated = replace(
            config,
            reminders_list_id=managed_list.id,
            reminders_list_name=managed_list.name,
        )
        if updated != config:
            self.config_store.save(updated)
        return updated, managed_list

    def _ensure_calendar(self, config: AppConfig) -> Tuple[AppConfig, ContainerRef]:
        created_now = not config.calendar_id
        managed_calendar = self.calendar.ensure_calendar(config.calendar_id, config.calendar_name)
        updated = replace(config, calendar_id=managed_calendar.id, calendar_name=managed_calendar.name)
        if updated != config:
            self.config_store.save(updated)
        for delay in (0, 1, 2, 4, 8):
            if delay:
                self.sleep(delay)
            try:
                if self.calendar.verify_writable(managed_calendar.id):
                    return updated, managed_calendar
            except AppleNotFoundError:
                # A freshly created ownership token may not be visible to a
                # new osascript invocation yet. A token recorded earlier that
                # stops resolving means the owned calendar is gone: stop.
                if not created_now:
                    raise
        raise AppleSyncPendingError(
            "managed calendar was created but is not writable yet; retry capture later"
        )

    def sync_notification(self, item: ProgressItem, week_key: str) -> NotificationResult:
        route = route_notification(item)
        if route is NotificationRoute.NONE:
            return NotificationResult(item.key, route, NotificationStatus.SKIPPED)
        source = f"week:{week_key}\nsection:{item.section}\ntext:{item.text}"
        try:
            config = self.config_store.load()
            if route is NotificationRoute.REMINDER:
                config, managed_list = self._ensure_reminder_list(config)
                external_id = self.reminders.upsert(
                    managed_list.id,
                    item.key,
                    item.text,
                    source,
                    item.due_at,
                )
            else:
                if item.end_at is None:
                    raise ValidationError("calendar notification requires end_at")
                config, managed_calendar = self._ensure_calendar(config)
                external_id = self.calendar.upsert(
                    managed_calendar.id,
                    item.key,
                    item.text,
                    source,
                    item.due_at,
                    item.end_at,
                )
            return NotificationResult(item.key, route, NotificationStatus.SYNCED, external_id)
        except (AppleScriptError, ValidationError) as exc:
            return NotificationResult(item.key, route, NotificationStatus.ERROR, error=str(exc))

    def close_notification(self, item: ProgressItem) -> Tuple[NotificationResult, ...]:
        config = self.config_store.load()
        results: List[NotificationResult] = []
        if config.reminders_list_id:
            try:
                external_id = self.reminders.complete(config.reminders_list_id, item.key)
                if external_id != "MISSING":
                    results.append(
                        NotificationResult(item.key, NotificationRoute.REMINDER, NotificationStatus.SYNCED, external_id)
                    )
            except AppleScriptError as exc:
                results.append(
                    NotificationResult(item.key, NotificationRoute.REMINDER, NotificationStatus.ERROR, error=str(exc))
                )
        if config.calendar_id:
            try:
                external_id = self.calendar.delete_event(config.calendar_id, item.key)
                if external_id != "MISSING":
                    results.append(
                        NotificationResult(item.key, NotificationRoute.CALENDAR, NotificationStatus.SYNCED, external_id)
                    )
            except AppleScriptError as exc:
                results.append(
                    NotificationResult(item.key, NotificationRoute.CALENDAR, NotificationStatus.ERROR, error=str(exc))
                )
        return tuple(results)
