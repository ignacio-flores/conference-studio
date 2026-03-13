from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.responsive import (  # noqa: E402
    MOBILE_MAX_WIDTH,
    TABLET_MAX_WIDTH,
    normalize_viewport_width,
    parse_mobile_override,
    resolve_viewport_mode,
)


class ResponsiveViewportTests(unittest.TestCase):
    def test_normalize_viewport_width_uses_default_for_invalid_values(self) -> None:
        self.assertEqual(normalize_viewport_width("", default=1200), 1200)
        self.assertEqual(normalize_viewport_width("bad", default=1200), 1200)
        self.assertEqual(normalize_viewport_width(0, default=1200), 1200)

    def test_resolve_viewport_mode_uses_mobile_tablet_desktop_thresholds(self) -> None:
        self.assertEqual(resolve_viewport_mode(MOBILE_MAX_WIDTH), ("mobile", True))
        self.assertEqual(resolve_viewport_mode(MOBILE_MAX_WIDTH + 1), ("tablet", False))
        self.assertEqual(resolve_viewport_mode(TABLET_MAX_WIDTH), ("tablet", False))
        self.assertEqual(resolve_viewport_mode(TABLET_MAX_WIDTH + 1), ("desktop", False))

    def test_resolve_viewport_mode_obeys_force_mobile_override(self) -> None:
        self.assertEqual(resolve_viewport_mode(1600, force_mobile_mode=True), ("mobile", True))
        self.assertEqual(resolve_viewport_mode(390, force_mobile_mode=False), ("mobile", False))

    def test_parse_mobile_override_handles_true_false_and_empty(self) -> None:
        self.assertTrue(parse_mobile_override("1"))
        self.assertFalse(parse_mobile_override("0"))
        self.assertIsNone(parse_mobile_override(""))
        self.assertIsNone(parse_mobile_override("invalid"))


if __name__ == "__main__":
    unittest.main()
