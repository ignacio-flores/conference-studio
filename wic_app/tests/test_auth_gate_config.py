from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


class AuthGateConfigTests(unittest.TestCase):
    def test_auth_gate_is_explicitly_opt_in(self) -> None:
        app_text = (APP_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("def _access_gate_required() -> bool:", app_text)
        self.assertIn("require_raw = _env_setting(APP_REQUIRE_AUTH_SETTING)", app_text)
        self.assertIn("if not require_raw:", app_text)
        self.assertIn("return False", app_text)
        self.assertIn("return parse_bool_setting(require_raw, default=False)", app_text)
        self.assertNotIn("_secret_setting(APP_REQUIRE_AUTH_SETTING)", app_text)

    def test_password_resolution_is_env_first_then_secrets(self) -> None:
        app_text = (APP_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("def _resolve_auth_password() -> str:", app_text)
        self.assertIn("configured_password = _env_setting(APP_PASSWORD_SETTING)", app_text)
        self.assertIn("return _secret_setting(APP_PASSWORD_SETTING)", app_text)
        self.assertIn("configured_password = _resolve_auth_password()", app_text)


if __name__ == "__main__":
    unittest.main()
