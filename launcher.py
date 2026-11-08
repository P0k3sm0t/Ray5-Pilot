"""Windows EXE entry point using the shared first-run dependency setup."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def project_dir() -> Path:
    location = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    if (location / "app.py").is_file():
        return location
    if (location.parent / "app.py").is_file():
        return location.parent
    return location


def main() -> int:
    root = project_dir()
    print("Ray5 Pilot Launcher", flush=True)
    print(f"Project folder: {root}", flush=True)
    for name in ("app.py", "Start_Ray5_Pilot.bat", "requirements.txt", "config.example.json"):
        if not (root / name).is_file():
            print(f"[ERROR] Missing {name}. Extract the complete Ray5 Pilot release before starting.")
            try:
                input("Press Enter to exit...")
            except EOFError:
                pass
            return 1

    print("Preparing Python environment and checking required packages...", flush=True)
    # Use the same setup as the BAT so both entry points install into .venv.
    command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", "Start_Ray5_Pilot.bat"]
    try:
        return subprocess.call(command, cwd=str(root))
    except OSError as exc:
        print(f"[ERROR] Could not start setup: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
