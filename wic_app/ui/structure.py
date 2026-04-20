from __future__ import annotations

import html
from typing import Callable, Dict, List, Optional, Sequence

import streamlit as st


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _clip_text(value: object, limit: int) -> str:
    clean = _normalize_text(value)
    if len(clean) <= limit:
        return clean
    if limit <= 3:
        return clean[:limit]
    return f"{clean[: limit - 3]}..."


def resolve_structure_title_lines(visible_room_columns: int) -> int:
    columns = max(0, int(visible_room_columns or 0))
    return 2 if columns <= 5 else 1


def structure_title_char_limit(visible_room_columns: int) -> int:
    return 84 if resolve_structure_title_lines(visible_room_columns) == 2 else 42


def build_block_filter_label(block_num: int, block_label: object, time_label: object) -> str:
    return f"B{int(block_num or 0)} | {_normalize_text(block_label)} | {_normalize_text(time_label)}"


def _status_value(session: object) -> str:
    status = _normalize_text(getattr(session, "status", "active")).lower()
    return status if status in {"active", "inactive"} else "active"


def _status_color(status: str) -> str:
    return "#2e7d32" if status == "active" else "#9e9e9e"


def _occupancy_color(used: int, capacity: int) -> str:
    if used > capacity:
        return "#c62828"
    if used == capacity:
        return "#2e7d32"
    return "#757575"


def _format_block_time_cell(row: Dict[str, object]) -> str:
    block_num = int(row.get("block_num", 0) or 0)
    block_label = html.escape(_normalize_text(row.get("block_label", "")) or "[No block]")
    time_label = html.escape(_normalize_text(row.get("time_label", "")) or "[No time]")
    return (
        "<div style='line-height:1.15;'>"
        f"<div><strong>B{block_num} | {block_label}</strong></div>"
        f"<div style='font-size:0.82rem;color:#5f6f86;margin-top:0.1rem;'>{time_label}</div>"
        "</div>"
    )


def _session_hover_help(session: object) -> str:
    session_code = _normalize_text(getattr(session, "session_code", "")) or "[No code]"
    session_title = _normalize_text(getattr(session, "session_title", "")) or "[No session title]"
    lines = [f"{session_code} | {session_title}"]

    capacity = max(1, int(getattr(session, "capacity", 1) or 1))
    papers = list(getattr(session, "papers", []) or [])
    for talk_idx in range(1, capacity + 1):
        lines.append("")
        paper = papers[talk_idx - 1] if talk_idx - 1 < len(papers) else None
        if paper is None:
            lines.append(f"- Slot {talk_idx}: [Empty slot]")
            continue
        title = _normalize_text(getattr(paper, "title", "")) or "[No title]"
        presenter = _normalize_text(getattr(paper, "full_name", "")) or "[No presenter]"
        lines.append(f'- Slot {talk_idx}: "{_clip_text(title, 92)}" - {_clip_text(presenter, 52)}')

    overflow_papers = list(getattr(session, "overflow_papers", []) or [])
    if overflow_papers:
        for idx, paper in enumerate(overflow_papers[:3], start=1):
            lines.append("")
            title = _normalize_text(getattr(paper, "title", "")) or "[No title]"
            presenter = _normalize_text(getattr(paper, "full_name", "")) or "[No presenter]"
            lines.append(f'- [!] (overflow #{idx}) "{_clip_text(title, 88)}" - {_clip_text(presenter, 48)}')
        if len(overflow_papers) > 3:
            lines.append("")
            lines.append(f"... {len(overflow_papers) - 3} more overflow paper(s)")

    return "\n".join(lines)


def structure_session_counts(session: object, unassigned_count: int = 0) -> Dict[str, int]:
    capacity = max(1, int(getattr(session, "capacity", 1) or 1))
    papers = list(getattr(session, "papers", []) or [])
    filled = sum(1 for paper in papers[:capacity] if paper is not None)
    overflow = len(list(getattr(session, "overflow_papers", []) or []))
    used = filled + overflow
    open_slots = max(0, capacity - filled)
    potential_fill = min(open_slots, max(0, int(unassigned_count or 0)))
    return {
        "filled": filled,
        "capacity": capacity,
        "overflow": overflow,
        "used": used,
        "open_slots": open_slots,
        "potential_fill": potential_fill,
    }


