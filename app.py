from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from threading import RLock
from typing import Any
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
console.add("info", f"CONFIG PATH: {cfg_mgr.config_path}")
console.add("info", f"CONFIG EXISTS: {cfg_mgr.config_path.exists()}")
console.add("info", f"RAY5 HOST: {cfg.get('ray5', {}).get('host', '')}")
console.add("info", f"RAY5 PORT: {cfg.get('ray5', {}).get('port', '')}")
console.add("info", f"RAY5 BASE URL: {ray5._base()}")


_SENSITIVE_DEBUG_TOKENS = ("password", "pass", "key", "token", "secret", "credential", "auth")


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


def reload_components() -> None:
    global cfg, ray5, camera, jobs, status_monitor, _placeholder_api_warned, _placeholder_host_warned
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


def _is_ray5_host_configured(config: dict[str, Any] | None = None) -> bool:
    if config is None:
        with app_state_lock:
            config = cfg
    host = str(config.get("ray5", {}).get("host", "")).strip()
    return bool(host) and host.upper() != "YOUR_RAY5_IP"


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


@app.get("/")
def dashboard() -> str:
    return render_template("index.html")


@app.get("/setup")
def setup_page() -> str:
    return render_template("setup.html")


@app.get("/api/status")
def api_status() -> Any:
    global _last_logged_status_source, _status_error_logged
    with app_state_lock:
        active_cfg = cfg
        active_monitor = status_monitor
    st_cfg = active_cfg.get("status", {}) if isinstance(active_cfg.get("status"), dict) else {}
    prefer_live = bool(st_cfg.get("prefer_live_status", True))
    synthetic_fallback = bool(st_cfg.get("synthetic_fallback_enabled", True))
    monitor_status = active_monitor.get_latest_status() if (active_monitor and prefer_live) else None
    live_fresh = bool(monitor_status and not monitor_status.get("stale", True))
    if not _is_ray5_host_configured():
        state = "NOT_CONFIGURED"
        source = "synthetic"
        online = False
        mpos = {"x": None, "y": None, "z": None}
        wpos = {"x": None, "y": None, "z": None}
        feed = None
        spindle = None
        raw_status = ""
        ws_connected = False
        ws_page_id = None
        last_error = "Ray5 host is not configured. Set ray5.host in Settings."
        alarm_message = None
    elif live_fresh:
        state = monitor_status.get("state", "UNKNOWN")
        mpos = monitor_status.get("machine_position", {}) or {}
        wpos = monitor_status.get("work_position", {}) or {}
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
        source = "cache"
        state = monitor_status.get("state", "UNKNOWN")
        mpos = monitor_status.get("machine_position", {}) or {}
        wpos = monitor_status.get("work_position", {}) or {}
        feed = monitor_status.get("feed")
        spindle = monitor_status.get("spindle")
        raw_status = monitor_status.get("raw_status", "")
        ws_connected = bool(monitor_status.get("websocket_connected", False))
        ws_page_id = monitor_status.get("websocket_page_id")
        last_error = monitor_status.get("last_error")
        alarm_message = monitor_status.get("alarm_message")
        online = bool(ws_connected or raw_status)
        if synthetic_fallback and not online:
            source = "synthetic"
    else:
        source = "synthetic"
        state = "UNKNOWN"
        mpos = {"x": None, "y": None, "z": None}
        wpos = {"x": None, "y": None, "z": None}
        feed = None
        spindle = None
        raw_status = ""
        ws_connected = bool(active_monitor.is_connected()) if active_monitor else False
        ws_page_id = active_monitor.get_page_id() if active_monitor else None
        last_error = None
        alarm_message = None
        online = ws_connected if synthetic_fallback else False

    if source != _last_logged_status_source:
        console.add("info", f"Status source changed: {source}")
        _last_logged_status_source = source
    if not online:
        err = str(last_error or "Ray5 live status unavailable")
        if not _status_error_logged:
            console.add("error", f"Status error: {err}")
            _status_error_logged = True
    else:
        _status_error_logged = False
    cam = _camera_cfg(active_cfg)
    cam_url = cam["url"]
    cam_scheme = (urlsplit(cam_url).scheme or "").lower() if cam_url else ""
    cam_masked = mask_camera_url(cam_url) if cam["mask_credentials"] else cam_url
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
            "feed": feed,
            "spindle": spindle,
            "raw": raw_status,
            "raw_status": raw_status,
            "status_source": source,
            "position_source": "live_websocket" if source == "live_websocket" else ("cache" if source == "cache" else ("synthetic" if source == "synthetic" else "unknown")),
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
    return jsonify(
        {
            "ok": ok,
            "message": "Command sent" if ok else (result.get("message") or "Command failed"),
            "command": command,
            "result": result,
        }
    )


@app.get("/api/camera/video-enabled")
def api_camera_video_enabled_get() -> Any:
    cam = _camera_cfg()
    return jsonify({"ok": True, "enabled": bool(cam["video_enabled"])})


@app.post("/api/camera/video-enabled")
def api_camera_video_enabled_post() -> Any:
    body = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled", True))
    current = cfg_mgr.load()
    cam = current.get("camera", {}) if isinstance(current.get("camera"), dict) else {}
    cam["video_enabled"] = enabled
    current["camera"] = cam
    cfg_mgr.save(current)
    reload_components()
    msg = "Camera video enabled." if enabled else "Camera video disabled."
    console.add("info", msg)
    return jsonify({"ok": True, "enabled": enabled, "message": msg})


