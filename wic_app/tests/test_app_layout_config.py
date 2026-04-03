from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


class AppLayoutConfigTests(unittest.TestCase):
    def test_uses_state_backed_navigation_instead_of_streamlit_tabs(self) -> None:
        app_py = APP_ROOT / "app.py"
        text = app_py.read_text(encoding="utf-8")
        self.assertIn('APP_TITLE = "Conference Studio"', text)
        self.assertIn('TAB_LABELS = ["Programme", "Structure", "Paper List", "Archived", "Labels", "Checks"]', text)
        self.assertIn('key="active_tab"', text)
        self.assertNotIn("st.tabs(", text)
        self.assertNotIn("Programme-first mode: edits are auto-applied", text)
        self.assertIn('DEFAULT_CONFERENCE_LABEL = "WIC 2026"', text)
        self.assertIn("UI_SETTINGS_FILE", text)
        self.assertIn("def _load_ui_settings()", text)
        self.assertIn("def _save_conference_label", text)
        self.assertIn("LABEL_CATALOG_FILE", text)
        self.assertIn("load_label_catalog_fn=load_label_catalog", text)
        self.assertIn("write_label_catalog_fn=write_label_catalog", text)
        self.assertIn("Total accepted papers", text)
        self.assertIn("Active papers", text)
        self.assertIn("Archived papers", text)
        self.assertIn("Total accepted papers = Active papers + Archived papers", text)
        self.assertIn("Scheduled in active sessions", text)
        self.assertIn("Overflow in inactive sessions", text)
        self.assertIn(
            "Active papers = Scheduled(active) + Overflow(active) + Scheduled(inactive) + Overflow(inactive) + Unassigned",
            text,
        )
        self.assertIn("EMPTY_LABEL_SENTINEL", text)
        self.assertIn("def _classification_override_value", text)
        self.assertIn("conference_label_draft", text)
        self.assertIn('key="conference_title_edit_toggle"', text)
        self.assertIn("pills_widget = getattr(st, \"pills\", None)", text)
        self.assertIn('elif active_tab == "Archived":', text)
        self.assertIn("render_archived_tab(", text)
        self.assertIn("archive_reason_options=archive_reason_options", text)
        self.assertIn("bulk_update_archived_reason=_bulk_update_archived_reason", text)
        self.assertIn("def _init_viewport_state()", text)
        self.assertIn("MOBILE_QUERY_PARAM = \"mobile\"", text)
        self.assertIn("APP_PASSWORD_SETTING = \"APP_PASSWORD\"", text)
        self.assertIn("APP_REQUIRE_AUTH_SETTING = \"APP_REQUIRE_AUTH\"", text)
        self.assertIn("def _enforce_access_gate()", text)
        self.assertIn("def _resolve_auth_password() -> str:", text)
        self.assertIn("def _env_setting(name: str) -> str:", text)
        self.assertIn("def _secret_setting(name: str) -> str:", text)
        self.assertIn("force_mobile_mode", text)


if __name__ == "__main__":
    unittest.main()
