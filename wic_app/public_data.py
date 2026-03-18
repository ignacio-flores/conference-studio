from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from engine.config import ConferenceConfig


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATA_DIR = REPO_ROOT / "public_data"
PUBLIC_JSON_FILE = PUBLIC_DATA_DIR / "programme.json"
PUBLIC_XLSX_FILE = PUBLIC_DATA_DIR / "programme.xlsx"


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _public_talk_record(paper: object, session: object) -> Dict[str, Any]:
    return {
        "submission_id": _clean_text(getattr(paper, "submission_id", "")),
        "title": _clean_text(getattr(paper, "title", "")),
        "authors": _clean_text(getattr(paper, "full_name", "")),
        "abstract": _clean_text(getattr(paper, "abstract", "")),
        "primary_theme": _clean_text(getattr(paper, "primary_theme", getattr(session, "primary_theme", ""))),
        "subtheme": _clean_text(getattr(paper, "detailed_subtheme", getattr(session, "subtheme", ""))),
        "session_id": _clean_text(getattr(session, "session_id", "")),
        "session_code": _clean_text(getattr(session, "session_code", "")),
        "session_title": _clean_text(getattr(session, "session_title", "")),
        "day_label": _clean_text(getattr(session, "day_label", "")),
        "day_num": int(getattr(session, "day_num", 0) or 0),
        "time": _clean_text(getattr(session, "time", "")),
        "block_label": _clean_text(getattr(session, "block_label", "")),
        "block_num": int(getattr(session, "block_num", 0) or 0),
        "room": _clean_text(getattr(session, "room", "")),
        "talk_index": int(getattr(paper, "talk_index", 0) or 0),
        "talk_start_min": int(getattr(paper, "talk_start_min", 0) or 0),
        "talk_end_min": int(getattr(paper, "talk_end_min", 0) or 0),
    }


def build_public_payload(
    state: object,
    conference_config: Optional["ConferenceConfig"] = None,
    *,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    if conference_config is None:
        from engine.config import load_conference_config

        config = load_conference_config()
    else:
        config = conference_config
    timestamp = _clean_text(generated_at) or datetime.now(timezone.utc).isoformat(timespec="seconds")

    sessions: List[Dict[str, Any]] = []
    papers: List[Dict[str, Any]] = []

    active_sessions = sorted(
        list(getattr(state, "sessions", []) or []),
        key=lambda session: (
            int(getattr(session, "day_num", 0) or 0),
            int(getattr(session, "start_min", 0) or 0),
            _clean_text(getattr(session, "room", "")),
            _clean_text(getattr(session, "session_code", "")),
        ),
    )

    for session in active_sessions:
        talks: List[Dict[str, Any]] = []
        for paper in list(getattr(session, "papers", []) or []):
            if paper is None:
                continue
            talk_record = _public_talk_record(paper, session)
            talks.append(talk_record)
            papers.append(talk_record)

        sessions.append(
            {
                "session_id": _clean_text(getattr(session, "session_id", "")),
                "session_code": _clean_text(getattr(session, "session_code", "")),
                "session_title": _clean_text(getattr(session, "session_title", "")),
                "day_label": _clean_text(getattr(session, "day_label", "")),
                "day_num": int(getattr(session, "day_num", 0) or 0),
                "time": _clean_text(getattr(session, "time", "")),
                "block_label": _clean_text(getattr(session, "block_label", "")),
                "block_num": int(getattr(session, "block_num", 0) or 0),
                "room": _clean_text(getattr(session, "room", "")),
                "start_min": int(getattr(session, "start_min", 0) or 0),
                "end_min": int(getattr(session, "end_min", 0) or 0),
                "capacity": int(getattr(session, "capacity", len(talks)) or len(talks)),
                "primary_theme": _clean_text(getattr(session, "primary_theme", "")),
                "subtheme": _clean_text(getattr(session, "subtheme", "")),
                "talks": talks,
            }
        )

    return {
        "conference": {
            "title": config.conference_title,
            "subtitle": config.conference_subtitle,
            "generated_at": timestamp,
        },
        "sessions": sessions,
        "papers": sorted(
            papers,
            key=lambda paper: (
                int(paper.get("day_num", 0) or 0),
                int(paper.get("talk_start_min", 0) or 0),
                str(paper.get("room", "")),
                str(paper.get("session_code", "")),
                str(paper.get("submission_id", "")),
            ),
        ),
        "filters": {
            "days": sorted({session["day_label"] for session in sessions if session["day_label"]}),
            "rooms": sorted({session["room"] for session in sessions if session["room"]}),
            "themes": sorted({paper["primary_theme"] for paper in papers if paper["primary_theme"]}),
            "subthemes": sorted({paper["subtheme"] for paper in papers if paper["subtheme"]}),
        },
    }


def write_public_payload(payload: Dict[str, Any], output_path: Path = PUBLIC_JSON_FILE) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def load_public_payload(path: Path = PUBLIC_JSON_FILE) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
