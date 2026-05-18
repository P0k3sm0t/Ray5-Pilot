#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

PY_FILES = [
    "app.py",
    "updater.py",
    "ray5_client.py",
    "config_manager.py",
    "job_manager.py",
    "camera_manager.py",
    "console_log.py",
    "calibrate_camera.py",
    "ray5_status_monitor.py",
    "gcode_safety.py",
]

JS_FILES = [
    "web/static/app.js",
    "web/static/setup.js",
    "web/static/machine_settings.js",
]

ABSENT_PATHS = [
    "config.json",
    "update_work",
    "update_backups",
    "update_logs",
    "build",
    "dist",
    ".venv",
    "launcher.py",
    "build_launcher.bat",
]

RUNTIME_DIRS = [
    "logs",
    "camera_captures",
    "timelapse",
    "imported_jobs",
    "watched_gcode",
    "rejected_jobs",
]

SECRET_TERMS = [
    "ArielJoe19",
    "10.0.0.195",
    "10.0.0.138",
    "FBI Mobile",
    "12345678",
    "rtsp://P0k3sm0t",
]

TEXT_EXTS = {
    ".py", ".js", ".html", ".css", ".md", ".json", ".txt", ".bat", ".yml", ".yaml", ".ini", ".toml", "",
}

IGNORE_TEXT_FILES = {"Ray5 Pilot.exe"}


class Result:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.passes: list[str] = []

    def ok(self, msg: str) -> None:
        self.passes.append(msg)
        print(f"[PASS] {msg}")

    def fail(self, msg: str) -> None:
        self.failures.append(msg)
        print(f"[FAIL] {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        print(f"[WARN] {msg}")


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)


def check_python_compile(r: Result) -> None:
    errors = []
    for rel in PY_FILES:
        p = ROOT / rel
        if not p.exists():
            errors.append(f"missing: {rel}")
            continue
        try:
            source = p.read_text(encoding="utf-8")
            compile(source, str(p), "exec")
        except Exception as exc:
            errors.append(f"{rel}: {exc}")
    if errors:
        r.fail("Python syntax")
        for e in errors:
            print(f"  - {e}")
    else:
        r.ok("Python syntax")


def check_js_syntax(r: Result) -> None:
    node = shutil.which("node")
    if not node:
        r.fail("JavaScript syntax (node not found)")
        return
    errors = []
    for rel in JS_FILES:
        p = ROOT / rel
        if not p.exists():
            errors.append(f"missing: {rel}")
            continue
        cp = _run([node, "--check", str(p)], ROOT)
        if cp.returncode != 0:
            errors.append(f"{rel}: {(cp.stderr or cp.stdout).strip()}")
    if errors:
        r.fail("JavaScript syntax")
        for e in errors:
            print(f"  - {e}")
    else:
        r.ok("JavaScript syntax")


def check_json(r: Result) -> None:
    p = ROOT / "config.example.json"
    try:
        with p.open("r", encoding="utf-8") as f:
            json.load(f)
        r.ok("config.example.json")
    except Exception as exc:
        r.fail(f"config.example.json ({exc})")


