from __future__ import annotations

from typing import Callable

import streamlit as st


def render_top_actions(
    state,
    not_edited_count: int,
    undo_count: int,
    undo_last_change: Callable[[], bool],
    refresh_state: Callable[[str], None],
    export_publish_excel: Callable,
    export_publish_pdf: Callable,
    export_publish_docx: Callable,
    publish_public_bundle: Callable,
    preview_public_bundle: Callable,
    export_draft_workbook: Callable | None = None,
) -> None:
    v = state.validations
    issues_suffix = " ⚠" if v.get("has_planning_issues", False) else ""
    menu_label = f"☰ Actions ({max(0, int(undo_count))} undo){issues_suffix}"

    popover = getattr(st, "popover", None)
    if callable(popover):
        container = popover(menu_label)
    else:
        container = st.expander(menu_label, expanded=False)

    with container:
        if v.get("has_planning_issues", False):
            st.warning(
                "Planning issues exist (overflow/unassigned/collisions). You can still publish, but review Checks."
            )

        if st.button("Publish (Excel + PDF + Word)", type="primary", use_container_width=True):
            try:
                if not_edited_count > 0:
                    st.warning(f"Publishing with {not_edited_count} not-edited papers.")
                xlsx_path = export_publish_excel(state)
                docx_path = export_publish_docx(state)
                pdf_path = export_publish_pdf(state)
                st.success(f"Publish Excel: {xlsx_path}")
                st.success(f"Publish PDF: {pdf_path}")
                st.success(f"Publish Word: {docx_path}")
            except Exception as exc:
                st.error(f"Publish failed: {exc}")

        if st.button("Prepare Public Bundle", use_container_width=True):
            try:
                bundle_path = publish_public_bundle(state)
                st.success(f"Public bundle ready: {bundle_path}")
            except Exception as exc:
                st.error(f"Public bundle failed: {exc}")

        if st.button("Preview Public Bundle", use_container_width=True):
            try:
                preview_details = preview_public_bundle(state)
                st.session_state.public_bundle_preview_url = preview_details["url"]
                st.session_state.public_bundle_preview_started = bool(preview_details.get("started", False))
            except Exception as exc:
                st.error(f"Public preview failed: {exc}")

        preview_url = str(st.session_state.get("public_bundle_preview_url", "") or "").strip()
        if preview_url:
            if bool(st.session_state.get("public_bundle_preview_started", False)):
                st.success(f"Public preview started: {preview_url}")
            else:
                st.info(f"Public preview already running: {preview_url}")
            link_button = getattr(st, "link_button", None)
            if callable(link_button):
                link_button("Open Public Preview", preview_url, use_container_width=True)
            else:
                st.markdown(f"[Open Public Preview]({preview_url})")

        if st.button(
            f"Undo ({max(0, int(undo_count))} remaining)",
            disabled=undo_count <= 0,
            use_container_width=True,
        ):
            if undo_last_change():
                st.rerun()

        if st.button("Reload From Disk", use_container_width=True):
            refresh_state("Reloaded from disk.")
            st.rerun()

        st.caption("Session code format: `D{day}-B{block}-{room}`")
