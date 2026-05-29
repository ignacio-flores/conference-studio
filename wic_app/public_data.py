from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from urllib.parse import urlparse

from reclassification_engine import room_sort_key

if TYPE_CHECKING:
    from engine.config import ConferenceConfig


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATA_DIR = REPO_ROOT / "public_data"
PUBLIC_JSON_FILE = PUBLIC_DATA_DIR / "programme.json"
PUBLIC_XLSX_FILE = PUBLIC_DATA_DIR / "programme.xlsx"
PUBLIC_DISPLAY_FULL = "full"
PUBLIC_DISPLAY_PUBLIC_SAFE = "public_safe"
DEFAULT_PUBLIC_EXPORT_SETTINGS = {
    "publish_display": PUBLIC_DISPLAY_FULL,
    "show_rooms": True,
    "show_moderators": True,
    "show_links": True,
}


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def resolve_public_export_settings(
    *,
    public_settings: Optional[Dict[str, object]] = None,
    publish_display: Optional[str] = None,
    show_rooms: Optional[bool] = None,
    show_moderators: Optional[bool] = None,
    show_links: Optional[bool] = None,
) -> Dict[str, object]:
    settings = dict(DEFAULT_PUBLIC_EXPORT_SETTINGS)
    normalized_publish_display = _clean_text(publish_display).lower()
    if normalized_publish_display not in {PUBLIC_DISPLAY_FULL, PUBLIC_DISPLAY_PUBLIC_SAFE}:
        normalized_publish_display = PUBLIC_DISPLAY_FULL
    settings["publish_display"] = normalized_publish_display
    if normalized_publish_display == PUBLIC_DISPLAY_PUBLIC_SAFE:
        settings["show_rooms"] = False
        settings["show_moderators"] = False
    if isinstance(public_settings, dict):
        for key in settings.keys():
            if key in public_settings:
                settings[key] = public_settings[key]
    normalized_existing_display = _clean_text(settings.get("publish_display", "")).lower()
    settings["publish_display"] = (
        normalized_existing_display
        if normalized_existing_display in {PUBLIC_DISPLAY_FULL, PUBLIC_DISPLAY_PUBLIC_SAFE}
        else normalized_publish_display
    )
    if settings["publish_display"] == PUBLIC_DISPLAY_PUBLIC_SAFE:
        settings["show_rooms"] = False
        settings["show_moderators"] = False
    if show_rooms is not None:
        settings["show_rooms"] = bool(show_rooms)
    if show_moderators is not None:
        settings["show_moderators"] = bool(show_moderators)
    if show_links is not None:
        settings["show_links"] = bool(show_links)
    settings["publish_display"] = (
        PUBLIC_DISPLAY_FULL
        if settings["show_rooms"] and settings["show_moderators"]
        else PUBLIC_DISPLAY_PUBLIC_SAFE
    )
    return {
        "publish_display": settings["publish_display"],
        "show_rooms": bool(settings["show_rooms"]),
        "show_moderators": bool(settings["show_moderators"]),
        "show_links": bool(settings["show_links"]),
    }


def _public_presenter_display(name: str, *, is_moderator: bool, show_moderators: bool) -> str:
    presenter = _clean_text(name) or "[No presenter]"
    if show_moderators and is_moderator:
        return f"{presenter} (Chair)"
    return presenter


def _public_room_display(room: object, *, show_rooms: bool) -> str:
    if not show_rooms:
        return ""
    return _clean_text(room)


def _public_paper_url(paper: object, *, show_links: bool) -> str:
    if not show_links:
        return ""
    url = _clean_text(getattr(paper, "link_to_pdf", ""))
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return url
    return ""


def _session_talks(session: object) -> List[object]:
    scheduled = [paper for paper in list(getattr(session, "papers", []) or []) if paper is not None]
    overflow = [paper for paper in list(getattr(session, "overflow_papers", []) or []) if paper is not None]
    return scheduled + overflow


def _room_label_lookup(sessions: List[object], *, show_rooms: bool) -> Dict[str, Dict[str, object]]:
    ordered_rooms = sorted(
        {
            _clean_text(getattr(session, "room", ""))
            for session in sessions
            if _clean_text(getattr(session, "room", ""))
        },
        key=room_sort_key,
    )
    lookup: Dict[str, Dict[str, object]] = {}
    for idx, room in enumerate(ordered_rooms, start=1):
        lookup[room] = {
            "room_index": idx,
            "display_room": room if show_rooms else f"Track {idx}",
        }
    return lookup


