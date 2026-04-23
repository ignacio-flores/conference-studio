from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class PublicReleaseCliTests(unittest.TestCase):
    def test_publish_cli_generates_public_json_and_excel(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        script_path = repo_root / "wic_app" / "generate_wic_programme_draft.py"
        default_config_path = repo_root / "wic_app" / "assets" / "conference.default.json"
        default_config = json.loads(default_config_path.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = dict(default_config)
            files = dict(default_config.get("files", {}))
            files["draft_output"] = str(tmp_path / "draft.xlsx")
            files["publish_xlsx_output"] = str(tmp_path / "publish.xlsx")
            files["publish_pdf_output"] = str(tmp_path / "publish.pdf")
            files["publish_docx_output"] = str(tmp_path / "publish.docx")
            files["public_json_output"] = str(tmp_path / "programme.json")
            files["public_xlsx_output"] = str(tmp_path / "programme_public.xlsx")
            config["files"] = files

            config_path = tmp_path / "conference.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--publish",
                    "--publish-display",
                    "public_safe",
                    "--config",
                    str(config_path),
                ],
                cwd=str(repo_root / "wic_app"),
                capture_output=True,
                text=True,
                timeout=120,
            )

            output = (completed.stdout or "") + (completed.stderr or "")
            self.assertEqual(completed.returncode, 0, output[-4000:])
            self.assertIn("Publish display mode: public_safe", output)
            self.assertIn("Generated public JSON", output)
            self.assertIn("Generated public workbook", output)
            self.assertTrue(
                ("Generated publish Word" in output) or ("Publish Word skipped" in output),
                output,
            )
            self.assertTrue((tmp_path / "programme.json").exists())
            self.assertTrue((tmp_path / "programme_public.xlsx").exists())


if __name__ == "__main__":
    unittest.main()