def _flatten_keys(value: object, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            k_str = str(k)
            key = f"{prefix}.{k_str}" if prefix else k_str
            keys.add(key)
            keys |= _flatten_keys(v, key)
    return keys


def _load_default_config_literal() -> dict:
    cfg_path = ROOT / "config_manager.py"
    source = cfg_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "DEFAULT_CONFIG":
                    return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "DEFAULT_CONFIG" and node.value is not None:
                return ast.literal_eval(node.value)
    raise RuntimeError("DEFAULT_CONFIG literal not found in config_manager.py")


def check_config_key_coverage(r: Result) -> None:
    try:
        example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        default_cfg = _load_default_config_literal()
        ex_keys = _flatten_keys(example)
        def_keys = _flatten_keys(default_cfg)
        missing = sorted(def_keys - ex_keys)
        extra = sorted(ex_keys - def_keys)
        if missing or extra:
            r.fail("config key coverage")
            print(f"  - missing keys: {len(missing)}")
            for k in missing[:50]:
                print(f"    * {k}")
            print(f"  - extra keys: {len(extra)}")
            for k in extra[:50]:
                print(f"    * {k}")
        else:
            r.ok("config key coverage")
    except Exception as exc:
        r.fail(f"config key coverage ({exc})")


def check_version_cache_busting(r: Result) -> None:
    try:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        setup_html = (ROOT / "web/templates/setup.html").read_text(encoding="utf-8")
        needle = f"setup.js?v={version}"
        if needle in setup_html:
            r.ok("VERSION/cache-busting")
        else:
            r.fail(f"VERSION/cache-busting (missing '{needle}')")
    except Exception as exc:
        r.fail(f"VERSION/cache-busting ({exc})")


def _runtime_real_files(path: Path) -> list[Path]:
    out: list[Path] = []
    if not path.exists():
        return out
    for fp in path.rglob("*"):
        if not fp.is_file():
            continue
        rel_name = fp.name.lower()
        if rel_name in {".gitkeep", ".gitignore"}:
            continue
        if rel_name.endswith(".pyc"):
            continue
        if "__pycache__" in fp.parts:
            continue
        out.append(fp)
    return out


def check_github_safe_files(r: Result) -> None:
    problems = []
    pycache_found = []
    for rel in ABSENT_PATHS:
        p = ROOT / rel
        if p.exists():
            problems.append(f"must be absent: {rel}")
    for rel in RUNTIME_DIRS:
        p = ROOT / rel
        if p.exists():
            real_files = _runtime_real_files(p)
            if real_files:
                problems.append(f"runtime dir has files: {rel} ({len(real_files)})")
                for item in real_files[:10]:
                    print(f"    * {item.relative_to(ROOT)}")
    for fp in ROOT.rglob("__pycache__"):
        if fp.is_dir():
            pycache_found.append(str(fp.relative_to(ROOT)))
    if pycache_found:
        r.warn("__pycache__ present but ignored")
    if problems:
        r.fail("GitHub-safe file checks")
        for p in problems:
            print(f"  - {p}")
    else:
        r.ok("GitHub-safe file checks")


def _iter_scan_files() -> Iterable[Path]:
    roots = [ROOT / "web", ROOT / "docs"]
    runtime_roots = {str((ROOT / d).resolve()) for d in RUNTIME_DIRS}
    seen: set[Path] = set()
    for fixed in [
        ROOT / "README.md",
        ROOT / "app.py",
        ROOT / "updater.py",
        ROOT / "config_manager.py",
        ROOT / "ray5_client.py",
        ROOT / "job_manager.py",
        ROOT / "camera_manager.py",
        ROOT / "console_log.py",
        ROOT / "calibrate_camera.py",
        ROOT / "ray5_status_monitor.py",
        ROOT / "gcode_safety.py",
        ROOT / "requirements.txt",
        ROOT / "VERSION",
        ROOT / "config.example.json",
        ROOT / ".gitignore",
    ]:
        if fixed.exists() and fixed.is_file():
            if fixed.name.lower() == "config.json":
                continue
            if fixed.resolve() not in seen:
                seen.add(fixed.resolve())
                yield fixed
    for folder in roots:
        if not folder.exists():
            continue
        for fp in folder.rglob("*"):
            if not fp.is_file():
                continue
            if ".git" in fp.parts or fp.name.lower() == "config.json":
                continue
            if fp.name in IGNORE_TEXT_FILES:
                continue
            resolved = fp.resolve()
            if any(str(resolved).startswith(root + os.sep) or str(resolved) == root for root in runtime_roots):
                continue
            if fp.suffix.lower() not in TEXT_EXTS:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            yield fp


def _read_text_safely(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="ignore")


def check_secret_scan(r: Result) -> None:
    hits = []
    p0_hits = []
    for fp in _iter_scan_files():
        text = _read_text_safely(fp)
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            for term in SECRET_TERMS:
                if term in line:
                    hits.append(f"{fp.relative_to(ROOT)}:{i}: {term}")
            if "P0k3sm0t" in line and not (
                "github.com/P0k3sm0t/" in line
                or "raw.githubusercontent.com/P0k3sm0t/" in line
                or "api.github.com/repos/P0k3sm0t/" in line
            ):
                p0_hits.append(f"{fp.relative_to(ROOT)}:{i}")
    if hits or p0_hits:
        r.fail("Secret scan")
        for h in hits[:100]:
            print(f"  - {h}")
        for h in p0_hits[:100]:
            print(f"  - disallowed P0k3sm0t use: {h}")
    else:
        r.ok("Secret scan")


def check_firmware_rename(r: Result) -> None:
    problems = []
    required_hits = 0
    for fp in [ROOT / "web/templates/index.html", ROOT / "web/templates/setup.html", ROOT / "web/templates/machine_settings.html"]:
        if not fp.exists():
            continue
        txt = _read_text_safely(fp)
        required_hits += txt.count("Firmware Settings")
        if re.search(r"Machine Settings", txt, flags=re.IGNORECASE):
            problems.append(f"{fp.relative_to(ROOT)} contains user-facing 'Machine Settings'")
    for fp in [ROOT / "web/static/app.js", ROOT / "web/static/setup.js", ROOT / "web/static/machine_settings.js"]:
        if not fp.exists():
            continue
        txt = _read_text_safely(fp)
        if re.search(r"Machine Settings", txt, flags=re.IGNORECASE):
            problems.append(f"{fp.relative_to(ROOT)} contains user-facing 'Machine Settings'")
    if required_hits == 0:
        problems.append("No 'Firmware Settings' label found in checked templates")
    if problems:
        r.fail("Firmware Settings rename check")
        for p in problems:
            print(f"  - {p}")
    else:
        r.ok("Firmware Settings rename check")


def _check_markers(file_path: Path, markers: list[tuple[str, str]]) -> list[str]:
    txt = _read_text_safely(file_path)
    missing = []
    for label, marker in markers:
        if marker not in txt:
            missing.append(label)
    return missing


def check_safety_feature_presence(r: Result) -> None:
    app_markers = [
        ("communication-loss safety lockout", "comm_lost_during_job"),
        ("clear comm-loss endpoint", "/api/safety/clear-comm-loss"),
        ("recent job activity tracking", "last_job_start_time"),
        ("SD/system-check lockout skip", "System-check SD probe skipped due to communication-loss safety lockout."),
        ("background timelapse stop/build worker", "timelapse_stop_worker"),
        ("stop_pending", "stop_pending"),
        ("build_in_progress", "build_in_progress"),
        ("final_capture_delay_seconds", "final_capture_delay_seconds"),
        ("final frame retry attempts", "final frame capture attempt"),
        ("unique final frame target", "final frame target"),
        ("duplicate timelapse start guard", "Timelapse is already active."),
    ]
    js_markers = [
        ("SD auto-refresh pause busy/lockout", "isMachineBusyForSdRefresh"),
        ("camera setup guard", "Camera is not configured. Set up camera first in Settings."),
        ("single Video/Camera message helper", "function setVideoCardMessage"),
        ("deleted timelapse playback clearing", "Selected timelapse was deleted."),
        ("Stop Timelapse confirmation", "Stop the active timelapse and save/build the output?"),
        ("Start Timelapse blocked message handling", "startTimelapseManual"),
    ]
    missing = []
    missing += [f"app.py: {m}" for m in _check_markers(ROOT / "app.py", app_markers)]
    missing += [f"web/static/app.js: {m}" for m in _check_markers(ROOT / "web/static/app.js", js_markers)]
    if missing:
        r.fail("Safety feature static checks")
        for m in missing:
            print(f"  - missing indicator: {m}")
    else:
        r.ok("Safety feature static checks")


def check_requirements_ranges(r: Result) -> None:
    req_path = ROOT / "requirements.txt"
    txt = _read_text_safely(req_path).lower()
    checks = ["flask>=", "requests>=", "opencv-python>=", "numpy>=", "pillow>=", "websocket-client>="]
    missing = [c for c in checks if c not in txt]
    if missing:
        r.fail("Requirements ranges")
        for m in missing:
            print(f"  - missing: {m}")
    else:
        r.ok("Requirements ranges")


def check_launcher(r: Result) -> None:
    problems = []
    if not (ROOT / "Ray5 Pilot.exe").exists():
        problems.append("Ray5 Pilot.exe missing")
    if not (ROOT / "Start_Ray5_Pilot.bat").exists():
        problems.append("Start_Ray5_Pilot.bat missing")
    gi = _read_text_safely(ROOT / ".gitignore")
    if "*.exe" not in gi:
        problems.append(".gitignore missing '*.exe'")
    if "!/Ray5 Pilot.exe" not in gi:
        problems.append(".gitignore missing '!/Ray5 Pilot.exe'")
    if problems:
        r.fail("Launcher checks")
        for p in problems:
            print(f"  - {p}")
    else:
        r.ok("Launcher checks")


def check_git_status(r: Result, require_clean: bool) -> None:
    git = shutil.which("git")
    if not git:
        r.warn("git not available; status check skipped")
        return
    cp = _run([git, "status", "--short"], ROOT)
    if cp.returncode != 0:
        r.fail(f"git status checked ({(cp.stderr or cp.stdout).strip()})")
        return
    out = cp.stdout.strip()
    if out:
        print("  - working tree dirty:")
        for ln in out.splitlines():
            print(f"    {ln}")
        if require_clean:
            r.fail("git status checked (dirty and --require-clean set)")
            return
        r.warn("git working tree is dirty")
    r.ok("git status checked")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ray5 Pilot no-hardware safety/regression check")
    parser.add_argument("--require-clean", action="store_true", help="Fail when git working tree is dirty")
    args = parser.parse_args()

    os.chdir(ROOT)
    print("Ray5 Pilot Safety Check\n")

    r = Result()
    check_python_compile(r)
    check_js_syntax(r)
    check_json(r)
    check_config_key_coverage(r)
    check_version_cache_busting(r)
    check_github_safe_files(r)
    check_secret_scan(r)
    check_firmware_rename(r)
    check_safety_feature_presence(r)
    check_requirements_ranges(r)
    check_launcher(r)
    check_git_status(r, args.require_clean)

    print()
    if r.failures:
        print("Result: FAIL")
        return 1
    print("Result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
