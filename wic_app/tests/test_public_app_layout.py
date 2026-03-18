from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


class PublicAppLayoutTests(unittest.TestCase):
    def test_public_app_uses_structure_programme_and_papers_tabs(self) -> None:
        text = (APP_ROOT / "public_app.py").read_text(encoding="utf-8")
        self.assertIn('st.tabs(["Structure", "Programme", "Papers"])', text)
        self.assertNotIn('st.tabs(["Schedule", "Papers"])', text)

    def test_public_app_exposes_read_only_session_and_paper_details(self) -> None:
        text = (APP_ROOT / "public_app.py").read_text(encoding="utf-8")
        self.assertIn('st.subheader("Session details")', text)
        self.assertIn('st.subheader("Paper details")', text)
        self.assertIn("abstract_open_submission_id", text)

    def test_public_app_does_not_use_admin_inspector_language(self) -> None:
        text = (APP_ROOT / "public_app.py").read_text(encoding="utf-8")
        self.assertNotIn("Inspector", text)
        self.assertNotIn("Selection active", text)


if __name__ == "__main__":
    unittest.main()
