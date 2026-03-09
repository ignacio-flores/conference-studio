from __future__ import annotations

from datetime import datetime
import html
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from engine.config import load_conference_config
from exporters.publish import export_draft_workbook, export_publish_excel, export_publish_pdf
from reclassification_engine import (
    CLASSIFICATION_OVERRIDES_FILE,
    MANUAL_TALKS_FILE,
    PAPER_METADATA_OVERRIDES_FILE,
    PAPER_PLACEMENTS_FILE,
    PROGRAMME_LAYOUT_OVERRIDES_FILE,
    SESSION_STRUCTURE_FILE,
    SESSION_NAME_OVERRIDES_FILE,
    THEME_ORDER,
    add_block_row_sessions,
    clear_day_sessions,
    clone_day_structure,
    bulk_add_room_sessions,
    build_programme_state,
    clear_session,
    create_manual_talk,
    create_session,
    delete_day_sessions,
    format_minutes,
    load_manual_talks,
    load_classification_overrides,
    load_paper_metadata_overrides,
    load_paper_placements,
    load_session_structure_rows,
    load_session_name_overrides,
    parse_start_minutes,
    papers_to_rows,
    programme_talk_rows,
    relabel_day_sessions,
    rename_room_for_day,
    remove_session,
    restore_session,
    room_sort_key,
    update_session_structure_row,
    validate_session_structure_rows,
    write_classification_overrides,
    write_paper_metadata_overrides,
    write_paper_placements,
    write_session_structure_rows,
    write_session_name_overrides,
)
from ui.actions import render_top_actions
from ui.papers import render_paper_list_tab
from ui.programme import render_programme_tab as render_programme_tab_view
from ui.structure import (
    block_filter_labels_for_day,
    build_empty_slot_selection,
    build_new_room_selection,
    build_room_selection,
    build_session_selection,
    collect_visible_sessions,
    group_sessions_for_structure_matrix,
    render_structure_inspector,
    render_structure_matrix,
    structure_session_counts,
)
from ui.structure_time import (
    build_time_label,
    minutes_to_clock,
    parse_clock_minutes,
    resolve_session_time_inputs,
)

