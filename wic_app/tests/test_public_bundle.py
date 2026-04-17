from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from bundle_public_app import PUBLIC_BUNDLE_DIR, assemble_public_bundle
from reclassification_engine import build_programme_state


class PublicBundleTests(unittest.TestCase):
    def test_assemble_public_bundle_creates_static_www_files(self) -> None:
        state = build_programme_state()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle_path = assemble_public_bundle(state, output_dir=tmp_path / "public_bundle")

            self.assertEqual(bundle_path, tmp_path / "public_bundle")
            self.assertTrue((bundle_path / "www" / "index.html").exists())
            self.assertTrue((bundle_path / "www" / "assets" / "styles.css").exists())
            self.assertTrue((bundle_path / "www" / "assets" / "app.js").exists())
            self.assertTrue((bundle_path / "www" / "data" / "programme.json").exists())
            self.assertTrue((bundle_path / "www" / "programme.xlsx").exists())
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
        self.assertNotIn("streamlit run", readme_text)

    def test_public_bundle_default_path_is_repo_local(self) -> None:
        expected = APP_ROOT.parent / "public_bundle"
        self.assertEqual(PUBLIC_BUNDLE_DIR, expected)


if __name__ == "__main__":
    unittest.main()
