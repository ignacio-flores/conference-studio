from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import ui.archived as archived_view  # noqa: E402


class ArchivedViewTests(unittest.TestCase):
    def test_resolve_archive_reason_options_merges_defaults_catalog_and_used_reasons(self) -> None:
        resolver = getattr(archived_view, "resolve_archive_reason_options", None)
        self.assertTrue(callable(resolver))
        options = resolver(
            catalog_reasons=["Withdrawn by organizers", "Other"],
            archive_overrides={
                "P1": {"ArchiveReason": "Author requested embargo"},
                "P2": {"ArchiveReason": "Duplicate submission"},
            },
        )
        self.assertEqual(
            options,
            [
                "Duplicate submission",
                "Author cancelled attendance",
                "Other",
                "Withdrawn by organizers",
                "Author requested embargo",
            ],
        )

    def test_filter_archived_papers_applies_reason_and_query(self) -> None:
        filter_fn = getattr(archived_view, "filter_archived_papers", None)
        self.assertTrue(callable(filter_fn))
        papers = [
            SimpleNamespace(submission_id="P1", title="Top incomes", full_name="Alice Example"),
            SimpleNamespace(submission_id="P2", title="Wealth taxation", full_name="Bob Example"),
            SimpleNamespace(submission_id="P3", title="Archive records", full_name="Cara Example"),
        ]
        archive_overrides = {
            "P1": {"ArchiveReason": "Duplicate submission"},
            "P2": {"ArchiveReason": "Author cancelled attendance"},
            "P3": {"ArchiveReason": "Duplicate submission"},
        }
        filtered = filter_fn(
            papers,
            archive_overrides,
            query="archive",
            reason_filter="Duplicate submission",
        )
        self.assertEqual([paper.submission_id for paper in filtered], ["P3"])

    def test_filtered_archived_submission_ids_follow_current_filters(self) -> None:
        target_ids_fn = getattr(archived_view, "filtered_archived_submission_ids", None)
        self.assertTrue(callable(target_ids_fn))
        papers = [
            SimpleNamespace(submission_id="P1", title="Top incomes", full_name="Alice Example"),
            SimpleNamespace(submission_id="P2", title="Wealth taxation", full_name="Bob Example"),
            SimpleNamespace(submission_id="P3", title="Archive records", full_name="Cara Example"),
        ]
        archive_overrides = {
            "P1": {"ArchiveReason": "Duplicate submission"},
            "P2": {"ArchiveReason": "Author cancelled attendance"},
            "P3": {"ArchiveReason": "Duplicate submission"},
        }
        self.assertEqual(
            target_ids_fn(
                papers,
                archive_overrides,
                query="example",
                reason_filter="Duplicate submission",
            ),
            ["P1", "P3"],
        )


if __name__ == "__main__":
    unittest.main()
