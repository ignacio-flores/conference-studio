from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFERENCE_CONFIG_PATH = APP_DIR / "assets" / "conference.default.json"
CONFIG_ENV_VAR = "WIC_CONFERENCE_CONFIG"


@dataclass(frozen=True)
class SubthemeRule:
    label: str
    keywords: Tuple[str, ...]


@dataclass(frozen=True)
class ThemesConfig:
    order: Tuple[str, ...]
    short: Dict[str, str]
    alias: Dict[str, str]
    keywords: Dict[str, Tuple[str, ...]]
    subtheme_rules: Dict[str, Tuple[SubthemeRule, ...]]


@dataclass(frozen=True)
class SkipTimeWindow:
    day_label: str
    time_label: str

    def matches(self, day_label: str, time_label: str) -> bool:
        return self.day_label == day_label and self.time_label.strip() == time_label.strip()


@dataclass(frozen=True)
class ExtraRoomsRule:
    day_label: str
    block_nums: Optional[Tuple[int, ...]]
    rooms: Tuple[str, ...]

    def matches(self, day_label: str, block_num: int) -> bool:
        day_ok = self.day_label == "*" or self.day_label == day_label
        block_ok = self.block_nums is None or block_num in self.block_nums
        return day_ok and block_ok


@dataclass(frozen=True)
class ProgrammeParsingConfig:
    room_header_row: int
    room_column_start: int
    room_column_end: int
    room_name_pattern: str
    scan_row_start: int
    scan_row_end: int
    block_column: int
    time_column: int
    session_required_token: str
    optional_token: str
    session_label_regex: str
    skip_time_windows: Tuple[SkipTimeWindow, ...]
    extra_rooms: Tuple[ExtraRoomsRule, ...]


@dataclass(frozen=True)
class ParsingConfig:
    submissions_sheet: str
    accepted_reviewer_scores: Tuple[str, ...]
    programme: ProgrammeParsingConfig


@dataclass(frozen=True)
class ForbiddenTimeWindow:
    day_num: int
    time_label: str


@dataclass(frozen=True)
class ValidationConfig:
    expected_slots: int
    expected_reserve_slots: int
    strict_expected_slots: bool
    strict_expected_reserve_slots: bool
    forbidden_time_windows: Tuple[ForbiddenTimeWindow, ...]
    forbidden_block_tokens: Tuple[str, ...]


@dataclass(frozen=True)
class StructureConfig:
    default_session_capacity: int
    allow_duplicate_day_time_room: bool
    enforce_unique_session_code: bool


@dataclass(frozen=True)
class ConferenceConfig:
    conference_title: str
    conference_subtitle: str
    files: Dict[str, str]
    days: Tuple[str, ...]
    room_priority: Dict[str, int]
    themes: ThemesConfig
    parsing: ParsingConfig
    validation: ValidationConfig
    structure: StructureConfig

    @property
    def day_to_num(self) -> Dict[str, int]:
        return {day: idx for idx, day in enumerate(self.days, start=1)}

    def signature(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _read_raw_config(path: Path) -> Dict[str, Any]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "YAML config requires PyYAML. Install it or use JSON for conference config."
            ) from exc
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise RuntimeError(f"Conference config must be an object: {path}")
    return data


def _to_str_tuple(items: Sequence[Any]) -> Tuple[str, ...]:
    return tuple(str(item) for item in items)


def _parse_themes(raw: Dict[str, Any]) -> ThemesConfig:
    order = _to_str_tuple(raw.get("order", []))
    short = {str(k): str(v) for k, v in dict(raw.get("short", {})).items()}
    alias = {str(k): str(v) for k, v in dict(raw.get("alias", {})).items()}
    keywords = {
        str(theme): _to_str_tuple(words)
        for theme, words in dict(raw.get("keywords", {})).items()
    }

    subtheme_rules: Dict[str, Tuple[SubthemeRule, ...]] = {}
    for theme, rules in dict(raw.get("subtheme_rules", {})).items():
        parsed_rules: List[SubthemeRule] = []
        for rule in list(rules or []):
            if not isinstance(rule, dict):
                continue
            parsed_rules.append(
                SubthemeRule(
                    label=str(rule.get("label", "")),
                    keywords=_to_str_tuple(rule.get("keywords", [])),
                )
            )
        subtheme_rules[str(theme)] = tuple(parsed_rules)

    return ThemesConfig(
        order=order,
        short=short,
        alias=alias,
        keywords=keywords,
        subtheme_rules=subtheme_rules,
    )


