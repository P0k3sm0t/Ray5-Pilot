from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib import request as urlrequest
from urllib.parse import urlsplit

import cv2
from flask import Flask, jsonify, render_template, request, send_file

from camera_manager import CameraCaptureError, CameraManager, mask_camera_url, mjpeg_generator
from config_manager import ConfigManager
from console_log import ConsoleLog
from job_manager import JobManager
from ray5_client import Ray5Client
from ray5_status_monitor import Ray5StatusMonitor

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(BASE_DIR / "web" / "templates"), static_folder=str(BASE_DIR / "web" / "static"))

cfg_mgr = ConfigManager(BASE_DIR)
cfg = cfg_mgr.ensure_config()
console = ConsoleLog()
ray5 = Ray5Client(cfg)
camera = CameraManager(cfg, BASE_DIR)
jobs = JobManager(BASE_DIR, cfg)
_cached_status: dict[str, Any] = {"state": "UNKNOWN", "x": None, "y": None, "z": None, "raw": "", "source": "synthetic"}
_last_logged_status_source: str | None = None
_status_error_logged = False
_watch_stop = threading.Event()
_watch_thread: threading.Thread | None = None
status_monitor: Ray5StatusMonitor | None = None
_placeholder_host_warned = False
_placeholder_api_warned = False
app_state_lock = RLock()
runtime_started = False
timelapse_lock = RLock()
timelapse_capture_lock = RLock()
timelapse_stop_event = threading.Event()
timelapse_thread: threading.Thread | None = None
timelapse_stop_worker: threading.Thread | None = None
timelapse_duplicate_log_at: dict[str, float] = {}
timelapse_state: dict[str, Any] = {
    "enabled": False,
    "armed": False,
    "active": False,
    "paused": False,
    "stopping": False,
    "error": "",
    "job_name": "",
    "job_source": "",
    "control_mode": "",
    "started_at": None,
    "last_snapshot_at": None,
    "interval_seconds": 30,
    "final_capture_delay_seconds": 3.0,
    "playback_fps": 10.0,
    "output_dir": "timelapse",
    "snapshot_count": 0,
    "session_dir": "",
    "session_id": "",
    "stop_pending": False,
    "build_in_progress": False,
    "stop_reason": "",
    "stop_pending_session_id": "",
    "status": "Disabled",
}
system_check_state: dict[str, Any] = {
    "ray5_http_reachable": None,
    "ray5_http_at": None,
    "sd_card_list_working": None,
    "sd_card_list_at": None,
    "camera_test_passed": None,
    "camera_test_at": None,
    "last_auto_check_at": None,
    "auto_check_in_progress": False,
    "last_auto_check_log_at": None,
}
ray5_comm_safety_state: dict[str, Any] = {
    "comm_lost_during_job": False,
    "last_known_machine_state": "",
    "last_job_start_time": None,
    "last_comm_ok_time": None,
    "message": "",
    "entered_at": None,
    "last_skip_log_at": None,
}
github_update_status: dict[str, Any] = {
    "checked": False,
    "checking": False,
    "ok": None,
    "current_version": "unknown",
    "latest_version": "",
    "update_available": False,
    "message": "Checking...",
    "checked_at": None,
    "last_checked": None,
    "error": "",
    "release_url": GITHUB_REPO_URL if "GITHUB_REPO_URL" in globals() else "",
    "source_zip_url": "",
    "source_zip_sha256": "",
    "checksum_source": "",
    "checksum_url": "",
    "checksum_available": False,
    "update_installable": False,
}
github_update_check_started = False
github_update_lock = RLock()
github_update_check_thread: threading.Thread | None = None
GITHUB_UPDATE_CACHE_TTL_SECONDS = 1800.0
camera_stream_clients = 0
camera_stream_clients_lock = RLock()
console.add("info", f"CONFIG PATH: {cfg_mgr.config_path}")
console.add("info", f"CONFIG EXISTS: {cfg_mgr.config_path.exists()}")
console.add("info", f"RAY5 HOST: {cfg.get('ray5', {}).get('host', '')}")
console.add("info", f"RAY5 PORT: {cfg.get('ray5', {}).get('port', '')}")
console.add("info", f"RAY5 BASE URL: {ray5._base()}")


_SENSITIVE_DEBUG_TOKENS = ("password", "pass", "key", "token", "secret", "credential", "auth")
GITHUB_REPO_URL = "https://github.com/P0k3sm0t/Ray5-Pilot"
GITHUB_SOURCE_ZIP_FALLBACK_URL = "https://github.com/P0k3sm0t/Ray5-Pilot/archive/refs/heads/main.zip"
GITHUB_MAIN_VERSION_URL = "https://raw.githubusercontent.com/P0k3sm0t/Ray5-Pilot/main/VERSION"
GITHUB_LATEST_RELEASE_API_URL = "https://api.github.com/repos/P0k3sm0t/Ray5-Pilot/releases/latest"
UPDATE_STATUS_PATH = BASE_DIR / "update_logs" / "update_status.json"
_update_shutdown_started = False
calibration_lock = RLock()
calibration_process: subprocess.Popen[Any] | None = None


def _is_sensitive_key(name: str) -> bool:
    n = str(name or "").strip().lower()
    return any(tok in n for tok in _SENSITIVE_DEBUG_TOKENS)


def _sanitize_debug_value(key: str, value: str) -> str:
    if _is_sensitive_key(key):
        return "******"
    v = str(value or "").strip()
    if any(tok in v.lower() for tok in _SENSITIVE_DEBUG_TOKENS):
        return "******"
    return v


def _sanitize_debug_obj(obj: Any, key_name: str = "") -> Any:
    if isinstance(obj, dict):
        # ESP400 entries often describe field identity in P/H/F/K then store value in V.
        descriptor = " ".join(
            [
                str(obj.get("P", "")),
                str(obj.get("H", "")),
                str(obj.get("F", "")),
                str(obj.get("K", "")),
                str(obj.get("name", "")),
                str(obj.get("path", "")),
            ]
        ).lower()
        descriptor_sensitive = any(tok in descriptor for tok in _SENSITIVE_DEBUG_TOKENS)
        out: dict[str, Any] = {}
        for k, v in obj.items():
            k_str = str(k)
            if _is_sensitive_key(k_str):
                out[k_str] = "******"
                continue
            if k_str == "V" and descriptor_sensitive:
                out[k_str] = "******"
                continue
            out[k_str] = _sanitize_debug_obj(v, key_name=k_str)
        return out
    if isinstance(obj, list):
        return [_sanitize_debug_obj(item, key_name=key_name) for item in obj]
    if isinstance(obj, str):
        return _sanitize_debug_value(key_name, obj)
    return obj


def _parse_and_sanitize_esp400(raw: str) -> Any:
    txt = str(raw or "").strip()
    if txt.startswith("{") or txt.startswith("["):
        try:
            parsed = json.loads(txt)
            return _sanitize_debug_obj(parsed)
        except Exception:
            pass
    lines: list[dict[str, str]] = []
    for ln in txt.replace("\r", "\n").split("\n"):
        s = ln.strip()
        if not s:
            continue
        if "=" in s:
            k, v = s.split("=", 1)
            key = k.strip()
            val = _sanitize_debug_value(key, v)
            lines.append({"K": key, "V": val})
        else:
            lines.append({"K": s, "V": ""})
    return lines


def _sanitize_plain_text_lines(raw: str) -> list[str]:
    out: list[str] = []
    for ln in str(raw or "").replace("\r", "\n").split("\n"):
        s = ln.strip()
        if not s:
            continue
        if ":" in s:
            k, v = s.split(":", 1)
            key = k.strip()
            val = _sanitize_debug_value(key, v)
            out.append(f"{key}: {val}")
        elif "=" in s:
            k, v = s.split("=", 1)
            key = k.strip()
            val = _sanitize_debug_value(key, v)
            out.append(f"{key}={val}")
        else:
            if any(tok in s.lower() for tok in _SENSITIVE_DEBUG_TOKENS):
                out.append("******")
            else:
                out.append(s)
    return out


def _normalize_version_text(value: str) -> str:
    txt = str(value or "").strip().lstrip("\ufeff")
    if txt.lower().startswith("v"):
        txt = txt[1:]
    return txt


def _parse_version_parts(value: str) -> tuple[int, ...]:
    core = _normalize_version_text(value).split("-", 1)[0].strip()
    if not re.fullmatch(r"\d+(?:\.\d+)*", core):
        return tuple()
    parts = [int(token) for token in core.split(".")]
    return tuple(parts)


def _compare_versions(current: str, latest: str) -> int:
    cur = list(_parse_version_parts(current))
    lat = list(_parse_version_parts(latest))
    if not cur or not lat:
        return 0
    while len(cur) < len(lat):
        cur.append(0)
    while len(lat) < len(cur):
        lat.append(0)
    if cur < lat:
        return -1
    if cur > lat:
        return 1
    return 0


def _read_local_version() -> str:
    try:
        return _normalize_version_text((BASE_DIR / "VERSION").read_text(encoding="utf-8").strip())
    except Exception:
        return ""


def _fetch_remote_main_version(timeout_seconds: float = 5.0) -> str:
    req = urlrequest.Request(
        GITHUB_MAIN_VERSION_URL,
        headers={"User-Agent": "Ray5-Pilot-UpdateCheck"},
        method="GET",
    )
    with urlrequest.urlopen(req, timeout=timeout_seconds) as resp:
        raw = resp.read().decode("utf-8", errors="replace").strip()
    return _normalize_version_text(raw)


def _extract_sha256_from_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    patterns = [
        r"\bsha256\s*[:=]\s*([0-9a-f]{64})\b",
        r"\bSHA256\s*[:=]\s*([0-9A-F]{64})\b",
        r"\b([0-9a-f]{64})\b",
    ]
    for pat in patterns:
        m = re.search(pat, raw, flags=re.IGNORECASE)
        if m:
            return str(m.group(1)).strip().lower()
    return ""


def _log_github_http_diagnostics(err: HTTPError) -> None:
    code = int(getattr(err, "code", 0) or 0)
    if code == 403:
        headers = getattr(err, "headers", None)
        limit = headers.get("X-RateLimit-Limit") if headers else None
        remaining = headers.get("X-RateLimit-Remaining") if headers else None
        reset = headers.get("X-RateLimit-Reset") if headers else None
        console.add(
            "warn",
            f"GitHub update check 403 (rate-limited or forbidden). "
            f"X-RateLimit-Limit={limit or 'n/a'} "
            f"X-RateLimit-Remaining={remaining or 'n/a'} "
            f"X-RateLimit-Reset={reset or 'n/a'}",
        )
        return
    if code == 404:
        console.add("warn", "GitHub update check 404: no release found for this repository.")
        return
    console.add("warn", f"GitHub update check HTTP error: {code} {err.reason}")


def _fetch_latest_release_update_info(timeout_seconds: float = 8.0) -> dict[str, Any]:
    req = urlrequest.Request(
        GITHUB_LATEST_RELEASE_API_URL,
        headers={"User-Agent": "Ray5-Pilot-UpdateCheck", "Accept": "application/vnd.github+json"},
        method="GET",
    )
    with urlrequest.urlopen(req, timeout=timeout_seconds) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected latest release payload.")
    tag = _normalize_version_text(str(payload.get("tag_name") or payload.get("name") or "").strip())
    if not tag:
        raise RuntimeError("Latest release tag is missing.")
    release_url = str(payload.get("html_url") or GITHUB_REPO_URL).strip() or GITHUB_REPO_URL
    assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    zip_candidates: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "").strip().lower()
        url = str(asset.get("browser_download_url") or "").strip()
        if not url or not name.endswith(".zip"):
            continue
        zip_candidates.append(asset)
    latest_lower = latest = str(tag).strip().lower()
    preferred_names = {
        f"ray5-pilot-v{latest_lower}.zip",
        f"ray5-pilot-{latest_lower}.zip",
    }
    zip_asset: dict[str, Any] | None = None
    for asset in zip_candidates:
        name = str(asset.get("name") or "").strip().lower()
        if name in preferred_names:
            zip_asset = asset
            break
    if zip_asset is None:
        for asset in zip_candidates:
            name = str(asset.get("name") or "").strip().lower()
            if name.startswith("ray5-pilot") and name.endswith(".zip"):
                zip_asset = asset
                break
    if zip_asset is None and zip_candidates:
        zip_asset = zip_candidates[0]
    source_zip_url = ""
    source_zip_sha256 = ""
    install_metadata_missing = False
    checksum_source = ""
    checksum_url = ""
    if zip_asset:
        zip_name = str(zip_asset.get("name") or "").strip()
        source_zip_url = str(zip_asset.get("browser_download_url") or "").strip()
        sidecar_names = [
            f"{zip_name}.sha256.txt",
            f"{zip_name}.sha256",
            f"Ray5-Pilot-v{tag}.sha256.txt",
            f"ray5-pilot-v{tag}.sha256.txt",
        ]
        sidecar_asset: dict[str, Any] | None = None
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            aname = str(asset.get("name") or "").strip()
            if not aname:
                continue
            if any(aname.lower() == s.lower() for s in sidecar_names):
                sidecar_asset = asset
                break
        if sidecar_asset is None:
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                aname = str(asset.get("name") or "").strip().lower()
                if aname.endswith(".sha256.txt") or aname.endswith(".sha256"):
                    if zip_name.lower() in aname or f"v{tag}".lower() in aname:
                        sidecar_asset = asset
                        break
        if sidecar_asset is not None:
            checksum_url = str(sidecar_asset.get("browser_download_url") or "").strip()
            try:
                req = urlrequest.Request(
                    checksum_url,
                    headers={"User-Agent": "Ray5-Pilot-UpdateCheck"},
                    method="GET",
                )
                with urlrequest.urlopen(req, timeout=timeout_seconds) as resp:
                    sidecar_text = resp.read().decode("utf-8", errors="replace")
                parsed = _extract_sha256_from_text(sidecar_text)
                if parsed:
                    source_zip_sha256 = parsed
                    checksum_source = "sidecar"
            except Exception as exc:
                console.add("warn", f"Release checksum sidecar read failed: {exc}")
        if not source_zip_sha256:
            digest_raw = str(zip_asset.get("digest") or "").strip()
            parsed = _extract_sha256_from_text(digest_raw)
            if parsed:
                source_zip_sha256 = parsed
                checksum_source = "github_asset_digest"
        if not source_zip_sha256:
            install_metadata_missing = True
    else:
        install_metadata_missing = True
    return {
        "tag": tag,
        "release_url": release_url,
        "source_zip_url": source_zip_url,
        "source_zip_sha256": source_zip_sha256,
        "checksum_source": checksum_source,
        "checksum_url": checksum_url,
        "install_metadata_missing": bool(install_metadata_missing),
    }


def _check_source_update() -> dict[str, Any]:
    current_version = _read_local_version()
    latest_version = ""
    try:
        release_info = _fetch_latest_release_update_info(timeout_seconds=8.0)
        latest_version = str(release_info.get("tag") or "").strip()
        cmp_result = _compare_versions(current_version, latest_version)
        update_available = cmp_result < 0
        source_zip_url = str(release_info.get("source_zip_url") or "").strip()
        source_zip_sha256 = str(release_info.get("source_zip_sha256") or "").strip().lower()
        checksum_available = bool(re.fullmatch(r"[0-9a-f]{64}", source_zip_sha256))
        has_install_metadata = bool(source_zip_url and checksum_available)
        update_installable = bool(update_available and has_install_metadata)
        install_metadata_missing = bool(release_info.get("install_metadata_missing", False)) or not has_install_metadata
        if update_available and update_installable:
            message = f"Source update available: {latest_version}"
        elif update_available and install_metadata_missing:
            message = "Update available, but in-app install is blocked because the release ZIP/checksum asset is missing."
        elif install_metadata_missing:
            message = "Ray5 Pilot is up to date. In-app install metadata is unavailable."
        else:
            message = "Ray5 Pilot source is up to date."
        return {
            "ok": True,
            "current_version": current_version,
            "latest_version": latest_version,
            "latest_tag": latest_version,
            "update_available": update_available,
            "release_url": str(release_info.get("release_url") or GITHUB_REPO_URL),
            "source_zip_url": source_zip_url,
            "source_zip_sha256": source_zip_sha256,
            "checksum_available": checksum_available,
            "update_installable": update_installable,
            "install_metadata_missing": install_metadata_missing,
            "message": message,
        }
    except HTTPError as exc:
        _log_github_http_diagnostics(exc)
        message = "Unable to check for updates right now."
        if int(getattr(exc, "code", 0) or 0) == 403:
            message = "GitHub update check was rate-limited. Try again later."
        elif int(getattr(exc, "code", 0) or 0) == 404:
            message = "No GitHub release was found for update checking."
        return {
            "ok": False,
            "current_version": current_version,
            "latest_version": latest_version,
            "latest_tag": "",
            "update_available": False,
            "release_url": GITHUB_REPO_URL,
            "source_zip_url": "",
            "source_zip_url_fallback": GITHUB_SOURCE_ZIP_FALLBACK_URL,
            "source_zip_sha256": "",
            "checksum_source": "",
            "checksum_url": "",
            "message": message,
        }
    except URLError as exc:
        console.add("warn", f"GitHub update check network failure: {exc}")
        return {
            "ok": False,
            "current_version": current_version,
            "latest_version": latest_version,
            "latest_tag": "",
            "update_available": False,
            "release_url": GITHUB_REPO_URL,
            "source_zip_url": "",
            "source_zip_url_fallback": GITHUB_SOURCE_ZIP_FALLBACK_URL,
            "source_zip_sha256": "",
            "checksum_source": "",
            "checksum_url": "",
            "message": "Unable to check for updates right now.",
        }
    except Exception as exc:
        console.add("warn", f"GitHub update check failed: {exc}")
        return {
            "ok": False,
            "current_version": current_version,
            "latest_version": latest_version,
            "latest_tag": "",
            "update_available": False,
            "release_url": GITHUB_REPO_URL,
            "source_zip_url": "",
            "source_zip_url_fallback": GITHUB_SOURCE_ZIP_FALLBACK_URL,
            "source_zip_sha256": "",
            "checksum_source": "",
            "checksum_url": "",
            "message": "Unable to check for updates right now.",
        }


def _snapshot_startup_update_status() -> dict[str, Any]:
    with app_state_lock:
        return dict(github_update_status)


def _github_update_cache_snapshot() -> dict[str, Any]:
    with app_state_lock:
        return dict(github_update_status)


