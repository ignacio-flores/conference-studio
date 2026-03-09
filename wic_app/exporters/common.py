from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from reclassification_engine import ProgrammeState, parse_start_minutes, room_sort_key


def group_sessions_by_day_block(state: ProgrammeState) -> Dict[str, Dict[Tuple[int, str, str], Dict[str, object]]]:
    out: Dict[str, Dict[Tuple[int, str, str], Dict[str, object]]] = defaultdict(dict)
    for session in state.sessions:
        key = (session.block_num, session.time, session.block_label)
        out[session.day_label][key] = out[session.day_label].get(key, {})
        out[session.day_label][key][session.room] = session
    return out


def paper_row_lookup(state: ProgrammeState) -> Dict[str, int]:
    sorted_papers = sorted(state.papers, key=lambda p: p.submission_id)
    return {p.submission_id: idx + 1 for idx, p in enumerate(sorted_papers)}


def ordered_sessions(state: ProgrammeState) -> List[object]:
    return sorted(
        state.sessions,
        key=lambda s: (s.day_num, int(getattr(s, "start_min", parse_start_minutes(s.time))), room_sort_key(s.room)),
    )
