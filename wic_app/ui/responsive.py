from __future__ import annotations

from typing import Optional, Tuple

MOBILE_MAX_WIDTH = 767
TABLET_MAX_WIDTH = 1023
DEFAULT_VIEWPORT_WIDTH = 1280


def normalize_viewport_width(value: object, default: int = DEFAULT_VIEWPORT_WIDTH) -> int:
    try:
        parsed = int(float(str(value).strip()))
    except Exception:
        parsed = int(default)
    if parsed <= 0:
        return int(default)
    return parsed


def parse_bool_setting(value: object, default: bool = False) -> bool:
    cleaned = str(value or "").strip().lower()
    if cleaned in {"1", "true", "yes", "on"}:
        return True
    if cleaned in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def parse_mobile_override(value: object) -> Optional[bool]:
    cleaned = str(value or "").strip().lower()
    if cleaned in {"1", "true", "yes", "on"}:
        return True
    if cleaned in {"0", "false", "no", "off"}:
        return False
    return None


def resolve_viewport_mode(
    viewport_width: object,
    force_mobile_mode: Optional[bool] = None,
) -> Tuple[str, bool]:
    width = normalize_viewport_width(viewport_width)
    if force_mobile_mode is True:
        return "mobile", True

    tier = "desktop"
    if width <= MOBILE_MAX_WIDTH:
        tier = "mobile"
    elif width <= TABLET_MAX_WIDTH:
        tier = "tablet"

    if force_mobile_mode is False:
        return tier, False
    return tier, tier == "mobile"
