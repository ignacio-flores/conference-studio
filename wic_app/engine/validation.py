from __future__ import annotations

from collections import Counter
from typing import Dict

from engine.config import ConferenceConfig


def validate_programme_state(
    state,
    config: ConferenceConfig,
) -> Dict[str, object]:
    papers = state.papers
    sessions = list(getattr(state, "sessions", []))
    inactive_sessions = list(getattr(state, "inactive_sessions", []))

    scheduled_ids = []
    overflow_ids = []
    overflow_by_session: Dict[str, list[str]] = {}
    incomplete_sessions: list[str] = []
    session_capacity_mismatch: list[str] = []

    for session in sessions:
        capacity = max(1, int(getattr(session, "capacity", len(getattr(session, "papers", [])) or 4)))
        if len(session.papers) != capacity:
            session_capacity_mismatch.append(str(session.session_code))
        for paper in session.papers:
            if paper is not None:
                scheduled_ids.append(paper.submission_id)
        if session.overflow_papers:
            overflow_by_session[session.session_code] = [p.submission_id for p in session.overflow_papers]
            overflow_ids.extend(overflow_by_session[session.session_code])
        if sum(1 for paper in session.papers if paper is not None) < capacity:
            incomplete_sessions.append(str(session.session_code))

    unassigned_ids = [paper.submission_id for paper in state.unassigned_papers]
    accounted_ids = scheduled_ids + overflow_ids + unassigned_ids
    id_counts = Counter(accounted_ids)
    duplicates = sorted([sid for sid, count in id_counts.items() if count > 1])

    all_ids = sorted([p.submission_id for p in papers])
    assigned_set = set(accounted_ids)
    missing = sorted([sid for sid in all_ids if sid not in assigned_set])

    reserve_slots = sum(1 for session in sessions for paper in session.papers if paper is None)
    forbidden_window_assigned = []
    for session in sessions:
        if any(
            window.day_num == session.day_num and window.time_label.strip() == session.time.strip()
            for window in config.validation.forbidden_time_windows
        ):
            forbidden_window_assigned.append(session.session_code)

    forbidden_tokens = [token.upper() for token in config.validation.forbidden_block_tokens]
    forbidden_block_sessions = []
    for session in sessions:
        block_upper = session.block_label.upper()
        if any(token and token in block_upper for token in forbidden_tokens):
            forbidden_block_sessions.append(session.session_code)

    duplicate_session_codes: list[str] = []
    duplicate_session_slots: list[str] = []
    code_counts = Counter([str(session.session_code) for session in sessions if str(session.session_code).strip()])
    duplicate_session_codes = sorted([code for code, count in code_counts.items() if count > 1])
    slot_counts = Counter([f"{session.day_num}|{session.time}|{session.room}" for session in sessions])
    duplicate_session_slots = sorted([slot for slot, count in slot_counts.items() if count > 1])

    reviewed_count = sum(1 for p in papers if p.reviewed)
    over_capacity_sessions = sorted([code for code, values in overflow_by_session.items() if values])

    validations = {
        "accepted_papers": len(papers),
        "sessions": len(sessions),
        "inactive_sessions": len(inactive_sessions),
        "assigned_papers": len(scheduled_ids),
        "scheduled_papers": len(scheduled_ids),
        "overflow_papers": len(overflow_ids),
        "unassigned_papers": len(unassigned_ids),
        "accounted_papers": len(accounted_ids),
        "duplicate_submission_ids": duplicates,
        "missing_submission_ids": missing,
        "unassigned_submission_ids": sorted(unassigned_ids),
        "overflow_submission_ids": sorted(overflow_ids),
        "overflow_by_session": overflow_by_session,
        "over_capacity_sessions": over_capacity_sessions,
        "slot_conflicts": list(state.slot_conflicts),
        "reserve_slots": reserve_slots,
        "day1_opening_assigned_sessions": forbidden_window_assigned,
        "optional_block_assigned_sessions": forbidden_block_sessions,
        "incomplete_sessions": sorted(incomplete_sessions),
        "session_capacity_mismatch": session_capacity_mismatch,
        "duplicate_session_codes": duplicate_session_codes,
        "duplicate_session_slots": duplicate_session_slots,
        "reviewed_papers": reviewed_count,
        "unreviewed_papers": len(papers) - reviewed_count,
    }

    hard_constraints_ok = len(forbidden_window_assigned) == 0 and len(forbidden_block_sessions) == 0
    if config.validation.strict_expected_slots:
        hard_constraints_ok = hard_constraints_ok and (len(sessions) == config.validation.expected_slots)
    if config.structure.enforce_unique_session_code:
        hard_constraints_ok = hard_constraints_ok and (len(duplicate_session_codes) == 0)
    if not config.structure.allow_duplicate_day_time_room:
        hard_constraints_ok = hard_constraints_ok and (len(duplicate_session_slots) == 0)
    hard_constraints_ok = hard_constraints_ok and (len(session_capacity_mismatch) == 0)

    planning_issues_present = (
        len(duplicates) == 0
        and len(missing) == 0
        and len(unassigned_ids) == 0
        and len(overflow_ids) == 0
        and len(state.slot_conflicts) == 0
    )
    if config.validation.strict_expected_reserve_slots:
        planning_issues_present = planning_issues_present and (reserve_slots == config.validation.expected_reserve_slots)

    validations["hard_constraints_ok"] = hard_constraints_ok
    validations["is_valid"] = hard_constraints_ok and planning_issues_present
    validations["has_planning_issues"] = not planning_issues_present

    return validations