def _update_github_check_cache_from_result(result: dict[str, Any], checking: bool = False) -> dict[str, Any]:
    checked_at_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    checked_at_epoch = time.time()
    current_version = str(result.get("current_version") or result.get("local_version") or _read_local_version() or "unknown")
    latest_version = str(result.get("latest_version") or "").strip()
    ok = bool(result.get("ok"))
    update_available = bool(result.get("update_available"))
    release_url = str(result.get("release_url") or GITHUB_REPO_URL)
    source_zip_url = str(result.get("source_zip_url") or "")
    source_zip_sha256 = str(result.get("source_zip_sha256") or "").strip().lower()
    checksum_source = str(result.get("checksum_source") or "").strip()
    checksum_url = str(result.get("checksum_url") or "").strip()
    checksum_available = bool(result.get("checksum_available")) if ("checksum_available" in result) else bool(re.fullmatch(r"[0-9a-f]{64}", source_zip_sha256))
    update_installable = bool(result.get("update_installable")) if ("update_installable" in result) else bool(update_available and checksum_available and source_zip_url)
    install_metadata_missing = bool(result.get("install_metadata_missing", False))
    payload: dict[str, Any] = {
        "checked": True,
        "checking": bool(checking),
        "ok": ok,
        "current_version": current_version,
        "local_version": current_version,
        "latest_version": latest_version,
        "update_available": update_available,
        "checked_at": checked_at_iso,
        "last_checked": checked_at_epoch,
        "release_url": release_url,
        "source_zip_url": source_zip_url,
        "source_zip_url_fallback": GITHUB_SOURCE_ZIP_FALLBACK_URL,
        "source_zip_sha256": source_zip_sha256,
        "checksum_source": checksum_source,
        "checksum_url": checksum_url,
        "checksum_available": checksum_available,
        "update_installable": update_installable,
        "install_metadata_missing": install_metadata_missing,
        "error": "",
    }
    if ok:
        message = str(result.get("message") or "").strip()
        if message:
            payload["message"] = message
        elif update_available and not update_installable:
            payload["message"] = "Update available, but in-app install is blocked because the release ZIP/checksum asset is missing."
        else:
            payload["message"] = f"Update available: {latest_version or 'latest'}" if update_available else "Up to date"
    else:
        payload["message"] = "Unable to check"
        payload["error"] = str(result.get("message") or "Unable to check for updates right now.")
    with app_state_lock:
        github_update_status.update(payload)
        return dict(github_update_status)


def _github_update_refresh_needed(snapshot: dict[str, Any] | None = None, ttl_seconds: float = GITHUB_UPDATE_CACHE_TTL_SECONDS) -> bool:
    s = snapshot if isinstance(snapshot, dict) else _github_update_cache_snapshot()
    if bool(s.get("checking", False)):
        return False
    if not bool(s.get("checked", False)):
        return True
    last_checked_raw = s.get("last_checked")
    try:
        last_checked = float(last_checked_raw)
    except Exception:
        return True
    return (time.time() - last_checked) > max(30.0, float(ttl_seconds))


def _run_github_update_check_worker() -> None:
    global github_update_check_thread
    result = _check_source_update()
    _update_github_check_cache_from_result(result, checking=False)
    with github_update_lock:
        github_update_check_thread = None


def _start_github_update_check(force: bool = False, ttl_seconds: float = GITHUB_UPDATE_CACHE_TTL_SECONDS) -> dict[str, Any]:
    global github_update_check_thread
    with github_update_lock:
        snapshot = _github_update_cache_snapshot()
        thread_alive = bool(github_update_check_thread is not None and github_update_check_thread.is_alive())
        if thread_alive:
            return snapshot
        if not force and not _github_update_refresh_needed(snapshot, ttl_seconds=ttl_seconds):
            return snapshot
        with app_state_lock:
            github_update_status["checking"] = True
            github_update_status["message"] = "Checking..."
        t = threading.Thread(target=_run_github_update_check_worker, daemon=True, name="github-update-check")
        github_update_check_thread = t
        t.start()
        return _github_update_cache_snapshot()


def _start_startup_update_check() -> None:
    global github_update_check_started
    with app_state_lock:
        if github_update_check_started:
            return
        github_update_check_started = True
    _start_github_update_check(force=True)


def _get_machine_state_for_update_guard() -> str:
    with app_state_lock:
        active_monitor = status_monitor
        active_cfg = cfg
    st_cfg = active_cfg.get("status", {}) if isinstance(active_cfg.get("status"), dict) else {}
    prefer_live = bool(st_cfg.get("prefer_live_status", True))
    if not active_monitor or not prefer_live:
        return "UNKNOWN"
    latest = active_monitor.get_latest_status() or {}
    return str(latest.get("state") or "UNKNOWN").strip()


def _delayed_process_exit(delay_seconds: float = 0.8) -> None:
    global _update_shutdown_started
    if _update_shutdown_started:
        return
    _update_shutdown_started = True

    def _shutdown_worker() -> None:
        time.sleep(max(0.2, float(delay_seconds)))
        try:
            console.add("warn", "Ray5 Pilot shutting down for updater handoff.")
        except Exception:
            pass
        os._exit(0)

    t = threading.Thread(target=_shutdown_worker, daemon=True, name="update-shutdown")
    t.start()


def reload_components() -> None:
    global cfg, ray5, camera, jobs, status_monitor, _placeholder_api_warned, _placeholder_host_warned
    tl_state = _timelapse_snapshot_state()
    if bool(tl_state.get("active", False)) or bool(tl_state.get("paused", False)) or bool(tl_state.get("armed", False)):
        # Intentionally synchronous: we stop timelapse before swapping runtime objects so the
        # worker cannot continue capturing against stale camera/job references.
        stop_result = _timelapse_stop_internal(reason="settings_reload")
        if not bool(stop_result.get("ok")):
            msg = str(stop_result.get("message", "Unable to stop timelapse before settings reload.")).strip()
            console.add("warn", f"Settings reload blocked: {msg}")
            raise RuntimeError(msg)
        console.add("info", "Timelapse stopped because Settings were reloaded.")

    new_cfg = cfg_mgr.load()
    new_ray5 = Ray5Client(new_cfg)
    new_camera = CameraManager(new_cfg, BASE_DIR)
    new_jobs = JobManager(BASE_DIR, new_cfg)
    new_monitor: Ray5StatusMonitor | None = None
    if _is_ray5_host_configured(new_cfg):
        new_monitor = Ray5StatusMonitor(new_ray5, new_cfg, console)
        new_ray5.set_page_id_getter(new_monitor.get_page_id)
    else:
        new_ray5.set_page_id_getter(lambda: None)

    with app_state_lock:
        old_monitor = status_monitor
        cfg = new_cfg
        ray5 = new_ray5
        camera = new_camera
        jobs = new_jobs
        status_monitor = new_monitor
        _placeholder_api_warned = False
        _placeholder_host_warned = False

    _stop_watch_thread()
    if old_monitor is not None:
        try:
            old_monitor.stop()
        except Exception as exc:
            console.add("warn", f"Status monitor stop warning during reload: {exc}")
    if new_monitor is not None:
        try:
            new_monitor.start()
        except Exception as exc:
            console.add("error", f"Status monitor start failed after reload: {exc}")
    else:
        _warn_placeholder_host_once()
    console.add("info", f"CONFIG PATH: {cfg_mgr.config_path}")
    console.add("info", f"RAY5 HOST: {new_cfg.get('ray5', {}).get('host', '')}")
    console.add("info", f"RAY5 PORT: {new_cfg.get('ray5', {}).get('port', '')}")
    console.add("info", f"RAY5 BASE URL: {new_ray5._base()}")
    _warn_if_non_local_bind()
    ensure_runtime_directories(new_cfg)
    _ensure_watch_thread()


def _status_fallback(live: dict[str, Any]) -> dict[str, Any]:
    global _cached_status
    if live.get("ok") and live.get("parsed"):
        parsed = live["parsed"]
        _cached_status = {
            "state": parsed.get("state") or "UNKNOWN",
            "x": parsed.get("x"),
            "y": parsed.get("y"),
            "z": parsed.get("z"),
            "raw": live.get("raw", ""),
            "source": "live" if live.get("raw") else "cache",
        }
        return _cached_status
    if _cached_status.get("raw"):
        s = dict(_cached_status)
        s["source"] = "cache"
        return s
    return {"state": "UNKNOWN", "x": None, "y": None, "z": None, "raw": "", "source": "synthetic"}


def _watch_loop() -> None:
    with app_state_lock:
        active_jobs = jobs
    console.add("info", f"Watcher started: {active_jobs.watched_dir.name} -> {active_jobs.imported_dir.name}")
    while not _watch_stop.is_set():
        try:
            with app_state_lock:
                active_cfg = cfg
                active_jobs = jobs
            jobs_cfg = active_cfg.get("jobs", {})
            if bool(jobs_cfg.get("watch_enabled", True)):
                imported = active_jobs.poll_watched_imports()
                for item in imported:
                    if item.get("rejected"):
                        console.add(
                            "error",
                            f"G-code safety scan failed: {item.get('name','unknown')} blocked as 3D printer G-code; "
                            f"matches={','.join(item.get('matches', []))}",
                        )
                        continue
                    src = item.get("source_name", item.get("name"))
                    dst = item.get("name")
                    if item.get("removed_source", False):
                        console.add("info", f"Imported watched job: source={src} dest={dst}; removed source")
                    else:
                        console.add("info", f"Imported watched job: source={src} dest={dst}")
            poll_seconds = max(1.0, float(jobs_cfg.get("watch_poll_seconds", 3)))
        except Exception as exc:
            console.add("error", f"Watch poller error: {exc}")
            poll_seconds = 3.0
        _watch_stop.wait(poll_seconds)


def _ensure_watch_thread() -> None:
    global _watch_thread
    with app_state_lock:
        active_jobs = jobs
        thread_running = _watch_thread is not None and _watch_thread.is_alive()
    if thread_running:
        return
    if active_jobs.watched_dir.resolve() == active_jobs.imported_dir.resolve():
        console.add("error", "Watcher disabled: watched_gcode_dir and imported_jobs_dir are the same folder")
        return
    _watch_stop.clear()
    new_thread = threading.Thread(target=_watch_loop, daemon=True, name="watched-folder-poller")
    with app_state_lock:
        _watch_thread = new_thread
    new_thread.start()


def _stop_watch_thread() -> None:
    global _watch_thread
    with app_state_lock:
        thread = _watch_thread
    if thread is None:
        return
    _watch_stop.set()
    try:
        thread.join(timeout=2.0)
    except Exception:
        pass
    if thread.is_alive():
        console.add("warn", "Watcher stop timeout: previous watched-folder thread still alive; keeping stop event set.")
        return
    with app_state_lock:
        _watch_thread = None
    _watch_stop.clear()


def _warn_if_non_local_bind() -> None:
    with app_state_lock:
        active_cfg = cfg
    host = str(active_cfg.get("web_ui", {}).get("host", "127.0.0.1")).strip().lower()
    if host not in {"127.0.0.1", "localhost"}:
        console.add("warn", "Web UI is bound to a non-local host. Ray5 Pilot exposes machine-control endpoints without authentication.")


def _max_upload_bytes() -> int:
    with app_state_lock:
        active_cfg = cfg
    limits = active_cfg.get("limits", {}) if isinstance(active_cfg.get("limits"), dict) else {}
    return int(float(limits.get("max_gcode_upload_mb", 50)) * 1024 * 1024)


def _set_system_check_flag(key: str, value: bool | None) -> None:
    with app_state_lock:
        system_check_state[key] = value
        system_check_state[f"{key}_at"] = time.time() if value is not None else None


def _set_camera_check_result(ok: bool | None, reason: str = "") -> None:
    _set_system_check_flag("camera_test_passed", ok)
    if reason:
        level = "info" if ok is True else ("warn" if ok is False else "info")
        console.add(level, f"Camera health update: {reason}")


def _record_job_activity(source: str, name: str = "") -> None:
    now = time.time()
    with app_state_lock:
        ray5_comm_safety_state["last_job_start_time"] = now
        if not ray5_comm_safety_state.get("last_known_machine_state"):
            ray5_comm_safety_state["last_known_machine_state"] = "Run"
    console.add("warn", f"Job activity recorded source={source} name={name or 'unknown'}")


def _is_machine_active_state(state: str) -> bool:
    s = str(state or "").strip().lower().split(":", 1)[0]
    return s in {"run", "hold", "jog", "door"}


def _is_recent_job_activity(now: float | None = None) -> bool:
    ts = ray5_comm_safety_state.get("last_job_start_time")
    if not isinstance(ts, (int, float)):
        return False
    now_ts = float(now if isinstance(now, (int, float)) else time.time())
    return (now_ts - float(ts)) <= 180.0


def _update_comm_safety_state(status_source: str, online: bool, state_base: str) -> None:
    now = time.time()
    source = str(status_source or "").strip().lower()
    state = str(state_base or "").strip()
    state_norm = state.lower().split(":", 1)[0] if state else ""
    entered = False
    with app_state_lock:
        if source == "live_websocket" and bool(online):
            ray5_comm_safety_state["last_comm_ok_time"] = now
            if state:
                ray5_comm_safety_state["last_known_machine_state"] = state
            if state_norm == "idle":
                ray5_comm_safety_state["last_job_start_time"] = None
        comm_lost = bool(ray5_comm_safety_state.get("comm_lost_during_job", False))
        last_known = str(ray5_comm_safety_state.get("last_known_machine_state", "") or "")
        active_or_recent = _is_machine_active_state(last_known) or _is_recent_job_activity(now)
        comm_unavailable = source in {"offline", "fallback_offline", "synthetic"} or not bool(online)
        if (not comm_lost) and comm_unavailable and active_or_recent:
            ray5_comm_safety_state["comm_lost_during_job"] = True
            ray5_comm_safety_state["message"] = (
                "Communication was lost while a job may have been active. "
                "Verify the Ray5 screen and machine state before continuing."
            )
            ray5_comm_safety_state["entered_at"] = now
            entered = True
    if entered:
        console.add("warn", "Communication-loss safety lockout entered (job may have been active).")


def _snapshot_comm_safety_state() -> dict[str, Any]:
    with app_state_lock:
        snap = dict(ray5_comm_safety_state)
    return {
        "comm_lost_during_job": bool(snap.get("comm_lost_during_job", False)),
        "last_known_machine_state": str(snap.get("last_known_machine_state", "") or ""),
        "last_job_start_time": snap.get("last_job_start_time"),
        "last_comm_ok_time": snap.get("last_comm_ok_time"),
        "message": str(snap.get("message", "") or ""),
        "entered_at": snap.get("entered_at"),
        "requires_ack": bool(snap.get("comm_lost_during_job", False)),
    }


def _run_system_check_probe() -> None:
    try:
        with app_state_lock:
            active_cfg = cfg
            system_check_state["auto_check_in_progress"] = True
            system_check_state["last_auto_check_at"] = time.time()
        if not _is_ray5_host_configured(active_cfg):
            return
        if bool(ray5_comm_safety_state.get("comm_lost_during_job", False)):
            now = time.time()
            with app_state_lock:
                last_log = ray5_comm_safety_state.get("last_skip_log_at")
                if (last_log is None) or ((now - float(last_log)) >= 60.0):
                    ray5_comm_safety_state["last_skip_log_at"] = now
                    console.add("warn", "System-check SD probe skipped due to communication-loss safety lockout.")
            return

        # Lightweight HTTP reachability probe.
        http_ok = bool(ray5.connectivity().get("connected"))
        _set_system_check_flag("ray5_http_reachable", http_ok)
        if not http_ok:
            return

        # Reuse existing SD listing method to update SD health without touching UI state.
        req_path = str(active_cfg.get("ray5", {}).get("sd_path", "/") or "/")
        sd_res = ray5.list_files(path=req_path)
        _set_system_check_flag("sd_card_list_working", bool(sd_res.get("ok")))
        if sd_res.get("ok"):
            _set_system_check_flag("ray5_http_reachable", True)
    except Exception as exc:
        with app_state_lock:
            now = time.time()
            last_log = system_check_state.get("last_auto_check_log_at")
            should_log = (last_log is None) or ((now - float(last_log)) >= 60.0)
            if should_log:
                system_check_state["last_auto_check_log_at"] = now
        if should_log:
            console.add("warn", f"System check auto-probe warning: {exc}")
    finally:
        with app_state_lock:
            system_check_state["auto_check_in_progress"] = False


def _schedule_system_check_probe() -> None:
    with app_state_lock:
        active_cfg = cfg
        if not _is_ray5_host_configured(active_cfg):
            return
        if bool(system_check_state.get("auto_check_in_progress", False)):
            return
        now = time.time()
        last = system_check_state.get("last_auto_check_at")
        interval = 20.0
        if isinstance(last, (int, float)) and (now - float(last) < interval):
            return
        system_check_state["auto_check_in_progress"] = True
    threading.Thread(target=_run_system_check_probe, name="system-check-probe", daemon=True).start()


def _is_ray5_host_configured(config: dict[str, Any] | None = None) -> bool:
    if config is None:
        with app_state_lock:
            config = cfg
    host = str(config.get("ray5", {}).get("host", "")).strip()
    return bool(host) and host.upper() != "YOUR_RAY5_IP"


def _resolve_runtime_dir(path_like: str | Path) -> Path:
    p = Path(path_like)
    if p.is_absolute():
        return p
    return (BASE_DIR / p).resolve()


def ensure_runtime_directories(config: dict[str, Any] | None = None) -> None:
    if config is None:
        with app_state_lock:
            config = cfg
    jobs_cfg = config.get("jobs", {}) if isinstance(config.get("jobs"), dict) else {}
    camera_cfg = config.get("camera", {}) if isinstance(config.get("camera"), dict) else {}
    timelapse_cfg = config.get("timelapse", {}) if isinstance(config.get("timelapse"), dict) else {}
    dirs: dict[str, Path] = {
        "imported_jobs": _resolve_runtime_dir(str(jobs_cfg.get("imported_jobs_dir", "imported_jobs") or "imported_jobs")),
        "watched_gcode": _resolve_runtime_dir(str(jobs_cfg.get("watched_gcode_dir", "watched_gcode") or "watched_gcode")),
        "rejected_jobs": _resolve_runtime_dir(str(jobs_cfg.get("rejected_jobs_dir", "rejected_jobs") or "rejected_jobs")),
        "logs": _resolve_runtime_dir("logs"),
        "camera_captures": _resolve_runtime_dir(str(camera_cfg.get("output_dir", "camera_captures") or "camera_captures")),
        "timelapse": _resolve_runtime_dir(str(timelapse_cfg.get("output_dir", "timelapse") or "timelapse")),
    }
    created: list[str] = []
    for name, directory in dirs.items():
        existed = directory.exists()
        directory.mkdir(parents=True, exist_ok=True)
        if not existed:
            created.append(f"{name}={directory}")
    if created:
        console.add("info", "Runtime folders created: " + ", ".join(created))


def _warn_placeholder_host_once() -> None:
    global _placeholder_host_warned
    with app_state_lock:
        if _placeholder_host_warned:
            return
        _placeholder_host_warned = True
    console.add("warn", "Ray5 host is still placeholder; configure Settings > Ray5 Network.")


def _require_ray5_configured():
    global _placeholder_api_warned
    if _is_ray5_host_configured():
        return None
    with app_state_lock:
        should_log = not _placeholder_api_warned
        if should_log:
            _placeholder_api_warned = True
    if should_log:
        console.add("warn", "Ray5 API request blocked because host is not configured.")
    return (
        jsonify(
            {
                "ok": False,
                "message": "Ray5 host is not configured. Set ray5.host in Settings.",
                "not_configured": True,
            }
        ),
        400,
    )

if _is_ray5_host_configured():
    status_monitor = Ray5StatusMonitor(ray5, cfg, console)
    ray5.set_page_id_getter(status_monitor.get_page_id)
else:
    _warn_placeholder_host_once()
    status_monitor = None
    ray5.set_page_id_getter(lambda: None)


