from __future__ import annotations

from typing import Callable, List

import pandas as pd
import streamlit as st

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

    rooms_per_row, column_width = resolve_programme_layout_density(
        max_rooms=max_rooms,
        has_selection=has_selection,
        columns_choice=columns_choice,
    )

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
            render_programme_block_grid(
                block_sessions,
                column_width_px=column_width,
                rooms_per_row=rooms_per_row,
            )

    if has_selection:
        left_col, right_col = st.columns([3.2, 1.2], gap="large")
        with left_col:
            _render_grid_content()
        with right_col:
            render_programme_inspector(state)
    else:
        _render_grid_content()
