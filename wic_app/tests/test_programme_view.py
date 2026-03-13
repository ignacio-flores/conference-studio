from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.programme import PROGRAMME_COLUMN_OPTIONS, resolve_programme_layout_density  # noqa: E402


class ProgrammeViewTests(unittest.TestCase):
    def test_programme_column_options_include_auto_and_one_to_six(self) -> None:
        self.assertEqual(PROGRAMME_COLUMN_OPTIONS, ["Auto", "1", "2", "3", "4", "5", "6"])

    def test_auto_mode_changes_with_inspector_state(self) -> None:
        rooms_no_inspector, width_no_inspector = resolve_programme_layout_density(
            max_rooms=8,
            has_selection=False,
            columns_choice="Auto",
        )
        rooms_with_inspector, width_with_inspector = resolve_programme_layout_density(
            max_rooms=8,
            has_selection=True,
            columns_choice="Auto",
        )
        self.assertGreaterEqual(rooms_no_inspector, rooms_with_inspector)
        self.assertGreater(width_no_inspector, 0)
        self.assertGreater(width_with_inspector, 0)

    def test_manual_mode_forces_column_count_with_cap(self) -> None:
        rooms_per_row, _ = resolve_programme_layout_density(
            max_rooms=10,
            has_selection=False,
            columns_choice="5",
        )
        self.assertEqual(rooms_per_row, 5)

        capped_rooms, _ = resolve_programme_layout_density(
            max_rooms=3,
            has_selection=False,
            columns_choice="6",
        )
        self.assertEqual(capped_rooms, 3)

    def test_programme_inspector_includes_transfer_content_controls(self) -> None:
        app_text = (APP_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('scope_prefix="prog"', app_text)
        self.assertIn('"Transfer mode"', app_text)
        self.assertIn('"Transfer session to..."', app_text)
        self.assertIn("show_title=False", app_text)
        self.assertIn('"Archive reason"', app_text)
        self.assertIn("_render_archive_controls(", app_text)
        self.assertIn('kind == "overflow"', app_text)
        self.assertIn('"overflow_order"', app_text)
        self.assertIn('key=f"select_overflow_{session.session_id}_{overflow_order}"', app_text)
        self.assertIn('[!] (overflow #{overflow_order})', app_text)

    def test_programme_view_includes_mobile_dialog_and_compare_mode(self) -> None:
        app_text = (APP_ROOT / "app.py").read_text(encoding="utf-8")
        programme_text = (APP_ROOT / "ui" / "programme.py").read_text(encoding="utf-8")
        self.assertIn('@st.dialog("Programme inspector", width="large")', app_text)
        self.assertIn("mobile_mode=mobile_mode", app_text)
        self.assertIn("open_mobile_inspector_dialog", programme_text)
        self.assertIn('"Compare multiple rooms"', programme_text)
        self.assertIn("if mobile_mode and not compare_mode:", programme_text)


if __name__ == "__main__":
    unittest.main()
