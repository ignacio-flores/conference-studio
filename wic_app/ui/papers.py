from __future__ import annotations

import html
import re
from typing import Callable, Dict, Iterable, List, Tuple

import pandas as pd
import streamlit as st

HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = HTML_TAG_RE.sub("", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def _clip_text(value: object, limit: int) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[: limit - 3]}..."


def presenter_with_abstract_html(full_name: str, abstract: str) -> str:
    name = html.escape(_clean_text(full_name) or "[No presenter]")
    preview = html.escape(_clean_text(abstract) or "No abstract provided")
    return f"<span title='{preview}'>{name}</span>"


def title_link_html(title: str, link_to_pdf: str) -> str:
    safe_title = html.escape(_clean_text(title) or "[No title]")
    link = _normalize_text(link_to_pdf)
    if link.startswith("http"):
        safe_link = html.escape(link, quote=True)
        return (
            f"<a href='{safe_link}' target='_blank' rel='noopener noreferrer' "
            f"title='Open paper in a new tab'>{safe_title}</a>"
        )
    return f"<span title='No paper link available'>{safe_title}</span>"


def paper_public_row(raw: Dict[str, object]) -> Dict[str, str]:
    return {
        "PresenterHTML": presenter_with_abstract_html(
            _normalize_text(raw.get("FullName", "")),
            _normalize_text(raw.get("Abstract", "")),
        ),
        "TitleHTML": title_link_html(
            _normalize_text(raw.get("Title", "")),
            _normalize_text(raw.get("LinkToPDF", "")),
        ),
        "Theme": _normalize_text(raw.get("PrimaryTheme", "")),
        "Subtheme": _normalize_text(raw.get("Subtheme", "")),
        "Notes": _normalize_text(raw.get("OverrideNotes", "")),
        "Placement": _normalize_text(raw.get("PlacementStatus", "")),
        "Session": _normalize_text(raw.get("SessionCode", "")),
        "Day": _normalize_text(raw.get("Day", "")),
        "Block": _normalize_text(raw.get("Block", "")),
        "Room": _normalize_text(raw.get("Room", "")),
        "HasLink": "yes" if _normalize_text(raw.get("LinkToPDF", "")).startswith("http") else "no",
    }


def build_classification_update_df(
    submission_id: str,
    primary_theme: str,
    subtheme: str,
    override_notes: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "SubmissionID": _normalize_text(submission_id),
                "PrimaryTheme": _normalize_text(primary_theme),
                "Subtheme": _normalize_text(subtheme),
                "OverrideNotes": _normalize_text(override_notes),
            }
        ]
    )


def build_paper_metadata_update_df(
    submission_id: str,
    title: str,
    full_name: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "SubmissionID": _normalize_text(submission_id),
                "Title": _normalize_text(title),
                "FullName": _normalize_text(full_name),
            }
        ]
    )


