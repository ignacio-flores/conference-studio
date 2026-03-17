from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class RepoRenameHygieneTests(unittest.TestCase):
    def test_gitignore_excludes_local_virtualenvs(self) -> None:
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".venv/", text)
        self.assertIn(".venv_linux/", text)

    def test_readme_uses_current_conference_studio_names(self) -> None:
        text = (REPO_ROOT / "wic_app" / "README.md").read_text(encoding="utf-8")
        self.assertIn("# Conference Studio", text)
        self.assertIn("`Conference_Studio.command`", text)
        self.assertIn("`./Conference_Studio_Linux.sh`", text)
        self.assertNotIn("Launch_WIC_Studio.command", text)
        self.assertNotIn("Launch_WIC_Studio_Linux.sh", text)
        self.assertNotIn("WIC Sessions Reclassification Studio", text)

    def test_repo_does_not_track_virtualenv_directories(self) -> None:
        completed = subprocess.run(
            ["git", "ls-files"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        tracked_virtualenv_paths = [
            line for line in completed.stdout.splitlines() if line.startswith(".venv")
        ]
        self.assertEqual([], tracked_virtualenv_paths[:10], tracked_virtualenv_paths[:10])


if __name__ == "__main__":
    unittest.main()
