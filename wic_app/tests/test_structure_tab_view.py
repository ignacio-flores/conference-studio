from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from reclassification_engine import parse_start_minutes, room_sort_key  # noqa: E402
from ui.structure import (  # noqa: E402
    block_filter_labels_for_day,
    build_block_filter_label,
    build_empty_slot_selection,
    build_new_room_selection,
    build_room_selection,
    build_session_selection,
    group_sessions_for_structure_matrix,
    resolve_structure_title_lines,
    structure_session_counts,
)


def _fake_session(
    *,
    session_id: str,
    session_code: str,
    session_title: str = "",
    status: str,
    day_label: str,
    block_num: int,
    block_label: str,
    time: str,
    room: str,
    capacity: int,
    papers: list[object | None],
    overflow_count: int,
) -> SimpleNamespace:
    return SimpleNamespace(
        session_id=session_id,
        session_code=session_code,
        session_title=session_title,
        status=status,
        day_label=day_label,
        block_num=block_num,
        block_label=block_label,
        time=time,
        room=room,
        capacity=capacity,
        papers=papers,
        overflow_papers=[object() for _ in range(overflow_count)],
    )


class StructureTabViewTests(unittest.TestCase):
    def test_group_sessions_for_matrix_by_day_block_and_room(self) -> None:
        sessions = [
            _fake_session(
                session_id="S1",
                session_code="D1-B1-R1",
                session_title="Inequality and Growth",
                status="active",
                day_label="Day 1",
                block_num=1,
                block_label="SESSION 1",
                time="9h30-11h00",
                room="R1",
                capacity=3,
                papers=[None, None, None],
                overflow_count=0,
            ),
            _fake_session(
                session_id="S2",
                session_code="D1-B1-R2",
                session_title="Climate and Distribution",
                status="inactive",
                day_label="Day 1",
                block_num=1,
                block_label="SESSION 1",
                time="9h30-11h00",
                room="R2",
                capacity=3,
                papers=[None, None, None],
                overflow_count=0,
            ),
            _fake_session(
                session_id="S3",
                session_code="D1-B2-R1",
                session_title="Social Mobility and Wealth",
                status="active",
                day_label="Day 1",
                block_num=2,
                block_label="SESSION 2",
                time="11h30-13h00",
                room="R1",
                capacity=3,
                papers=[None, None, None],
                overflow_count=0,
            ),
            _fake_session(
                session_id="S4",
                session_code="D2-B1-R1",
                session_title="Taxation and Redistribution",
                status="active",
                day_label="Day 2",
                block_num=1,
                block_label="SESSION 1",
                time="9h30-11h00",
                room="R1",
                capacity=3,
                papers=[None, None, None],
                overflow_count=0,
            ),
        ]

        labels = block_filter_labels_for_day(
            sessions,
            day_label="Day 1",
            status_filter="all",
            search_text="",
            parse_start_minutes_fn=parse_start_minutes,
        )
        self.assertEqual(labels, ["All blocks", "B1 | SESSION 1 | 9h30-11h00", "B2 | SESSION 2 | 11h30-13h00"])

        matrix = group_sessions_for_structure_matrix(
            sessions,
            day_label="Day 1",
            status_filter="all",
            block_filter_label="All blocks",
            search_text="",
            parse_start_minutes_fn=parse_start_minutes,
            room_sort_key_fn=room_sort_key,
        )
        self.assertEqual(matrix["rooms"], ["R1", "R2"])
        self.assertEqual(len(matrix["rows"]), 2)
        self.assertEqual(matrix["rows"][0]["display_label"], "B1 | SESSION 1 | 9h30-11h00")
        self.assertEqual(matrix["rows"][1]["display_label"], "B2 | SESSION 2 | 11h30-13h00")
        self.assertEqual(matrix["rows"][0]["sessions_by_room"]["R1"].session_id, "S1")
        self.assertEqual(matrix["rows"][0]["sessions_by_room"]["R2"].session_id, "S2")
        self.assertEqual(matrix["rows"][1]["sessions_by_room"]["R1"].session_id, "S3")
        self.assertNotIn("R2", matrix["rows"][1]["sessions_by_room"])

        matrix_active_only = group_sessions_for_structure_matrix(
            sessions,
            day_label="Day 1",
            status_filter="active",
            block_filter_label="All blocks",
            search_text="",
            parse_start_minutes_fn=parse_start_minutes,
            room_sort_key_fn=room_sort_key,
        )
        self.assertEqual(len(matrix_active_only["rows"]), 2)
        self.assertEqual(matrix_active_only["rooms"], ["R1"])

        matrix_single_block = group_sessions_for_structure_matrix(
            sessions,
            day_label="Day 1",
            status_filter="all",
            block_filter_label="B1 | SESSION 1 | 9h30-11h00",
            search_text="",
            parse_start_minutes_fn=parse_start_minutes,
            room_sort_key_fn=room_sort_key,
        )
        self.assertEqual(len(matrix_single_block["rows"]), 1)
        self.assertEqual(matrix_single_block["rows"][0]["display_label"], "B1 | SESSION 1 | 9h30-11h00")
        self.assertEqual(matrix_single_block["rooms"], ["R1", "R2"])

        matrix_title_search = group_sessions_for_structure_matrix(
            sessions,
            day_label="Day 1",
            status_filter="all",
            block_filter_label="All blocks",
            search_text="mobility",
            parse_start_minutes_fn=parse_start_minutes,
            room_sort_key_fn=room_sort_key,
        )
        self.assertEqual(len(matrix_title_search["rows"]), 1)
        self.assertEqual(matrix_title_search["rows"][0]["display_label"], "B2 | SESSION 2 | 11h30-13h00")
        self.assertEqual(matrix_title_search["rooms"], ["R1"])

    def test_block_filter_label_helper_matches_matrix_rows(self) -> None:
        self.assertEqual(build_block_filter_label(2, "SESSION 2", "11h30-13h00"), "B2 | SESSION 2 | 11h30-13h00")

    def test_structure_session_counts_and_unassigned_indicator(self) -> None:
        session = _fake_session(
            session_id="S1",
            session_code="D1-B1-R1",
            session_title="Land and Agrarian Structure",
            status="active",
            day_label="Day 1",
            block_num=1,
            block_label="SESSION 1",
            time="9h30-11h00",
            room="R1",
            capacity=4,
            papers=[object(), None, object(), None],
            overflow_count=1,
        )

        counts = structure_session_counts(session, unassigned_count=3)
        self.assertEqual(counts["filled"], 2)
        self.assertEqual(counts["capacity"], 4)
        self.assertEqual(counts["overflow"], 1)
        self.assertEqual(counts["used"], 3)
        self.assertEqual(counts["open_slots"], 2)
        self.assertEqual(counts["potential_fill"], 2)

        counts_limited = structure_session_counts(session, unassigned_count=1)
        self.assertEqual(counts_limited["potential_fill"], 1)

    def test_selection_payload_builders(self) -> None:
        session = _fake_session(
            session_id="S1",
            session_code="D1-B1-R1",
            session_title="Environmental Inequality",
            status="active",
            day_label="Day 1",
            block_num=1,
            block_label="SESSION 1",
            time="9h30-11h00",
            room="R1",
            capacity=3,
            papers=[None, None, None],
            overflow_count=0,
        )
        session_selection = build_session_selection(session)
        self.assertEqual(session_selection["kind"], "session")
        self.assertEqual(session_selection["session_id"], "S1")
        self.assertEqual(session_selection["day_label"], "Day 1")
        self.assertEqual(session_selection["block_num"], 1)
        self.assertEqual(session_selection["time_label"], "9h30-11h00")
        self.assertEqual(session_selection["room"], "R1")

        room_selection = build_room_selection(
            day_label="Day 2",
            room="R5",
        )
        self.assertEqual(room_selection["kind"], "room")
        self.assertEqual(room_selection["session_id"], "")
        self.assertEqual(room_selection["day_label"], "Day 2")
        self.assertEqual(room_selection["block_num"], 0)
        self.assertEqual(room_selection["block_label"], "")
        self.assertEqual(room_selection["time_label"], "")
        self.assertEqual(room_selection["room"], "R5")

        empty_slot_selection = build_empty_slot_selection(
            day_label="Day 3",
            block_num=2,
            block_label="SESSION 2",
            time_label="14h00-15h30",
            room="R2-01",
        )
        self.assertEqual(empty_slot_selection["kind"], "empty_slot")
        self.assertEqual(empty_slot_selection["day_label"], "Day 3")
        self.assertEqual(empty_slot_selection["block_num"], 2)
        self.assertEqual(empty_slot_selection["block_label"], "SESSION 2")
        self.assertEqual(empty_slot_selection["time_label"], "14h00-15h30")
        self.assertEqual(empty_slot_selection["room"], "R2-01")

        new_room_selection = build_new_room_selection("Day 1")
        self.assertEqual(new_room_selection["kind"], "new_room")
        self.assertEqual(new_room_selection["day_label"], "Day 1")
        self.assertEqual(new_room_selection["room"], "")

    def test_structure_tab_has_day_row_room_labels_and_lazy_advanced_gate(self) -> None:
        app_text = (APP_ROOT / "app.py").read_text(encoding="utf-8")
        structure_text = (APP_ROOT / "ui" / "structure.py").read_text(encoding="utf-8")
        self.assertIn('"Manage days"', app_text)
        self.assertIn('"Add/Delete days"', app_text)
        self.assertIn('"Add session"', app_text)
        self.assertIn('"Add room"', structure_text)
        self.assertIn('"Search SessionTitle/SessionCode/Room"', app_text)
        self.assertIn('key="structure_show_advanced_tools"', app_text)
        self.assertIn("if not show_advanced_tools:", app_text)
        self.assertIn("with st.expander(\"Advanced table editor\", expanded=False):", app_text)
        self.assertNotIn('"Hide inspector"', app_text)
        self.assertNotIn('"Show inspector"', app_text)
        self.assertIn('key="close_structure_inspector_btn"', structure_text)
        self.assertIn('st.caption("Transfer Content")', app_text)
        self.assertIn('scope_prefix="struct"', app_text)
        self.assertIn('"Transfer mode"', app_text)
        self.assertIn('f"Session papers ({counts[\'filled\']}/{counts[\'capacity\']} filled)"', app_text)
        self.assertIn("<div title='", app_text)
        self.assertIn('[!] (overflow #{overflow_idx})', app_text)
        self.assertNotIn('st.caption("Overflow papers")', app_text)
        self.assertIn("def _session_hover_help(session: object) -> str:", structure_text)
        self.assertIn("help=_session_hover_help(session)", structure_text)
        self.assertIn('[!] (overflow #{idx})', structure_text)
        self.assertNotIn("Abstract:", structure_text)
        self.assertIn("def _render_structure_tab(state, mobile_mode: bool = False) -> None:", app_text)
        self.assertIn("mobile_mode=mobile_mode", app_text)
        self.assertIn("def _render_structure_matrix_mobile(", structure_text)
        self.assertIn("mobile_mode: bool = False", structure_text)
        self.assertIn("hidden on mobile screens", app_text)

    def test_structure_tab_clears_selection_on_filter_navigation_and_transfer(self) -> None:
        app_text = (APP_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("def _clear_structure_selection_for_navigation() -> None:", app_text)
        self.assertIn('if active_tab == "Structure" and not preserve_structure_selection:', app_text)
        self.assertIn("pending_structure_session_focus", app_text)
        self.assertIn("preserve_structure_selection=True", app_text)
        self.assertGreaterEqual(app_text.count("on_change=_clear_structure_selection_for_navigation"), 6)
        self.assertIn('if filter_col2.button(', app_text)
        self.assertIn('"Add/Delete days"', app_text)
        self.assertIn('key="structure_day_tools_toggle"', app_text)
        self.assertIn("        _clear_structure_selection_for_navigation()", app_text)
        self.assertIn('if add_row_col1.button(', app_text)
        self.assertIn('"Add session"', app_text)
        self.assertIn('key=f"structure_add_row_toggle_{day_pick}"', app_text)
        self.assertIn(
            "on_success_select_target=lambda _target_session_id: _clear_structure_selection()",
            app_text,
        )

    def test_session_title_edit_saves_on_enter_and_keeps_cancel(self) -> None:
        app_text = (APP_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn(
            "def _submit_session_title_edit(session_code: str, title_draft_key: str, title_edit_mode_key: str)",
            app_text,
        )
        self.assertGreaterEqual(app_text.count("on_change=_submit_session_title_edit"), 2)
        self.assertNotIn('key=f"struct_ins_session_title_save_{session.session_id}"', app_text)
        self.assertNotIn('key=f"ins_session_title_save_{session.session_id}"', app_text)
        self.assertIn('key=f"struct_ins_session_title_cancel_{session.session_id}"', app_text)
        self.assertIn('key=f"ins_session_title_cancel_{session.session_id}"', app_text)
        self.assertIn('st.caption("Press Enter to save.")', app_text)

    def test_title_line_density_uses_two_lines_for_up_to_five_rooms(self) -> None:
        self.assertEqual(resolve_structure_title_lines(visible_room_columns=3), 2)
        self.assertEqual(resolve_structure_title_lines(visible_room_columns=5), 2)
        self.assertEqual(resolve_structure_title_lines(visible_room_columns=6), 1)


if __name__ == "__main__":
    unittest.main()
