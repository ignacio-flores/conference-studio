from __future__ import annotations

from datetime import datetime
import html
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
    PAPER_PLACEMENTS_FILE,
    PROGRAMME_LAYOUT_OVERRIDES_FILE,
    SESSION_STRUCTURE_FILE,
    SESSION_NAME_OVERRIDES_FILE,
    THEME_ORDER,
    bulk_add_room_sessions,
    build_programme_state,
    clear_session,
    create_manual_talk,
    create_session,
    format_minutes,
    load_manual_talks,
    load_classification_overrides,
    load_paper_placements,
    load_session_structure_rows,
    load_session_name_overrides,
    parse_start_minutes,
    papers_to_rows,
    programme_talk_rows,
    remove_session,
    restore_session,
    room_sort_key,
    sessions_to_rows,
    update_session_structure_row,
    validate_session_structure_rows,
    write_classification_overrides,
    write_paper_placements,
    write_session_structure_rows,
    write_session_name_overrides,
)
from ui.actions import render_top_actions
from ui.papers import render_paper_list_tab
from ui.programme import render_programme_tab as render_programme_tab_view
from ui.sessions import render_session_names_tab
from ui.structure_time import (
    build_time_label,
    minutes_to_clock,
    parse_clock_minutes,
    resolve_session_time_inputs,
)

NOTE_SPLIT_RE = re.compile(r"note\s*to\s*conference\s*organizers", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")

APP_CONFERENCE_CONFIG = load_conference_config()
APP_TITLE = f"{APP_CONFERENCE_CONFIG.conference_title} Reclassification Studio"


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
        config_path=config_path,
    )


def _read_state_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_state_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _init_session_state() -> None:
    if "wic_state" not in st.session_state:
        st.session_state.wic_state = _load_state()
    if "last_change" not in st.session_state:
        st.session_state.last_change = None
    if "flash_message" not in st.session_state:
        st.session_state.flash_message = ""


def _snapshot_for_undo() -> Dict[str, object]:
    tracked_files = [
        CLASSIFICATION_OVERRIDES_FILE,
        SESSION_NAME_OVERRIDES_FILE,
        PROGRAMME_LAYOUT_OVERRIDES_FILE,
        SESSION_STRUCTURE_FILE,
        PAPER_PLACEMENTS_FILE,
        MANUAL_TALKS_FILE,
    ]
    return {
        "files": {str(path): _read_state_file(path) for path in tracked_files},
        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
    }


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

    st.session_state.last_change = snapshot
    write_classification_overrides(existing_overrides.values(), CLASSIFICATION_OVERRIDES_FILE)
    _refresh_state("Applied paper classification changes.")
    return True


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

    st.session_state.last_change = snapshot
    write_session_name_overrides(merged, SESSION_NAME_OVERRIDES_FILE)
    _refresh_state(f"Updated session title for {code}.")
    return True


def _apply_session_name_edits_if_changed(edited_df: pd.DataFrame) -> bool:
    if edited_df.empty:
        return False

    current_overrides = load_session_name_overrides(SESSION_NAME_OVERRIDES_FILE)
    merged = dict(current_overrides)
    changed = False
    snapshot: Optional[Dict[str, object]] = None

    for _, row in edited_df.iterrows():
        code = _normalize_text(row.get("SessionCode", ""))
        if not code:
            continue

        new_title = _normalize_text(row.get("CustomTitle", row.get("SessionTitleOverride", "")))
        old_title = _normalize_text(current_overrides.get(code, ""))

        if new_title == old_title:
            continue

        if snapshot is None:
            snapshot = _snapshot_for_undo()

        if new_title:
            merged[code] = new_title
        else:
            merged.pop(code, None)
        changed = True

    if not changed:
        return False

    st.session_state.last_change = snapshot
    write_session_name_overrides(merged, SESSION_NAME_OVERRIDES_FILE)
    _refresh_state("Applied session title changes.")
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

    st.session_state.last_change = _snapshot_for_undo()
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

    st.session_state.last_change = snapshot
    write_paper_placements(merged.values(), PAPER_PLACEMENTS_FILE)
    _refresh_state(message)
    return True


