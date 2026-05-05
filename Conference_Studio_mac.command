#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_SUPPORT_DIR="${HOME}/Library/Application Support/Conference Studio"
VENV_DIR="${CONFERENCE_STUDIO_VENV_DIR:-$APP_SUPPORT_DIR/.venv}"
LEGACY_VENV_DIR=".venv"
REQUIREMENTS_FILE="wic_app/requirements.txt"
APP_ENTRYPOINT="wic_app/app.py"
REQ_HASH_FILE="$VENV_DIR/.requirements.sha256"

pause_if_interactive() {
  if [ -t 0 ]; then
    read -r -p "Press Enter to close..." _ || true
  fi
}

fail() {
  echo "Error: $1"
  pause_if_interactive
  exit 1
}

if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 is not installed or not in PATH."
fi

venv_python() {
  echo "$VENV_DIR/bin/python3"
}

venv_python_in() {
  echo "$1/bin/python3"
}

venv_usable_at() {
  local venv_dir="$1"
  local python_bin
  python_bin="$(venv_python_in "$venv_dir")"
  [ -x "$python_bin" ] || return 1
  "$python_bin" -c "import sys; print(sys.executable)" >/dev/null 2>&1 || return 1
}

venv_has_pip_at() {
  local venv_dir="$1"
  local python_bin
  python_bin="$(venv_python_in "$venv_dir")"
  [ -x "$python_bin" ] || return 1
  "$python_bin" -m pip --version >/dev/null 2>&1 || return 1
}

venv_has_streamlit_at() {
  local venv_dir="$1"
  local python_bin
  python_bin="$(venv_python_in "$venv_dir")"
  [ -x "$python_bin" ] || return 1
  "$python_bin" -c "import streamlit" >/dev/null 2>&1 || return 1
}

move_broken_venv_aside() {
  local venv_dir="$1"
  local backup
  backup="${venv_dir}.broken.$(date +%Y%m%d%H%M%S)"
  echo "Detected unusable virtual environment at $venv_dir."
  mv "$venv_dir" "$backup" || fail "Could not move old $venv_dir."
  echo "Moved old environment to $backup"
}

handle_legacy_repo_venv() {
  if [ ! -e "$LEGACY_VENV_DIR" ]; then
    return
  fi

  if venv_usable_at "$LEGACY_VENV_DIR" && venv_has_pip_at "$LEGACY_VENV_DIR"; then
    echo "Ignoring repo-local $LEGACY_VENV_DIR; using mac environment at $VENV_DIR."
    return
  fi

  move_broken_venv_aside "$LEGACY_VENV_DIR"
}

ensure_venv() {
  handle_legacy_repo_venv

  if venv_usable_at "$VENV_DIR" && venv_has_pip_at "$VENV_DIR"; then
    return
  fi

  if [ -e "$VENV_DIR" ]; then
    move_broken_venv_aside "$VENV_DIR"
  fi

  echo "Creating mac virtual environment ($VENV_DIR)..."
  mkdir -p "$(dirname "$VENV_DIR")" || fail "Could not create $APP_SUPPORT_DIR."
  python3 -m venv "$VENV_DIR" || fail "Failed to create $VENV_DIR."

  if ! venv_usable_at "$VENV_DIR"; then
    fail "Created virtual environment, but its Python does not run."
  fi

  if ! venv_has_pip_at "$VENV_DIR"; then
    fail "pip is unavailable in $VENV_DIR."
  fi
}

ensure_venv

if [ ! -f "$REQUIREMENTS_FILE" ]; then
  fail "missing $REQUIREMENTS_FILE"
fi

CURRENT_HASH="$(shasum -a 256 "$REQUIREMENTS_FILE" | awk '{print $1}')"
INSTALLED_HASH=""

if [ -f "$REQ_HASH_FILE" ]; then
  INSTALLED_HASH="$(cat "$REQ_HASH_FILE")"
fi

DEPS_OK=1
if ! venv_has_streamlit_at "$VENV_DIR"; then
  DEPS_OK=0
fi

if [ "$CURRENT_HASH" != "$INSTALLED_HASH" ] || [ "$DEPS_OK" -ne 1 ]; then
  echo "Installing/updating dependencies..."
  "$(venv_python)" -m pip install --upgrade pip || fail "Failed to update pip."
  "$(venv_python)" -m pip install -r "$REQUIREMENTS_FILE" || fail "Failed to install dependencies."
  echo "$CURRENT_HASH" > "$REQ_HASH_FILE"
else
  echo "Dependencies are up to date."
fi

if ! venv_has_streamlit_at "$VENV_DIR"; then
  fail "streamlit is still unavailable after installing dependencies."
fi

echo "Starting WIC Reclassification Studio..."
"$(venv_python)" -m streamlit run "$APP_ENTRYPOINT"

echo
echo "WIC Studio stopped."
pause_if_interactive
