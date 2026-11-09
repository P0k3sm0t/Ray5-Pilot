"""Cache successful dependency setup inside the launcher's virtual environment."""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import os


PACKAGES = ("Flask", "requests", "opencv-python", "numpy", "pillow", "websocket-client")
IMPORT_CHECK = "import flask, requests, cv2, numpy, PIL, websocket"


def signature(root: Path) -> dict:
    versions = {}
    for package in PACKAGES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return {"requirements": hashlib.sha256((root / "requirements.txt").read_bytes()).hexdigest(),
            "python": sys.version, "executable": sys.executable, "packages": versions}


def prepare(root: Path, state_dir: Path | None = None, runner=None) -> bool:
    runner = runner or subprocess.run
    if state_dir is None:
        if sys.prefix == sys.base_prefix:
            raise RuntimeError("Start setup inside the project's .venv, not the global Python environment.")
        state_dir = Path(sys.prefix)
    marker = state_dir / ".ray5_pilot_dependencies.json"
    current = signature(root)
    try:
        previous = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None
    check = [sys.executable, "-c", IMPORT_CHECK]
    if previous == current and all(current["packages"].values()):
        result = runner(check, capture_output=True, timeout=60)
        if result.returncode == 0:
            print("Dependencies ready (cached).", flush=True)
            return False
    print("Installing/checking project requirements...", flush=True)
    runner([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
            "-r", str(root / "requirements.txt")], check=True, timeout=900)
    runner(check, check=True, capture_output=True, timeout=60)
    state_dir.mkdir(parents=True, exist_ok=True)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=state_dir, suffix=".tmp", delete=False) as file:
            staged = Path(file.name)
            json.dump(signature(root), file)
        os.replace(staged, marker)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return True


if __name__ == "__main__":
    try:
        prepare(Path(__file__).resolve().parents[1])
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"[SETUP ERROR] Dependency setup failed: {error}", file=sys.stderr)
        raise SystemExit(1)
