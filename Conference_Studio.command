#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is not installed or not in PATH."
  read -r -p "Press Enter to close..." _
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Creating local virtual environment (.venv)..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

REQ_HASH_FILE=".venv/.requirements.sha256"
REQUIREMENTS_FILE="wic_app/requirements.txt"
APP_ENTRYPOINT="wic_app/app.py"

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
  python -m pip install --upgrade pip
  python -m pip install -r "$REQUIREMENTS_FILE"
  echo "$CURRENT_HASH" > "$REQ_HASH_FILE"
else
  echo "Dependencies are up to date."
fi

echo "Starting WIC Reclassification Studio..."
python -m streamlit run "$APP_ENTRYPOINT"

echo
echo "WIC Studio stopped."
read -r -p "Press Enter to close..." _