NOTE_SPLIT_RE = re.compile(r"note\s*to\s*conference\s*organizers", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")

APP_TITLE = "Conference Studio"
TAB_LABELS = ["Programme", "Structure", "Paper List", "Checks"]
UNDO_STACK_LIMIT = 20
DEFAULT_CONFERENCE_LABEL = "WIC 2026"
UI_SETTINGS_FILE = Path(__file__).resolve().parent / "state" / "ui_settings.json"


st.set_page_config(page_title=APP_TITLE, layout="wide")
st.markdown(
    """
<style>
div.stButton > button[kind="primary"] {
    background-color: #e6f2ff !important;
    color: #0b3a66 !important;
    border: 1px solid #a8cffa !important;
}
div.stButton > button[kind="primary"]:hover {
    background-color: #d6e9ff !important;
    border-color: #8bbcf2 !important;
}
div.stButton > button[kind="primary"]:focus {
    box-shadow: 0 0 0 0.2rem rgba(70, 140, 220, 0.25) !important;
}
</style>
""",
    unsafe_allow_html=True,
)


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _strip_html_fragments(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = HTML_TAG_RE.sub("", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def _clean_display_text(value: object) -> str:
    return _strip_html_fragments(value)


def _preview_abstract(value: object) -> str:
    clean = _strip_html_fragments(value)
    match = NOTE_SPLIT_RE.search(clean)
    if match:
        clean = clean[: match.start()]
    return clean.strip()


def _app_config_path() -> Optional[Path]:
    config_env = os.environ.get("WIC_CONFERENCE_CONFIG", "").strip()
    return Path(config_env) if config_env else None


def _load_state():
    config_path = _app_config_path()
    return build_programme_state(
        classification_overrides_path=CLASSIFICATION_OVERRIDES_FILE,
        session_name_overrides_path=SESSION_NAME_OVERRIDES_FILE,
        programme_layout_overrides_path=PROGRAMME_LAYOUT_OVERRIDES_FILE,
        paper_metadata_overrides_path=PAPER_METADATA_OVERRIDES_FILE,
        config_path=config_path,
    )


def _read_state_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_state_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _load_ui_settings() -> Dict[str, object]:
    if not UI_SETTINGS_FILE.exists():
        return {}
    try:
        payload = json.loads(UI_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_ui_settings(payload: Dict[str, object]) -> None:
    UI_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    UI_SETTINGS_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _save_conference_label(label: object) -> None:
    cleaned = _normalize_text(label) or DEFAULT_CONFERENCE_LABEL
    st.session_state.conference_label = cleaned
    payload = _load_ui_settings()
    payload["conference_label"] = cleaned
    payload["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    _write_ui_settings(payload)


def _init_session_state() -> None:
    if "wic_state" not in st.session_state:
        st.session_state.wic_state = _load_state()
    if "undo_stack" not in st.session_state or not isinstance(st.session_state.undo_stack, list):
        st.session_state.undo_stack = []
    legacy_last_change = st.session_state.pop("last_change", None)
    if legacy_last_change and isinstance(legacy_last_change, dict):
        st.session_state.undo_stack.append(legacy_last_change)
        st.session_state.undo_stack = st.session_state.undo_stack[-UNDO_STACK_LIMIT:]
    if "flash_message" not in st.session_state:
        st.session_state.flash_message = ""
    if "structure_selection" not in st.session_state:
        st.session_state.structure_selection = {}
    if "active_tab" not in st.session_state or st.session_state.active_tab not in TAB_LABELS:
        st.session_state.active_tab = TAB_LABELS[0]
    settings = _load_ui_settings()
    saved_label = _normalize_text(settings.get("conference_label", ""))
    if "conference_label" not in st.session_state:
        st.session_state.conference_label = saved_label or DEFAULT_CONFERENCE_LABEL
    legacy_input = _normalize_text(st.session_state.pop("conference_label_input", ""))
    st.session_state.pop("conference_label_input_src", None)
    if "conference_label_draft" not in st.session_state:
        st.session_state.conference_label_draft = legacy_input or st.session_state.conference_label
    if "conference_edit_mode" not in st.session_state:
        st.session_state.conference_edit_mode = False
    if not saved_label:
        _save_conference_label(st.session_state.conference_label)


def _snapshot_for_undo() -> Dict[str, object]:
    tracked_files = [
        CLASSIFICATION_OVERRIDES_FILE,
        SESSION_NAME_OVERRIDES_FILE,
        PROGRAMME_LAYOUT_OVERRIDES_FILE,
        SESSION_STRUCTURE_FILE,
        PAPER_PLACEMENTS_FILE,
        PAPER_METADATA_OVERRIDES_FILE,
        MANUAL_TALKS_FILE,
    ]
    return {
        "files": {str(path): _read_state_file(path) for path in tracked_files},
        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
    }


def _push_undo_snapshot(snapshot: Optional[Dict[str, object]] = None) -> None:
    stack = st.session_state.get("undo_stack")
    if not isinstance(stack, list):
        stack = []
    stack.append(snapshot or _snapshot_for_undo())
    st.session_state.undo_stack = stack[-UNDO_STACK_LIMIT:]


def _undo_count() -> int:
    stack = st.session_state.get("undo_stack")
    if not isinstance(stack, list):
        return 0
    return len(stack)


def _refresh_state(message: str = "") -> None:
    st.session_state.wic_state = _load_state()
    if message:
        st.session_state.flash_message = message


def _normalize_layout_override_row(row: Dict[str, object], now: str) -> Dict[str, str]:
    status = _normalize_text(row.get("PlacementStatus", "scheduled")).lower()
    if status not in {"scheduled", "unassigned", "overflow"}:
        status = "scheduled"

    session_id = _normalize_text(row.get("SessionId", ""))
    talk_index = _normalize_text(row.get("TalkIndex", ""))
    overflow_order = _normalize_text(row.get("OverflowOrder", ""))

    if status == "unassigned":
        session_id = ""
        talk_index = ""
        overflow_order = ""
    elif status == "scheduled":
        overflow_order = ""
    elif status == "overflow":
        talk_index = ""

    return {
        "SubmissionID": _normalize_text(row.get("SubmissionID", "")),
        "PlacementStatus": status,
        "SessionId": session_id,
        "TalkIndex": talk_index,
        "OverflowOrder": overflow_order,
        "UpdatedAt": _normalize_text(row.get("UpdatedAt", "")) or now,
    }


def _apply_classification_edits_if_changed(edited_df: pd.DataFrame) -> bool:
    if edited_df.empty:
        return False

    state = st.session_state.wic_state
    current_map = {
        paper.submission_id: {
            "theme": _normalize_text(paper.primary_theme),
            "subtheme": _normalize_text(paper.detailed_subtheme),
            "notes": _normalize_text(paper.override_notes),
        }
        for paper in state.papers
    }

    existing_overrides = load_classification_overrides(CLASSIFICATION_OVERRIDES_FILE)
    now = datetime.utcnow().isoformat(timespec="seconds")
    changed = False
    snapshot: Optional[Dict[str, object]] = None

    for _, row in edited_df.iterrows():
        sid = _normalize_text(row.get("SubmissionID", ""))
        if not sid or sid not in current_map:
            continue

        theme = _normalize_text(row.get("PrimaryTheme", ""))
        subtheme = _normalize_text(row.get("Subtheme", ""))
        notes = _normalize_text(row.get("OverrideNotes", ""))

        current = current_map[sid]
        if theme == current["theme"] and subtheme == current["subtheme"] and notes == current["notes"]:
            continue

        if snapshot is None:
            snapshot = _snapshot_for_undo()

        existing_overrides[sid] = {
            "SubmissionID": sid,
            "OverridePrimaryTheme": theme,
            "OverrideSubtheme": subtheme,
            "Reviewed": "True",
            "OverrideNotes": notes,
            "UpdatedAt": now,
        }
        changed = True

    if not changed:
        return False

    _push_undo_snapshot(snapshot)
    write_classification_overrides(existing_overrides.values(), CLASSIFICATION_OVERRIDES_FILE)
    _refresh_state("Applied paper classification changes.")
    return True


def _apply_paper_metadata_edits_if_changed(edited_df: pd.DataFrame) -> bool:
    if edited_df.empty:
        return False

    state = st.session_state.wic_state
    current_map = {
        paper.submission_id: {
            "title": _normalize_text(paper.title),
            "author": _normalize_text(paper.full_name),
        }
        for paper in state.papers
    }
    existing_overrides = load_paper_metadata_overrides(PAPER_METADATA_OVERRIDES_FILE)
    merged = dict(existing_overrides)
    now = datetime.utcnow().isoformat(timespec="seconds")
    changed = False
    snapshot: Optional[Dict[str, object]] = None

    for _, row in edited_df.iterrows():
        sid = _normalize_text(row.get("SubmissionID", ""))
        if not sid or sid not in current_map:
            continue

        new_title = _normalize_text(row.get("Title", ""))
        new_author = _normalize_text(row.get("FullName", ""))
        current = current_map[sid]
        if new_title == current["title"] and new_author == current["author"]:
            continue

        if snapshot is None:
            snapshot = _snapshot_for_undo()

        merged[sid] = {
            "SubmissionID": sid,
            "TitleOverride": new_title,
            "AuthorOverride": new_author,
            "UpdatedAt": now,
        }
        changed = True

    if not changed:
        return False

    _push_undo_snapshot(snapshot)
    write_paper_metadata_overrides(merged.values(), PAPER_METADATA_OVERRIDES_FILE)
    _refresh_state("Applied paper metadata changes.")
    return True


def _apply_paper_session_selection_edit(submission_id: str, target_selection: tuple[str, str]) -> bool:
    sid = _normalize_text(submission_id)
    if not sid:
        return False

    kind = _normalize_text(target_selection[0] if isinstance(target_selection, tuple) and len(target_selection) > 0 else "")
    target_session_id = _normalize_text(
        target_selection[1] if isinstance(target_selection, tuple) and len(target_selection) > 1 else ""
    )

    state = st.session_state.wic_state
    paper = next((candidate for candidate in state.papers if _normalize_text(candidate.submission_id) == sid), None)
    if paper is None:
        st.error(f"Paper {sid} was not found.")
        return False

    current_status = _normalize_text(getattr(paper, "placement_status", "")).lower()
    current_session_id = (
        _normalize_text(getattr(paper, "session_id", "")) if current_status in {"scheduled", "overflow"} else ""
    )

    if kind == "unassigned":
        if not current_session_id:
            return False
        return _apply_layout_updates(
            {
                sid: {
                    "PlacementStatus": "unassigned",
                    "SessionId": "",
                    "TalkIndex": "",
                    "OverflowOrder": "",
                }
            },
            f"Moved {sid} to unassigned.",
        )

    if kind != "session" or not target_session_id:
        st.error("Select a target session or unassigned.")
        return False
    if target_session_id == current_session_id:
        return False

    target_session = next(
        (session for session in state.all_sessions if _normalize_text(session.session_id) == target_session_id),
        None,
    )
    if target_session is None:
        st.error("Target session is no longer available.")
        return False

    first_empty_slot = None
    for slot_index, assigned in enumerate(list(getattr(target_session, "papers", []) or []), start=1):
        if assigned is None:
            first_empty_slot = slot_index
            break

    if first_empty_slot is not None:
        return _apply_layout_updates(
            {
                sid: {
                    "PlacementStatus": "scheduled",
                    "SessionId": _normalize_text(target_session.session_id),
                    "TalkIndex": str(first_empty_slot),
                    "OverflowOrder": "",
                }
            },
            f"Moved {sid} to {target_session.session_code} slot {first_empty_slot}.",
        )

    overflow_order = len(list(getattr(target_session, "overflow_papers", []) or [])) + 1
    return _apply_layout_updates(
        {
            sid: {
                "PlacementStatus": "overflow",
                "SessionId": _normalize_text(target_session.session_id),
                "TalkIndex": "",
                "OverflowOrder": str(max(1, overflow_order)),
            }
        },
        f"Moved {sid} to overflow in {target_session.session_code}.",
    )


def _apply_session_name_override(session_code: str, title: str) -> bool:
    code = _normalize_text(session_code)
    if not code:
        return False

    new_title = _normalize_text(title)
    current_overrides = load_session_name_overrides(SESSION_NAME_OVERRIDES_FILE)
    old_title = _normalize_text(current_overrides.get(code, ""))

    if new_title == old_title:
        return False

    snapshot = _snapshot_for_undo()
    merged = dict(current_overrides)
    if new_title:
        merged[code] = new_title
    else:
        merged.pop(code, None)

    _push_undo_snapshot(snapshot)
    write_session_name_overrides(merged, SESSION_NAME_OVERRIDES_FILE)
    _refresh_state(f"Updated session title for {code}.")
    return True


def _normalize_int_string(value: object, default: int) -> str:
    try:
        text = str(value).strip()
        if not text:
            return str(default)
        parsed = int(float(text))
        return str(parsed)
    except Exception:
        return str(default)


def _apply_session_structure_edits_if_changed(edited_df: pd.DataFrame) -> bool:
    if edited_df.empty:
        return False

    config = load_conference_config(_app_config_path())
    current_rows = load_session_structure_rows(SESSION_STRUCTURE_FILE)
    merged: Dict[str, Dict[str, str]] = {sid: dict(row) for sid, row in current_rows.items()}
    changed = False

    for _, row in edited_df.iterrows():
        session_id = _normalize_text(row.get("SessionId", ""))
        if not session_id or session_id not in merged:
            continue

        current = merged[session_id]
        candidate = dict(current)
        candidate["SessionCode"] = _normalize_text(row.get("SessionCode", current.get("SessionCode", "")))
        status = _normalize_text(row.get("Status", current.get("Status", "active"))).lower()
        candidate["Status"] = status if status in {"active", "inactive"} else current.get("Status", "active")
        candidate["DayLabel"] = _normalize_text(row.get("DayLabel", current.get("DayLabel", "")))
        day_default = config.day_to_num.get(candidate["DayLabel"], int(current.get("DayNum", "0") or 0))
        candidate["DayNum"] = _normalize_int_string(row.get("DayNum", current.get("DayNum", "")), day_default)
        candidate["BlockLabel"] = _normalize_text(row.get("BlockLabel", current.get("BlockLabel", "")))

        block_text = _normalize_text(row.get("BlockNum", current.get("BlockNum", "")))
        if not block_text:
            block_match = re.search(r"(\d+)", candidate["BlockLabel"])
            block_default = int(block_match.group(1)) if block_match else int(current.get("BlockNum", "0") or 0)
            candidate["BlockNum"] = str(block_default)
        else:
            candidate["BlockNum"] = _normalize_int_string(block_text, int(current.get("BlockNum", "0") or 0))

        current_start = int(current.get("StartMin", "0") or 0)
        current_end = int(
            current.get("EndMin", str(current_start + config.structure.default_session_duration_min)) or 0
        )
        start_min, _, end_min, time_label = resolve_session_time_inputs(
            start_time_value=row.get("StartTime", current_start),
            duration_value=row.get("DurationMin", max(1, current_end - current_start)),
            current_start_min=current_start,
            current_end_min=current_end,
            default_duration_min=config.structure.default_session_duration_min,
        )
        candidate["StartMin"] = str(start_min)
        candidate["EndMin"] = str(end_min)
        candidate["TimeLabel"] = time_label

        candidate["Room"] = _normalize_text(row.get("Room", current.get("Room", "")))
        candidate["Capacity"] = _normalize_int_string(
            row.get("Capacity", current.get("Capacity", "")),
            config.structure.default_session_capacity,
        )
        if int(candidate["Capacity"]) <= 0:
            candidate["Capacity"] = str(config.structure.default_session_capacity)
        candidate["Source"] = _normalize_text(row.get("Source", current.get("Source", "manual"))) or "manual"

        if any(candidate.get(k, "") != current.get(k, "") for k in candidate.keys()):
            candidate["UpdatedAt"] = datetime.utcnow().isoformat(timespec="seconds")
            merged[session_id] = candidate
            changed = True

    if not changed:
        return False

    errors = validate_session_structure_rows(merged.values(), config)
    if errors:
        st.error(errors[0])
        return False

    _push_undo_snapshot()
    write_session_structure_rows(merged.values(), SESSION_STRUCTURE_FILE)
    _refresh_state("Applied session structure changes.")
    return True


def _apply_layout_updates(update_rows: Dict[str, Dict[str, object]], message: str) -> bool:
    if not update_rows:
        return False

    current_overrides = load_paper_placements(PAPER_PLACEMENTS_FILE)
    merged = dict(current_overrides)
    state = st.session_state.wic_state
    code_to_id = {
        _normalize_text(session.session_code): _normalize_text(session.session_id)
        for session in state.all_sessions
    }
    now = datetime.utcnow().isoformat(timespec="seconds")
    changed = False
    snapshot: Optional[Dict[str, object]] = None

    for sid, row in update_rows.items():
        sid = _normalize_text(sid)
        if not sid:
            continue

        normalized = _normalize_layout_override_row(
            {
                "SubmissionID": sid,
                "PlacementStatus": row.get("PlacementStatus", "scheduled"),
                "SessionId": row.get("SessionId", ""),
                "TalkIndex": row.get("TalkIndex", ""),
                "OverflowOrder": row.get("OverflowOrder", ""),
                "UpdatedAt": now,
            },
            now=now,
        )
        if not normalized["SessionId"]:
            maybe_code = _normalize_text(row.get("SessionCode", ""))
            if maybe_code:
                normalized["SessionId"] = code_to_id.get(maybe_code, "")
        if normalized["PlacementStatus"] in {"scheduled", "overflow"} and not normalized["SessionId"]:
            normalized["PlacementStatus"] = "unassigned"
            normalized["TalkIndex"] = ""
            normalized["OverflowOrder"] = ""

        existing_raw = current_overrides.get(sid, {})
        existing = _normalize_layout_override_row(
            {
                "SubmissionID": sid,
                "PlacementStatus": existing_raw.get("PlacementStatus", ""),
                "SessionId": existing_raw.get("SessionId", ""),
                "TalkIndex": existing_raw.get("TalkIndex", ""),
                "OverflowOrder": existing_raw.get("OverflowOrder", ""),
                "UpdatedAt": existing_raw.get("UpdatedAt", ""),
            },
            now=now,
        )

        if (
            normalized["PlacementStatus"] == existing["PlacementStatus"]
            and normalized["SessionId"] == existing["SessionId"]
            and normalized["TalkIndex"] == existing["TalkIndex"]
            and normalized["OverflowOrder"] == existing["OverflowOrder"]
        ):
            continue

        if snapshot is None:
            snapshot = _snapshot_for_undo()

        merged[sid] = normalized
        changed = True

    if not changed:
        return False

    _push_undo_snapshot(snapshot)
    write_paper_placements(merged.values(), PAPER_PLACEMENTS_FILE)
    _refresh_state(message)
    return True


def _undo_last_change() -> bool:
    stack = st.session_state.get("undo_stack")
    if not isinstance(stack, list) or not stack:
        return False

    last_change = stack[-1]
    files_snapshot = last_change.get("files", {})
    if not isinstance(files_snapshot, dict):
        return False
    for raw_path, content in files_snapshot.items():
        _write_state_file(Path(raw_path), str(content))

    stack.pop()
    st.session_state.undo_stack = stack
    _refresh_state("Undid one change.")
    return True


def _set_structure_selection(selection: Dict[str, object]) -> None:
    st.session_state.structure_selection = dict(selection)


def _clear_structure_selection() -> None:
    st.session_state.structure_selection = {}


def _apply_room_bulk_updates_if_changed(
    selection: Dict[str, object],
    status_update: str,
    capacity_update: Optional[int],
) -> bool:
    day_label = _normalize_text(selection.get("day_label", ""))
    room = _normalize_text(selection.get("room", ""))

    if not day_label or not room:
        st.error("Room selection is incomplete.")
        return False

    config = load_conference_config(_app_config_path())
    rows = load_session_structure_rows(SESSION_STRUCTURE_FILE)
    status_value = _normalize_text(status_update).lower()
    if status_value not in {"", "active", "inactive"}:
        status_value = ""
    cap_value = max(1, int(capacity_update)) if capacity_update is not None else None

    matched = 0
    changed = 0
    now = datetime.utcnow().isoformat(timespec="seconds")
    merged: Dict[str, Dict[str, str]] = {sid: dict(row) for sid, row in rows.items()}

    for session_id, row in rows.items():
        if _normalize_text(row.get("DayLabel", "")) != day_label:
            continue
        if _normalize_text(row.get("Room", "")) != room:
            continue

        matched += 1
        candidate = dict(row)
        row_changed = False
        if status_value and _normalize_text(candidate.get("Status", "active")).lower() != status_value:
            candidate["Status"] = status_value
            row_changed = True
        if cap_value is not None and _normalize_text(candidate.get("Capacity", "")) != str(cap_value):
            candidate["Capacity"] = str(cap_value)
            row_changed = True
        if row_changed:
            candidate["UpdatedAt"] = now
            merged[session_id] = candidate
            changed += 1

    if matched == 0:
        st.info("No matching sessions found for this room on the selected day.")
        return False
    if changed == 0:
        st.info("No room changes detected.")
        return False

    errors = validate_session_structure_rows(merged.values(), config)
    if errors:
        st.error(errors[0])
        return False

    _push_undo_snapshot()
    write_session_structure_rows(merged.values(), SESSION_STRUCTURE_FILE)
    _refresh_state(f"Updated {changed} session(s) in room {room}.")
    return True


def _render_structure_session_inspector(state, session: object) -> None:
    st.markdown("**Session**")
    session_title = _normalize_text(getattr(session, "session_title", "")) or "[No title]"
    st.markdown(f"### {session_title}")
    st.caption(
        f"{session.session_code} | {session.day_label} | {session.block_label} | "
        f"{session.time} | {session.room}"
    )
    counts = structure_session_counts(session, unassigned_count=len(state.unassigned_papers))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Filled", f"{counts['filled']}/{counts['capacity']}")
    c2.metric("Open slots", counts["open_slots"])
    c3.metric("Overflow", counts["overflow"])
    c4.metric("Potential fill", counts["potential_fill"])

    st.markdown("---")
    st.caption("Session Title")
    title_key = f"struct_ins_session_title_{session.session_code}"
    title_src = f"{title_key}_src"
    current_title = _normalize_text(session.session_title)
    if st.session_state.get(title_src) != current_title:
        st.session_state[title_key] = current_title
        st.session_state[title_src] = current_title
    st.text_input("Session Title", key=title_key)
    if st.button(
        "Apply Session Title",
        key=f"struct_ins_apply_title_{session.session_id}",
        use_container_width=True,
    ):
        title = _normalize_text(st.session_state.get(title_key, ""))
        if _apply_session_name_override(session.session_code, title):
            st.rerun()
        st.info("No title changes detected.")

    st.markdown("---")
    st.caption("Structure")
    status_options = ["active", "inactive"]
    current_status = _normalize_text(getattr(session, "status", "active")).lower()
    status_idx = status_options.index(current_status) if current_status in status_options else 0
    st_col1, st_col2 = st.columns(2)
    new_status = st_col1.selectbox(
        "Status",
        options=status_options,
        index=status_idx,
        key=f"struct_ins_status_{session.session_id}",
    )
    new_code = st_col2.text_input(
        "Session Code",
        value=_normalize_text(session.session_code),
        key=f"struct_ins_code_{session.session_id}",
    )

    st_col3, st_col4, st_col5 = st.columns(3)
    new_room = st_col3.text_input(
        "Room",
        value=_normalize_text(session.room),
        key=f"struct_ins_room_{session.session_id}",
    )
    new_start = st_col4.text_input(
        "Start Time (HH:MM)",
        value=minutes_to_clock(int(session.start_min)),
        key=f"struct_ins_start_{session.session_id}",
    )
    new_duration = st_col5.number_input(
        "Duration (min)",
        min_value=1,
        max_value=360,
        value=max(1, int(session.end_min - session.start_min)),
        step=5,
        key=f"struct_ins_duration_{session.session_id}",
    )
    new_capacity = st.number_input(
        "Capacity",
        min_value=1,
        max_value=20,
        value=max(1, int(session.capacity)),
        step=1,
        key=f"struct_ins_capacity_{session.session_id}",
    )
    if st.button(
        "Apply Session Structure Changes",
        key=f"struct_ins_apply_{session.session_id}",
        use_container_width=True,
    ):
        _push_undo_snapshot()
        start_min = parse_clock_minutes(new_start, default=int(session.start_min))
        end_min = start_min + int(new_duration)
        result = update_session_structure_row(
            session.session_id,
            {
                "SessionCode": new_code,
                "Status": new_status,
                "Room": new_room,
                "StartMin": str(start_min),
                "EndMin": str(end_min),
                "TimeLabel": build_time_label(start_min, end_min),
                "Capacity": str(int(new_capacity)),
            },
            config_path=_app_config_path(),
        )
        if result.get("ok", False):
            _refresh_state(f"Updated structure for {session.session_code}.")
            st.rerun()
        st.error(str(result.get("error", "Failed to update session structure.")))

    st.markdown("---")
    st.caption("Lifecycle")
    if _normalize_text(getattr(session, "status", "active")).lower() == "active":
        life_left, life_right = st.columns(2)
        confirm_clear = life_left.checkbox(
            "Confirm clear",
            key=f"struct_ins_confirm_clear_{session.session_id}",
        )
        if life_left.button(
            "Clear Session",
            key=f"struct_ins_clear_{session.session_id}",
            use_container_width=True,
            disabled=not confirm_clear,
        ):
            _push_undo_snapshot()
            result = clear_session(session.session_id)
            if result.get("ok", False):
                moved = int(result.get("moved_to_unassigned", 0) or 0)
                _refresh_state(f"Cleared {session.session_code}; moved {moved} paper(s) to unassigned.")
                st.rerun()
            st.error(str(result.get("error", "Failed to clear session.")))

        confirm_remove = life_right.checkbox(
            "Confirm remove",
            key=f"struct_ins_confirm_remove_{session.session_id}",
        )
        if life_right.button(
            "Remove Session",
            key=f"struct_ins_remove_{session.session_id}",
            use_container_width=True,
            disabled=not confirm_remove,
        ):
            _push_undo_snapshot()
            result = remove_session(session.session_id)
            if result.get("ok", False):
                moved = int(result.get("moved_to_unassigned", 0) or 0)
                _refresh_state(f"Removed {session.session_code}; moved {moved} paper(s) to unassigned.")
                _clear_structure_selection()
                st.rerun()
            st.error(str(result.get("error", "Failed to remove session.")))
    else:
        if st.button(
            "Restore Session",
            key=f"struct_ins_restore_{session.session_id}",
            use_container_width=True,
        ):
            _push_undo_snapshot()
            result = restore_session(session.session_id, config_path=_app_config_path())
            if result.get("ok", False):
                _refresh_state(f"Restored {session.session_code}.")
                st.rerun()
            st.error(str(result.get("error", "Failed to restore session.")))


def _render_structure_room_inspector(state, selection: Dict[str, object]) -> None:
    config = load_conference_config(_app_config_path())
    day_label = _normalize_text(selection.get("day_label", ""))
    room = _normalize_text(selection.get("room", ""))

    st.markdown("**Room**")
    st.caption(f"{room} | {day_label}")

    day_room_sessions = [
        session
        for session in state.all_sessions
        if session.day_label == day_label and _normalize_text(session.room) == room
    ]
    active_day = len([session for session in day_room_sessions if _normalize_text(session.status).lower() == "active"])
    inactive_day = len(day_room_sessions) - active_day
    m1, m2, m3 = st.columns(3)
    m1.metric("Sessions this day", len(day_room_sessions))
    m2.metric("Active this day", active_day)
    m3.metric("Inactive this day", inactive_day)

    st.markdown("---")
    st.caption("Room name")
    rename_key = f"struct_room_rename_{day_label}_{room}"
    rename_src_key = f"{rename_key}_src"
    if st.session_state.get(rename_src_key) != room:
        st.session_state[rename_key] = room
        st.session_state[rename_src_key] = room
    st.text_input("Room name", key=rename_key)
    if st.button(
        "Apply Room Rename",
        key=f"struct_room_rename_apply_{day_label}_{room}",
        use_container_width=True,
    ):
        new_room = _normalize_text(st.session_state.get(rename_key, ""))
        snapshot = _snapshot_for_undo()
        result = rename_room_for_day(
            day_label=day_label,
            room=room,
            new_room=new_room,
            config_path=_app_config_path(),
        )
        if result.get("ok", False):
            updated = int(result.get("updated", 0) or 0)
            if updated <= 0:
                st.info("No room rename changes detected.")
                return
            _push_undo_snapshot(snapshot)
            _set_structure_selection(
                build_room_selection(
                    day_label=day_label,
                    room=new_room,
                )
            )
            _refresh_state(f"Renamed room to {new_room} for {day_label} ({updated} session(s)).")
            st.rerun()
        st.error(str(result.get("error", "Failed to rename room for day.")))

    st.markdown("---")
    st.caption("Add Room Sessions For Selected Day Blocks")
    day_block_signature_to_label: Dict[str, str] = {}
    for session in state.all_sessions:
        if _normalize_text(session.day_label) != day_label:
            continue
        signature = f"{int(session.block_num)}::{_normalize_text(session.block_label)}::{_normalize_text(session.time)}"
        day_block_signature_to_label[signature] = (
            f"B{int(session.block_num)} | {_normalize_text(session.block_label)} | {_normalize_text(session.time)}"
        )
    day_block_signatures = sorted(
        day_block_signature_to_label.keys(),
        key=lambda sig: (int(sig.split("::", 1)[0]), day_block_signature_to_label.get(sig, "")),
    )

    add_capacity = st.number_input(
        "Capacity for new sessions",
        min_value=1,
        max_value=20,
        value=config.structure.default_session_capacity,
        step=1,
        key=f"struct_room_add_capacity_{day_label}_{room}",
    )
    add_signatures = st.multiselect(
        "Day blocks",
        options=day_block_signatures,
        default=day_block_signatures,
        format_func=lambda sig: day_block_signature_to_label.get(sig, sig),
        key=f"struct_room_add_blocks_{day_label}_{room}",
    )
    if st.button(
        "Add Room Sessions For Selected Blocks",
        key=f"struct_room_add_btn_{day_label}_{room}",
        use_container_width=True,
    ):
        if not add_signatures:
            st.info("Choose at least one day block.")
            return
        _push_undo_snapshot()
        result = bulk_add_room_sessions(
            room=room,
            capacity=int(add_capacity),
            day_labels=[day_label],
            block_signatures=list(add_signatures),
            config_path=_app_config_path(),
        )
        if result.get("ok", False):
            created = int(result.get("created", 0) or 0)
            skipped_active = int(result.get("skipped_active", 0) or 0)
            skipped_inactive = int(result.get("skipped_inactive", 0) or 0)
            _refresh_state(
                f"Room add complete. Created {created}, skipped active {skipped_active}, skipped inactive {skipped_inactive}."
            )
            st.rerun()
        st.error(str(result.get("error", "Failed to add room sessions.")))

    st.markdown("---")
    st.caption("Bulk Room Structure Updates")
    status_pick = st.selectbox(
        "Set status",
        options=["No change", "active", "inactive"],
        key=f"struct_room_status_{day_label}_{room}",
    )
    apply_capacity = st.checkbox(
        "Update capacity",
        value=False,
        key=f"struct_room_apply_capacity_{day_label}_{room}",
    )
    default_day_capacity = day_room_sessions[0].capacity if day_room_sessions else config.structure.default_session_capacity
    bulk_capacity = st.number_input(
        "Capacity value",
        min_value=1,
        max_value=20,
        value=max(1, int(default_day_capacity)),
        step=1,
        key=f"struct_room_bulk_capacity_{day_label}_{room}",
    )
    if st.button(
        "Apply Room Bulk Updates",
        key=f"struct_room_apply_btn_{day_label}_{room}",
        use_container_width=True,
    ):
        status_value = "" if status_pick == "No change" else status_pick
        cap_value = int(bulk_capacity) if apply_capacity else None
        if not status_value and cap_value is None:
            st.info("Choose at least one room update (status and/or capacity).")
        elif _apply_room_bulk_updates_if_changed(selection, status_value, cap_value):
            st.rerun()


def _render_structure_empty_slot_inspector(selection: Dict[str, object]) -> None:
    config = load_conference_config(_app_config_path())
    day_label = _normalize_text(selection.get("day_label", ""))
    block_num = int(selection.get("block_num", 0) or 0)
    block_label = _normalize_text(selection.get("block_label", ""))
    time_label = _normalize_text(selection.get("time_label", ""))
    room = _normalize_text(selection.get("room", ""))
    st.markdown("**Empty Slot**")
    st.caption(f"{day_label} | B{block_num} {block_label} | {time_label} | {room}")

    if not (day_label and block_label and time_label and room):
        st.warning("Empty slot selection is incomplete.")
        return

    code_key = f"struct_empty_code_{day_label}_{block_num}_{room}_{time_label}"
    cap_key = f"struct_empty_capacity_{day_label}_{block_num}_{room}_{time_label}"
    session_code = st.text_input("Session Code (optional)", value="", key=code_key)
    capacity = st.number_input(
        "Capacity",
        min_value=1,
        max_value=20,
        value=config.structure.default_session_capacity,
        step=1,
        key=cap_key,
    )
    if st.button("Create Session In This Slot", use_container_width=True, key=f"struct_empty_create_{day_label}_{block_num}_{room}_{time_label}"):
        _push_undo_snapshot()
        result = create_session(
            day_label=day_label,
            block_label=block_label,
            time_label=time_label,
            room=room,
            capacity=int(capacity),
            block_num=int(block_num),
            session_code=session_code,
            source="manual",
            config_path=_app_config_path(),
        )
        if result.get("ok", False):
            _set_structure_selection(
                {
                    "kind": "session",
                    "session_id": _normalize_text(result.get("session_id", "")),
                    "day_label": day_label,
                    "block_num": block_num,
                    "block_label": block_label,
                    "time_label": time_label,
                    "room": room,
                }
            )
            _refresh_state(f"Created session {result.get('session_code', '')}.")
            st.rerun()
        st.error(str(result.get("error", "Failed to create session.")))


def _render_structure_new_room_inspector(state, selection: Dict[str, object]) -> None:
    config = load_conference_config(_app_config_path())
    day_label = _normalize_text(selection.get("day_label", ""))
    st.markdown("**Add Room Column**")
    st.caption(day_label or "No day selected")

    if not day_label:
        st.warning("Day selection is required.")
        return

    day_block_signature_to_label: Dict[str, str] = {}
    for session in state.all_sessions:
        if _normalize_text(session.day_label) != day_label:
            continue
        signature = f"{int(session.block_num)}::{_normalize_text(session.block_label)}::{_normalize_text(session.time)}"
        day_block_signature_to_label[signature] = (
            f"B{int(session.block_num)} | {_normalize_text(session.block_label)} | {_normalize_text(session.time)}"
        )
    day_block_signatures = sorted(
        day_block_signature_to_label.keys(),
        key=lambda sig: (int(sig.split("::", 1)[0]), day_block_signature_to_label.get(sig, "")),
    )

    room_name = st.text_input("New Room Name", value="", key=f"struct_new_room_name_{day_label}")
    room_capacity = st.number_input(
        "Capacity",
        min_value=1,
        max_value=20,
        value=config.structure.default_session_capacity,
        step=1,
        key=f"struct_new_room_capacity_{day_label}",
    )
    selected_blocks = st.multiselect(
        "Day blocks",
        options=day_block_signatures,
        default=day_block_signatures,
        format_func=lambda sig: day_block_signature_to_label.get(sig, sig),
        key=f"struct_new_room_blocks_{day_label}",
    )
    if st.button("Create Room Sessions", use_container_width=True, key=f"struct_new_room_create_{day_label}"):
        room = _normalize_text(room_name)
        if not room:
            st.info("Enter a room name.")
            return
        if not selected_blocks:
            st.info("Choose at least one block.")
            return
        _push_undo_snapshot()
        result = bulk_add_room_sessions(
            room=room,
            capacity=int(room_capacity),
            day_labels=[day_label],
            block_signatures=list(selected_blocks),
            config_path=_app_config_path(),
        )
        if result.get("ok", False):
            _set_structure_selection(
                build_room_selection(
                    day_label=day_label,
                    room=room,
                )
            )
            created = int(result.get("created", 0) or 0)
            skipped_active = int(result.get("skipped_active", 0) or 0)
            skipped_inactive = int(result.get("skipped_inactive", 0) or 0)
            _refresh_state(
                f"Room add complete. Created {created}, skipped active {skipped_active}, skipped inactive {skipped_inactive}."
            )
            st.rerun()
        st.error(str(result.get("error", "Failed to add room sessions.")))


def _render_structure_tab(state) -> None:
    st.subheader("Structure")
    config = load_conference_config(_app_config_path())
    all_sessions = sorted(state.all_sessions, key=_session_sort_key)

    day_options = sorted({_normalize_text(session.day_label) for session in all_sessions if _normalize_text(session.day_label)})
    if not day_options:
        day_options = list(config.days)
    if not day_options:
        day_options = ["Day 1"]

    filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns([1.7, 0.9, 2.1, 1.2, 2.1])
    day_pick = filter_col1.selectbox("Day", day_options, key="structure_day_filter")
    filter_col2.caption("Manage days")
    if filter_col2.button(
        "Add/Delete days",
        key="structure_day_tools_toggle",
        use_container_width=True,
        help="Open day operations for clone, clear, delete, or relabel.",
    ):
        st.session_state.structure_day_tools_open = not bool(st.session_state.get("structure_day_tools_open", False))
        st.rerun()
    status_pick = filter_col4.selectbox(
        "Status",
        options=["all", "active", "inactive"],
        format_func=lambda value: value.title(),
        key="structure_status_filter",
    )
    search_text = filter_col5.text_input("Search SessionCode/Room", "", key="structure_search")
    block_options = block_filter_labels_for_day(
        all_sessions,
        day_label=day_pick,
        status_filter=status_pick,
        search_text=search_text,
        parse_start_minutes_fn=parse_start_minutes,
    )
    current_block = st.session_state.get("structure_block_filter", "All blocks")
    if current_block not in block_options:
        st.session_state.structure_block_filter = block_options[0]
        current_block = block_options[0]
    block_index = block_options.index(current_block) if current_block in block_options else 0
    block_pick = filter_col3.selectbox(
        "Block (optional)",
        options=block_options,
        index=block_index,
        key="structure_block_filter",
    )

    day_sessions = [session for session in all_sessions if _normalize_text(session.day_label) == day_pick]
    day_rooms = sorted(
        {_normalize_text(session.room) for session in day_sessions if _normalize_text(session.room)},
        key=room_sort_key,
    )

    resolved_day_num = int(config.day_to_num.get(day_pick, 0))
    if resolved_day_num <= 0 and day_sessions:
        resolved_day_num = int(getattr(day_sessions[0], "day_num", 0) or 0)

    if bool(st.session_state.get("structure_day_tools_open", False)):
        with st.container(border=True):
            st.markdown("**Add/Delete days**")
            day_action = st.selectbox(
                "Action",
                options=["Clone Day", "Clear Day", "Delete Day", "Relabel Day"],
                key="structure_day_action_pick",
            )

            if day_action == "Clone Day":
                clone_col1, clone_col2, clone_col3 = st.columns([1.6, 2.2, 1.2])
                source_day = clone_col1.selectbox(
                    "Source day",
                    options=day_options,
                    index=day_options.index(day_pick) if day_pick in day_options else 0,
                    key="structure_day_clone_source",
                )
                target_day_label = clone_col2.text_input(
                    "Target day label",
                    value=f"{source_day} Copy",
                    key="structure_day_clone_target_label",
                )
                source_day_num = int(config.day_to_num.get(source_day, 0))
                if source_day_num <= 0 and source_day in day_options:
                    source_day_sessions = [
                        session for session in all_sessions if _normalize_text(session.day_label) == source_day
                    ]
                    if source_day_sessions:
                        source_day_num = int(getattr(source_day_sessions[0], "day_num", 0) or 0)
                target_day_num = clone_col3.number_input(
                    "Target day #",
                    min_value=1,
                    max_value=99,
                    value=max(1, source_day_num),
                    step=1,
                    key="structure_day_clone_target_num",
                )
                if st.button("Apply Clone Day", key="structure_day_clone_submit", use_container_width=True):
                    snapshot = _snapshot_for_undo()
                    result = clone_day_structure(
                        source_day_label=source_day,
                        target_day_label=_normalize_text(target_day_label),
                        target_day_num=int(target_day_num),
                        config_path=_app_config_path(),
                    )
                    if result.get("ok", False):
                        created = int(result.get("created", 0) or 0)
                        skipped_active = int(result.get("skipped_active", 0) or 0)
                        skipped_inactive = int(result.get("skipped_inactive", 0) or 0)
                        if created > 0:
                            _push_undo_snapshot(snapshot)
                        _refresh_state(
                            f"Clone day complete. Created {created}, skipped active {skipped_active}, skipped inactive {skipped_inactive}."
                        )
                        st.rerun()
                    st.error(str(result.get("error", "Failed to clone day structure.")))

            elif day_action == "Clear Day":
                confirm_clear_day = st.checkbox(
                    f"Confirm clear all papers assigned on {day_pick}",
                    key="structure_day_clear_confirm",
                )
                if st.button(
                    "Apply Clear Day",
                    key="structure_day_clear_submit",
                    use_container_width=True,
                    disabled=not confirm_clear_day,
                ):
                    snapshot = _snapshot_for_undo()
                    result = clear_day_sessions(
                        day_label=day_pick,
                        session_structure_path=SESSION_STRUCTURE_FILE,
                        paper_placements_path=PAPER_PLACEMENTS_FILE,
                    )
                    if result.get("ok", False):
                        moved = int(result.get("moved_to_unassigned", 0) or 0)
                        if moved > 0:
                            _push_undo_snapshot(snapshot)
                        _refresh_state(f"Cleared day {day_pick}; moved {moved} paper(s) to unassigned.")
                        st.rerun()
                    st.error(str(result.get("error", "Failed to clear day sessions.")))

            elif day_action == "Delete Day":
                confirm_delete_day = st.checkbox(
                    f"Confirm delete all sessions for {day_pick}",
                    key="structure_day_delete_confirm",
                )
                if st.button(
                    "Apply Delete Day",
                    key="structure_day_delete_submit",
                    use_container_width=True,
                    disabled=not confirm_delete_day,
                ):
                    snapshot = _snapshot_for_undo()
                    result = delete_day_sessions(
                        day_label=day_pick,
                        session_structure_path=SESSION_STRUCTURE_FILE,
                        paper_placements_path=PAPER_PLACEMENTS_FILE,
                    )
                    if result.get("ok", False):
                        deleted = int(result.get("deleted", 0) or 0)
                        moved = int(result.get("moved_to_unassigned", 0) or 0)
                        if deleted > 0 or moved > 0:
                            _push_undo_snapshot(snapshot)
                        _clear_structure_selection()
                        _refresh_state(f"Deleted day {day_pick}; removed {deleted} sessions and unassigned {moved} paper(s).")
                        st.rerun()
                    st.error(str(result.get("error", "Failed to delete day sessions.")))

            else:
                relabel_col1, relabel_col2 = st.columns([2.2, 1.2])
                new_day_label = relabel_col1.text_input(
                    "New day label",
                    value=day_pick,
                    key="structure_day_relabel_label",
                )
                new_day_num = relabel_col2.number_input(
                    "New day #",
                    min_value=1,
                    max_value=99,
                    value=max(1, resolved_day_num or 1),
                    step=1,
                    key="structure_day_relabel_num",
                )
                confirm_relabel_day = st.checkbox(
                    f"Confirm relabel all sessions from {day_pick}",
                    key="structure_day_relabel_confirm",
                )
                if st.button(
                    "Apply Relabel Day",
                    key="structure_day_relabel_submit",
                    use_container_width=True,
                    disabled=not confirm_relabel_day,
                ):
                    snapshot = _snapshot_for_undo()
                    result = relabel_day_sessions(
                        day_label=day_pick,
                        new_day_label=_normalize_text(new_day_label),
                        new_day_num=int(new_day_num),
                        session_structure_path=SESSION_STRUCTURE_FILE,
                        session_name_overrides_path=SESSION_NAME_OVERRIDES_FILE,
                        config_path=_app_config_path(),
                    )
                    if result.get("ok", False):
                        updated = int(result.get("updated", 0) or 0)
                        migrated_overrides = int(result.get("migrated_overrides", 0) or 0)
                        if updated > 0:
                            _push_undo_snapshot(snapshot)
                        _clear_structure_selection()
                        _refresh_state(
                            f"Relabeled day to {_normalize_text(new_day_label)} (#{int(new_day_num)}); updated {updated} sessions, migrated {migrated_overrides} title override(s)."
                        )
                        st.rerun()
                    st.error(str(result.get("error", "Failed to relabel day sessions.")))

    matrix_data = group_sessions_for_structure_matrix(
        all_sessions,
        day_label=day_pick,
        status_filter=status_pick,
        block_filter_label=block_pick,
        search_text=search_text,
        parse_start_minutes_fn=parse_start_minutes,
        room_sort_key_fn=room_sort_key,
    )
    visible_sessions = collect_visible_sessions(matrix_data)

    visible_active = len([session for session in visible_sessions if _normalize_text(session.status).lower() == "active"])
    visible_inactive = len(visible_sessions) - visible_active
    visible_open_slots = sum(structure_session_counts(session)["open_slots"] for session in visible_sessions)
    visible_overflow = sum(structure_session_counts(session)["overflow"] for session in visible_sessions)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Visible active sessions", visible_active)
    c2.metric("Visible inactive sessions", visible_inactive)
    c3.metric("Visible open slots", visible_open_slots)
    c4.metric("Visible overflow papers", visible_overflow)
    selection = st.session_state.get("structure_selection", {})
    has_selection = isinstance(selection, dict) and _normalize_text(selection.get("kind", "")) in {
        "session",
        "room",
        "empty_slot",
        "new_room",
    }

    def _on_select_session(session: object) -> None:
        _set_structure_selection(build_session_selection(session))

    def _on_select_room(room: str) -> None:
        _set_structure_selection(
            build_room_selection(
                day_label=day_pick,
                room=room,
            )
        )

    def _on_select_empty_slot(row: Dict[str, object], room: str) -> None:
        _set_structure_selection(
            build_empty_slot_selection(
                day_label=day_pick,
                block_num=int(row.get("block_num", 0) or 0),
                block_label=_normalize_text(row.get("block_label", "")),
                time_label=_normalize_text(row.get("time_label", "")),
                room=room,
            )
        )

    def _on_select_new_room() -> None:
        _set_structure_selection(build_new_room_selection(day_pick))

    def _render_matrix() -> None:
        render_structure_matrix(
            matrix=matrix_data,
            selection=selection if isinstance(selection, dict) else {},
            day_label=day_pick,
            on_select_session=_on_select_session,
            on_select_room=_on_select_room,
            on_select_empty_slot=_on_select_empty_slot,
            on_select_new_room=_on_select_new_room,
        )

    if has_selection:
        left_col, right_col = st.columns([3.2, 1.2], gap="large")
        with left_col:
            _render_matrix()
        with right_col:
            render_structure_inspector(
                state=state,
                selection=selection,
                find_session_by_id=lambda session_id: next(
                    (session for session in state.all_sessions if session.session_id == session_id),
                    None,
                ),
                render_session_panel=lambda session: _render_structure_session_inspector(state, session),
                render_room_panel=lambda room_selection: _render_structure_room_inspector(state, room_selection),
                render_empty_slot_panel=lambda empty_slot_selection: _render_structure_empty_slot_inspector(
                    empty_slot_selection
                ),
                render_new_room_panel=lambda new_room_selection: _render_structure_new_room_inspector(
                    state, new_room_selection
                ),
                clear_selection=_clear_structure_selection,
            )
    else:
        _render_matrix()

    st.markdown("---")
    add_row_col1, add_row_col2 = st.columns([1.1, 3.9])
    if add_row_col1.button(
        "Add session",
        key=f"structure_add_row_toggle_{day_pick}",
        use_container_width=True,
        help="Append a new full row of sessions for all rooms in the selected day.",
    ):
        st.session_state.structure_add_row_open = not bool(st.session_state.get("structure_add_row_open", False))
        st.rerun()
    add_row_col2.caption("Append one new block row across every room in this day.")

    if bool(st.session_state.get("structure_add_row_open", False)):
        with st.container(border=True):
            st.markdown("**Add session**")
            if not day_rooms:
                st.info(f"No rooms found for {day_pick}. Add a room first.")
            else:
                max_block_num = max([int(getattr(session, "block_num", 0) or 0) for session in day_sessions] + [0])
                default_block_num = max(1, max_block_num + 1)
                default_block_label = f"SESSION {default_block_num}"
                anchor_session = max(
                    day_sessions,
                    key=lambda session: (
                        int(getattr(session, "block_num", 0) or 0),
                        int(getattr(session, "start_min", parse_start_minutes(_normalize_text(getattr(session, "time", "")))) or 0),
                    ),
                )
                default_start_min = int(
                    getattr(
                        anchor_session,
                        "start_min",
                        parse_start_minutes(_normalize_text(getattr(anchor_session, "time", ""))),
                    )
                    or 0
                )
                anchor_end = int(
                    getattr(anchor_session, "end_min", default_start_min + int(config.structure.default_session_duration_min))
                    or (default_start_min + int(config.structure.default_session_duration_min))
                )
                default_duration = max(1, anchor_end - default_start_min)
                capacity_samples = [
                    int(getattr(session, "capacity", config.structure.default_session_capacity) or config.structure.default_session_capacity)
                    for session in day_sessions
                ]
                if capacity_samples:
                    default_capacity = max(sorted(set(capacity_samples)), key=capacity_samples.count)
                else:
                    default_capacity = int(config.structure.default_session_capacity)

                with st.form(f"structure_add_row_form_{day_pick}", clear_on_submit=False):
                    row_col1, row_col2, row_col3, row_col4 = st.columns([1.0, 2.0, 1.2, 1.1])
                    block_num_value = row_col1.number_input(
                        "Block #",
                        min_value=1,
                        max_value=99,
                        value=default_block_num,
                        step=1,
                        key=f"structure_add_row_block_num_{day_pick}",
                    )
                    block_label_value = row_col2.text_input(
                        "Block label",
                        value=default_block_label,
                        key=f"structure_add_row_block_label_{day_pick}",
                    )
                    start_time_value = row_col3.text_input(
                        "Start (HH:MM)",
                        value=minutes_to_clock(default_start_min),
                        key=f"structure_add_row_start_{day_pick}",
                    )
                    duration_value = row_col4.number_input(
                        "Duration (min)",
                        min_value=1,
                        max_value=360,
                        value=int(default_duration),
                        step=5,
                        key=f"structure_add_row_duration_{day_pick}",
                    )
                    capacity_value = st.number_input(
                        "Capacity",
                        min_value=1,
                        max_value=20,
                        value=int(default_capacity),
                        step=1,
                        key=f"structure_add_row_capacity_{day_pick}",
                    )
                    create_row_submit = st.form_submit_button("Create Row", use_container_width=True)
                    if create_row_submit:
                        snapshot = _snapshot_for_undo()
                        start_min_value = parse_clock_minutes(start_time_value, default=default_start_min)
                        result = add_block_row_sessions(
                            day_label=day_pick,
                            block_label=_normalize_text(block_label_value),
                            block_num=int(block_num_value),
                            start_min=int(start_min_value),
                            duration_min=int(duration_value),
                            capacity=int(capacity_value),
                            config_path=_app_config_path(),
                        )
                        if result.get("ok", False):
                            created = int(result.get("created", 0) or 0)
                            skipped_active = int(result.get("skipped_active", 0) or 0)
                            skipped_inactive = int(result.get("skipped_inactive", 0) or 0)
                            if created > 0:
                                _push_undo_snapshot(snapshot)
                            _refresh_state(
                                f"Row add complete. Created {created}, skipped active {skipped_active}, skipped inactive {skipped_inactive}."
                            )
                            st.session_state.structure_add_row_open = False
                            st.rerun()
                        st.error(str(result.get("error", "Failed to create row sessions.")))

    show_advanced_tools = st.toggle(
        "Show advanced structure tools",
        value=False,
        key="structure_show_advanced_tools",
        help="Enable table editor and secondary structure tools only when needed.",
    )
    if not show_advanced_tools:
        return

    session_rows = list(load_session_structure_rows(SESSION_STRUCTURE_FILE).values())
    session_rows = sorted(
        session_rows,
        key=lambda row: (
            _normalize_text(row.get("Status", "active")),
            int(str(row.get("DayNum", "0") or "0")),
            int(str(row.get("StartMin", "0") or "0")),
            room_sort_key(_normalize_text(row.get("Room", ""))),
            _normalize_text(row.get("SessionCode", "")),
        ),
    )

    with st.expander("Advanced table editor", expanded=False):
        structure_editor_rows: List[Dict[str, object]] = []
        for row in session_rows:
            start_min = int(str(row.get("StartMin", "0") or "0"))
            end_min = int(
                str(row.get("EndMin", str(start_min + config.structure.default_session_duration_min)) or "0")
            )
            duration_min = max(1, end_min - start_min)
            structure_editor_rows.append(
                {
                    "SessionId": _normalize_text(row.get("SessionId", "")),
                    "SessionCode": _normalize_text(row.get("SessionCode", "")),
                    "Status": _normalize_text(row.get("Status", "active")),
                    "DayLabel": _normalize_text(row.get("DayLabel", "")),
                    "DayNum": int(str(row.get("DayNum", "0") or "0")),
                    "BlockLabel": _normalize_text(row.get("BlockLabel", "")),
                    "BlockNum": int(str(row.get("BlockNum", "0") or "0")),
                    "StartTime": minutes_to_clock(start_min),
                    "DurationMin": duration_min,
                    "EndTime": minutes_to_clock(start_min + duration_min),
                    "TimeLabel": build_time_label(start_min, start_min + duration_min),
                    "Room": _normalize_text(row.get("Room", "")),
                    "Capacity": int(
                        str(
                            row.get(
                                "Capacity",
                                str(config.structure.default_session_capacity),
                            )
                            or config.structure.default_session_capacity
                        )
                    ),
                    "Source": _normalize_text(row.get("Source", "manual")) or "manual",
                }
            )
        structure_df = pd.DataFrame(structure_editor_rows)
        if structure_df.empty:
            st.info("No sessions yet. Create sessions below to start from scratch.")
        else:
            edited_structure = st.data_editor(
                structure_df,
                key="session_structure_editor",
                hide_index=True,
                use_container_width=True,
                num_rows="fixed",
                column_config={
                    "SessionId": st.column_config.TextColumn(disabled=True),
                    "SessionCode": st.column_config.TextColumn(),
                    "Status": st.column_config.SelectboxColumn(options=["active", "inactive"]),
                    "DayLabel": st.column_config.TextColumn(),
                    "DayNum": st.column_config.NumberColumn(format="%d"),
                    "BlockLabel": st.column_config.TextColumn(),
                    "BlockNum": st.column_config.NumberColumn(format="%d"),
                    "StartTime": st.column_config.TextColumn(help="HH:MM"),
                    "DurationMin": st.column_config.NumberColumn(format="%d"),
                    "EndTime": st.column_config.TextColumn(disabled=True),
                    "TimeLabel": st.column_config.TextColumn(disabled=True),
                    "Room": st.column_config.TextColumn(),
                    "Capacity": st.column_config.NumberColumn(format="%d"),
                    "Source": st.column_config.TextColumn(),
                },
            )
            if _apply_session_structure_edits_if_changed(edited_structure):
                st.rerun()

    with st.expander("Secondary structure tools", expanded=False):
        st.markdown("#### Create Session")
        day_options = list(config.days) or sorted(
            {row.get("DayLabel", "") for row in session_rows if row.get("DayLabel", "")}
        )
        if not day_options:
            day_options = ["Day 1"]
        with st.form("create_session_form", clear_on_submit=False):
            day_label = st.selectbox("Day", day_options, key="create_session_day")
            block_label = st.text_input("Block Label", value="SESSION 1", key="create_session_block")
            start_time = st.text_input("Start Time (HH:MM)", value="09:30", key="create_session_start_time")
            duration_min = st.number_input(
                "Duration (min)",
                min_value=1,
                max_value=360,
                value=config.structure.default_session_duration_min,
                step=5,
                key="create_session_duration",
            )
            room = st.text_input("Room", value="R-New", key="create_session_room")
            capacity = st.number_input(
                "Capacity",
                min_value=1,
                max_value=20,
                value=config.structure.default_session_capacity,
                step=1,
                key="create_session_capacity",
            )
            session_code = st.text_input("Session Code (optional)", value="", key="create_session_code")
            create_submit = st.form_submit_button("Create Session", use_container_width=True)
            if create_submit:
                _push_undo_snapshot()
                start_min = parse_clock_minutes(start_time, default=parse_start_minutes("9h30"))
                end_min = start_min + int(duration_min)
                time_label = build_time_label(start_min, end_min)
                result = create_session(
                    day_label=day_label,
                    block_label=block_label,
                    time_label=time_label,
                    room=room,
                    capacity=int(capacity),
                    start_min=start_min,
                    end_min=end_min,
                    session_code=session_code,
                    source="manual",
                    config_path=_app_config_path(),
                )
                if result.get("ok", False):
                    _refresh_state(f"Created session {result.get('session_code', '')}.")
                    st.rerun()
                st.error(str(result.get("error", "Failed to create session.")))

        st.markdown("#### Add Room (Bulk)")
        known_days = sorted({row.get("DayLabel", "") for row in session_rows if row.get("DayLabel", "")})
        if not known_days:
            known_days = list(config.days)

        block_signature_to_label: Dict[str, str] = {}
        for row in session_rows:
            row_block_num = int(str(row.get("BlockNum", "0") or "0"))
            row_block_label = _normalize_text(row.get("BlockLabel", ""))
            row_time_label = _normalize_text(row.get("TimeLabel", ""))
            if row_block_num <= 0 or not row_time_label:
                continue
            signature = f"{row_block_num}::{row_block_label}::{row_time_label}"
            display_label = f"B{row_block_num} | {row_block_label} | {row_time_label}"
            block_signature_to_label[signature] = display_label
        block_signatures_sorted = sorted(
            block_signature_to_label.keys(),
            key=lambda sig: (int(sig.split("::", 1)[0]), block_signature_to_label.get(sig, "")),
        )

        if known_days and block_signatures_sorted:
            with st.form("add_room_bulk_form", clear_on_submit=False):
                st.caption("Default selection includes all days and all known blocks.")
                new_room = st.text_input("New Room", value="R-New2", key="add_room_name")
                new_capacity = st.number_input(
                    "Capacity",
                    min_value=1,
                    max_value=20,
                    value=config.structure.default_session_capacity,
                    step=1,
                    key="add_room_capacity",
                )
                selected_days = st.multiselect(
                    "Days",
                    options=known_days,
                    default=known_days,
                    key="add_room_days",
                )
                selected_signatures = st.multiselect(
                    "Blocks",
                    options=block_signatures_sorted,
                    default=block_signatures_sorted,
                    format_func=lambda sig: block_signature_to_label.get(sig, sig),
                    key="add_room_block_signatures",
                )
                add_room_submit = st.form_submit_button("Add Room Sessions", use_container_width=True)
                if add_room_submit:
                    _push_undo_snapshot()
                    result = bulk_add_room_sessions(
                        room=new_room,
                        capacity=int(new_capacity),
                        day_labels=list(selected_days),
                        block_signatures=list(selected_signatures),
                        config_path=_app_config_path(),
                    )
                    if result.get("ok", False):
                        created = int(result.get("created", 0) or 0)
                        skipped_active = int(result.get("skipped_active", 0) or 0)
                        skipped_inactive = int(result.get("skipped_inactive", 0) or 0)
                        summary = (
                            f"Bulk add complete. Created {created}, "
                            f"skipped active {skipped_active}, skipped inactive {skipped_inactive}."
                        )
                        _refresh_state(summary)
                        st.rerun()
                    st.error(str(result.get("error", "Failed to add room sessions.")))
        else:
            st.info("No known day/block combinations available yet. Create a first session above.")

        st.markdown("#### Manual Talks (From-Scratch Input)")
        manual_papers = load_manual_talks(MANUAL_TALKS_FILE)
        if manual_papers:
            manual_rows = [
                {
                    "SubmissionID": paper.submission_id,
                    "Presenter": paper.full_name,
                    "Title": paper.title,
                    "Themes": paper.source_themes,
                }
                for paper in manual_papers
            ]
            st.dataframe(pd.DataFrame(manual_rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No manual talks yet.")

        with st.form("manual_talk_form", clear_on_submit=True):
            full_name = st.text_input("Presenter Name", value="")
            title = st.text_input("Talk Title", value="")
            abstract = st.text_area("Abstract", value="", height=120)
            themes = st.text_input("Themes (comma-separated)", value="")
            email = st.text_input("Email", value="")
            link_to_pdf = st.text_input("PDF URL", value="")
            manual_submit = st.form_submit_button("Add Manual Talk", use_container_width=True)
            if manual_submit:
                _push_undo_snapshot()
                result = create_manual_talk(
                    full_name=full_name,
                    title=title,
                    abstract=abstract,
                    themes=themes,
                    email=email,
                    link_to_pdf=link_to_pdf,
                    manual_talks_path=MANUAL_TALKS_FILE,
                    paper_placements_path=PAPER_PLACEMENTS_FILE,
                )
                if result.get("ok", False):
                    _refresh_state(f"Added manual talk {result.get('submission_id', '')}.")
                    st.rerun()
                st.error(str(result.get("error", "Failed to add manual talk.")))


def _quality_panel(edited_count: int, not_edited_count: int) -> None:
    state = st.session_state.wic_state
    v = state.validations

    st.subheader("Checks")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Accepted papers", v.get("accepted_papers", 0))
    c2.metric("Scheduled papers", v.get("scheduled_papers", 0))
    c3.metric("Overflow papers", v.get("overflow_papers", 0))
    c4.metric("Unassigned papers", v.get("unassigned_papers", 0))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Edited papers", edited_count)
    c6.metric("Not edited papers", not_edited_count)
    c7.metric("Reserve slots", v.get("reserve_slots", 0))
    c8.metric("Sessions", v.get("sessions", 0))

    inactive_assigned = int(v.get("inactive_assigned_papers", 0) or 0)
    inactive_overflow = int(v.get("inactive_overflow_papers", 0) or 0)
    c9, c10 = st.columns(2)
    c9.metric("Inactive-assigned papers", inactive_assigned)
    c10.metric("Inactive overflow papers", inactive_overflow)
    if inactive_assigned > 0:
        st.info(
            "Some papers are assigned to inactive sessions. They stay stored for planning but are hidden from active programme views."
        )

    if v.get("hard_constraints_ok", False):
        st.success("Hard constraints are valid (session grid and forbidden blocks).")
    else:
        st.error("Hard constraints failed.")

    if v.get("has_planning_issues", False):
        st.warning("Planning issues detected (overflow/unassigned/collisions). Publish is still available.")
    else:
        st.success("No planning issues detected.")

    with st.expander("Issue details", expanded=True):
        st.write(
            {
                "duplicate_submission_ids": v.get("duplicate_submission_ids", []),
                "missing_submission_ids": v.get("missing_submission_ids", []),
                "unassigned_submission_ids": v.get("unassigned_submission_ids", []),
                "overflow_by_session": v.get("overflow_by_session", {}),
                "slot_conflicts": v.get("slot_conflicts", []),
                "inactive_sessions": v.get("inactive_sessions", 0),
                "inactive_assigned_papers": v.get("inactive_assigned_papers", 0),
                "inactive_assigned_submission_ids": v.get("inactive_assigned_submission_ids", []),
                "inactive_overflow_by_session": v.get("inactive_overflow_by_session", {}),
                "incomplete_sessions": v.get("incomplete_sessions", []),
                "duplicate_session_codes": v.get("duplicate_session_codes", []),
                "duplicate_session_slots": v.get("duplicate_session_slots", []),
                "day1_opening_assigned_sessions": v.get("day1_opening_assigned_sessions", []),
                "optional_block_assigned_sessions": v.get("optional_block_assigned_sessions", []),
            }
        )


def _clip_text(text: str, max_len: int) -> str:
    value = _clean_display_text(text)
    if len(value) <= max_len:
        return value
    if max_len <= 3:
        return value[:max_len]
    return f"{value[: max_len - 3]}..."


def _day_block_rows(day_talks: pd.DataFrame) -> List[Dict[str, object]]:
    if day_talks.empty:
        return []
    rows_df = (
        day_talks[["BlockNum", "Time", "Block"]]
        .drop_duplicates()
        .sort_values(by=["BlockNum", "Time"], key=lambda s: s.map(parse_start_minutes if s.name == "Time" else lambda x: x))
    )
    out: List[Dict[str, object]] = []
    for row in rows_df.to_dict(orient="records"):
        block_num = int(row["BlockNum"])
        time_label = str(row["Time"])
        block_label = str(row["Block"])
        out.append(
            {
                "BlockNum": block_num,
                "Time": time_label,
                "Block": block_label,
                "Label": f"{_clean_display_text(block_label)} | {time_label}",
            }
        )
    return out


def _get_block_sessions(
    state,
    day_label: str,
    block_num: int,
    time_label: str,
    block_label: str,
) -> List[object]:
    sessions = [
        session
        for session in state.sessions
        if session.day_label == day_label
        and session.block_num == block_num
        and session.time == time_label
        and session.block_label == block_label
    ]
    return sorted(sessions, key=lambda s: room_sort_key(s.room))


def _session_sort_key(session: object) -> tuple:
    return (session.day_num, parse_start_minutes(session.time), room_sort_key(session.room))


def _paper_location_summary(paper: object) -> str:
    status = _normalize_text(getattr(paper, "placement_status", "")).lower()
    session_code = _normalize_text(getattr(paper, "session_code", ""))
    talk_index = int(getattr(paper, "talk_index", 0) or 0)
    overflow_order = int(getattr(paper, "overflow_order", 0) or 0)
    if status == "unassigned":
        return "Unassigned"
    if status == "scheduled":
        if session_code and talk_index > 0:
            return f"Scheduled in {session_code} slot {talk_index}"
        return "Scheduled"
    if status == "overflow":
        if session_code:
            if overflow_order > 0:
                return f"Overflow in {session_code} (#{overflow_order})"
            return f"Overflow in {session_code}"
        return "Overflow"
    return "Unknown placement"


def _candidate_sort_key(paper: object) -> tuple:
    status = _normalize_text(getattr(paper, "placement_status", "")).lower()
    status_rank = {"unassigned": 0, "overflow": 1, "scheduled": 2}
    return (
        status_rank.get(status, 9),
        _normalize_text(getattr(paper, "session_code", "")),
        int(getattr(paper, "talk_index", 0) or 0),
        _normalize_text(getattr(paper, "full_name", "")).lower(),
        _normalize_text(getattr(paper, "submission_id", "")).lower(),
    )


def _set_programme_selection(kind: str, session_id: str, talk_index: int = 0) -> None:
    st.session_state.programme_selection = {
        "kind": kind,
        "session_id": session_id,
        "talk_index": int(talk_index),
    }


def _clear_programme_selection() -> None:
    st.session_state.programme_selection = {}


def _render_programme_block_grid(
    block_sessions: List[object],
    column_width_px: int,
    rooms_per_row: int,
) -> None:
    if not block_sessions:
        st.info("No sessions in this block.")
        return

    first = block_sessions[0]
    block_label = _clean_display_text(first.block_label)
    title_limit = max(56, int(column_width_px / 3))
    slot_title_limit = max(42, int(column_width_px / 3))
    presenter_limit = max(24, int(column_width_px / 8))

    st.markdown(
        f"**{html.escape(block_label)}**  \n"
        f"`{format_minutes(first.start_min)}-{format_minutes(first.end_min)}`"
    )

    rooms = sorted([session.room for session in block_sessions], key=room_sort_key)
    by_room = {session.room: session for session in block_sessions}
    row_size = max(1, min(len(rooms), int(rooms_per_row)))
    selection = st.session_state.get("programme_selection", {})
    selected_kind = ""
    selected_session_id = ""
    selected_talk_index = 0
    if isinstance(selection, dict):
        selected_kind = _normalize_text(selection.get("kind", "")).lower()
        selected_session_id = _normalize_text(selection.get("session_id", ""))
        selected_talk_index = int(selection.get("talk_index", 0) or 0)

    for start_idx in range(0, len(rooms), row_size):
        row_rooms = rooms[start_idx : start_idx + row_size]
        cols = st.columns(len(row_rooms), gap="small")
        for col, room in zip(cols, row_rooms):
            session = by_room[room]
            with col:
                with st.container(border=True):
                    st.caption(f"Room: {room} | {session.session_code}")
                    session_button_label = _clip_text(session.session_title, title_limit)
                    session_is_selected = selected_kind == "session" and selected_session_id == session.session_id
                    if st.button(
                        session_button_label,
                        key=f"select_session_{session.session_id}_{session.day_num}_{session.block_num}",
                        type="primary",
                        use_container_width=True,
                    ):
                        _set_programme_selection("session", session.session_id, 0)
                        st.rerun()

                    for talk_idx in range(1, max(1, session.capacity) + 1):
                        paper = session.papers[talk_idx - 1]
                        slot_is_selected = (
                            selected_kind == "slot"
                            and selected_session_id == session.session_id
                            and selected_talk_index == talk_idx
                        )

                        if paper is None:
                            if st.button(
                                "[Empty slot]",
                                key=f"select_empty_{session.session_id}_{talk_idx}",
                                type="primary" if slot_is_selected else "secondary",
                                use_container_width=True,
                            ):
                                _set_programme_selection("slot", session.session_id, talk_idx)
                                st.rerun()
                            continue

                        presenter = _clip_text(paper.full_name, presenter_limit)
                        title = _clip_text(paper.title, slot_title_limit + 36)
                        abstract_preview = _preview_abstract(paper.abstract)
                        slot_button_label = f"\"{title}\"\n({presenter})"
                        if st.button(
                            slot_button_label,
                            key=f"select_slot_{session.session_id}_{talk_idx}",
                            type="primary" if slot_is_selected else "secondary",
                            use_container_width=True,
                            help=abstract_preview,
                        ):
                            _set_programme_selection("slot", session.session_id, talk_idx)
                            st.rerun()

                    if session.overflow_papers:
                        st.error(f"Overflow: {len(session.overflow_papers)}")


def _on_inspector_paper_fields_change(submission_id: str) -> None:
    theme = _normalize_text(st.session_state.get(f"ins_theme_{submission_id}", ""))
    subtheme = _normalize_text(st.session_state.get(f"ins_subtheme_{submission_id}", ""))
    notes = _normalize_text(st.session_state.get(f"ins_notes_{submission_id}", ""))
    edited_df = pd.DataFrame(
        [{"SubmissionID": submission_id, "PrimaryTheme": theme, "Subtheme": subtheme, "OverrideNotes": notes}]
    )
    _apply_classification_edits_if_changed(edited_df)


def _on_inspector_session_title_change(session_code: str) -> None:
    title = _normalize_text(st.session_state.get(f"ins_session_title_{session_code}", ""))
    _apply_session_name_override(session_code, title)


def _render_paper_slot_inspector(
    state,
    session: object,
    talk_index: int,
    paper: object,
    all_sessions: List[object],
) -> None:
    st.markdown("**Paper Slot**")
    st.caption(
        f"{session.session_code} | {session.time} | {session.room} | Slot {talk_index}"
    )

    presenter = _clean_display_text(paper.full_name)
    title = _clean_display_text(paper.title)
    abstract_preview = _preview_abstract(paper.abstract)
    pdf_url = _normalize_text(paper.link_to_pdf)
    if pdf_url.startswith("http"):
        st.markdown(
            f"<b>{html.escape(presenter)}</b><br>"
            f"<a href='{html.escape(pdf_url)}' target='_blank' rel='noopener noreferrer' "
            f"title='{html.escape(abstract_preview)}'>{html.escape(title)}</a>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<b>{html.escape(presenter)}</b><br>"
            f"<span title='{html.escape(abstract_preview)}'>{html.escape(title)}</span>",
            unsafe_allow_html=True,
        )
    with st.expander("Abstract (click to expand)", expanded=False):
        st.write(abstract_preview or "[No abstract provided]")

    st.markdown("---")
    st.caption("Classification")

    theme_options = list(THEME_ORDER)
    if paper.primary_theme and paper.primary_theme not in theme_options:
        theme_options = [paper.primary_theme] + theme_options

    theme_key = f"ins_theme_{paper.submission_id}"
    theme_src = f"{theme_key}_src"
    if st.session_state.get(theme_src) != paper.primary_theme:
        st.session_state[theme_key] = paper.primary_theme
        st.session_state[theme_src] = paper.primary_theme

    subtheme_key = f"ins_subtheme_{paper.submission_id}"
    subtheme_src = f"{subtheme_key}_src"
    if st.session_state.get(subtheme_src) != paper.detailed_subtheme:
        st.session_state[subtheme_key] = paper.detailed_subtheme
        st.session_state[subtheme_src] = paper.detailed_subtheme

    notes_key = f"ins_notes_{paper.submission_id}"
    notes_src = f"{notes_key}_src"
    if st.session_state.get(notes_src) != paper.override_notes:
        st.session_state[notes_key] = paper.override_notes
        st.session_state[notes_src] = paper.override_notes

    st.selectbox(
        "PrimaryTheme",
        theme_options,
        key=theme_key,
        on_change=_on_inspector_paper_fields_change,
        args=(paper.submission_id,),
    )
    st.text_input(
        "Subtheme",
        key=subtheme_key,
        on_change=_on_inspector_paper_fields_change,
        args=(paper.submission_id,),
    )
    st.text_area(
        "Notes",
        key=notes_key,
        height=100,
        on_change=_on_inspector_paper_fields_change,
        args=(paper.submission_id,),
    )

    st.markdown("---")
    st.caption("Placement")
    if all_sessions:
        session_ids = [s.session_id for s in all_sessions]
        default_idx = session_ids.index(session.session_id) if session.session_id in session_ids else 0

        def _format_session_pick(session_id: str) -> str:
            selected = next((s for s in all_sessions if s.session_id == session_id), None)
            if selected is None:
                return session_id
            return f"{selected.session_code} | {selected.day_label} | {selected.time} | {selected.room} | cap {selected.capacity}"

        target_session_id = st.selectbox(
            "Target Session",
            session_ids,
            index=default_idx,
            key=f"ins_move_session_{paper.submission_id}",
            format_func=_format_session_pick,
        )
        target_session = next((s for s in all_sessions if s.session_id == target_session_id), None)
        max_slots = max(1, int(getattr(target_session, "capacity", 1) if target_session is not None else 1))
        target_slot = st.selectbox(
            "Target Slot",
            list(range(1, max_slots + 1)),
            index=max(0, min(max_slots - 1, talk_index - 1)),
            key=f"ins_move_slot_{paper.submission_id}",
        )
        if st.button("Move Paper", key=f"ins_move_btn_{paper.submission_id}", use_container_width=True):
            if _apply_layout_updates(
                {
                    paper.submission_id: {
                        "PlacementStatus": "scheduled",
                        "SessionId": target_session_id,
                        "TalkIndex": str(target_slot),
                        "OverflowOrder": "",
                    }
                },
                f"Moved {paper.submission_id} to {target_session.session_code if target_session else target_session_id} slot {target_slot}.",
            ):
                st.rerun()

    st.caption("If the target slot/session is full, the move is kept as overflow and flagged in Checks.")
    if st.button("Drop To Unassigned", key=f"ins_drop_{paper.submission_id}", use_container_width=True):
        if _apply_layout_updates(
                {
                    paper.submission_id: {
                        "PlacementStatus": "unassigned",
                        "SessionId": "",
                        "TalkIndex": "",
                        "OverflowOrder": "",
                    }
                },
            f"Moved {paper.submission_id} to unassigned.",
        ):
            st.rerun()


def _render_empty_slot_inspector(state, session: object, talk_index: int) -> None:
    st.markdown("**Empty Slot**")
    st.caption(
        f"{session.session_code} | {session.time} | {session.room} | Slot {talk_index}"
    )

    unassigned = list(state.unassigned_papers)
    st.metric("Unassigned papers", len(unassigned))
    st.caption("Suggestions show unassigned papers first. Choosing an already assigned paper will move it here.")
    all_papers = sorted(list(state.papers), key=_candidate_sort_key)
    if not all_papers:
        st.info("No papers available.")
        return

    paper_map = {paper.submission_id: paper for paper in all_papers}
    options = [""] + [paper.submission_id for paper in all_papers]

    def _format_pick(submission_id: str) -> str:
        sid = _normalize_text(submission_id)
        if not sid:
            return "Select a paper..."
        paper = paper_map.get(sid)
        if paper is None:
            return sid
        name = _clip_text(_clean_display_text(paper.full_name), 40)
        title = _clip_text(_clean_display_text(paper.title), 68)
        placement = _paper_location_summary(paper)
        return f"{sid} | {name} | {title} [{placement}]"

    pick = st.selectbox(
        "Assign or move paper",
        options,
        format_func=_format_pick,
        key=f"ins_empty_pick_{session.session_id}_{talk_index}",
    )
    selected_paper = paper_map.get(_normalize_text(pick))
    if selected_paper is not None and _normalize_text(selected_paper.placement_status).lower() != "unassigned":
        st.info(f"Assigning this paper will move it from: {_paper_location_summary(selected_paper)}")

    if st.button(
        "Assign To This Slot",
        key=f"ins_empty_assign_{session.session_id}_{talk_index}",
        use_container_width=True,
    ):
        sid = _normalize_text(pick)
        if sid:
            if _apply_layout_updates(
                {
                    sid: {
                        "PlacementStatus": "scheduled",
                        "SessionId": session.session_id,
                        "TalkIndex": str(talk_index),
                        "OverflowOrder": "",
                    }
                },
                f"Assigned {sid} to {session.session_code} slot {talk_index}.",
            ):
                st.rerun()


def _render_session_inspector(state, session: object, all_sessions: List[object]) -> None:
    st.markdown("**Session**")
    st.caption(f"{session.session_code} | {session.time} | {session.room}")

    title_key = f"ins_session_title_{session.session_code}"
    title_src = f"{title_key}_src"
    current_title = _normalize_text(session.session_title)
    if st.session_state.get(title_src) != current_title:
        st.session_state[title_key] = current_title
        st.session_state[title_src] = current_title

    st.text_input(
        "Session Title",
        key=title_key,
        on_change=_on_inspector_session_title_change,
        args=(session.session_code,),
    )
    st.caption(f"Theme: {session.primary_theme}")
    st.caption(f"Subtheme: {session.subtheme}")
    st.caption(f"Capacity: {session.capacity}")
    st.caption(
        f"Time: {minutes_to_clock(session.start_min)}-{minutes_to_clock(session.end_min)} "
        f"({max(1, session.end_min - session.start_min)} min)"
    )

    st.markdown("---")
    st.caption("Structure")
    cap_col, code_col, dur_col = st.columns(3)
    new_capacity = cap_col.number_input(
        "Capacity",
        min_value=1,
        max_value=20,
        value=max(1, int(session.capacity)),
        step=1,
        key=f"ins_capacity_{session.session_id}",
    )
    new_code = code_col.text_input(
        "Session Code",
        value=session.session_code,
        key=f"ins_session_code_{session.session_id}",
    )
    new_duration = dur_col.number_input(
        "Duration (min)",
        min_value=1,
        max_value=360,
        value=max(1, int(session.end_min - session.start_min)),
        step=5,
        key=f"ins_duration_{session.session_id}",
    )
    if st.button("Apply Structure Changes", key=f"ins_apply_structure_{session.session_id}", use_container_width=True):
        snapshot = _snapshot_for_undo()
        result = update_session_structure_row(
            session.session_id,
            {
                "Capacity": str(int(new_capacity)),
                "SessionCode": new_code,
                "EndMin": str(int(session.start_min) + int(new_duration)),
                "TimeLabel": build_time_label(int(session.start_min), int(session.start_min) + int(new_duration)),
            },
        )
        if not result.get("ok", False):
            st.error(str(result.get("error", "Failed to update session structure.")))
        else:
            _push_undo_snapshot(snapshot)
            _refresh_state(f"Updated structure for {session.session_code}.")
            st.rerun()

    st.markdown("---")
    st.caption("Session Slots")
    for talk_idx in range(1, max(1, session.capacity) + 1):
        paper = session.papers[talk_idx - 1]
        if paper is None:
            st.write(f"Slot {talk_idx}: [Empty slot]")
            if st.button(
                f"Open Empty Slot {talk_idx}",
                key=f"ins_open_empty_{session.session_id}_{talk_idx}",
                use_container_width=True,
            ):
                _set_programme_selection("slot", session.session_id, talk_idx)
                st.rerun()
            continue
        st.write(f"Slot {talk_idx}: {paper.submission_id} | {_clip_text(paper.full_name, 52)}")
        if st.button(
            f"Open Slot {talk_idx}",
            key=f"ins_open_slot_{session.session_id}_{talk_idx}",
            use_container_width=True,
        ):
            _set_programme_selection("slot", session.session_id, talk_idx)
            st.rerun()

    st.markdown("---")
    st.caption("Session Lifecycle")
    action_col1, action_col2 = st.columns(2)
    confirm_clear = action_col1.checkbox("Confirm clear", key=f"ins_confirm_clear_{session.session_id}")
    if action_col1.button(
        "Clear Session",
        key=f"ins_clear_session_{session.session_id}",
        use_container_width=True,
        disabled=not confirm_clear,
    ):
        snapshot = _snapshot_for_undo()
        result = clear_session(session.session_id)
        if not result.get("ok", False):
            st.error(str(result.get("error", "Failed to clear session.")))
        else:
            _push_undo_snapshot(snapshot)
            moved = int(result.get("moved_to_unassigned", 0) or 0)
            _refresh_state(f"Cleared {session.session_code} and moved {moved} paper(s) to unassigned.")
            st.rerun()
    confirm_remove = action_col2.checkbox("Confirm remove", key=f"ins_confirm_remove_{session.session_id}")
    if action_col2.button(
        "Remove Session",
        key=f"ins_remove_session_{session.session_id}",
        use_container_width=True,
        disabled=not confirm_remove,
    ):
        snapshot = _snapshot_for_undo()
        result = remove_session(session.session_id)
        if not result.get("ok", False):
            st.error(str(result.get("error", "Failed to remove session.")))
        else:
            _push_undo_snapshot(snapshot)
            _clear_programme_selection()
            moved = int(result.get("moved_to_unassigned", 0) or 0)
            _refresh_state(f"Removed {session.session_code}; {moved} paper(s) moved to unassigned.")
            st.rerun()

    st.markdown("---")
    st.caption(f"Overflow papers: {len(session.overflow_papers)}")
    if not session.overflow_papers:
        st.info("No overflow papers in this session.")
        return

    for overflow_pos, paper in enumerate(session.overflow_papers, start=1):
        with st.expander(f"Overflow {overflow_pos}: {paper.submission_id} | {_clip_text(paper.title, 62)}", expanded=False):
            presenter = _clean_display_text(paper.full_name)
            title = _clean_display_text(paper.title)
            abstract_preview = _preview_abstract(paper.abstract)
            pdf_url = _normalize_text(paper.link_to_pdf)
            if pdf_url.startswith("http"):
                st.markdown(
                    f"<b>{html.escape(presenter)}</b><br>"
                    f"<a href='{html.escape(pdf_url)}' target='_blank' rel='noopener noreferrer' "
                    f"title='{html.escape(abstract_preview)}'>{html.escape(title)}</a>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<b>{html.escape(presenter)}</b><br>"
                    f"<span title='{html.escape(abstract_preview)}'>{html.escape(title)}</span>",
                    unsafe_allow_html=True,
                )

            session_ids = [s.session_id for s in all_sessions]
            default_idx = session_ids.index(session.session_id) if session.session_id in session_ids else 0
            target_session_id = st.selectbox(
                "Target Session",
                session_ids,
                index=default_idx,
                key=f"ins_ov_target_session_{paper.submission_id}_{session.session_id}_{overflow_pos}",
                format_func=lambda session_id: next(
                    (
                        f"{s.session_code} | {s.day_label} | {s.time} | {s.room} | cap {s.capacity}"
                        for s in all_sessions
                        if s.session_id == session_id
                    ),
                    session_id,
                ),
            )
            target_session = next((s for s in all_sessions if s.session_id == target_session_id), None)
            target_capacity = max(1, int(getattr(target_session, "capacity", 1) if target_session is not None else 1))
            target_slot = st.selectbox(
                "Target Slot",
                list(range(1, target_capacity + 1)),
                index=0,
                key=f"ins_ov_target_slot_{paper.submission_id}_{session.session_id}_{overflow_pos}",
            )
            if st.button(
                "Move Overflow Paper",
                key=f"ins_ov_move_{paper.submission_id}_{session.session_id}_{overflow_pos}",
                use_container_width=True,
            ):
                if _apply_layout_updates(
                    {
                        paper.submission_id: {
                            "PlacementStatus": "scheduled",
                            "SessionId": target_session_id,
                            "TalkIndex": str(target_slot),
                            "OverflowOrder": "",
                        }
                    },
                    f"Moved {paper.submission_id} to {target_session.session_code if target_session else target_session_id} slot {target_slot}.",
                ):
                    st.rerun()
            if st.button(
                "Drop Overflow To Unassigned",
                key=f"ins_ov_drop_{paper.submission_id}_{session.session_id}_{overflow_pos}",
                use_container_width=True,
            ):
                if _apply_layout_updates(
                    {
                        paper.submission_id: {
                            "PlacementStatus": "unassigned",
                            "SessionId": "",
                            "TalkIndex": "",
                            "OverflowOrder": "",
                        }
                    },
                    f"Moved {paper.submission_id} to unassigned.",
                ):
                    st.rerun()


def _render_programme_inspector(state) -> None:
    head1, head2 = st.columns([4, 1])
    head1.markdown("### Inspector")
    if head2.button("✕", key="close_inspector_btn", help="Close inspector", use_container_width=True):
        _clear_programme_selection()
        st.rerun()
    st.caption("Selection-based editor from the programme grid.")

    unassigned_count = len(state.unassigned_papers)
    overflow_count = state.validations.get("overflow_papers", 0)
    c1, c2 = st.columns(2)
    c1.metric("Unassigned", unassigned_count)
    c2.metric("Overflow", overflow_count)

    selection = st.session_state.get("programme_selection", {})
    if not isinstance(selection, dict) or not selection.get("session_id"):
        st.info("Nothing selected yet.")
        return

    session_map = {session.session_id: session for session in state.sessions}
    session = session_map.get(_normalize_text(selection.get("session_id", "")))
    if session is None:
        st.warning("Selected item is no longer available. Pick another slot/session.")
        _clear_programme_selection()
        return

    all_sessions = list(sorted(state.sessions, key=_session_sort_key))
    kind = _normalize_text(selection.get("kind", ""))
    if kind == "session":
        _render_session_inspector(state, session, all_sessions)
        return

    talk_index = int(selection.get("talk_index", 0) or 0)
    if talk_index < 1 or talk_index > len(session.papers):
        st.warning("Invalid slot selection. Pick a slot again.")
        return

    paper = session.papers[talk_index - 1]
    if paper is None:
        _render_empty_slot_inspector(state, session, talk_index)
    else:
        _render_paper_slot_inspector(state, session, talk_index, paper, all_sessions)


_init_session_state()
state = st.session_state.wic_state
edited_ids = set(getattr(state, "edited_submission_ids", set()))
edited_count = len([p for p in state.papers if p.submission_id in edited_ids])
not_edited_count = len(state.papers) - edited_count

title_col, edit_col = st.columns([8.6, 0.6], gap="small")
with title_col:
    st.markdown(
        (
            "<h1 style='margin:0;text-align:left;'>"
            "Conference Studio"
            f"<span style='color:#5f6f86;font-weight:600;'>&nbsp;&middot;&nbsp;{html.escape(st.session_state.conference_label)}</span>"
            "</h1>"
        ),
        unsafe_allow_html=True,
    )
with edit_col:
    if st.button("✎", key="conference_title_edit_toggle", help="Edit conference name."):
        st.session_state.conference_edit_mode = True
        st.session_state.conference_label_draft = st.session_state.conference_label
        st.rerun()

if st.session_state.get("conference_edit_mode", False):
    st.text_input(
        "Conference name",
        key="conference_label_draft",
        label_visibility="collapsed",
        placeholder="Conference name",
    )
    edit_save_col, edit_cancel_col = st.columns([1.2, 1.2], gap="small")
    if edit_save_col.button("Save conference name", use_container_width=True, key="conference_name_save"):
        _save_conference_label(st.session_state.get("conference_label_draft", ""))
        st.session_state.conference_edit_mode = False
        st.rerun()
    if edit_cancel_col.button("Cancel", use_container_width=True, key="conference_name_cancel"):
        st.session_state.conference_edit_mode = False
        st.rerun()

if st.session_state.flash_message:
    st.success(st.session_state.flash_message)
    st.session_state.flash_message = ""

nav_col, actions_col = st.columns([5.2, 1.8], gap="small")
with nav_col:
    pills_widget = getattr(st, "pills", None)
    if callable(pills_widget):
        try:
            pills_widget(
                "Navigation",
                TAB_LABELS,
                key="active_tab",
                selection_mode="single",
                label_visibility="collapsed",
            )
        except TypeError:
            pills_widget(
                "Navigation",
                TAB_LABELS,
                key="active_tab",
            )
    else:
        st.radio(
            "Navigation",
            TAB_LABELS,
            key="active_tab",
            horizontal=True,
            label_visibility="collapsed",
        )
with actions_col:
    render_top_actions(
        state=state,
        not_edited_count=not_edited_count,
        undo_count=_undo_count(),
        undo_last_change=_undo_last_change,
        refresh_state=_refresh_state,
        export_publish_excel=export_publish_excel,
        export_publish_pdf=export_publish_pdf,
        export_draft_workbook=export_draft_workbook,
    )

active_tab = _normalize_text(st.session_state.get("active_tab", TAB_LABELS[0]))
if active_tab not in TAB_LABELS:
    active_tab = TAB_LABELS[0]
    st.session_state.active_tab = active_tab

if active_tab == "Programme":
    render_programme_tab_view(
        state=state,
        programme_talk_rows=programme_talk_rows,
        day_block_rows=_day_block_rows,
        get_block_sessions=_get_block_sessions,
        render_programme_block_grid=_render_programme_block_grid,
        render_programme_inspector=_render_programme_inspector,
    )
elif active_tab == "Structure":
    _render_structure_tab(state)
elif active_tab == "Paper List":
    render_paper_list_tab(
        state=state,
        edited_ids=edited_ids,
        theme_order=THEME_ORDER,
        papers_to_rows=papers_to_rows,
        apply_classification_edits_if_changed=_apply_classification_edits_if_changed,
        apply_paper_metadata_edits_if_changed=_apply_paper_metadata_edits_if_changed,
        apply_paper_session_selection_edit=_apply_paper_session_selection_edit,
    )
else:
    _quality_panel(edited_count=edited_count, not_edited_count=not_edited_count)
