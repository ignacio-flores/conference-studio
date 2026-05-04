from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from bundle_public_app import PUBLIC_BUNDLE_DIR, assemble_public_bundle
from reclassification_engine import build_programme_state


class PublicBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        def _write_fake_pdf(_state, output_path: Path, **_kwargs) -> Path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"%PDF-FAKE")
            return output_path

        self._pdf_export_patch = patch("bundle_public_app.export_publish_pdf", side_effect=_write_fake_pdf)
        self.pdf_export_mock = self._pdf_export_patch.start()
        self.addCleanup(self._pdf_export_patch.stop)

    def _zip_text(self, archive_path: Path, suffixes: tuple[str, ...]) -> str:
        with zipfile.ZipFile(archive_path) as archive:
            return "\n".join(
                archive.read(name).decode("utf-8", errors="ignore")
                for name in archive.namelist()
                if name.endswith(suffixes)
            )

    def test_assemble_public_bundle_creates_static_www_files(self) -> None:
        state = build_programme_state()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle_path = assemble_public_bundle(state, output_dir=tmp_path / "public_bundle")

            self.assertEqual(bundle_path, tmp_path / "public_bundle")
            self.assertTrue((bundle_path / "www" / "index.html").exists())
            self.assertTrue((bundle_path / "www" / "assets" / "styles.css").exists())
            self.assertTrue((bundle_path / "www" / "assets" / "app.js").exists())
            self.assertTrue((bundle_path / "www" / "assets" / "logos" / "WIC-logo.png").exists())
            self.assertTrue((bundle_path / "www" / "assets" / "logos" / "Logos-partners-768x414.png").exists())
            self.assertTrue((bundle_path / "www" / "data" / "programme.json").exists())
            self.assertTrue((bundle_path / "www" / "programme.xlsx").exists())
            self.assertTrue((bundle_path / "www" / "programme.pdf").exists())
            self.assertTrue((bundle_path / "README.md").exists())
            self.assertFalse((bundle_path / "wic_app" / "public_app.py").exists())
            self.assertFalse((bundle_path / "wic_app" / "public_data.py").exists())
            self.assertFalse((bundle_path / "public_data").exists())
            self.assertFalse((bundle_path / "requirements.txt").exists())
            self.assertFalse((bundle_path / "source_data").exists())
            self.assertFalse((bundle_path / "exports").exists())
            self.assertFalse((bundle_path / "wic_app" / "state").exists())

    def test_bundle_readme_references_static_www_deployment(self) -> None:
        state = build_programme_state()
        with tempfile.TemporaryDirectory() as tmp:
            bundle_path = assemble_public_bundle(state, output_dir=Path(tmp) / "public_bundle")
            readme_text = (bundle_path / "README.md").read_text(encoding="utf-8")

        self.assertIn("www/", readme_text)
        self.assertIn("static", readme_text.lower())
        self.assertIn("programme.pdf", readme_text)
        self.assertNotIn("streamlit run", readme_text)

    def test_public_bundle_threads_public_visibility_settings_into_payload(self) -> None:
        state = build_programme_state()
        with tempfile.TemporaryDirectory() as tmp:
            bundle_path = assemble_public_bundle(
                state,
                output_dir=Path(tmp) / "public_bundle",
                publish_display="public_safe",
                show_links=False,
            )
            payload = json.loads((bundle_path / "www" / "data" / "programme.json").read_text(encoding="utf-8"))
            workbook_xml = self._zip_text(bundle_path / "www" / "programme.xlsx", (".xml", ".rels"))
            visible_text_xml = self._zip_text(bundle_path / "www" / "programme.xlsx", ("sharedStrings.xml",))

        self.assertEqual(
            payload["public_settings"],
            {
                "publish_display": "public_safe",
                "show_rooms": False,
                "show_moderators": False,
                "show_links": False,
            },
        )
        self.assertTrue(all(str(session.get("display_room", "")).startswith("Track ") for session in payload["sessions"]))
        self.assertTrue(all("link_to_pdf" not in paper for paper in payload["papers"]))
        self.assertTrue(all(not str(paper.get("paper_url", "")).strip() for paper in payload["papers"]))
        self.assertNotIn("Session Directory", workbook_xml)
        self.assertNotIn("Paper Index", workbook_xml)
        self.assertNotIn("Issues", workbook_xml)
        self.assertNotIn("Title Presenter Index", workbook_xml)
        self.assertIn("Track 1", visible_text_xml)
        self.assertNotIn("PaperURL", visible_text_xml)
        self.pdf_export_mock.assert_any_call(
            state,
            bundle_path / "www" / "programme.pdf",
            publish_display="public_safe",
        )

    def test_public_bundle_download_workbook_uses_publish_workbook_and_can_show_links(self) -> None:
        state = build_programme_state()
        with tempfile.TemporaryDirectory() as tmp:
            bundle_path = assemble_public_bundle(
                state,
                output_dir=Path(tmp) / "public_bundle",
                publish_display="full",
                show_links=True,
            )
            workbook_xml = self._zip_text(bundle_path / "www" / "programme.xlsx", (".xml", ".rels"))
            visible_text_xml = self._zip_text(bundle_path / "www" / "programme.xlsx", ("sharedStrings.xml",))

        self.assertNotIn("Session Directory", workbook_xml)
        self.assertNotIn("Paper Index", workbook_xml)
        self.assertNotIn("Issues", workbook_xml)
        self.assertNotIn("PaperURL", visible_text_xml)

    def test_public_bundle_payload_omits_removed_blank_paper_url(self) -> None:
        state = build_programme_state()
        target = next(
            paper
            for session in state.sessions
            for paper in (
                list(getattr(session, "papers", []) or [])
                + list(getattr(session, "overflow_papers", []) or [])
            )
            if paper is not None and str(getattr(paper, "link_to_pdf", "")).strip()
        )
        target_id = target.submission_id
        original_url = target.link_to_pdf
        target.link_to_pdf = ""

        with tempfile.TemporaryDirectory() as tmp:
            bundle_path = assemble_public_bundle(
                state,
                output_dir=Path(tmp) / "public_bundle",
                show_links=True,
            )
            payload = json.loads((bundle_path / "www" / "data" / "programme.json").read_text(encoding="utf-8"))
            workbook_xml = self._zip_text(bundle_path / "www" / "programme.xlsx", (".xml", ".rels"))

        record = next(paper for paper in payload["papers"] if paper["submission_id"] == target_id)
        self.assertEqual(record["paper_url"], "")
        self.assertNotIn(original_url, json.dumps(payload))
        self.assertNotIn(original_url, workbook_xml)

    def test_public_bundle_default_path_is_repo_local(self) -> None:
        expected = APP_ROOT.parent / "public_bundle"
        self.assertEqual(PUBLIC_BUNDLE_DIR, expected)


if __name__ == "__main__":
    unittest.main()
