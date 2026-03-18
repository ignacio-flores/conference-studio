from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


class PublicAppConfigTests(unittest.TestCase):
    def test_public_app_requires_explicit_enable_flag(self) -> None:
        app_text = (APP_ROOT / "public_app.py").read_text(encoding="utf-8")
        self.assertIn('PUBLIC_ENABLED_SETTING = "PUBLIC_ENABLED"', app_text)
        self.assertIn("def _public_release_enabled() -> bool:", app_text)
        self.assertIn("enabled_raw = _env_setting(PUBLIC_ENABLED_SETTING)", app_text)
        self.assertIn("if not enabled_raw:", app_text)
        self.assertIn("return False", app_text)

    def test_public_app_loads_only_public_snapshot(self) -> None:
        app_text = (APP_ROOT / "public_app.py").read_text(encoding="utf-8")
        self.assertIn("from public_data import", app_text)
        self.assertIn("load_public_payload", app_text)
        self.assertNotIn("build_programme_state", app_text)
        self.assertNotIn("write_", app_text)


if __name__ == "__main__":
    unittest.main()
