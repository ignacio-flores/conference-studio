from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from engine.config import load_conference_config
from public_data import build_public_payload, write_public_payload


def _paper(
    submission_id: str,
    *,
    session_id: str,
    session_code: str,
    session_title: str,
    day_label: str,
    day_num: int,
    time: str,
    block_label: str,
    block_num: int,
    room: str,
    placement_status: str = "scheduled",
) -> SimpleNamespace:
    return SimpleNamespace(
        submission_id=submission_id,
        full_name=f"Author {submission_id}",
        email=f"{submission_id.lower()}@example.com",
        reviewer_score="1",
        source_themes="Source theme",
        title=f"Title {submission_id}",
        abstract=f"Abstract {submission_id}",
        link_to_pdf=f"https://private.example/{submission_id}.pdf",
        primary_theme="Theme A",
        detailed_subtheme="Subtheme A",
        secondary_tags=["Tag 1"],
        rationale="Internal rationale",
        override_notes="Internal note",
        reviewed=True,
        session_id=session_id,
        session_code=session_code,
        session_title=session_title,
        day_label=day_label,
        day_num=day_num,
        block_label=block_label,
        block_num=block_num,
        time=time,
        room=room,
        talk_index=1,
        talk_start_min=600,
        talk_end_min=630,
        placement_status=placement_status,
        overflow_order=0,
    )


def _session(
    session_id: str,
    *,
    status: str,
    paper: SimpleNamespace | None,
    day_label: str,
    day_num: int,
    time: str,
    block_label: str,
    block_num: int,
    room: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        session_id=session_id,
        session_code=f"D{day_num}-B{block_num}-{room}",
        status=status,
        day_label=day_label,
        day_num=day_num,
        time=time,
        block_label=block_label,
        block_num=block_num,
        room=room,
        start_min=600,
        end_min=660,
        capacity=1,
        source="test",
        session_title=f"Session {session_id}",
        primary_theme="Theme A",
        subtheme="Subtheme A",
        papers=[paper],
        overflow_papers=[],
    )


class PublicDataTests(unittest.TestCase):
    def test_build_public_payload_excludes_private_archived_and_inactive_content(self) -> None:
        conference = load_conference_config()
        active_paper = _paper(
            "P1",
            session_id="S1",
            session_code="D1-B1-R1",
            session_title="Session S1",
            day_label="Day 1",
            day_num=1,
            time="10h00-11h00",
            block_label="SESSION 1",
            block_num=1,
            room="R1",
        )
        inactive_paper = _paper(
            "P2",
            session_id="S2",
            session_code="D1-B1-R2",
            session_title="Session S2",
            day_label="Day 1",
            day_num=1,
            time="10h00-11h00",
            block_label="SESSION 1",
            block_num=1,
            room="R2",
        )
        archived_paper = _paper(
            "P3",
            session_id="",
            session_code="",
            session_title="",
            day_label="",
            day_num=0,
            time="",
            block_label="",
            block_num=0,
            room="",
            placement_status="unassigned",
        )
        active_session = _session(
            "S1",
            status="active",
            paper=active_paper,
            day_label="Day 1",
            day_num=1,
            time="10h00-11h00",
            block_label="SESSION 1",
            block_num=1,
            room="R1",
        )
        inactive_session = _session(
            "S2",
            status="inactive",
            paper=inactive_paper,
            day_label="Day 1",
            day_num=1,
            time="10h00-11h00",
            block_label="SESSION 1",
            block_num=1,
            room="R2",
        )
        state = SimpleNamespace(
            papers=[active_paper, inactive_paper],
            sessions=[active_session],
            inactive_sessions=[inactive_session],
            archived_papers=[archived_paper],
            validations={},
            unassigned_papers=[],
            slot_conflicts=[],
            edited_submission_ids=set(),
        )

        payload = build_public_payload(state, conference, generated_at="2026-03-18T12:00:00")

        self.assertEqual(payload["conference"]["generated_at"], "2026-03-18T12:00:00")
        self.assertEqual([session["session_id"] for session in payload["sessions"]], ["S1"])
        self.assertEqual([paper["submission_id"] for paper in payload["papers"]], ["P1"])
        self.assertEqual(payload["filters"]["rooms"], ["R1"])

        session_talk = payload["sessions"][0]["talks"][0]
        self.assertEqual(session_talk["submission_id"], "P1")
        for forbidden_key in ("email", "reviewer_score", "link_to_pdf", "override_notes", "rationale"):
            self.assertNotIn(forbidden_key, session_talk)
            self.assertNotIn(forbidden_key, payload["papers"][0])

    def test_write_public_payload_persists_json_snapshot(self) -> None:
        payload = {
            "conference": {
                "title": "Test Conference",
                "subtitle": "Public Programme",
                "generated_at": "2026-03-18T12:00:00",
            },
            "sessions": [],
            "papers": [],
            "filters": {"days": [], "rooms": [], "themes": [], "subthemes": []},
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "programme.json"
            returned_path = write_public_payload(payload, output_path)

            self.assertEqual(returned_path, output_path)
            self.assertTrue(output_path.exists())
            loaded = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["conference"]["title"], "Test Conference")


if __name__ == "__main__":
    unittest.main()
