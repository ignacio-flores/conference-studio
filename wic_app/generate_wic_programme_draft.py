#!/usr/bin/env python3
"""Generate WIC 2026 draft and publish outputs from current overrides.

Usage:
    python3 generate_wic_programme_draft.py
    python3 generate_wic_programme_draft.py --publish
"""

from __future__ import annotations

import argparse

from exporters.publish import export_draft_workbook, export_publish_excel, export_publish_pdf
from reclassification_engine import (
    DRAFT_OUTPUT_FILE,
    PUBLISH_PDF_FILE,
    PUBLISH_XLSX_FILE,
    build_programme_state,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also generate publish Excel and PDF outputs.",
    )
    args = parser.parse_args()

    state = build_programme_state()
    validations = state.validations

    draft_path = export_draft_workbook(state, DRAFT_OUTPUT_FILE)
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
        xlsx_path = export_publish_excel(state, PUBLISH_XLSX_FILE)
        print(f"Generated publish workbook: {xlsx_path}")
        try:
            pdf_path = export_publish_pdf(state, PUBLISH_PDF_FILE)
            print(f"Generated publish PDF: {pdf_path}")
        except RuntimeError as exc:
            print(f"Publish PDF skipped: {exc}")


if __name__ == "__main__":
    main()
