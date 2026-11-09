import os
import shutil
import subprocess
import sys
import time
import webbrowser
from urllib import request as urlrequest
from urllib.error import URLError
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


def open_dashboard_when_ready(host: str, port: int, timeout_seconds: float = 20) -> bool:
    host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    authority = f"[{host}]" if ":" in host else host
    url = f"http://{authority}:{port}/"
    opener = urlrequest.build_opener(urlrequest.ProxyHandler({}))
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=1) as response:
                if response.status == 200:
                    try:
                        return bool(webbrowser.open(url, new=2))
                    except Exception:
                        print(f"Could not open a browser. Open {url} manually.", flush=True)
                        return False
        except (OSError, URLError):
            pass
        time.sleep(.25)
    print(f"Web UI did not become ready for automatic opening. Open {url} manually.", flush=True)
    return False

