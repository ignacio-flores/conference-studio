from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.labels import (  # noqa: E402
    build_bulk_primary_update_df,
    build_bulk_secondary_update_df,
    merged_primary_label_options,
    parse_label_values,
    relabel_catalog_values,
)


class LabelsViewTests(unittest.TestCase):
    def test_parse_label_values_deduplicates_and_strips(self) -> None:
        parsed = parse_label_values("  A, B ; A\nC \n  ")
        self.assertEqual(parsed, ["A", "B", "C"])

    def test_merged_primary_options_include_empty_and_deduplicate(self) -> None:
        options = merged_primary_label_options(
            theme_order=["Theme 1", "Theme 2"],
            catalog_primary_labels=["Theme 2", "Theme 3"],
            paper_primary_labels=["Theme 4", "Theme 1"],
        )
        self.assertEqual(options[0], "")
        self.assertEqual(options[1:], ["Theme 1", "Theme 2", "Theme 3", "Theme 4"])

    def test_bulk_primary_updates_preserve_secondary_and_notes(self) -> None:
        papers_df = pd.DataFrame(
            [
                {"SubmissionID": "P1", "PrimaryTheme": "A", "Subtheme": "SA", "OverrideNotes": "N1"},
                {"SubmissionID": "P2", "PrimaryTheme": "B", "Subtheme": "SB", "OverrideNotes": "N2"},
                {"SubmissionID": "P3", "PrimaryTheme": "A", "Subtheme": "SC", "OverrideNotes": "N3"},
            ]
        )

        updates = build_bulk_primary_update_df(papers_df, source_primary="A", target_primary="")
        self.assertEqual(len(updates), 2)
        self.assertEqual(updates.iloc[0]["SubmissionID"], "P1")
        self.assertEqual(updates.iloc[0]["PrimaryTheme"], "")
        self.assertEqual(updates.iloc[0]["Subtheme"], "SA")
        self.assertEqual(updates.iloc[0]["OverrideNotes"], "N1")
        self.assertEqual(updates.iloc[1]["SubmissionID"], "P3")

    def test_bulk_secondary_updates_honor_optional_primary_filter(self) -> None:
        papers_df = pd.DataFrame(
            [
                {"SubmissionID": "P1", "PrimaryTheme": "A", "Subtheme": "S1", "OverrideNotes": "N1"},
                {"SubmissionID": "P2", "PrimaryTheme": "A", "Subtheme": "S2", "OverrideNotes": "N2"},
                {"SubmissionID": "P3", "PrimaryTheme": "B", "Subtheme": "S1", "OverrideNotes": "N3"},
            ]
        )

        updates = build_bulk_secondary_update_df(
            papers_df,
            source_secondary="S1",
            target_secondary="S9",
            primary_filter="A",
        )
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates.iloc[0]["SubmissionID"], "P1")
        self.assertEqual(updates.iloc[0]["PrimaryTheme"], "A")
        self.assertEqual(updates.iloc[0]["Subtheme"], "S9")
        self.assertEqual(updates.iloc[0]["OverrideNotes"], "N1")

    def test_relabel_catalog_values_drops_source_even_when_no_papers_match(self) -> None:
        updated = relabel_catalog_values(
            {
                "primary": ["Theme A", "Theme B"],
                "secondary": ["Sub 1"],
            },
            label_type="primary",
            source_label="Theme B",
            target_label="",
        )
        self.assertEqual(updated["primary"], {"Theme A"})
        self.assertEqual(updated["secondary"], {"Sub 1"})

    def test_relabel_catalog_values_renames_secondary(self) -> None:
        updated = relabel_catalog_values(
            {
                "primary": ["Theme A"],
                "secondary": ["Sub 1", "Sub 2"],
            },
            label_type="secondary",
            source_label="Sub 2",
            target_label="Sub 9",
        )
        self.assertEqual(updated["primary"], {"Theme A"})
        self.assertEqual(updated["secondary"], {"Sub 1", "Sub 9"})


if __name__ == "__main__":
    unittest.main()
