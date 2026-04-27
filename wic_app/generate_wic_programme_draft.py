#!/usr/bin/env python3
"""Generate WIC 2026 draft and publish outputs from current overrides.

Usage:
    python3 generate_wic_programme_draft.py
    python3 generate_wic_programme_draft.py --publish
"""

from __future__ import annotations

import argparse
from pathlib import Path

from runtime_compat import install_hashlib_usedforsecurity_compat

install_hashlib_usedforsecurity_compat()

from engine.config import load_conference_config
from exporters.publish import (
    PUBLISH_DISPLAY_FULL,
    PUBLISH_DISPLAY_PUBLIC_SAFE,
    export_draft_workbook,
    export_public_excel,
    export_public_payload,
    export_publish_docx,
    export_publish_excel,
    export_publish_pdf,
)
from public_data import PUBLIC_JSON_FILE, PUBLIC_XLSX_FILE
from reclassification_engine import (
    DRAFT_OUTPUT_FILE,
    PUBLISH_DOCX_FILE,
    PUBLISH_PDF_FILE,
    PUBLISH_XLSX_FILE,
    build_programme_state,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also generate publish Excel, PDF, and Word outputs.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="",
        help="Optional path to conference config JSON/YAML.",
    )
    parser.add_argument(
        "--publish-display",
        type=str,
        choices=[PUBLISH_DISPLAY_FULL, PUBLISH_DISPLAY_PUBLIC_SAFE],
        default=PUBLISH_DISPLAY_FULL,
        help="Publish display mode: full or public_safe.",
    )
    parser.add_argument(
        "--public-rooms",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Show room names in public JSON/XLSX outputs. Defaults to the legacy mapping from --publish-display.",
    )
    parser.add_argument(
        "--public-moderators",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Show moderator labels in public JSON/XLSX outputs. Defaults to the legacy mapping from --publish-display.",
    )
    parser.add_argument(
        "--public-links",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Show paper URLs in public JSON/XLSX outputs when available.",
    )
    parser.add_argument(
        "--hide-public-links",
        action="store_true",
        help="Legacy alias to hide paper URLs in public JSON/XLSX outputs.",
    )
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve() if args.config else None
    conference_config = load_conference_config(config_path)

    draft_output = DRAFT_OUTPUT_FILE.parent / conference_config.files.get("draft_output", DRAFT_OUTPUT_FILE.name)
    publish_xlsx_output = PUBLISH_XLSX_FILE.parent / conference_config.files.get("publish_xlsx_output", PUBLISH_XLSX_FILE.name)
    publish_pdf_output = PUBLISH_PDF_FILE.parent / conference_config.files.get("publish_pdf_output", PUBLISH_PDF_FILE.name)
    publish_docx_output = PUBLISH_DOCX_FILE.parent / conference_config.files.get("publish_docx_output", PUBLISH_DOCX_FILE.name)
    public_json_output = PUBLIC_JSON_FILE.parent / conference_config.files.get("public_json_output", PUBLIC_JSON_FILE.name)
    public_xlsx_output = PUBLIC_XLSX_FILE.parent / conference_config.files.get("public_xlsx_output", PUBLIC_XLSX_FILE.name)

    state = build_programme_state(config_path=config_path)
    validations = state.validations

    draft_path = export_draft_workbook(state, draft_output)
    print(f"Generated draft workbook: {draft_path}")

    print(f"Accepted papers: {validations.get('accepted_papers', 0)}")
    print(f"Scheduled papers: {validations.get('scheduled_papers', validations.get('assigned_papers', 0))}")
    print(f"Overflow papers: {validations.get('overflow_papers', 0)}")
    print(f"Unassigned papers: {validations.get('unassigned_papers', 0)}")
    print(f"Sessions: {validations.get('sessions', 0)}")
    print(f"Reserve slots: {validations.get('reserve_slots', 0)}")
    print(f"Reviewed papers: {validations.get('reviewed_papers', 0)}")
    print(f"Unreviewed papers: {validations.get('unreviewed_papers', 0)}")

    if validations.get("duplicate_submission_ids"):
        print(f"Duplicates: {validations['duplicate_submission_ids']}")
    if validations.get("missing_submission_ids"):
        print(f"Missing papers: {validations['missing_submission_ids']}")

    if args.publish:
        public_show_rooms = (
            args.public_rooms
            if args.public_rooms is not None
            else args.publish_display == PUBLISH_DISPLAY_FULL
        )
        public_show_moderators = (
            args.public_moderators
            if args.public_moderators is not None
            else args.publish_display == PUBLISH_DISPLAY_FULL
        )
        public_show_links = True
        if args.public_links is not None:
            public_show_links = bool(args.public_links)
        if args.hide_public_links:
            public_show_links = False

        print(f"Publish display mode: {args.publish_display}")
        print(
            "Public export settings: "
            f"rooms={'shown' if public_show_rooms else 'hidden'}, "
            f"moderators={'shown' if public_show_moderators else 'hidden'}, "
            f"links={'shown' if public_show_links else 'hidden'}"
        )
        public_json_path = export_public_payload(
            state,
            public_json_output,
            conference_config=conference_config,
            show_rooms=public_show_rooms,
            show_moderators=public_show_moderators,
            show_links=public_show_links,
        )
        print(f"Generated public JSON: {public_json_path}")
        public_xlsx_path = export_public_excel(
            state,
            public_xlsx_output,
            conference_config=conference_config,
            show_rooms=public_show_rooms,
            show_moderators=public_show_moderators,
            show_links=public_show_links,
        )
        print(f"Generated public workbook: {public_xlsx_path}")
        xlsx_path = export_publish_excel(
            state,
            publish_xlsx_output,
            publish_display=args.publish_display,
            show_links=public_show_links,
        )
        print(f"Generated publish workbook: {xlsx_path}")
        try:
            docx_path = export_publish_docx(state, publish_docx_output, publish_display=args.publish_display)
            print(f"Generated publish Word: {docx_path}")
        except RuntimeError as exc:
            print(f"Publish Word skipped: {exc}")
        try:
            pdf_path = export_publish_pdf(state, publish_pdf_output, publish_display=args.publish_display)
            print(f"Generated publish PDF: {pdf_path}")
        except RuntimeError as exc:
            print(f"Publish PDF skipped: {exc}")


if __name__ == "__main__":
    main()
