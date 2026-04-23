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
        self.assertIn("export_publish_docx: Callable", text)
        self.assertIn("Publish display", text)
        self.assertIn("hide rooms + moderators", text.lower())
        self.assertIn('Publish (Excel + PDF + Word)', text)
        self.assertIn('Prepare Public Bundle', text)
        self.assertIn('Preview Public Bundle', text)
        self.assertIn("publish_display = st.radio(", text)
        self.assertIn("docx_path = export_publish_docx(state, publish_display=publish_display)", text)
        self.assertIn("xlsx_path = export_publish_excel(state, publish_display=publish_display)", text)
        self.assertIn("pdf_path = export_publish_pdf(state, publish_display=publish_display)", text)
        self.assertIn("Publish Word:", text)
        self.assertIn("bundle_path = publish_public_bundle(state)", text)
        self.assertIn("preview_details = preview_public_bundle(state)", text)
        self.assertIn("Public bundle ready:", text)
        self.assertIn("Open Public Preview", text)

    def test_app_wires_public_bundle_publish_action_into_menu(self) -> None:
        text = (APP_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("publish_public_bundle=_publish_public_bundle", text)
        self.assertIn("preview_public_bundle=_preview_public_bundle", text)
        self.assertIn("export_publish_docx=export_publish_docx", text)

    def test_actions_menu_does_not_expose_draft_export(self) -> None:
        actions_text = (APP_ROOT / "ui" / "actions.py").read_text(encoding="utf-8")
        app_text = (APP_ROOT / "app.py").read_text(encoding="utf-8")

        self.assertNotIn("Export Draft", actions_text)
        self.assertNotIn("Draft exported:", actions_text)
        self.assertNotIn("path = export_draft_workbook(state)", actions_text)
        self.assertIn("export_draft_workbook: Callable | None = None", actions_text)
        self.assertIn("export_draft_workbook=None", app_text)
        self.assertNotIn("export_draft_workbook=export_draft_workbook", app_text)


if __name__ == "__main__":
    unittest.main()
