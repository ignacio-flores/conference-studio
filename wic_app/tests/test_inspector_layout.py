from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import ui.inspector_layout as inspector_layout  # noqa: E402


class _FakeStreamlit:
    def __init__(self) -> None:
        self.session_state = {}
        self.markdown_calls = []

    def markdown(self, body: str, unsafe_allow_html: bool = False) -> None:
        self.markdown_calls.append((body, unsafe_allow_html))


class InspectorLayoutTests(unittest.TestCase):
    def test_sticky_css_contract_contains_expected_selectors_and_variables(self) -> None:
        css = inspector_layout._sticky_inspector_css()
        sticky_selector = '[data-testid="stHorizontalBlock"] > [data-testid="column"]:has(.wic-inspector-marker)'
        scroll_selector = f'{sticky_selector} > [data-testid="stVerticalBlock"]'

        self.assertIn("--wic-inspector-top: 0.75rem;", css)
        self.assertIn("--wic-inspector-bottom-gap: 0.75rem;", css)
        self.assertIn(
            "--wic-inspector-max-h: calc(100vh - var(--wic-inspector-top) - var(--wic-inspector-bottom-gap));",
            css,
        )
        self.assertIn(sticky_selector, css)
        self.assertIn(scroll_selector, css)
        self.assertIn("overflow-y: auto;", css)
        self.assertIn("@media (max-width: 1200px)", css)
        self.assertIn("position: static;", css)

    def test_inject_css_renders_style_block(self) -> None:
        fake_streamlit = _FakeStreamlit()
        with patch.object(inspector_layout, "st", fake_streamlit):
            inspector_layout.inject_sticky_inspector_css()

        self.assertEqual(len(fake_streamlit.markdown_calls), 1)
        self.assertTrue(fake_streamlit.markdown_calls[0][1])
        self.assertIn("<style>", fake_streamlit.markdown_calls[0][0])

    def test_render_marker_emits_hidden_scope_marker(self) -> None:
        fake_streamlit = _FakeStreamlit()
        with patch.object(inspector_layout, "st", fake_streamlit):
            inspector_layout.render_inspector_marker("programme inspector")

        self.assertEqual(len(fake_streamlit.markdown_calls), 1)
        marker_html, unsafe_html = fake_streamlit.markdown_calls[0]
        self.assertTrue(unsafe_html)
        self.assertIn("wic-inspector-marker", marker_html)
        self.assertIn("data-wic-inspector-scope='programme-inspector'", marker_html)


if __name__ == "__main__":
    unittest.main()
