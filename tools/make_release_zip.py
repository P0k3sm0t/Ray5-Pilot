from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"
OUTPUT_ZIP = DIST_DIR / "Ray5-Pilot-release.zip"
CHECKSUM_FILE = DIST_DIR / "Ray5-Pilot-release.zip.sha256.txt"

INCLUDE_PATHS = [
    "VERSION",
    "app.py",
    "ray5_client.py",
    "config_manager.py",
    "ray5_status_monitor.py",
    "job_manager.py",
    "gcode_safety.py",
    "console_log.py",
    "camera_manager.py",
    "calibrate_camera.py",
    "updater.py",
    "config.example.json",
    "README.md",
    "requirements.txt",
    "LICENSE",
    "web",
    "tools",
    "Start_Ray5_Pilot.bat",
    "build_launcher.bat",
]

EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
    "logs",
    "camera_captures",
    "timelapse",
    "watched_gcode",
    "imported_jobs",
    "rejected_jobs",
    "backups",
    "update_backups",
}

EXCLUDE_FILE_PATTERNS = (
    "*.pyc",
    "*.pyo",
    "*.log",
    "config.json",
)


def _should_exclude(path: Path) -> bool:
    rel = path.relative_to(PROJECT_ROOT)
    for part in rel.parts:
        if part in EXCLUDE_DIR_NAMES:
            return True
    rel_posix = rel.as_posix()
    for pat in EXCLUDE_FILE_PATTERNS:
        if fnmatch.fnmatch(rel.name, pat) or fnmatch.fnmatch(rel_posix, pat):
            return True
    return False


def _iter_included_files() -> tuple[list[Path], int]:
    files: list[Path] = []
    skipped = 0
    for rel in INCLUDE_PATHS:
        p = PROJECT_ROOT / rel
        if not p.exists():
            continue
        if p.is_file():
            if _should_exclude(p):
                skipped += 1
            else:
                files.append(p)
            continue
        for child in p.rglob("*"):
            if not child.is_file():
                continue
            if _should_exclude(child):
                skipped += 1
                continue
            files.append(child)
    # Deduplicate while preserving deterministic order.
    seen: set[str] = set()
    unique: list[Path] = []
    for f in sorted(files, key=lambda x: x.relative_to(PROJECT_ROOT).as_posix()):
        key = str(f.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique, skipped


def _pick_executable() -> Path | None:
    preferred = PROJECT_ROOT / "dist" / "Ray5 Pilot.exe"
    fallback = PROJECT_ROOT / "Ray5 Pilot.exe"
    if preferred.is_file():
        return preferred
    if fallback.is_file():
        return fallback
    return None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def main() -> int:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    included, skipped = _iter_included_files()
    exe_src = _pick_executable()

    print(f"[RELEASE ZIP] writing {OUTPUT_ZIP}")
    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src in included:
            arcname = src.relative_to(PROJECT_ROOT).as_posix()
            zf.write(src, arcname)
        if exe_src is not None:
            zf.write(exe_src, "Ray5 Pilot.exe")
            print(f"[RELEASE ZIP] including executable: {exe_src} -> Ray5 Pilot.exe")
        else:
            print("[RELEASE ZIP] warning: Ray5 Pilot.exe not found; zip will be source-only")

    sha256 = _sha256_file(OUTPUT_ZIP)
    checksum_line = f"{sha256}  {OUTPUT_ZIP.name}\n"
    try:
        CHECKSUM_FILE.write_text(checksum_line, encoding="utf-8")
    except Exception as exc:
        raise RuntimeError(f"Failed to write checksum file {CHECKSUM_FILE}: {exc}") from exc

    print(f"[RELEASE ZIP] included={len(included)} skipped={skipped}")
    print(f"[RELEASE ZIP] sha256: {sha256}")
    print(f"[RELEASE ZIP] checksum file: {CHECKSUM_FILE}")
    print(f"[RELEASE ZIP] done: {OUTPUT_ZIP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
