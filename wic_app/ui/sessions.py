from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def render_session_names_tab(
    state,
    sessions_to_rows: Callable,
    load_session_name_overrides: Callable,
    session_name_overrides_file: Path,
    apply_session_name_edits_if_changed: Callable[[pd.DataFrame], bool],
) -> None:
    st.subheader("Session Names")

    sessions_df = pd.DataFrame(sessions_to_rows(state))
    if sessions_df.empty:
        st.info("No sessions available.")
        return

    name_overrides = load_session_name_overrides(session_name_overrides_file)
    sessions_df["CustomTitle"] = sessions_df["SessionCode"].map(name_overrides).fillna("")
    sessions_df["AutoTitle"] = sessions_df["AutoTitle"] if "AutoTitle" in sessions_df.columns else sessions_df["SessionTitle"]
    sessions_df["HasOverride"] = sessions_df["CustomTitle"].astype(str).str.strip() != ""

    f1, f2, f3 = st.columns([2, 2, 3])
    day_options = ["All"] + sorted([value for value in sessions_df["Day"].dropna().unique().tolist() if str(value).strip()])
    block_options = ["All"] + sorted([value for value in sessions_df["Block"].dropna().unique().tolist() if str(value).strip()])
    day_filter = f1.selectbox("Day", day_options, key="session_names_day_filter")
    block_filter = f2.selectbox("Block", block_options, key="session_names_block_filter")
    search_text = f3.text_input("Search code/room/title", "", key="session_names_search")
    overrides_only = st.checkbox("Show only sessions with custom titles", value=False, key="session_names_overrides_only")

    filtered = sessions_df.copy()
    if day_filter != "All":
        filtered = filtered[filtered["Day"] == day_filter]
    if block_filter != "All":
        filtered = filtered[filtered["Block"] == block_filter]
    if overrides_only:
        filtered = filtered[filtered["HasOverride"]]
    if search_text.strip():
        q = search_text.strip().lower()
        filtered = filtered[
            filtered["SessionCode"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["Room"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["AutoTitle"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["CustomTitle"].astype(str).str.lower().str.contains(q, na=False)
        ]

    editable_sessions = filtered[
        [
            "SessionCode",
            "Day",
            "Block",
            "Time",
            "Room",
            "Capacity",
            "AutoTitle",
            "CustomTitle",
        ]
    ].copy()

    edited_sessions = st.data_editor(
        editable_sessions,
        key="session_name_editor",
        hide_index=True,
        use_container_width=True,
        column_config={
            "SessionCode": st.column_config.TextColumn(disabled=True),
            "Day": st.column_config.TextColumn(disabled=True),
            "Block": st.column_config.TextColumn(disabled=True),
            "Time": st.column_config.TextColumn(disabled=True),
            "Room": st.column_config.TextColumn(disabled=True),
            "Capacity": st.column_config.NumberColumn(disabled=True, format="%d"),
            "AutoTitle": st.column_config.TextColumn(disabled=True, width="large"),
            "CustomTitle": st.column_config.TextColumn(width="large"),
        },
    )

    actions_left, actions_right = st.columns([1, 1])
    if actions_left.button("Save Title Changes", use_container_width=True, key="session_names_save_btn"):
        if apply_session_name_edits_if_changed(edited_sessions):
            st.rerun()
        st.info("No title changes detected.")

    if actions_right.button("Clear Visible Overrides", use_container_width=True, key="session_names_clear_visible_btn"):
        if edited_sessions.empty:
            st.info("No sessions in the current filter.")
        else:
            cleared = edited_sessions.copy()
            cleared["CustomTitle"] = ""
            if apply_session_name_edits_if_changed(cleared):
                st.rerun()
            st.info("No visible overrides to clear.")

    override_count = int((sessions_df["CustomTitle"].astype(str).str.strip() != "").sum())
    st.caption(f"Custom title overrides: {override_count}")
