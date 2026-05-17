from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib import request as urlrequest


ALLOWED_UPDATE_PATHS: tuple[str, ...] = (
    "README.md",
    "VERSION",
    ".gitignore",
    "app.py",
    "camera_manager.py",
    "config.example.json",
    "config_manager.py",
    "ray5_client.py",
    "job_manager.py",
    "console_log.py",
    "calibrate_camera.py",
    "ray5_status_monitor.py",
    "gcode_safety.py",
    "requirements.txt",
    "web/templates/index.html",
    "web/templates/setup.html",
    "web/templates/camera_calibration.html",
    "web/templates/machine_settings.html",
    "web/static/app.js",
    "web/static/setup.js",
    "web/static/machine_settings.js",
    "web/static/style.css",
    "web/static/favicon.ico",
    "web/static/favicon.svg",
    "web/static/camera_placeholder.svg",
)


def _now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_wait_for_parent_exit(parent_pid: int, timeout_seconds: float, log) -> None:
    if parent_pid <= 0:
        return
    deadline = time.time() + max(1.0, timeout_seconds)
    while time.time() < deadline:
        if not _is_process_running(parent_pid):
            log(f"Parent process {parent_pid} exited.")
            return
        time.sleep(0.25)
    log(f"Parent process {parent_pid} still running after {timeout_seconds:.0f}s; continuing cautiously.")


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            output = (result.stdout or "").strip()
            return bool(output and "No tasks are running" not in output)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _write_update_status(
    project_root: Path,
    ok: bool,
    from_version: str,
    to_version: str,
    message: str,
    log_path: Path,
) -> None:
    status_path = project_root / "update_logs" / "update_status.json"
    payload = {
        "ok": bool(ok),
        "status": "success" if ok else "failed",
        "from_version": str(from_version or ""),
        "to_version": str(to_version or ""),
        "message": str(message or ""),
        "log_file": str(log_path.relative_to(project_root)).replace("\\", "/"),
        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _remove_path_safe(path: Path, log) -> None:
    try:
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except Exception as exc:
        log(f"WARN: cleanup failed for {path}: {exc}")


def _rotate_old_entries(root: Path, keep: int, is_candidate, log) -> None:
    try:
        candidates = [p for p in root.iterdir() if is_candidate(p)]
    except Exception as exc:
        log(f"WARN: cleanup scan failed for {root}: {exc}")
        return
    if len(candidates) <= keep:
        return
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in candidates[keep:]:
        _remove_path_safe(old, log)


def _run(argv: argparse.Namespace) -> int:
    project_root = Path(argv.project_root).resolve()
    python_exe = str(Path(argv.python_exe).resolve())
    source_url = str(argv.source_url).strip()
    stamp = _now_stamp()

    work_dir = project_root / "update_work"
    backups_root = project_root / "update_backups"
    logs_root = project_root / "update_logs"
    backup_dir = backups_root / f"update_{stamp}"
    log_path = logs_root / f"update_{stamp}.log"
    download_zip = work_dir / f"source_{stamp}.zip"
    extract_dir = work_dir / f"extract_{stamp}"

    work_dir.mkdir(parents=True, exist_ok=True)
    backups_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    update_ok = False
    final_message = f"Ray5 Pilot update failed. See update log."
    with log_path.open("w", encoding="utf-8") as log_file:
        def log(msg: str) -> None:
            line = f"[{dt.datetime.now().isoformat(timespec='seconds')}] {msg}"
            print(line)
            log_file.write(line + "\n")
            log_file.flush()

        log("Ray5 Pilot updater started.")
        log(f"Project root: {project_root}")
        log(f"Current version: {argv.current_version}")
        log(f"Remote version: {argv.remote_version}")
        log(f"Source URL: {source_url}")

        _safe_wait_for_parent_exit(int(argv.parent_pid), timeout_seconds=20.0, log=log)

        log(f"Downloading update ZIP to {download_zip}")
        req = urlrequest.Request(source_url, headers={"User-Agent": "Ray5-Pilot-Updater"}, method="GET")
        with urlrequest.urlopen(req, timeout=15) as resp, download_zip.open("wb") as out_f:
            shutil.copyfileobj(resp, out_f)

        log(f"Extracting ZIP to {extract_dir}")
        with zipfile.ZipFile(download_zip, "r") as zf:
            zf.extractall(extract_dir)

        try:
            roots = [p for p in extract_dir.iterdir() if p.is_dir()]
            if not roots:
                raise RuntimeError("No extracted root folder found.")
            source_root = roots[0]
            log(f"Using extracted source root: {source_root}")

            backed_up: list[str] = []
            copied: list[str] = []
            for rel in ALLOWED_UPDATE_PATHS:
                src = (source_root / rel).resolve()
                dst = (project_root / rel).resolve()
                if not src.exists():
                    log(f"WARN: Missing in update source, skipped: {rel}")
                    continue
                if dst.exists():
                    backup_target = (backup_dir / rel).resolve()
                    _copy_file(dst, backup_target)
                    backed_up.append(rel)
                _copy_file(src, dst)
                copied.append(rel)
                log(f"Updated: {rel}")

            pip_ok = True
            try:
                py_exe_path = Path(python_exe)
                py_exe_text = str(py_exe_path).replace("\\", "/").lower()
                looks_like_venv = any(token in py_exe_text for token in ("/.venv/", "/venv/", "/env/"))
                log(f"Python executable for pip install: {python_exe}")
                log(f"Python virtual environment detected by path: {'yes' if looks_like_venv else 'no'}")
                if not looks_like_venv:
                    log("WARN: Python executable path does not look like .venv/venv/env; requirements will install into the current Python environment.")
                log("Running pip install for requirements.txt")
                result = subprocess.run(
                    [python_exe, "-m", "pip", "install", "-r", "requirements.txt"],
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                if result.returncode != 0:
                    pip_ok = False
                    log(f"WARN: pip install failed (exit {result.returncode}).")
                    if result.stdout:
                        log(result.stdout.strip())
                    if result.stderr:
                        log(result.stderr.strip())
                else:
                    log("pip install completed successfully.")
            except Exception as exc:
                pip_ok = False
                log(f"WARN: pip install raised exception: {exc}")

            log(f"Backed up files: {len(backed_up)}")
            log(f"Copied files: {len(copied)}")
            if not pip_ok:
                log("Update completed with pip warning.")
            else:
                log("Update completed successfully.")

            update_ok = True
            final_message = f"Ray5 Pilot updated successfully to {argv.remote_version or 'latest'}."
        except Exception as exc:
            update_ok = False
            final_message = "Ray5 Pilot update failed. See update log."
            log(f"ERROR: {exc}")

        _write_update_status(
            project_root=project_root,
            ok=update_ok,
            from_version=str(argv.current_version or ""),
            to_version=str(argv.remote_version or ""),
            message=final_message,
            log_path=log_path,
        )
        log(f"Update status written: update_logs/update_status.json")
        # Conservative cleanup/rotation after status is written.
        _remove_path_safe(work_dir, log)
        _rotate_old_entries(
            backups_root,
            keep=5,
            is_candidate=lambda p: p.is_dir() and p.name.startswith("update_"),
            log=log,
        )
        _rotate_old_entries(
            logs_root,
            keep=10,
            is_candidate=lambda p: p.is_file() and p.suffix.lower() == ".log" and p.name.startswith("update_"),
            log=log,
        )

        restart_cmd = [python_exe, "app.py"]
        if os.name == "nt":
            log("Restarting Ray5 Pilot in a new console so CTRL+C works normally.")
        else:
            log("Restarting Ray5 Pilot in current shell session.")
        log(f"Restart command: {' '.join(restart_cmd)}")
        try:
            if os.name == "nt":
                subprocess.Popen(
                    restart_cmd,
                    cwd=str(project_root),
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                )
            else:
                subprocess.Popen(restart_cmd, cwd=str(project_root))
            log("Ray5 Pilot restart launched.")
        except Exception as exc:
            log(f"ERROR: failed to restart app.py: {exc}")
            return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ray5 Pilot self-updater")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--python-exe", required=True)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--current-version", default="")
    parser.add_argument("--remote-version", default="")
    args = parser.parse_args()
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
