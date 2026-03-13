from __future__ import annotations

from typing import Callable, List

import pandas as pd
import streamlit as st

from ui.inspector_layout import render_inspector_marker

PROGRAMME_COLUMN_OPTIONS = ["Auto", "1", "2", "3", "4", "5", "6"]


def resolve_programme_layout_density(
    max_rooms: int,
    has_selection: bool,
    columns_choice: str,
) -> tuple[int, int]:
    safe_max_rooms = max(1, int(max_rooms or 1))
    width_budget = 960 if has_selection else 1450
    choice = str(columns_choice or "Auto")

    if choice == "Auto":
        target = max(1, width_budget // 320)
        rooms_per_row = min(safe_max_rooms, target)
    else:
        try:
            rooms_per_row = max(1, int(choice))
        except Exception:
            rooms_per_row = safe_max_rooms
        rooms_per_row = min(safe_max_rooms, rooms_per_row)

    column_width = max(220, min(560, width_budget // max(1, rooms_per_row)))
    return rooms_per_row, column_width


def render_programme_tab(
    state,
    programme_talk_rows: Callable,
    day_block_rows: Callable[[pd.DataFrame], List[dict]],
    get_block_sessions: Callable,
    render_programme_block_grid: Callable,
    render_programme_inspector: Callable,
    mobile_mode: bool = False,
    open_mobile_inspector_dialog: Callable[[], None] | None = None,
) -> None:
    st.subheader("Programme")

    talks_df = pd.DataFrame(programme_talk_rows(state))
    if talks_df.empty:
        st.info("No programme data loaded.")
        return

    day_options = sorted(talks_df["Day"].unique().tolist())
    day_pick = st.selectbox("Day", day_options, key="programme_day")
    day_talks = talks_df[talks_df["Day"] == day_pick].copy()
    block_rows = day_block_rows(day_talks)

    if not block_rows:
        st.info("No programme blocks available for this day.")
        return

    block_labels = ["All blocks"] + [row["Label"] for row in block_rows]
    if mobile_mode:
        with st.expander("Programme filters", expanded=True):
            selected_block_label = st.selectbox(
                "Block (optional)",
                block_labels,
                key=f"programme_block_filter_{day_pick}",
            )
            compare_mode = st.toggle(
                "Compare multiple rooms",
                value=False,
                key="programme_mobile_compare",
                help="Off = stacked one-room cards. On = multi-room rows.",
            )
            columns_choice = st.selectbox(
                "Columns per row",
                PROGRAMME_COLUMN_OPTIONS,
                key="programme_columns_per_row",
                disabled=not compare_mode,
            )
    else:
        c1, c2 = st.columns([2.8, 3.6])
        with c1:
            selected_block_label = st.selectbox(
                "Block (optional)",
                block_labels,
                key=f"programme_block_filter_{day_pick}",
            )
        with c2:
            columns_choice = st.selectbox(
                "Columns per row",
                PROGRAMME_COLUMN_OPTIONS,
                key="programme_columns_per_row",
            )
        compare_mode = True

    selection = st.session_state.get("programme_selection", {})
    has_selection = isinstance(selection, dict) and bool(selection.get("session_id"))

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
            get_block_sessions(
                state,
                day_pick,
                block["BlockNum"],
                block["Time"],
                block["Block"],
            )
        )
        max_rooms = max(max_rooms, room_count)

    room_filter_options: List[str] = []
    for block in candidate_blocks:
        block_sessions = get_block_sessions(
            state,
            day_pick,
            block["BlockNum"],
            block["Time"],
            block["Block"],
        )
        room_filter_options.extend([str(getattr(session, "room", "")).strip() for session in block_sessions])
    room_filter_options = sorted({room for room in room_filter_options if room})

    selected_rooms = room_filter_options
    if mobile_mode and room_filter_options:
        selected_rooms = st.multiselect(
            "Room filter (optional)",
            options=room_filter_options,
            default=room_filter_options,
            key=f"programme_mobile_room_filter_{day_pick}",
            help="Unselect rooms to simplify the mobile grid.",
        )
        if not selected_rooms:
            st.info("Showing all rooms because no room is selected.")
            selected_rooms = room_filter_options

    if mobile_mode and not compare_mode:
        rooms_per_row = 1
        column_width = 360
    else:
        rooms_per_row, column_width = resolve_programme_layout_density(
            max_rooms=max_rooms,
            has_selection=has_selection,
            columns_choice=columns_choice,
        )
        if mobile_mode:
            rooms_per_row = min(2, rooms_per_row)

    def _render_grid_content() -> None:
        st.caption("Click a session card or slot block to open the inspector.")

        for block in candidate_blocks:
            block_sessions = get_block_sessions(
                state,
                day_pick,
                block["BlockNum"],
                block["Time"],
                block["Block"],
            )
            if selected_rooms:
                selected_room_set = set(selected_rooms)
                block_sessions = [
                    session for session in block_sessions if str(getattr(session, "room", "")).strip() in selected_room_set
                ]
            render_programme_block_grid(
                block_sessions,
                column_width_px=column_width,
                rooms_per_row=rooms_per_row,
            )

    if has_selection and not mobile_mode:
        left_col, right_col = st.columns([3.2, 1.2], gap="large")
        with left_col:
            _render_grid_content()
        with right_col:
            render_inspector_marker("programme")
            render_programme_inspector(state)
    else:
        _render_grid_content()
        if has_selection and mobile_mode:
            st.caption("Selection active. Inspector opens in a dialog on mobile.")
            if callable(open_mobile_inspector_dialog):
                open_mobile_inspector_dialog()
