from __future__ import annotations

import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence

import pandas as pd
import streamlit as st

NO_LABEL_DISPLAY = "[No label]"
ALL_PRIMARY_FILTER = "__all_primary__"
LABEL_TYPE_PRIMARY = "primary"
LABEL_TYPE_SECONDARY = "secondary"



def _normalize_text(value: object) -> str:
    return str(value or "").strip()



def format_label_option(value: object) -> str:
    cleaned = _normalize_text(value)
    return cleaned if cleaned else NO_LABEL_DISPLAY



def parse_label_values(raw: object) -> List[str]:
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



def merged_primary_label_options(
    theme_order: Sequence[str],
    catalog_primary_labels: Sequence[str],
    paper_primary_labels: Sequence[str],
) -> List[str]:
    options: List[str] = [""]
    seen = {""}
    for candidate in list(theme_order) + list(catalog_primary_labels) + list(paper_primary_labels):
        cleaned = _normalize_text(candidate)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        options.append(cleaned)
    return options


def relabel_catalog_values(
    catalog: Dict[str, Iterable[str]],
    *,
    label_type: str,
    source_label: str,
    target_label: str,
) -> Dict[str, set[str]]:
    source_value = _normalize_text(source_label)
    target_value = _normalize_text(target_label)
    primary = {_normalize_text(value) for value in catalog.get(LABEL_TYPE_PRIMARY, []) if _normalize_text(value)}
    secondary = {_normalize_text(value) for value in catalog.get(LABEL_TYPE_SECONDARY, []) if _normalize_text(value)}

    if label_type == LABEL_TYPE_PRIMARY:
        if source_value:
            primary.discard(source_value)
        if target_value:
            primary.add(target_value)
    elif label_type == LABEL_TYPE_SECONDARY:
        if source_value:
            secondary.discard(source_value)
        if target_value:
            secondary.add(target_value)

    return {
        LABEL_TYPE_PRIMARY: primary,
        LABEL_TYPE_SECONDARY: secondary,
    }



def build_bulk_primary_update_df(
    papers_df: pd.DataFrame,
    source_primary: str,
    target_primary: str,
) -> pd.DataFrame:
    columns = ["SubmissionID", "PrimaryTheme", "Subtheme", "OverrideNotes"]
    if papers_df.empty:
        return pd.DataFrame(columns=columns)

    source = _normalize_text(source_primary)
    if not source:
        return pd.DataFrame(columns=columns)

    working = papers_df.copy()
    working["PrimaryTheme"] = working["PrimaryTheme"].astype(str).map(_normalize_text)
    matched = working[working["PrimaryTheme"] == source]
    if matched.empty:
        return pd.DataFrame(columns=columns)

    updates = pd.DataFrame(
        {
            "SubmissionID": matched["SubmissionID"].astype(str).map(_normalize_text),
            "PrimaryTheme": _normalize_text(target_primary),
            "Subtheme": matched["Subtheme"].astype(str).map(_normalize_text),
            "OverrideNotes": matched["OverrideNotes"].astype(str).map(_normalize_text),
        }
    )
    return updates[columns].reset_index(drop=True)



def build_bulk_secondary_update_df(
    papers_df: pd.DataFrame,
    source_secondary: str,
    target_secondary: str,
    primary_filter: Optional[str] = None,
) -> pd.DataFrame:
    columns = ["SubmissionID", "PrimaryTheme", "Subtheme", "OverrideNotes"]
    if papers_df.empty:
        return pd.DataFrame(columns=columns)

    source = _normalize_text(source_secondary)
    if not source:
        return pd.DataFrame(columns=columns)

    working = papers_df.copy()
    working["PrimaryTheme"] = working["PrimaryTheme"].astype(str).map(_normalize_text)
    working["Subtheme"] = working["Subtheme"].astype(str).map(_normalize_text)

    if primary_filter is not None:
        working = working[working["PrimaryTheme"] == _normalize_text(primary_filter)]

    matched = working[working["Subtheme"] == source]
    if matched.empty:
        return pd.DataFrame(columns=columns)

    updates = pd.DataFrame(
        {
            "SubmissionID": matched["SubmissionID"].astype(str).map(_normalize_text),
            "PrimaryTheme": matched["PrimaryTheme"].astype(str).map(_normalize_text),
            "Subtheme": _normalize_text(target_secondary),
            "OverrideNotes": matched["OverrideNotes"].astype(str).map(_normalize_text),
        }
    )
    return updates[columns].reset_index(drop=True)



