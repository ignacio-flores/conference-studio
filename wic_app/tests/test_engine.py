from __future__ import annotations

import copy
import json
import re
import shutil
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from engine.config import load_conference_config
from engine.validation import validate_programme_state
from exporters.publish import (
    PUBLISH_DISPLAY_PUBLIC_SAFE,
    PROGRAMME_CHANGE_NOTICE,
    export_draft_workbook,
    export_public_excel,
    export_public_payload,
    export_publish_docx,
    export_publish_excel,
    export_publish_pdf,
)
from ui.structure_time import build_time_label
from reclassification_engine import (
    CLASSIFICATION_OVERRIDES_FILE,
    MANUAL_TALKS_FILE,
    PAPER_ARCHIVE_OVERRIDES_FILE,
    PAPER_METADATA_OVERRIDES_FILE,
    PAPER_PLACEMENTS_FILE,
    PROGRAMME_FILE,
    PROGRAMME_LAYOUT_OVERRIDES_FILE,
    SESSION_NAME_OVERRIDES_FILE,
    SESSION_STRUCTURE_FILE,
    SUBMISSIONS_FILE,
    add_room_session,
    add_block_row_sessions,
    build_programme_state,
    bulk_add_room_sessions,
    clear_day_sessions,
    clear_session,
    clone_day_structure,
    create_manual_talk,
    create_session,
    delete_day_sessions,
    load_paper_placements,
    load_paper_metadata_overrides,
    load_paper_archive_overrides,
    load_session_structure_rows,
    load_session_name_overrides,
    parse_programme_slots,
    relabel_day_sessions,
    rename_room_for_day,
    remove_session,
    restore_session,
    transfer_session_content,
    update_session_structure_row,
    write_paper_placements,
    write_paper_metadata_overrides,
    write_paper_archive_overrides,
    write_session_name_overrides,
    write_session_structure_rows,
)


