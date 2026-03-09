from __future__ import annotations

import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path


def _find_free_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    except PermissionError as exc:
        raise RuntimeError("socket bind not permitted in this environment") from exc


class AppStartupSmokeTests(unittest.TestCase):
    def test_streamlit_startup_has_no_traceback(self) -> None:
        try:
            import streamlit  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("streamlit is not installed in this environment")

        repo_root = Path(__file__).resolve().parents[2]
        app_path = repo_root / "wic_app" / "app.py"
        config_path = repo_root / "wic_app" / "assets" / "conference.default.json"
        try:
            port = _find_free_port()
        except RuntimeError as exc:
            self.skipTest(str(exc))

        cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
            f"--server.port={port}",
        ]
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["WIC_CONFERENCE_CONFIG"] = str(config_path)

        output = ""
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(repo_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=12,
            )
            output = (completed.stdout or "") + (completed.stderr or "")
            if completed.returncode != 0:
                if "Operation not permitted" in output:
                    self.skipTest("network/socket operations are not permitted in this environment")
                self.fail(f"Streamlit app exited with code {completed.returncode}.\n{output[-3000:]}")
        except subprocess.TimeoutExpired as exc:
            # Healthy startup is expected to still be running; timeout is acceptable.
            output = (exc.stdout or "") + (exc.stderr or "")

        self.assertNotIn("Traceback", output)
        self.assertNotIn("NameError", output)


if __name__ == "__main__":
    unittest.main()
