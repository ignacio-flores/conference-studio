#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
REQUIREMENTS_FILE="wic_app/requirements.txt"
APP_ENTRYPOINT="wic_app/app.py"
REQ_HASH_FILE="$VENV_DIR/.requirements.sha256"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is not installed or not in PATH."
  read -r -p "Press Enter to close..." _
  exit 1
fi

venv_python() {
  echo "$VENV_DIR/bin/python3"
}

ensure_venv() {
  if [ -x "$(venv_python)" ]; then
    return
  fi

  if [ -e "$VENV_DIR" ]; then
    backup="${VENV_DIR}.broken.$(date +%Y%m%d%H%M%S)"
    echo "Detected unusable local virtual environment at $VENV_DIR."
    mv "$VENV_DIR" "$backup"
    echo "Moved old environment to $backup"
  fi

  echo "Creating local virtual environment ($VENV_DIR)..."
  python3 -m venv "$VENV_DIR"
}

ensure_venv

if [ ! -f "$REQUIREMENTS_FILE" ]; then
  echo "Error: missing $REQUIREMENTS_FILE"
  read -r -p "Press Enter to close..." _
  exit 1
fi

CURRENT_HASH="$(shasum -a 256 "$REQUIREMENTS_FILE" | awk '{print $1}')"
INSTALLED_HASH=""

if [ -f "$REQ_HASH_FILE" ]; then
  INSTALLED_HASH="$(cat "$REQ_HASH_FILE")"
fi

if [ "$CURRENT_HASH" != "$INSTALLED_HASH" ]; then
  echo "Installing/updating dependencies..."
  "$(venv_python)" -m pip install --upgrade pip
  "$(venv_python)" -m pip install -r "$REQUIREMENTS_FILE"
  echo "$CURRENT_HASH" > "$REQ_HASH_FILE"
else
  echo "Dependencies are up to date."
fi

echo "Starting WIC Reclassification Studio..."
"$(venv_python)" -m streamlit run "$APP_ENTRYPOINT"

echo
echo "WIC Studio stopped."
read -r -p "Press Enter to close..." _
