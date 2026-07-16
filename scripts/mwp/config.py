from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(RuntimeError):
    """Raised when local ownership configuration is invalid."""


@dataclass(frozen=True)
class AppConfig:
    version: int = 1
    timezone: str = "system"
    notes_account_name: str = "iCloud"
    notes_folder_name: str = "Weekly Progress"
    notes_folder_id: Optional[str] = None
    reminders_list_name: str = "Weekly Progress"
    reminders_list_id: Optional[str] = None
    calendar_name: str = "Weekly Progress"
    calendar_id: Optional[str] = None

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version != 1:
            raise ConfigError(f"unsupported config version: {self.version}")
        for field_name in (
            "timezone",
            "notes_account_name",
            "notes_folder_name",
            "reminders_list_name",
            "calendar_name",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"{field_name} must be a non-empty string")
            if any(ord(character) < 32 or ord(character) == 127 for character in value):
                raise ConfigError(f"{field_name} must not contain control characters")
        for field_name in ("notes_folder_id", "reminders_list_id", "calendar_id"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ConfigError(f"{field_name} must be null or a non-empty string")
            if value is not None and any(ord(character) < 32 or ord(character) == 127 for character in value):
                raise ConfigError(f"{field_name} must not contain control characters")
        if self.timezone != "system":
            try:
                ZoneInfo(self.timezone)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ConfigError(f"invalid timezone: {self.timezone}") from exc

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        allowed = {item.name for item in fields(cls)}
        unknown = set(data) - allowed
        if unknown:
            raise ConfigError(f"unknown config fields: {', '.join(sorted(unknown))}")
        try:
            config = cls(**data)
        except TypeError as exc:
            raise ConfigError(f"invalid config: {exc}") from exc
        return config


def default_config_path() -> Path:
    override = os.environ.get("MWP_CONFIG_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "manage-weekly-progress" / "config.json"


class ConfigStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or default_config_path()

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"cannot read config {self.path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError("config root must be a JSON object")
        return AppConfig.from_dict(data)

    def save(self, config: AppConfig) -> None:
        AppConfig.from_dict(asdict(config))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                delete=False,
            ) as handle:
                temp = Path(handle.name)
                os.chmod(temp, 0o600)
                handle.write(json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
        except OSError as exc:
            try:
                if temp is not None:
                    temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise ConfigError(f"cannot save config {self.path}: {exc}") from exc