def _public_talk_record(
    paper: object,
    session: object,
    settings: Dict[str, object],
    *,
    display_room: str,
    room_index: int,
) -> Dict[str, Any]:
    authors = _clean_text(getattr(paper, "full_name", ""))
    is_moderator = bool(getattr(paper, "is_moderator", False))
    display_presenter = _public_presenter_display(
        authors,
        is_moderator=is_moderator,
        show_moderators=settings["show_moderators"],
    )
    return {
        "submission_id": _clean_text(getattr(paper, "submission_id", "")),
        "title": _clean_text(getattr(paper, "title", "")),
        "authors": authors,
        "is_moderator": is_moderator if settings["show_moderators"] else False,
        "presenter_display": display_presenter,
        "display_presenter": display_presenter,
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
        "room": _public_room_display(getattr(session, "room", ""), show_rooms=settings["show_rooms"]),
        "display_room": display_room,
        "room_index": room_index,
        "paper_url": _public_paper_url(paper, show_links=settings["show_links"]),
        "talk_index": int(getattr(paper, "talk_index", 0) or 0),
        "talk_start_min": int(getattr(paper, "talk_start_min", 0) or 0) or int(getattr(session, "start_min", 0) or 0),
        "talk_end_min": int(getattr(paper, "talk_end_min", 0) or 0) or int(getattr(session, "end_min", 0) or 0),
    }


def build_public_payload(
    state: object,
    conference_config: Optional["ConferenceConfig"] = None,
    *,
    generated_at: Optional[str] = None,
    public_settings: Optional[Dict[str, object]] = None,
    publish_display: Optional[str] = None,
    show_rooms: Optional[bool] = None,
    show_moderators: Optional[bool] = None,
    show_links: Optional[bool] = None,
) -> Dict[str, Any]:
    if conference_config is None:
        from engine.config import load_conference_config

        config = load_conference_config()
    else:
        config = conference_config
    timestamp = _clean_text(generated_at) or datetime.now(timezone.utc).isoformat(timespec="seconds")
    settings = resolve_public_export_settings(
        public_settings=public_settings,
        publish_display=publish_display,
        show_rooms=show_rooms,
        show_moderators=show_moderators,
        show_links=show_links,
    )

    sessions: List[Dict[str, Any]] = []
    papers: List[Dict[str, Any]] = []

    active_sessions = sorted(
        list(getattr(state, "sessions", []) or []),
        key=lambda session: (
            int(getattr(session, "day_num", 0) or 0),
            int(getattr(session, "start_min", 0) or 0),
            room_sort_key(_clean_text(getattr(session, "room", ""))),
            _clean_text(getattr(session, "session_code", "")),
        ),
    )
    room_lookup = _room_label_lookup(active_sessions, show_rooms=settings["show_rooms"])

    for session in active_sessions:
        raw_room = _clean_text(getattr(session, "room", ""))
        room_meta = room_lookup.get(raw_room, {"room_index": 0, "display_room": _public_room_display(raw_room, show_rooms=True)})
        display_room = _clean_text(room_meta.get("display_room", ""))
        room_index = int(room_meta.get("room_index", 0) or 0)
        talks: List[Dict[str, Any]] = []
        for paper in _session_talks(session):
            talk_record = _public_talk_record(
                paper,
                session,
                settings,
                display_room=display_room,
                room_index=room_index,
            )
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
                "room": _public_room_display(raw_room, show_rooms=settings["show_rooms"]),
                "display_room": display_room,
                "room_index": room_index,
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
        "settings": settings,
        "public_settings": settings,
        "sessions": sessions,
        "papers": sorted(
            papers,
            key=lambda paper: (
                int(paper.get("day_num", 0) or 0),
                int(paper.get("talk_start_min", 0) or 0),
                int(paper.get("room_index", 0) or 0),
                str(paper.get("session_code", "")),
                str(paper.get("submission_id", "")),
            ),
        ),
        "filters": {
            "days": sorted({session["day_label"] for session in sessions if session["day_label"]}),
            "rooms": [room_lookup[room]["display_room"] for room in sorted(room_lookup.keys(), key=room_sort_key)],
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