def build_session_selection(session: object) -> Dict[str, object]:
    return {
        "kind": "session",
        "session_id": _normalize_text(getattr(session, "session_id", "")),
        "day_label": _normalize_text(getattr(session, "day_label", "")),
        "block_num": int(getattr(session, "block_num", 0) or 0),
        "block_label": _normalize_text(getattr(session, "block_label", "")),
        "time_label": _normalize_text(getattr(session, "time", "")),
        "room": _normalize_text(getattr(session, "room", "")),
    }


def build_room_selection(
    day_label: str,
    room: str,
    block_num: int = 0,
    block_label: str = "",
    time_label: str = "",
) -> Dict[str, object]:
    return {
        "kind": "room",
        "session_id": "",
        "day_label": _normalize_text(day_label),
        "block_num": int(block_num or 0),
        "block_label": _normalize_text(block_label),
        "time_label": _normalize_text(time_label),
        "room": _normalize_text(room),
    }


def build_empty_slot_selection(
    day_label: str,
    block_num: int,
    block_label: str,
    time_label: str,
    room: str,
) -> Dict[str, object]:
    return {
        "kind": "empty_slot",
        "session_id": "",
        "day_label": _normalize_text(day_label),
        "block_num": int(block_num or 0),
        "block_label": _normalize_text(block_label),
        "time_label": _normalize_text(time_label),
        "room": _normalize_text(room),
    }


def build_new_room_selection(day_label: str) -> Dict[str, object]:
    return {
        "kind": "new_room",
        "session_id": "",
        "day_label": _normalize_text(day_label),
        "block_num": 0,
        "block_label": "",
        "time_label": "",
        "room": "",
    }


def _session_matches_query(session: object, query: str) -> bool:
    q = _normalize_text(query).lower()
    if not q:
        return True
    session_code = _normalize_text(getattr(session, "session_code", "")).lower()
    session_title = _normalize_text(getattr(session, "session_title", "")).lower()
    room = _normalize_text(getattr(session, "room", "")).lower()
    return q in session_code or q in session_title or q in room


def block_filter_labels_for_day(
    sessions: Sequence[object],
    day_label: str,
    status_filter: str,
    search_text: str,
    parse_start_minutes_fn: Callable[[str], int],
) -> List[str]:
    chosen_day = _normalize_text(day_label)
    normalized_status = _normalize_text(status_filter).lower()
    blocks: Dict[tuple, str] = {}
    for session in sessions:
        if chosen_day and _normalize_text(getattr(session, "day_label", "")) != chosen_day:
            continue
        if normalized_status in {"active", "inactive"} and _status_value(session) != normalized_status:
            continue
        if not _session_matches_query(session, search_text):
            continue
        block_num = int(getattr(session, "block_num", 0) or 0)
        block_label = _normalize_text(getattr(session, "block_label", ""))
        time_label = _normalize_text(getattr(session, "time", ""))
        key = (block_num, parse_start_minutes_fn(time_label), time_label, block_label)
        blocks[key] = build_block_filter_label(block_num, block_label, time_label)
    labels = [blocks[key] for key in sorted(blocks.keys())]
    return ["All blocks"] + labels


