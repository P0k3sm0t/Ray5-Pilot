#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
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

TEXT_EXTS = {
    ".py",
    ".js",
    ".html",
    ".css",
    ".md",
    ".json",
    ".txt",
    ".bat",
    ".yml",
    ".yaml",
    ".ini",
    ".toml",
    "",
}

IGNORE_TEXT_FILES = {"Ray5 Pilot.exe"}

SAFE_PUBLIC_URL_RE = re.compile(
    r"(https://github\.com/P0k3sm0t/Ray5-Pilot|https://raw\.githubusercontent\.com/P0k3sm0t/Ray5-Pilot/|https://api\.github\.com/repos/P0k3sm0t/Ray5-Pilot|https://eu\.longer\.net/pages/download-firmware)",
    re.IGNORECASE,
)

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "rtsp credentials in URL",
        re.compile(r"rtsp://[^/\s:@]+:[^/\s@]+@", re.IGNORECASE),
    ),
    (
        "http/https credentials in URL",
        re.compile(r"https?://[^/\s:@]+:[^/\s@]+@", re.IGNORECASE),
    ),
    (
        "secret assignment keyword",
        re.compile(r"\b(password|passwd|pwd|token|secret|api[_-]?key|pin)\b\s*[:=]\s*(['\"]).{4,}\2", re.IGNORECASE),
    ),
    (
        "private LAN IPv4 literal",
        re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b"),
    ),
]

LOCAL_TERMS_FILE = ROOT / "tools" / "secret_terms.local.txt"


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
            key = f"{prefix}.{k}" if prefix else str(k)
            keys.add(key)
            keys |= _flatten_keys(v, key)
    return keys


def _load_default_config_literal() -> dict:
    source = (ROOT / "config_manager.py").read_text(encoding="utf-8")
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
            print(f"  - extra keys: {len(extra)}")
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
        n = fp.name.lower()
        if n in {".gitkeep", ".gitignore"}:
            continue
        if n.endswith(".pyc"):
            continue
        if "__pycache__" in fp.parts:
            continue
        out.append(fp)
    return out


def check_github_safe_files(r: Result) -> None:
    problems = []
    pycache_found = []
    for rel in ABSENT_PATHS:
        if (ROOT / rel).exists():
            problems.append(f"must be absent: {rel}")
    for rel in RUNTIME_DIRS:
        real_files = _runtime_real_files(ROOT / rel)
        if real_files:
            problems.append(f"runtime dir has files: {rel} ({len(real_files)})")
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
    fixed_files = [
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
    ]
    for fp in fixed_files:
        if fp.exists() and fp.is_file() and fp.name.lower() != "config.json":
            resolved = fp.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield fp
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


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="ignore")


def _load_local_terms() -> list[str]:
    if not LOCAL_TERMS_FILE.exists():
        return []
    terms: list[str] = []
    for line in LOCAL_TERMS_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        terms.append(s)
    return terms


def check_secret_scan(r: Result) -> None:
    hits = []
    local_terms = _load_local_terms()
    placeholder_markers = ("username", "password", "camera_ip", "your_ray5_ip", "example:")
    for fp in _iter_scan_files():
        txt = _read_text(fp)
        lines = txt.splitlines()
        for i, line in enumerate(lines, start=1):
            if SAFE_PUBLIC_URL_RE.search(line):
                continue
            lower_line = line.lower()
            if any(marker in lower_line for marker in placeholder_markers):
                continue
            for label, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    hits.append(f"{fp.relative_to(ROOT)}:{i}: {label}")
            for term in local_terms:
                if term and term in line:
                    hits.append(f"{fp.relative_to(ROOT)}:{i}: local denylist match")
    if hits:
        r.fail("Secret scan")
        for h in hits[:120]:
            print(f"  - {h}")
    else:
        r.ok("Secret scan")


