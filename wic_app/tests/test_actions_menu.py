from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


class ActionsMenuTests(unittest.TestCase):
    def test_actions_menu_exposes_public_bundle_publish_action(self) -> None:
        text = (APP_ROOT / "ui" / "actions.py").read_text(encoding="utf-8")
        self.assertIn("publish_public_bundle: Callable", text)
        self.assertIn("preview_public_bundle: Callable", text)
        self.assertIn('Prepare Public Bundle', text)
        self.assertIn('Preview Public Bundle', text)
        self.assertIn("bundle_path = publish_public_bundle(state)", text)
        self.assertIn("preview_details = preview_public_bundle(state)", text)
        self.assertIn("Public bundle ready:", text)
        self.assertIn("Open Public Preview", text)

    def test_app_wires_public_bundle_publish_action_into_menu(self) -> None:
        text = (APP_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("publish_public_bundle=_publish_public_bundle", text)
        self.assertIn("preview_public_bundle=_preview_public_bundle", text)


if __name__ == "__main__":
    unittest.main()
