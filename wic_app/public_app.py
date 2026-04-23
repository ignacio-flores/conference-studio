from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from runtime_compat import install_hashlib_usedforsecurity_compat

install_hashlib_usedforsecurity_compat()

import streamlit as st

from public_data import PUBLIC_JSON_FILE, PUBLIC_XLSX_FILE, load_public_payload


APP_TITLE = "Conference Programme"
PUBLIC_ENABLED_SETTING = "PUBLIC_ENABLED"
PUBLIC_JSON_PATH_SETTING = "PUBLIC_JSON_PATH"
PUBLIC_XLSX_PATH_SETTING = "PUBLIC_XLSX_PATH"


st.set_page_config(page_title=APP_TITLE, layout="wide")


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _clean_key(value: object) -> str:
    return _normalize_text(value).lower()


def _env_setting(name: str) -> str:
    return _normalize_text(os.environ.get(name, ""))


def _parse_bool_setting(value: object, default: bool = False) -> bool:
    normalized = _normalize_text(value).lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _public_release_enabled() -> bool:
    enabled_raw = _env_setting(PUBLIC_ENABLED_SETTING)
    if not enabled_raw:
        return False
    return _parse_bool_setting(enabled_raw, default=False)


def _public_json_path() -> Path:
    configured = _env_setting(PUBLIC_JSON_PATH_SETTING)
    return Path(configured) if configured else PUBLIC_JSON_FILE


def _public_xlsx_path() -> Path:
    configured = _env_setting(PUBLIC_XLSX_PATH_SETTING)
    return Path(configured) if configured else PUBLIC_XLSX_FILE


def _holding_page() -> None:
    st.title(APP_TITLE)
    st.info("The public programme is not available yet.")
    st.stop()


def _data_unavailable() -> None:
    st.title(APP_TITLE)
    st.warning("The public programme is temporarily unavailable.")
    st.stop()


def _load_dataset() -> Dict[str, Any]:
    path = _public_json_path()
    if not path.exists():
        _data_unavailable()
    try:
        return load_public_payload(path)
    except Exception:
        _data_unavailable()
    return {}


def _inject_public_css() -> None:
    st.markdown(
        """
<style>
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at top left, rgba(219, 232, 246, 0.85), transparent 34%),
        linear-gradient(180deg, #f7fafc 0%, #eef3f8 100%);
}
[data-testid="block-container"] {
    padding-top: 1.25rem;
    padding-bottom: 2rem;
}
.public-shell {
    padding: 1rem 1.1rem 0.8rem;
    border: 1px solid #d6dee8;
    border-radius: 18px;
    background: rgba(255,255,255,0.86);
    box-shadow: 0 14px 40px rgba(25, 49, 79, 0.07);
    margin-bottom: 1rem;
}
.public-kicker {
    display: inline-block;
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #43607d;
    margin-bottom: 0.35rem;
}
.public-note {
    font-size: 0.92rem;
    color: #5a6e84;
}
.public-matrix-row {
    padding: 0.2rem 0 0.55rem;
}
.public-matrix-block {
    padding: 0.75rem 0.85rem;
    border: 1px solid #d4dde8;
    border-radius: 14px;
    background: #f8fbfd;
    min-height: 100%;
}
.public-session-card {
    padding: 0.75rem 0.85rem;
    border: 1px solid #d5dde8;
    border-radius: 14px;
    background: white;
    margin-bottom: 0.45rem;
}
.public-session-meta {
    font-size: 0.85rem;
    color: #5f6f86;
}
.public-detail-card {
    padding: 0.95rem 1rem;
    border: 1px solid #d3dde8;
    border-radius: 18px;
    background: rgba(255,255,255,0.92);
    position: sticky;
    top: 0.6rem;
}
.public-detail-list {
    border-top: 1px solid #e2e8ef;
    margin-top: 0.85rem;
    padding-top: 0.85rem;
}
</style>
""",
        unsafe_allow_html=True,
    )


def _day_sort_key(day_label: str) -> Tuple[int, str]:
    digits = "".join(ch for ch in _normalize_text(day_label) if ch.isdigit())
    return (int(digits or 999), _normalize_text(day_label))


