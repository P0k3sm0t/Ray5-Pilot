from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "ray5": {
        "host": "YOUR_RAY5_IP",
        "port": 8848,
        "timeout": 4,
        "request_timeout_seconds": 4,
        "command_endpoint": "/command",
        "command_field": "commandText",
        "files_endpoint": "/files",
        "upload_endpoint": "/upload",
        "run_command_template": "$sd/runzip=/{filename}",
        "upload_path": "/",
        "sd_path": "/",
    },
    "web_ui": {"host": "127.0.0.1", "port": 5050, "debug": False},
    "camera": {
        "enabled": False,
        "video_enabled": True,
        "url": "rtsp://USERNAME:PASSWORD@CAMERA_IP:554/stream2",
        "stream_url": "",
        "snapshot_url": "",
        "proxy_enabled": True,
        "proxy_path": "/camera/stream",
        "mask_credentials": True,
        "reconnect_seconds": 5,
        "capture_method": "ffmpeg",
        "output_dir": "camera_captures",
        "filename_prefix": "ray5_bed",
        "save_history": False,
        "keep_last": 0,
        "auto_cleanup_on_start": True,
        "cleanup_on_capture": True,
        "latest_raw_name": "latest_raw.jpg",
        "latest_processed_name": "latest.jpg",
        "auto_capture_on_start": False,
        "timeout_seconds": 15,
        "deskew": {"enabled": False, "source_points": [], "output_size": [1200, 1200]},
        "postprocess": {
            "enabled": False,
            "scale": 1.0,
            "center_crop_margin": 0,
            "rotate_degrees": 90,
            "final_size": [1200, 1200],
            "dpi": 101.6,
            "overlay_guides": {
                "enabled": False,
                "draw_center_cross": True,
                "draw_border": True,
                "draw_corner_marks": True,
            },
        },
        "overlay_alignment": {
            "enabled": True,
            "physical_width_mm": 300,
            "physical_height_mm": 300,
            "source_offset_x_px": 0,
            "source_offset_y_px": 0,
            "offset_x_mm": 0,
            "offset_y_mm": 0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "fine_rotation_degrees": 0.0,
        },
    },
    "jobs": {
        "imported_jobs_dir": "imported_jobs",
        "watched_gcode_dir": "watched_gcode",
        "watch_enabled": True,
        "watch_poll_seconds": 3,
        "delete_watched_after_import": True,
        "allowed_extensions": [".gcode", ".nc", ".gc"],
    },
    "framing": {
        "margin_mm": 2.0,
        "feedrate": 3000,
        "force_laser_off": True,
        "validate_bounds": True,
        "clamp_to_machine_area": True,
        "frame_feedrate": 3000,
        "frame_margin_mm": 2.0,
        "laser_off_during_frame": True,
    },
    "machine": {
        "bed_width_mm": 390,
        "bed_height_mm": 360,
        "min_x": 0,
        "min_y": 0,
        "max_x": 390,
        "max_y": 360,
    },
    "manual_controls": {
        "default_jog_step": 10,
        "default_jog_step_mm": 10,
        "default_feedrate": 500,
        "jog_steps": [0.1, 1, 5, 10, 50],
        "feedrates": [500, 1000, 3000, 6000],
        "force_laser_off_before_move": True,
        "enable_z_jog": False,
        "preset_enabled": True,
        "preset_label": "Go To Preset",
        "preset_x": 0,
        "preset_y": 0,
        "preset_feedrate": 1500,
    },
    "safety": {
        "test_fire_enabled": False,
        "enable_test_fire": False,
        "test_fire_power": 1,
        "test_fire_duration_ms": 100,
        "test_fire_duration_seconds": 0.1,
        "test_fire_max_power": 5,
        "test_fire_max_duration_ms": 500,
        "confirm_dangerous_actions": True,
        "reject_3d_printer_gcode": True,
        "gcode_safety_scan_lines": 5000,
        "allow_unknown_gcode": True,
    },
    "sd_files": {
        "auto_refresh_seconds": 0,
        "show_storage_summary": True,
        "enable_delete": True,
        "enable_start": True,
        "enable_preview": False,
    },
    "upload": {
        "preserve_original": True,
        "sanitize_filename": False,
        "screen_compatible_rewrite": False,
        "convert_m4_to_m3": False,
        "force_extension": "",
        "normalize_line_endings": False,
        "start_after_upload": False,
    },
    "job_control": {
        "stop_mode": "soft_reset",
        "allow_soft_reset_stop": True,
        "stop_sends_laser_off_first": True,
        "stop_unlock_after_reset": False,
        "stop_refresh_status_after": True,
    },
    "limits": {
        "max_gcode_upload_mb": 50,
        "max_bounds_parse_mb": 50,
    },
    "status": {
        "prefer_live_status": True,
        "websocket_enabled": True,
        "debug_logging": False,
        "websocket_port": 8849,
        "websocket_path": "/",
        "websocket_subprotocol": "arduino",
        "poll_seconds": 1.0,
        "reconnect_seconds": 3.0,
        "stale_after_seconds": 5.0,
        "synthetic_fallback_enabled": True,
        "show_status_source": True,
        "show_position_source": True,
    },
    "console": {
        "raw_command_enabled": True,
        "confirm_dangerous_raw_commands": True,
    },
    "air_assist": {"supported": True, "on_command": "M8", "off_command": "M9"},
}


class ConfigManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.config_path = base_dir / "config.json"
        self.example_path = base_dir / "config.example.json"

    def ensure_config(self) -> dict[str, Any]:
        if self.config_path.exists():
            return self.load()
        if self.example_path.exists():
            self.config_path.write_text(self.example_path.read_text(encoding="utf-8-sig"), encoding="utf-8")
            return self.load()
        self.save(DEFAULT_CONFIG)
        return self.load()

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        except Exception:
            data = {}
        return self._merged(DEFAULT_CONFIG, data)

    def save(self, data: dict[str, Any]) -> None:
        try:
            current_raw = json.loads(self.config_path.read_text(encoding="utf-8-sig")) if self.config_path.exists() else {}
        except Exception:
            current_raw = {}
        merged_current = self._merged(DEFAULT_CONFIG, current_raw if isinstance(current_raw, dict) else {})
        merged_final = self._merged(merged_current, data)
        self.config_path.write_text(json.dumps(merged_final, indent=2), encoding="utf-8")

    def validate(self, data: dict[str, Any]) -> tuple[bool, str]:
        try:
            ray_host = str(data.get("ray5", {}).get("host", "")).strip()
            if not ray_host:
                return False, "ray5.host cannot be empty"
            ray_port = int(data.get("ray5", {}).get("port", 8848))
            if not (1 <= ray_port <= 65535):
                return False, "ray5.port must be 1-65535"
            port = int(data.get("web_ui", {}).get("port", 5050))
            if not (1 <= port <= 65535):
                return False, "web_ui.port must be 1-65535"
            web_host = str(data.get("web_ui", {}).get("host", "")).strip()
            if not web_host:
                return False, "web_ui.host cannot be empty"
            timeout = float(data.get("ray5", {}).get("request_timeout_seconds", 4))
            if timeout <= 0:
                return False, "ray5.request_timeout_seconds must be > 0"
            jobs = data.get("jobs", {})
            imported_dir = str(jobs.get("imported_jobs_dir") or jobs.get("imported_jobs_folder") or "").strip()
            watched_dir = str(jobs.get("watched_gcode_dir") or jobs.get("watched_folder") or "").strip()
            if not imported_dir:
                return False, "jobs.imported_jobs_dir cannot be empty"
            if not watched_dir:
                return False, "jobs.watched_gcode_dir cannot be empty"
            poll_seconds = float(jobs.get("watch_poll_seconds", 3))
            if poll_seconds < 1:
                return False, "jobs.watch_poll_seconds must be >= 1"
            camera = data.get("camera", {})
            if not bool(camera.get("enabled", False)):
                pass
            else:
                # Allow either stream or snapshot when enabled.
                stream = str(camera.get("url", "") or camera.get("stream_url", "")).strip()
                snap = str(camera.get("snapshot_url", "")).strip()
                if not stream and not snap:
                    return False, "camera requires stream_url or snapshot_url when enabled"
            return True, "ok"
        except Exception as exc:
            return False, str(exc)

    def _merged(self, default: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = dict(default)
        for k, v in current.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = self._merged(out[k], v)
            else:
                out[k] = v
        return out
