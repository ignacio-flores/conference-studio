from __future__ import annotations

import copy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from engine.config import load_conference_config
from exporters.publish import export_draft_workbook, export_publish_excel, export_publish_pdf
from reclassification_engine import (
    CLASSIFICATION_OVERRIDES_FILE,
    MANUAL_TALKS_FILE,
    PAPER_PLACEMENTS_FILE,
    PROGRAMME_FILE,
    PROGRAMME_LAYOUT_OVERRIDES_FILE,
    SESSION_NAME_OVERRIDES_FILE,
    SESSION_STRUCTURE_FILE,
    SUBMISSIONS_FILE,
    add_room_session,
    build_programme_state,
    bulk_add_room_sessions,
    clear_session,
    create_manual_talk,
    create_session,
    load_paper_placements,
    load_session_structure_rows,
    parse_programme_slots,
    remove_session,
    restore_session,
    update_session_structure_row,
    write_paper_placements,
    write_session_name_overrides,
    write_session_structure_rows,
)


class EngineTests(unittest.TestCase):
    def _temp_state_paths(self, root: Path) -> dict:
        state_dir = root / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return {
            "classification": state_dir / "classification_overrides.csv",
            "session_names": state_dir / "session_name_overrides.csv",
            "layout": state_dir / "programme_layout_overrides.csv",
            "structure": state_dir / "session_structure.csv",
            "placements": state_dir / "paper_placements.csv",
            "manual": state_dir / "manual_talks.csv",
        }

    def _build_state(self, paths: dict, submissions: Path, programme: Path):
        return build_programme_state(
            submissions_path=submissions,
            programme_path=programme,
            classification_overrides_path=paths["classification"],
            session_name_overrides_path=paths["session_names"],
            programme_layout_overrides_path=paths["layout"],
            session_structure_path=paths["structure"],
            paper_placements_path=paths["placements"],
            manual_talks_path=paths["manual"],
        )

    def test_default_config_parity(self) -> None:
        config = load_conference_config()
        self.assertEqual(config.validation.expected_slots, 75)
        self.assertEqual(config.validation.expected_reserve_slots, 3)
        self.assertEqual(config.structure.default_session_duration_min, 90)
        self.assertEqual(len(config.days), 3)
        self.assertIn("Factors contributing to income inequalities", config.themes.order)

    def test_parse_programme_slots_expected_count(self) -> None:
        config = load_conference_config()
        slots = parse_programme_slots(PROGRAMME_FILE, config)
        self.assertEqual(len(slots), config.validation.expected_slots)

    def test_layout_override_conflict_moves_to_overflow(self) -> None:
        state = build_programme_state()
        papers = copy.deepcopy(state.papers)
        sessions = copy.deepcopy(state.sessions)

        target_session = next(
            session for session in sessions if session.papers[0] is not None and session.papers[1] is not None
        )
        sid_occupied = target_session.papers[0].submission_id
        sid_moved = target_session.papers[1].submission_id

        from engine.scheduling import apply_programme_layout_overrides

        _, conflicts = apply_programme_layout_overrides(
            papers,
            sessions,
            {
                sid_moved: {
                    "SubmissionID": sid_moved,
                    "PlacementStatus": "scheduled",
                    "SessionCode": target_session.session_code,
                    "TalkIndex": "1",
                    "OverflowOrder": "",
                }
            },
        )

        self.assertTrue(conflicts, "Expected slot conflict when target slot is occupied.")
        moved_paper = next(p for p in papers if p.submission_id == sid_moved)
        self.assertEqual(moved_paper.placement_status, "overflow")
        self.assertEqual(target_session.papers[0].submission_id, sid_occupied)

    def test_validation_happy_path(self) -> None:
        state = build_programme_state()
        self.assertTrue(state.validations["hard_constraints_ok"])
        self.assertTrue(state.validations["is_valid"])

    def test_exports_smoke(self) -> None:
        state = build_programme_state()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = export_draft_workbook(state, tmp_path / "draft.xlsx")
            publish_xlsx_path = export_publish_excel(state, tmp_path / "publish.xlsx")
            self.assertTrue(draft_path.exists())
            self.assertTrue(publish_xlsx_path.exists())
            self.assertGreater(draft_path.stat().st_size, 0)
            self.assertGreater(publish_xlsx_path.stat().st_size, 0)

            try:
                publish_pdf_path = export_publish_pdf(state, tmp_path / "publish.pdf")
            except RuntimeError:
                return
            self.assertTrue(publish_pdf_path.exists())
            self.assertGreater(publish_pdf_path.stat().st_size, 0)

    def test_session_lifecycle_clear_remove_restore_create_add_room(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            for src, key in [
                (CLASSIFICATION_OVERRIDES_FILE, "classification"),
                (SESSION_NAME_OVERRIDES_FILE, "session_names"),
                (PROGRAMME_LAYOUT_OVERRIDES_FILE, "layout"),
                (SESSION_STRUCTURE_FILE, "structure"),
                (PAPER_PLACEMENTS_FILE, "placements"),
                (MANUAL_TALKS_FILE, "manual"),
            ]:
                if src.exists():
                    shutil.copy2(src, paths[key])

            state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            target = next(session for session in state.sessions if any(paper is not None for paper in session.papers))
            target_session_id = target.session_id

            clear_result = clear_session(target_session_id, paper_placements_path=paths["placements"])
            self.assertTrue(clear_result.get("ok", False))
            state_after_clear = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            cleared_session = next(session for session in state_after_clear.sessions if session.session_id == target_session_id)
            self.assertTrue(all(paper is None for paper in cleared_session.papers))
            self.assertEqual(len(cleared_session.overflow_papers), 0)

            remove_result = remove_session(
                target_session_id,
                session_structure_path=paths["structure"],
                paper_placements_path=paths["placements"],
            )
            self.assertTrue(remove_result.get("ok", False))
            state_after_remove = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            self.assertNotIn(target_session_id, {session.session_id for session in state_after_remove.sessions})
            self.assertIn(target_session_id, {session.session_id for session in state_after_remove.inactive_sessions})

            restore_result = restore_session(
                target_session_id,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(restore_result.get("ok", False))
            state_after_restore = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            self.assertIn(target_session_id, {session.session_id for session in state_after_restore.sessions})

            create_result = create_session(
                day_label=target.day_label,
                block_label=target.block_label,
                time_label=target.time,
                room="TEST-ROOM-A",
                capacity=5,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(create_result.get("ok", False))

            add_room_result = add_room_session(
                day_label=target.day_label,
                block_label=target.block_label,
                time_label=target.time,
                room="TEST-ROOM-B",
                capacity=4,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(add_room_result.get("ok", False))

            final_state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            session_ids = {session.session_id for session in final_state.sessions}
            self.assertIn(create_result["session_id"], session_ids)
            self.assertIn(add_room_result["session_id"], session_ids)

    def test_from_scratch_manual_talks_and_capacity_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            missing_submissions = tmp_path / "missing_submissions.xlsx"
            missing_programme = tmp_path / "missing_programme.xlsx"

            empty_state = self._build_state(paths, submissions=missing_submissions, programme=missing_programme)
            self.assertEqual(len(empty_state.sessions), 0)

            create_result = create_session(
                day_label="Day 1 (4th June)",
                block_label="SESSION X",
                time_label="9h00-10h00",
                room="R-FROM-SCRATCH",
                capacity=3,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(create_result.get("ok", False))
            session_id = create_result["session_id"]

            manual_ids = []
            for idx in range(1, 5):
                talk_result = create_manual_talk(
                    full_name=f"Manual Presenter {idx}",
                    title=f"Manual Talk {idx}",
                    manual_talks_path=paths["manual"],
                    paper_placements_path=paths["placements"],
                )
                self.assertTrue(talk_result.get("ok", False))
                manual_ids.append(talk_result["submission_id"])

            placements = load_paper_placements(paths["placements"])
            for idx, sid in enumerate(manual_ids, start=1):
                placements[sid] = {
                    "SubmissionID": sid,
                    "PlacementStatus": "scheduled",
                    "SessionId": session_id,
                    "TalkIndex": str(idx),
                    "OverflowOrder": "",
                    "UpdatedAt": "2026-01-01T00:00:00",
                }
            write_paper_placements(placements.values(), paths["placements"])

            state = self._build_state(paths, submissions=missing_submissions, programme=missing_programme)
            target = next(session for session in state.sessions if session.session_id == session_id)
            self.assertEqual(sum(1 for paper in target.papers if paper is not None), 3)
            self.assertEqual(len(target.overflow_papers), 1)
            occupied_ranges = [(paper.talk_start_min, paper.talk_end_min) for paper in target.papers if paper is not None]
            self.assertEqual(occupied_ranges, [(540, 560), (560, 580), (580, 600)])

    def test_legacy_layout_auto_migration_to_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            if PROGRAMME_LAYOUT_OVERRIDES_FILE.exists():
                shutil.copy2(PROGRAMME_LAYOUT_OVERRIDES_FILE, paths["layout"])

            self.assertFalse(paths["structure"].exists())
            self.assertFalse(paths["placements"].exists())

            state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            self.assertGreater(len(state.sessions), 0)
            self.assertTrue(paths["structure"].exists())
            self.assertTrue(paths["placements"].exists())

            placements_first = load_paper_placements(paths["placements"])
            self.assertGreater(len(placements_first), 0)
            state_second = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            placements_second = load_paper_placements(paths["placements"])
            self.assertEqual(len(placements_first), len(placements_second))
            self.assertEqual(len(state.papers), len(state_second.papers))
            backups = list(paths["layout"].parent.glob("programme_layout_overrides.csv.bak.*"))
            self.assertTrue(backups)

    def test_template_duration_repair_is_idempotent_and_manual_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            for src, key in [
                (CLASSIFICATION_OVERRIDES_FILE, "classification"),
                (SESSION_NAME_OVERRIDES_FILE, "session_names"),
                (PROGRAMME_LAYOUT_OVERRIDES_FILE, "layout"),
                (SESSION_STRUCTURE_FILE, "structure"),
                (PAPER_PLACEMENTS_FILE, "placements"),
                (MANUAL_TALKS_FILE, "manual"),
            ]:
                if src.exists():
                    shutil.copy2(src, paths[key])

            manual_result = create_session(
                day_label="Day 1 (4th June)",
                block_label="MANUAL DURATION",
                time_label="20h00-20h45",
                room="MANUAL-DUR",
                capacity=3,
                source="manual",
                session_structure_path=paths["structure"],
            )
            self.assertTrue(manual_result.get("ok", False))
            manual_id = manual_result["session_id"]

            state_first = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            self.assertGreater(len(state_first.sessions), 0)
            rows_after_first = load_session_structure_rows(paths["structure"])
            template_durations = []
            for row in rows_after_first.values():
                if str(row.get("Source", "")).strip().lower() != "template":
                    continue
                start_min = int(row.get("StartMin", "0") or 0)
                end_min = int(row.get("EndMin", "0") or 0)
                template_durations.append(end_min - start_min)
            self.assertTrue(template_durations)
            self.assertTrue(all(duration == 90 for duration in template_durations))

            manual_row = rows_after_first[manual_id]
            manual_duration = int(manual_row.get("EndMin", "0")) - int(manual_row.get("StartMin", "0"))
            self.assertEqual(manual_duration, 45)

            state_second = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            self.assertEqual(len(state_first.sessions), len(state_second.sessions))
            rows_after_second = load_session_structure_rows(paths["structure"])
            self.assertEqual(rows_after_first, rows_after_second)

    def test_duration_update_recomputes_talk_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            for src, key in [
                (CLASSIFICATION_OVERRIDES_FILE, "classification"),
                (SESSION_NAME_OVERRIDES_FILE, "session_names"),
                (PROGRAMME_LAYOUT_OVERRIDES_FILE, "layout"),
                (SESSION_STRUCTURE_FILE, "structure"),
                (PAPER_PLACEMENTS_FILE, "placements"),
                (MANUAL_TALKS_FILE, "manual"),
            ]:
                if src.exists():
                    shutil.copy2(src, paths[key])

            state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            target = next(session for session in state.sessions if sum(1 for paper in session.papers if paper is not None) >= 3)
            new_end = target.start_min + 120
            update_result = update_session_structure_row(
                target.session_id,
                {"EndMin": str(new_end), "TimeLabel": f"{target.time}"},
                session_structure_path=paths["structure"],
            )
            self.assertTrue(update_result.get("ok", False))

            refreshed = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            updated = next(session for session in refreshed.sessions if session.session_id == target.session_id)
            self.assertEqual(updated.end_min - updated.start_min, 120)
            talk_lengths = [paper.talk_end_min - paper.talk_start_min for paper in updated.papers if paper is not None]
            self.assertTrue(talk_lengths)
            self.assertTrue(all(length == 30 for length in talk_lengths))

    def test_bulk_add_room_sessions_defaults_and_collision_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            for src, key in [
                (CLASSIFICATION_OVERRIDES_FILE, "classification"),
                (SESSION_NAME_OVERRIDES_FILE, "session_names"),
                (PROGRAMME_LAYOUT_OVERRIDES_FILE, "layout"),
                (SESSION_STRUCTURE_FILE, "structure"),
                (PAPER_PLACEMENTS_FILE, "placements"),
                (MANUAL_TALKS_FILE, "manual"),
            ]:
                if src.exists():
                    shutil.copy2(src, paths[key])

            rows = load_session_structure_rows(paths["structure"])
            day_labels = sorted({row["DayLabel"] for row in rows.values() if row.get("DayLabel", "")})
            block_signatures = sorted(
                {
                    f"{int(row.get('BlockNum', '0') or 0)}::{row.get('BlockLabel', '')}::{row.get('TimeLabel', '')}"
                    for row in rows.values()
                    if int(row.get("BlockNum", "0") or 0) > 0 and str(row.get("TimeLabel", "")).strip()
                }
            )
            self.assertTrue(day_labels)
            self.assertTrue(block_signatures)

            bulk_result = bulk_add_room_sessions(
                room="BULK-ROOM",
                capacity=4,
                day_labels=day_labels,
                block_signatures=block_signatures,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(bulk_result.get("ok", False))
            created_first_run = int(bulk_result.get("created", 0) or 0)
            self.assertGreater(created_first_run, 0)

            rerun_result = bulk_add_room_sessions(
                room="BULK-ROOM",
                capacity=4,
                day_labels=day_labels,
                block_signatures=block_signatures,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(rerun_result.get("ok", False))
            self.assertEqual(int(rerun_result.get("created", 0) or 0), 0)
            self.assertGreaterEqual(int(rerun_result.get("skipped_active", 0) or 0), created_first_run)

            rows_after = load_session_structure_rows(paths["structure"])
            created_codes = list(rerun_result.get("skipped_active_codes", []))
            self.assertTrue(created_codes)
            target_code = created_codes[0]
            target_row = next((row for row in rows_after.values() if row.get("SessionCode", "") == target_code), None)
            self.assertIsNotNone(target_row)
            target_row["Status"] = "inactive"
            write_session_structure_rows(rows_after.values(), paths["structure"])

            third_result = bulk_add_room_sessions(
                room="BULK-ROOM",
                capacity=4,
                day_labels=day_labels,
                block_signatures=block_signatures,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(third_result.get("ok", False))
            self.assertGreaterEqual(int(third_result.get("skipped_inactive", 0) or 0), 1)

    def test_session_name_override_clear_restores_auto_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            for src, key in [
                (CLASSIFICATION_OVERRIDES_FILE, "classification"),
                (SESSION_NAME_OVERRIDES_FILE, "session_names"),
                (PROGRAMME_LAYOUT_OVERRIDES_FILE, "layout"),
                (SESSION_STRUCTURE_FILE, "structure"),
                (PAPER_PLACEMENTS_FILE, "placements"),
                (MANUAL_TALKS_FILE, "manual"),
            ]:
                if src.exists():
                    shutil.copy2(src, paths[key])

            state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            session = state.sessions[0]
            original_title = session.session_title
            custom_title = f"{original_title} (Custom)"

            write_session_name_overrides({session.session_code: custom_title}, paths["session_names"])
            state_custom = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            changed = next(s for s in state_custom.sessions if s.session_code == session.session_code)
            self.assertEqual(changed.session_title, custom_title)

            write_session_name_overrides({}, paths["session_names"])
            state_reset = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            reset = next(s for s in state_reset.sessions if s.session_code == session.session_code)
            self.assertNotEqual(reset.session_title, custom_title)


if __name__ == "__main__":
    unittest.main()
