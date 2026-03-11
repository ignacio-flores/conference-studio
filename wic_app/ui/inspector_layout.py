from __future__ import annotations

import re

import streamlit as st

_SCOPE_TOKEN_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _normalize_scope(scope: object) -> str:
    normalized = _SCOPE_TOKEN_RE.sub("-", str(scope or "").strip()).strip("-")
    return normalized or "default"


def _sticky_inspector_css() -> str:
    return """
<style>
:root {
    --wic-inspector-top: 0.75rem;
    --wic-inspector-bottom-gap: 0.75rem;
    --wic-inspector-max-h: calc(100vh - var(--wic-inspector-top) - var(--wic-inspector-bottom-gap));
}

[data-testid="stHorizontalBlock"] > [data-testid="column"]:has(.wic-inspector-marker) {
    position: sticky;
    top: var(--wic-inspector-top);
    align-self: flex-start;
}

[data-testid="stHorizontalBlock"] > .stColumn:has(.wic-inspector-marker) {
    position: sticky;
    top: var(--wic-inspector-top);
    align-self: flex-start;
}

[data-testid="stHorizontalBlock"] > [data-testid="column"]:has(.wic-inspector-marker) > [data-testid="stVerticalBlock"] {
    max-height: var(--wic-inspector-max-h);
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 0.25rem;
}

[data-testid="stHorizontalBlock"] > .stColumn:has(.wic-inspector-marker) > [data-testid="stVerticalBlock"] {
    max-height: var(--wic-inspector-max-h);
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 0.25rem;
}

.wic-inspector-marker {
    display: none;
}

@media (max-width: 1200px) {
    [data-testid="stHorizontalBlock"] > [data-testid="column"]:has(.wic-inspector-marker) {
        position: static;
        top: auto;
    }

    [data-testid="stHorizontalBlock"] > .stColumn:has(.wic-inspector-marker) {
        position: static;
        top: auto;
    }

    [data-testid="stHorizontalBlock"] > [data-testid="column"]:has(.wic-inspector-marker) > [data-testid="stVerticalBlock"] {
        max-height: none;
        overflow-y: visible;
        overflow-x: visible;
        padding-right: 0;
    }

    [data-testid="stHorizontalBlock"] > .stColumn:has(.wic-inspector-marker) > [data-testid="stVerticalBlock"] {
        max-height: none;
        overflow-y: visible;
        overflow-x: visible;
        padding-right: 0;
    }
}
</style>
""".strip()


def inject_sticky_inspector_css() -> None:
    st.markdown(_sticky_inspector_css(), unsafe_allow_html=True)


def render_inspector_marker(scope: str) -> None:
    safe_scope = _normalize_scope(scope)
    st.markdown(
        (
            "<div class='wic-inspector-marker' "
            f"data-wic-inspector-scope='{safe_scope}' "
            "aria-hidden='true'></div>"
        ),
        unsafe_allow_html=True,
    )
