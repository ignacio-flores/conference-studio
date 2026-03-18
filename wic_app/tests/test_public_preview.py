from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from preview_public_bundle import PUBLIC_PREVIEW_PORT, ensure_public_bundle_preview


class PublicPreviewTests(unittest.TestCase):
    def test_ensure_public_bundle_preview_starts_server_when_port_is_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "public_bundle"
            app_path = bundle_dir / "wic_app" / "public_app.py"
            app_path.parent.mkdir(parents=True, exist_ok=True)
            app_path.write_text("print('ok')\n", encoding="utf-8")

            with mock.patch("preview_public_bundle._is_local_port_open", return_value=False), mock.patch(
                "preview_public_bundle.subprocess.Popen"
            ) as popen_mock:
                result = ensure_public_bundle_preview(bundle_dir=bundle_dir)

            self.assertTrue(result["started"])
            self.assertEqual(result["port"], PUBLIC_PREVIEW_PORT)
            self.assertEqual(result["url"], f"http://127.0.0.1:{PUBLIC_PREVIEW_PORT}")
            popen_mock.assert_called_once()

    def test_ensure_public_bundle_preview_reuses_server_when_port_is_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "public_bundle"
            app_path = bundle_dir / "wic_app" / "public_app.py"
            app_path.parent.mkdir(parents=True, exist_ok=True)
            app_path.write_text("print('ok')\n", encoding="utf-8")

            with mock.patch("preview_public_bundle._is_local_port_open", return_value=True), mock.patch(
                "preview_public_bundle.subprocess.Popen"
            ) as popen_mock:
                result = ensure_public_bundle_preview(bundle_dir=bundle_dir)

            self.assertFalse(result["started"])
            self.assertEqual(result["url"], f"http://127.0.0.1:{PUBLIC_PREVIEW_PORT}")
            popen_mock.assert_not_called()

    def test_ensure_public_bundle_preview_requires_bundle_app(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "public_bundle"
            with self.assertRaises(FileNotFoundError):
                ensure_public_bundle_preview(bundle_dir=bundle_dir)


if __name__ == "__main__":
    unittest.main()