def group_sessions_for_structure_matrix(
    sessions: Sequence[object],
    day_label: str,
    status_filter: str,
    block_filter_label: str,
    search_text: str,
    parse_start_minutes_fn: Callable[[str], int],
    room_sort_key_fn: Callable[[str], object],
) -> Dict[str, object]:
    chosen_day = _normalize_text(day_label)
    normalized_status = _normalize_text(status_filter).lower()
    chosen_block_label = _normalize_text(block_filter_label)

    grouped: Dict[tuple, Dict[str, object]] = {}
    room_set: set[str] = set()
    day_filtered_sessions: List[object] = []

    for session in sessions:
        if chosen_day and _normalize_text(getattr(session, "day_label", "")) != chosen_day:
            continue
        if normalized_status in {"active", "inactive"} and _status_value(session) != normalized_status:
            continue
        if not _session_matches_query(session, search_text):
            continue
        day_filtered_sessions.append(session)
        room = _normalize_text(getattr(session, "room", ""))
        if room:
            room_set.add(room)

    for session in day_filtered_sessions:
        block_num = int(getattr(session, "block_num", 0) or 0)
        block_label = _normalize_text(getattr(session, "block_label", ""))
        time_label = _normalize_text(getattr(session, "time", ""))
        display_block_label = build_block_filter_label(block_num, block_label, time_label)
        if chosen_block_label and chosen_block_label != "All blocks" and display_block_label != chosen_block_label:
            continue

        block_key = (block_num, parse_start_minutes_fn(time_label), time_label, block_label)
        if block_key not in grouped:
            grouped[block_key] = {
                "block_num": block_num,
                "block_label": block_label,
                "time_label": time_label,
                "display_label": display_block_label,
                "sessions_by_room": {},
            }
        room = _normalize_text(getattr(session, "room", ""))
        grouped[block_key]["sessions_by_room"][room] = session

    rooms = sorted(room_set, key=room_sort_key_fn)
    rows: List[Dict[str, object]] = [grouped[key] for key in sorted(grouped.keys())]
    return {"rooms": rooms, "rows": rows}


def collect_visible_sessions(matrix: Dict[str, object]) -> List[object]:
    visible: List[object] = []
    rows = matrix.get("rows", []) if isinstance(matrix, dict) else []
    for block in rows:
        sessions_by_room = block.get("sessions_by_room", {})
        if not isinstance(sessions_by_room, dict):
            continue
        for session in sessions_by_room.values():
            if session is not None:
                visible.append(session)
    return visible


def _render_structure_matrix_mobile(
    *,
    rows: List[Dict[str, object]],
    rooms: List[str],
    selection: Dict[str, object],
    day_label: str,
    on_select_session: Callable[[object], None],
    on_select_room: Callable[[str], None],
    on_select_empty_slot: Callable[[Dict[str, object], str], None],
    on_select_new_room: Callable[[], None],
) -> None:
    selected_kind = _normalize_text(selection.get("kind", "") if isinstance(selection, dict) else "").lower()
    selected_session_id = _normalize_text(selection.get("session_id", "") if isinstance(selection, dict) else "")
    selected_room = _normalize_text(selection.get("room", "") if isinstance(selection, dict) else "")
    selected_day = _normalize_text(selection.get("day_label", "") if isinstance(selection, dict) else "")
    selected_block_num = int(selection.get("block_num", 0) or 0) if isinstance(selection, dict) else 0
    selected_time_label = _normalize_text(selection.get("time_label", "") if isinstance(selection, dict) else "")
    title_limit = 88

    st.caption("Tap room/session cards to open the structure inspector.")
    if st.button(
        "Add room",
        key=f"struct_room_new_mobile_{day_label}",
        type="primary" if selected_kind == "new_room" and selected_day == day_label else "secondary",
        use_container_width=True,
        help="Add a new room column for this day.",
    ):
        on_select_new_room()
        st.rerun()

    for row in rows:
        with st.container(border=True):
            st.markdown(_format_block_time_cell(row), unsafe_allow_html=True)
            for room in rooms:
                session = row["sessions_by_room"].get(room)
                room_is_selected = selected_kind == "room" and selected_day == day_label and selected_room == room
                if st.button(
                    f"Room: {room}",
                    key=(
                        f"struct_room_mobile_{day_label}_{int(row['block_num'])}_"
                        f"{_normalize_text(row['time_label'])}_{room}"
                    ),
                    type="primary" if room_is_selected else "secondary",
                    use_container_width=True,
                ):
                    on_select_room(room)
                    st.rerun()

                if session is None:
                    empty_slot_selected = (
                        selected_kind == "empty_slot"
                        and selected_day == day_label
                        and selected_room == room
                        and selected_block_num == int(row["block_num"])
                        and selected_time_label == _normalize_text(row["time_label"])
                    )
                    if st.button(
                        "[Empty slot]",
                        key=(
                            f"struct_empty_mobile_{day_label}_{int(row['block_num'])}_"
                            f"{_normalize_text(row['time_label'])}_{room}"
                        ),
                        type="primary" if empty_slot_selected else "secondary",
                        use_container_width=True,
                        help="Create a session in this empty room/block slot.",
                    ):
                        on_select_empty_slot(row, room)
                        st.rerun()
                    continue

                with st.container(border=True):
                    status_label = _status_value(session)
                    status_color = _status_color(status_label)
                    st.markdown(
                        (
                            "<div style='height:6px;border-radius:6px;"
                            f"background:{status_color};margin-bottom:0.35rem;'></div>"
                        ),
                        unsafe_allow_html=True,
                    )
                    session_is_selected = (
                        selected_kind == "session"
                        and selected_session_id == _normalize_text(getattr(session, "session_id", ""))
                    )
                    session_title = _normalize_text(getattr(session, "session_title", "")) or "[No session title]"
                    if st.button(
                        _clip_text(session_title, title_limit),
                        key=f"struct_session_mobile_{_normalize_text(getattr(session, 'session_id', ''))}",
                        type="primary" if session_is_selected else "secondary",
                        use_container_width=True,
                        help=_session_hover_help(session),
                    ):
                        on_select_session(session)
                        st.rerun()
                    counts = structure_session_counts(session)
                    used = counts["used"]
                    capacity = counts["capacity"]
                    occ_color = _occupancy_color(used, capacity)
                    st.markdown(
                        f"<div style='font-size:0.88rem;font-weight:700;color:{occ_color};'>{used}/{capacity}</div>",
                        unsafe_allow_html=True,
                    )


