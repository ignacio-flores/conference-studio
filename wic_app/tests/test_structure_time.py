from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.structure_time import (  # noqa: E402
    build_time_label,
    minutes_to_clock,
    parse_clock_minutes,
    parse_positive_int,
    resolve_session_time_inputs,
)


class StructureTimeTests(unittest.TestCase):
    def test_parse_clock_minutes_valid_formats(self) -> None:
        self.assertEqual(parse_clock_minutes("09:30", default=0), 570)
        self.assertEqual(parse_clock_minutes("9h30", default=0), 570)
        self.assertEqual(parse_clock_minutes("570", default=0), 570)

    def test_parse_clock_minutes_invalid_fallback(self) -> None:
        self.assertEqual(parse_clock_minutes("", default=600), 600)
        self.assertEqual(parse_clock_minutes("bad", default=600), 600)
        self.assertEqual(parse_clock_minutes("12:99", default=600), 600)
        self.assertEqual(parse_clock_minutes("77:00", default=600), 600)

    def test_parse_positive_int_clamps(self) -> None:
        self.assertEqual(parse_positive_int("5", default=9), 5)
        self.assertEqual(parse_positive_int("0", default=9), 9)
        self.assertEqual(parse_positive_int("-2", default=9), 9)
        self.assertEqual(parse_positive_int("bad", default=9), 9)

    def test_build_time_label_is_deterministic(self) -> None:
        self.assertEqual(build_time_label(570, 660), "9h30-11h00")
        self.assertEqual(build_time_label(960, 1050), "16h00-17h30")

    def test_resolve_session_time_inputs_defaults_and_mapping(self) -> None:
        start_min, duration_min, end_min, label = resolve_session_time_inputs(
            start_time_value="",
            duration_value="",
            current_start_min=570,
            current_end_min=660,
            default_duration_min=90,
        )
        self.assertEqual(start_min, 570)
        self.assertEqual(duration_min, 90)
        self.assertEqual(end_min, 660)
        self.assertEqual(label, "9h30-11h00")

        start_min, duration_min, end_min, label = resolve_session_time_inputs(
            start_time_value="10:00",
            duration_value="bad",
            current_start_min=570,
            current_end_min=660,
            default_duration_min=90,
        )
        self.assertEqual(start_min, 600)
        self.assertEqual(duration_min, 90)
        self.assertEqual(end_min, 690)
        self.assertEqual(label, "10h00-11h30")
        self.assertEqual(minutes_to_clock(end_min), "11:30")


if __name__ == "__main__":
    unittest.main()
