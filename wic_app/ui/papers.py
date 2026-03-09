from __future__ import annotations

from typing import Callable, Iterable, List

import pandas as pd
import streamlit as st


def render_paper_list_tab(
    state,
    edited_ids: Iterable[str],
    theme_order: List[str],
    papers_to_rows: Callable,
    apply_classification_edits_if_changed: Callable[[pd.DataFrame], bool],
) -> None:
    st.subheader("Paper List")
    edited_ids_set = set(edited_ids)
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
        filtered = filtered[~filtered["SubmissionID"].isin(edited_ids_set)]
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
            "PrimaryTheme": st.column_config.SelectboxColumn(options=theme_order),
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

    if apply_classification_edits_if_changed(edited):
        st.rerun()

