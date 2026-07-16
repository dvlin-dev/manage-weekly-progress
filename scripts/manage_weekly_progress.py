#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from zoneinfo import ZoneInfo

from mwp.apple import AppleScriptError, AppleScriptRunner, CalendarStore, NotesStore, ReminderStore
from mwp.config import ConfigError, ConfigStore
from mwp.model import CapturePayload, ValidationError, WeekRef
from mwp.note_format import ManagedRegionError, WeeklyState, merge_capture, merge_managed_region
from mwp.service import NotificationRoute, WeeklyProgressService, route_notification, state_to_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage-weekly-progress",
        description="Manage weekly progress in Apple Notes.",
    )
    parser.add_argument("--config", type=Path, help="Override the local ownership config path")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Check macOS app access and configuration")
    configure = subparsers.add_parser("configure", help="Set local names, account, or timezone")
    configure.add_argument("--timezone")
    configure.add_argument("--notes-account-name")
    configure.add_argument("--notes-folder-name")
    configure.add_argument("--reminders-list-name")
    configure.add_argument("--calendar-name")
    capture = subparsers.add_parser("capture", help="Capture or update weekly progress")
    capture.add_argument("--input", type=str, required=True, help="UTF-8 JSON file, or - for stdin")
    capture.add_argument("--dry-run", action="store_true", help="Validate and preview without Apple app writes")
    review = subparsers.add_parser("review", help="Read structured weekly progress")
    review.add_argument("--week", required=True, help="ISO week such as 2026-W29")
    rollover = subparsers.add_parser("rollover", help="Carry open items into another week")
    rollover.add_argument("--from-week", required=True, help="Source ISO week")
    rollover.add_argument("--to-week", required=True, help="Later target ISO week")
    return parser


def _read_json(path: str) -> Dict[str, Any]:
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"cannot read input {path}: {exc}") from exc
    if len(raw.encode("utf-8")) > 1_000_000:
        raise ValidationError("capture input must not exceed 1 MB")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"input is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError("capture input must be a JSON object")
    return value


def _service(config_path: Optional[Path]) -> WeeklyProgressService:
    runner = AppleScriptRunner()
    return WeeklyProgressService(
        ConfigStore(config_path),
        NotesStore(runner),
        ReminderStore(runner),
        CalendarStore(runner),
    )


def _doctor(config_path: Optional[Path]) -> tuple[int, Dict[str, Any]]:
    runner = AppleScriptRunner()
    checks: Dict[str, Dict[str, str]] = {}
    for name, store in (
        ("notes", NotesStore(runner)),
        ("reminders", ReminderStore(runner)),
        ("calendar", CalendarStore(runner)),
    ):
        try:
            store.doctor()
            checks[name] = {"status": "ok"}
        except AppleScriptError as exc:
            checks[name] = {"status": "error", "message": str(exc)}
    store = ConfigStore(config_path)
    context: Optional[Dict[str, Any]] = None
    try:
        config = store.load()
        config_status: Dict[str, Any] = {
            "status": "ok",
            "path": str(store.path),
            "notes_initialized": bool(config.notes_folder_id),
            "reminders_initialized": bool(config.reminders_list_id),
            "calendar_initialized": bool(config.calendar_id),
        }
        today = (
            date.today()
            if config.timezone == "system"
            else datetime.now(ZoneInfo(config.timezone)).date()
        )
        week = WeekRef.from_date(today, config.timezone)
        context = {
            "timezone": config.timezone,
            "today": today.isoformat(),
            "current_week": week.iso_key,
            "current_week_title": week.title,
        }
    except ConfigError as exc:
        config_status = {"status": "error", "message": str(exc)}
    notes_ok = checks["notes"]["status"] == "ok"
    config_ok = config_status["status"] == "ok"
    overall_ok = notes_ok and config_ok
    output = {"ok": overall_ok, "checks": checks, "config": config_status}
    if context is not None:
        output["context"] = context
    return (0 if output["ok"] else 1), output


def _dry_run(payload: CapturePayload) -> Dict[str, Any]:
    week = WeekRef.from_date(payload.day)
    state = merge_capture(WeeklyState.empty(week), payload)
    notifications = []
    for item in payload.all_items():
        route = route_notification(item)
        if route is not NotificationRoute.NONE:
            notifications.append({"key": item.key, "route": route.value, "status": "planned"})
    return {
        "dry_run": True,
        "week": week.iso_key,
        "title": week.title,
        "state": state_to_dict(state),
        "note_body": merge_managed_region("", state),
        "notifications": notifications,
    }


def _configure(args: argparse.Namespace) -> Dict[str, Any]:
    store = ConfigStore(args.config)
    current = store.load()
    changes: Dict[str, Any] = {}
    for field_name in (
        "timezone",
        "notes_account_name",
        "notes_folder_name",
        "reminders_list_name",
        "calendar_name",
    ):
        value = getattr(args, field_name)
        if value is not None:
            if not value.strip():
                raise ValidationError(f"{field_name} must not be empty")
            changes[field_name] = value.strip()
    if not changes:
        raise ValidationError("configure requires at least one option")
    if "timezone" in changes:
        WeekRef.from_date(date.today(), changes["timezone"])
    if changes.get("notes_folder_name") not in (None, current.notes_folder_name):
        changes["notes_folder_id"] = None
    if changes.get("reminders_list_name") not in (None, current.reminders_list_name):
        changes["reminders_list_id"] = None
    if changes.get("calendar_name") not in (None, current.calendar_name):
        changes["calendar_id"] = None
    updated = replace(current, **changes)
    store.save(updated)
    return {"ok": True, "config_path": str(store.path), "config": asdict(updated)}


def _emit(value: Dict[str, Any], stream: Any = sys.stdout) -> None:
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            code, output = _doctor(args.config)
        elif args.command == "configure":
            output = _configure(args)
            code = 0
        elif args.command == "capture":
            payload = CapturePayload.from_dict(_read_json(args.input))
            output = _dry_run(payload) if args.dry_run else _service(args.config).capture(payload).to_dict()
            code = 0
        elif args.command == "review":
            output = _service(args.config).review(args.week).to_dict()
            code = 0
        elif args.command == "rollover":
            output = _service(args.config).rollover(args.from_week, args.to_week).to_dict()
            code = 0
        else:
            raise AssertionError(f"unhandled command: {args.command}")
        _emit(output)
        return code
    except (ValidationError, json.JSONDecodeError) as exc:
        _emit({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}, sys.stderr)
        return 2
    except (ConfigError, AppleScriptError, ManagedRegionError) as exc:
        _emit({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}, sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
