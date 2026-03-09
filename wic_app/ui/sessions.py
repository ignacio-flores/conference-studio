from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st


def render_session_names_tab(
    state,
    sessions_to_rows: Callable,
    load_session_name_overrides: Callable,
    session_name_overrides_file: Path,
    apply_session_name_edits_if_changed: Callable[[pd.DataFrame], bool],
) -> None:
    st.subheader("Session Names")

    sessions_df = pd.DataFrame(sessions_to_rows(state))
    name_overrides = load_session_name_overrides(session_name_overrides_file)
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

    if apply_session_name_edits_if_changed(edited_sessions):
        st.rerun()