def start_runtime() -> None:
    global runtime_started
    with app_state_lock:
        if runtime_started:
            return
        active_monitor = status_monitor
        runtime_started = True
    _warn_if_non_local_bind()
    with app_state_lock:
        active_cfg = cfg
    ensure_runtime_directories(active_cfg)
    _start_startup_update_check()
    _ensure_watch_thread()
    if active_monitor is not None:
        try:
            active_monitor.start()
        except Exception as exc:
            console.add("error", f"Status monitor start failed: {exc}")
    else:
        _warn_placeholder_host_once()


def stop_runtime() -> None:
    global runtime_started
    with app_state_lock:
        if not runtime_started:
            return
        active_monitor = status_monitor
        runtime_started = False
    _stop_watch_thread()
    if active_monitor is not None:
        try:
            active_monitor.stop()
        except Exception as exc:
            console.add("warn", f"Status monitor stop warning: {exc}")
    try:
        _timelapse_stop_internal(reason="runtime_stop")
    except Exception as exc:
        console.add("warn", f"Timelapse stop warning: {exc}")


def _camera_cfg(config: dict[str, Any] | None = None) -> dict[str, Any]:
    if config is None:
        with app_state_lock:
            config = cfg
    c = config.get("camera", {}) if isinstance(config.get("camera"), dict) else {}
    return {
        "enabled": bool(c.get("enabled", False)),
        "video_enabled": bool(c.get("video_enabled", True)),
        "url": str(c.get("url") or c.get("stream_url") or "").strip(),
        "snapshot_url": str(c.get("snapshot_url") or "").strip(),
        "proxy_enabled": bool(c.get("proxy_enabled", True)),
        "proxy_path": str(c.get("proxy_path", "/camera/stream")).strip() or "/camera/stream",
        "mask_credentials": bool(c.get("mask_credentials", True)),
        "reconnect_seconds": max(1.0, float(c.get("reconnect_seconds", 5))),
    }


def _timelapse_cfg(config: dict[str, Any] | None = None) -> dict[str, Any]:
    if config is None:
        with app_state_lock:
            config = cfg
    tl = config.get("timelapse", {}) if isinstance(config.get("timelapse"), dict) else {}
    source = str(tl.get("frame_source", "processed") or "processed").strip().lower()
    if source not in {"processed", "raw"}:
        source = "processed"
    playback_fps = float(tl.get("playback_fps", 10) or 10)
    if playback_fps < 1:
        playback_fps = 1.0
    if playback_fps > 60:
        playback_fps = 60.0
    final_capture_delay_seconds = float(tl.get("final_capture_delay_seconds", 3) or 0)
    if final_capture_delay_seconds < 0:
        final_capture_delay_seconds = 0.0
    if final_capture_delay_seconds > 30:
        final_capture_delay_seconds = 30.0
    return {
        "enabled": bool(tl.get("enabled", False)),
        "interval_seconds": max(1, int(tl.get("interval_seconds", 30) or 30)),
        "final_capture_delay_seconds": final_capture_delay_seconds,
        "output_dir": str(tl.get("output_dir", "timelapse") or "timelapse").strip() or "timelapse",
        "frame_source": source,
        "playback_fps": playback_fps,
    }


