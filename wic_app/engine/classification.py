from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple


def classify_papers(
    papers: List[object],
    classification_overrides: Optional[Dict[str, Dict[str, str]]] = None,
    *,
    normalize_key: Callable[[str], str],
    map_source_themes: Callable[[str], List[str]],
    infer_theme_from_text: Callable[[str], str],
    classify_subtheme: Callable[[str, str], Tuple[str, List[str]]],
    keyword_matches: Callable[[str, List[str]], List[str]],
    theme_keywords: Dict[str, List[str]],
    parse_bool: Callable[[str], bool],
    empty_label_sentinel: str = "",
) -> None:
    overrides = classification_overrides or {}

    for paper in papers:
        text = normalize_key(f"{getattr(paper, 'title', '')} {getattr(paper, 'abstract', '')}")
        tags = map_source_themes(getattr(paper, "source_themes", ""))
        inferred_primary = infer_theme_from_text(text)

        if tags:
            primary = tags[0]
            secondary = list(dict.fromkeys(tags[1:]))[:2]
            source_hint = "source theme"

            override_candidates = {"Income and wealth mobility", "Land inequality"}
            if inferred_primary in override_candidates and inferred_primary != primary:
                inferred_hits = keyword_matches(text, theme_keywords.get(inferred_primary, []))
                if len(inferred_hits) >= 2:
                    secondary = list(dict.fromkeys([primary] + secondary))[:2]
                    primary = inferred_primary
                    source_hint = "title/abstract override"
        else:
            primary = inferred_primary
            secondary = []
            source_hint = "title/abstract inference"

        subtheme, matched_keywords = classify_subtheme(primary, text)

        paper.primary_theme = primary
        paper.detailed_subtheme = subtheme
        paper.secondary_tags = secondary
        paper.matched_keywords = matched_keywords
        paper.rationale = (
            f"Mapped via {source_hint} to '{primary}' and grouped under '{subtheme}'."
        )
        paper.reviewed = False
        paper.override_notes = ""

        override = overrides.get(paper.submission_id)
        if not override:
            continue

        override_theme_raw = str(override.get("OverridePrimaryTheme", "")).strip()
        override_subtheme_raw = str(override.get("OverrideSubtheme", "")).strip()
        theme_is_explicit_empty = bool(empty_label_sentinel) and override_theme_raw == empty_label_sentinel
        subtheme_is_explicit_empty = bool(empty_label_sentinel) and override_subtheme_raw == empty_label_sentinel
        override_theme = "" if theme_is_explicit_empty else override_theme_raw
        override_subtheme = "" if subtheme_is_explicit_empty else override_subtheme_raw
        has_theme_override = theme_is_explicit_empty or bool(override_theme)
        has_subtheme_override = subtheme_is_explicit_empty or bool(override_subtheme)
        reviewed = parse_bool(override.get("Reviewed", ""))
        notes = override.get("OverrideNotes", "")

        if has_theme_override:
            paper.primary_theme = override_theme
            if paper.primary_theme and paper.primary_theme not in paper.secondary_tags and paper.primary_theme != primary:
                paper.secondary_tags = list(dict.fromkeys([primary] + paper.secondary_tags))[:2]

        if has_subtheme_override:
            paper.detailed_subtheme = override_subtheme
        elif has_theme_override and override_theme and override_theme != primary:
            paper.detailed_subtheme = classify_subtheme(paper.primary_theme, text)[0]

        if has_theme_override or has_subtheme_override:
            paper.rationale = "Mapped by manual override in curation UI."

        paper.reviewed = reviewed
        paper.override_notes = notes
