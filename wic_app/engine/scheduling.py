from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple


def _parse_positive_int(raw: str, default: int = 0) -> int:
    try:
        value = int(str(raw).strip())
        return value if value > 0 else default
    except Exception:
        return default


def build_equal_time_ranges(start_min: int, end_min: int, slots: int) -> List[Tuple[int, int]]:
    if slots <= 0:
        return []
    if end_min <= start_min:
        end_min = start_min + 90
    total = end_min - start_min
    base = total // slots
    remainder = total % slots
    ranges: List[Tuple[int, int]] = []
    cursor = start_min
    for idx in range(slots):
        length = base + (1 if idx < remainder else 0)
        next_cursor = cursor + max(1, length)
        ranges.append((cursor, next_cursor))
        cursor = next_cursor
    if ranges:
        ranges[-1] = (ranges[-1][0], end_min)
    return ranges


def apply_paper_placements(
    papers: List[object],
    sessions: List[object],
    placements: Dict[str, Dict[str, str]],
) -> Tuple[List[object], List[Dict[str, str]]]:
    paper_map = {p.submission_id: p for p in papers}
    session_map = {
        getattr(s, "session_id", ""): s
        for s in sessions
        if str(getattr(s, "status", "active")).strip().lower() == "active"
    }

    slot_map: Dict[Tuple[str, int], Optional[str]] = {}
    paper_place: Dict[str, Tuple[str, str, int]] = {}
    overflow_map: Dict[str, List[Tuple[int, str]]] = defaultdict(list)
    unassigned_ids: set[str] = set()
    slot_conflicts: List[Dict[str, str]] = []

    for session in session_map.values():
        capacity = max(1, int(getattr(session, "capacity", len(getattr(session, "papers", [])) or 4)))
        session.papers = [None] * capacity
        session.overflow_papers = []
        for idx in range(1, capacity + 1):
            slot_map[(session.session_id, idx)] = None

    def detach(sid: str) -> None:
        current = paper_place.get(sid)
        if not current:
            return
        status, session_id, position = current
        if status == "scheduled":
            slot_map[(session_id, position)] = None
        elif status == "overflow":
            overflow_map[session_id] = [
                (o, existing_sid)
                for o, existing_sid in overflow_map.get(session_id, [])
                if existing_sid != sid
            ]
        elif status == "unassigned":
            unassigned_ids.discard(sid)
        paper_place.pop(sid, None)

    for sid, row in placements.items():
        if sid not in paper_map:
            continue

        status = str(row.get("PlacementStatus", "")).strip().lower()
        target_session_id = str(row.get("SessionId", "")).strip()
        talk_index = _parse_positive_int(row.get("TalkIndex", ""), default=0)
        overflow_order = _parse_positive_int(row.get("OverflowOrder", ""), default=9999)

        detach(sid)

        if status == "unassigned":
            unassigned_ids.add(sid)
            paper_place[sid] = ("unassigned", "", 0)
            continue

        if status == "scheduled":
            target_session = session_map.get(target_session_id)
            target_capacity = 0 if target_session is None else int(getattr(target_session, "capacity", 4))
            if target_session is None or talk_index < 1:
                unassigned_ids.add(sid)
                paper_place[sid] = ("unassigned", "", 0)
                continue
            if talk_index > target_capacity:
                normalized_overflow_order = overflow_order if overflow_order > 0 else talk_index - target_capacity
                overflow_map[target_session_id].append((normalized_overflow_order, sid))
                paper_place[sid] = ("overflow", target_session_id, normalized_overflow_order)
                slot_conflicts.append(
                    {
                        "SubmissionID": sid,
                        "SessionCode": str(getattr(target_session, "session_code", "")),
                        "TalkIndex": str(talk_index),
                        "Reason": (
                            f"TalkIndex {talk_index} exceeds session capacity {target_capacity}; "
                            "paper moved to overflow."
                        ),
                    }
                )
                continue
            key = (target_session_id, talk_index)
            occupant_sid = slot_map.get(key)
            if occupant_sid is None:
                slot_map[key] = sid
                paper_place[sid] = ("scheduled", target_session_id, talk_index)
            else:
                overflow_map[target_session_id].append((overflow_order, sid))
                paper_place[sid] = ("overflow", target_session_id, overflow_order)
                slot_conflicts.append(
                    {
                        "SubmissionID": sid,
                        "SessionCode": str(getattr(target_session, "session_code", "")),
                        "TalkIndex": str(talk_index),
                        "Reason": f"Target slot occupied by {occupant_sid}; moved to overflow.",
                    }
                )
            continue

        if status == "overflow":
            if target_session_id not in session_map:
                unassigned_ids.add(sid)
                paper_place[sid] = ("unassigned", "", 0)
                continue
            overflow_map[target_session_id].append((overflow_order, sid))
            paper_place[sid] = ("overflow", target_session_id, overflow_order)
            continue

        unassigned_ids.add(sid)
        paper_place[sid] = ("unassigned", "", 0)

    for session_id, session in session_map.items():
        capacity = max(1, int(getattr(session, "capacity", len(getattr(session, "papers", [])) or 4)))
        slot_ranges = build_equal_time_ranges(
            int(getattr(session, "start_min", 0) or 0),
            int(getattr(session, "end_min", 0) or 0),
            capacity,
        )
        rebuilt_slots: List[Optional[object]] = []
        for idx in range(1, capacity + 1):
            sid = slot_map.get((session_id, idx))
            paper = paper_map.get(sid) if sid else None
            rebuilt_slots.append(paper)
            if paper is not None:
                paper.placement_status = "scheduled"
                paper.session_code = session.session_code
                paper.session_title = session.session_title
                paper.session_id = session_id
                paper.day_label = session.day_label
                paper.day_num = session.day_num
                paper.block_label = session.block_label
                paper.block_num = session.block_num
                paper.time = session.time
                paper.room = session.room
                paper.talk_index = idx
                paper.overflow_order = 0
                if idx - 1 < len(slot_ranges):
                    paper.talk_start_min = slot_ranges[idx - 1][0]
                    paper.talk_end_min = slot_ranges[idx - 1][1]
                else:
                    paper.talk_start_min = 0
                    paper.talk_end_min = 0
        session.papers = rebuilt_slots

        ordered_overflow = sorted(
            overflow_map.get(session_id, []),
            key=lambda x: (x[0], paper_map[x[1]].title.lower()),
        )
        session.overflow_papers = []
        for rank, (_, sid) in enumerate(ordered_overflow, start=1):
            paper = paper_map[sid]
            paper.placement_status = "overflow"
            paper.session_code = session.session_code
            paper.session_title = session.session_title
            paper.session_id = session_id
            paper.day_label = session.day_label
            paper.day_num = session.day_num
            paper.block_label = session.block_label
            paper.block_num = session.block_num
            paper.time = session.time
            paper.room = session.room
            paper.talk_index = 0
            paper.overflow_order = rank
            paper.talk_start_min = 0
            paper.talk_end_min = 0
            session.overflow_papers.append(paper)

    for sid in unassigned_ids:
        paper = paper_map[sid]
        paper.placement_status = "unassigned"
        paper.session_id = ""
        paper.session_code = ""
        paper.session_title = ""
        paper.day_label = ""
        paper.day_num = 0
        paper.block_label = ""
        paper.block_num = 0
        paper.time = ""
        paper.room = ""
        paper.talk_index = 0
        paper.overflow_order = 0
        paper.talk_start_min = 0
        paper.talk_end_min = 0

    for paper in papers:
        if paper.submission_id in unassigned_ids:
            continue
        if paper.placement_status == "overflow":
            continue
        if paper.session_code:
            paper.placement_status = "scheduled"
        else:
            paper.placement_status = "unassigned"

    unassigned_papers = sorted(
        [paper_map[sid] for sid in unassigned_ids if sid in paper_map],
        key=lambda p: p.title.lower(),
    )
    return unassigned_papers, slot_conflicts