class EngineTests(unittest.TestCase):
    def _simple_publish_state(self) -> SimpleNamespace:
        paper_1 = SimpleNamespace(
            submission_id="P1",
            full_name="Presenter One",
            title="Title One",
            abstract="Abstract One",
            link_to_pdf="https://example.org/p1.pdf",
            primary_theme="Theme A",
            detailed_subtheme="Subtheme A",
            session_code="S1",
            session_title="Session One",
            day_label="Day 1 (4th June)",
            day_num=1,
            time="10h00-11h00",
            block_label="SESSION 1",
            block_num=1,
            room="R1",
        )
        paper_2 = SimpleNamespace(
            submission_id="P2",
            full_name="Presenter Two",
            title="Title Two",
            abstract="Abstract Two",
            link_to_pdf="https://example.org/p2.pdf",
            primary_theme="Theme B",
            detailed_subtheme="Subtheme B",
            session_code="S1",
            session_title="Session One",
            day_label="Day 1 (4th June)",
            day_num=1,
            time="10h00-11h00",
            block_label="SESSION 1",
            block_num=1,
            room="R1",
        )
        session = SimpleNamespace(
            session_id="S1",
            session_code="S1",
            day_label="Day 1 (4th June)",
            day_num=1,
            time="10h00-11h00",
            block_label="SESSION 1",
            block_num=1,
            room="R1",
            start_min=600,
            end_min=660,
            capacity=2,
            session_title="Session One",
            primary_theme="Theme A",
            subtheme="Subtheme A",
            papers=[paper_1, paper_2],
            overflow_papers=[],
        )
        return SimpleNamespace(
            papers=[paper_1, paper_2],
            sessions=[session],
            inactive_sessions=[],
            unassigned_papers=[],
            slot_conflicts=[],
            validations={
                "scheduled_papers": 2,
                "overflow_papers": 0,
                "unassigned_papers": 0,
                "reserve_slots": 0,
                "accepted_papers": 2,
            },
        )

    def _temp_state_paths(self, root: Path) -> dict:
        state_dir = root / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return {
            "classification": state_dir / "classification_overrides.csv",
            "session_names": state_dir / "session_name_overrides.csv",
            "layout": state_dir / "programme_layout_overrides.csv",
            "structure": state_dir / "session_structure.csv",
            "placements": state_dir / "paper_placements.csv",
            "metadata": state_dir / "paper_metadata_overrides.csv",
            "archive": state_dir / "paper_archive_overrides.csv",
            "manual": state_dir / "manual_talks.csv",
        }

    def _zip_text(self, archive_path: Path, suffixes: tuple[str, ...]) -> str:
        with zipfile.ZipFile(archive_path) as archive:
            return "\n".join(
                archive.read(name).decode("utf-8", errors="ignore")
                for name in archive.namelist()
                if name.endswith(suffixes)
            )

    def _build_state(self, paths: dict, submissions: Path, programme: Path):
        return build_programme_state(
            submissions_path=submissions,
            programme_path=programme,
            classification_overrides_path=paths["classification"],
            session_name_overrides_path=paths["session_names"],
            programme_layout_overrides_path=paths["layout"],
            session_structure_path=paths["structure"],
            paper_placements_path=paths["placements"],
            paper_metadata_overrides_path=paths["metadata"],
            paper_archive_overrides_path=paths["archive"],
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
        self.assertEqual(
            state.validations["is_valid"],
            state.validations["hard_constraints_ok"] and not state.validations["has_planning_issues"],
        )

    def test_validate_programme_state_marks_clean_plan_valid(self) -> None:
        config = load_conference_config()
        paper = SimpleNamespace(submission_id="P1", reviewed=True)
        session = SimpleNamespace(
            session_code="D1-B1-R1",
            day_num=2,
            time="11h15-12h45",
            block_label="SESSION 1",
            room="R1",
            capacity=1,
            papers=[paper],
            overflow_papers=[],
        )
        state = SimpleNamespace(
            papers=[paper],
            sessions=[session],
            inactive_sessions=[],
            unassigned_papers=[],
            slot_conflicts=[],
        )

        validations = validate_programme_state(state, config)

        self.assertTrue(validations["hard_constraints_ok"])
        self.assertFalse(validations["has_planning_issues"])
        self.assertTrue(validations["is_valid"])

    def test_exports_smoke(self) -> None:
        state = build_programme_state()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_path = export_draft_workbook(state, tmp_path / "draft.xlsx")
            public_xlsx_path = export_public_excel(state, tmp_path / "public.xlsx")
            public_payload_path = export_public_payload(state, tmp_path / "programme.json")
            publish_xlsx_path = export_publish_excel(state, tmp_path / "publish.xlsx")
            try:
                publish_docx_path = export_publish_docx(state, tmp_path / "publish.docx")
            except RuntimeError as exc:
                self.skipTest(str(exc))
            self.assertTrue(draft_path.exists())
            self.assertTrue(public_xlsx_path.exists())
            self.assertTrue(public_payload_path.exists())
            self.assertTrue(publish_xlsx_path.exists())
            self.assertTrue(publish_docx_path.exists())
            self.assertGreater(draft_path.stat().st_size, 0)
            self.assertGreater(public_xlsx_path.stat().st_size, 0)
            self.assertGreater(public_payload_path.stat().st_size, 0)
            self.assertGreater(publish_xlsx_path.stat().st_size, 0)
            self.assertGreater(publish_docx_path.stat().st_size, 0)
            payload = json.loads(public_payload_path.read_text(encoding="utf-8"))
            if payload["papers"]:
                first_paper = payload["papers"][0]
                self.assertNotIn("email", first_paper)
                self.assertNotIn("reviewer_score", first_paper)
                self.assertNotIn("link_to_pdf", first_paper)
                self.assertIn("display_presenter", first_paper)
                self.assertIn("display_room", first_paper)
                self.assertIn("paper_url", first_paper)
            self.assertEqual(payload["public_settings"]["publish_display"], "full")
            self.assertTrue(payload["public_settings"]["show_rooms"])
            self.assertTrue(payload["public_settings"]["show_moderators"])
            self.assertFalse(payload["public_settings"]["show_links"])
            workbook_text = self._zip_text(public_xlsx_path, (".xml",))
            self.assertNotIn("LinkToPDF", workbook_text)
            self.assertNotIn("Open PDF", workbook_text)

            try:
                publish_pdf_path = export_publish_pdf(state, tmp_path / "publish.pdf")
            except RuntimeError:
                return
            self.assertTrue(publish_pdf_path.exists())
            self.assertGreater(publish_pdf_path.stat().st_size, 0)

    def test_publish_workbook_is_session_centered_without_theme_or_link_metadata(self) -> None:
        state = self._simple_publish_state()
        with tempfile.TemporaryDirectory() as tmp:
            publish_xlsx_path = export_publish_excel(state, Path(tmp) / "publish.xlsx")

            workbook_xml = self._zip_text(publish_xlsx_path, (".xml", ".rels"))
            visible_text_xml = self._zip_text(publish_xlsx_path, ("sharedStrings.xml",))

        self.assertNotIn("PrimaryTheme", workbook_xml)
        self.assertNotIn("Subtheme", workbook_xml)
        self.assertNotIn("LinkToPDF", workbook_xml)
        self.assertNotIn("Publish Programme", workbook_xml)
        self.assertNotIn("This publish workbook contains schedule-ready information without abstract body text.", workbook_xml)
        self.assertNotIn("https://example.org", workbook_xml)
        self.assertIn("plenary sessions programme", workbook_xml)
        self.assertIn("https://inequalitylab.world/www-site/uploads/2026/04/2026-WIC-Programme.pdf", workbook_xml)
        self.assertNotIn("10h00-10h30", workbook_xml)
        self.assertNotIn("10h30-11h00", workbook_xml)
        self.assertNotIn("10:00-10:30", workbook_xml)
        self.assertNotIn("10:30-11:00", workbook_xml)
        self.assertNotIn("Session Directory", workbook_xml)
        self.assertNotIn("Paper Index", workbook_xml)
        self.assertNotIn("Issues", workbook_xml)
        self.assertNotIn("Title Presenter Index", workbook_xml)
        self.assertIn("10:00-11:00", visible_text_xml)
        self.assertIn("Title One", workbook_xml)
        self.assertLess(workbook_xml.index("Title One"), workbook_xml.index("Presenter One"))
        self.assertNotIn("Presenter One - Title One", workbook_xml)

    def test_publish_workbook_public_safe_hides_rooms_and_moderator_labels_and_adds_notice(self) -> None:
        state = self._simple_publish_state()
        state.papers[0].is_moderator = True
        with tempfile.TemporaryDirectory() as tmp:
            publish_xlsx_path = export_publish_excel(
                state,
                Path(tmp) / "publish_public_safe.xlsx",
                publish_display=PUBLISH_DISPLAY_PUBLIC_SAFE,
            )

            workbook_xml = self._zip_text(publish_xlsx_path, (".xml", ".rels"))
            visible_text_xml = self._zip_text(publish_xlsx_path, ("sharedStrings.xml",))

        self.assertIn(PROGRAMME_CHANGE_NOTICE, visible_text_xml)
        self.assertIn("Track 1", visible_text_xml)
        self.assertNotIn("Session Directory", workbook_xml)
        self.assertNotIn("Paper Index", workbook_xml)
        self.assertNotIn("Issues", workbook_xml)
        self.assertNotIn("Title Presenter Index", workbook_xml)
        self.assertNotIn(" (Chair)", workbook_xml)
        self.assertNotIn(">R1<", workbook_xml)
        self.assertNotIn(">S1<", workbook_xml)
        self.assertNotIn("S1", visible_text_xml)

    def test_publish_workbook_can_include_links_when_enabled(self) -> None:
        state = self._simple_publish_state()
        with tempfile.TemporaryDirectory() as tmp:
            publish_xlsx_path = export_publish_excel(
                state,
                Path(tmp) / "publish_with_links.xlsx",
                show_links=True,
            )

            workbook_xml = self._zip_text(publish_xlsx_path, (".xml", ".rels"))
            visible_text_xml = self._zip_text(publish_xlsx_path, ("sharedStrings.xml",))

        self.assertNotIn("PaperURL", visible_text_xml)
        self.assertNotIn("https://example.org/p1.pdf", workbook_xml)
        self.assertNotIn("https://example.org/p2.pdf", workbook_xml)
        self.assertNotIn("Paper Index", workbook_xml)

    def test_public_workbook_uses_public_safe_display_and_can_keep_public_links(self) -> None:
        state = self._simple_publish_state()
        state.papers[0].is_moderator = True
        with tempfile.TemporaryDirectory() as tmp:
            public_xlsx_path = export_public_excel(
                state,
                Path(tmp) / "public.xlsx",
                publish_display=PUBLISH_DISPLAY_PUBLIC_SAFE,
                show_links=True,
            )

            workbook_xml = self._zip_text(public_xlsx_path, (".xml", ".rels"))
            visible_text_xml = self._zip_text(public_xlsx_path, ("sharedStrings.xml",))

        self.assertIn("Public settings: rooms=hidden, moderators=hidden, links=shown", visible_text_xml)
        self.assertIn("PaperURL", visible_text_xml)
        self.assertIn("https://example.org/p1.pdf", workbook_xml)
        self.assertNotIn(" (Chair)", workbook_xml)
        self.assertNotIn(">R1<", workbook_xml)

    def test_public_workbook_omits_removed_blank_paper_url_but_keeps_other_links(self) -> None:
        state = self._simple_publish_state()
        state.papers[0].link_to_pdf = ""
        with tempfile.TemporaryDirectory() as tmp:
            public_xlsx_path = export_public_excel(
                state,
                Path(tmp) / "public_blank_link.xlsx",
                show_links=True,
            )

            workbook_xml = self._zip_text(public_xlsx_path, (".xml", ".rels"))
            visible_text_xml = self._zip_text(public_xlsx_path, ("sharedStrings.xml",))

        self.assertIn("Public settings: rooms=shown, moderators=shown, links=shown", visible_text_xml)
        self.assertIn("PaperURL", visible_text_xml)
        self.assertNotIn("https://example.org/p1.pdf", workbook_xml)
        self.assertIn("https://example.org/p2.pdf", workbook_xml)

    def test_publish_workbook_treats_overflow_papers_as_session_presentations_and_adds_disclaimer(self) -> None:
        state = self._simple_publish_state()
        overflow_paper = SimpleNamespace(
            submission_id="P3",
            full_name="Presenter Overflow",
            title="Title Overflow",
            abstract="Abstract Overflow",
            link_to_pdf="https://example.org/p3.pdf",
            primary_theme="Theme C",
            detailed_subtheme="Subtheme C",
            session_code="S1",
            session_title="Session One",
            day_label="Day 1 (4th June)",
            day_num=1,
            time="10h00-11h00",
            block_label="SESSION 1",
            block_num=1,
            room="R1",
            placement_status="overflow",
            overflow_order=1,
        )
        state.papers.append(overflow_paper)
        state.sessions[0].overflow_papers = [overflow_paper]
        state.validations["overflow_papers"] = 1

        with tempfile.TemporaryDirectory() as tmp:
            publish_xlsx_path = export_publish_excel(state, Path(tmp) / "publish.xlsx")

            workbook_xml = self._zip_text(publish_xlsx_path, (".xml", ".rels"))
            visible_text_xml = self._zip_text(publish_xlsx_path, ("sharedStrings.xml",))

        self.assertIn("This programme covers parallel sessions only.", workbook_xml)
        self.assertIn("plenary sessions programme", visible_text_xml)
        self.assertNotIn("https://inequalitylab.world/www-site/uploads/2026/04/2026-WIC-Programme.pdf", visible_text_xml)
        self.assertIn("https://inequalitylab.world/www-site/uploads/2026/04/2026-WIC-Programme.pdf", workbook_xml)
        self.assertIn("Title Overflow", workbook_xml)
        self.assertLess(workbook_xml.index("Title Overflow"), workbook_xml.index("Presenter Overflow"))
        self.assertNotIn("Overflow: 1", workbook_xml)

    def test_publish_docx_matches_session_booklet_content_and_links_plenary_programme(self) -> None:
        state = self._simple_publish_state()
        overflow_paper = SimpleNamespace(
            submission_id="P3",
            full_name="Presenter Overflow",
            title="Title Overflow",
            abstract="Abstract Overflow",
            link_to_pdf="https://example.org/p3.pdf",
            primary_theme="Theme C",
            detailed_subtheme="Subtheme C",
            session_code="S1",
            session_title="Session One",
            day_label="Day 1 (4th June)",
            day_num=1,
            time="10h00-11h00",
            block_label="SESSION 1",
            block_num=1,
            room="R1",
            placement_status="overflow",
            overflow_order=1,
        )
        state.papers.append(overflow_paper)
        state.sessions[0].overflow_papers = [overflow_paper]

        with tempfile.TemporaryDirectory() as tmp:
            try:
                publish_docx_path = export_publish_docx(state, Path(tmp) / "publish.docx")
            except RuntimeError as exc:
                self.skipTest(str(exc))
            document_xml = self._zip_text(publish_docx_path, ("document.xml",))
            relationship_xml = self._zip_text(publish_docx_path, (".rels",))

        self.assertIn("World Inequality Conference 2026", document_xml)
        self.assertIn("Session Booklet", document_xml)
        self.assertIn("Session One", document_xml)
        self.assertIn("Title One", document_xml)
        self.assertIn("Presenter One", document_xml)
        self.assertIn("Title Overflow", document_xml)
        self.assertIn("Presenter Overflow", document_xml)
        self.assertIn("This programme covers parallel sessions only.", document_xml)
        self.assertIn("plenary sessions programme", document_xml)
        self.assertNotIn("https://inequalitylab.world/www-site/uploads/2026/04/2026-WIC-Programme.pdf", document_xml)
        self.assertIn("https://inequalitylab.world/www-site/uploads/2026/04/2026-WIC-Programme.pdf", relationship_xml)
        self.assertLess(document_xml.index("Title Overflow"), document_xml.index("Presenter Overflow"))

    def test_publish_docx_public_safe_hides_rooms_and_moderator_labels_and_adds_notice(self) -> None:
        state = self._simple_publish_state()
        state.papers[0].is_moderator = True
        with tempfile.TemporaryDirectory() as tmp:
            try:
                publish_docx_path = export_publish_docx(
                    state,
                    Path(tmp) / "publish_public_safe.docx",
                    publish_display=PUBLISH_DISPLAY_PUBLIC_SAFE,
                )
            except RuntimeError as exc:
                self.skipTest(str(exc))
            document_xml = self._zip_text(publish_docx_path, ("document.xml",))

        self.assertIn(PROGRAMME_CHANGE_NOTICE, document_xml)
        self.assertNotIn(" (Chair)", document_xml)
        self.assertNotIn(" | 10h00-11h00 | R1", document_xml)

    def test_publish_pdf_starts_with_sessions_and_omits_theme_and_link_metadata(self) -> None:
        state = self._simple_publish_state()
        captured_story = []

        class FakeColors(types.SimpleNamespace):
            black = "#000000"

            @staticmethod
            def HexColor(value: str) -> str:
                return value

        class FakeParagraphStyle:
            def __init__(self, name: str, **kwargs) -> None:
                self.name = name
                self.kwargs = kwargs

        class FakeParagraph:
            def __init__(self, text: str, _style) -> None:
                self.text = text

            def getPlainText(self) -> str:
                return re.sub(r"<[^>]+>", "", self.text)

        class CapturingDoc:
            def __init__(self, filename: str, **_kwargs) -> None:
                self.filename = filename

            def build(self, story) -> None:
                captured_story.extend(story)
                Path(self.filename).write_bytes(b"%PDF-FAKE")

        fake_modules = {
            "reportlab": types.ModuleType("reportlab"),
            "reportlab.lib": types.ModuleType("reportlab.lib"),
            "reportlab.lib.colors": FakeColors(),
            "reportlab.lib.pagesizes": types.SimpleNamespace(A4=(595, 842)),
            "reportlab.lib.styles": types.SimpleNamespace(
                ParagraphStyle=FakeParagraphStyle,
                getSampleStyleSheet=lambda: {
                    "Title": FakeParagraphStyle("Title"),
                    "Heading2": FakeParagraphStyle("Heading2"),
                    "Normal": FakeParagraphStyle("Normal"),
                },
            ),
            "reportlab.lib.units": types.SimpleNamespace(mm=1),
            "reportlab.platypus": types.SimpleNamespace(
                PageBreak=lambda: SimpleNamespace(kind="PageBreak"),
                Paragraph=FakeParagraph,
                SimpleDocTemplate=CapturingDoc,
                Spacer=lambda *_args: SimpleNamespace(kind="Spacer"),
            ),
        }

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(sys.modules, fake_modules):
                publish_pdf_path = export_publish_pdf(state, Path(tmp) / "publish.pdf", branding_config_path=None)
                self.assertTrue(publish_pdf_path.exists())

        paragraph_text = "\n".join(
            item.getPlainText() for item in captured_story if hasattr(item, "getPlainText")
        )
        paragraph_markup = "\n".join(
            item.text for item in captured_story if hasattr(item, "text")
        )
        self.assertNotIn("Timetable", paragraph_text)
        self.assertNotIn("Theme:", paragraph_text)
        self.assertNotIn("PDF link", paragraph_text)
        self.assertNotIn("Publish Programme", paragraph_text)
        self.assertNotIn("This publish PDF lists sessions and presentations", paragraph_text)
        self.assertNotIn("S1 |", paragraph_text)
        self.assertIn("Session Booklet", paragraph_text)
        self.assertIn("<b>Session One</b>", paragraph_markup)
        self.assertIn("Title One", paragraph_text)
        self.assertLess(paragraph_text.index("Title One"), paragraph_text.index("Presenter One"))
        self.assertIn("plenary sessions programme", paragraph_text)
        self.assertNotIn("https://inequalitylab.world/www-site/uploads/2026/04/2026-WIC-Programme.pdf", paragraph_text)
        self.assertIn("href='https://inequalitylab.world/www-site/uploads/2026/04/2026-WIC-Programme.pdf'", paragraph_markup)

    def test_publish_pdf_treats_overflow_papers_as_session_presentations_and_adds_disclaimer(self) -> None:
        state = self._simple_publish_state()
        overflow_paper = SimpleNamespace(
            submission_id="P3",
            full_name="Presenter Overflow",
            title="Title Overflow",
            abstract="Abstract Overflow",
            link_to_pdf="https://example.org/p3.pdf",
            primary_theme="Theme C",
            detailed_subtheme="Subtheme C",
            session_code="S1",
            session_title="Session One",
            day_label="Day 1 (4th June)",
            day_num=1,
            time="10h00-11h00",
            block_label="SESSION 1",
            block_num=1,
            room="R1",
            placement_status="overflow",
            overflow_order=1,
        )
        state.papers.append(overflow_paper)
        state.sessions[0].overflow_papers = [overflow_paper]
        captured_story = []

        class FakeColors(types.SimpleNamespace):
            black = "#000000"

            @staticmethod
            def HexColor(value: str) -> str:
                return value

        class FakeParagraphStyle:
            def __init__(self, name: str, **kwargs) -> None:
                self.name = name
                self.kwargs = kwargs

        class FakeParagraph:
            def __init__(self, text: str, _style) -> None:
                self.text = text

            def getPlainText(self) -> str:
                return re.sub(r"<[^>]+>", "", self.text)

        class CapturingDoc:
            def __init__(self, filename: str, **_kwargs) -> None:
                self.filename = filename

            def build(self, story) -> None:
                captured_story.extend(story)
                Path(self.filename).write_bytes(b"%PDF-FAKE")

        fake_modules = {
            "reportlab": types.ModuleType("reportlab"),
            "reportlab.lib": types.ModuleType("reportlab.lib"),
            "reportlab.lib.colors": FakeColors(),
            "reportlab.lib.pagesizes": types.SimpleNamespace(A4=(595, 842)),
            "reportlab.lib.styles": types.SimpleNamespace(
                ParagraphStyle=FakeParagraphStyle,
                getSampleStyleSheet=lambda: {
                    "Title": FakeParagraphStyle("Title"),
                    "Heading2": FakeParagraphStyle("Heading2"),
                    "Normal": FakeParagraphStyle("Normal"),
                },
            ),
            "reportlab.lib.units": types.SimpleNamespace(mm=1),
            "reportlab.platypus": types.SimpleNamespace(
                PageBreak=lambda: SimpleNamespace(kind="PageBreak"),
                Paragraph=FakeParagraph,
                SimpleDocTemplate=CapturingDoc,
                Spacer=lambda *_args: SimpleNamespace(kind="Spacer"),
            ),
        }

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(sys.modules, fake_modules):
                publish_pdf_path = export_publish_pdf(state, Path(tmp) / "publish.pdf", branding_config_path=None)
                self.assertTrue(publish_pdf_path.exists())

        paragraph_text = "\n".join(
            item.getPlainText() for item in captured_story if hasattr(item, "getPlainText")
        )

        self.assertIn("This programme covers parallel sessions only.", paragraph_text)
        self.assertIn("plenary sessions programme", paragraph_text)
        self.assertNotIn("https://inequalitylab.world/www-site/uploads/2026/04/2026-WIC-Programme.pdf", paragraph_text)
        self.assertIn("Title Overflow", paragraph_text)
        self.assertLess(paragraph_text.index("Title Overflow"), paragraph_text.index("Presenter Overflow"))
        self.assertNotIn("Overflow: 1", paragraph_text)

    def test_publish_pdf_public_safe_hides_rooms_and_moderator_labels_and_adds_notice(self) -> None:
        state = self._simple_publish_state()
        state.papers[0].is_moderator = True
        captured_story = []

        class FakeColors(types.SimpleNamespace):
            black = "#000000"

            @staticmethod
            def HexColor(value: str) -> str:
                return value

        class FakeParagraphStyle:
            def __init__(self, name: str, **kwargs) -> None:
                self.name = name
                self.kwargs = kwargs

        class FakeParagraph:
            def __init__(self, text: str, _style) -> None:
                self.text = text

            def getPlainText(self) -> str:
                return re.sub(r"<[^>]+>", "", self.text)

        class CapturingDoc:
            def __init__(self, filename: str, **_kwargs) -> None:
                self.filename = filename

            def build(self, story) -> None:
                captured_story.extend(story)
                Path(self.filename).write_bytes(b"%PDF-FAKE")

        fake_modules = {
            "reportlab": types.ModuleType("reportlab"),
            "reportlab.lib": types.ModuleType("reportlab.lib"),
            "reportlab.lib.colors": FakeColors(),
            "reportlab.lib.pagesizes": types.SimpleNamespace(A4=(595, 842)),
            "reportlab.lib.styles": types.SimpleNamespace(
                ParagraphStyle=FakeParagraphStyle,
                getSampleStyleSheet=lambda: {
                    "Title": FakeParagraphStyle("Title"),
                    "Heading2": FakeParagraphStyle("Heading2"),
                    "Normal": FakeParagraphStyle("Normal"),
                },
            ),
            "reportlab.lib.units": types.SimpleNamespace(mm=1),
            "reportlab.platypus": types.SimpleNamespace(
                PageBreak=lambda: SimpleNamespace(kind="PageBreak"),
                Paragraph=FakeParagraph,
                SimpleDocTemplate=CapturingDoc,
                Spacer=lambda *_args: SimpleNamespace(kind="Spacer"),
            ),
        }

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(sys.modules, fake_modules):
                publish_pdf_path = export_publish_pdf(
                    state,
                    Path(tmp) / "publish_public_safe.pdf",
                    branding_config_path=None,
                    publish_display=PUBLISH_DISPLAY_PUBLIC_SAFE,
                )
                self.assertTrue(publish_pdf_path.exists())

        paragraph_text = "\n".join(
            item.getPlainText() for item in captured_story if hasattr(item, "getPlainText")
        )

        self.assertIn(PROGRAMME_CHANGE_NOTICE, paragraph_text)
        self.assertNotIn(" (Chair)", paragraph_text)
        self.assertNotIn(" | 10h00-11h00 | R1", paragraph_text)

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

    def test_time_update_preserves_session_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            missing_submissions = tmp_path / "missing_submissions.xlsx"
            missing_programme = tmp_path / "missing_programme.xlsx"

            create_result = create_session(
                day_label="Day 1 (4th June)",
                block_label="SESSION X",
                time_label="9h00-10h00",
                room="R-TIME-EDIT",
                capacity=3,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(create_result.get("ok", False))
            session_id = create_result["session_id"]

            manual_ids = []
            for idx in range(1, 5):
                talk_result = create_manual_talk(
                    full_name=f"Time Edit Presenter {idx}",
                    title=f"Time Edit Talk {idx}",
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

            initial = self._build_state(paths, submissions=missing_submissions, programme=missing_programme)
            target = next(session for session in initial.sessions if session.session_id == session_id)
            self.assertEqual([paper.submission_id for paper in target.papers if paper is not None], manual_ids[:3])
            self.assertEqual([paper.submission_id for paper in target.overflow_papers], manual_ids[3:])

            start_min = 600
            end_min = 660
            update_result = update_session_structure_row(
                session_id,
                {
                    "StartMin": str(start_min),
                    "EndMin": str(end_min),
                    "TimeLabel": build_time_label(start_min, end_min),
                },
                session_structure_path=paths["structure"],
            )
            self.assertTrue(update_result.get("ok", False))

            refreshed = self._build_state(paths, submissions=missing_submissions, programme=missing_programme)
            updated = next(session for session in refreshed.sessions if session.session_id == session_id)
            self.assertEqual(updated.time, "10h00-11h00")
            self.assertEqual([paper.submission_id for paper in updated.papers if paper is not None], manual_ids[:3])
            self.assertEqual([paper.submission_id for paper in updated.overflow_papers], manual_ids[3:])
            occupied_ranges = [(paper.talk_start_min, paper.talk_end_min) for paper in updated.papers if paper is not None]
            self.assertEqual(occupied_ranges, [(600, 620), (620, 640), (640, 660)])

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

    def test_paper_metadata_overrides_apply_to_title_author_link_and_moderator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            for src, key in [
                (CLASSIFICATION_OVERRIDES_FILE, "classification"),
                (SESSION_NAME_OVERRIDES_FILE, "session_names"),
                (PROGRAMME_LAYOUT_OVERRIDES_FILE, "layout"),
                (SESSION_STRUCTURE_FILE, "structure"),
                (PAPER_PLACEMENTS_FILE, "placements"),
                (PAPER_METADATA_OVERRIDES_FILE, "metadata"),
                (MANUAL_TALKS_FILE, "manual"),
            ]:
                if src.exists():
                    shutil.copy2(src, paths[key])

            state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            paper = state.papers[0]
            sid = paper.submission_id
            new_title = f"{paper.title} (Edited)"
            new_author = f"{paper.full_name} (Edited)"
            new_link = "https://example.org/edited-paper.pdf"

            write_paper_metadata_overrides(
                [
                    {
                        "SubmissionID": sid,
                        "TitleOverride": new_title,
                        "AuthorOverride": new_author,
                        "LinkToPDFOverride": new_link,
                        "LinkToPDFOverrideActive": "True",
                        "IsModerator": "True",
                    }
                ],
                paths["metadata"],
            )
            loaded = load_paper_metadata_overrides(paths["metadata"])
            self.assertEqual(loaded[sid]["TitleOverride"], new_title)
            self.assertEqual(loaded[sid]["AuthorOverride"], new_author)
            self.assertEqual(loaded[sid]["LinkToPDFOverride"], new_link)
            self.assertEqual(loaded[sid]["LinkToPDFOverrideActive"], "True")
            self.assertEqual(loaded[sid]["IsModerator"], "True")

            state_after = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            updated = next(p for p in state_after.papers if p.submission_id == sid)
            self.assertEqual(updated.title, new_title)
            self.assertEqual(updated.full_name, new_author)
            self.assertEqual(updated.link_to_pdf, new_link)
            self.assertTrue(bool(getattr(updated, "is_moderator", False)))

    def test_paper_metadata_overrides_support_legacy_rows_without_moderator_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            for src, key in [
                (CLASSIFICATION_OVERRIDES_FILE, "classification"),
                (SESSION_NAME_OVERRIDES_FILE, "session_names"),
                (PROGRAMME_LAYOUT_OVERRIDES_FILE, "layout"),
                (SESSION_STRUCTURE_FILE, "structure"),
                (PAPER_PLACEMENTS_FILE, "placements"),
                (PAPER_METADATA_OVERRIDES_FILE, "metadata"),
                (MANUAL_TALKS_FILE, "manual"),
            ]:
                if src.exists():
                    shutil.copy2(src, paths[key])

            state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            paper = state.papers[0]
            sid = paper.submission_id
            legacy_title = "Legacy Title Override"
            legacy_author = "Legacy Author Override"
            paths["metadata"].write_text(
                (
                    "SubmissionID,TitleOverride,AuthorOverride,UpdatedAt\n"
                    f"{sid},{legacy_title},{legacy_author},2026-04-01T10:00:00\n"
                ),
                encoding="utf-8",
            )

            state_after = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            updated = next(p for p in state_after.papers if p.submission_id == sid)
            self.assertEqual(updated.title, legacy_title)
            self.assertEqual(updated.full_name, legacy_author)
            self.assertEqual(load_paper_metadata_overrides(paths["metadata"])[sid]["LinkToPDFOverrideActive"], "")
            self.assertFalse(bool(getattr(updated, "is_moderator", False)))

    def test_paper_metadata_blank_active_link_override_removes_source_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            for src, key in [
                (CLASSIFICATION_OVERRIDES_FILE, "classification"),
                (SESSION_NAME_OVERRIDES_FILE, "session_names"),
                (PROGRAMME_LAYOUT_OVERRIDES_FILE, "layout"),
                (SESSION_STRUCTURE_FILE, "structure"),
                (PAPER_PLACEMENTS_FILE, "placements"),
                (PAPER_METADATA_OVERRIDES_FILE, "metadata"),
                (MANUAL_TALKS_FILE, "manual"),
            ]:
                if src.exists():
                    shutil.copy2(src, paths[key])

            state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            paper = next(p for p in state.papers if str(getattr(p, "link_to_pdf", "")).strip())
            sid = paper.submission_id

            write_paper_metadata_overrides(
                [
                    {
                        "SubmissionID": sid,
                        "LinkToPDFOverride": "",
                        "LinkToPDFOverrideActive": "True",
                    }
                ],
                paths["metadata"],
            )
            loaded = load_paper_metadata_overrides(paths["metadata"])
            self.assertIn(sid, loaded)
            self.assertEqual(loaded[sid]["LinkToPDFOverride"], "")
            self.assertEqual(loaded[sid]["LinkToPDFOverrideActive"], "True")
            self.assertIn("LinkToPDFOverrideActive", paths["metadata"].read_text(encoding="utf-8"))

            state_after = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            updated = next(p for p in state_after.papers if p.submission_id == sid)
            self.assertEqual(updated.link_to_pdf, "")

    def test_paper_archive_overrides_roundtrip_and_exclusion_from_active_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            for src, key in [
                (CLASSIFICATION_OVERRIDES_FILE, "classification"),
                (SESSION_NAME_OVERRIDES_FILE, "session_names"),
                (PROGRAMME_LAYOUT_OVERRIDES_FILE, "layout"),
                (SESSION_STRUCTURE_FILE, "structure"),
                (PAPER_PLACEMENTS_FILE, "placements"),
                (PAPER_METADATA_OVERRIDES_FILE, "metadata"),
                (PAPER_ARCHIVE_OVERRIDES_FILE, "archive"),
                (MANUAL_TALKS_FILE, "manual"),
            ]:
                if src.exists():
                    shutil.copy2(src, paths[key])

            state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            paper = state.papers[0]
            sid = paper.submission_id

            write_paper_archive_overrides(
                [
                    {
                        "SubmissionID": sid,
                        "ArchiveReason": "Duplicate submission",
                        "ArchiveNote": "Merged with canonical record.",
                        "ArchivedAt": "2026-03-01T10:00:00",
                        "PreviousPlacementStatus": "scheduled",
                        "PreviousSessionId": paper.session_id,
                        "PreviousTalkIndex": str(max(1, int(paper.talk_index or 1))),
                        "PreviousOverflowOrder": "",
                    }
                ],
                paths["archive"],
            )
            loaded_archive = load_paper_archive_overrides(paths["archive"])
            self.assertIn(sid, loaded_archive)
            self.assertEqual(loaded_archive[sid]["ArchiveReason"], "Duplicate submission")
            self.assertEqual(loaded_archive[sid]["ArchiveNote"], "Merged with canonical record.")

            state_after = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            self.assertNotIn(sid, {p.submission_id for p in state_after.papers})
            self.assertIn(sid, {p.submission_id for p in state_after.archived_papers})
            self.assertEqual(int(state_after.validations.get("archived_papers", 0) or 0), 1)
            self.assertIn(sid, state_after.validations.get("archived_submission_ids", []))
            self.assertEqual(
                int((state_after.validations.get("archived_by_reason", {}) or {}).get("Duplicate submission", 0) or 0),
                1,
            )
            self.assertNotIn(sid, state_after.validations.get("unassigned_submission_ids", []))
            self.assertFalse(
                any(
                    sid == getattr(slot_paper, "submission_id", "")
                    for session in state_after.all_sessions
                    for slot_paper in list(getattr(session, "papers", []) or [])
                    if slot_paper is not None
                )
            )

    def test_restore_from_archive_returns_paper_to_unassigned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            for src, key in [
                (CLASSIFICATION_OVERRIDES_FILE, "classification"),
                (SESSION_NAME_OVERRIDES_FILE, "session_names"),
                (PROGRAMME_LAYOUT_OVERRIDES_FILE, "layout"),
                (SESSION_STRUCTURE_FILE, "structure"),
                (PAPER_PLACEMENTS_FILE, "placements"),
                (PAPER_METADATA_OVERRIDES_FILE, "metadata"),
                (PAPER_ARCHIVE_OVERRIDES_FILE, "archive"),
                (MANUAL_TALKS_FILE, "manual"),
            ]:
                if src.exists():
                    shutil.copy2(src, paths[key])

            state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            paper = state.papers[0]
            sid = paper.submission_id

            write_paper_archive_overrides(
                [
                    {
                        "SubmissionID": sid,
                        "ArchiveReason": "Author cancelled attendance",
                        "ArchiveNote": "Unable to travel.",
                        "ArchivedAt": "2026-03-02T09:30:00",
                        "PreviousPlacementStatus": "scheduled",
                        "PreviousSessionId": paper.session_id,
                        "PreviousTalkIndex": str(max(1, int(paper.talk_index or 1))),
                        "PreviousOverflowOrder": "",
                    }
                ],
                paths["archive"],
            )
            state_archived = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            self.assertIn(sid, {p.submission_id for p in state_archived.archived_papers})

            placements = load_paper_placements(paths["placements"])
            placements[sid] = {
                "SubmissionID": sid,
                "PlacementStatus": "unassigned",
                "SessionId": "",
                "TalkIndex": "",
                "OverflowOrder": "",
                "UpdatedAt": "2026-03-02T10:00:00",
            }
            write_paper_placements(placements.values(), paths["placements"])
            write_paper_archive_overrides([], paths["archive"])

            state_restored = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            self.assertIn(sid, {p.submission_id for p in state_restored.papers})
            self.assertNotIn(sid, {p.submission_id for p in state_restored.archived_papers})
            self.assertIn(sid, [p.submission_id for p in state_restored.unassigned_papers])
            self.assertEqual(int(state_restored.validations.get("archived_papers", 0) or 0), 0)

    def test_validation_exposes_disjoint_active_and_archived_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            for src, key in [
                (CLASSIFICATION_OVERRIDES_FILE, "classification"),
                (SESSION_NAME_OVERRIDES_FILE, "session_names"),
                (PROGRAMME_LAYOUT_OVERRIDES_FILE, "layout"),
                (SESSION_STRUCTURE_FILE, "structure"),
                (PAPER_PLACEMENTS_FILE, "placements"),
                (PAPER_METADATA_OVERRIDES_FILE, "metadata"),
                (PAPER_ARCHIVE_OVERRIDES_FILE, "archive"),
                (MANUAL_TALKS_FILE, "manual"),
            ]:
                if src.exists():
                    shutil.copy2(src, paths[key])

            state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            scheduled_paper = next((paper for paper in state.papers if str(paper.session_id).strip()), None)
            self.assertIsNotNone(scheduled_paper)
            sid = scheduled_paper.submission_id

            write_paper_archive_overrides(
                [
                    {
                        "SubmissionID": sid,
                        "ArchiveReason": "Duplicate submission",
                        "ArchiveNote": "",
                        "ArchivedAt": "2026-04-03T10:00:00",
                        "PreviousPlacementStatus": "scheduled",
                        "PreviousSessionId": scheduled_paper.session_id,
                        "PreviousTalkIndex": str(max(1, int(scheduled_paper.talk_index or 1))),
                        "PreviousOverflowOrder": "",
                    }
                ],
                paths["archive"],
            )

            state_after = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            validations = state_after.validations

            self.assertEqual(
                int(validations["total_papers"] or 0),
                int(validations["active_papers"] or 0) + int(validations["archived_papers"] or 0),
            )
            self.assertEqual(
                int(validations["active_papers"] or 0),
                int(validations["scheduled_active_papers"] or 0)
                + int(validations["overflow_active_papers"] or 0)
                + int(validations["scheduled_in_inactive_sessions"] or 0)
                + int(validations["overflow_in_inactive_sessions"] or 0)
                + int(validations["unassigned_active_papers"] or 0),
            )
            self.assertEqual(
                int((validations["archived_by_previous_status"] or {}).get("scheduled", 0) or 0),
                1,
            )
            self.assertEqual(
                int((validations["archived_by_previous_status"] or {}).get("overflow", 0) or 0),
                0,
            )
            self.assertEqual(
                int((validations["archived_by_previous_status"] or {}).get("unassigned", 0) or 0),
                0,
            )

    def test_assignment_to_inactive_session_is_tracked_as_inactive_assigned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            paths = self._temp_state_paths(tmp_path)
            for src, key in [
                (CLASSIFICATION_OVERRIDES_FILE, "classification"),
                (SESSION_NAME_OVERRIDES_FILE, "session_names"),
                (PROGRAMME_LAYOUT_OVERRIDES_FILE, "layout"),
                (SESSION_STRUCTURE_FILE, "structure"),
                (PAPER_PLACEMENTS_FILE, "placements"),
                (PAPER_METADATA_OVERRIDES_FILE, "metadata"),
                (MANUAL_TALKS_FILE, "manual"),
            ]:
                if src.exists():
                    shutil.copy2(src, paths[key])

            state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            if not state.inactive_sessions:
                chosen = state.sessions[0]
                remove_result = remove_session(
                    chosen.session_id,
                    session_structure_path=paths["structure"],
                    paper_placements_path=paths["placements"],
                )
                self.assertTrue(remove_result.get("ok", False))
                state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)

            self.assertTrue(state.inactive_sessions, "Expected at least one inactive session for this test.")
            inactive_session = state.inactive_sessions[0]
            paper = state.papers[0]
            sid = paper.submission_id

            placements = load_paper_placements(paths["placements"])
            placements[sid] = {
                "SubmissionID": sid,
                "PlacementStatus": "scheduled",
                "SessionId": inactive_session.session_id,
                "TalkIndex": "999",
                "OverflowOrder": "",
                "UpdatedAt": "",
            }
            write_paper_placements(placements.values(), paths["placements"])

            state_after = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
            updated = next(p for p in state_after.papers if p.submission_id == sid)
            self.assertEqual(updated.session_id, inactive_session.session_id)
            self.assertNotEqual(updated.placement_status, "unassigned")
            self.assertNotIn(sid, [p.submission_id for p in state_after.unassigned_papers])
            self.assertNotIn(sid, state_after.validations.get("missing_submission_ids", []))
            self.assertGreaterEqual(int(state_after.validations.get("inactive_assigned_papers", 0) or 0), 1)
            self.assertIn(sid, state_after.validations.get("inactive_assigned_submission_ids", []))

    def test_rename_room_for_day_success_and_collision_rejection(self) -> None:
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
            active_rows = [
                row
                for row in rows.values()
                if str(row.get("Status", "active")).strip().lower() == "active"
            ]
            grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
            for row in active_rows:
                key = (str(row.get("DayLabel", "")).strip(), str(row.get("TimeLabel", "")).strip())
                grouped.setdefault(key, []).append(row)

            collision_group = next(
                (
                    (key, group)
                    for key, group in grouped.items()
                    if key[0] and key[1] and len({str(item.get("Room", "")).strip() for item in group}) >= 2
                ),
                None,
            )
            self.assertIsNotNone(collision_group)
            (day_label, _), group_rows = collision_group
            room_a = str(group_rows[0].get("Room", "")).strip()
            room_b = str(group_rows[1].get("Room", "")).strip()

            collision_result = rename_room_for_day(
                day_label=day_label,
                room=room_a,
                new_room=room_b,
                session_structure_path=paths["structure"],
            )
            self.assertFalse(collision_result.get("ok", False))

            existing_rooms = {
                str(row.get("Room", "")).strip()
                for row in rows.values()
                if str(row.get("DayLabel", "")).strip() == day_label
            }
            renamed_room = f"{room_a}-RENAMED"
            suffix = 2
            while renamed_room in existing_rooms:
                renamed_room = f"{room_a}-RENAMED-{suffix}"
                suffix += 1

            rename_result = rename_room_for_day(
                day_label=day_label,
                room=room_a,
                new_room=renamed_room,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(rename_result.get("ok", False))
            self.assertGreater(int(rename_result.get("updated", 0) or 0), 0)

            rows_after = load_session_structure_rows(paths["structure"])
            updated_rows = [
                row
                for row in rows_after.values()
                if str(row.get("DayLabel", "")).strip() == day_label
                and str(row.get("Room", "")).strip() == renamed_room
            ]
            self.assertGreaterEqual(len(updated_rows), int(rename_result.get("updated", 0) or 0))

    def test_add_block_row_sessions_creates_for_all_day_rooms_and_skips_on_rerun(self) -> None:
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
            day_label = next((str(row.get("DayLabel", "")).strip() for row in rows.values() if str(row.get("DayLabel", "")).strip()), "")
            self.assertTrue(day_label)
            day_rows = [row for row in rows.values() if str(row.get("DayLabel", "")).strip() == day_label]
            day_rooms = {
                str(row.get("Room", "")).strip()
                for row in day_rows
                if str(row.get("Room", "")).strip()
            }
            self.assertTrue(day_rooms)

            max_end = max([int(str(row.get("EndMin", "0") or "0")) for row in day_rows] + [8 * 60])
            max_block = max([int(str(row.get("BlockNum", "0") or "0")) for row in day_rows] + [0])
            first_result = add_block_row_sessions(
                day_label=day_label,
                block_label=f"SESSION {max_block + 1}",
                block_num=max_block + 1,
                start_min=max_end + 15,
                duration_min=90,
                capacity=4,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(first_result.get("ok", False))
            created_first = int(first_result.get("created", 0) or 0)
            self.assertEqual(created_first, len(day_rooms))

            second_result = add_block_row_sessions(
                day_label=day_label,
                block_label=f"SESSION {max_block + 1}",
                block_num=max_block + 1,
                start_min=max_end + 15,
                duration_min=90,
                capacity=4,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(second_result.get("ok", False))
            self.assertEqual(int(second_result.get("created", 0) or 0), 0)
            self.assertGreaterEqual(int(second_result.get("skipped_active", 0) or 0), len(day_rooms))

    def test_clear_day_sessions_unassigns_papers_and_keeps_rows(self) -> None:
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

            rows_before = load_session_structure_rows(paths["structure"])
            placements_before = load_paper_placements(paths["placements"])
            session_to_day = {
                str(row.get("SessionId", "")).strip(): str(row.get("DayLabel", "")).strip()
                for row in rows_before.values()
            }
            affected_by_day: dict[str, list[str]] = {}
            for sid, placement in placements_before.items():
                status = str(placement.get("PlacementStatus", "")).strip().lower()
                if status not in {"scheduled", "overflow"}:
                    continue
                session_id = str(placement.get("SessionId", "")).strip()
                day_label = session_to_day.get(session_id, "")
                if not day_label:
                    continue
                affected_by_day.setdefault(day_label, []).append(sid)

            target_day = next((day for day, submission_ids in affected_by_day.items() if submission_ids), "")
            self.assertTrue(target_day)
            day_rows_before = [
                row for row in rows_before.values() if str(row.get("DayLabel", "")).strip() == target_day
            ]

            result = clear_day_sessions(
                day_label=target_day,
                session_structure_path=paths["structure"],
                paper_placements_path=paths["placements"],
            )
            self.assertTrue(result.get("ok", False))
            self.assertGreater(int(result.get("moved_to_unassigned", 0) or 0), 0)

            rows_after = load_session_structure_rows(paths["structure"])
            day_rows_after = [
                row for row in rows_after.values() if str(row.get("DayLabel", "")).strip() == target_day
            ]
            self.assertEqual(len(day_rows_before), len(day_rows_after))

            placements_after = load_paper_placements(paths["placements"])
            for sid in affected_by_day[target_day]:
                updated = placements_after[sid]
                self.assertEqual(str(updated.get("PlacementStatus", "")).strip().lower(), "unassigned")
                self.assertEqual(str(updated.get("SessionId", "")).strip(), "")

    def test_delete_day_sessions_unassigns_and_removes_rows(self) -> None:
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

            rows_before = load_session_structure_rows(paths["structure"])
            placements_before = load_paper_placements(paths["placements"])
            session_to_day = {
                str(row.get("SessionId", "")).strip(): str(row.get("DayLabel", "")).strip()
                for row in rows_before.values()
            }
            day_scores: dict[str, int] = {}
            for placement in placements_before.values():
                status = str(placement.get("PlacementStatus", "")).strip().lower()
                if status not in {"scheduled", "overflow"}:
                    continue
                session_id = str(placement.get("SessionId", "")).strip()
                day_label = session_to_day.get(session_id, "")
                if not day_label:
                    continue
                day_scores[day_label] = day_scores.get(day_label, 0) + 1

            target_day = next(iter(day_scores.keys()), "")
            self.assertTrue(target_day)
            deleted_session_ids = {
                str(row.get("SessionId", "")).strip()
                for row in rows_before.values()
                if str(row.get("DayLabel", "")).strip() == target_day
            }
            affected_submissions = [
                sid
                for sid, placement in placements_before.items()
                if str(placement.get("SessionId", "")).strip() in deleted_session_ids
                and str(placement.get("PlacementStatus", "")).strip().lower() in {"scheduled", "overflow"}
            ]

            result = delete_day_sessions(
                day_label=target_day,
                session_structure_path=paths["structure"],
                paper_placements_path=paths["placements"],
            )
            self.assertTrue(result.get("ok", False))
            self.assertEqual(int(result.get("deleted", 0) or 0), len(deleted_session_ids))

            rows_after = load_session_structure_rows(paths["structure"])
            self.assertFalse(
                any(str(row.get("DayLabel", "")).strip() == target_day for row in rows_after.values())
            )

            placements_after = load_paper_placements(paths["placements"])
            for sid in affected_submissions:
                updated = placements_after[sid]
                self.assertEqual(str(updated.get("PlacementStatus", "")).strip().lower(), "unassigned")
                self.assertEqual(str(updated.get("SessionId", "")).strip(), "")

    def test_relabel_day_sessions_rewrites_codes_and_migrates_overrides(self) -> None:
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

            rows_before = load_session_structure_rows(paths["structure"])
            target_day = next((str(row.get("DayLabel", "")).strip() for row in rows_before.values() if str(row.get("DayLabel", "")).strip()), "")
            self.assertTrue(target_day)
            target_rows_before = [
                row for row in rows_before.values() if str(row.get("DayLabel", "")).strip() == target_day
            ]
            self.assertTrue(target_rows_before)
            old_code = str(target_rows_before[0].get("SessionCode", "")).strip()
            self.assertTrue(old_code)

            write_session_name_overrides({old_code: "Relabeled Session Title"}, paths["session_names"])

            new_day_label = f"{target_day} (Relabeled)"
            result = relabel_day_sessions(
                day_label=target_day,
                new_day_label=new_day_label,
                new_day_num=88,
                session_structure_path=paths["structure"],
                session_name_overrides_path=paths["session_names"],
            )
            self.assertTrue(result.get("ok", False))
            self.assertGreater(int(result.get("updated", 0) or 0), 0)

            rows_after = load_session_structure_rows(paths["structure"])
            relabeled_rows = [
                row for row in rows_after.values() if str(row.get("DayLabel", "")).strip() == new_day_label
            ]
            self.assertEqual(len(relabeled_rows), len(target_rows_before))
            relabeled_codes = [str(row.get("SessionCode", "")).strip() for row in relabeled_rows]
            self.assertTrue(all(code.startswith("D88-B") for code in relabeled_codes))
            self.assertEqual(len(relabeled_codes), len(set(relabeled_codes)))
            self.assertTrue(all(str(row.get("DayNum", "")).strip() == "88" for row in relabeled_rows))

            overrides_after = load_session_name_overrides(paths["session_names"])
            self.assertNotIn(old_code, overrides_after)
            self.assertIn("Relabeled Session Title", set(overrides_after.values()))

    def test_transfer_session_content_replace_moves_title_slots_overflow_and_resizes_target(self) -> None:
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
            candidate_sessions = [session for session in state.sessions if any(paper is not None for paper in session.papers)]
            self.assertGreaterEqual(len(candidate_sessions), 2)
            source = candidate_sessions[0]
            target = candidate_sessions[1]

            rows = load_session_structure_rows(paths["structure"])
            rows[source.session_id]["Capacity"] = "5"
            rows[target.session_id]["Capacity"] = "2"
            rows[target.session_id]["Status"] = "inactive"
            write_session_structure_rows(rows.values(), paths["structure"])

            placements = load_paper_placements(paths["placements"])
            source_rows = {
                sid: dict(row)
                for sid, row in placements.items()
                if str(row.get("SessionId", "")).strip() == source.session_id
                and str(row.get("PlacementStatus", "")).strip().lower() in {"scheduled", "overflow"}
            }
            target_rows = {
                sid: dict(row)
                for sid, row in placements.items()
                if str(row.get("SessionId", "")).strip() == target.session_id
                and str(row.get("PlacementStatus", "")).strip().lower() in {"scheduled", "overflow"}
            }
            self.assertTrue(source_rows)
            self.assertTrue(target_rows)
            if not any(str(row.get("PlacementStatus", "")).strip().lower() == "overflow" for row in source_rows.values()):
                source_sid_for_overflow = next(
                    (
                        sid
                        for sid, row in source_rows.items()
                        if str(row.get("PlacementStatus", "")).strip().lower() == "scheduled"
                    ),
                    "",
                )
                self.assertTrue(source_sid_for_overflow)
                placements[source_sid_for_overflow]["PlacementStatus"] = "overflow"
                placements[source_sid_for_overflow]["TalkIndex"] = ""
                placements[source_sid_for_overflow]["OverflowOrder"] = "1"
                write_paper_placements(placements.values(), paths["placements"])
                placements = load_paper_placements(paths["placements"])
                source_rows = {
                    sid: dict(row)
                    for sid, row in placements.items()
                    if str(row.get("SessionId", "")).strip() == source.session_id
                    and str(row.get("PlacementStatus", "")).strip().lower() in {"scheduled", "overflow"}
                }

            write_session_name_overrides(
                {
                    source.session_code: "Source Previous Override",
                    target.session_code: "Target Previous Override",
                },
                paths["session_names"],
            )

            result = transfer_session_content(
                source_session_id=source.session_id,
                target_session_id=target.session_id,
                mode="replace",
                session_structure_path=paths["structure"],
                paper_placements_path=paths["placements"],
                session_name_overrides_path=paths["session_names"],
                source_effective_title="Source Effective Title",
                target_effective_title="Target Effective Title",
            )
            self.assertTrue(result.get("ok", False))
            self.assertEqual(int(result.get("moved_to_target", 0) or 0), len(source_rows))
            self.assertEqual(int(result.get("moved_to_source", 0) or 0), 0)
            self.assertEqual(int(result.get("unassigned_from_target", 0) or 0), len(target_rows))
            self.assertGreaterEqual(int(result.get("capacity_updates", 0) or 0), 1)
            self.assertGreaterEqual(int(result.get("title_updates", 0) or 0), 1)
            self.assertTrue(result.get("warnings", []))

            rows_after = load_session_structure_rows(paths["structure"])
            self.assertEqual(str(rows_after[target.session_id].get("Capacity", "")).strip(), "5")
            placements_after = load_paper_placements(paths["placements"])
            for sid, before_row in source_rows.items():
                updated = placements_after[sid]
                self.assertEqual(str(updated.get("SessionId", "")).strip(), target.session_id)
                self.assertEqual(
                    str(updated.get("PlacementStatus", "")).strip().lower(),
                    str(before_row.get("PlacementStatus", "")).strip().lower(),
                )
                if str(before_row.get("PlacementStatus", "")).strip().lower() == "scheduled":
                    self.assertEqual(
                        str(updated.get("TalkIndex", "")).strip(),
                        str(before_row.get("TalkIndex", "")).strip(),
                    )
                if str(before_row.get("PlacementStatus", "")).strip().lower() == "overflow":
                    self.assertEqual(
                        str(updated.get("OverflowOrder", "")).strip(),
                        str(before_row.get("OverflowOrder", "")).strip(),
                    )
            for sid in target_rows:
                updated = placements_after[sid]
                self.assertEqual(str(updated.get("PlacementStatus", "")).strip().lower(), "unassigned")
                self.assertEqual(str(updated.get("SessionId", "")).strip(), "")

            overrides_after = load_session_name_overrides(paths["session_names"])
            self.assertNotIn(source.session_code, overrides_after)
            self.assertEqual(overrides_after.get(target.session_code, ""), "Source Effective Title")

    def test_transfer_session_content_swap_exchanges_slots_overflow_titles_and_resizes_both(self) -> None:
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
            candidate_sessions = [session for session in state.sessions if session.session_id and session.session_code]
            self.assertGreaterEqual(len(candidate_sessions), 2)
            source = candidate_sessions[0]
            target = candidate_sessions[1]

            all_submission_ids = [paper.submission_id for paper in state.papers if paper.submission_id]
            self.assertGreaterEqual(len(all_submission_ids), 4)
            sid_source_scheduled, sid_source_overflow, sid_target_scheduled, sid_target_overflow = all_submission_ids[:4]

            placements = load_paper_placements(paths["placements"])
            for row in placements.values():
                if str(row.get("SessionId", "")).strip() in {source.session_id, target.session_id}:
                    row["PlacementStatus"] = "unassigned"
                    row["SessionId"] = ""
                    row["TalkIndex"] = ""
                    row["OverflowOrder"] = ""
            placements[sid_source_scheduled]["PlacementStatus"] = "scheduled"
            placements[sid_source_scheduled]["SessionId"] = source.session_id
            placements[sid_source_scheduled]["TalkIndex"] = "2"
            placements[sid_source_scheduled]["OverflowOrder"] = ""
            placements[sid_source_overflow]["PlacementStatus"] = "overflow"
            placements[sid_source_overflow]["SessionId"] = source.session_id
            placements[sid_source_overflow]["TalkIndex"] = ""
            placements[sid_source_overflow]["OverflowOrder"] = "2"
            placements[sid_target_scheduled]["PlacementStatus"] = "scheduled"
            placements[sid_target_scheduled]["SessionId"] = target.session_id
            placements[sid_target_scheduled]["TalkIndex"] = "3"
            placements[sid_target_scheduled]["OverflowOrder"] = ""
            placements[sid_target_overflow]["PlacementStatus"] = "overflow"
            placements[sid_target_overflow]["SessionId"] = target.session_id
            placements[sid_target_overflow]["TalkIndex"] = ""
            placements[sid_target_overflow]["OverflowOrder"] = "1"
            write_paper_placements(placements.values(), paths["placements"])

            rows = load_session_structure_rows(paths["structure"])
            rows[source.session_id]["Capacity"] = "1"
            rows[target.session_id]["Capacity"] = "1"
            rows[source.session_id]["Status"] = "active"
            rows[target.session_id]["Status"] = "active"
            write_session_structure_rows(rows.values(), paths["structure"])

            write_session_name_overrides(
                {
                    source.session_code: "Source Override Before Swap",
                    target.session_code: "Target Override Before Swap",
                },
                paths["session_names"],
            )

            result = transfer_session_content(
                source_session_id=source.session_id,
                target_session_id=target.session_id,
                mode="swap",
                session_structure_path=paths["structure"],
                paper_placements_path=paths["placements"],
                session_name_overrides_path=paths["session_names"],
                source_effective_title="Source Effective Swap Title",
                target_effective_title="Target Effective Swap Title",
            )
            self.assertTrue(result.get("ok", False))
            self.assertEqual(int(result.get("moved_to_target", 0) or 0), 2)
            self.assertEqual(int(result.get("moved_to_source", 0) or 0), 2)
            self.assertEqual(int(result.get("unassigned_from_target", 0) or 0), 0)
            self.assertEqual(int(result.get("capacity_updates", 0) or 0), 2)
            self.assertGreaterEqual(int(result.get("title_updates", 0) or 0), 2)
            self.assertEqual(list(result.get("warnings", []) or []), [])

            placements_after = load_paper_placements(paths["placements"])
            self.assertEqual(str(placements_after[sid_source_scheduled].get("SessionId", "")).strip(), target.session_id)
            self.assertEqual(str(placements_after[sid_source_scheduled].get("PlacementStatus", "")).strip().lower(), "scheduled")
            self.assertEqual(str(placements_after[sid_source_scheduled].get("TalkIndex", "")).strip(), "2")
            self.assertEqual(str(placements_after[sid_source_overflow].get("SessionId", "")).strip(), target.session_id)
            self.assertEqual(str(placements_after[sid_source_overflow].get("PlacementStatus", "")).strip().lower(), "overflow")
            self.assertEqual(str(placements_after[sid_source_overflow].get("OverflowOrder", "")).strip(), "2")
            self.assertEqual(str(placements_after[sid_target_scheduled].get("SessionId", "")).strip(), source.session_id)
            self.assertEqual(str(placements_after[sid_target_scheduled].get("PlacementStatus", "")).strip().lower(), "scheduled")
            self.assertEqual(str(placements_after[sid_target_scheduled].get("TalkIndex", "")).strip(), "3")
            self.assertEqual(str(placements_after[sid_target_overflow].get("SessionId", "")).strip(), source.session_id)
            self.assertEqual(str(placements_after[sid_target_overflow].get("PlacementStatus", "")).strip().lower(), "overflow")
            self.assertEqual(str(placements_after[sid_target_overflow].get("OverflowOrder", "")).strip(), "1")

            rows_after = load_session_structure_rows(paths["structure"])
            self.assertEqual(str(rows_after[source.session_id].get("Capacity", "")).strip(), "3")
            self.assertEqual(str(rows_after[target.session_id].get("Capacity", "")).strip(), "2")

            overrides_after = load_session_name_overrides(paths["session_names"])
            self.assertEqual(overrides_after.get(source.session_code, ""), "Target Effective Swap Title")
            self.assertEqual(overrides_after.get(target.session_code, ""), "Source Effective Swap Title")

    def test_transfer_session_content_invalid_inputs(self) -> None:
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
            self.assertTrue(state.all_sessions)
            source_session_id = state.all_sessions[0].session_id

            missing_ids = transfer_session_content(
                source_session_id="",
                target_session_id=source_session_id,
                mode="replace",
                session_structure_path=paths["structure"],
                paper_placements_path=paths["placements"],
                session_name_overrides_path=paths["session_names"],
            )
            self.assertFalse(missing_ids.get("ok", False))

            same_ids = transfer_session_content(
                source_session_id=source_session_id,
                target_session_id=source_session_id,
                mode="replace",
                session_structure_path=paths["structure"],
                paper_placements_path=paths["placements"],
                session_name_overrides_path=paths["session_names"],
            )
            self.assertFalse(same_ids.get("ok", False))

            unknown_target = transfer_session_content(
                source_session_id=source_session_id,
                target_session_id="missing-session-id",
                mode="replace",
                session_structure_path=paths["structure"],
                paper_placements_path=paths["placements"],
                session_name_overrides_path=paths["session_names"],
            )
            self.assertFalse(unknown_target.get("ok", False))

            bad_mode = transfer_session_content(
                source_session_id=source_session_id,
                target_session_id=state.all_sessions[1].session_id if len(state.all_sessions) > 1 else "missing-session-id",
                mode="invalid-mode",
                session_structure_path=paths["structure"],
                paper_placements_path=paths["placements"],
                session_name_overrides_path=paths["session_names"],
            )
            self.assertFalse(bad_mode.get("ok", False))

    def test_clone_day_structure_skips_existing_slots_on_rerun(self) -> None:
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
            source_day = next((str(row.get("DayLabel", "")).strip() for row in rows.values() if str(row.get("DayLabel", "")).strip()), "")
            self.assertTrue(source_day)

            first_result = clone_day_structure(
                source_day_label=source_day,
                target_day_label=f"{source_day} Clone",
                target_day_num=91,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(first_result.get("ok", False))
            first_created = int(first_result.get("created", 0) or 0)
            self.assertGreater(first_created, 0)

            second_result = clone_day_structure(
                source_day_label=source_day,
                target_day_label=f"{source_day} Clone",
                target_day_num=91,
                session_structure_path=paths["structure"],
            )
            self.assertTrue(second_result.get("ok", False))
            self.assertEqual(int(second_result.get("created", 0) or 0), 0)
            self.assertGreaterEqual(int(second_result.get("skipped_active", 0) or 0), first_created)


if __name__ == "__main__":
    unittest.main()