def render_structure_matrix(
    matrix: Dict[str, object],
    selection: Dict[str, object],
    day_label: str,
    on_select_session: Callable[[object], None],
    on_select_room: Callable[[str], None],
    on_select_empty_slot: Callable[[Dict[str, object], str], None],
    on_select_new_room: Callable[[], None],
    mobile_mode: bool = False,
) -> None:
    rows = matrix.get("rows", []) if isinstance(matrix, dict) else []
    rooms = matrix.get("rooms", []) if isinstance(matrix, dict) else []
    if not rows:
        st.info("No sessions found for the current filters.")
        return

    if mobile_mode:
        _render_structure_matrix_mobile(
            rows=rows,
            rooms=rooms,
            selection=selection,
            day_label=day_label,
            on_select_session=on_select_session,
            on_select_room=on_select_room,
            on_select_empty_slot=on_select_empty_slot,
            on_select_new_room=on_select_new_room,
        )
        return

    st.caption("Click a room header or session card to open the structure inspector.")
    selected_kind = _normalize_text(selection.get("kind", "") if isinstance(selection, dict) else "").lower()
    selected_session_id = _normalize_text(selection.get("session_id", "") if isinstance(selection, dict) else "")
    selected_room = _normalize_text(selection.get("room", "") if isinstance(selection, dict) else "")
    selected_day = _normalize_text(selection.get("day_label", "") if isinstance(selection, dict) else "")
    selected_block_num = int(selection.get("block_num", 0) or 0) if isinstance(selection, dict) else 0
    selected_time_label = _normalize_text(selection.get("time_label", "") if isinstance(selection, dict) else "")
    title_limit = structure_title_char_limit(len(rooms))

    header_cols = st.columns([1.8] + [1.0] * len(rooms) + [0.7], gap="small")
    header_cols[0].caption("Block / Time")
    for idx, room in enumerate(rooms, start=1):
        with header_cols[idx]:
            room_is_selected = selected_kind == "room" and selected_day == day_label and selected_room == room
            if st.button(
                room,
                key=f"struct_room_header_{day_label}_{room}",
                type="primary" if room_is_selected else "secondary",
                use_container_width=True,
            ):
                on_select_room(room)
                st.rerun()
    with header_cols[-1]:
        new_room_selected = selected_kind == "new_room" and selected_day == day_label
        if st.button(
            "Add room",
            key=f"struct_room_new_{day_label}",
            type="primary" if new_room_selected else "secondary",
            use_container_width=True,
            help="Add a new room column for this day.",
        ):
            on_select_new_room()
            st.rerun()

    for row in rows:
        cols = st.columns([1.8] + [1.0] * len(rooms) + [0.7], gap="small")
        cols[0].markdown(_format_block_time_cell(row), unsafe_allow_html=True)

        for idx, room in enumerate(rooms, start=1):
            session = row["sessions_by_room"].get(room)
            with cols[idx]:
                if session is None:
                    empty_slot_selected = (
                        selected_kind == "empty_slot"
                        and selected_day == day_label
                        and selected_room == room
                        and selected_block_num == int(row["block_num"])
                        and selected_time_label == _normalize_text(row["time_label"])
                    )
                    if empty_slot_selected:
                        st.markdown(
                            "<div style='height:6px;border-radius:6px;background:#1e88e5;margin-bottom:0.35rem;'></div>",
                            unsafe_allow_html=True,
                        )
                    if st.button(
                        "+",
                        key=(
                            f"struct_empty_{day_label}_{int(row['block_num'])}_"
                            f"{_normalize_text(row['time_label'])}_{room}"
                        ),
                        type="primary" if empty_slot_selected else "secondary",
                        use_container_width=True,
                        help="Create a session in this empty room/block slot.",
                    ):
                        on_select_empty_slot(row, room)
                        st.rerun()
                    continue

                with st.container(border=True):
                    status_label = _status_value(session)
                    status_color = _status_color(status_label)
                    st.markdown(
                        (
                            "<div style='height:6px;border-radius:6px;"
                            f"background:{status_color};margin-bottom:0.35rem;'></div>"
                        ),
                        unsafe_allow_html=True,
                    )

                    session_is_selected = (
                        selected_kind == "session"
                        and selected_session_id == _normalize_text(getattr(session, "session_id", ""))
                    )
                    session_title = _normalize_text(getattr(session, "session_title", "")) or "[No session title]"
                    session_button_label = _clip_text(session_title, title_limit)
                    if st.button(
                        session_button_label,
                        key=f"struct_session_{_normalize_text(getattr(session, 'session_id', ''))}",
                        type="primary" if session_is_selected else "secondary",
                        use_container_width=True,
                        help=_session_hover_help(session),
                    ):
                        on_select_session(session)
                        st.rerun()

                    counts = structure_session_counts(session)
                    used = counts["used"]
                    capacity = counts["capacity"]
                    occ_color = _occupancy_color(used, capacity)
                    st.markdown(
                        f"<div style='font-size:0.88rem;font-weight:700;color:{occ_color};'>{used}/{capacity}</div>",
                        unsafe_allow_html=True,
                    )
                    if session_is_selected:
                        st.markdown(
                            "<div style='height:4px;border-radius:6px;background:#1e88e5;margin-top:0.2rem;'></div>",
                            unsafe_allow_html=True,
                        )
        cols[-1].caption("")


def render_structure_inspector(
    state,
    selection: Dict[str, object],
    find_session_by_id: Callable[[str], Optional[object]],
    render_session_panel: Callable[[object], None],
    render_room_panel: Callable[[Dict[str, object]], None],
    render_empty_slot_panel: Callable[[Dict[str, object]], None],
    render_new_room_panel: Callable[[Dict[str, object]], None],
    clear_selection: Callable[[], None],
) -> None:
    _, head2 = st.columns([4, 1])
    if head2.button("✕", key="close_structure_inspector_btn", help="Close inspector", use_container_width=True):
        clear_selection()
        st.rerun()

    kind = _normalize_text(selection.get("kind", "") if isinstance(selection, dict) else "").lower()
    if kind == "session":
        session_id = _normalize_text(selection.get("session_id", ""))
        session = find_session_by_id(session_id)
        if session is None:
            st.warning("Selected session is no longer available.")
            return
        render_session_panel(session)
        return

    if kind == "room":
        render_room_panel(selection)
        return

    if kind == "empty_slot":
        render_empty_slot_panel(selection)
        return

    if kind == "new_room":
        render_new_room_panel(selection)
        return

    st.info("Nothing selected yet.")
