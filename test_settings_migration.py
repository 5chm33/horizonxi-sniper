"""Pure tests for the backwards-compatible auth settings migration."""
import unittest

from settings_migration import auth_config_for_save, migrate_auth_config


class SettingsMigrationTests(unittest.TestCase):
    def test_legacy_password_is_discarded_but_username_is_kept(self):
        self.assertEqual(
            migrate_auth_config({"username": "alice", "password": "secret"}),
            {"username": "alice"},
        )

    def test_missing_or_non_string_username_is_safe(self):
        self.assertEqual(migrate_auth_config({}), {"username": ""})
        self.assertEqual(
            migrate_auth_config({"username": 123, "password": "secret"}),
            {"username": "123"},
        )

    def test_save_payload_never_contains_password(self):
        self.assertEqual(auth_config_for_save("alice"), {"username": "alice"})
        self.assertNotIn("password", auth_config_for_save("alice"))


if __name__ == "__main__":
    unittest.main()
