from __future__ import annotations

import shutil
from pathlib import Path

from exporters.publish import export_public_excel, export_public_payload


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
PUBLIC_BUNDLE_DIR = REPO_ROOT / "public_bundle"
PUBLIC_BUNDLE_WIC_APP_DIR = PUBLIC_BUNDLE_DIR / "wic_app"
PUBLIC_BUNDLE_DATA_DIR = PUBLIC_BUNDLE_DIR / "public_data"

PUBLIC_RUNTIME_FILES = [
    "public_app.py",
    "public_data.py",
]


def _bundle_readme_text() -> str:
    return """# Conference Programme

This folder is a self-contained public bundle generated from the private Conference Studio editor.

Run locally:

```bash
pip install -r requirements.txt
export PUBLIC_ENABLED=true
streamlit run wic_app/public_app.py
```

Files:

- `wic_app/public_app.py`: read-only Streamlit entrypoint
- `public_data/programme.json`: public programme dataset
- `public_data/programme.xlsx`: public workbook download

This bundle is intended to be copied into a separate public repository.
"""


def assemble_public_bundle(state, output_dir: Path = PUBLIC_BUNDLE_DIR) -> Path:
    output_dir = Path(output_dir).resolve()
    bundle_wic_app_dir = output_dir / "wic_app"
    bundle_data_dir = output_dir / "public_data"

    if output_dir.exists():
        shutil.rmtree(output_dir)

    bundle_wic_app_dir.mkdir(parents=True, exist_ok=True)
    bundle_data_dir.mkdir(parents=True, exist_ok=True)

    for filename in PUBLIC_RUNTIME_FILES:
        shutil.copy2(APP_DIR / filename, bundle_wic_app_dir / filename)

    export_public_payload(state, bundle_data_dir / "programme.json")
    export_public_excel(state, bundle_data_dir / "programme.xlsx")

    requirements_src = APP_DIR / "requirements-public.txt"
    shutil.copy2(requirements_src, output_dir / "requirements.txt")
    (output_dir / "README.md").write_text(_bundle_readme_text(), encoding="utf-8")

    return output_dir
