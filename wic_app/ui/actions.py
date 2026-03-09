from __future__ import annotations

from typing import Callable

import streamlit as st


def render_top_actions(
    state,
    not_edited_count: int,
    can_undo: bool,
    undo_last_change: Callable[[], bool],
    refresh_state: Callable[[str], None],
    export_publish_excel: Callable,
    export_publish_pdf: Callable,
    export_draft_workbook: Callable,
) -> None:
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
            xlsx_path = export_publish_excel(state)
            pdf_path = export_publish_pdf(state)
            st.success(f"Publish Excel: {xlsx_path}")
            st.success(f"Publish PDF: {pdf_path}")
        except Exception as exc:
            st.error(f"Publish failed: {exc}")

    if a2.button("Undo Last Change", disabled=not can_undo, use_container_width=True):
        if undo_last_change():
            st.rerun()

    if a3.button("Reload From Disk", use_container_width=True):
        refresh_state("Reloaded from disk.")
        st.rerun()

    if a4.button("Export Draft", use_container_width=True):
        try:
            path = export_draft_workbook(state)
            st.success(f"Draft exported: {path}")
        except Exception as exc:
            st.error(f"Draft export failed: {exc}")

    st.caption("Session code format: `D{day}-B{block}-{room}`")