def _undo_last_change() -> bool:
    last_change = st.session_state.get("last_change")
    if not last_change:
        return False

    files_snapshot = last_change.get("files", {})
    if not isinstance(files_snapshot, dict):
        return False
    for raw_path, content in files_snapshot.items():
        _write_state_file(Path(raw_path), str(content))

    st.session_state.last_change = None
    _refresh_state("Undid last change.")
    return True


def _render_structure_tab(state) -> None:
    st.subheader("Structure")
    config = load_conference_config(_app_config_path())
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
    structure_editor_rows: List[Dict[str, object]] = []
    for row in session_rows:
        start_min = int(str(row.get("StartMin", "0") or "0"))
        end_min = int(str(row.get("EndMin", str(start_min + config.structure.default_session_duration_min)) or "0"))
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
                "Capacity": int(str(row.get("Capacity", str(config.structure.default_session_capacity)) or config.structure.default_session_capacity)),
                "Source": _normalize_text(row.get("Source", "manual")) or "manual",
            }
        )
    structure_df = pd.DataFrame(structure_editor_rows)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active sessions", len(state.sessions))
    c2.metric("Inactive sessions", len(state.inactive_sessions))
    c3.metric("Unassigned papers", len(state.unassigned_papers))
    c4.metric("Manual talks", len([p for p in state.papers if _normalize_text(getattr(p, "source", "")) == "manual"]))

    st.markdown("#### Session Structure Table")
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

    st.markdown("#### Lifecycle Actions")
    active_sessions = sorted(state.sessions, key=_session_sort_key)
    inactive_sessions = sorted(state.inactive_sessions, key=_session_sort_key)

    left, right = st.columns(2, gap="large")
    with left:
        st.caption("Active Session Actions")
        active_ids = [session.session_id for session in active_sessions]
        if active_ids:
            active_pick = st.selectbox(
                "Select active session",
                active_ids,
                format_func=lambda session_id: next(
                    (
                        f"{s.session_code} | {s.day_label} | {s.time} | {s.room} | cap {s.capacity}"
                        for s in active_sessions
                        if s.session_id == session_id
                    ),
                    session_id,
                ),
                key="structure_active_pick",
            )
            a1, a2 = st.columns(2)
            confirm_clear = a1.checkbox("Confirm clear", key="structure_confirm_clear")
            if a1.button(
                "Clear Session",
                key="structure_clear_session",
                use_container_width=True,
                disabled=not confirm_clear,
            ):
                st.session_state.last_change = _snapshot_for_undo()
                result = clear_session(active_pick)
                if result.get("ok", False):
                    moved = int(result.get("moved_to_unassigned", 0) or 0)
                    _refresh_state(f"Cleared session and moved {moved} paper(s) to unassigned.")
                    st.rerun()
                st.error(str(result.get("error", "Failed to clear session.")))
            confirm_remove = a2.checkbox("Confirm remove", key="structure_confirm_remove")
            if a2.button(
                "Remove Session",
                key="structure_remove_session",
                use_container_width=True,
                disabled=not confirm_remove,
            ):
                st.session_state.last_change = _snapshot_for_undo()
                result = remove_session(active_pick)
                if result.get("ok", False):
                    moved = int(result.get("moved_to_unassigned", 0) or 0)
                    _refresh_state(f"Removed session and moved {moved} paper(s) to unassigned.")
                    st.rerun()
                st.error(str(result.get("error", "Failed to remove session.")))
        else:
            st.info("No active sessions available.")

    with right:
        st.caption("Inactive Session Actions")
        inactive_ids = [session.session_id for session in inactive_sessions]
        if inactive_ids:
            inactive_pick = st.selectbox(
                "Select inactive session",
                inactive_ids,
                format_func=lambda session_id: next(
                    (
                        f"{s.session_code} | {s.day_label} | {s.time} | {s.room} | cap {s.capacity}"
                        for s in inactive_sessions
                        if s.session_id == session_id
                    ),
                    session_id,
                ),
                key="structure_inactive_pick",
            )
            if st.button("Restore Session", key="structure_restore_session", use_container_width=True):
                st.session_state.last_change = _snapshot_for_undo()
                result = restore_session(inactive_pick, config_path=_app_config_path())
                if result.get("ok", False):
                    _refresh_state("Restored session to active.")
                    st.rerun()
                st.error(str(result.get("error", "Failed to restore session.")))
        else:
            st.info("No inactive sessions available.")

    st.markdown("#### Create Session")
    day_options = list(config.days) or sorted({row.get("DayLabel", "") for row in session_rows if row.get("DayLabel", "")})
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
            st.session_state.last_change = _snapshot_for_undo()
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
        block_num = int(str(row.get("BlockNum", "0") or "0"))
        block_label = _normalize_text(row.get("BlockLabel", ""))
        time_label = _normalize_text(row.get("TimeLabel", ""))
        if block_num <= 0 or not time_label:
            continue
        signature = f"{block_num}::{block_label}::{time_label}"
        display_label = f"B{block_num} | {block_label} | {time_label}"
        block_signature_to_label[signature] = display_label
    block_signatures_sorted = sorted(
        block_signature_to_label.keys(),
        key=lambda sig: (
            int(sig.split("::", 1)[0]),
            block_signature_to_label.get(sig, ""),
        ),
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
                st.session_state.last_change = _snapshot_for_undo()
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
            st.session_state.last_change = _snapshot_for_undo()
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

    st.subheader("Quality")
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

    st.caption("If the target slot/session is full, the move is kept as overflow and flagged in Quality.")
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
            st.session_state.last_change = snapshot
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
            st.session_state.last_change = snapshot
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
            st.session_state.last_change = snapshot
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

st.title(APP_TITLE)
st.caption("Programme-first mode: edits are auto-applied, auto-saved, and synced immediately across tabs.")

if st.session_state.flash_message:
    st.success(st.session_state.flash_message)
    st.session_state.flash_message = ""

render_top_actions(
    state=state,
    not_edited_count=not_edited_count,
    can_undo=st.session_state.last_change is not None,
    undo_last_change=_undo_last_change,
    refresh_state=_refresh_state,
    export_publish_excel=export_publish_excel,
    export_publish_pdf=export_publish_pdf,
    export_draft_workbook=export_draft_workbook,
)

_tabs = st.tabs(["Programme", "Structure", "Paper List", "Session Names", "Quality"])

with _tabs[0]:
    render_programme_tab_view(
        state=state,
        programme_talk_rows=programme_talk_rows,
        day_block_rows=_day_block_rows,
        get_block_sessions=_get_block_sessions,
        render_programme_block_grid=_render_programme_block_grid,
        render_programme_inspector=_render_programme_inspector,
    )

with _tabs[1]:
    _render_structure_tab(state)

with _tabs[2]:
    render_paper_list_tab(
        state=state,
        edited_ids=edited_ids,
        theme_order=THEME_ORDER,
        papers_to_rows=papers_to_rows,
        apply_classification_edits_if_changed=_apply_classification_edits_if_changed,
    )

with _tabs[3]:
    render_session_names_tab(
        state=state,
        sessions_to_rows=sessions_to_rows,
        load_session_name_overrides=load_session_name_overrides,
        session_name_overrides_file=SESSION_NAME_OVERRIDES_FILE,
        apply_session_name_edits_if_changed=_apply_session_name_edits_if_changed,
    )

with _tabs[4]:
    _quality_panel(edited_count=edited_count, not_edited_count=not_edited_count)
