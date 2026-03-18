from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from bundle_public_app import PUBLIC_BUNDLE_DIR, assemble_public_bundle
from reclassification_engine import build_programme_state


def _find_free_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    except PermissionError as exc:
        raise RuntimeError("socket bind not permitted in this environment") from exc


class PublicBundleTests(unittest.TestCase):
    def test_assemble_public_bundle_creates_self_contained_files(self) -> None:
        state = build_programme_state()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle_path = assemble_public_bundle(state, output_dir=tmp_path / "public_bundle")

            self.assertEqual(bundle_path, tmp_path / "public_bundle")
            self.assertTrue((bundle_path / "wic_app" / "public_app.py").exists())
            self.assertTrue((bundle_path / "wic_app" / "public_data.py").exists())
            self.assertTrue((bundle_path / "public_data" / "programme.json").exists())
            self.assertTrue((bundle_path / "public_data" / "programme.xlsx").exists())
            self.assertTrue((bundle_path / "requirements.txt").exists())
            self.assertTrue((bundle_path / "README.md").exists())
            self.assertFalse((bundle_path / "source_data").exists())
            self.assertFalse((bundle_path / "exports").exists())
            self.assertFalse((bundle_path / "wic_app" / "state").exists())

    def test_bundle_public_app_starts_in_isolation(self) -> None:
        try:
            import streamlit  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("streamlit is not installed in this environment")

        try:
            port = _find_free_port()
        except RuntimeError as exc:
            self.skipTest(str(exc))

        state = build_programme_state()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bundle_path = assemble_public_bundle(state, output_dir=tmp_path / "public_bundle")
            cmd = [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(bundle_path / "wic_app" / "public_app.py"),
                "--server.headless=true",
                "--browser.gatherUsageStats=false",
                f"--server.port={port}",
            ]
            env = dict(os.environ)
            env["PYTHONUNBUFFERED"] = "1"
            env["PUBLIC_ENABLED"] = "true"

            output = ""
            try:
                completed = subprocess.run(
                    cmd,
                    cwd=str(bundle_path),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=12,
                )
                output = (completed.stdout or "") + (completed.stderr or "")
                if completed.returncode != 0:
                    if "Operation not permitted" in output:
                        self.skipTest("network/socket operations are not permitted in this environment")
                    self.fail(f"Bundle app exited with code {completed.returncode}.\n{output[-3000:]}")
            except subprocess.TimeoutExpired as exc:
                output = (exc.stdout or "") + (exc.stderr or "")

            self.assertNotIn("Traceback", output)
            self.assertNotIn("ModuleNotFoundError", output)

    def test_public_bundle_default_path_is_repo_local(self) -> None:
        expected = APP_ROOT.parent / "public_bundle"
        self.assertEqual(PUBLIC_BUNDLE_DIR, expected)


if __name__ == "__main__":
    unittest.main()
