from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"

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
    "platform_utils.py",
    "calibrate_camera.py",
    "updater.py",
    "config.example.json",
    "README.md",
    "RELEASE_NOTES.md",
    "requirements.txt",
    "LICENSE",
    "web",
    "docs",
    "tools",
    "Start_Ray5_Pilot.bat",
    "launcher.py",
    "start-ray5-pilot.sh",
    "build_launcher.bat",
]

EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
    "logs",
    "camera_captures",
    "snapshots",
    "timelapse",
    "watched_gcode",
    "imported_jobs",
    "rejected_jobs",
    "backups",
    "update_backups",
    "update_work",
    "update_logs",
    "uploads",
    "node_modules",
}

EXCLUDE_FILE_PATTERNS = (
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.tmp",
    "*.bak",
    "*.bak.*",
    "*~",
    ".env",
    ".env.*",
    "secret_terms.local.txt",
    "config.json",
)

REQUIRED_FILES = tuple(p for p in INCLUDE_PATHS if Path(p).suffix == ".py") + (
    "VERSION", "config.example.json", "requirements.txt",
    "Start_Ray5_Pilot.bat", "start-ray5-pilot.sh",
    "web/templates/index.html", "web/templates/setup.html",
    "web/templates/machine_settings.html", "web/templates/esp32.html",
    "web/static/app.js", "web/static/setup.js", "web/static/esp32.js",
    "web/static/machine_settings.js",
    "tools/prepare_environment.py",
    "web/static/camera-tools.css",
    "web/templates/camera_popout.html",
    "web/templates/camera_calibration.html",
)


def _should_exclude(path: Path) -> bool:
    try:
        relatives = (path.relative_to(PROJECT_ROOT), path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return True  # Never package a link/junction pointing outside the project.
    for rel in relatives:
        if any(part.lower() in EXCLUDE_DIR_NAMES for part in rel.parts):
            return True
        for pat in EXCLUDE_FILE_PATTERNS:
            if fnmatch.fnmatchcase(rel.name.lower(), pat) or fnmatch.fnmatchcase(rel.as_posix().lower(), pat):
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


def _release_version() -> str:
    version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8-sig").strip()
    if not re.fullmatch(r"\d+(?:\.\d+)+(?:[-+][A-Za-z0-9.-]+)?", version):
        raise ValueError("VERSION must contain a version such as 1.2.4 or 1.2.4-beta.1")
    return version


def _validate_included_files(included: list[Path]) -> None:
    names = {p.relative_to(PROJECT_ROOT).as_posix() for p in included}
    missing = sorted(set(REQUIRED_FILES) - names)
    if missing:
        raise RuntimeError("Release package is missing required files: " + ", ".join(missing))


def _zip_mode_for_path(path: Path) -> int:
    return 0o755 if path.suffix.lower() == ".sh" else 0o644


def _write_file_with_mode(zf: zipfile.ZipFile, src: Path, arcname: str) -> None:
    st = src.stat()
    dt_tuple = time.localtime(st.st_mtime)
    zi = zipfile.ZipInfo(arcname)
    zi.date_time = (min(2107, max(1980, dt_tuple.tm_year)), dt_tuple.tm_mon, dt_tuple.tm_mday,
                    dt_tuple.tm_hour, dt_tuple.tm_min, dt_tuple.tm_sec)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.create_system = 3  # Unix
    zi.external_attr = (_zip_mode_for_path(src) << 16)
    with src.open("rb") as source, zf.open(zi, "w", force_zip64=True) as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a Ray5 Pilot ZIP and SHA256 checksum without local runtime files.")
    parser.add_argument("--output-dir", type=Path, default=DIST_DIR,
                        help="Output folder (default: project dist). Use a separate folder for test builds.")
    parser.add_argument("--force", action="store_true", help="Replace an existing ZIP/checksum in the output folder.")
    args = parser.parse_args(argv)
    included, skipped = _iter_included_files()
    _validate_included_files(included)
    exe_src = _pick_executable()
    release_version = _release_version()
    package_root = f"Ray5-Pilot-v{release_version}"
    output_dir = args.output_dir.resolve()
    output_zip = output_dir / f"{package_root}.zip"
    checksum_file = output_dir / f"{package_root}.zip.sha256.txt"
    if not args.force and (output_zip.exists() or checksum_file.exists()):
        raise FileExistsError("Release output already exists. Choose --output-dir or explicitly use --force.")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[RELEASE ZIP] writing {output_zip}")
    # Stage both outputs before replacing anything, so build errors preserve existing artifacts.
    with tempfile.TemporaryDirectory(prefix="release-stage-", dir=output_dir) as staging:
        staged_zip = Path(staging) / output_zip.name
        with zipfile.ZipFile(staged_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for src in included:
                arcname = f"{package_root}/{src.relative_to(PROJECT_ROOT).as_posix()}"
                _write_file_with_mode(zf, src, arcname)
            if exe_src is not None:
                if exe_src.resolve() not in (PROJECT_ROOT.resolve() / "Ray5 Pilot.exe",
                                             PROJECT_ROOT.resolve() / "dist" / "Ray5 Pilot.exe"):
                    raise RuntimeError("Launcher resolves outside its expected project location")
                _write_file_with_mode(zf, exe_src, f"{package_root}/Ray5 Pilot.exe")
                print(f"[RELEASE ZIP] including executable: {exe_src} -> {package_root}/Ray5 Pilot.exe")
            else:
                print("[RELEASE ZIP] warning: Ray5 Pilot.exe not found; zip will be source-only")
        sha256 = _sha256_file(staged_zip)
        staged_checksum = Path(staging) / checksum_file.name
        staged_checksum.write_text(f"{sha256}  {output_zip.name}\n", encoding="utf-8")
        os.replace(staged_zip, output_zip)
        os.replace(staged_checksum, checksum_file)

    print(f"[RELEASE ZIP] included={len(included)} skipped={skipped}")
    print(f"[RELEASE ZIP] sha256: {sha256}")
    print(f"[RELEASE ZIP] checksum file: {checksum_file}")
    print(f"[RELEASE ZIP] done: {output_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
