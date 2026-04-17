from __future__ import annotations

import shutil
from pathlib import Path

from exporters.publish import export_public_excel, export_public_payload


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
PUBLIC_BUNDLE_DIR = REPO_ROOT / "public_bundle"
PUBLIC_WWW_SOURCE_DIR = APP_DIR / "public_www"


def _bundle_readme_text() -> str:
    return """# Conference Programme

This folder is a self-contained static public bundle generated from the private Conference Studio editor.

Upload the contents of `www/` to any standard static web host.

Local preview:

```bash
cd www
python3 -m http.server 8000
```

Files:

- `www/index.html`: public site shell
- `www/assets/`: static CSS and JavaScript
- `www/data/programme.json`: public programme dataset
- `www/programme.xlsx`: public workbook download

This bundle is intended to be copied into a separate public repository or uploaded directly to a static server.
"""


def assemble_public_bundle(state, output_dir: Path = PUBLIC_BUNDLE_DIR) -> Path:
    output_dir = Path(output_dir).resolve()
    bundle_www_dir = output_dir / "www"
    bundle_assets_dir = bundle_www_dir / "assets"
    bundle_data_dir = bundle_www_dir / "data"

    if output_dir.exists():
        shutil.rmtree(output_dir)

    bundle_assets_dir.mkdir(parents=True, exist_ok=True)
    bundle_data_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(PUBLIC_WWW_SOURCE_DIR / "index.html", bundle_www_dir / "index.html")
    shutil.copy2(PUBLIC_WWW_SOURCE_DIR / "assets" / "styles.css", bundle_assets_dir / "styles.css")
    shutil.copy2(PUBLIC_WWW_SOURCE_DIR / "assets" / "app.js", bundle_assets_dir / "app.js")

    export_public_payload(state, bundle_data_dir / "programme.json")
    export_public_excel(state, bundle_www_dir / "programme.xlsx")

    (output_dir / "README.md").write_text(_bundle_readme_text(), encoding="utf-8")

    return output_dir
