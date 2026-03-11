from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from engine.classification import classify_papers  # noqa: E402


class ClassificationEmptyLabelTests(unittest.TestCase):
    def test_explicit_empty_sentinel_keeps_labels_blank(self) -> None:
        paper = SimpleNamespace(
            submission_id="P1",
            title="Sample Title",
            abstract="Sample Abstract",
            source_themes="",
            primary_theme="",
            detailed_subtheme="",
            secondary_tags=[],
            matched_keywords=[],
            rationale="",
            reviewed=False,
            override_notes="",
        )
        sentinel = "__WIC_EMPTY_LABEL__"
        overrides = {
            "P1": {
                "OverridePrimaryTheme": sentinel,
                "OverrideSubtheme": sentinel,
                "Reviewed": "True",
                "OverrideNotes": "blank labels",
            }
        }

        classify_papers(
            papers=[paper],
            classification_overrides=overrides,
            normalize_key=lambda text: str(text or "").lower(),
            map_source_themes=lambda raw: ["Theme A"] if str(raw or "").strip() else [],
            infer_theme_from_text=lambda text: "Theme A",
            classify_subtheme=lambda primary, text: (f"{primary} subtheme", []),
            keyword_matches=lambda text, keywords: [],
            theme_keywords={"Theme A": ["sample"]},
            parse_bool=lambda value: str(value).strip().lower() in {"1", "true", "yes"},
            empty_label_sentinel=sentinel,
        )

        self.assertEqual(paper.primary_theme, "")
        self.assertEqual(paper.detailed_subtheme, "")
        self.assertEqual(paper.override_notes, "blank labels")
        self.assertTrue(paper.reviewed)
        self.assertEqual(paper.rationale, "Mapped by manual override in curation UI.")


if __name__ == "__main__":
    unittest.main()
