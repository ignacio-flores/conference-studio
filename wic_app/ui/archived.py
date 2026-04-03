from __future__ import annotations

import re
from typing import Callable, Dict, Iterable, List, Sequence

import streamlit as st

from reclassification_engine import DEFAULT_ARCHIVE_REASON_OPTIONS


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def parse_archive_reason_values(raw: object) -> List[str]:
    text = str(raw or "")
    parts = re.split(r"[,;\n]+", text)
    labels: List[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = _normalize_text(part)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        labels.append(cleaned)
    return labels


def resolve_archive_reason_options(
    catalog_reasons: Sequence[str],
    archive_overrides: Dict[str, Dict[str, str]],
) -> List[str]:
    options: List[str] = []
    seen: set[str] = set()
    for candidate in list(DEFAULT_ARCHIVE_REASON_OPTIONS) + list(catalog_reasons):
        cleaned = _normalize_text(candidate)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        options.append(cleaned)
    for row in list(archive_overrides.values()):
        cleaned = _normalize_text(row.get("ArchiveReason", "")) or "Other"
        if cleaned in seen:
            continue
        seen.add(cleaned)
        options.append(cleaned)
    return options


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


def filter_archived_papers(
    archived_papers: Iterable[object],
    archive_overrides: Dict[str, Dict[str, str]],
    *,
    query: str,
    reason_filter: str,
) -> List[object]:
    filtered: List[object] = []
    for paper in list(archived_papers or []):
        sid = _normalize_text(getattr(paper, "submission_id", ""))
        row = archive_overrides.get(sid, {})
        reason = _normalize_text(row.get("ArchiveReason", "")) or "Other"
        if reason_filter != "All" and reason != _normalize_text(reason_filter):
            continue

        if _normalize_text(query):
            q = _normalize_text(query).lower()
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
    return filtered


def filtered_archived_submission_ids(
    archived_papers: Iterable[object],
    archive_overrides: Dict[str, Dict[str, str]],
    *,
    query: str,
    reason_filter: str,
) -> List[str]:
    return [
        _normalize_text(getattr(paper, "submission_id", ""))
        for paper in filter_archived_papers(
            archived_papers,
            archive_overrides,
            query=query,
            reason_filter=reason_filter,
        )
        if _normalize_text(getattr(paper, "submission_id", ""))
    ]


def render_archived_tab(
    state,
    archive_overrides: Dict[str, Dict[str, str]],
    restore_archived_paper: Callable[[str], bool],
    archive_reason_options: Sequence[str],
    load_archive_reason_labels: Callable[[], List[str]],
    add_archive_reason_labels: Callable[[Iterable[str]], bool],
    bulk_update_archived_reason: Callable[[List[str], str], bool],
    mobile_mode: bool = False,
) -> None:
    st.subheader("Archived")

    with st.expander("Archive reason labels", expanded=False):
        current_labels = list(load_archive_reason_labels() or [])
        if current_labels:
            st.caption(f"Saved labels: {', '.join(current_labels)}")
        else:
            st.caption("No saved archive reason labels yet. Default suggestions still stay available.")
        new_labels_raw = st.text_area(
            "New archive reason labels",
            value="",
            height=80,
            key="archived_reason_labels_input",
        )
        if st.button("Add archive labels", key="archived_reason_labels_add", use_container_width=True):
            new_labels = parse_archive_reason_values(new_labels_raw)
            if not new_labels:
                st.info("Enter at least one archive reason label.")
            elif add_archive_reason_labels(new_labels):
                st.rerun()
            else:
                st.info("No new archive reason labels were added.")

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
    if mobile_mode:
        reason_filter = st.selectbox("Reason", ["All"] + list(archive_reason_options))
    else:
        reason_filter = reason_col.selectbox("Reason", ["All"] + list(archive_reason_options))

    filtered = filter_archived_papers(
        archived_papers,
        archive_overrides,
        query=query,
        reason_filter=reason_filter,
    )
    filtered_ids = filtered_archived_submission_ids(
        archived_papers,
        archive_overrides,
        query=query,
        reason_filter=reason_filter,
    )

    bulk_reason = st.selectbox(
        "New archive reason",
        list(archive_reason_options),
        key="archived_bulk_reason",
    )
    if st.button(
        f"Apply to {len(filtered_ids)} filtered archived paper(s)",
        key="archived_bulk_reason_apply",
        use_container_width=True,
        disabled=not filtered_ids,
    ):
        if bulk_update_archived_reason(filtered_ids, bulk_reason):
            st.rerun()
        st.info("No archived reason changes detected.")

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
