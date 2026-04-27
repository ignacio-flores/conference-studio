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
        self.assertIn("Parallel Sessions", text)
        self.assertIn("This programme covers parallel paper sessions only.", text)
        self.assertIn('data-view="programme"', text)
        self.assertIn('data-view="papers"', text)
        self.assertIn('id="day-switcher"', text)
        self.assertIn('id="programme-view"', text)
        self.assertIn('id="papers-view"', text)
        self.assertIn('id="download-link"', text)
        self.assertIn('id="session-detail-template"', text)
        self.assertIn('id="talk-row-template"', text)
        self.assertIn('class="talk-title talk-title-link"', text)
        self.assertIn('class="abstract-toggle"', text)

    def test_stylesheet_contains_editorial_and_responsive_hooks(self) -> None:
        text = (APP_ROOT / "public_www" / "assets" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("--paper-bg", text)
        self.assertIn("--ink", text)
        self.assertIn("--coral", text)
        self.assertIn(".programme-block", text)
        self.assertIn(".programme-workspace", text)
        self.assertIn(".programme-workspace-layout", text)
        self.assertIn(".programme-workspace-layout.has-panel", text)
        self.assertIn(".programme-timetable-grid", text)
        self.assertIn(".programme-timetable-room", text)
        self.assertIn(".programme-timetable-time", text)
        self.assertIn(".programme-timetable-cell", text)
        self.assertIn(".session-panel", text)
        self.assertIn(".session-panel.is-open", text)
        self.assertIn(".programme-timetable-cell .session-room", text)
        self.assertIn(".session-card", text)
        self.assertIn(".talk-row", text)
        self.assertIn(".abstract-panel", text)
        self.assertIn(".talk-title-link", text)
        self.assertIn(".abstract-toggle", text)
        self.assertIn("@media (max-width: 900px)", text)
        self.assertIn(".session-card:hover", text)
        self.assertIn(".is-expanded", text)

    def test_app_js_contains_rendering_and_interaction_hooks(self) -> None:
        text = (APP_ROOT / "public_www" / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("fetch('data/programme.json')", text)
        self.assertIn("renderProgramme", text)
        self.assertIn("renderPapers", text)
        self.assertIn("renderDaySwitcher", text)
        self.assertIn("Parallel Sessions", text)
        self.assertIn("This programme covers parallel paper sessions only.", text)
        self.assertIn("buildProgrammeMatrix", text)
        self.assertIn("renderProgrammeMatrix", text)
        self.assertIn("renderSessionPanel", text)
        self.assertIn("closeSessionPanel", text)
        self.assertIn("has-panel", text)
        self.assertIn("programme-timetable-grid", text)
        self.assertIn("session-panel", text)
        self.assertIn("toggleSession", text)
        self.assertIn("toggleAbstract", text)
        self.assertIn("click", text)
        self.assertIn("activeDay", text)
        self.assertIn("programme-view", text)
        self.assertIn("presenter_display", text)
        self.assertIn("display_room", text)
        self.assertIn("display_presenter", text)
        self.assertIn("paper_url", text)
        self.assertIn("settings", text)
        self.assertIn("buildPaperTitleLink", text)
        self.assertIn("Show abstract", text)
        self.assertNotIn("paperLinkLabel", text)
        self.assertNotIn("time.textContent = cleanText(session.time)", text)
        self.assertIn("pendingProgrammeFocus", text)
        self.assertIn("scrollIntoView", text)
        self.assertNotIn("renderStructureBlock", text)
        self.assertNotIn("mouseover", text)
        self.assertNotIn("hoveredAbstractId", text)


if __name__ == "__main__":
    unittest.main()