def apply_programme_layout_overrides(
    papers: List[object],
    sessions: List[object],
    overrides: Dict[str, Dict[str, str]],
) -> Tuple[List[object], List[Dict[str, str]]]:
    code_to_id: Dict[str, str] = {}
    for session in sessions:
        session_id = str(getattr(session, "session_id", "")).strip()
        session_code = str(getattr(session, "session_code", "")).strip()
        if session_id and session_code:
            code_to_id[session_code] = session_id

    placements: Dict[str, Dict[str, str]] = {}

    # Seed with current placement state so partial override payloads preserve
    # existing scheduled occupants and can still report target slot conflicts.
    for paper in papers:
        sid = str(getattr(paper, "submission_id", "")).strip()
        if not sid:
            continue
        status = str(getattr(paper, "placement_status", "")).strip().lower()
        if status not in {"scheduled", "overflow", "unassigned"}:
            status = "unassigned"
        placements[sid] = {
            "SubmissionID": sid,
            "PlacementStatus": status,
            "SessionId": str(getattr(paper, "session_id", "")).strip(),
            "TalkIndex": str(getattr(paper, "talk_index", "")).strip(),
            "OverflowOrder": str(getattr(paper, "overflow_order", "")).strip(),
        }

    for sid, row in overrides.items():
        session_code = str(row.get("SessionCode", "")).strip()
        session_id = code_to_id.get(session_code, "")
        placements[sid] = {
            "SubmissionID": sid,
            "PlacementStatus": str(row.get("PlacementStatus", "")).strip(),
            "SessionId": session_id,
            "TalkIndex": str(row.get("TalkIndex", "")).strip(),
            "OverflowOrder": str(row.get("OverflowOrder", "")).strip(),
        }

    return apply_paper_placements(papers, sessions, placements)