def _paper_labels_df(state) -> pd.DataFrame:
    rows: List[Dict[str, str]] = []
    for paper in list(getattr(state, "papers", []) or []):
        rows.append(
            {
                "SubmissionID": _normalize_text(getattr(paper, "submission_id", "")),
                "PrimaryTheme": _normalize_text(getattr(paper, "primary_theme", "")),
                "Subtheme": _normalize_text(getattr(paper, "detailed_subtheme", "")),
                "OverrideNotes": _normalize_text(getattr(paper, "override_notes", "")),
            }
        )
    return pd.DataFrame(rows, columns=["SubmissionID", "PrimaryTheme", "Subtheme", "OverrideNotes"])



def render_labels_tab(
    state,
    theme_order: Sequence[str],
    load_label_catalog_fn: Callable[[], Dict[str, List[str]]],
    write_label_catalog_fn: Callable[[Dict[str, Iterable[str]]], None],
    apply_classification_edits_if_changed: Callable[[pd.DataFrame], bool],
) -> None:
    st.subheader("Labels")

    papers_df = _paper_labels_df(state)
    if papers_df.empty:
        st.info("No papers available.")
        return

    catalog = load_label_catalog_fn() or {}
    catalog_primary = sorted({_normalize_text(value) for value in catalog.get("primary", []) if _normalize_text(value)}, key=str.casefold)
    catalog_secondary = sorted({_normalize_text(value) for value in catalog.get("secondary", []) if _normalize_text(value)}, key=str.casefold)

    paper_primary_values = sorted(
        {_normalize_text(value) for value in papers_df["PrimaryTheme"].tolist() if _normalize_text(value)},
        key=str.casefold,
    )
    paper_secondary_values = sorted(
        {_normalize_text(value) for value in papers_df["Subtheme"].tolist() if _normalize_text(value)},
        key=str.casefold,
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Papers", len(papers_df))
    m2.metric("Primary labels", len(set(catalog_primary) | set(paper_primary_values)))
    m3.metric("Secondary labels", len(set(catalog_secondary) | set(paper_secondary_values)))

    with st.expander("Create labels", expanded=True):
        with st.form("labels_create_form", clear_on_submit=True):
            create_col1, create_col2 = st.columns(2)
            new_primary_raw = create_col1.text_input(
                "New primary labels (comma, semicolon, or new-line separated)",
                value="",
            )
            new_secondary_raw = create_col2.text_input(
                "New secondary labels (comma, semicolon, or new-line separated)",
                value="",
            )
            create_submit = st.form_submit_button("Add labels", use_container_width=True)

        if create_submit:
            new_primary = parse_label_values(new_primary_raw)
            new_secondary = parse_label_values(new_secondary_raw)
            if not new_primary and not new_secondary:
                st.info("Enter at least one label value.")
            else:
                updated_primary = set(catalog_primary) | set(new_primary)
                updated_secondary = set(catalog_secondary) | set(new_secondary)
                write_label_catalog_fn(
                    {
                        "primary": updated_primary,
                        "secondary": updated_secondary,
                    }
                )
                st.rerun()

    st.markdown("---")
    st.caption("Bulk primary operations")
    source_primary_options = sorted(set(catalog_primary) | set(paper_primary_values), key=str.casefold)
    if not source_primary_options:
        st.info("No primary labels available to update.")
    else:
        with st.form("labels_bulk_primary_form", clear_on_submit=False):
            source_primary = st.selectbox(
                "Source primary label",
                source_primary_options,
            )
            primary_action = st.selectbox(
                "Action",
                ["Rename label", "Drop to empty"],
            )
            target_primary = st.text_input(
                "Target primary label",
                value="",
                disabled=primary_action != "Rename label",
            )
            primary_submit = st.form_submit_button("Apply primary bulk update", use_container_width=True)

        if primary_submit:
            target_primary_value = "" if primary_action == "Drop to empty" else _normalize_text(target_primary)
            if primary_action == "Rename label" and not target_primary_value:
                st.error("Target primary label is required for rename.")
            else:
                refreshed_catalog = load_label_catalog_fn() or {}
                updated_catalog = relabel_catalog_values(
                    refreshed_catalog,
                    label_type=LABEL_TYPE_PRIMARY,
                    source_label=source_primary,
                    target_label=target_primary_value,
                )
                refreshed_primary = {
                    _normalize_text(value) for value in refreshed_catalog.get(LABEL_TYPE_PRIMARY, []) if _normalize_text(value)
                }
                refreshed_secondary = {
                    _normalize_text(value) for value in refreshed_catalog.get(LABEL_TYPE_SECONDARY, []) if _normalize_text(value)
                }
                catalog_changed = (
                    updated_catalog[LABEL_TYPE_PRIMARY] != refreshed_primary
                    or updated_catalog[LABEL_TYPE_SECONDARY] != refreshed_secondary
                )
                updates_df = build_bulk_primary_update_df(
                    papers_df,
                    source_primary=source_primary,
                    target_primary=target_primary_value,
                )
                if updates_df.empty:
                    if catalog_changed:
                        write_label_catalog_fn(updated_catalog)
                        st.rerun()
                    st.info("No papers matched the selected source primary label.")
                else:
                    labels_changed = apply_classification_edits_if_changed(updates_df)
                    if labels_changed or catalog_changed:
                        if catalog_changed:
                            write_label_catalog_fn(updated_catalog)
                        st.rerun()
                    st.info("No primary label changes detected.")

    st.markdown("---")
    st.caption("Bulk secondary operations")
    primary_filter_options = [ALL_PRIMARY_FILTER] + merged_primary_label_options(
        theme_order,
        catalog_primary,
        paper_primary_values,
    )

    with st.form("labels_bulk_secondary_form", clear_on_submit=False):
        primary_filter_pick = st.selectbox(
            "Primary filter (optional)",
            primary_filter_options,
            format_func=lambda value: (
                "All primary labels"
                if value == ALL_PRIMARY_FILTER
                else format_label_option(value)
            ),
        )

        filtered_df = papers_df.copy()
        primary_filter_value: Optional[str] = None
        if primary_filter_pick != ALL_PRIMARY_FILTER:
            primary_filter_value = _normalize_text(primary_filter_pick)
            filtered_df = filtered_df[
                filtered_df["PrimaryTheme"].astype(str).map(_normalize_text) == primary_filter_value
            ]

        source_secondary_options = sorted(
            set(catalog_secondary)
            | {
                _normalize_text(value)
                for value in filtered_df.get("Subtheme", []).tolist()
                if _normalize_text(value)
            },
            key=str.casefold,
        )

        source_secondary = st.selectbox(
            "Source secondary label",
            source_secondary_options if source_secondary_options else [""],
            format_func=lambda value: _normalize_text(value) or "[No secondary labels available]",
            disabled=not source_secondary_options,
        )

        secondary_action = st.selectbox(
            "Action",
            ["Rename label", "Drop to empty"],
        )
        target_secondary = st.text_input(
            "Target secondary label",
            value="",
            disabled=secondary_action != "Rename label",
        )
        secondary_submit = st.form_submit_button(
            "Apply secondary bulk update",
            use_container_width=True,
            disabled=not source_secondary_options,
        )

    if secondary_submit:
        target_secondary_value = "" if secondary_action == "Drop to empty" else _normalize_text(target_secondary)
        if secondary_action == "Rename label" and not target_secondary_value:
            st.error("Target secondary label is required for rename.")
        else:
            refreshed_catalog = load_label_catalog_fn() or {}
            updated_catalog = relabel_catalog_values(
                refreshed_catalog,
                label_type=LABEL_TYPE_SECONDARY,
                source_label=source_secondary,
                target_label=target_secondary_value,
            )
            refreshed_primary = {
                _normalize_text(value) for value in refreshed_catalog.get(LABEL_TYPE_PRIMARY, []) if _normalize_text(value)
            }
            refreshed_secondary = {
                _normalize_text(value) for value in refreshed_catalog.get(LABEL_TYPE_SECONDARY, []) if _normalize_text(value)
            }
            catalog_changed = (
                updated_catalog[LABEL_TYPE_PRIMARY] != refreshed_primary
                or updated_catalog[LABEL_TYPE_SECONDARY] != refreshed_secondary
            )
            updates_df = build_bulk_secondary_update_df(
                papers_df,
                source_secondary=source_secondary,
                target_secondary=target_secondary_value,
                primary_filter=primary_filter_value,
            )
            if updates_df.empty:
                if catalog_changed:
                    write_label_catalog_fn(updated_catalog)
                    st.rerun()
                st.info("No papers matched the selected secondary label criteria.")
            else:
                labels_changed = apply_classification_edits_if_changed(updates_df)
                if labels_changed or catalog_changed:
                    if catalog_changed:
                        write_label_catalog_fn(updated_catalog)
                    st.rerun()
                st.info("No secondary label changes detected.")
