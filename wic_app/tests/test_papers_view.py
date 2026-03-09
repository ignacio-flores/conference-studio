from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.papers import (  # noqa: E402
    build_classification_update_df,
    build_paper_metadata_update_df,
    build_session_options,
    default_session_option_for_paper,
    paper_public_row,
    presenter_with_abstract_html,
    title_link_html,
)


class PapersViewTests(unittest.TestCase):
    def test_presenter_hover_contains_abstract(self) -> None:
        html_value = presenter_with_abstract_html(
            "Alice Example",
            "This is an abstract preview.",
        )
        self.assertIn("title='This is an abstract preview.'", html_value)
        self.assertIn("Alice Example", html_value)

    def test_title_link_generation_with_and_without_url(self) -> None:
        linked = title_link_html("Paper Title", "https://example.org/paper.pdf")
        self.assertIn("href='https://example.org/paper.pdf'", linked)
        self.assertIn("target='_blank'", linked)
        self.assertIn("Paper Title", linked)

        no_link = title_link_html("No Link Paper", "")
        self.assertIn("No Link Paper", no_link)
        self.assertNotIn("href=", no_link)

    def test_paper_public_row_hides_submission_id(self) -> None:
        raw = {
            "SubmissionID": "ABC123",
            "FullName": "Presenter",
            "Abstract": "Abstract",
            "Title": "Title",
            "LinkToPDF": "https://example.org/paper.pdf",
            "PrimaryTheme": "Theme",
            "Subtheme": "Subtheme",
            "OverrideNotes": "Notes",
            "PlacementStatus": "scheduled",
            "SessionCode": "S1",
            "Day": "Day 1",
            "Block": "SESSION 1",
            "Room": "R1",
        }
        out = paper_public_row(raw)
        self.assertNotIn("SubmissionID", out)
        self.assertEqual(out["HasLink"], "yes")
        self.assertIn("href=", out["TitleHTML"])

    def test_single_row_edit_payload(self) -> None:
        edited = build_classification_update_df(
            submission_id="XYZ",
            primary_theme="Theme A",
            subtheme="Sub A",
            override_notes="Note",
        )
        self.assertEqual(list(edited.columns), ["SubmissionID", "PrimaryTheme", "Subtheme", "OverrideNotes"])
        self.assertEqual(len(edited), 1)
        self.assertEqual(str(edited.iloc[0]["SubmissionID"]), "XYZ")
        self.assertEqual(str(edited.iloc[0]["PrimaryTheme"]), "Theme A")

    def test_single_row_metadata_payload(self) -> None:
        edited = build_paper_metadata_update_df(
            submission_id="XYZ",
            title="Adjusted Title",
            full_name="Adjusted Author",
        )
        self.assertEqual(list(edited.columns), ["SubmissionID", "Title", "FullName"])
        self.assertEqual(len(edited), 1)
        self.assertEqual(str(edited.iloc[0]["SubmissionID"]), "XYZ")
        self.assertEqual(str(edited.iloc[0]["Title"]), "Adjusted Title")
        self.assertEqual(str(edited.iloc[0]["FullName"]), "Adjusted Author")

    def test_table_details_button_key_is_used(self) -> None:
        text = (APP_ROOT / "ui" / "papers.py").read_text(encoding="utf-8")
        self.assertIn('key=f"paper_row_details_{sid}"', text)
        self.assertIn('"Target Session"', text)
        self.assertIn("apply_paper_session_selection_edit", text)
        self.assertNotIn("paper_row_open_presenter_", text)
        self.assertNotIn("paper_row_open_theme_", text)
        self.assertNotIn("paper_row_open_place_", text)

    def test_session_options_rank_unassigned_active_inactive(self) -> None:
        state = SimpleNamespace(
            all_sessions=[
                SimpleNamespace(session_id="I1", session_code="S-I1", status="inactive", day_label="Day 1", time="10h00-11h00", room="R2"),
                SimpleNamespace(session_id="A2", session_code="S-A2", status="active", day_label="Day 1", time="11h00-12h00", room="R1"),
                SimpleNamespace(session_id="A1", session_code="S-A1", status="active", day_label="Day 1", time="09h00-10h00", room="R1"),
            ],
            papers=[],
        )
        options, labels = build_session_options(state)
        self.assertEqual(options[0], ("unassigned", ""))
        self.assertIn("[active]", labels[options[1]])
        self.assertIn("[active]", labels[options[2]])
        self.assertIn("[inactive]", labels[options[3]])

    def test_default_session_option_uses_paper_session_id(self) -> None:
        state = SimpleNamespace(
            all_sessions=[
                SimpleNamespace(session_id="A1", session_code="S-A1", status="active", day_label="Day 1", time="09h00-10h00", room="R1"),
            ],
            papers=[
                SimpleNamespace(
                    submission_id="P1",
                    placement_status="scheduled",
                    session_id="A1",
                )
            ],
        )
        options, _ = build_session_options(state)
        selected = default_session_option_for_paper(state, "P1", options)
        self.assertEqual(selected, ("session", "A1"))


if __name__ == "__main__":
    unittest.main()