def _filtered_papers(
    papers_df: pd.DataFrame,
    edited_ids_set: set[str],
    theme_filter: str,
    subtheme_filter: str,
    day_filter: str,
    block_filter: str,
    room_filter: str,
    show_not_edited_only: bool,
    query: str,
) -> pd.DataFrame:
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
            filtered["Title"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["FullName"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["SubmissionID"].astype(str).str.lower().str.contains(q, na=False)
        ]
    return filtered


def _session_status_rank(status: str) -> int:
    normalized = _normalize_text(status).lower()
    if normalized == "active":
        return 1
    if normalized == "inactive":
        return 2
    return 3


def build_session_options(state) -> tuple[List[Tuple[str, str]], Dict[Tuple[str, str], str]]:
    options: List[Tuple[str, str]] = [("unassigned", "")]
    labels: Dict[Tuple[str, str], str] = {
        ("unassigned", ""): "Unassigned",
    }

    all_sessions = sorted(
        list(getattr(state, "all_sessions", []) or []),
        key=lambda session: (
            _session_status_rank(getattr(session, "status", "")),
            _normalize_text(getattr(session, "session_code", "")).lower(),
            _normalize_text(getattr(session, "day_label", "")),
            _normalize_text(getattr(session, "time", "")),
            _normalize_text(getattr(session, "room", "")),
        ),
    )
    for session in all_sessions:
        session_id = _normalize_text(getattr(session, "session_id", ""))
        if not session_id:
            continue
        status = _normalize_text(getattr(session, "status", "")).lower() or "inactive"
        code = _normalize_text(getattr(session, "session_code", "")) or "[No code]"
        day_label = _normalize_text(getattr(session, "day_label", ""))
        time_label = _normalize_text(getattr(session, "time", ""))
        room = _normalize_text(getattr(session, "room", ""))
        option = ("session", session_id)
        options.append(option)
        labels[option] = f"{code} | {day_label} | {time_label} | {room} [{status}]"

    return options, labels


def default_session_option_for_paper(
    state,
    submission_id: str,
    session_options: Iterable[Tuple[str, str]],
) -> Tuple[str, str]:
    sid = _normalize_text(submission_id)
    paper = next(
        (candidate for candidate in list(getattr(state, "papers", []) or []) if _normalize_text(candidate.submission_id) == sid),
        None,
    )
    default = ("unassigned", "")
    options_set = set(session_options)
    if paper is None:
        return default
    placement_status = _normalize_text(getattr(paper, "placement_status", "")).lower()
    if placement_status not in {"scheduled", "overflow"}:
        return default
    session_id = _normalize_text(getattr(paper, "session_id", ""))
    candidate = ("session", session_id)
    return candidate if session_id and candidate in options_set else default


def render_paper_list_tab(
    state,
    edited_ids: Iterable[str],
    theme_order: List[str],
    papers_to_rows: Callable,
    apply_classification_edits_if_changed: Callable[[pd.DataFrame], bool],
    apply_paper_metadata_edits_if_changed: Callable[[pd.DataFrame], bool],
    apply_paper_session_selection_edit: Callable[[str, Tuple[str, str]], bool],
) -> None:
    st.subheader("Paper List")
    edited_ids_set = set(edited_ids)
    papers_df = pd.DataFrame(papers_to_rows(state))
    if papers_df.empty:
        st.info("No papers available.")
        return

    f1, f2, f3, f4, f5, f6 = st.columns([2, 2, 2, 2, 2, 3])
    theme_filter = f1.selectbox("Theme", ["All"] + sorted(papers_df["PrimaryTheme"].dropna().unique().tolist()))
    subtheme_filter = f2.selectbox("Subtheme", ["All"] + sorted(papers_df["Subtheme"].dropna().unique().tolist()))
    day_filter = f3.selectbox("Day", ["All"] + sorted(papers_df["Day"].dropna().unique().tolist()))
    block_filter = f4.selectbox("Block", ["All"] + sorted(papers_df["Block"].dropna().unique().tolist()))
    room_filter = f5.selectbox("Room", ["All"] + sorted(papers_df["Room"].dropna().unique().tolist()))
    query = f6.text_input("Search title/presenter", "")
    show_not_edited_only = st.checkbox("Show not-edited papers only", value=False)

    filtered = _filtered_papers(
        papers_df=papers_df,
        edited_ids_set=edited_ids_set,
        theme_filter=theme_filter,
        subtheme_filter=subtheme_filter,
        day_filter=day_filter,
        block_filter=block_filter,
        room_filter=room_filter,
        show_not_edited_only=show_not_edited_only,
        query=query,
    )
    if filtered.empty:
        st.info("No papers match the current filters.")
        return

    filtered = filtered.sort_values(by=["Day", "Block", "Room", "SessionCode", "FullName"], kind="stable")
    st.caption(f"Showing {len(filtered)} paper(s).")

    edit_key = "paper_list_edit_submission_id"
    edit_sid = _normalize_text(st.session_state.get(edit_key, ""))
    session_options, session_labels = build_session_options(state)
    visible_ids = set(filtered["SubmissionID"].astype(str).tolist())
    if edit_sid and edit_sid not in visible_ids:
        st.session_state[edit_key] = ""
        edit_sid = ""

    st.caption("Table view with Details editor. Hover presenter for abstract preview.")
    header_cols = st.columns([2.2, 3.2, 1.8, 1.2, 2.0, 0.8], gap="small")
    header_cols[0].markdown("**Presenter**")
    header_cols[1].markdown("**Title**")
    header_cols[2].markdown("**Theme**")
    header_cols[3].markdown("**Session**")
    header_cols[4].markdown("**Placement**")
    header_cols[5].markdown("**Details**")

    for row in filtered.to_dict(orient="records"):
        sid = _normalize_text(row.get("SubmissionID", ""))
        if not sid:
            continue
        public_row = paper_public_row(row)
        is_editing = edit_sid == sid
        row_cols = st.columns([2.2, 3.2, 1.8, 1.2, 2.0, 0.8], gap="small")
        row_cols[0].markdown(public_row["PresenterHTML"], unsafe_allow_html=True)
        row_cols[1].markdown(public_row["TitleHTML"], unsafe_allow_html=True)
        row_cols[2].caption(_clip_text(f"{public_row['Theme']} | {public_row['Subtheme']}", 62) or "[No theme]")
        row_cols[3].caption(_clip_text(public_row["Session"] or "[Unassigned]", 24))
        placement = (
            f"{public_row['Placement']} | {public_row['Session']} | "
            f"{public_row['Day']} | {public_row['Block']} | {public_row['Room']}"
        )
        row_cols[4].caption(_clip_text(placement, 86))
        if row_cols[5].button(
            "Details",
            key=f"paper_row_details_{sid}",
            use_container_width=True,
        ):
            st.session_state[edit_key] = sid
            st.rerun()

        if not is_editing:
            continue

        with st.container(border=True):
            st.caption("Edit Paper")
            abstract = _clean_text(row.get("Abstract", "")) or "No abstract provided."
            with st.expander("Abstract", expanded=True):
                st.write(abstract)

            e_meta_1, e_meta_2 = st.columns([2, 3], gap="small")
            new_author = e_meta_1.text_input(
                "Author",
                value=_normalize_text(row.get("FullName", "")),
                key=f"paper_edit_author_{sid}",
            )
            new_title = e_meta_2.text_input(
                "Title",
                value=_normalize_text(row.get("Title", "")),
                key=f"paper_edit_title_{sid}",
            )
            session_key = f"paper_edit_session_target_{sid}"
            session_src = f"{session_key}_src"
            default_session_target = default_session_option_for_paper(state, sid, session_options)
            if st.session_state.get(session_src) != default_session_target:
                st.session_state[session_key] = default_session_target
                st.session_state[session_src] = default_session_target
            new_session_target = st.selectbox(
                "Target Session",
                options=session_options,
                key=session_key,
                format_func=lambda option: session_labels.get(option, "Unassigned"),
                help="Unassigned first, then active sessions, then inactive sessions.",
            )

            st.caption("Classification")
            theme_options = list(theme_order)
            current_theme = _normalize_text(row.get("PrimaryTheme", ""))
            if current_theme and current_theme not in theme_options:
                theme_options = [current_theme] + theme_options
            theme_index = theme_options.index(current_theme) if current_theme in theme_options else 0
            e1, e2 = st.columns([2, 3], gap="small")
            new_theme = e1.selectbox(
                "PrimaryTheme",
                options=theme_options,
                index=theme_index,
                key=f"paper_edit_theme_{sid}",
            )
            new_subtheme = e2.text_input(
                "Subtheme",
                value=_normalize_text(row.get("Subtheme", "")),
                key=f"paper_edit_subtheme_{sid}",
            )
            new_notes = st.text_area(
                "Notes",
                value=_normalize_text(row.get("OverrideNotes", "")),
                height=90,
                key=f"paper_edit_notes_{sid}",
            )
            save_col, cancel_col = st.columns(2)
            if save_col.button("Save", key=f"paper_edit_save_{sid}", use_container_width=True):
                classification_row = build_classification_update_df(
                    submission_id=sid,
                    primary_theme=new_theme,
                    subtheme=new_subtheme,
                    override_notes=new_notes,
                )
                metadata_row = build_paper_metadata_update_df(
                    submission_id=sid,
                    title=new_title,
                    full_name=new_author,
                )
                class_changed = apply_classification_edits_if_changed(classification_row)
                metadata_changed = apply_paper_metadata_edits_if_changed(metadata_row)
                session_changed = apply_paper_session_selection_edit(sid, new_session_target)
                if class_changed or metadata_changed or session_changed:
                    st.session_state[edit_key] = ""
                    st.rerun()
                st.info("No paper changes detected.")
            if cancel_col.button("Cancel", key=f"paper_edit_cancel_{sid}", use_container_width=True):
                st.session_state[edit_key] = ""
                st.rerun()