def _parse_parsing(raw: Dict[str, Any]) -> ParsingConfig:
    programme_raw = dict(raw.get("programme", {}))

    skip_windows: List[SkipTimeWindow] = []
    for row in list(programme_raw.get("skip_time_windows", [])):
        if not isinstance(row, dict):
            continue
        skip_windows.append(
            SkipTimeWindow(
                day_label=str(row.get("day_label", "")),
                time_label=str(row.get("time_label", "")),
            )
        )

    extra_rooms: List[ExtraRoomsRule] = []
    for row in list(programme_raw.get("extra_rooms", [])):
        if not isinstance(row, dict):
            continue
        block_nums_raw = row.get("block_nums", [])
        if block_nums_raw == "*" or block_nums_raw is None:
            block_nums: Optional[Tuple[int, ...]] = None
        else:
            block_nums = tuple(int(v) for v in list(block_nums_raw))
        extra_rooms.append(
            ExtraRoomsRule(
                day_label=str(row.get("day_label", "*")),
                block_nums=block_nums,
                rooms=_to_str_tuple(row.get("rooms", [])),
            )
        )

    return ParsingConfig(
        submissions_sheet=str(raw.get("submissions_sheet", "Sheet1")),
        accepted_reviewer_scores=_to_str_tuple(raw.get("accepted_reviewer_scores", ["1"])),
        programme=ProgrammeParsingConfig(
            room_header_row=int(programme_raw.get("room_header_row", 3)),
            room_column_start=int(programme_raw.get("room_column_start", 4)),
            room_column_end=int(programme_raw.get("room_column_end", 39)),
            room_name_pattern=str(programme_raw.get("room_name_pattern", r"^(Amphi|R\d+-\d+)$")),
            scan_row_start=int(programme_raw.get("scan_row_start", 1)),
            scan_row_end=int(programme_raw.get("scan_row_end", 89)),
            block_column=int(programme_raw.get("block_column", 3)),
            time_column=int(programme_raw.get("time_column", 2)),
            session_required_token=str(programme_raw.get("session_required_token", "SESSION")),
            optional_token=str(programme_raw.get("optional_token", "OPTIONAL")),
            session_label_regex=str(programme_raw.get("session_label_regex", r"SESSION\s*(\d+)")),
            skip_time_windows=tuple(skip_windows),
            extra_rooms=tuple(extra_rooms),
        ),
    )


def _parse_validation(raw: Dict[str, Any]) -> ValidationConfig:
    forbidden_windows: List[ForbiddenTimeWindow] = []
    for row in list(raw.get("forbidden_time_windows", [])):
        if not isinstance(row, dict):
            continue
        forbidden_windows.append(
            ForbiddenTimeWindow(
                day_num=int(row.get("day_num", 0)),
                time_label=str(row.get("time_label", "")),
            )
        )

    return ValidationConfig(
        expected_slots=int(raw.get("expected_slots", 75)),
        expected_reserve_slots=int(raw.get("expected_reserve_slots", 3)),
        strict_expected_slots=bool(raw.get("strict_expected_slots", False)),
        strict_expected_reserve_slots=bool(raw.get("strict_expected_reserve_slots", False)),
        forbidden_time_windows=tuple(forbidden_windows),
        forbidden_block_tokens=_to_str_tuple(raw.get("forbidden_block_tokens", ["OPTIONAL"])),
    )


def _parse_structure(raw: Dict[str, Any]) -> StructureConfig:
    return StructureConfig(
        default_session_capacity=max(1, int(raw.get("default_session_capacity", 4))),
        allow_duplicate_day_time_room=bool(raw.get("allow_duplicate_day_time_room", False)),
        enforce_unique_session_code=bool(raw.get("enforce_unique_session_code", True)),
    )


def resolve_config_path(config_path: Optional[Path] = None) -> Path:
    if config_path is not None:
        return Path(config_path).expanduser().resolve()
    env_value = os.environ.get(CONFIG_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return DEFAULT_CONFERENCE_CONFIG_PATH


def load_conference_config(config_path: Optional[Path] = None) -> ConferenceConfig:
    path = resolve_config_path(config_path)
    raw = _read_raw_config(path)

    return ConferenceConfig(
        conference_title=str(raw.get("conference_title", "World Inequality Conference")),
        conference_subtitle=str(raw.get("conference_subtitle", "Programme")),
        files={str(k): str(v) for k, v in dict(raw.get("files", {})).items()},
        days=_to_str_tuple(raw.get("days", [])),
        room_priority={str(k): int(v) for k, v in dict(raw.get("room_priority", {})).items()},
        themes=_parse_themes(dict(raw.get("themes", {}))),
        parsing=_parse_parsing(dict(raw.get("parsing", {}))),
        validation=_parse_validation(dict(raw.get("validation", {}))),
        structure=_parse_structure(dict(raw.get("structure", {}))),
    )
