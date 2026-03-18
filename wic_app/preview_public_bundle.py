from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

from bundle_public_app import PUBLIC_BUNDLE_DIR


PUBLIC_PREVIEW_HOST = "127.0.0.1"
PUBLIC_PREVIEW_PORT = 8510


def _preview_url(port: int = PUBLIC_PREVIEW_PORT) -> str:
    return f"http://{PUBLIC_PREVIEW_HOST}:{int(port)}"


def _is_local_port_open(port: int, host: str = PUBLIC_PREVIEW_HOST) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=0.25):
            return True
    except OSError:
        return False


def ensure_public_bundle_preview(bundle_dir: Path = PUBLIC_BUNDLE_DIR, port: int = PUBLIC_PREVIEW_PORT) -> dict:
    bundle_dir = Path(bundle_dir).resolve()
    app_path = bundle_dir / "wic_app" / "public_app.py"
    if not app_path.exists():
        raise FileNotFoundError(app_path)

    url = _preview_url(port)
    if _is_local_port_open(port):
        return {"url": url, "port": int(port), "started": False, "bundle_path": bundle_dir}

    env = dict(os.environ)
    env["PUBLIC_ENABLED"] = "true"
    env.setdefault("PYTHONUNBUFFERED", "1")

    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
            f"--server.address={PUBLIC_PREVIEW_HOST}",
            f"--server.port={int(port)}",
        ],
        cwd=str(bundle_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return {"url": url, "port": int(port), "started": True, "bundle_path": bundle_dir}