@app.get("/camera/stream")
def camera_stream() -> Any:
    cam = _camera_cfg()
    if not cam["enabled"] or not cam["proxy_enabled"]:
        return "Camera proxy is disabled", 404
    if not cam["url"]:
        return "Camera URL not configured", 404
    return app.response_class(
        mjpeg_generator(cam["url"], cam["reconnect_seconds"]),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/camera/snapshot")
def camera_snapshot() -> Any:
    ok, data, ctype = camera.snapshot()
    if not ok:
        return jsonify({"ok": False, "error": data.decode(errors="ignore")})
    return send_file(io.BytesIO(data), mimetype=ctype)


@app.post("/api/camera/test")
def api_camera_test() -> Any:
    cam = _camera_cfg()
    if not cam["enabled"]:
        return jsonify({"ok": False, "message": "Camera test failed: camera disabled."})
    if not cam["url"]:
        return jsonify({"ok": False, "message": "Camera test failed: camera URL not configured."})
    cap = cv2.VideoCapture(cam["url"])
    try:
        if not cap.isOpened():
            return jsonify({"ok": False, "message": "Camera test failed: camera open failed."})
        ok, frame = cap.read()
        if not ok or frame is None:
            return jsonify({"ok": False, "message": "Camera test failed: camera read failed."})
        return jsonify({"ok": True, "message": "Camera test passed."})
    finally:
        cap.release()


@app.post("/api/camera/open-external")
def api_camera_open_external() -> Any:
    cam = _camera_cfg()
    if not cam["url"]:
        return jsonify({"ok": False, "error": "camera URL not configured"})
    try:
        webbrowser.open(cam["url"])
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.post("/api/camera/capture")
def api_camera_capture() -> Any:
    try:
        p = camera.capture("manual")
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
        console.add("warn", f"Camera capture failed: {exc}")
        return jsonify({"ok": False, "error": str(exc)})


@app.get("/camera/calibration")
def camera_calibration_page() -> Any:
    return render_template("camera_calibration.html")


@app.get("/camera-calibration")
def camera_calibration_page_legacy() -> Any:
    return render_template("camera_calibration.html")


@app.get("/api/camera/config-status")
def api_camera_config_status() -> Any:
    return jsonify({"ok": True, **camera.config_status()})


@app.post("/api/camera/calibration/run")
def api_camera_calibration_run() -> Any:
    latest_raw = camera.output_dir / "latest_raw.jpg"
    if not latest_raw.exists():
        return jsonify({"ok": False, "error": "Take a snapshot first, then run calibration."}), 400
    script = BASE_DIR / "calibrate_camera.py"
    try:
        subprocess.Popen([sys.executable, str(script)], cwd=str(BASE_DIR))
        console.add("info", "Camera calibration launched")
        return jsonify({"ok": True, "message": "Calibration window launched"})
    except Exception as exc:
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
    return jsonify({"ok": ok, "response": resp, "upload_ok": upload_ok, "upload": upload_detail, "run_filename": machine_filename})


@app.delete("/api/jobs/<path:filename>")
def api_jobs_delete(filename: str) -> Any:
    try:
        jobs.delete_job(filename)
        console.add("info", f"Deleted job: {filename}")
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


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
    if axis == "z" and not bool(controls.get("enable_z_jog", controls.get("enable_jog_z", False))):
        return jsonify({"ok": False, "message": "Z jog is disabled in config", "raw": ""}), 400
    if bool(controls.get("force_laser_off_before_move", True)):
        ray5.laser_off()
    console.add("info", f"Manual move {axis.upper()} {distance}mm F{feedrate}")
    result = ray5.move(axis=axis, distance=distance, feedrate=feedrate)
    console.add("info", f"Move result: {'ok' if result.get('ok') else 'fail'} {str(result.get('message',''))[:120]}")
    return jsonify(result)


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
    console.add("warn", "Test fire requested")
    safety = cfg.get("safety", {})
    enabled = bool(safety.get("test_fire_enabled", safety.get("enable_test_fire", False)))
    if not enabled:
        console.add("warn", "Test fire blocked by safety config")
        return jsonify({"ok": False, "error": "test fire disabled"}), 403
    body = request.get_json(silent=True) or {}
    req_power = int(body.get("power", safety.get("test_fire_power", 1)))
    req_duration_ms = int(body.get("duration_ms", safety.get("test_fire_duration_ms", 100)))
    max_power = int(safety.get("test_fire_max_power", 5))
    max_duration_ms = int(safety.get("test_fire_max_duration_ms", 500))
    power = max(0, min(max_power, req_power))
    duration_ms = max(10, min(max_duration_ms, req_duration_ms))
    console.add("warn", f"Test fire pulse sent power={power} duration_ms={duration_ms}")
    result = ray5.test_fire(power=power, duration_ms=duration_ms)
    if not result.get("ok"):
        console.add("error", f"Test fire failed: {str(result.get('message','unknown'))[:120]}")
    console.add("warn", f"Test fire completed; laser forced off (power={power}, duration_ms={duration_ms})")
    return jsonify(result | {"power": power, "duration_ms": duration_ms})


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
    return jsonify(result)


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


@app.post("/api/config")
def api_config_post() -> Any:
    body = request.get_json(silent=True) or {}
    ok, msg = cfg_mgr.validate(body)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 400
    cfg_mgr.save(body)
    reload_components()
    console.add("info", "Config saved")
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
    app.run(
        host=str(c.get("web_ui", {}).get("host", "127.0.0.1")),
        port=int(c.get("web_ui", {}).get("port", 5050)),
        debug=bool(c.get("web_ui", {}).get("debug", False)),
        use_reloader=False,
    )
