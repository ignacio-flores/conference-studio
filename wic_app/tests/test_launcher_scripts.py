from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class LauncherScriptTests(unittest.TestCase):
    def test_macos_launcher_uses_venv_python_directly(self) -> None:
        text = (REPO_ROOT / "Conference_Studio_mac.command").read_text(encoding="utf-8")
        self.assertIn('APP_SUPPORT_DIR="${HOME}/Library/Application Support/Conference Studio"', text)
        self.assertIn('VENV_DIR="${CONFERENCE_STUDIO_VENV_DIR:-$APP_SUPPORT_DIR/.venv}"', text)
        self.assertIn('LEGACY_VENV_DIR=".venv"', text)
        self.assertIn('venv_python()', text)
        self.assertIn('venv_usable_at()', text)
        self.assertIn('venv_has_pip_at()', text)
        self.assertIn('venv_has_streamlit_at()', text)
        self.assertIn('move_broken_venv_aside "$LEGACY_VENV_DIR"', text)
        self.assertIn('"$(venv_python)" -m pip install --upgrade pip', text)
        self.assertIn('"$(venv_python)" -m pip install -r "$REQUIREMENTS_FILE"', text)
        self.assertIn('"$(venv_python)" -m streamlit run "$APP_ENTRYPOINT"', text)
        self.assertNotIn("source .venv/bin/activate", text)

    def test_linux_launcher_uses_venv_python_directly(self) -> None:
        text = (REPO_ROOT / "Conference_Studio_Linux.sh").read_text(encoding="utf-8")
        self.assertIn('VENV_DIR=".venv_linux"', text)
        self.assertIn('venv_python()', text)
        self.assertIn('"$(venv_python)" -m pip install --upgrade pip', text)
        self.assertIn('"$(venv_python)" -m pip install -r "$REQUIREMENTS_FILE"', text)
        self.assertIn('"$(venv_python)" -m streamlit run "$APP_ENTRYPOINT"', text)
        self.assertNotIn("source .venv_linux/bin/activate", text)

    def test_windows_launcher_exists_and_uses_windows_venv_python(self) -> None:
        launcher_path = REPO_ROOT / "Conference_Studio_Windows.cmd"
        self.assertTrue(launcher_path.exists(), str(launcher_path))

        text = launcher_path.read_text(encoding="utf-8")
        self.assertIn('set "VENV_DIR=.venv_windows"', text)
        self.assertIn('set "VENV_PY=%VENV_DIR%\\Scripts\\python.exe"', text)
        self.assertIn('"%VENV_PY%" -m pip install --upgrade pip', text)
        self.assertIn('"%VENV_PY%" -m pip install -r "%REQUIREMENTS_FILE%"', text)
        self.assertIn('"%VENV_PY%" -m streamlit run "%APP_ENTRYPOINT%"', text)


if __name__ == "__main__":
    unittest.main()
