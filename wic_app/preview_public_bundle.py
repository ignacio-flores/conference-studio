from __future__ import annotations

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
    app_path = bundle_dir / "www" / "index.html"
    if not app_path.exists():
        raise FileNotFoundError(app_path)

    url = _preview_url(port)
    if _is_local_port_open(port):
        return {"url": url, "port": int(port), "started": False, "bundle_path": bundle_dir}

    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(int(port)),
            "--bind",
            PUBLIC_PREVIEW_HOST,
        ],
        cwd=str(bundle_dir / "www"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return {"url": url, "port": int(port), "started": True, "bundle_path": bundle_dir}