def _session_sort_key(session: Dict[str, Any]) -> Tuple[int, int, str, str]:
    return (
        int(session.get("day_num", 0) or 0),
        int(session.get("start_min", 0) or 0),
        _normalize_text(session.get("room", "")),
        _normalize_text(session.get("session_code", "")),
    )


def _paper_sort_key(paper: Dict[str, Any]) -> Tuple[int, int, str, str]:
    return (
        int(paper.get("day_num", 0) or 0),
        int(paper.get("talk_start_min", 0) or 0),
        _normalize_text(paper.get("room", "")),
        _normalize_text(paper.get("title", "")),
    )


def _find_session(sessions: List[Dict[str, Any]], session_id: str) -> Optional[Dict[str, Any]]:
    target = _normalize_text(session_id)
    return next((session for session in sessions if _normalize_text(session.get("session_id", "")) == target), None)


def _find_paper(papers: List[Dict[str, Any]], submission_id: str) -> Optional[Dict[str, Any]]:
    target = _normalize_text(submission_id)
    return next((paper for paper in papers if _normalize_text(paper.get("submission_id", "")) == target), None)


def _render_downloads() -> None:
    xlsx_path = _public_xlsx_path()
    if not xlsx_path.exists():
        return
    st.download_button(
        "Download Excel",
        data=xlsx_path.read_bytes(),
        file_name=xlsx_path.name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=False,
    )


