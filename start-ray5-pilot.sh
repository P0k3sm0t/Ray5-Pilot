#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting Ray5 Pilot..."
echo "Web UI opens at the configured address after the server is ready."
echo "If needed on Linux: chmod +x start-ray5-pilot.sh"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found in PATH."
  echo
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  if [ -d ".venv" ]; then
    echo "Detected a partial or broken .venv (missing .venv/bin/python)."
    echo "Remove it and rerun:"
    echo "  rm -rf .venv"
    echo "  ./start-ray5-pilot.sh"
    echo
    read -r -p "Press Enter to close..."
    exit 1
  fi
  if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
    echo "python3 can run, but venv support is missing (ensurepip unavailable)."
    echo "Install required packages, then rerun:"
    echo "  sudo apt update"
    echo "  sudo apt install python3-venv python3-pip"
    echo "  rm -rf .venv"
    echo "  ./start-ray5-pilot.sh"
    echo
    read -r -p "Press Enter to close..."
    exit 1
  fi
  echo "Creating Python virtual environment (.venv)..."
  python3 -m venv .venv
fi

PYTHON_BIN=".venv/bin/python"

if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  echo "Detected a broken Python virtual environment: pip is unavailable."
  echo "Repair steps:"
  echo "  sudo apt update"
  echo "  sudo apt install python3-venv"
  echo "  rm -rf .venv"
  echo "  ./start-ray5-pilot.sh"
  echo
  read -r -p "Press Enter to close..."
  exit 1
fi

"$PYTHON_BIN" tools/prepare_environment.py

if [ ! -f "config.json" ] && [ -f "config.example.json" ]; then
  cp "config.example.json" "config.json"
  echo "Created config.json from config.example.json"
fi

"$PYTHON_BIN" app.py

echo
echo "Ray5 Pilot stopped."
read -r -p "Press Enter to close..."