def _timelapse_output_dir(config: dict[str, Any] | None = None) -> Path:
    tl = _timelapse_cfg(config)
    out = (BASE_DIR / tl["output_dir"]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out


def _timelapse_status_label(state: dict[str, Any]) -> str:
    if not bool(state.get("enabled", False)):
        return "Disabled"
    if bool(state.get("build_in_progress", False)):
        return "Building"
    if bool(state.get("stop_pending", False)):
        return "Stopping (Queued)"
    if bool(state.get("stopping", False)):
        return "Stopping"
    if bool(state.get("active", False)) and bool(state.get("paused", False)):
        return "Paused"
    if bool(state.get("active", False)):
        return "Running"
    if bool(state.get("armed", False)):
        return "Armed"
    if str(state.get("error", "")).strip():
        return "Error"
    return "Stopped"


def _timelapse_refresh_enabled() -> None:
    tl = _timelapse_cfg()
    with timelapse_lock:
        timelapse_state["enabled"] = bool(tl["enabled"])
        timelapse_state["interval_seconds"] = int(tl["interval_seconds"])
        timelapse_state["final_capture_delay_seconds"] = float(tl["final_capture_delay_seconds"])
        timelapse_state["playback_fps"] = float(tl["playback_fps"])
        timelapse_state["output_dir"] = str(tl["output_dir"])
        timelapse_state["frame_source"] = str(tl["frame_source"])
        timelapse_state["status"] = _timelapse_status_label(timelapse_state)


def _timelapse_snapshot_state() -> dict[str, Any]:
    _timelapse_refresh_enabled()
    with timelapse_lock:
        state = dict(timelapse_state)
        state["status"] = _timelapse_status_label(state)
        return state


def _timelapse_normalize_state(machine_state: str) -> str:
    raw = str(machine_state or "").strip()
    if not raw:
        return ""
    base = raw.split(":", 1)[0].strip().lower()
    if base == "run":
        return "Run"
    if base == "hold":
        return "Hold"
    if base == "idle":
        return "Idle"
    if base == "alarm":
        return "Alarm"
    if base == "door":
        return "Door"
    if base == "sleep":
        return "Sleep"
    return raw


def _timelapse_is_terminal_state(machine_state: str, online: bool) -> bool:
    if not online:
        return True
    s = _timelapse_normalize_state(machine_state).lower()
    if not s:
        return False
    return s in {"idle", "alarm", "door", "sleep", "unknown", "not_configured"}


def _build_timelapse_video(session_dir: Path, output_file: Path, fps: float) -> tuple[bool, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False, "ffmpeg not found; frames kept without video build"
    pattern = str(session_dir / "frame_%06d.jpg")
    cmd = [
        ffmpeg,
        "-y",
        "-framerate",
        f"{fps:.3f}",
        "-i",
        pattern,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_file),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _timelapse_session_id_from_video_name(filename: str) -> str:
    name = str(filename or "").strip()
    m = re.search(r"_(\d{8}_\d{6})\.[A-Za-z0-9]+$", name)
    return m.group(1) if m else ""


def _timelapse_worker() -> None:
    while not timelapse_stop_event.is_set():
        with timelapse_lock:
            active = bool(timelapse_state.get("active", False))
            paused = bool(timelapse_state.get("paused", False))
            stop_pending = bool(timelapse_state.get("stop_pending", False))
            build_in_progress = bool(timelapse_state.get("build_in_progress", False))
            stopping = bool(timelapse_state.get("stopping", False))
            interval = max(1, int(timelapse_state.get("interval_seconds", 30) or 30))
            session_dir_str = str(timelapse_state.get("session_dir", ""))
            frame_source = str(timelapse_state.get("frame_source", "processed") or "processed").strip().lower()
        if not active:
            break
        if stop_pending or build_in_progress or stopping:
            # Stop/build flow owns final capture and output sequencing.
            break
        if paused:
            if timelapse_stop_event.wait(0.25):
                break
            continue
        try:
            if frame_source not in {"processed", "raw"}:
                frame_source = "processed"
            console.add("info", f"Timelapse frame source: {frame_source}")
            session_dir = Path(session_dir_str) if session_dir_str else _timelapse_output_dir() / "session_unspecified"
            session_dir.mkdir(parents=True, exist_ok=True)
            session_dir_resolved = session_dir.resolve()
            out_dir_resolved = _timelapse_output_dir().resolve()
            if out_dir_resolved not in session_dir_resolved.parents and session_dir_resolved != out_dir_resolved:
                raise RuntimeError("timelapse session directory is outside configured timelapse output directory")
            with timelapse_capture_lock:
                with timelapse_lock:
                    snap_count = int(timelapse_state.get("snapshot_count", 0))
                    snap_count += 1
                    frame_target = session_dir / f"frame_{snap_count:06d}.jpg"
                    while frame_target.exists():
                        snap_count += 1
                        frame_target = session_dir / f"frame_{snap_count:06d}.jpg"
                camera.capture_timelapse_frame_to(frame_target, source=frame_source)
            _set_camera_check_result(True, "timelapse frame capture succeeded")
            with timelapse_lock:
                timelapse_state["snapshot_count"] = snap_count
                timelapse_state["last_snapshot_at"] = time.time()
            console.add("info", f"Timelapse frame captured: {frame_target.name}")
        except Exception as exc:
            _set_camera_check_result(False, "timelapse frame capture failed")
            with timelapse_lock:
                timelapse_state["error"] = str(exc)
            console.add("warn", f"Timelapse capture warning: {exc}")
        if timelapse_stop_event.wait(interval):
            break


def _timelapse_start_internal(reason: str, job_name: str = "", job_source: str = "") -> dict[str, Any]:
    _timelapse_refresh_enabled()
    tl = _timelapse_cfg()
    if not tl["enabled"]:
        with timelapse_lock:
            timelapse_state["enabled"] = False
            timelapse_state["armed"] = False
            timelapse_state["active"] = False
            timelapse_state["status"] = _timelapse_status_label(timelapse_state)
        return {"ok": False, "message": "Timelapse is disabled in Settings."}
    with timelapse_lock:
        if reason == "manual" and bool(timelapse_state.get("armed", False)) and not bool(timelapse_state.get("active", False)):
            return {
                "ok": False,
                "message": "Timelapse is armed for a job. Press Stop Timelapse to cancel or wait for Run.",
            }
        if timelapse_state.get("active"):
            return {"ok": True, "message": "Timelapse already running."}
        timelapse_state["enabled"] = True
        timelapse_state["armed"] = False
        timelapse_state["active"] = True
        timelapse_state["paused"] = False
        timelapse_state["stopping"] = False
        timelapse_state["stop_pending"] = False
        timelapse_state["build_in_progress"] = False
        timelapse_state["stop_reason"] = ""
        timelapse_state["stop_pending_session_id"] = ""
        timelapse_state["error"] = ""
        timelapse_state["job_name"] = job_name or str(timelapse_state.get("job_name", ""))
        timelapse_state["job_source"] = job_source or str(timelapse_state.get("job_source", ""))
        if reason == "manual":
            timelapse_state["control_mode"] = "manual"
        else:
            current_mode = str(timelapse_state.get("control_mode", "")).strip().lower()
            timelapse_state["control_mode"] = "job" if current_mode != "manual" else "manual"
        timelapse_state["interval_seconds"] = int(tl["interval_seconds"])
        timelapse_state["final_capture_delay_seconds"] = float(tl["final_capture_delay_seconds"])
        timelapse_state["playback_fps"] = float(tl["playback_fps"])
        timelapse_state["output_dir"] = str(tl["output_dir"])
        timelapse_state["started_at"] = time.time()
        timelapse_state["last_snapshot_at"] = None
        timelapse_state["snapshot_count"] = 0
        out_dir = _timelapse_output_dir()
        session_id = time.strftime("%Y%m%d_%H%M%S")
        session_name = f"session_{session_id}"
        session_dir = out_dir / session_name
        session_dir.mkdir(parents=True, exist_ok=True)
        timelapse_state["session_dir"] = str(session_dir)
        timelapse_state["session_id"] = session_id
        timelapse_state["status"] = _timelapse_status_label(timelapse_state)
    timelapse_stop_event.clear()
    global timelapse_thread
    timelapse_thread = threading.Thread(target=_timelapse_worker, name="timelapse-worker", daemon=True)
    timelapse_thread.start()
    console.add("info", f"Timelapse capture interval: {tl['interval_seconds']}s")
    console.add("info", f"Timelapse playback FPS: {tl['playback_fps']}")
    console.add("info", f"Timelapse started ({reason}) interval={tl['interval_seconds']}s")
    return {"ok": True, "message": "Timelapse started."}


def _timelapse_stop_internal(reason: str) -> dict[str, Any]:
    global timelapse_stop_worker
    with timelapse_lock:
        was_active = bool(timelapse_state.get("active", False))
        was_armed = bool(timelapse_state.get("armed", False))
        timelapse_state["stop_pending"] = False
        timelapse_state["stop_pending_session_id"] = ""
        timelapse_state["build_in_progress"] = False
        timelapse_state["stop_reason"] = str(reason or "")
        timelapse_state["stopping"] = was_active
    if not was_active and not was_armed:
        with timelapse_lock:
            timelapse_state["status"] = _timelapse_status_label(timelapse_state)
        return {"ok": True, "message": "Timelapse already stopped."}
    timelapse_stop_event.set()
    global timelapse_thread
    th = timelapse_thread
    join_timeout = max(10.0, float(getattr(camera, "timeout_seconds", 15.0)) + 10.0)
    if th and th.is_alive():
        th.join(timeout=join_timeout)
    if th and th.is_alive():
        with timelapse_lock:
            timelapse_state["stopping"] = False
            timelapse_state["status"] = _timelapse_status_label(timelapse_state)
        console.add("warn", "Timelapse stop timeout: capture is still in progress; keeping current session active.")
        return {
            "ok": False,
            "message": "Timelapse stop is waiting for an in-progress capture to finish. Try Stop again in a few seconds.",
        }
    timelapse_thread = None
    with timelapse_lock:
        session_dir_str = str(timelapse_state.get("session_dir", ""))
        session_id = str(timelapse_state.get("session_id", "")).strip()
        snap_count = int(timelapse_state.get("snapshot_count", 0))
        interval = max(1, int(timelapse_state.get("interval_seconds", 30) or 30))
        playback_fps = max(1.0, min(60.0, float(timelapse_state.get("playback_fps", 10) or 10)))
        job_name = str(timelapse_state.get("job_name", ""))
    built_video = ""
    build_message = ""
    cleaned_session = ""
    if session_dir_str and snap_count > 0:
        session_dir = Path(session_dir_str)
        out_dir = _timelapse_output_dir()
        stamp = session_id or time.strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", job_name).strip("_") if job_name else ""
        video_name = f"timelapse_{safe_name}_{stamp}.mp4" if safe_name else f"timelapse_{stamp}.mp4"
        output_file = out_dir / video_name
        fps = playback_fps
        ok, err = _build_timelapse_video(session_dir, output_file, fps)
        if ok and output_file.exists():
            built_video = output_file.name
            try:
                session_dir_res = session_dir.resolve()
                out_dir_res = out_dir.resolve()
                if (
                    session_dir_res.exists()
                    and session_dir_res.is_dir()
                    and out_dir_res in session_dir_res.parents
                    and session_dir_res.name.startswith("session_")
                ):
                    shutil.rmtree(session_dir_res)
                    cleaned_session = session_dir_res.name
                    console.add("info", f"Timelapse session folder cleaned: {cleaned_session}")
            except Exception as exc:
                console.add("warn", f"Timelapse session cleanup warning: {exc}")
        elif err:
            build_message = err
            console.add("warn", f"Timelapse video build warning: {err}")
    with timelapse_lock:
        timelapse_state["active"] = False
        timelapse_state["paused"] = False
        timelapse_state["armed"] = False
        timelapse_state["stopping"] = False
        timelapse_state["stop_pending"] = False
        timelapse_state["stop_pending_session_id"] = ""
        timelapse_state["build_in_progress"] = False
        timelapse_state["stop_reason"] = ""
        timelapse_state["job_name"] = ""
        timelapse_state["job_source"] = ""
        timelapse_state["control_mode"] = ""
        timelapse_state["session_dir"] = ""
        timelapse_state["session_id"] = ""
        timelapse_state["status"] = _timelapse_status_label(timelapse_state)
    timelapse_stop_worker = None
    msg = "Timelapse stopped."
    if built_video:
        msg = f"Timelapse stopped. Video saved: {built_video}"
    elif snap_count <= 0:
        msg = "Timelapse stopped. No frames were captured."
    elif build_message:
        msg = f"Timelapse stopped. Frames captured, but video was not built: {build_message}"
    console.add("info", f"Timelapse stopped ({reason})")
    return {"ok": True, "message": msg, "video": built_video, "cleaned_session": cleaned_session}


def _timelapse_arm(job_name: str, job_source: str) -> dict[str, Any]:
    _timelapse_refresh_enabled()
    tl = _timelapse_cfg()
    if not tl["enabled"]:
        return {"ok": False, "message": "Timelapse disabled; not armed."}
    with timelapse_lock:
        if timelapse_state.get("active"):
            return {"ok": True, "message": "Timelapse already running."}
        timelapse_state["enabled"] = True
        timelapse_state["armed"] = True
        timelapse_state["paused"] = False
        timelapse_state["stopping"] = False
        timelapse_state["stop_pending"] = False
        timelapse_state["build_in_progress"] = False
        timelapse_state["stop_reason"] = ""
        timelapse_state["stop_pending_session_id"] = ""
        timelapse_state["error"] = ""
        timelapse_state["job_name"] = str(job_name or "")
        timelapse_state["job_source"] = str(job_source or "")
        timelapse_state["control_mode"] = "job"
        timelapse_state["interval_seconds"] = int(tl["interval_seconds"])
        timelapse_state["final_capture_delay_seconds"] = float(tl["final_capture_delay_seconds"])
        timelapse_state["playback_fps"] = float(tl["playback_fps"])
        timelapse_state["output_dir"] = str(tl["output_dir"])
        timelapse_state["status"] = _timelapse_status_label(timelapse_state)
    console.add("info", f"Timelapse armed source={job_source} job={job_name}")
    return {"ok": True, "message": "Timelapse armed."}


def _timelapse_observe_machine_state(machine_state: str, online: bool) -> None:
    state_now = _timelapse_snapshot_state()
    if not state_now.get("enabled", False):
        return
    control_mode = str(state_now.get("control_mode", "")).strip().lower()
    if not control_mode:
        if state_now.get("armed", False):
            control_mode = "job"
        elif state_now.get("active", False):
            control_mode = "manual"
    if state_now.get("active", False) and control_mode == "manual":
        return
    normalized_state = _timelapse_normalize_state(machine_state)
    if control_mode == "job" and state_now.get("armed", False) and normalized_state == "Run":
        _timelapse_start_internal(reason="auto", job_name=str(state_now.get("job_name", "")), job_source=str(state_now.get("job_source", "")))
        return
    if control_mode == "job" and state_now.get("active", False):
        if normalized_state == "Hold":
            with timelapse_lock:
                if not timelapse_state.get("paused", False):
                    timelapse_state["paused"] = True
                    timelapse_state["status"] = _timelapse_status_label(timelapse_state)
            return
        if normalized_state == "Run":
            with timelapse_lock:
                if timelapse_state.get("paused", False):
                    timelapse_state["paused"] = False
                    timelapse_state["status"] = _timelapse_status_label(timelapse_state)
            return
    if control_mode == "job" and state_now.get("active", False) and _timelapse_is_terminal_state(normalized_state, online):
        _queue_timelapse_stop_from_status(
            reason=f"state={machine_state or 'unknown'}",
            machine_state=machine_state,
            online=bool(online),
        )


def _timelapse_should_capture_final_frame(reason: str, machine_state: str, online: bool) -> bool:
    reason_l = str(reason or "").strip().lower()
    state_norm = _timelapse_normalize_state(machine_state).strip().lower()
    if not online:
        return False
    if state_norm != "idle":
        return False
    if "offline" in reason_l or "alarm" in reason_l or "door" in reason_l or "sleep" in reason_l or "not_configured" in reason_l:
        return False
    with app_state_lock:
        if bool(ray5_comm_safety_state.get("comm_lost_during_job", False)):
            return False
    return True


def _timelapse_capture_final_frame_after_delay(
    session_id: str,
    session_dir_str: str,
    frame_source: str,
    delay_seconds: float,
) -> None:
    max_attempts = 3
    retry_delay_seconds = 1.5
    delay = max(0.0, min(30.0, float(delay_seconds or 0.0)))
    if delay <= 0:
        return
    console.add("info", f"Timelapse final frame delay: {delay:g}s")
    time.sleep(delay)
    if timelapse_stop_event.is_set():
        return
    with timelapse_lock:
        current_session_id = str(timelapse_state.get("session_id", "")).strip()
        current_session_dir = str(timelapse_state.get("session_dir", "")).strip()
        current_active = bool(timelapse_state.get("active", False))
    if not current_active or not current_session_id or current_session_id != str(session_id or "").strip():
        return
    if current_session_dir != str(session_dir_str or "").strip():
        return
    source = str(frame_source or "processed").strip().lower()
    if source not in {"processed", "raw"}:
        source = "processed"
    session_dir = Path(session_dir_str)
    out_dir_resolved = _timelapse_output_dir().resolve()
    session_dir_resolved = session_dir.resolve()
    if out_dir_resolved not in session_dir_resolved.parents and session_dir_resolved != out_dir_resolved:
        console.add("warn", "Timelapse final frame capture skipped: session directory is outside configured output directory")
        return

    last_error = ""
    for attempt in range(1, max_attempts + 1):
        if timelapse_stop_event.is_set():
            return
        try:
            with timelapse_lock:
                current_session_id = str(timelapse_state.get("session_id", "")).strip()
                current_active = bool(timelapse_state.get("active", False))
            if current_session_id != str(session_id or "").strip() or not current_active:
                return
            with timelapse_capture_lock:
                with timelapse_lock:
                    snap_count = int(timelapse_state.get("snapshot_count", 0))
                    frame_target = session_dir / f"frame_{snap_count+1:06d}.jpg"
                    while frame_target.exists():
                        snap_count += 1
                        frame_target = session_dir / f"frame_{snap_count+1:06d}.jpg"
                console.add("info", f"Timelapse final frame target: {frame_target.name}")
                console.add("info", f"Timelapse final frame capture attempt {attempt}/{max_attempts}")
                camera.capture_timelapse_frame_to(frame_target, source=source)
            _set_camera_check_result(True, "timelapse final frame capture succeeded")
            with timelapse_lock:
                timelapse_state["snapshot_count"] = max(int(timelapse_state.get("snapshot_count", 0)), snap_count + 1)
                timelapse_state["last_snapshot_at"] = time.time()
            console.add("info", f"Timelapse final frame captured: {frame_target.name}")
            return
        except Exception as exc:
            last_error = str(exc)
            _set_camera_check_result(False, "timelapse final frame capture failed")
            try:
                if 'frame_target' in locals() and isinstance(frame_target, Path) and frame_target.exists():
                    frame_target.unlink(missing_ok=True)
            except Exception:
                pass
            if attempt < max_attempts:
                console.add("warn", f"Timelapse final frame capture retry after failure: {last_error}")
                time.sleep(retry_delay_seconds)
            else:
                console.add("warn", f"Timelapse final frame capture failed after retries: {last_error}")


def _timelapse_stop_worker_run(reason: str, session_id: str, machine_state: str, online: bool) -> None:
    global timelapse_stop_worker
    console.add(
        "info",
        f"Timelapse stop/build worker start: session={session_id or 'none'} reason={reason} machine_state={machine_state or 'unknown'}",
    )
    with timelapse_lock:
        timelapse_state["build_in_progress"] = True
        timelapse_state["status"] = _timelapse_status_label(timelapse_state)
    try:
        with timelapse_lock:
            control_mode = str(timelapse_state.get("control_mode", "")).strip().lower()
            session_dir_str = str(timelapse_state.get("session_dir", "")).strip()
            frame_source = str(timelapse_state.get("frame_source", "processed")).strip().lower()
            final_delay_seconds = float(timelapse_state.get("final_capture_delay_seconds", 3.0) or 0.0)
        if (
            control_mode == "job"
            and _timelapse_should_capture_final_frame(reason=reason, machine_state=machine_state, online=bool(online))
        ):
            _timelapse_capture_final_frame_after_delay(
                session_id=session_id,
                session_dir_str=session_dir_str,
                frame_source=frame_source,
                delay_seconds=final_delay_seconds,
            )
        result = _timelapse_stop_internal(reason=reason)
        if result.get("ok"):
            console.add("info", f"Timelapse stop/build worker complete: session={session_id or 'none'}")
        else:
            console.add(
                "warn",
                f"Timelapse stop/build worker completed with warning: session={session_id or 'none'} message={result.get('message','')}",
            )
    except Exception as exc:
        with timelapse_lock:
            timelapse_state["error"] = str(exc)
            timelapse_state["build_in_progress"] = False
            timelapse_state["stop_pending"] = False
            timelapse_state["stop_pending_session_id"] = ""
            timelapse_state["status"] = _timelapse_status_label(timelapse_state)
        console.add("error", f"Timelapse stop/build worker failed: {exc}")
    finally:
        with timelapse_lock:
            timelapse_state["build_in_progress"] = False
            timelapse_state["stop_pending"] = False
            timelapse_state["stop_pending_session_id"] = ""
            timelapse_state["status"] = _timelapse_status_label(timelapse_state)
        timelapse_duplicate_log_at.pop(str(session_id or "none"), None)
        timelapse_stop_worker = None


def _queue_timelapse_stop_from_status(reason: str, machine_state: str, online: bool) -> bool:
    global timelapse_stop_worker
    now = time.time()
    duplicate_log_window_seconds = 12.0
    duplicate_log_message = ""
    def _mark_duplicate(session_key: str, msg: str) -> None:
        nonlocal duplicate_log_message
        last = float(timelapse_duplicate_log_at.get(session_key, 0) or 0)
        if (now - last) >= duplicate_log_window_seconds:
            timelapse_duplicate_log_at[session_key] = now
            duplicate_log_message = msg
    with timelapse_lock:
        session_id = str(timelapse_state.get("session_id", "")).strip()
        control_mode = str(timelapse_state.get("control_mode", "")).strip().lower()
        active = bool(timelapse_state.get("active", False))
        session_key = session_id or "none"
        duplicate_detected = False
        if control_mode != "job" or not active:
            return False
        if bool(timelapse_state.get("build_in_progress", False)):
            _mark_duplicate(session_key, f"Timelapse stop/build already running; duplicate request ignored for session={session_id or 'none'}")
            duplicate_detected = True
        pending_session = str(timelapse_state.get("stop_pending_session_id", "")).strip()
        if (not duplicate_detected) and bool(timelapse_state.get("stop_pending", False)) and pending_session == session_id and session_id:
            _mark_duplicate(session_key, f"Timelapse stop/build already queued; duplicate request ignored for session={session_id}")
            duplicate_detected = True
        if (not duplicate_detected) and timelapse_stop_worker is not None and timelapse_stop_worker.is_alive():
            _mark_duplicate(session_key, f"Timelapse stop/build worker alive; duplicate request ignored for session={session_id or 'none'}")
            duplicate_detected = True
        if not duplicate_detected:
            timelapse_duplicate_log_at.pop(session_key, None)
            timelapse_state["stop_pending"] = True
            timelapse_state["stop_pending_session_id"] = session_id
            timelapse_state["stop_reason"] = str(reason or "")
            timelapse_state["status"] = _timelapse_status_label(timelapse_state)
        else:
            session_id = str(timelapse_state.get("session_id", "")).strip()
    if duplicate_log_message:
        console.add("info", duplicate_log_message)
        return False
    console.add(
        "info",
        f"Queued background timelapse stop/build: session={session_id or 'none'} reason={reason} machine_state={machine_state or 'unknown'}",
    )
    worker = threading.Thread(
        target=_timelapse_stop_worker_run,
        name=f"timelapse-stop-{session_id or int(time.time())}",
        args=(str(reason or ""), str(session_id or ""), str(machine_state or ""), bool(online)),
        daemon=True,
    )
    timelapse_stop_worker = worker
    worker.start()
    return True


@app.get("/")
def dashboard() -> str:
    return render_template("index.html")


@app.get("/setup")
def setup_page() -> str:
    return render_template("setup.html")


@app.get("/machine-settings")
def machine_settings_page() -> str:
    return render_template("machine_settings.html")


@app.get("/api/status")
def api_status() -> Any:
    global _last_logged_status_source, _status_error_logged
    with app_state_lock:
        active_cfg = cfg
        active_monitor = status_monitor
    _schedule_system_check_probe()
    st_cfg = active_cfg.get("status", {}) if isinstance(active_cfg.get("status"), dict) else {}
    prefer_live = bool(st_cfg.get("prefer_live_status", True))
    live_status_stale_seconds = float(st_cfg.get("live_status_stale_seconds", 15.0) or 15.0)
    if live_status_stale_seconds < 10.0:
        live_status_stale_seconds = 10.0
    if live_status_stale_seconds > 20.0:
        live_status_stale_seconds = 20.0
    monitor_status = active_monitor.get_latest_status() if (active_monitor and prefer_live) else None
    monitor_age = None
    monitor_ws_connected = False
    if isinstance(monitor_status, dict):
        monitor_age = monitor_status.get("age_seconds")
        monitor_ws_connected = bool(monitor_status.get("websocket_connected", False))
    live_fresh = bool(
        monitor_status
        and monitor_ws_connected
        and (monitor_age is not None)
        and (float(monitor_age) <= live_status_stale_seconds)
    )
    if not _is_ray5_host_configured():
        state = "Offline"
        source = "offline"
        online = False
        mpos = {"x": 0.0, "y": 0.0, "z": None}
        wpos = {"x": None, "y": None, "z": None}
        wco = {"x": None, "y": None, "z": None}
        wco_available = False
        wpos_calculated = False
        feed = 0.0
        spindle = 0.0
        raw_status = ""
        ws_connected = False
        ws_page_id = None
        last_error = "Ray5 host is not configured. Set ray5.host in Settings."
        alarm_message = None
    elif live_fresh:
        state = monitor_status.get("state", "UNKNOWN")
        mpos = monitor_status.get("machine_position", {}) or {}
        wpos = monitor_status.get("work_position", {}) or {}
        wco = monitor_status.get("work_offset", {}) or {}
        wco_available = bool(monitor_status.get("wco_available", False))
        wpos_calculated = bool(monitor_status.get("wpos_calculated", False))
        source = "live_websocket"
        online = True
        feed = monitor_status.get("feed")
        spindle = monitor_status.get("spindle")
        raw_status = monitor_status.get("raw_status", "")
        ws_connected = bool(monitor_status.get("websocket_connected", False))
        ws_page_id = monitor_status.get("websocket_page_id")
        last_error = None
        alarm_message = monitor_status.get("alarm_message")
    elif monitor_status:
        source = "fallback_offline"
        state = "Offline"
        mpos = {"x": 0.0, "y": 0.0, "z": None}
        wpos = {"x": None, "y": None, "z": None}
        wco = {"x": None, "y": None, "z": None}
        wco_available = False
        wpos_calculated = False
        feed = 0.0
        spindle = 0.0
        raw_status = monitor_status.get("raw_status", "")
        ws_connected = bool(monitor_status.get("websocket_connected", False))
        ws_page_id = monitor_status.get("websocket_page_id")
        last_error = monitor_status.get("last_error")
        alarm_message = monitor_status.get("alarm_message")
        online = False
    else:
        source = "fallback_offline"
        state = "Offline"
        mpos = {"x": 0.0, "y": 0.0, "z": None}
        wpos = {"x": None, "y": None, "z": None}
        wco = {"x": None, "y": None, "z": None}
        wco_available = False
        wpos_calculated = False
        feed = 0.0
        spindle = 0.0
        raw_status = ""
        ws_connected = bool(active_monitor.is_connected()) if active_monitor else False
        ws_page_id = None
        last_error = None
        alarm_message = None
        online = False

    raw_state = str(state or "").strip()
    state_base = raw_state.split(":", 1)[0] if raw_state else "UNKNOWN"
    _update_comm_safety_state(status_source=source, online=bool(online), state_base=state_base)
    if source in {"offline", "fallback_offline"} or not online:
        display_state = "Offline" if _is_ray5_host_configured() else "Not Configured"
    else:
        display_state = state_base or "Unknown"

    if source in {"offline", "fallback_offline"}:
        alarm_status = "Unknown"
    elif state_base.lower() == "alarm":
        alarm_status = "Active"
    elif online:
        alarm_status = "Clear"
    else:
        alarm_status = "Unknown"

    state_key = state_base.lower()
    if source in {"offline", "fallback_offline"}:
        job_status = "Unknown"
    elif state_key == "run":
        job_status = "Running"
    elif state_key == "hold":
        job_status = "Paused"
    elif state_key == "idle":
        job_status = "Stopped"
    elif state_key == "alarm":
        job_status = "Alarm"
    else:
        job_status = "Unknown"

    has_w = (wpos.get("x") is not None) or (wpos.get("y") is not None)
    has_m = (mpos.get("x") is not None) or (mpos.get("y") is not None)
    if source in {"offline", "fallback_offline"}:
        coordinate_source = "—"
    elif wpos_calculated and has_m and wco_available:
        coordinate_source = "MPos + WCO"
    elif has_w and has_m and wco_available:
        coordinate_source = "WPos + MPos + WCO"
    elif has_w and has_m:
        coordinate_source = "WPos + MPos"
    elif has_m and wco_available:
        coordinate_source = "MPos + WCO"
    elif has_w:
        coordinate_source = "WPos"
    elif has_m:
        coordinate_source = "MPos"
    else:
        coordinate_source = "—"

    monitor_coordinate_source = ""
    if isinstance(monitor_status, dict):
        monitor_coordinate_source = str(monitor_status.get("coordinate_source_label") or "").strip()
    if monitor_coordinate_source and source == "live_websocket":
        coordinate_source = monitor_coordinate_source

    last_update_ts = None
    last_update_age_seconds = None
    if isinstance(monitor_status, dict):
        last_update_ts = monitor_status.get("timestamp")
        last_update_age_seconds = monitor_status.get("age_seconds")
    if last_update_age_seconds is None and last_update_ts:
        try:
            last_update_age_seconds = max(0.0, float(time.time() - float(last_update_ts)))
        except Exception:
            last_update_age_seconds = None

    if source != _last_logged_status_source:
        console.add("info", f"Status source changed: {source}")
        _last_logged_status_source = source
    if not online:
        err = str(last_error or "Ray5 live status unavailable")
        if ws_connected and _is_ray5_host_configured():
            if not _status_error_logged:
                age_txt = f"{last_update_age_seconds:.1f}s" if isinstance(last_update_age_seconds, (int, float)) else "unknown"
                console.add(
                    "warn",
                    f"Status stale: no fresh live packet for {age_txt}; falling back offline after {live_status_stale_seconds:.0f}s timeout.",
                )
                _status_error_logged = True
        else:
            if not _status_error_logged:
                console.add("error", f"Status error: {err}")
                _status_error_logged = True
    else:
        _status_error_logged = False
    cam = _camera_cfg(active_cfg)
    cam_url = cam["url"]
    cam_scheme = (urlsplit(cam_url).scheme or "").lower() if cam_url else ""
    cam_masked = mask_camera_url(cam_url) if cam["mask_credentials"] else cam_url
    with app_state_lock:
        http_ok = system_check_state.get("ray5_http_reachable")
        sd_ok = system_check_state.get("sd_card_list_working")
        cam_test_ok = system_check_state.get("camera_test_passed")
    ws_reachable: bool | None
    if not _is_ray5_host_configured():
        ws_reachable = None
    else:
        # Reachable means we currently have live websocket-backed machine status.
        ws_reachable = bool(ws_connected and online and source == "live_websocket")
    if ws_reachable is True:
        page_id_captured: bool | None = bool(ws_page_id not in (None, ""))
    elif ws_reachable is False:
        page_id_captured = False
    else:
        page_id_captured = None

    if http_ok is False:
        sd_working_current: bool | None = False
    elif http_ok is True:
        sd_working_current = bool(sd_ok) if sd_ok is not None else None
    else:
        sd_working_current = None
    _timelapse_observe_machine_state(str(state), bool(online))
    tl_state = _timelapse_snapshot_state()
    app_version_value = _read_local_version() or "unknown"
    update_status_cached = _snapshot_startup_update_status()
    comm_safety = _snapshot_comm_safety_state()
    return jsonify(
        {
            "ok": True,
            "online": online,
            "connected": online,
            "machine_state": state,
            "state": state,
            "position": {"x": mpos.get("x"), "y": mpos.get("y"), "z": mpos.get("z")},
            "machine_position": {"x": mpos.get("x"), "y": mpos.get("y"), "z": mpos.get("z")},
            "work_position": {"x": wpos.get("x"), "y": wpos.get("y"), "z": wpos.get("z")},
            "work_offset": {"x": wco.get("x"), "y": wco.get("y"), "z": wco.get("z")},
            "wco_x": wco.get("x"),
            "wco_y": wco.get("y"),
            "wco_available": bool(wco_available and source == "live_websocket"),
            "wpos_calculated": bool(wpos_calculated and source == "live_websocket"),
            "feed": feed,
            "spindle": spindle,
            "raw": raw_status,
            "raw_status": raw_status,
            "status_source": source,
            "position_source": "live_websocket" if source == "live_websocket" else ("cache" if source == "cache" else ("synthetic" if source == "synthetic" else "unknown")),
            "state_base": state_base,
            "display_state": display_state,
            "alarm_status": alarm_status,
            "job_status": job_status,
            "connection_status": "Online" if (online and source == "live_websocket") else "Offline",
            "coordinate_source_label": coordinate_source,
            "last_update_ts": last_update_ts,
            "last_update_age_seconds": last_update_age_seconds,
            "ray5_host": active_cfg.get("ray5", {}).get("host"),
            "ray5_port": active_cfg.get("ray5", {}).get("port"),
            "mainboard_online": online,
            "machine_state_label": "Connected / status estimated" if source in {"cache", "synthetic"} else state,
            "position_reliable": source == "live_websocket",
            "websocket_connected": ws_connected,
            "websocket_page_id": ws_page_id,
            "last_error": last_error,
            "alarm_message": alarm_message,
            "camera_enabled": cam["enabled"],
            "camera_video_enabled": cam["video_enabled"],
            "camera_configured": bool(cam_url),
            "camera_preview_supported": bool(cam["enabled"] and cam["video_enabled"] and cam["proxy_enabled"] and cam_url),
            "camera_proxy_path": cam["proxy_path"],
            "camera_url_masked": cam_masked,
            "camera_scheme": cam_scheme,
            "app_version": app_version_value,
            "update_status": update_status_cached,
            "comm_safety": comm_safety,
            "system_check": {
                "ray5_host_configured": bool(_is_ray5_host_configured(active_cfg)),
                "ray5_http_reachable": http_ok,
                "ray5_websocket_reachable": ws_reachable,
                "page_id_captured": page_id_captured,
                "sd_card_list_working": sd_working_current,
                "camera_url_configured": bool(cam_url),
                "camera_test_passed": cam_test_ok,
            },
            "timelapse_state": tl_state,
        }
    )


@app.get("/api/status/debug")
def api_status_debug() -> Any:
    with app_state_lock:
        active_monitor = status_monitor
    if active_monitor is None:
        return jsonify(
            {
                "monitor_exists": False,
                "websocket_enabled": False,
                "websocket_connected": False,
                "page_id": None,
                "last_raw_message": None,
                "last_raw_status": None,
                "last_status_age_seconds": None,
                "last_parse_error": None,
                "poll_count": 0,
                "status_trigger_count": 0,
                "status_line_count": 0,
                "latest_status": None,
                "last_error": None,
            }
        )
    return jsonify(active_monitor.get_debug_info())


@app.get("/api/console")
def api_console() -> Any:
    return jsonify({"ok": True, "items": console.list()})


@app.post("/api/console/clear")
def api_console_clear() -> Any:
    console.clear()
    return jsonify({"ok": True})


@app.post("/api/console/command")
def api_console_command() -> Any:
    blocked = _require_ray5_configured()
    if blocked:
        return blocked
    console_cfg = cfg.get("console", {}) if isinstance(cfg.get("console"), dict) else {}
    if not bool(console_cfg.get("raw_command_enabled", True)):
        return jsonify({"ok": False, "message": "Raw console commands are disabled in Settings."}), 403
    body = request.get_json(silent=True) or {}
    command = str(body.get("command", "")).strip()
    if not command:
        return jsonify({"ok": False, "message": "Command cannot be empty."}), 400

    cmd_upper = command.upper()
    if cmd_upper in {"CTRL-X", "CTRLX", "^X", "\\X18", "0X18", "SOFT_RESET"}:
        command_to_send = "\x18"
    else:
        command_to_send = command

    console.add("info", f"Raw command requested: {command}")
    if command == "?":
        result = ray5.query_status_command()
        ok = bool(result.get("ok"))
        if ok:
            console.add("info", "Raw command status query result: ok")
        else:
            console.add("error", f"Raw command status query failed: {result.get('message') or result.get('raw') or 'unknown'}")
    else:
        result = ray5.send_gcode(command_to_send)
        ok = bool(result.get("ok"))
        if ok:
            console.add("info", "Raw command result: ok")
        else:
            console.add("error", f"Raw command failed: {result.get('message') or result.get('raw') or 'unknown'}")
    response_text = str(result.get("raw", "") or "").strip()
    if response_text:
        # Keep multiline device responses visible in Live Console (e.g. $$, $I, $G).
        preview = response_text[:12000]
        console.add("info", f"Raw command response:\n{preview}")
    return jsonify(
        {
            "ok": ok,
            "message": "Command sent" if ok else (result.get("message") or "Command failed"),
            "command": command,
            "response": response_text,
            "raw": response_text,
            "result": result,
        }
    )


GRBL_SETTING_INFO: dict[str, dict[str, str]] = {
    "0": {"description": "Step pulse time", "unit": "microseconds", "notes": ""},
    "1": {"description": "Step idle delay", "unit": "milliseconds", "notes": ""},
    "2": {"description": "Step pulse invert", "unit": "mask", "notes": ""},
    "3": {"description": "Direction invert", "unit": "mask", "notes": ""},
    "4": {"description": "Step enable invert", "unit": "boolean", "notes": ""},
    "5": {"description": "Limit pins invert", "unit": "boolean", "notes": ""},
    "6": {"description": "Probe pin invert", "unit": "boolean", "notes": ""},
    "10": {"description": "Status report options", "unit": "mask", "notes": ""},
    "11": {"description": "Junction deviation", "unit": "mm", "notes": ""},
    "12": {"description": "Arc tolerance", "unit": "mm", "notes": ""},
    "13": {"description": "Report inches", "unit": "boolean", "notes": ""},
    "20": {"description": "Soft limits", "unit": "boolean", "notes": ""},
    "21": {"description": "Hard limits", "unit": "boolean", "notes": ""},
    "22": {"description": "Homing cycle", "unit": "boolean", "notes": ""},
    "23": {"description": "Homing direction invert", "unit": "mask", "notes": ""},
    "24": {"description": "Homing locate feed rate", "unit": "mm/min", "notes": ""},
    "25": {"description": "Homing seek rate", "unit": "mm/min", "notes": ""},
    "26": {"description": "Homing debounce", "unit": "milliseconds", "notes": ""},
    "27": {"description": "Homing pull-off", "unit": "mm", "notes": ""},
    "30": {"description": "Maximum spindle/laser value", "unit": "S-value max", "notes": ""},
    "31": {"description": "Minimum spindle/laser value", "unit": "S-value min", "notes": ""},
    "32": {"description": "Laser mode", "unit": "boolean", "notes": ""},
    "100": {"description": "X steps/mm", "unit": "steps/mm", "notes": ""},
    "101": {"description": "Y steps/mm", "unit": "steps/mm", "notes": ""},
    "102": {"description": "Z steps/mm", "unit": "steps/mm", "notes": ""},
    "110": {"description": "X max rate", "unit": "mm/min", "notes": ""},
    "111": {"description": "Y max rate", "unit": "mm/min", "notes": ""},
    "112": {"description": "Z max rate", "unit": "mm/min", "notes": ""},
    "120": {"description": "X acceleration", "unit": "mm/sec²", "notes": ""},
    "121": {"description": "Y acceleration", "unit": "mm/sec²", "notes": ""},
    "122": {"description": "Z acceleration", "unit": "mm/sec²", "notes": ""},
    "130": {"description": "X max travel", "unit": "mm", "notes": ""},
    "131": {"description": "Y max travel", "unit": "mm", "notes": ""},
    "132": {"description": "Z max travel", "unit": "mm", "notes": ""},
}


def _parse_machine_settings_raw(raw_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in str(raw_text or "").replace("\r", "\n").split("\n"):
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^\$(\d+)=(.+)$", s)
        if not m:
            continue
        key = m.group(1)
        value = m.group(2).strip()
        if key in seen:
            continue
        seen.add(key)
        info = GRBL_SETTING_INFO.get(key, {"description": "Unknown / firmware-specific setting", "unit": "—", "notes": "—"})
        rows.append(
            {
                "key": key,
                "code": f"${key}",
                "value": value,
                "description": str(info.get("description", "")),
                "unit": str(info.get("unit", "—")),
                "notes": str(info.get("notes", "—")),
                "raw": s,
            }
        )
    rows.sort(key=lambda x: int(x["key"]))
    return rows


def _collect_machine_settings_raw(timeout_seconds: float = 4.0, max_lines: int = 200) -> tuple[str, str]:
    start_ts = time.time()
    initial_result = ray5.send_gcode("$$")
    immediate_raw = str(initial_result.get("raw", "") or "")
    lines: list[str] = []
    seen_settings = False
    end_at = start_ts + max(1.0, float(timeout_seconds))
    while time.time() < end_at:
        if status_monitor is not None:
            new_lines = status_monitor.get_lines_since(start_ts)
            if new_lines:
                lines = new_lines[-max(1, int(max_lines)) :]
                seen_settings = any(re.match(r"^\$(\d+)=(.+)$", str(x).strip()) for x in lines)
        # If settings already arrived and stream has signaled completion, stop early.
        if seen_settings and any(str(x).strip().lower() == "ok" for x in lines):
            break
        time.sleep(0.1)

    combined_parts = [immediate_raw]
    if lines:
        combined_parts.append("\n".join(lines))
    combined = "\n".join([p for p in combined_parts if str(p).strip()]).strip()
    if not combined:
        combined = immediate_raw.strip()
    return combined, str(initial_result.get("message") or "")


def _validate_machine_setting_change(item: Any) -> tuple[bool, str, str]:
    if not isinstance(item, dict):
        return False, "", "Change must be an object."
    key = str(item.get("key", "")).strip()
    value = str(item.get("value", "")).strip()
    if not re.match(r"^\d+$", key):
        return False, key, "Invalid setting key."
    if not value:
        return False, key, "Value cannot be empty."
    if re.search(r"[\r\n;|&`]", value):
        return False, key, "Value contains forbidden characters."
    if re.search(r"[\x00-\x1f]", value):
        return False, key, "Value contains control characters."
    if not re.match(r"^-?\d+(\.\d+)?$", value):
        return False, key, "Value must be numeric."
    return True, key, value


@app.get("/api/machine-settings")
def api_machine_settings_get() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    raw_text, initial_message = _collect_machine_settings_raw(timeout_seconds=4.0, max_lines=200)
    settings = _parse_machine_settings_raw(raw_text)
    if not settings:
        detail = str(raw_text or initial_message or "No response text received.").strip()
        return jsonify(
            {
                "ok": False,
                "settings": [],
                "raw": raw_text,
                "error": f"No GRBL settings were found in the $$ response. Device output: {detail[:3000]}",
            }
        ), 502
    return jsonify({"ok": True, "settings": settings, "raw": raw_text, "message": f"Loaded {len(settings)} setting(s)."})


@app.post("/api/machine-settings")
def api_machine_settings_post() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    changes = body.get("changes")
    if not isinstance(changes, list) or not changes:
        return jsonify({"ok": False, "error": "changes must be a non-empty list"}), 400
    results: list[dict[str, Any]] = []
    success_count = 0
    for item in changes:
        valid, key, value_or_error = _validate_machine_setting_change(item)
        if not valid:
            results.append({"key": key, "command": "", "ok": False, "message": value_or_error})
            continue
        command = f"${key}={value_or_error}"
        send_res = ray5.send_gcode(command)
        row_ok = bool(send_res.get("ok"))
        if row_ok:
            success_count += 1
        results.append(
            {
                "key": key,
                "command": command,
                "ok": row_ok,
                "message": str(send_res.get("message") or ("ok" if row_ok else "failed")),
                "raw": str(send_res.get("raw", "") or ""),
            }
        )
    total = len(changes)
    all_ok = success_count == total
    msg = f"Saved {success_count} setting(s)." if all_ok else f"Saved {success_count} setting(s), {total - success_count} failed."
    status = 200 if all_ok else 207
    return jsonify({"ok": all_ok, "results": results, "message": msg}), status


@app.get("/api/camera/video-enabled")
def api_camera_video_enabled_get() -> Any:
    cam = _camera_cfg()
    return jsonify({"ok": True, "enabled": bool(cam["video_enabled"])})


@app.post("/api/camera/video-enabled")
def api_camera_video_enabled_post() -> Any:
    global cfg
    body = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled", True))
    current = cfg_mgr.load()
    cam = current.get("camera", {}) if isinstance(current.get("camera"), dict) else {}
    cam["video_enabled"] = enabled
    current["camera"] = cam
    cfg_mgr.save(current)
    # Keep runtime services alive; this toggle should not restart watchers/status monitor.
    with app_state_lock:
        cfg = current
    msg = "Camera video enabled." if enabled else "Camera video disabled."
    console.add("info", msg)
    return jsonify({"ok": True, "enabled": enabled, "message": msg})


@app.get("/camera/stream")
def camera_stream() -> Any:
    global camera_stream_clients
    cam = _camera_cfg()
    if not cam["enabled"] or not cam["proxy_enabled"]:
        return "Camera proxy is disabled", 404
    if not cam["url"]:
        return "Camera URL not configured", 404
    stream_health = {"last": None}

    def _on_stream_frame_ok() -> None:
        if stream_health["last"] is True:
            return
        stream_health["last"] = True
        _set_camera_check_result(True, "live stream frame read succeeded")

    def _on_stream_frame_fail(reason: str = "live stream frame read failed") -> None:
        if stream_health["last"] is False:
            return
        stream_health["last"] = False
        _set_camera_check_result(False, str(reason or "live stream frame read failed"))

    with camera_stream_clients_lock:
        camera_stream_clients += 1
        active_clients = camera_stream_clients
    console.add("info", f"Camera stream client connected. active_clients={active_clients}")

    def _stream_wrapper():
        global camera_stream_clients
        try:
            yield from mjpeg_generator(
                cam["url"],
                cam["reconnect_seconds"],
                on_frame_ok=_on_stream_frame_ok,
                on_frame_fail=_on_stream_frame_fail,
            )
        finally:
            with camera_stream_clients_lock:
                camera_stream_clients = max(0, int(camera_stream_clients) - 1)
                remaining = camera_stream_clients
            console.add("info", f"Camera stream client disconnected. active_clients={remaining}")

    return app.response_class(
        _stream_wrapper(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/api/camera/mark-working")
def api_camera_mark_working() -> Any:
    # Frontend image load events are not authoritative camera health checks.
    return jsonify({"ok": True, "message": "ignored: backend-only camera health tracking"})


@app.post("/api/camera/mark-failed")
def api_camera_mark_failed() -> Any:
    # Frontend image error events are not authoritative camera health checks.
    return jsonify({"ok": True, "message": "ignored: backend-only camera health tracking"})


@app.get("/api/camera/snapshot")
def camera_snapshot() -> Any:
    latest_path = camera.latest_path
    if latest_path.exists():
        return send_file(latest_path, mimetype="image/jpeg")
    return jsonify({"ok": False, "error": "No latest snapshot available. Take a snapshot first."}), 404


@app.post("/api/camera/test")
def api_camera_test() -> Any:
    cam = _camera_cfg()
    if not cam["enabled"]:
        _set_camera_check_result(False, "camera test failed: camera disabled")
        return jsonify({"ok": False, "message": "Camera test failed: camera disabled."})
    if not cam["url"]:
        _set_camera_check_result(False, "camera test failed: camera URL not configured")
        return jsonify({"ok": False, "message": "Camera test failed: camera URL not configured."})
    cap = cv2.VideoCapture(cam["url"])
    try:
        if not cap.isOpened():
            _set_camera_check_result(False, "camera test failed: camera open failed")
            return jsonify({"ok": False, "message": "Camera test failed: camera open failed."})
        ok, frame = cap.read()
        if not ok or frame is None:
            _set_camera_check_result(False, "camera test failed: camera read failed")
            return jsonify({"ok": False, "message": "Camera test failed: camera read failed."})
        _set_camera_check_result(True, "camera test passed")
        return jsonify({"ok": True, "message": "Camera test passed."})
    finally:
        cap.release()


@app.post("/api/camera/open-external")
def api_camera_open_external() -> Any:
    cam = _camera_cfg()
    raw_url = str(cam.get("url", "") or "").strip()
    if not raw_url:
        return jsonify({"ok": False, "error": "camera URL not configured"})
    scheme = urlsplit(raw_url).scheme.strip().lower()
    allowed_schemes = {"http", "https", "rtsp", "rtsps"}
    if scheme not in allowed_schemes:
        console.add(
            "warn",
            f"Camera external open blocked: unsupported URL scheme '{scheme or 'none'}' "
            f"for {mask_camera_url(raw_url)}",
        )
        return jsonify({"ok": False, "error": f"unsupported camera URL scheme: {scheme or 'none'}"})
    try:
        webbrowser.open(raw_url)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.post("/api/camera/capture")
def api_camera_capture() -> Any:
    try:
        p = camera.capture("manual")
        _set_camera_check_result(True, "manual camera capture succeeded")
        dbg = dict(camera.last_capture_debug)
        raw_size = dbg.get("raw_size", ["?", "?"])
        proc_size = dbg.get("processed_size", ["?", "?"])
        deskew_enabled = bool(dbg.get("deskew_enabled", False))
        sp_count = int(dbg.get("source_points_count", 0))
        deskew_out = dbg.get("deskew_output_size", ["?", "?"])
        deskew_applied = bool(dbg.get("deskew_applied", False))
        console.add("info", f"[CAMERA] Raw image size: {raw_size[0]}x{raw_size[1]}")
        console.add("info", f"[CAMERA] Deskew enabled: {'true' if deskew_enabled else 'false'}")
        console.add("info", f"[CAMERA] Deskew source points: {sp_count}")
        console.add("info", f"[CAMERA] Deskew output size: {deskew_out[0]}x{deskew_out[1]}")
        if deskew_applied:
            console.add("info", "[CAMERA] Deskew applied source_points=4 output_size="
                        f"{deskew_out[0]}x{deskew_out[1]}")
        else:
            console.add("warn", f"[CAMERA] Deskew skipped: {dbg.get('deskew_skip_reason', 'unknown')}")
        console.add("info", f"[CAMERA] Final image saved: {p.name} size={proc_size[0]}x{proc_size[1]}")
        console.add("info", f"[CAMERA] latest_raw path: {dbg.get('latest_raw_path','')}")
        console.add("info", f"[CAMERA] latest path: {dbg.get('latest_path','')}")
        console.add("info", f"Camera capture saved: {p.name}")
        return jsonify(
            {
                "ok": True,
                "filename": p.name,
                "path": str(p),
                "open_url": f"/api/snapshots/open/{p.name}",
                "latest_url": "/api/snapshots/open/latest.jpg",
                "raw_url": "/api/snapshots/open/latest_raw.jpg",
                "instructions_exists": bool(dbg.get("instructions_exists", False)),
                "deskew_applied": bool(dbg.get("deskew_applied", False)),
                "postprocess_applied": bool(dbg.get("postprocess_applied", False)),
                "output_size": dbg.get("processed_size", [None, None]),
            }
        )
    except CameraCaptureError as exc:
        _set_camera_check_result(False, "manual camera capture failed")
        console.add("warn", f"Camera capture failed: {exc}")
        return jsonify({"ok": False, "error": str(exc)})


@app.get("/camera/calibration")
def camera_calibration_page() -> Any:
    return render_template("camera_calibration.html")


@app.get("/camera/popout")
def camera_popout_page() -> Any:
    return render_template("camera_popout.html")


@app.get("/camera-calibration")
def camera_calibration_page_legacy() -> Any:
    return render_template("camera_calibration.html")


@app.get("/api/camera/config-status")
def api_camera_config_status() -> Any:
    return jsonify({"ok": True, **camera.config_status()})


@app.post("/api/camera/calibration/run")
def api_camera_calibration_run() -> Any:
    global calibration_process
    latest_raw = camera.output_dir / "latest_raw.jpg"
    if not latest_raw.exists():
        return jsonify({"ok": False, "error": "Take a snapshot first, then run calibration."}), 400
    script = BASE_DIR / "calibrate_camera.py"
    with calibration_lock:
        if calibration_process is not None:
            if calibration_process.poll() is None:
                return jsonify({"ok": False, "error": "Camera calibration is already running."}), 409
            calibration_process = None
    try:
        with calibration_lock:
            calibration_process = subprocess.Popen([sys.executable, str(script)], cwd=str(BASE_DIR))
        console.add("info", "Camera calibration launched")
        return jsonify({"ok": True, "message": "Calibration window launched"})
    except Exception as exc:
        with calibration_lock:
            calibration_process = None
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/snapshots")
def api_snapshots() -> Any:
    return jsonify({"ok": True, "items": camera.list_snapshots(limit=100)})


@app.post("/api/snapshots/open-folder")
def api_snapshots_open_folder() -> Any:
    try:
        camera.open_capture_folder()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.get("/api/snapshots/open/<path:filename>")
def api_snapshots_open(filename: str) -> Any:
    try:
        p = camera.safe_snapshot_path(filename)
        return send_file(str(p), mimetype="image/jpeg")
    except CameraCaptureError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@app.get("/api/snapshots/download/<path:filename>")
def api_snapshots_download(filename: str) -> Any:
    try:
        p = camera.safe_snapshot_path(filename)
        return send_file(str(p), as_attachment=True, download_name=p.name)
    except CameraCaptureError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@app.get("/api/timelapses")
def api_timelapses() -> Any:
    out_dir = _timelapse_output_dir()
    allowed = {".mp4", ".webm", ".mov", ".avi"}
    items: list[dict[str, Any]] = []
    for p in sorted(out_dir.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file() or p.suffix.lower() not in allowed:
            continue
        s = p.stat()
        items.append(
            {
                "name": p.name,
                "filename": p.name,
                "size_bytes": int(s.st_size),
                "modified": float(s.st_mtime),
                "url": f"/api/timelapses/open/{p.name}",
            }
        )
    return jsonify({"ok": True, "items": items})


@app.get("/api/timelapse/state")
def api_timelapse_state() -> Any:
    return jsonify({"ok": True, "state": _timelapse_snapshot_state()})


@app.post("/api/timelapse/start")
def api_timelapse_start() -> Any:
    body = request.get_json(silent=True) or {}
    job_name = str(body.get("job_name", "")).strip()
    job_source = str(body.get("job_source", "manual")).strip() or "manual"
    comm_safety = _snapshot_comm_safety_state()
    if bool(comm_safety.get("comm_lost_during_job", False)):
        result = {"ok": False, "message": str(comm_safety.get("message") or "Timelapse start blocked by communication-loss safety lockout.")}
        return jsonify(result | {"state": _timelapse_snapshot_state()}), 409

    state_now = _timelapse_snapshot_state()
    with timelapse_lock:
        worker_alive = bool(timelapse_stop_worker is not None and timelapse_stop_worker.is_alive())
    status_text = str(state_now.get("status", "")).strip().lower()
    session_id = str(state_now.get("session_id", "")).strip()
    timelapse_busy = (
        bool(state_now.get("armed", False))
        or bool(state_now.get("active", False))
        or bool(state_now.get("paused", False))
        or bool(state_now.get("stopping", False))
        or bool(state_now.get("stop_pending", False))
        or bool(state_now.get("build_in_progress", False))
        or worker_alive
        or (bool(session_id) and status_text not in {"stopped", "disabled"})
    )
    if timelapse_busy:
        result = {"ok": False, "message": "Timelapse is already active."}
        return jsonify(result | {"state": state_now}), 409

    with app_state_lock:
        active_monitor = status_monitor
    latest_status = active_monitor.get_latest_status() if active_monitor is not None else None
    machine_state = ""
    online = False
    if isinstance(latest_status, dict):
        machine_state = str(latest_status.get("state") or "").strip()
        online = bool(latest_status.get("websocket_connected", False))
    normalized_state = _timelapse_normalize_state(machine_state)
    if not online or normalized_state != "Run":
        result = {"ok": False, "message": "Timelapse can only be manually started while the Ray5 is running."}
        return jsonify(result | {"state": _timelapse_snapshot_state()}), 409

    effective_job_name = job_name or "manual_run_timelapse"
    # Manual Start is now constrained to active Run state and uses job-mode behavior.
    result = _timelapse_start_internal(reason="auto", job_name=effective_job_name, job_source=job_source)
    status_code = 200 if result.get("ok") else 400
    return jsonify(result | {"state": _timelapse_snapshot_state()}), status_code


@app.post("/api/timelapse/stop")
def api_timelapse_stop() -> Any:
    state = _timelapse_snapshot_state()
    if bool(state.get("stop_pending", False)) or bool(state.get("build_in_progress", False)) or bool(state.get("stopping", False)):
        return jsonify({"ok": True, "message": "Timelapse stop already in progress.", "state": state})
    if not (bool(state.get("active", False)) or bool(state.get("armed", False)) or bool(state.get("paused", False))):
        return jsonify({"ok": True, "message": "No active timelapse to stop.", "state": state})
    result = _timelapse_stop_internal(reason="manual")
    if result.get("ok"):
        result["message"] = "Timelapse stopped and saving/building output."
    return jsonify(result | {"state": _timelapse_snapshot_state()})


@app.get("/api/timelapses/open/<path:filename>")
def api_timelapses_open(filename: str) -> Any:
    out_dir = _timelapse_output_dir()
    p = (out_dir / str(filename or "")).resolve()
    if out_dir not in p.parents:
        return jsonify({"ok": False, "error": "invalid timelapse path"}), 400
    if not p.exists() or not p.is_file():
        return jsonify({"ok": False, "error": "timelapse not found"}), 404
    if p.suffix.lower() not in {".mp4", ".webm", ".mov", ".avi"}:
        return jsonify({"ok": False, "error": "unsupported timelapse file type"}), 400
    return send_file(str(p), as_attachment=False, download_name=p.name)


@app.post("/api/timelapses/delete")
def api_timelapses_delete() -> Any:
    body = request.get_json(silent=True) or {}
    filenames = body.get("filenames")
    if not isinstance(filenames, list) or not filenames:
        return jsonify({"ok": False, "message": "filenames must be a non-empty list"}), 400
    out_dir = _timelapse_output_dir()
    allowed = {".mp4", ".webm", ".mov", ".avi"}
    deleted: list[str] = []
    deleted_sessions: list[str] = []
    failed: list[dict[str, str]] = []
    for raw in filenames:
        name = str(raw or "").strip()
        if not name:
            failed.append({"filename": "", "error": "Empty filename."})
            continue
        lower = name.lower()
        if ".." in name or name.startswith("/") or "\\" in name or lower.startswith("http://") or lower.startswith("https://") or Path(name).is_absolute():
            failed.append({"filename": name, "error": "Invalid filename."})
            continue
        p = (out_dir / name).resolve()
        if out_dir not in p.parents:
            failed.append({"filename": name, "error": "Path traversal is not allowed."})
            continue
        if p.suffix.lower() not in allowed:
            failed.append({"filename": name, "error": "Unsupported timelapse file type."})
            continue
        if not p.exists():
            failed.append({"filename": name, "error": "File not found."})
            continue
        if not p.is_file():
            failed.append({"filename": name, "error": "Only files can be deleted."})
            continue
        try:
            p.unlink()
            deleted.append(p.name)
            console.add("info", f"Deleted timelapse: {p.name}")
            session_id = _timelapse_session_id_from_video_name(p.name)
            if session_id:
                session_dir = (out_dir / f"session_{session_id}").resolve()
                try:
                    if (
                        session_dir.exists()
                        and session_dir.is_dir()
                        and out_dir.resolve() in session_dir.parents
                        and session_dir.name.startswith("session_")
                    ):
                        shutil.rmtree(session_dir)
                        deleted_sessions.append(session_dir.name)
                        console.add("info", f"Deleted timelapse session folder: {session_dir.name}")
                except OSError as exc:
                    failed.append({"filename": name, "error": f"Video deleted, session folder delete failed: {exc}"})
        except OSError as exc:
            failed.append({"filename": name, "error": str(exc)})
    if failed:
        msg = f"Deleted {len(deleted)} timelapse file(s), {len(failed)} failed."
        return jsonify({"ok": False, "deleted": deleted, "deleted_sessions": deleted_sessions, "failed": failed, "message": msg}), 207
    msg = f"Deleted {len(deleted)} timelapse file(s)."
    return jsonify({"ok": True, "deleted": deleted, "deleted_sessions": deleted_sessions, "failed": [], "message": msg})


@app.get("/api/jobs")
def api_jobs() -> Any:
    return jsonify({"ok": True, "jobs": jobs.list_jobs()})


@app.post("/api/jobs/import")
def api_jobs_import() -> Any:
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "file is required"}), 400
    ext = Path(f.filename or "").suffix.lower()
    if ext not in jobs.allowed:
        return jsonify({"ok": False, "error": f"extension {ext!r} not allowed"}), 400
    content = f.read()
    if len(content) > _max_upload_bytes():
        return jsonify({"ok": False, "error": "file exceeds upload size limit"}), 400
    safety = jobs.validate_gcode_bytes(str(f.filename or ""), content)
    if not safety.get("ok"):
        console.add(
            "error",
            f"G-code safety scan failed: {f.filename} blocked as 3D printer G-code; matches={','.join(safety.get('matches', []))}",
        )
        return jsonify(
            {
                "ok": False,
                "message": "Blocked: this looks like 3D printer G-code, not laser G-code.",
                "reason": safety.get("reason", ""),
                "detected_type": safety.get("detected_type", "3d_printer"),
                "matches": safety.get("matches", []),
            }
        ), 400
    try:
        meta = jobs.import_uploaded_bytes(f.filename, content)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if safety.get("detected_type") == "unknown":
        console.add("warn", f"G-code safety scan warning: {meta.get('name')} detected=unknown allowed_by_config=true")
    else:
        console.add("info", f"G-code safety scan passed: {meta.get('name')} detected={safety.get('detected_type')}")
    console.add("info", f"Imported job: {meta.get('name')}")
    return jsonify({"ok": True, "job": meta})


@app.post("/api/jobs/frame")
def api_jobs_frame() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    filename = str(body.get("filename", "")).strip()
    framing = cfg.get("framing", {})
    margin = float(body.get("margin", framing.get("margin_mm", framing.get("frame_margin_mm", 2.0))))
    feed = float(body.get("feed", framing.get("feedrate", framing.get("frame_feedrate", 3000))))
    try:
        frame_plan = jobs.frame_commands(filename=filename, cfg=cfg, margin=margin, feed=feed)
    except ValueError as exc:
        console.add("error", f"Frame failed for {filename}: {exc}")
        return jsonify({"ok": False, "error": str(exc)}), 400

    job_bounds = frame_plan["job_bounds"]
    requested_bounds = frame_plan["requested_frame_bounds"]
    safe_bounds = frame_plan["safe_frame_bounds"]
    clamped = bool(frame_plan["clamped"])
    force_laser_off = bool(frame_plan["force_laser_off"])
    points = frame_plan["points"]
    cmds = frame_plan["commands"]
    if frame_plan.get("bounds_source") == "lightburn_bounds_comment":
        console.add(
            "info",
            f"Bounds parsed from LightBurn comment: X {job_bounds['min_x']:.3f}..{job_bounds['max_x']:.3f} Y {job_bounds['min_y']:.3f}..{job_bounds['max_y']:.3f}",
        )
    console.add(
        "info",
        f"Frame job bounds: X {job_bounds['min_x']:.3f}..{job_bounds['max_x']:.3f} Y {job_bounds['min_y']:.3f}..{job_bounds['max_y']:.3f}",
    )
    console.add(
        "info",
        f"Frame requested with margin: X {requested_bounds['min_x']:.3f}..{requested_bounds['max_x']:.3f} Y {requested_bounds['min_y']:.3f}..{requested_bounds['max_y']:.3f}",
    )
    console.add(
        "info",
        f"Frame safe bounds: X {safe_bounds['min_x']:.3f}..{safe_bounds['max_x']:.3f} Y {safe_bounds['min_y']:.3f}..{safe_bounds['max_y']:.3f} clamped={'true' if clamped else 'false'}",
    )

    console.add("info", f"Frame requested: filename={filename}")
    cmd_results: list[dict[str, Any]] = []
    frame_ok = True
    err_msg = ""
    try:
        if force_laser_off:
            ray5.send_gcode("M5")
        result = ray5.send_gcode(cmds)
        cmd_results.append(
            {
                "command_count": len(cmds),
                "ok": bool(result.get("ok")),
                "response_preview": str(result.get("raw", ""))[:160],
                "endpoint": result.get("endpoint"),
                "param": result.get("param"),
            }
        )
        console.add(
            "info",
            f"Ray5 command send: count={len(cmds)} endpoint={result.get('endpoint','/command')} param={result.get('param','cmd')}",
        )
        console.add("info", f"Ray5 command response: {'ok' if result.get('ok') else 'fail'}")
        if not result.get("ok"):
            frame_ok = False
            err_msg = "Frame command batch failed"
    finally:
        if force_laser_off:
            ray5.send_gcode("M5")
    if not frame_ok:
        console.add("error", f"Frame failed: {err_msg}")
        return jsonify({"ok": False, "error": err_msg, "commands": cmds, "results": cmd_results}), 502
    console.add("info", "Frame complete")
    return jsonify(
        {
            "ok": True,
            "message": "Frame complete. Margin was clamped to the machine edge." if clamped else "Frame complete.",
            "clamped": clamped,
            "job_bounds": job_bounds,
            "requested_frame_bounds": requested_bounds,
            "safe_frame_bounds": safe_bounds,
            "bounds": safe_bounds,
            "commands": cmds,
            "points": points,
            "results": cmd_results,
        }
    )


@app.post("/api/jobs/upload")
def api_jobs_upload() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    filename = str(body.get("filename", "")).strip()
    try:
        p = jobs.safe_imported_path(filename)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not p.exists():
        return jsonify({"ok": False, "error": "Job file not found"}), 404
    if not p.is_file() or p.suffix.lower() not in jobs.allowed:
        return jsonify({"ok": False, "error": "Invalid job file type"}), 400
    if p.stat().st_size > _max_upload_bytes():
        return jsonify({"ok": False, "error": "file exceeds upload size limit"}), 400
    safety = jobs.validate_gcode_path(p)
    if not safety.get("ok"):
        console.add(
            "error",
            f"G-code safety scan failed: {filename} blocked as 3D printer G-code; matches={','.join(safety.get('matches', []))}",
        )
        return jsonify(
            {
                "ok": False,
                "message": "Blocked: this looks like 3D printer G-code, not laser G-code.",
                "reason": safety.get("reason", ""),
                "detected_type": safety.get("detected_type", "3d_printer"),
                "matches": safety.get("matches", []),
            }
        ), 400
    if safety.get("detected_type") == "unknown":
        console.add("warn", f"G-code safety scan warning: {filename} detected=unknown allowed_by_config=true")
    else:
        console.add("info", f"G-code safety scan passed: {filename} detected={safety.get('detected_type')}")
    detail = ray5.upload_file_detailed(p)
    if detail.get("filename_shortened"):
        console.add(
            "info",
            f"Ray5 upload filename shortened: original='{detail.get('original_filename', filename)}' final='{detail.get('upload_filename', '')}'",
        )
    console.add(
        "info",
        f"Upload source size={detail.get('source_size')} sha256={str(detail.get('source_sha256',''))[:12]} "
        f"payload_size={detail.get('payload_size')} payload_sha256={str(detail.get('payload_sha256',''))[:12]} "
        f"preserve_original={str(detail.get('preserve_original')).lower()} rewrite_used={str(detail.get('rewrite_used')).lower()}",
    )
    if detail.get("rewrite_used"):
        console.add("warn", "Upload rewrite enabled; uploaded file may differ from source.")
    console.add(
        "info",
        f"Upload start local={filename} upload={detail.get('upload_filename')} ext={Path(str(detail.get('upload_filename',''))).suffix} "
        f"endpoint={detail.get('endpoint')} method={detail.get('method')} params_keys={list((detail.get('params') or {}).keys())} "
        f"file_field={detail.get('file_field')} size={detail.get('file_size')}",
    )
    if detail.get("ok"):
        console.add(
            "info",
            f"Upload end: {filename} => ok status={detail.get('upload_status_code')} preview={str(detail.get('upload_response',''))[:120]}",
        )
        return jsonify(detail | {
            "source_size": detail.get("source_size"),
            "payload_size": detail.get("payload_size"),
            "preserve_original": detail.get("preserve_original"),
            "rewrite_used": detail.get("rewrite_used"),
        })
    console.add(
        "error",
        f"Ray5 upload failed endpoint={detail.get('endpoint')} method={detail.get('method')} filename={detail.get('upload_filename')} "
        f"status={detail.get('upload_status_code')} body_preview={str(detail.get('upload_response',''))[:160]} error={detail.get('error','')}",
    )
    return jsonify(detail), 502


@app.post("/api/jobs/start")
def api_jobs_start() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    filename = str(body.get("filename", "")).strip()
    try:
        local_path = jobs.safe_imported_path(filename)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not local_path.exists():
        return jsonify({"ok": False, "error": "Job file not found"}), 404
    if not local_path.is_file() or local_path.suffix.lower() not in jobs.allowed:
        return jsonify({"ok": False, "error": "Invalid job file type"}), 400
    if local_path.stat().st_size > _max_upload_bytes():
        return jsonify({"ok": False, "error": "file exceeds upload size limit"}), 400
    safety = jobs.validate_gcode_path(local_path)
    if not safety.get("ok"):
        console.add(
            "error",
            f"G-code safety scan failed: {filename} blocked as 3D printer G-code; matches={','.join(safety.get('matches', []))}",
        )
        return jsonify(
            {
                "ok": False,
                "message": "Blocked: this looks like 3D printer G-code, not laser G-code.",
                "reason": safety.get("reason", ""),
                "detected_type": safety.get("detected_type", "3d_printer"),
                "matches": safety.get("matches", []),
            }
        ), 400
    if safety.get("detected_type") == "unknown":
        console.add("warn", f"G-code safety scan warning: {filename} detected=unknown allowed_by_config=true")
    else:
        console.add("info", f"G-code safety scan passed: {filename} detected={safety.get('detected_type')}")
    console.add("info", f"Start request: {filename}")
    upload_detail = ray5.upload_file_detailed(local_path)
    if upload_detail.get("filename_shortened"):
        console.add(
            "info",
            f"Ray5 upload filename shortened: original='{upload_detail.get('original_filename', filename)}' final='{upload_detail.get('upload_filename', '')}'",
        )
    upload_ok = bool(upload_detail.get("ok"))
    console.add(
        "info",
        f"Upload source size={upload_detail.get('source_size')} sha256={str(upload_detail.get('source_sha256',''))[:12]} "
        f"payload_size={upload_detail.get('payload_size')} payload_sha256={str(upload_detail.get('payload_sha256',''))[:12]} "
        f"preserve_original={str(upload_detail.get('preserve_original')).lower()} rewrite_used={str(upload_detail.get('rewrite_used')).lower()}",
    )
    if upload_detail.get("rewrite_used"):
        console.add("warn", "Upload rewrite enabled; uploaded file may differ from source.")
    if not upload_ok:
        console.add("error", f"Start blocked: upload failed for {filename}")
        return jsonify({"ok": False, "error": "Upload failed before start", "upload": upload_detail}), 400
    machine_filename = str(upload_detail.get("upload_filename") or filename)
    ok, resp = ray5.start_file(machine_filename)
    console.add("info", f"Start result {filename}: {'ok' if ok else 'fail'} {str(resp)[:120]}")
    timelapse_arm = None
    if ok:
        _record_job_activity(source="imported_start", name=filename)
        timelapse_arm = _timelapse_arm(job_name=filename, job_source="imported")
    return jsonify({"ok": ok, "response": resp, "upload_ok": upload_ok, "upload": upload_detail, "run_filename": machine_filename, "timelapse_arm": timelapse_arm})


@app.delete("/api/jobs/<path:filename>")
def api_jobs_delete(filename: str) -> Any:
    try:
        jobs.delete_job(filename)
        console.add("info", f"Deleted job: {filename}")
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/imported-files/delete")
def api_imported_files_delete() -> Any:
    body = request.get_json(silent=True) or {}
    filenames = body.get("filenames")
    if not isinstance(filenames, list) or not filenames:
        return jsonify({"ok": False, "message": "filenames must be a non-empty list"}), 400

    deleted: list[str] = []
    failed: list[dict[str, str]] = []

    for raw_name in filenames:
        filename = str(raw_name or "").strip()
        if not filename:
            failed.append({"filename": "", "error": "Empty filename."})
            continue
        if Path(filename).is_absolute():
            failed.append({"filename": filename, "error": "Absolute paths are not allowed."})
            continue
        try:
            p = jobs.safe_imported_path(filename)
        except ValueError:
            failed.append({"filename": filename, "error": "Invalid imported job path."})
            continue

        try:
            rel = p.resolve().relative_to(jobs.imported_dir.resolve())
        except ValueError:
            failed.append({"filename": filename, "error": "Path escapes imported jobs folder."})
            continue
        if rel.parts and rel.parts[0] == "..":
            failed.append({"filename": filename, "error": "Path traversal is not allowed."})
            continue
        if not p.exists():
            failed.append({"filename": filename, "error": "File not found."})
            continue
        if not p.is_file():
            failed.append({"filename": filename, "error": "Only files can be deleted."})
            continue
        try:
            p.unlink()
            deleted.append(p.name)
            console.add("info", f"Deleted imported job: {p.name}")
        except OSError as exc:
            failed.append({"filename": filename, "error": str(exc)})

    if failed:
        msg = f"Deleted {len(deleted)} imported file(s), {len(failed)} failed."
        return jsonify({"ok": False, "deleted": deleted, "failed": failed, "message": msg}), 207
    msg = f"Deleted {len(deleted)} imported file(s)."
    return jsonify({"ok": True, "deleted": deleted, "failed": [], "message": msg})


@app.post("/api/home")
def api_home() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    axis = str(body.get("axis", "all")).strip().lower()
    console.add("info", f"Home {axis} requested")
    result = ray5.home(axis=axis)
    console.add("info", f"Home result: {'ok' if result.get('ok') else 'fail'} {str(result.get('message',''))[:120]}")
    return jsonify(result)


@app.post("/api/unlock")
def api_unlock() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    console.add("info", "Unlock / Clear Alarm requested")
    result = ray5.clear_alarm()
    steps = result.get("steps", {}) if isinstance(result.get("steps"), dict) else {}
    m5 = steps.get("M5", {}) if isinstance(steps.get("M5"), dict) else {}
    x = steps.get("$X", {}) if isinstance(steps.get("$X"), dict) else {}
    console.add("info", f"Command M5 => {'ok' if m5.get('ok') else 'fail'}")
    console.add("info", f"Command $X => {'ok' if x.get('ok') else 'fail'}")
    console.add("info", f"Unlock / Clear Alarm result: {'ok' if result.get('ok') else 'fail'}")
    if not result.get("ok"):
        dbg = ray5.debug_info(str(cfg_mgr.config_path))
        console.add(
            "error",
            "Unlock failed "
            f"endpoint={dbg.get('file_list_endpoint_attempted') or '/command'} method={dbg.get('method')} "
            f"status={dbg.get('http_status_code')} preview={dbg.get('response_preview')} error={dbg.get('last_error')}",
        )
    status_after = ray5.status()
    console.add("info", "Status refreshed after unlock")
    return jsonify({"ok": bool(result.get("ok")), "message": result.get("message", ""), "raw": result.get("raw", ""), "status": status_after})


@app.post("/api/alarm/clear")
def api_alarm_clear() -> Any:
    return api_unlock()


@app.post("/api/move")
def api_move() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    controls = cfg.get("manual_controls", {})
    axis = str(body.get("axis", "")).strip().lower()
    distance = float(body.get("distance", controls.get("default_jog_step", controls.get("default_jog_step_mm", 10))))
    feedrate = float(body.get("feedrate", controls.get("default_feedrate", 3000)))
    dx_in = body.get("dx")
    dy_in = body.get("dy")
    has_dx = dx_in is not None
    has_dy = dy_in is not None
    if has_dx or has_dy:
        dx = float(dx_in or 0.0)
        dy = float(dy_in or 0.0)
        if dx == 0.0 and dy == 0.0:
            return jsonify({"ok": False, "message": "dx/dy move requires non-zero delta", "raw": ""}), 400
        if bool(controls.get("force_laser_off_before_move", True)):
            ray5.laser_off()
        console.add("info", f"Manual move XY X{dx:.3f} Y{dy:.3f} F{feedrate:.0f}")
        cmd = f"$J=G91 G21 X{dx:.3f} Y{dy:.3f} F{feedrate:.0f}"
        result = ray5.send_gcode(cmd)
        console.add("info", f"Move result: {'ok' if result.get('ok') else 'fail'} {str(result.get('message',''))[:120]}")
        return jsonify(result)
    if axis == "z" and not bool(controls.get("enable_z_jog", controls.get("enable_jog_z", False))):
        return jsonify({"ok": False, "message": "Z jog is disabled in config", "raw": ""}), 400
    if bool(controls.get("force_laser_off_before_move", True)):
        ray5.laser_off()
    console.add("info", f"Manual move {axis.upper()} {distance}mm F{feedrate}")
    result = ray5.move(axis=axis, distance=distance, feedrate=feedrate)
    console.add("info", f"Move result: {'ok' if result.get('ok') else 'fail'} {str(result.get('message',''))[:120]}")
    return jsonify(result)


@app.post("/api/manual/center")
def api_manual_center() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    mc = cfg.get("manual_controls", {}) if isinstance(cfg.get("manual_controls"), dict) else {}
    machine = cfg.get("machine", {}) if isinstance(cfg.get("machine"), dict) else {}
    min_x = float(machine.get("min_x", 0))
    min_y = float(machine.get("min_y", 0))
    max_x = float(machine.get("max_x", machine.get("bed_width_mm", 390)))
    max_y = float(machine.get("max_y", machine.get("bed_height_mm", 360)))
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    feed = float(mc.get("preset_feedrate", mc.get("default_feedrate", 1500)))
    if feed <= 0:
        return jsonify({"ok": False, "message": "Center move feedrate must be positive."}), 400
    console.add("info", f"Manual center move requested: X={center_x:.3f} Y={center_y:.3f} F={feed:.0f}")
    result = ray5.send_gcode(["M5", "G21", "G90", f"G0 X{center_x:.3f} Y{center_y:.3f} F{feed:.0f}"])
    ok = bool(result.get("ok"))
    console.add("info", f"Manual center move result: {'ok' if ok else 'failed'} {str(result.get('message',''))[:120]}")
    return jsonify({"ok": ok, "message": (f"Moved to bed center X={center_x:.3f} Y={center_y:.3f}" if ok else str(result.get("message", "Center move failed"))), "raw": result.get("raw", ""), "x": center_x, "y": center_y})


@app.post("/api/preset-move")
def api_preset_move() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    mc = cfg.get("manual_controls", {}) if isinstance(cfg.get("manual_controls"), dict) else {}
    if not bool(mc.get("preset_enabled", True)):
        return jsonify({"ok": False, "message": "Preset move is disabled in settings."}), 400
    machine = cfg.get("machine", {}) if isinstance(cfg.get("machine"), dict) else {}
    min_x = float(machine.get("min_x", 0))
    min_y = float(machine.get("min_y", 0))
    max_x = float(machine.get("max_x", machine.get("bed_width_mm", 390)))
    max_y = float(machine.get("max_y", machine.get("bed_height_mm", 360)))
    x = float(mc.get("preset_x", 0))
    y = float(mc.get("preset_y", 0))
    feed = float(mc.get("preset_feedrate", 1500))
    if feed <= 0:
        return jsonify({"ok": False, "message": "Preset feedrate must be positive."}), 400
    if x < min_x or x > max_x or y < min_y or y > max_y:
        return jsonify({"ok": False, "message": f"Preset is outside machine bounds: X {min_x}..{max_x} Y {min_y}..{max_y}"}), 400
    console.add("info", f"Manual preset move requested: X={x:.3f} Y={y:.3f} F={feed:.0f}")
    result = ray5.send_gcode(["M5", "G21", "G90", f"G0 X{x:.3f} Y{y:.3f} F{feed:.0f}"])
    ok = bool(result.get("ok"))
    console.add("info", f"Manual preset move result: {'ok' if ok else 'failed'} {str(result.get('message',''))[:120]}")
    return jsonify({"ok": ok, "message": (f"Moved to preset X{x:.3f} Y{y:.3f}" if ok else str(result.get("message", "Preset move failed"))), "raw": result.get("raw", "")})


@app.post("/api/laser/off")
def api_laser_off() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    console.add("warn", "Laser off requested")
    result = ray5.laser_off()
    console.add("warn", f"Laser off result: {'ok' if result.get('ok') else 'fail'}")
    return jsonify(result)


@app.post("/api/laser/test-fire")
def api_test_fire() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    try:
        console.add("warn", "Test fire requested")
        safety = cfg.get("safety", {})
        enabled = bool(safety.get("test_fire_enabled", safety.get("enable_test_fire", False)))
        if not enabled:
            console.add("warn", "Test fire blocked by safety config")
            return jsonify({"ok": False, "error": "test fire disabled"}), 403
        body = request.get_json(silent=True) or {}
        req_power = int(body.get("power", safety.get("test_fire_power", 1)))
        req_duration_ms = int(body.get("duration_ms", safety.get("test_fire_duration_ms", 100)))
        req_s_value = int(body.get("s_value", safety.get("test_fire_s_value", 50)))
        max_power = int(safety.get("test_fire_max_power", 12))
        max_duration_ms = int(safety.get("test_fire_max_duration_ms", 5000))
        max_s_value = int(safety.get("test_fire_max_s_value", 500))
        use_direct_s = bool(safety.get("test_fire_use_direct_s_value", True))
        power_is_percent = bool(safety.get("test_fire_power_is_percent", True))
        s_max = max(1, int(safety.get("test_fire_s_max", 1000)))
        test_mode = str(safety.get("test_fire_mode", "stationary_m4")).strip().lower()
        test_cmd = str(safety.get("test_fire_command", "M4")).strip().upper()
        motion_axis = str(safety.get("test_fire_motion_axis", "X")).strip().upper() or "X"
        motion_mm = float(safety.get("test_fire_motion_mm", 1.0))
        motion_feedrate = float(safety.get("test_fire_motion_feedrate", 300))
        if test_mode not in {"stationary_m3", "stationary_m4", "motion_pulse"}:
            test_mode = "stationary_m4"
        if test_mode == "stationary_m3":
            test_cmd = "M3"
        elif test_mode == "stationary_m4":
            test_cmd = "M4"
        if test_cmd not in {"M3", "M4"}:
            test_cmd = "M4" if test_mode in {"stationary_m4", "motion_pulse"} else "M3"
        console.add("warn", f"Test Fire requested: input_power={req_power} duration_ms={req_duration_ms}")
        power = max(0, min(max_power, req_power))
        duration_ms = max(10, min(max_duration_ms, req_duration_ms))
        if use_direct_s:
            s_value = max(0, min(max_s_value, req_s_value))
            power_percent = int(round((float(s_value) / float(s_max)) * 100.0))
        else:
            if power_is_percent:
                s_value = int(round((float(power) / 100.0) * float(s_max)))
                power_percent = power
            else:
                s_value = power
                power_percent = int(round((float(s_value) / float(s_max)) * 100.0))
        if s_value <= 0:
            msg = "Test fire S value is 0. Increase test fire power or check test_fire_s_max."
            console.add("error", msg)
            return jsonify({"ok": False, "message": msg, "power_percent": power_percent, "s_value": s_value, "duration_ms": duration_ms}), 400
        console.add("warn", f"Test Fire clamped: percent={power_percent} s_value={s_value} duration_ms={duration_ms}")
        result = ray5.test_fire(
            s_value=s_value,
            duration_ms=duration_ms,
            command=test_cmd,
            mode=test_mode,
            motion_axis=motion_axis,
            motion_mm=motion_mm,
            motion_feedrate=motion_feedrate,
        )
        page_id_used = str(
            result.get("page_id_used")
            or result.get("page_id")
            or ("0" if result.get("page_id_fallback") else "0")
        )
        if page_id_used == "0" and bool(result.get("page_id_fallback")):
            console.add("warn", "No active PAGEID found; using PAGEID=0")
        console.add("warn", f"PAGEID used: {page_id_used}")
        command_list = result.get("commands") if isinstance(result.get("commands"), list) else []
        if not command_list:
            command_list = [f"{test_cmd} S{s_value}", "M5"]
        if test_mode == "motion_pulse":
            console.add("warn", f"Test Fire command on: {test_cmd} S{s_value}")
            for cmd_line in command_list:
                if str(cmd_line).strip().upper() == "M5":
                    console.add("warn", "Test Fire command off: M5")
                else:
                    console.add("warn", f"Test Fire command step: {cmd_line}")
        else:
            for idx, cmd_line in enumerate(command_list):
                if idx == 0:
                    console.add("warn", f"Test Fire command on: {cmd_line}")
                elif idx == len(command_list) - 1 and str(cmd_line).strip().upper() == "M5":
                    console.add("warn", "Test Fire command off: M5")
                else:
                    console.add("warn", f"Test Fire command step: {cmd_line}")
        steps = result.get("steps", {}) if isinstance(result.get("steps"), dict) else {}
        if steps:
            for step_name, step_result in steps.items():
                console.add("warn", f"Test fire step {step_name}: {'ok' if step_result.get('ok') else 'fail'} {str(step_result.get('message',''))[:120]}")
        if not result.get("ok"):
            console.add("error", f"Test fire failed: {str(result.get('message','unknown'))[:120]}")
        console.add("warn", "Test Fire complete; laser forced off")
        response = (
            result
            | {
                "power": power,
                "mode": test_mode,
                "command": test_cmd,
                "power_percent": power_percent,
                "s_value": s_value,
                "duration_ms": duration_ms,
                "page_id": page_id_used,
                "commands": command_list,
            }
        )
        if test_mode == "motion_pulse":
            response |= {
                "motion_mm": motion_mm,
                "motion_axis": motion_axis,
                "motion_feedrate": motion_feedrate,
            }
        return jsonify(response)
    except Exception as exc:
        console.add("error", f"Test fire failed: {exc}")
        return jsonify({"ok": False, "message": f"Test fire failed: {exc}"}), 500


@app.post("/api/air/on")
def api_air_on() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    console.add("info", "Air assist on requested")
    result = ray5.air_on()
    console.add("info", f"Air on result: {'ok' if result.get('ok') else 'fail'} {str(result.get('message',''))[:120]}")
    return jsonify(result)


@app.post("/api/air/off")
def api_air_off() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    console.add("info", "Air assist off requested")
    result = ray5.air_off()
    console.add("info", f"Air off result: {'ok' if result.get('ok') else 'fail'} {str(result.get('message',''))[:120]}")
    return jsonify(result)


@app.post("/api/stop")
def api_stop() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    console.add("warn", "Stop Job requested")
    jc = cfg.get("job_control", {}) if isinstance(cfg.get("job_control"), dict) else {}
    stop_mode = str(jc.get("stop_mode", "hold_only")).strip().lower()
    console.add("warn", f"Stop mode: {stop_mode}")
    result = ray5.stop_job()
    if stop_mode == "soft_reset":
        steps = result.get("steps", {}) if isinstance(result.get("steps"), dict) else {}
        if "M5" in steps:
            console.add("warn", f"Command M5 => {'ok' if steps.get('M5', {}).get('ok') else 'fail'}")
        if "CTRL_X" in steps:
            console.add("warn", f"Command Ctrl-X soft reset => {'ok' if steps.get('CTRL_X', {}).get('ok') else 'fail'}")
        if "$X" in steps:
            console.add("warn", f"Command $X => {'ok' if steps.get('$X', {}).get('ok') else 'fail'}")
    console.add("warn", f"Stop Job result: {'ok' if result.get('ok') else 'fail'} {str(result.get('message',''))[:120]}")
    status_after = None
    if bool(jc.get("stop_refresh_status_after", True)):
        try:
            if status_monitor is not None:
                pid = status_monitor.get_page_id()
                if pid not in (None, ""):
                    ray5.trigger_live_status(str(pid))
            time.sleep(0.25)
            status_after = status_monitor.get_latest_status() if status_monitor is not None else None
        except Exception:
            status_after = None
    return jsonify(result | {"status_after": status_after})


@app.post("/api/pause")
def api_pause() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    console.add("warn", "Pause requested")
    result = ray5.pause_job()
    console.add("warn", f"Pause result: {'ok' if result.get('ok') else 'fail'} {str(result.get('message',''))[:120]}")
    return jsonify(result)


@app.post("/api/resume")
def api_resume() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    console.add("warn", "Resume requested")
    result = ray5.resume_job()
    console.add("warn", f"Resume result: {'ok' if result.get('ok') else 'fail'} {str(result.get('message',''))[:120]}")
    return jsonify(result)


@app.get("/api/files")
def api_files() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    req_path = str(request.args.get("path", cfg.get("ray5", {}).get("sd_path", "/")) or "/")
    console.add("info", f"SD refresh requested path={req_path}")
    data = ray5.list_files(path=req_path)
    if not data.get("ok"):
        _set_system_check_flag("ray5_http_reachable", False)
        _set_system_check_flag("sd_card_list_working", False)
        dbg = ray5.debug_info(str(cfg_mgr.config_path))
        console.add(
            "error",
            "RAY5 HTTP request failed "
            f"endpoint={dbg.get('file_list_endpoint_attempted')} "
            f"params={dbg.get('files_params')} method={dbg.get('method')} "
            f"url={dbg.get('url')} status={dbg.get('http_status_code')} error={dbg.get('last_error')}",
        )
    else:
        storage = data.get("storage", {})
        _set_system_check_flag("ray5_http_reachable", True)
        _set_system_check_flag("sd_card_list_working", True)
        console.add(
            "info",
            f"SD refresh ok files={len(data.get('files', []))} used={storage.get('used', '---')} total={storage.get('total', '---')}",
        )
    return jsonify(data)


@app.post("/api/files/start")
def api_files_start() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    filename = str(body.get("filename", "")).strip()
    req_path = str(body.get("path", cfg.get("ray5", {}).get("sd_path", "/")) or "/")
    if not filename:
        return jsonify({"ok": False, "message": "filename is required"}), 400
    listing = ray5.list_files(path=req_path)
    if not listing.get("ok"):
        return jsonify({"ok": False, "message": "Unable to validate file from SD listing", "raw": listing.get("error", "")}), 400
    selected = next((f for f in listing.get("files", []) if str(f.get("name")) == filename), None)
    if not selected:
        return jsonify({"ok": False, "message": "File not found on SD list"}), 404
    if not bool(selected.get("can_start", False)):
        return jsonify({"ok": False, "message": "Selected entry cannot be started"}), 400
    console.add("info", f"SD start requested file={filename}")
    result = ray5.start_sd_file(str(selected.get("path") or filename))
    console.add("info", f"SD start {'ok' if result.get('ok') else 'fail'} file={filename}")
    timelapse_arm = None
    if result.get("ok"):
        _record_job_activity(source="sd_start", name=filename)
        timelapse_arm = _timelapse_arm(job_name=filename, job_source="sd")
    return jsonify(result | {"timelapse_arm": timelapse_arm})


@app.post("/api/files/upload")
def api_files_upload() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "message": "file is required"}), 400
    filename = Path(str(f.filename or "")).name
    ext = Path(filename).suffix.lower()
    if ext not in {".gc", ".nc", ".gcode"}:
        return jsonify({"ok": False, "message": f"extension {ext!r} not allowed"}), 400
    req_path = str(request.form.get("path", cfg.get("ray5", {}).get("sd_path", "/")) or "/")
    data = f.read()
    if len(data) > _max_upload_bytes():
        return jsonify({"ok": False, "message": "file exceeds upload size limit"}), 400
    safety = jobs.validate_gcode_bytes(filename, data)
    if not safety.get("ok"):
        console.add(
            "error",
            f"G-code safety scan failed: {filename} blocked as 3D printer G-code; matches={','.join(safety.get('matches', []))}",
        )
        return jsonify(
            {
                "ok": False,
                "message": "Blocked: this looks like 3D printer G-code, not laser G-code.",
                "reason": safety.get("reason", ""),
                "detected_type": safety.get("detected_type", "3d_printer"),
                "matches": safety.get("matches", []),
            }
        ), 400
    if safety.get("detected_type") == "unknown":
        console.add("warn", f"G-code safety scan warning: {filename} detected=unknown allowed_by_config=true")
    else:
        console.add("info", f"G-code safety scan passed: {filename} detected={safety.get('detected_type')}")
    console.add("info", f"SD direct upload start: {filename} size={len(data)} path={req_path}")
    result = ray5.upload_bytes_to_sd(filename=filename, data=data, path=req_path)
    if result.get("filename_shortened"):
        console.add(
            "info",
            f"Ray5 upload filename shortened: original='{result.get('original_filename', filename)}' final='{result.get('filename', filename)}'",
        )
    if result.get("ok"):
        console.add("info", f"SD direct upload end: {filename} => ok")
        return jsonify(
            {
                "ok": True,
                "filename": result.get("filename", filename),
                "path": result.get("path", req_path),
                "size": int(result.get("size", len(data))),
                "message": "Uploaded to SD",
            }
        )
    console.add("error", f"SD direct upload failed: {filename} => {result.get('message', 'unknown error')}")
    return jsonify({"ok": False, "filename": filename, "path": req_path, "size": len(data), "message": result.get("message", "Upload failed")}), 502


@app.delete("/api/files/delete")
def api_files_delete() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    filename = str(body.get("filename", "")).strip()
    req_path = str(body.get("path", cfg.get("ray5", {}).get("sd_path", "/")) or "/")
    if not filename:
        return jsonify({"ok": False, "message": "filename is required"}), 400
    listing = ray5.list_files(path=req_path)
    if not listing.get("ok"):
        return jsonify({"ok": False, "message": "Unable to validate file from SD listing", "raw": listing.get("error", "")}), 400
    selected = next((f for f in listing.get("files", []) if str(f.get("name")) == filename), None)
    if not selected:
        return jsonify({"ok": False, "message": "File not found on SD list"}), 404
    if not bool(selected.get("can_delete", False)):
        return jsonify({"ok": False, "message": "Selected entry cannot be deleted"}), 400
    console.add("warn", f"SD delete requested file={filename}")
    result = ray5.delete_sd_file(str(selected.get("path") or filename))
    console.add("warn", f"SD delete {'ok' if result.get('ok') else 'fail'} file={filename}")
    return jsonify(result)


@app.post("/api/files/delete")
def api_files_delete_post() -> Any:
    return api_files_delete()


@app.post("/api/sd-files/delete")
def api_sd_files_delete() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    req_path = str(body.get("path", cfg.get("ray5", {}).get("sd_path", "/")) or "/")
    files_in = body.get("files")
    filenames = body.get("filenames")

    requested: list[dict[str, str]] = []
    if isinstance(files_in, list):
        for item in files_in:
            if isinstance(item, dict):
                requested.append(
                    {
                        "name": str(item.get("name", "")).strip(),
                        "path": str(item.get("path", "")).strip(),
                    }
                )
    elif isinstance(filenames, list):
        for name in filenames:
            requested.append({"name": str(name or "").strip(), "path": ""})
    else:
        return jsonify({"ok": False, "message": "files or filenames must be a non-empty list"}), 400

    if not requested:
        return jsonify({"ok": False, "message": "files or filenames must be a non-empty list"}), 400

    listing = ray5.list_files(path=req_path)
    if not listing.get("ok"):
        return jsonify({"ok": False, "message": "Unable to validate files from SD listing", "raw": listing.get("error", "")}), 400

    listed_files = listing.get("files", []) if isinstance(listing.get("files"), list) else []
    by_name: dict[str, list[dict[str, Any]]] = {}
    by_path: dict[str, dict[str, Any]] = {}
    for f in listed_files:
        nm = str(f.get("name", "")).strip()
        pth = str(f.get("path", "")).strip()
        if nm:
            by_name.setdefault(nm, []).append(f)
        if pth:
            by_path[pth] = f

    deleted: list[str] = []
    failed: list[dict[str, str]] = []

    def _invalid_target(val: str) -> bool:
        low = val.lower()
        return (
            not val
            or ".." in val
            or low.startswith("http://")
            or low.startswith("https://")
            or "\\" in val
            or re.match(r"^[a-zA-Z]:", val) is not None
        )

    for item in requested:
        name = str(item.get("name", "")).strip()
        req_item_path = str(item.get("path", "")).strip()
        if _invalid_target(name):
            failed.append({"filename": name or "", "path": req_item_path, "error": "Invalid filename."})
            continue
        if req_item_path and _invalid_target(req_item_path):
            failed.append({"filename": name, "path": req_item_path, "error": "Invalid file path."})
            continue

        selected = None
        if req_item_path:
            selected = by_path.get(req_item_path)
        if selected is None:
            candidates = by_name.get(name, [])
            selected = candidates[0] if len(candidates) == 1 else None
        if selected is None:
            failed.append({"filename": name, "path": req_item_path, "error": "File not found on SD list."})
            continue
        if not bool(selected.get("can_delete", False)) or bool(selected.get("is_directory", False)):
            failed.append({"filename": name, "path": str(selected.get("path", req_item_path or "")), "error": "Selected entry cannot be deleted."})
            continue

        sd_target = str(selected.get("path") or selected.get("name") or "").strip()
        if _invalid_target(sd_target):
            failed.append({"filename": name, "path": sd_target, "error": "Unsafe SD target path."})
            continue

        console.add("warn", f"SD batch delete requested file={name} path={sd_target}")
        result = ray5.delete_sd_file(sd_target)
        if result.get("ok"):
            deleted.append(str(selected.get("name") or name))
            console.add("warn", f"SD batch delete ok file={name}")
        else:
            failed.append(
                {
                    "filename": name,
                    "path": sd_target,
                    "error": str(result.get("message") or "File not found or delete failed."),
                }
            )
            console.add("warn", f"SD batch delete fail file={name}")

    if failed:
        msg = f"Deleted {len(deleted)} SD file(s), {len(failed)} failed."
        return jsonify({"ok": False, "deleted": deleted, "failed": failed, "message": msg}), 207
    msg = f"Deleted {len(deleted)} SD file(s)."
    return jsonify({"ok": True, "deleted": deleted, "failed": [], "message": msg})


@app.post("/api/files/refresh")
def api_files_refresh() -> Any:
    return api_files()


@app.get("/api/debug/ray5")
def api_debug_ray5() -> Any:
    probe = ray5.list_files()
    dbg = ray5.debug_info(str(cfg_mgr.config_path))
    online = bool(ray5.connectivity().get("connected"))
    return jsonify(
        {
            "ok": True,
            "config_path": str(cfg_mgr.config_path),
            "ray5_host": dbg.get("ray5_host"),
            "ray5_port": dbg.get("ray5_port"),
            "base_url": dbg.get("base_url"),
            "files_endpoint": dbg.get("files_endpoint"),
            "files_params": dbg.get("files_params"),
            "file_list_endpoint_attempted": dbg.get("file_list_endpoint_attempted"),
            "http_status_code": dbg.get("http_status_code"),
            "online": online,
            "success": bool(probe.get("ok")),
            "response_preview": dbg.get("response_preview"),
            "last_error": probe.get("error") or dbg.get("last_error"),
            "method": dbg.get("method"),
            "url": dbg.get("url"),
        }
    )


@app.get("/api/debug/ray5/device-info")
def api_debug_ray5_device_info() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    result = ray5.get_device_info()
    raw = str(result.get("raw", ""))
    txt = raw.strip()
    parsed: Any | None = None
    if txt.startswith("{") or txt.startswith("["):
        try:
            parsed = _sanitize_debug_obj(json.loads(txt))
        except Exception:
            parsed = None
    sanitized_lines = _sanitize_plain_text_lines(raw) if parsed is None else []
    return jsonify(
        {
            "ok": bool(result.get("ok")),
            "message": str(result.get("message", "")),
            "count": int(result.get("count", 1) or 1),
            "param": "plain",
            "sanitized": True,
            "parsed": parsed,
            "lines": sanitized_lines,
            "raw": ("\n".join(sanitized_lines) if parsed is None else ""),
        }
    )


@app.get("/api/debug/ray5/keepalive")
def api_debug_ray5_keepalive() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    result = ray5.keepalive_ping()
    return jsonify(
        {
            "ok": bool(result.get("ok")),
            "message": str(result.get("message", "ok")),
            "count": int(result.get("count", 1) or 1),
        }
    )


@app.get("/api/debug/ray5/settings-info")
def api_debug_ray5_settings_info() -> Any:
    guard = _require_ray5_configured()
    if guard:
        return guard
    result = ray5.keepalive_ping()
    raw = str(result.get("raw", ""))
    rows = _sanitize_debug_obj(_parse_and_sanitize_esp400(raw))
    return jsonify(
        {
            "ok": bool(result.get("ok")),
            "message": str(result.get("message", "")),
            "count": int(result.get("count", 1) or 1),
            "sanitized": True,
            "settings": rows,
        }
    )


@app.get("/api/config")
def api_config_get() -> Any:
    loaded = cfg_mgr.load()
    host = str(loaded.get("ray5", {}).get("host", "")).strip()
    console.add("info", f"CONFIG API PATH: {cfg_mgr.config_path}")
    console.add("info", f"CONFIG API EXISTS: {cfg_mgr.config_path.exists()}")
    console.add("info", f"CONFIG API HOST: {host}")
    if cfg_mgr.config_path.exists() and host.upper() == "YOUR_RAY5_IP":
        console.add("warn", "Settings are showing placeholder Ray5 host. Do not save until config.json is loaded correctly.")
    return jsonify({"ok": True, "config": loaded})


@app.get("/api/config/debug")
def api_config_debug() -> Any:
    loaded = cfg_mgr.load()
    host = str(loaded.get("ray5", {}).get("host", "")).strip()
    cam = loaded.get("camera", {}) if isinstance(loaded.get("camera"), dict) else {}
    cam_url = str(cam.get("url") or cam.get("stream_url") or "").strip()
    cfg_exists = bool(cfg_mgr.config_path.exists())
    cfg_mtime = None
    if cfg_exists:
        try:
            cfg_mtime = cfg_mgr.config_path.stat().st_mtime
        except Exception:
            cfg_mtime = None
    return jsonify(
        {
            "ok": True,
            "cwd": str(Path.cwd()),
            "config_path": str(cfg_mgr.config_path),
            "config_exists": cfg_exists,
            "config_mtime": cfg_mtime,
            "ray5_host": host,
            "camera_enabled": bool(cam.get("enabled", False)),
            "camera_url_configured": bool(cam_url),
            "using_placeholder_host": host.upper() == "YOUR_RAY5_IP" or host == "",
        }
    )


@app.get("/api/github/check-updates")
def api_github_check_updates() -> Any:
    mode = str(request.args.get("mode", "")).strip().lower()
    force = str(request.args.get("force", "")).strip().lower() in {"1", "true", "yes", "on"}
    if mode == "refresh":
        snap = _start_github_update_check(force=force)
        return jsonify(snap)
    if force:
        snap = _start_github_update_check(force=True)
        return jsonify(snap)
    # Backward-compatible behavior: return cached status and trigger refresh if stale.
    snap = _start_github_update_check(force=False)
    return jsonify(snap)


@app.get("/api/github/update-status")
def api_github_update_status() -> Any:
    try:
        if not UPDATE_STATUS_PATH.exists():
            return jsonify({"ok": True, "status": "none", "message": ""})
        raw = UPDATE_STATUS_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return jsonify({"ok": True, "status": "none", "message": ""})
        return jsonify(data)
    except Exception as exc:
        console.add("warn", f"Failed to read update status: {exc}")
        return jsonify({"ok": True, "status": "none", "message": ""})


@app.post("/api/safety/clear-comm-loss")
def api_safety_clear_comm_loss() -> Any:
    with app_state_lock:
        was_locked = bool(ray5_comm_safety_state.get("comm_lost_during_job", False))
        ray5_comm_safety_state["comm_lost_during_job"] = False
        ray5_comm_safety_state["message"] = ""
        ray5_comm_safety_state["entered_at"] = None
        ray5_comm_safety_state["last_skip_log_at"] = None
    if was_locked:
        console.add("warn", "Communication-loss safety lockout cleared by user acknowledgement.")
    return jsonify({"ok": True, "message": "Communication-loss safety lockout cleared."})


@app.post("/api/github/apply-update")
def api_github_apply_update() -> Any:
    # Use a fresh check before apply-update safety decisions.
    update_info = _check_source_update()
    cached_state = _update_github_check_cache_from_result(update_info, checking=False)
    if not bool(update_info.get("ok")):
        return (
            jsonify(
                {
                    "ok": False,
                    "message": "Unable to check for updates right now.",
                    "update_status": cached_state,
                }
            ),
            503,
        )
    if not bool(update_info.get("update_available")):
        return (
            jsonify(
                {
                    "ok": False,
                    "message": "Ray5 Pilot source is already up to date.",
                    "update_status": cached_state,
                }
            ),
            409,
        )

    state_raw = _get_machine_state_for_update_guard()
    state_norm = _timelapse_normalize_state(state_raw).lower()
    if state_norm in {"run", "hold"}:
        return (
            jsonify(
                {
                    "ok": False,
                    "message": "Update blocked because the Ray5 appears to be running or paused. Stop the job before updating.",
                    "update_status": cached_state,
                }
            ),
            409,
        )

    updater_path = BASE_DIR / "updater.py"
    if not updater_path.exists():
        return jsonify({"ok": False, "message": "Updater script is missing. Cannot apply update.", "update_status": cached_state}), 500
    source_zip_url = str(update_info.get("source_zip_url") or "").strip()
    source_zip_sha256 = str(update_info.get("source_zip_sha256") or "").strip().lower()
    checksum_available = bool(re.fullmatch(r"[0-9a-f]{64}", source_zip_sha256))
    source_zip_lower = source_zip_url.lower()
    install_source_is_main_branch = ("/archive/refs/heads/main.zip" in source_zip_lower) or ("refs/heads/main" in source_zip_lower)
    if install_source_is_main_branch:
        return (
            jsonify(
                {
                    "ok": False,
                    "message": "Update blocked: main-branch source ZIP is not allowed for in-app installs.",
                    "update_status": cached_state,
                }
            ),
            503,
        )
    if not source_zip_url or not checksum_available:
        return (
            jsonify(
                {
                    "ok": False,
                    "message": "Update blocked: release package checksum metadata is unavailable.",
                    "update_status": cached_state,
                }
            ),
            503,
        )

    args = [
        sys.executable,
        str(updater_path),
        "--project-root",
        str(BASE_DIR),
        "--python-exe",
        str(sys.executable),
        "--parent-pid",
        str(os.getpid()),
        "--source-url",
        source_zip_url,
        "--expected-sha256",
        source_zip_sha256,
        "--current-version",
        str(update_info.get("current_version") or _read_local_version()),
        "--remote-version",
        str(update_info.get("latest_version") or ""),
    ]
    try:
        subprocess.Popen(args, cwd=str(BASE_DIR))
    except Exception as exc:
        console.add("error", f"Failed to launch updater: {exc}")
        return jsonify({"ok": False, "message": f"Failed to launch updater: {exc}", "update_status": cached_state}), 500

    _delayed_process_exit(delay_seconds=0.8)
    return jsonify({"ok": True, "message": "Update started. Ray5 Pilot will restart.", "update_status": cached_state})


@app.post("/api/config")
def api_config_post() -> Any:
    body = request.get_json(silent=True) or {}
    ok, msg = cfg_mgr.validate(body)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 400
    timelapse_cfg = body.get("timelapse", {}) if isinstance(body.get("timelapse"), dict) else {}
    disable_timelapse = bool(timelapse_cfg) and (timelapse_cfg.get("enabled") is False)
    pre_save_notice = ""
    if disable_timelapse:
        state = _timelapse_snapshot_state()
        if bool(state.get("active", False)):
            stop_result = _timelapse_stop_internal(reason="config_disable")
            pre_save_notice = str(stop_result.get("message", "")).strip()
            if not stop_result.get("ok"):
                return jsonify({"ok": False, "error": pre_save_notice or "Unable to disable timelapse while capture is active."}), 409
        elif bool(state.get("armed", False)):
            with timelapse_lock:
                timelapse_state["armed"] = False
                timelapse_state["paused"] = False
                timelapse_state["stopping"] = False
                timelapse_state["job_name"] = ""
                timelapse_state["job_source"] = ""
                timelapse_state["control_mode"] = ""
                timelapse_state["status"] = _timelapse_status_label(timelapse_state)
            pre_save_notice = "Timelapse armed state canceled because timelapse was disabled in Settings."

    cfg_mgr.save(body)
    try:
        reload_components()
    except Exception as exc:
        console.add("error", f"Config reload failed after save: {exc}")
        return jsonify({"ok": False, "error": f"Config saved, but runtime reload was blocked: {exc}"}), 409
    console.add("info", "Config saved")
    if pre_save_notice:
        return jsonify({"ok": True, "message": pre_save_notice})
    return jsonify({"ok": True})


if __name__ == "__main__":
    c = cfg_mgr.ensure_config()
    try:
        removed = 0
        with app_state_lock:
            active_cfg = cfg
            active_camera = camera
        if bool(active_cfg.get("camera", {}).get("auto_cleanup_on_start", True)):
            removed = active_camera.cleanup_snapshots(mode="startup", keep_latest=False)
            console.add("info", f"[CAMERA] Cleanup removed {removed} old image(s)")
        if bool(active_cfg.get("camera", {}).get("auto_capture_on_start", False)):
            p = active_camera.capture("startup")
            console.add("info", f"[CAMERA] Startup snapshot saved: {p.name}")
    except Exception as exc:
        console.add("warn", f"Startup camera capture skipped: {exc}")
    start_runtime()
    run_host = str(c.get("web_ui", {}).get("host", "127.0.0.1")).strip()
    run_debug_requested = bool(c.get("web_ui", {}).get("debug", False))
    run_host_norm = run_host.lower()
    run_debug = run_debug_requested
    if run_debug_requested and run_host_norm not in {"127.0.0.1", "localhost", "::1"}:
        run_debug = False
        console.add(
            "warn",
            f"web_ui.debug requested with non-local host '{run_host}'. For safety, debug mode has been forced off.",
        )
    app.run(
        host=run_host,
        port=int(c.get("web_ui", {}).get("port", 5050)),
        debug=run_debug,
        use_reloader=False,
    )
