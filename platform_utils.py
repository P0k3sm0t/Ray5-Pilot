import os
import shutil
import subprocess
import sys
from pathlib import Path


def _open_with_platform(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    opener = shutil.which("xdg-open")
    if not opener:
        raise RuntimeError("Unable to open path on Linux: xdg-open is not installed.")
    subprocess.Popen([opener, str(path)])


def open_file(path_like: str | Path) -> Path:
    path = Path(path_like).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"File does not exist: {path}")
    _open_with_platform(path)
    return path


def open_folder(path_like: str | Path) -> Path:
    path = Path(path_like).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise RuntimeError(f"Path is not a folder: {path}")
    _open_with_platform(path)
    return path

