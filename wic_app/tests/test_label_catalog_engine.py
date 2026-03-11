from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from reclassification_engine import (  # noqa: E402
    LABEL_CATALOG_HEADERS,
    LABEL_TYPE_PRIMARY,
    LABEL_TYPE_SECONDARY,
    ensure_state_files,
    load_label_catalog,
    merge_label_catalog_labels,
    write_label_catalog,
)


class LabelCatalogEngineTests(unittest.TestCase):
    def test_ensure_state_files_bootstraps_catalog_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            catalog_path = state_dir / "label_catalog.csv"
            ensure_state_files(state_dir=state_dir, label_catalog_file=catalog_path)
            self.assertTrue(catalog_path.exists())
            rows = catalog_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(rows[0].split(","), LABEL_CATALOG_HEADERS)

    def test_write_and_load_catalog_normalizes_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "label_catalog.csv"
            write_label_catalog(
                {
                    LABEL_TYPE_PRIMARY: ["Theme B", "Theme A", "Theme A", ""],
                    LABEL_TYPE_SECONDARY: ["Sub 2", "Sub 1", "Sub 1", ""],
                },
                catalog_path,
            )

            loaded = load_label_catalog(catalog_path)
            self.assertEqual(loaded[LABEL_TYPE_PRIMARY], ["Theme A", "Theme B"])
            self.assertEqual(loaded[LABEL_TYPE_SECONDARY], ["Sub 1", "Sub 2"])

            rows = catalog_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(rows[0].split(","), LABEL_CATALOG_HEADERS)

    def test_merge_catalog_adds_only_new_non_empty_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "label_catalog.csv"
            write_label_catalog(
                {
                    LABEL_TYPE_PRIMARY: ["Theme A"],
                    LABEL_TYPE_SECONDARY: ["Sub 1"],
                },
                catalog_path,
            )

            changed = merge_label_catalog_labels(
                primary_values=["Theme A", "Theme C", ""],
                secondary_values=["Sub 1", "Sub 3", ""],
                path=catalog_path,
            )
            self.assertTrue(changed)

            loaded = load_label_catalog(catalog_path)
            self.assertEqual(loaded[LABEL_TYPE_PRIMARY], ["Theme A", "Theme C"])
            self.assertEqual(loaded[LABEL_TYPE_SECONDARY], ["Sub 1", "Sub 3"])

            changed_again = merge_label_catalog_labels(
                primary_values=["Theme A"],
                secondary_values=["Sub 3"],
                path=catalog_path,
            )
            self.assertFalse(changed_again)


if __name__ == "__main__":
    unittest.main()
