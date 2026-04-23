from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


class PublicWwwLayoutTests(unittest.TestCase):
    def test_index_html_references_static_assets_and_programme_first_regions(self) -> None:
        text = (APP_ROOT / "public_www" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="assets/styles.css"', text)
        self.assertIn('src="assets/app.js"', text)
        self.assertIn('data-view="programme"', text)
        self.assertIn('data-view="papers"', text)
        self.assertIn('id="day-switcher"', text)
        self.assertIn('id="programme-view"', text)
        self.assertIn('id="papers-view"', text)
        self.assertIn('id="download-link"', text)
        self.assertIn('id="session-detail-template"', text)
        self.assertIn('id="talk-row-template"', text)

    def test_stylesheet_contains_editorial_and_responsive_hooks(self) -> None:
        text = (APP_ROOT / "public_www" / "assets" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("--paper-bg", text)
        self.assertIn("--ink", text)
        self.assertIn(".programme-block", text)
        self.assertIn(".session-card", text)
        self.assertIn(".talk-row", text)
        self.assertIn(".abstract-panel", text)
        self.assertIn("@media (max-width: 900px)", text)
        self.assertIn(".session-card:hover", text)
        self.assertIn(".is-expanded", text)

    def test_app_js_contains_rendering_and_interaction_hooks(self) -> None:
        text = (APP_ROOT / "public_www" / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("fetch('data/programme.json')", text)
        self.assertIn("renderProgramme", text)
        self.assertIn("renderPapers", text)
        self.assertIn("renderDaySwitcher", text)
        self.assertIn("toggleSession", text)
        self.assertIn("toggleAbstract", text)
        self.assertIn("mouseover", text)
        self.assertIn("click", text)
        self.assertIn("activeDay", text)
        self.assertIn("programme-view", text)
        self.assertIn("presenter_display", text)


if __name__ == "__main__":
    unittest.main()
