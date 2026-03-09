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
    clear_session,
    create_manual_talk,
    create_session,
    load_paper_placements,
    parse_programme_slots,
    remove_session,
    restore_session,
    write_paper_placements,
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


if __name__ == "__main__":
    unittest.main()