def check_firmware_rename(r: Result) -> None:
    problems = []
    required_hits = 0
    template_files = [ROOT / "web/templates/index.html", ROOT / "web/templates/setup.html", ROOT / "web/templates/machine_settings.html"]
    js_files = [ROOT / "web/static/app.js", ROOT / "web/static/setup.js", ROOT / "web/static/machine_settings.js"]
    for fp in template_files:
        if not fp.exists():
            continue
        txt = _read_text(fp)
        required_hits += txt.count("Firmware Settings")
        if re.search(r"Machine Settings", txt, flags=re.IGNORECASE):
            problems.append(f"{fp.relative_to(ROOT)} contains user-facing 'Machine Settings'")
    for fp in js_files:
        if not fp.exists():
            continue
        txt = _read_text(fp)
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


def _check_markers(path: Path, markers: list[tuple[str, str]]) -> list[str]:
    txt = _read_text(path)
    out = []
    for label, token in markers:
        if token not in txt:
            out.append(label)
    return out


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
        ("status timelapse label field", "timelapse_status_label"),
    ]
    client_markers = [
        ("clear_alarm soft reset step", '"CTRL_X"'),
        ("clear_alarm sends Ctrl-X", '"\\x18"'),
        ("clear_alarm delay after reset", "time.sleep(1.0)"),
        ("clear_alarm sends M5", 'send_gcode("M5")'),
        ("clear_alarm sends $X", 'send_gcode("$X")'),
    ]
    js_markers = [
        ("SD auto-refresh pause busy/lockout", "isMachineBusyForSdRefresh"),
        ("camera setup guard", "Camera is not configured. Set up camera first in Settings."),
        ("single Video/Camera message helper", "function setVideoCardMessage"),
        ("deleted timelapse playback clearing", "Selected timelapse was deleted."),
        ("Stop Timelapse confirmation", "Stop the active timelapse and save/build the output?"),
        ("Start Timelapse blocked message handling", "startTimelapseManual"),
        ("status timelapse renderer", "normalizeTimelapseStatusLabel"),
        ("status timelapse element", "statusTimelapse"),
    ]
    missing = []
    missing += [f"app.py: {x}" for x in _check_markers(ROOT / "app.py", app_markers)]
    missing += [f"web/static/app.js: {x}" for x in _check_markers(ROOT / "web/static/app.js", js_markers)]
    missing += [f"ray5_client.py: {x}" for x in _check_markers(ROOT / "ray5_client.py", client_markers)]
    app_txt = _read_text(ROOT / "app.py")
    if "def _timelapse_dashboard_status_label" in app_txt:
        missing.append("app.py: duplicate timelapse dashboard label helper still present")
    if 'tl_status_label = _timelapse_status_label(tl_state)' not in app_txt:
        missing.append("app.py: /api/status not using canonical _timelapse_status_label")
    if missing:
        r.fail("Safety feature static checks")
        for m in missing:
            print(f"  - missing indicator: {m}")
    else:
        r.ok("Safety feature static checks")


def check_updater_parser_hardening(r: Result) -> None:
    app_path = ROOT / "app.py"
    updater_path = ROOT / "updater.py"
    job_path = ROOT / "job_manager.py"
    gi_path = ROOT / ".gitignore"

    app_markers = [
        ("sidecar checksum support", ".sha256.txt"),
        ("digest fallback support", "github_asset_digest"),
        ("checksum source field", "checksum_source"),
        ("checksum url field", "checksum_url"),
        ("installability flag", "update_installable"),
        ("checksum flag", "checksum_available"),
        ("main-branch install block", "install_source_is_main_branch"),
        ("main.zip/main ref block token", "refs/heads/main"),
        ("rate-limit http handling", "code == 403"),
        ("rate-limit header logging", "X-RateLimit-Limit"),
        ("rate-limit user message", "rate-limited"),
    ]
    updater_markers = [
        ("expected-sha256 argument", "--expected-sha256"),
        ("missing checksum refusal", "Missing expected SHA-256"),
        ("mismatched checksum refusal", "checksum mismatch"),
    ]
    parser_markers = [
        ("G92 handling", "g92_set"),
        ("G92.1 handling", "g92_clear"),
        ("G92 offset tracking", "g92_offset_x"),
        ("segment start captured", "start_x, start_y = x, y"),
        ("segment start included in bounds", "_include_point(min_x, min_y, max_x, max_y, start_x, start_y)"),
        ("segment destination included in bounds", "_include_point(min_x, min_y, max_x, max_y, nx, ny)"),
    ]

    missing = []
    missing += [f"app.py: {x}" for x in _check_markers(app_path, app_markers)]
    missing += [f"updater.py: {x}" for x in _check_markers(updater_path, updater_markers)]
    missing += [f"job_manager.py: {x}" for x in _check_markers(job_path, parser_markers)]

    gi_txt = _read_text(gi_path)
    if "tools/secret_terms.local.txt" not in gi_txt:
        missing.append(".gitignore: missing tools/secret_terms.local.txt ignore")

    if missing:
        r.fail("Updater/parser hardening checks")
        for m in missing:
            print(f"  - missing indicator: {m}")
    else:
        r.ok("Updater/parser hardening checks")


