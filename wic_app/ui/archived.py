from __future__ import annotations

from typing import Callable, Dict, List

import streamlit as st


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _sort_archived_key(paper: object, archive_row: Dict[str, str]) -> tuple:
    archived_at = _normalize_text(archive_row.get("ArchivedAt", ""))
    return (
        archived_at,
        _normalize_text(getattr(paper, "submission_id", "")),
    )


def _previous_placement_label(archive_row: Dict[str, str], sessions_by_id: Dict[str, object]) -> str:
    status = _normalize_text(archive_row.get("PreviousPlacementStatus", "")).lower()
    session_id = _normalize_text(archive_row.get("PreviousSessionId", ""))
    talk_index = _normalize_text(archive_row.get("PreviousTalkIndex", ""))
    overflow_order = _normalize_text(archive_row.get("PreviousOverflowOrder", ""))

    if status not in {"scheduled", "unassigned", "overflow"}:
        status = "unassigned"
    if status == "unassigned":
        return "Unassigned"

    session = sessions_by_id.get(session_id)
    session_code = _normalize_text(getattr(session, "session_code", "")) if session is not None else session_id
    if status == "scheduled":
        if session_code and talk_index:
            return f"Scheduled in {session_code} slot {talk_index}"
        if session_code:
            return f"Scheduled in {session_code}"
        return "Scheduled"
    if session_code and overflow_order:
        return f"Overflow in {session_code} (#{overflow_order})"
    if session_code:
        return f"Overflow in {session_code}"
    return "Overflow"


def render_archived_tab(
    state,
    archive_overrides: Dict[str, Dict[str, str]],
    restore_archived_paper: Callable[[str], bool],
    mobile_mode: bool = False,
) -> None:
    st.subheader("Archived")
    archived_papers = list(getattr(state, "archived_papers", []) or [])
    if not archived_papers:
        st.info("No archived papers.")
        return

    sessions_by_id = {
        _normalize_text(getattr(session, "session_id", "")): session
        for session in list(getattr(state, "all_sessions", []) or [])
    }

    if mobile_mode:
        query = st.text_input("Search title/presenter/submission ID", "")
    else:
        query_col, reason_col = st.columns([3.2, 1.4])
        query = query_col.text_input("Search title/presenter/submission ID", "")
    reason_options = sorted(
        {
            _normalize_text(archive_overrides.get(_normalize_text(getattr(paper, "submission_id", "")), {}).get("ArchiveReason", "Other"))
            or "Other"
            for paper in archived_papers
        }
    )
    if mobile_mode:
        reason_filter = st.selectbox("Reason", ["All"] + reason_options)
    else:
        reason_filter = reason_col.selectbox("Reason", ["All"] + reason_options)

    filtered: List[object] = []
    for paper in archived_papers:
        sid = _normalize_text(getattr(paper, "submission_id", ""))
        row = archive_overrides.get(sid, {})
        reason = _normalize_text(row.get("ArchiveReason", "")) or "Other"
        if reason_filter != "All" and reason != reason_filter:
            continue

        if query.strip():
            q = query.strip().lower()
            haystack = " ".join(
                [
                    _normalize_text(getattr(paper, "submission_id", "")),
                    _normalize_text(getattr(paper, "title", "")),
                    _normalize_text(getattr(paper, "full_name", "")),
                ]
            ).lower()
            if q not in haystack:
                continue

        filtered.append(paper)

    if not filtered:
        st.info("No archived papers match the current filters.")
        return

    filtered = sorted(
        filtered,
        key=lambda paper: _sort_archived_key(
            paper,
            archive_overrides.get(_normalize_text(getattr(paper, "submission_id", "")), {}),
        ),
        reverse=True,
    )
    st.caption(f"Showing {len(filtered)} archived paper(s).")

    for paper in filtered:
        sid = _normalize_text(getattr(paper, "submission_id", ""))
        row = archive_overrides.get(sid, {})
        reason = _normalize_text(row.get("ArchiveReason", "")) or "Other"
        note = _normalize_text(row.get("ArchiveNote", ""))
        archived_at = _normalize_text(row.get("ArchivedAt", ""))
        previous_placement = _previous_placement_label(row, sessions_by_id)

        with st.container(border=True):
            if mobile_mode:
                st.markdown(f"**{_normalize_text(getattr(paper, 'title', '')) or '[No title]'}**")
                st.caption(
                    f"{_normalize_text(getattr(paper, 'full_name', '')) or '[No presenter]'} | {sid}"
                )
                st.caption(f"Reason: {reason}")
                st.caption(f"Archived at: {archived_at or '[unknown]'}")
                st.caption(f"Previous placement: {previous_placement}")
                if note:
                    st.caption(f"Note: {note}")
                if st.button("Restore", key=f"archived_restore_{sid}", use_container_width=True):
                    if restore_archived_paper(sid):
                        st.rerun()
            else:
                row_cols = st.columns([3.8, 2.4, 1.2], gap="small")
                row_cols[0].markdown(f"**{_normalize_text(getattr(paper, 'title', '')) or '[No title]'}**")
                row_cols[0].caption(
                    f"{_normalize_text(getattr(paper, 'full_name', '')) or '[No presenter]'} | {sid}"
                )
                row_cols[1].caption(f"Reason: {reason}")
                row_cols[1].caption(f"Archived at: {archived_at or '[unknown]'}")
                row_cols[1].caption(f"Previous placement: {previous_placement}")
                if note:
                    row_cols[1].caption(f"Note: {note}")
                if row_cols[2].button("Restore", key=f"archived_restore_{sid}", use_container_width=True):
                    if restore_archived_paper(sid):
                        st.rerun()
