from __future__ import annotations

import re
from typing import Tuple


def parse_positive_int(raw: object, default: int = 0) -> int:
    try:
        value = int(str(raw).strip())
        return value if value > 0 else int(default)
    except Exception:
        return int(default)


def parse_clock_minutes(value: object, default: int) -> int:
    text = str(value or "").strip()
    if not text:
        return int(default)
    match = re.match(r"^\s*(\d{1,2})\s*[:hH]\s*(\d{1,2})\s*$", text)
    if match is None:
        try:
            return int(float(text))
        except Exception:
            return int(default)
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour < 0 or hour > 47 or minute < 0 or minute > 59:
        return int(default)
    return hour * 60 + minute


def minutes_to_clock(total_minutes: int) -> str:
    total = max(0, int(total_minutes))
    return f"{total // 60:02d}:{total % 60:02d}"


def minutes_to_hhmm_label(total_minutes: int) -> str:
    total = max(0, int(total_minutes))
    return f"{total // 60}h{total % 60:02d}"


def build_time_label(start_min: int, end_min: int) -> str:
    start = max(0, int(start_min))
    end = max(start + 1, int(end_min))
    return f"{minutes_to_hhmm_label(start)}-{minutes_to_hhmm_label(end)}"


def resolve_session_time_inputs(
    start_time_value: object,
    duration_value: object,
    current_start_min: int,
    current_end_min: int,
    default_duration_min: int,
) -> Tuple[int, int, int, str]:
    current_start = int(current_start_min)
    current_end = int(current_end_min)
    current_duration = max(1, current_end - current_start)
    fallback_duration = current_duration if current_duration > 0 else max(1, int(default_duration_min))

    start_min = parse_clock_minutes(start_time_value, default=current_start)
    duration_min = parse_positive_int(duration_value, default=fallback_duration)
    end_min = start_min + duration_min
    return start_min, duration_min, end_min, build_time_label(start_min, end_min)
