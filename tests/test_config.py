from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from scripts.mwp.config import AppConfig, ConfigError, ConfigStore


class ConfigStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "nested" / "config.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_save_replaces_config_atomically(self) -> None:
        store = ConfigStore(self.path)
        store.save(AppConfig(notes_folder_id="folder-1"))

        self.assertEqual(store.load().notes_folder_id, "folder-1")
        self.assertFalse(self.path.with_suffix(".tmp").exists())

    def test_save_restricts_config_permissions_to_current_user(self) -> None:
        ConfigStore(self.path).save(AppConfig(notes_folder_id="folder-1"))

        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_unknown_config_field_is_rejected(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"mystery": True}), encoding="utf-8")

        with self.assertRaisesRegex(ConfigError, "unknown"):
            ConfigStore(self.path).load()

    def test_invalid_config_types_are_rejected(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"notes_folder_id": 123}), encoding="utf-8")

        with self.assertRaisesRegex(ConfigError, "notes_folder_id"):
            ConfigStore(self.path).load()

    def test_invalid_timezone_is_rejected(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"timezone": "Mars/Olympus"}), encoding="utf-8")

        with self.assertRaisesRegex(ConfigError, "timezone"):
            ConfigStore(self.path).load()

    def test_container_names_reject_control_characters(self) -> None:
        with self.assertRaisesRegex(ConfigError, "notes_folder_name"):
            AppConfig(notes_folder_name="unsafe\u0000name")

        with self.assertRaisesRegex(ConfigError, "calendar_id"):
            AppConfig(calendar_id="unsafe\u0000id")

    def test_missing_config_returns_defaults(self) -> None:
        config = ConfigStore(self.path).load()

        self.assertEqual(config.notes_folder_name, "Weekly Progress")
        self.assertEqual(config.timezone, "system")


if __name__ == "__main__":
    unittest.main()