def _apply_structure_filters(
    sessions: List[Dict[str, Any]],
    papers: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
    all_days = sorted({_normalize_text(session.get("day_label", "")) for session in sessions if _normalize_text(session.get("day_label", ""))}, key=_day_sort_key)
    selected_day = st.selectbox("Day", all_days, key="public_structure_day") if all_days else ""

    day_sessions = [session for session in sessions if _normalize_text(session.get("day_label", "")) == selected_day]
    day_papers = [paper for paper in papers if _normalize_text(paper.get("day_label", "")) == selected_day]

    room_options = sorted({_normalize_text(session.get("room", "")) for session in day_sessions if _normalize_text(session.get("room", ""))})
    theme_options = sorted({_normalize_text(session.get("primary_theme", "")) for session in day_sessions if _normalize_text(session.get("primary_theme", ""))})

    filter_cols = st.columns([1.8, 1.2, 1.2], gap="small")
    search_text = filter_cols[0].text_input(
        "Find a session or paper",
        key="public_structure_search",
        placeholder="Session title, author, room, theme",
    )
    selected_rooms = filter_cols[1].multiselect(
        "Rooms",
        options=room_options,
        default=room_options,
        key="public_structure_rooms",
    )
    selected_theme = filter_cols[2].selectbox("Theme", ["All"] + theme_options, key="public_structure_theme")

    query_terms = [term for term in _normalize_text(search_text).lower().split() if term]

    filtered_sessions: List[Dict[str, Any]] = []
    for session in day_sessions:
        room = _normalize_text(session.get("room", ""))
        theme = _normalize_text(session.get("primary_theme", ""))
        haystack_parts = [
            _normalize_text(session.get("session_title", "")),
            _normalize_text(session.get("session_code", "")),
            room,
            theme,
            _normalize_text(session.get("subtheme", "")),
        ]
        haystack_parts.extend(_normalize_text(talk.get("title", "")) for talk in session.get("talks", []))
        haystack_parts.extend(_normalize_text(talk.get("authors", "")) for talk in session.get("talks", []))
        haystack = " ".join(haystack_parts).lower()
        if selected_rooms and room not in selected_rooms:
            continue
        if selected_theme != "All" and theme != selected_theme:
            continue
        if query_terms and not all(term in haystack for term in query_terms):
            continue
        filtered_sessions.append(session)

    visible_session_ids = {_normalize_text(session.get("session_id", "")) for session in filtered_sessions}
    filtered_papers = [paper for paper in day_papers if _normalize_text(paper.get("session_id", "")) in visible_session_ids]
    return sorted(filtered_sessions, key=_session_sort_key), sorted(filtered_papers, key=_paper_sort_key), selected_day


def _render_structure_matrix(sessions: List[Dict[str, Any]], day_label: str) -> None:
    if not sessions:
        st.info("No sessions match the current filters.")
        return

    rooms = sorted({_normalize_text(session.get("room", "")) for session in sessions if _normalize_text(session.get("room", ""))})
    grouped: Dict[Tuple[int, int, str, str], Dict[str, Any]] = {}
    for session in sessions:
        key = (
            int(session.get("block_num", 0) or 0),
            int(session.get("start_min", 0) or 0),
            _normalize_text(session.get("time", "")),
            _normalize_text(session.get("block_label", "")),
        )
        grouped.setdefault(
            key,
            {
                "block_num": int(session.get("block_num", 0) or 0),
                "time": _normalize_text(session.get("time", "")),
                "block_label": _normalize_text(session.get("block_label", "")),
                "sessions_by_room": {},
            },
        )
        grouped[key]["sessions_by_room"][_normalize_text(session.get("room", ""))] = session

    st.markdown(
        f"<div class='public-note'>Browse sessions for <strong>{day_label}</strong>. Select a session to open its details.</div>",
        unsafe_allow_html=True,
    )

    header_cols = st.columns([1.35] + [1.0] * len(rooms), gap="small")
    header_cols[0].markdown("<div class='public-kicker'>Block / Time</div>", unsafe_allow_html=True)
    for idx, room in enumerate(rooms, start=1):
        header_cols[idx].markdown(f"<div class='public-kicker'>{room}</div>", unsafe_allow_html=True)

    for row_key in sorted(grouped.keys()):
        row = grouped[row_key]
        cols = st.columns([1.35] + [1.0] * len(rooms), gap="small")
        cols[0].markdown(
            (
                "<div class='public-matrix-block'>"
                f"<div class='public-kicker'>B{row['block_num']}</div>"
                f"<div><strong>{row['block_label']}</strong></div>"
                f"<div class='public-session-meta'>{row['time']}</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        for idx, room in enumerate(rooms, start=1):
            session = row["sessions_by_room"].get(room)
            with cols[idx]:
                if session is None:
                    st.markdown("<div class='public-matrix-block public-session-meta'>No session</div>", unsafe_allow_html=True)
                    continue
                talks = list(session.get("talks", []) or [])
                st.markdown(
                    (
                        "<div class='public-session-card'>"
                        f"<div class='public-kicker'>{room}</div>"
                        f"<div><strong>{session['session_title']}</strong></div>"
                        f"<div class='public-session-meta'>{session['primary_theme']}</div>"
                        f"<div class='public-session-meta'>{len(talks)} paper(s)</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Open session",
                    key=f"public_structure_session_{session['session_id']}",
                    use_container_width=True,
                ):
                    st.session_state.public_selected_session_id = _normalize_text(session.get("session_id", ""))
                    st.session_state.abstract_open_submission_id = ""
                    st.rerun()


def _render_session_details(sessions: List[Dict[str, Any]], papers: List[Dict[str, Any]]) -> None:
    st.subheader("Session details")
    selected_session_id = _normalize_text(st.session_state.get("public_selected_session_id", ""))
    session = _find_session(sessions, selected_session_id)
    if session is None:
        st.info("Choose a session from the structure or programme view.")
        return

    st.markdown("<div class='public-detail-card'>", unsafe_allow_html=True)
    st.markdown(f"**{session['session_title']}**")
    st.caption(
        f"{session['day_label']} | {session['time']} | {session['room']} | {session['block_label']}"
    )
    if _normalize_text(session.get("primary_theme", "")):
        st.markdown(
            f"<div class='public-note'><strong>{session['primary_theme']}</strong> · {session['subtheme']}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div class='public-detail-list'>", unsafe_allow_html=True)
    for talk in list(session.get("talks", []) or []):
        talk_id = _normalize_text(talk.get("submission_id", ""))
        st.markdown(f"**{talk['title']}**")
        st.caption(_normalize_text(talk.get("presenter_display", "")) or talk["authors"])
        if st.button("Show abstract", key=f"public_session_abstract_{talk_id}", use_container_width=True):
            st.session_state.abstract_open_submission_id = talk_id
            st.session_state.public_selected_paper_id = talk_id
            st.rerun()
        if _normalize_text(st.session_state.get("abstract_open_submission_id", "")) == talk_id:
            if talk.get("abstract"):
                st.write(talk["abstract"])
            selected_paper = _find_paper(papers, talk_id)
            if selected_paper is not None:
                st.caption(
                    f"Also in Papers: {selected_paper['day_label']} | {selected_paper['time']} | {selected_paper['room']}"
                )
        st.markdown("---")
    st.markdown("</div></div>", unsafe_allow_html=True)


def _render_structure_tab(sessions: List[Dict[str, Any]], papers: List[Dict[str, Any]]) -> None:
    filtered_sessions, filtered_papers, selected_day = _apply_structure_filters(sessions, papers)
    left_col, right_col = st.columns([2.6, 1.2], gap="large")
    with left_col:
        _render_structure_matrix(filtered_sessions, selected_day)
    with right_col:
        _render_session_details(filtered_sessions, filtered_papers)


def _render_programme_tab(sessions: List[Dict[str, Any]]) -> None:
    st.subheader("Programme")
    day_options = sorted({_normalize_text(session.get("day_label", "")) for session in sessions if _normalize_text(session.get("day_label", ""))}, key=_day_sort_key)
    selected_day = st.selectbox("Day", day_options, key="public_programme_day") if day_options else ""
    day_sessions = [session for session in sessions if _normalize_text(session.get("day_label", "")) == selected_day]

    block_labels = sorted(
        {f"B{int(session.get('block_num', 0) or 0)} | {_normalize_text(session.get('block_label', ''))}" for session in day_sessions}
    )
    selected_block = st.selectbox("Block", ["All blocks"] + block_labels, key="public_programme_block")

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for session in sorted(day_sessions, key=_session_sort_key):
        block_label = f"B{int(session.get('block_num', 0) or 0)} | {_normalize_text(session.get('block_label', ''))}"
        if selected_block != "All blocks" and block_label != selected_block:
            continue
        group_key = f"{session['time']} | {block_label}"
        grouped.setdefault(group_key, []).append(session)

    if not grouped:
        st.info("No programme blocks match the current filters.")
        return

    for group_label, block_sessions in grouped.items():
        st.markdown(f"### {group_label}")
        cols = st.columns(min(3, max(1, len(block_sessions))), gap="small")
        for idx, session in enumerate(block_sessions):
            with cols[idx % len(cols)]:
                st.markdown(
                    (
                        "<div class='public-session-card'>"
                        f"<div class='public-kicker'>{session['room']}</div>"
                        f"<div><strong>{session['session_title']}</strong></div>"
                        f"<div class='public-session-meta'>{session['primary_theme']}</div>"
                        f"<div class='public-session-meta'>{len(session.get('talks', []))} paper(s)</div>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
                if st.button("Open session", key=f"public_programme_session_{session['session_id']}", use_container_width=True):
                    st.session_state.public_selected_session_id = _normalize_text(session.get("session_id", ""))
                    st.session_state.abstract_open_submission_id = ""
                    st.rerun()


def _render_paper_details(papers: List[Dict[str, Any]]) -> None:
    st.subheader("Paper details")
    selected_paper_id = _normalize_text(st.session_state.get("public_selected_paper_id", ""))
    paper = _find_paper(papers, selected_paper_id)
    if paper is None:
        st.info("Choose a paper from the directory to view its details.")
        return

    st.markdown("<div class='public-detail-card'>", unsafe_allow_html=True)
    st.markdown(f"**{paper['title']}**")
    st.caption(paper["authors"])
    st.caption(
        f"{paper['day_label']} | {paper['time']} | {paper['room']} | {paper['session_title']}"
    )
    st.markdown(
        f"<div class='public-note'><strong>{paper['primary_theme']}</strong> · {paper['subtheme']}</div>",
        unsafe_allow_html=True,
    )
    if _normalize_text(paper.get("abstract", "")):
        st.write(paper["abstract"])
    st.markdown("</div>", unsafe_allow_html=True)


def _render_papers_tab(papers: List[Dict[str, Any]]) -> None:
    st.subheader("Papers")
    filter_cols = st.columns([2.0, 1.1, 1.1, 1.1], gap="small")
    query = filter_cols[0].text_input("Search papers", key="public_papers_search", placeholder="Title, author, session")
    day_options = sorted({_normalize_text(paper.get("day_label", "")) for paper in papers if _normalize_text(paper.get("day_label", ""))}, key=_day_sort_key)
    theme_options = sorted({_normalize_text(paper.get("primary_theme", "")) for paper in papers if _normalize_text(paper.get("primary_theme", ""))})
    room_options = sorted({_normalize_text(paper.get("room", "")) for paper in papers if _normalize_text(paper.get("room", ""))})
    selected_day = filter_cols[1].selectbox("Day", ["All"] + day_options, key="public_papers_day")
    selected_theme = filter_cols[2].selectbox("Theme", ["All"] + theme_options, key="public_papers_theme")
    selected_room = filter_cols[3].selectbox("Room", ["All"] + room_options, key="public_papers_room")

    query_terms = [term for term in _normalize_text(query).lower().split() if term]
    filtered_papers: List[Dict[str, Any]] = []
    for paper in sorted(papers, key=_paper_sort_key):
        if selected_day != "All" and _normalize_text(paper.get("day_label", "")) != selected_day:
            continue
        if selected_theme != "All" and _normalize_text(paper.get("primary_theme", "")) != selected_theme:
            continue
        if selected_room != "All" and _normalize_text(paper.get("room", "")) != selected_room:
            continue
        haystack = " ".join(
            [
                _normalize_text(paper.get("title", "")),
                _normalize_text(paper.get("authors", "")),
                _normalize_text(paper.get("session_title", "")),
                _normalize_text(paper.get("primary_theme", "")),
                _normalize_text(paper.get("subtheme", "")),
            ]
        ).lower()
        if query_terms and not all(term in haystack for term in query_terms):
            continue
        filtered_papers.append(paper)

    list_col, detail_col = st.columns([1.6, 1.2], gap="large")
    with list_col:
        st.caption(f"{len(filtered_papers)} paper(s)")
        for paper in filtered_papers:
            st.markdown(
                (
                    "<div class='public-session-card'>"
                    f"<div><strong>{paper['title']}</strong></div>"
                    f"<div class='public-session-meta'>{paper['authors']}</div>"
                    f"<div class='public-session-meta'>{paper['day_label']} · {paper['time']} · {paper['room']}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            if st.button("Open paper", key=f"public_paper_select_{paper['submission_id']}", use_container_width=True):
                st.session_state.public_selected_paper_id = _normalize_text(paper.get("submission_id", ""))
                st.rerun()
    with detail_col:
        _render_paper_details(filtered_papers)


def main() -> None:
    if not _public_release_enabled():
        _holding_page()

    payload = _load_dataset()
    conference = dict(payload.get("conference", {}))
    sessions = sorted(list(payload.get("sessions", []) or []), key=_session_sort_key)
    papers = sorted(list(payload.get("papers", []) or []), key=_paper_sort_key)

    _inject_public_css()

    st.markdown("<div class='public-shell'>", unsafe_allow_html=True)
    st.markdown("<div class='public-kicker'>Attendee view</div>", unsafe_allow_html=True)
    st.title(_normalize_text(conference.get("title")) or APP_TITLE)
    subtitle = _normalize_text(conference.get("subtitle"))
    if subtitle:
        st.caption(subtitle)
    generated_at = _normalize_text(conference.get("generated_at"))
    top_cols = st.columns([2.2, 1.0], gap="small")
    with top_cols[0]:
        if generated_at:
            st.caption(f"Updated: {generated_at}")
    with top_cols[1]:
        _render_downloads()

    if sessions and not _normalize_text(st.session_state.get("public_selected_session_id", "")):
        st.session_state.public_selected_session_id = _normalize_text(sessions[0].get("session_id", ""))

    if papers and not _normalize_text(st.session_state.get("public_selected_paper_id", "")):
        st.session_state.public_selected_paper_id = _normalize_text(papers[0].get("submission_id", ""))

    if "abstract_open_submission_id" not in st.session_state:
        st.session_state.abstract_open_submission_id = ""

    tab_structure, tab_programme, tab_papers = st.tabs(["Structure", "Programme", "Papers"])
    with tab_structure:
        _render_structure_tab(sessions, papers)
    with tab_programme:
        _render_programme_tab(sessions)
    with tab_papers:
        _render_papers_tab(papers)
    st.markdown("</div>", unsafe_allow_html=True)


main()
