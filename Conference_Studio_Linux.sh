#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv_linux"
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

show_package_hint() {
  if command -v apt-get >/dev/null 2>&1; then
    echo "Try installing: sudo apt-get update && sudo apt-get install -y python3-venv python3-pip"
  elif command -v dnf >/dev/null 2>&1; then
    echo "Try installing: sudo dnf install -y python3-pip python3-virtualenv"
  elif command -v pacman >/dev/null 2>&1; then
    echo "Try installing: sudo pacman -S --needed python-pip"
  fi
}

venv_python() {
  echo "$VENV_DIR/bin/python3"
}

venv_usable() {
  [ -x "$(venv_python)" ] || return 1
  "$(venv_python)" -c "import sys; print(sys.executable)" >/dev/null 2>&1 || return 1
}

venv_has_pip() {
  [ -x "$(venv_python)" ] || return 1
  "$(venv_python)" -m pip --version >/dev/null 2>&1 || return 1
}

create_or_recreate_venv() {
  if venv_usable && venv_has_pip; then
    return
  fi

  if [ -e "$VENV_DIR" ]; then
    backup="${VENV_DIR}.broken.$(date +%Y%m%d%H%M%S)"
    echo "Detected unusable Linux virtual environment at $VENV_DIR."
    mv "$VENV_DIR" "$backup" || fail "Could not move old $VENV_DIR."
    echo "Moved old environment to $backup"
  fi

  echo "Creating Linux virtual environment ($VENV_DIR)..."
  if ! python3 -m venv "$VENV_DIR"; then
    echo "Standard venv creation failed; retrying with --system-site-packages."
    python3 -m venv --system-site-packages "$VENV_DIR" || {
      show_package_hint
      fail "Failed to create $VENV_DIR."
    }
  fi

  if ! venv_has_pip; then
    echo "Recreating Linux virtual environment with --system-site-packages (pip fallback)..."
    backup="${VENV_DIR}.nopip.$(date +%Y%m%d%H%M%S)"
    mv "$VENV_DIR" "$backup" || fail "Could not move pip-less $VENV_DIR."
    python3 -m venv --system-site-packages "$VENV_DIR" || {
      show_package_hint
      fail "Failed to create fallback $VENV_DIR."
    }
  fi

  if ! venv_has_pip; then
    show_package_hint
    fail "pip is unavailable in $VENV_DIR."
  fi
}

requirements_hash() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$REQUIREMENTS_FILE" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$REQUIREMENTS_FILE" | awk '{print $1}'
  else
    python3 - <<'PY'
import hashlib
with open("wic_app/requirements.txt", "rb") as f:
    print(hashlib.sha256(f.read()).hexdigest())
PY
  fi
}

if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 is not installed or not in PATH."
fi

if [ ! -f "$REQUIREMENTS_FILE" ]; then
  fail "missing $REQUIREMENTS_FILE"
fi

create_or_recreate_venv

CURRENT_HASH="$(requirements_hash)"
INSTALLED_HASH=""
if [ -f "$REQ_HASH_FILE" ]; then
  INSTALLED_HASH="$(cat "$REQ_HASH_FILE")"
fi

DEPS_OK=1
if ! "$(venv_python)" -c "import streamlit" >/dev/null 2>&1; then
  DEPS_OK=0
fi

if [ "$CURRENT_HASH" != "$INSTALLED_HASH" ] || [ "$DEPS_OK" -ne 1 ]; then
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
pause_if_interactive