def check_upload_run_hardening(r: Result) -> None:
    app_path = ROOT / "app.py"
    client_path = ROOT / "ray5_client.py"
    monitor_path = ROOT / "ray5_status_monitor.py"
    js_path = ROOT / "web/static/app.js"

    app_markers = [
        ("post-upload verify helper", "_verify_uploaded_file_present_after_timeout"),
        ("http recovery wait helper", "_wait_for_ray5_http_reachable"),
        ("serialized SD list helper", "_ray5_list_files_locked"),
        ("verified-after-timeout flag", "verified_after_timeout"),
        ("upload timeout verify log", "Upload response failed/timed out; verifying whether file exists on SD before blocking start"),
        ("upload verified log", "Upload verified on SD after timeout; continuing with run"),
        ("upload could-not-verify log", "Upload could not be verified on SD after retries; start blocked"),
        ("upload-busy status source", "upload_busy"),
        ("upload-busy stale suppression log", "Suppressing live-status stale fallback while Ray5 is upload-busy"),
        ("upload-busy clear helper", "_clear_ray5_comm_busy"),
        ("unexpected-exception busy clear", "unexpected_exception"),
        ("sd upload busy reason marker", "SD direct upload writing"),
        ("size mismatch warning flag", "size_mismatch_warning"),
        ("size mismatch expected size field", "expected_size"),
        ("size mismatch actual size field", "actual_size"),
        ("size mismatch block message", "file size does not match"),
        ("fallback_offline preserved", "fallback_offline"),
        ("status stale log preserved", "Status stale: no fresh live packet"),
        ("sd_list_lock preserved", "sd_list_lock"),
        ("sha256 filename-aware parser", "expected_filename"),
        ("sha256 broad fallback comment", "Broad fallback: accept the first 64-hex token"),
    ]
    client_markers = [
        ("upload timeout setting", "upload_timeout_seconds"),
        ("upload payload-size timeout logic", "payload_size"),
        ("upload timeout used on upload call", "timeout=upload_timeout_seconds"),
    ]
    js_markers = [
        ("local upload busy helper", "function setLocalUploadBusyStatus"),
        ("Upload+Run progress message", "Upload+Run in progress..."),
        ("Upload progress message", "Upload in progress..."),
        ("Upload+Run backend message/error handling", "r.message || r.error"),
        ("imported Upload uses local busy helper", "setLocalUploadBusyStatus('uploading_to_sd', name"),
        ("SD upload uses local busy helper", "setLocalUploadBusyStatus('uploading_to_sd', file.name"),
    ]

    missing = []
    missing += [f"app.py: {x}" for x in _check_markers(app_path, app_markers)]
    missing += [f"ray5_client.py: {x}" for x in _check_markers(client_path, client_markers)]
    missing += [f"web/static/app.js: {x}" for x in _check_markers(js_path, js_markers)]

    monitor_txt = _read_text(monitor_path)
    if "fallback_offline" not in monitor_txt and "fallback_offline" not in _read_text(app_path):
        missing.append("ray5_status_monitor.py/app.py: missing fallback_offline handling indicator")

    if missing:
        r.fail("Upload+Run hardening checks")
        for m in missing:
            print(f"  - missing indicator: {m}")
    else:
        r.ok("Upload+Run hardening checks")


def check_requirements_ranges(r: Result) -> None:
    txt = _read_text(ROOT / "requirements.txt").lower()
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
    gi = _read_text(ROOT / ".gitignore")
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
    check_updater_parser_hardening(r)
    check_upload_run_hardening(r)
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
