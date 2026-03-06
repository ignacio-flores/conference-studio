from __future__ import annotations

from datetime import datetime
import html
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd
import streamlit as st

from exporters.publish import export_draft_workbook, export_publish_excel, export_publish_pdf
from reclassification_engine import (
    CLASSIFICATION_OVERRIDES_FILE,
    PROGRAMME_FILE,
    PROGRAMME_LAYOUT_OVERRIDES_FILE,
    SESSION_NAME_OVERRIDES_FILE,
    SUBMISSIONS_FILE,
    THEME_ORDER,
    build_programme_state,
    format_minutes,
    load_classification_overrides,
    load_programme_layout_overrides,
    load_session_name_overrides,
    parse_start_minutes,
    papers_to_rows,
    programme_talk_rows,
    room_sort_key,
    sessions_to_rows,
    write_classification_overrides,
    write_programme_layout_overrides,
    write_session_name_overrides,
)

try:
    from streamlit_sortables import sort_items as sortable_items
except Exception:
    sortable_items = None


NOTE_SPLIT_RE = re.compile(r"note\s*to\s*conference\s*organizers", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
DRAG_ITEM_SEP = " || "


st.set_page_config(page_title="WIC 2026 Reclassification Studio", layout="wide")
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


def _paper_drag_label(submission_id: str, title: str) -> str:
    compact_title = _clean_display_text(title)
    if len(compact_title) > 120:
        compact_title = f"{compact_title[:117]}..."
    return f"{submission_id}{DRAG_ITEM_SEP}{compact_title}"


def _sid_from_drag_label(label: str) -> str:
    return _normalize_text(str(label).split(DRAG_ITEM_SEP, 1)[0])


def _load_state():
    return build_programme_state(
        submissions_path=Path(SUBMISSIONS_FILE),
        programme_path=Path(PROGRAMME_FILE),
        classification_overrides_path=CLASSIFICATION_OVERRIDES_FILE,
        session_name_overrides_path=SESSION_NAME_OVERRIDES_FILE,
        programme_layout_overrides_path=PROGRAMME_LAYOUT_OVERRIDES_FILE,
    )


def _init_session_state() -> None:
    if "wic_state" not in st.session_state:
        st.session_state.wic_state = _load_state()
    if "last_change" not in st.session_state:
        st.session_state.last_change = None
    if "flash_message" not in st.session_state:
        st.session_state.flash_message = ""


def _edited_submission_ids() -> Set[str]:
    edited: Set[str] = set()

    class_overrides = load_classification_overrides(CLASSIFICATION_OVERRIDES_FILE)
    for sid, row in class_overrides.items():
        if (
            _normalize_text(row.get("OverridePrimaryTheme", ""))
            or _normalize_text(row.get("OverrideSubtheme", ""))
            or _normalize_text(row.get("OverrideNotes", ""))
            or _normalize_text(row.get("Reviewed", "")).lower() in {"true", "1", "yes", "y"}
        ):
            edited.add(sid)

    layout_overrides = load_programme_layout_overrides(PROGRAMME_LAYOUT_OVERRIDES_FILE)
    for sid, row in layout_overrides.items():
        status = _normalize_text(row.get("PlacementStatus", "")).lower()
        session_code = _normalize_text(row.get("SessionCode", ""))
        talk_index = _normalize_text(row.get("TalkIndex", ""))
        overflow_order = _normalize_text(row.get("OverflowOrder", ""))
        if status in {"unassigned", "overflow"} or session_code or talk_index or overflow_order:
            edited.add(sid)

    return edited


def _snapshot_for_undo() -> Dict[str, object]:
    return {
        "classification": load_classification_overrides(CLASSIFICATION_OVERRIDES_FILE),
        "session_titles": load_session_name_overrides(SESSION_NAME_OVERRIDES_FILE),
        "layout": load_programme_layout_overrides(PROGRAMME_LAYOUT_OVERRIDES_FILE),
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

    session_code = _normalize_text(row.get("SessionCode", ""))
    talk_index = _normalize_text(row.get("TalkIndex", ""))
    overflow_order = _normalize_text(row.get("OverflowOrder", ""))

    if status == "unassigned":
        session_code = ""
        talk_index = ""
        overflow_order = ""
    elif status == "scheduled":
        overflow_order = ""
    elif status == "overflow":
        talk_index = ""

    return {
        "SubmissionID": _normalize_text(row.get("SubmissionID", "")),
        "PlacementStatus": status,
        "SessionCode": session_code,
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

        new_title = _normalize_text(row.get("SessionTitleOverride", ""))
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


def _apply_layout_updates(update_rows: Dict[str, Dict[str, object]], message: str) -> bool:
    if not update_rows:
        return False

    current_overrides = load_programme_layout_overrides(PROGRAMME_LAYOUT_OVERRIDES_FILE)
    merged = dict(current_overrides)
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
                "SessionCode": row.get("SessionCode", ""),
                "TalkIndex": row.get("TalkIndex", ""),
                "OverflowOrder": row.get("OverflowOrder", ""),
                "UpdatedAt": now,
            },
            now=now,
        )

        existing_raw = current_overrides.get(sid, {})
        existing = _normalize_layout_override_row(
            {
                "SubmissionID": sid,
                "PlacementStatus": existing_raw.get("PlacementStatus", ""),
                "SessionCode": existing_raw.get("SessionCode", ""),
                "TalkIndex": existing_raw.get("TalkIndex", ""),
                "OverflowOrder": existing_raw.get("OverflowOrder", ""),
                "UpdatedAt": existing_raw.get("UpdatedAt", ""),
            },
            now=now,
        )

        if (
            normalized["PlacementStatus"] == existing["PlacementStatus"]
            and normalized["SessionCode"] == existing["SessionCode"]
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
    write_programme_layout_overrides(merged.values(), PROGRAMME_LAYOUT_OVERRIDES_FILE)
    _refresh_state(message)
    return True


def _undo_last_change() -> bool:
    last_change = st.session_state.get("last_change")
    if not last_change:
        return False

    classification_snapshot = last_change.get("classification", {})
    session_snapshot = last_change.get("session_titles", {})
    layout_snapshot = last_change.get("layout", {})

    write_classification_overrides(classification_snapshot.values(), CLASSIFICATION_OVERRIDES_FILE)
    write_session_name_overrides(session_snapshot, SESSION_NAME_OVERRIDES_FILE)
    write_programme_layout_overrides(layout_snapshot.values(), PROGRAMME_LAYOUT_OVERRIDES_FILE)

    st.session_state.last_change = None
    _refresh_state("Undid last change.")
    return True


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
        if session_code and talk_index in {1, 2, 3, 4}:
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


def _set_programme_selection(kind: str, session_code: str, talk_index: int = 0) -> None:
    st.session_state.programme_selection = {
        "kind": kind,
        "session_code": session_code,
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
    start = parse_start_minutes(first.time)
    title_limit = max(56, int(column_width_px / 3))
    slot_title_limit = max(42, int(column_width_px / 3))
    presenter_limit = max(24, int(column_width_px / 8))

    st.markdown(
        f"**{html.escape(block_label)}**  \n"
        f"`{format_minutes(start)}-{format_minutes(start + 90)}`"
    )

    rooms = sorted([session.room for session in block_sessions], key=room_sort_key)
    by_room = {session.room: session for session in block_sessions}
    row_size = max(1, min(len(rooms), int(rooms_per_row)))
    selection = st.session_state.get("programme_selection", {})
    selected_kind = ""
    selected_session_code = ""
    selected_talk_index = 0
    if isinstance(selection, dict):
        selected_kind = _normalize_text(selection.get("kind", "")).lower()
        selected_session_code = _normalize_text(selection.get("session_code", ""))
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
                    session_is_selected = selected_kind == "session" and selected_session_code == session.session_code
                    if st.button(
                        session_button_label,
                        key=f"select_session_{session.session_code}_{session.day_num}_{session.block_num}",
                        type="primary",
                        use_container_width=True,
                    ):
                        _set_programme_selection("session", session.session_code, 0)
                        st.rerun()

                    for talk_idx in range(1, 5):
                        paper = session.papers[talk_idx - 1]
                        slot_is_selected = (
                            selected_kind == "slot"
                            and selected_session_code == session.session_code
                            and selected_talk_index == talk_idx
                        )

                        if paper is None:
                            if st.button(
                                "[Empty slot]",
                                key=f"select_empty_{session.session_code}_{talk_idx}",
                                type="primary" if slot_is_selected else "secondary",
                                use_container_width=True,
                            ):
                                _set_programme_selection("slot", session.session_code, talk_idx)
                                st.rerun()
                            continue

                        presenter = _clip_text(paper.full_name, presenter_limit)
                        title = _clip_text(paper.title, slot_title_limit + 36)
                        abstract_preview = _preview_abstract(paper.abstract)
                        slot_button_label = f"\"{title}\"\n({presenter})"
                        if st.button(
                            slot_button_label,
                            key=f"select_slot_{session.session_code}_{talk_idx}",
                            type="primary" if slot_is_selected else "secondary",
                            use_container_width=True,
                            help=abstract_preview,
                        ):
                            _set_programme_selection("slot", session.session_code, talk_idx)
                            st.rerun()

                    if session.overflow_papers:
                        st.error(f"Overflow: {len(session.overflow_papers)}")


def _sortable_result_to_header_items(raw_result: object, headers: List[str]) -> Optional[Dict[str, List[str]]]:
    if not isinstance(raw_result, list):
        return None

    parsed: Dict[str, List[str]] = {}

    if len(raw_result) == len(headers) and all(isinstance(item, dict) for item in raw_result):
        for idx, item in enumerate(raw_result):
            header = _normalize_text(item.get("header", "")) or headers[idx]
            items = item.get("items", [])
            if not isinstance(items, list):
                items = []
            parsed[header] = [str(v) for v in items]
        return parsed

    if len(raw_result) == len(headers) and all(isinstance(item, list) for item in raw_result):
        for idx, items in enumerate(raw_result):
            parsed[headers[idx]] = [str(v) for v in items]
        return parsed

    return None


def _render_dragdrop_board(block_sessions: List[object], unassigned_papers: List[object]) -> bool:
    if sortable_items is None:
        st.info("Drag/drop board unavailable: install `streamlit-sortables` to enable it. Click-based move controls remain available below.")
        return False

    header_to_session: Dict[str, str] = {}
    containers: List[Dict[str, object]] = []

    for session in block_sessions:
        header = f"{session.session_code} ({session.room})"
        header_to_session[header] = session.session_code
        cards: List[str] = []
        for paper in session.papers:
            if paper is not None:
                cards.append(_paper_drag_label(paper.submission_id, paper.title))
        for paper in session.overflow_papers:
            cards.append(_paper_drag_label(paper.submission_id, paper.title))
        containers.append({"header": header, "items": cards})

    unassigned_header = "UNASSIGNED"
    header_to_session[unassigned_header] = ""
    containers.append(
        {
            "header": unassigned_header,
            "items": [_paper_drag_label(p.submission_id, p.title) for p in unassigned_papers],
        }
    )

    baseline = {
        block["header"]: [_sid_from_drag_label(item) for item in block["items"]]
        for block in containers
    }

    st.caption("Drag/drop board: move papers across sessions and UNASSIGNED. First 4 in each session are scheduled; extras become overflow.")
    raw_result = sortable_items(containers, direction="horizontal", multi_containers=True)

    parsed = _sortable_result_to_header_items(raw_result, [container["header"] for container in containers])
    if parsed is None:
        return False

    current = {
        header: [_sid_from_drag_label(item) for item in parsed.get(header, []) if _sid_from_drag_label(item)]
        for header in baseline.keys()
    }

    if current == baseline:
        return False

    updates: Dict[str, Dict[str, object]] = {}

    for header, session_code in header_to_session.items():
        sids = []
        seen = set()
        for sid in current.get(header, []):
            if sid and sid not in seen:
                seen.add(sid)
                sids.append(sid)

        if not session_code:
            for sid in sids:
                updates[sid] = {
                    "PlacementStatus": "unassigned",
                    "SessionCode": "",
                    "TalkIndex": "",
                    "OverflowOrder": "",
                }
            continue

        for idx, sid in enumerate(sids, start=1):
            if idx <= 4:
                updates[sid] = {
                    "PlacementStatus": "scheduled",
                    "SessionCode": session_code,
                    "TalkIndex": str(idx),
                    "OverflowOrder": "",
                }
            else:
                updates[sid] = {
                    "PlacementStatus": "overflow",
                    "SessionCode": session_code,
                    "TalkIndex": "",
                    "OverflowOrder": str(idx - 4),
                }

    if _apply_layout_updates(updates, "Applied drag/drop layout changes."):
        st.rerun()
    return True


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
    all_session_codes: List[str],
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
    if all_session_codes:
        default_idx = all_session_codes.index(session.session_code) if session.session_code in all_session_codes else 0
        target_session = st.selectbox(
            "Target Session",
            all_session_codes,
            index=default_idx,
            key=f"ins_move_session_{paper.submission_id}",
        )
        target_slot = st.selectbox(
            "Target Slot",
            [1, 2, 3, 4],
            index=max(0, min(3, talk_index - 1)),
            key=f"ins_move_slot_{paper.submission_id}",
        )
        if st.button("Move Paper", key=f"ins_move_btn_{paper.submission_id}", use_container_width=True):
            if _apply_layout_updates(
                {
                    paper.submission_id: {
                        "PlacementStatus": "scheduled",
                        "SessionCode": target_session,
                        "TalkIndex": str(target_slot),
                        "OverflowOrder": "",
                    }
                },
                f"Moved {paper.submission_id} to {target_session} slot {target_slot}.",
            ):
                st.rerun()

    st.caption("If the target slot/session is full, the move is kept as overflow and flagged in Quality.")
    if st.button("Drop To Unassigned", key=f"ins_drop_{paper.submission_id}", use_container_width=True):
        if _apply_layout_updates(
            {
                paper.submission_id: {
                    "PlacementStatus": "unassigned",
                    "SessionCode": "",
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
        key=f"ins_empty_pick_{session.session_code}_{talk_index}",
    )
    selected_paper = paper_map.get(_normalize_text(pick))
    if selected_paper is not None and _normalize_text(selected_paper.placement_status).lower() != "unassigned":
        st.info(f"Assigning this paper will move it from: {_paper_location_summary(selected_paper)}")

    if st.button(
        "Assign To This Slot",
        key=f"ins_empty_assign_{session.session_code}_{talk_index}",
        use_container_width=True,
    ):
        sid = _normalize_text(pick)
        if sid:
            if _apply_layout_updates(
                {
                    sid: {
                        "PlacementStatus": "scheduled",
                        "SessionCode": session.session_code,
                        "TalkIndex": str(talk_index),
                        "OverflowOrder": "",
                    }
                },
                f"Assigned {sid} to {session.session_code} slot {talk_index}.",
            ):
                st.rerun()


def _render_session_inspector(state, session: object, all_session_codes: List[str]) -> None:
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

    st.markdown("---")
    st.caption("Session Slots")
    for talk_idx in range(1, 5):
        paper = session.papers[talk_idx - 1]
        if paper is None:
            st.write(f"Slot {talk_idx}: [Empty slot]")
            if st.button(
                f"Open Empty Slot {talk_idx}",
                key=f"ins_open_empty_{session.session_code}_{talk_idx}",
                use_container_width=True,
            ):
                _set_programme_selection("slot", session.session_code, talk_idx)
                st.rerun()
            continue
        st.write(f"Slot {talk_idx}: {paper.submission_id} | {_clip_text(paper.full_name, 52)}")
        if st.button(
            f"Open Slot {talk_idx}",
            key=f"ins_open_slot_{session.session_code}_{talk_idx}",
            use_container_width=True,
        ):
            _set_programme_selection("slot", session.session_code, talk_idx)
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

            target_session = st.selectbox(
                "Target Session",
                all_session_codes,
                index=all_session_codes.index(session.session_code) if session.session_code in all_session_codes else 0,
                key=f"ins_ov_target_session_{paper.submission_id}_{session.session_code}_{overflow_pos}",
            )
            target_slot = st.selectbox(
                "Target Slot",
                [1, 2, 3, 4],
                index=0,
                key=f"ins_ov_target_slot_{paper.submission_id}_{session.session_code}_{overflow_pos}",
            )
            if st.button(
                "Move Overflow Paper",
                key=f"ins_ov_move_{paper.submission_id}_{session.session_code}_{overflow_pos}",
                use_container_width=True,
            ):
                if _apply_layout_updates(
                    {
                        paper.submission_id: {
                            "PlacementStatus": "scheduled",
                            "SessionCode": target_session,
                            "TalkIndex": str(target_slot),
                            "OverflowOrder": "",
                        }
                    },
                    f"Moved {paper.submission_id} to {target_session} slot {target_slot}.",
                ):
                    st.rerun()
            if st.button(
                "Drop Overflow To Unassigned",
                key=f"ins_ov_drop_{paper.submission_id}_{session.session_code}_{overflow_pos}",
                use_container_width=True,
            ):
                if _apply_layout_updates(
                    {
                        paper.submission_id: {
                            "PlacementStatus": "unassigned",
                            "SessionCode": "",
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
    if not isinstance(selection, dict) or not selection.get("session_code"):
        st.info("Nothing selected yet.")
        return

    session_map = {session.session_code: session for session in state.sessions}
    session = session_map.get(selection.get("session_code", ""))
    if session is None:
        st.warning("Selected item is no longer available. Pick another slot/session.")
        _clear_programme_selection()
        return

    all_session_codes = [s.session_code for s in sorted(state.sessions, key=_session_sort_key)]
    kind = _normalize_text(selection.get("kind", ""))
    if kind == "session":
        _render_session_inspector(state, session, all_session_codes)
        return

    talk_index = int(selection.get("talk_index", 0) or 0)
    if talk_index not in {1, 2, 3, 4}:
        st.warning("Invalid slot selection. Pick a slot again.")
        return

    paper = session.papers[talk_index - 1]
    if paper is None:
        _render_empty_slot_inspector(state, session, talk_index)
    else:
        _render_paper_slot_inspector(state, session, talk_index, paper, all_session_codes)


def _render_programme_tab(state) -> None:
    st.subheader("Programme")

    talks_df = pd.DataFrame(programme_talk_rows(state))
    if talks_df.empty:
        st.info("No programme data loaded.")
        return

    day_options = sorted(talks_df["Day"].unique().tolist())
    day_pick = st.selectbox("Day", day_options, key="programme_day")
    day_talks = talks_df[talks_df["Day"] == day_pick].copy()
    block_rows = _day_block_rows(day_talks)

    if not block_rows:
        st.info("No programme blocks available for this day.")
        return

    block_labels = ["All blocks"] + [row["Label"] for row in block_rows]
    c1, c2 = st.columns([2.8, 3.6])
    with c1:
        selected_block_label = st.selectbox(
            "Block (optional)",
            block_labels,
            key=f"programme_block_filter_{day_pick}",
        )
    with c2:
        column_width = st.slider("Column Width", min_value=220, max_value=560, value=360, step=10)

    selection = st.session_state.get("programme_selection", {})
    has_selection = isinstance(selection, dict) and bool(selection.get("session_code"))

    if selected_block_label == "All blocks":
        candidate_blocks = block_rows
    else:
        selected_block = next((row for row in block_rows if row["Label"] == selected_block_label), None)
        if selected_block is None:
            st.warning("Selected block not found.")
            return
        candidate_blocks = [selected_block]

    max_rooms = 1
    for block in candidate_blocks:
        room_count = len(
            _get_block_sessions(
                state,
                day_pick,
                block["BlockNum"],
                block["Time"],
                block["Block"],
            )
        )
        max_rooms = max(max_rooms, room_count)

    width_budget = 960 if has_selection else 1450
    rooms_per_row = max(1, min(max_rooms, width_budget // max(220, column_width)))
    st.caption(f"Layout density: {rooms_per_row} room card(s) per row.")

    def _render_grid_content() -> None:
        st.caption("Click a session card or slot block to open the inspector.")

        for block in candidate_blocks:
            block_sessions = _get_block_sessions(
                state,
                day_pick,
                block["BlockNum"],
                block["Time"],
                block["Block"],
            )
            _render_programme_block_grid(
                block_sessions,
                column_width_px=column_width,
                rooms_per_row=rooms_per_row,
            )

    if has_selection:
        left_col, right_col = st.columns([3.2, 1.2], gap="large")
        with left_col:
            _render_grid_content()
        with right_col:
            _render_programme_inspector(state)
    else:
        _render_grid_content()


def _render_top_actions(not_edited_count: int) -> None:
    state = st.session_state.wic_state
    v = state.validations

    if v.get("has_planning_issues", False):
        st.warning(
            "Planning issues exist (overflow/unassigned/collisions). You can still publish, but review the Quality tab first."
        )

    a1, a2, a3, a4 = st.columns([1.4, 1.1, 1.1, 1.1])

    if a1.button("Publish (Excel + PDF)", type="primary", use_container_width=True):
        try:
            if not_edited_count > 0:
                st.warning(f"Publishing with {not_edited_count} not-edited papers.")
            xlsx_path = export_publish_excel(st.session_state.wic_state)
            pdf_path = export_publish_pdf(st.session_state.wic_state)
            st.success(f"Publish Excel: {xlsx_path}")
            st.success(f"Publish PDF: {pdf_path}")
        except Exception as exc:
            st.error(f"Publish failed: {exc}")

    undo_disabled = st.session_state.last_change is None
    if a2.button("Undo Last Change", disabled=undo_disabled, use_container_width=True):
        if _undo_last_change():
            st.rerun()

    if a3.button("Reload From Disk", use_container_width=True):
        _refresh_state("Reloaded from disk.")
        st.rerun()

    if a4.button("Export Draft", use_container_width=True):
        try:
            path = export_draft_workbook(st.session_state.wic_state)
            st.success(f"Draft exported: {path}")
        except Exception as exc:
            st.error(f"Draft export failed: {exc}")

    st.caption("Session code format: `D{day}-B{block}-{room}`")


_init_session_state()
state = st.session_state.wic_state
edited_ids = _edited_submission_ids()
edited_count = len([p for p in state.papers if p.submission_id in edited_ids])
not_edited_count = len(state.papers) - edited_count

st.title("WIC 2026 Reclassification Studio")
st.caption("Programme-first mode: edits are auto-applied, auto-saved, and synced immediately across tabs.")

if st.session_state.flash_message:
    st.success(st.session_state.flash_message)
    st.session_state.flash_message = ""

_render_top_actions(not_edited_count)

_tabs = st.tabs(["Programme", "Paper List", "Session Names", "Quality"])

with _tabs[0]:
    _render_programme_tab(state)

with _tabs[1]:
    st.subheader("Paper List")
    papers_df = pd.DataFrame(papers_to_rows(state))

    f1, f2, f3, f4, f5, f6 = st.columns([2, 2, 2, 2, 2, 3])
    theme_filter = f1.selectbox("Theme", ["All"] + sorted(papers_df["PrimaryTheme"].dropna().unique().tolist()))
    subtheme_filter = f2.selectbox("Subtheme", ["All"] + sorted(papers_df["Subtheme"].dropna().unique().tolist()))
    day_filter = f3.selectbox("Day", ["All"] + sorted(papers_df["Day"].dropna().unique().tolist()))
    block_filter = f4.selectbox("Block", ["All"] + sorted(papers_df["Block"].dropna().unique().tolist()))
    room_filter = f5.selectbox("Room", ["All"] + sorted(papers_df["Room"].dropna().unique().tolist()))
    query = f6.text_input("Search title/presenter", "")

    show_not_edited_only = st.checkbox("Show not-edited papers only", value=False)

    filtered = papers_df.copy()
    if theme_filter != "All":
        filtered = filtered[filtered["PrimaryTheme"] == theme_filter]
    if subtheme_filter != "All":
        filtered = filtered[filtered["Subtheme"] == subtheme_filter]
    if day_filter != "All":
        filtered = filtered[filtered["Day"] == day_filter]
    if block_filter != "All":
        filtered = filtered[filtered["Block"] == block_filter]
    if room_filter != "All":
        filtered = filtered[filtered["Room"] == room_filter]
    if show_not_edited_only:
        filtered = filtered[~filtered["SubmissionID"].isin(edited_ids)]
    if query.strip():
        q = query.strip().lower()
        filtered = filtered[
            filtered["Title"].str.lower().str.contains(q, na=False)
            | filtered["FullName"].str.lower().str.contains(q, na=False)
            | filtered["SubmissionID"].str.lower().str.contains(q, na=False)
        ]

    edit_columns = [
        "SubmissionID",
        "FullName",
        "Title",
        "PrimaryTheme",
        "Subtheme",
        "OverrideNotes",
        "PlacementStatus",
        "SessionCode",
        "SessionTitle",
        "Day",
        "Block",
        "Room",
    ]

    edited = st.data_editor(
        filtered[edit_columns],
        key="paper_list_editor",
        use_container_width=True,
        num_rows="fixed",
        hide_index=True,
        column_config={
            "PrimaryTheme": st.column_config.SelectboxColumn(options=THEME_ORDER),
            "Subtheme": st.column_config.TextColumn(),
            "OverrideNotes": st.column_config.TextColumn(width="large"),
            "PlacementStatus": st.column_config.TextColumn(disabled=True),
            "SessionCode": st.column_config.TextColumn(disabled=True),
            "SessionTitle": st.column_config.TextColumn(disabled=True, width="large"),
            "Day": st.column_config.TextColumn(disabled=True),
            "Block": st.column_config.TextColumn(disabled=True),
            "Room": st.column_config.TextColumn(disabled=True),
        },
    )

    if _apply_classification_edits_if_changed(edited):
        st.rerun()

with _tabs[2]:
    st.subheader("Session Names")

    sessions_df = pd.DataFrame(sessions_to_rows(state))
    name_overrides = load_session_name_overrides(SESSION_NAME_OVERRIDES_FILE)
    sessions_df["SessionTitleOverride"] = sessions_df["SessionCode"].map(name_overrides).fillna("")

    editable_sessions = sessions_df[
        [
            "SessionCode",
            "Day",
            "Time",
            "Block",
            "Room",
            "PrimaryTheme",
            "Subtheme",
            "SessionTitle",
            "SessionTitleOverride",
            "OverflowCount",
        ]
    ]

    edited_sessions = st.data_editor(
        editable_sessions,
        key="session_name_editor",
        hide_index=True,
        use_container_width=True,
        column_config={
            "SessionCode": st.column_config.TextColumn(disabled=True),
            "Day": st.column_config.TextColumn(disabled=True),
            "Time": st.column_config.TextColumn(disabled=True),
            "Block": st.column_config.TextColumn(disabled=True),
            "Room": st.column_config.TextColumn(disabled=True),
            "PrimaryTheme": st.column_config.TextColumn(disabled=True),
            "Subtheme": st.column_config.TextColumn(disabled=True),
            "SessionTitle": st.column_config.TextColumn(disabled=True, width="large"),
            "SessionTitleOverride": st.column_config.TextColumn(width="large"),
            "OverflowCount": st.column_config.NumberColumn(disabled=True),
        },
    )

    if _apply_session_name_edits_if_changed(edited_sessions):
        st.rerun()

with _tabs[3]:
    _quality_panel(edited_count=edited_count, not_edited_count=not_edited_count)
