from __future__ import annotations

import json
import re
import time
import hashlib
from pathlib import Path
from typing import Any

import requests


class Ray5Client:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.session = requests.Session()
        self.session.trust_env = False
        self.last_debug: dict[str, Any] = {
            "endpoint": None,
            "method": None,
            "url": None,
            "params": None,
            "status_code": None,
            "success": False,
            "preview": "",
            "error": "",
        }
        self._page_id_getter = None

    def set_page_id_getter(self, getter: Any) -> None:
        self._page_id_getter = getter

    def _base(self) -> str:
        ray = self.cfg.get("ray5", {})
        return f"http://{ray.get('host','YOUR_RAY5_IP')}:{int(ray.get('port',8848))}"

    def _timeout(self) -> float:
        ray = self.cfg.get("ray5", {})
        raw = ray.get("request_timeout_seconds", ray.get("timeout", 4))
        return float(raw)

    def _request_command(self, commands: str | list[str]) -> dict[str, Any]:
        if isinstance(commands, str):
            return self._request_single_command(commands)
        cleaned = [str(c).strip() for c in commands if str(c).strip()]
        if not cleaned:
            return {"ok": False, "message": "no commands provided", "raw": "", "endpoint": "/command", "param": "commandText", "count": 0}
        previews: list[str] = []
        page_id_used: str | None = None
        page_id_fallback = False
        for cmd in cleaned:
            result = self._request_single_command(cmd)
            previews.append(f"{cmd}: {str(result.get('raw',''))[:80]}")
            if page_id_used is None:
                page_id_used = str(result.get("page_id_used") or "")
            page_id_fallback = page_id_fallback or bool(result.get("page_id_fallback"))
            if not result.get("ok"):
                return {
                    "ok": False,
                    "message": f"command failed: {cmd}",
                    "raw": "\n".join(previews),
                    "endpoint": result.get("endpoint", "/command"),
                    "param": "commandText",
                    "count": len(cleaned),
                    "page_id_used": page_id_used,
                    "page_id_fallback": page_id_fallback,
                }
        return {
            "ok": True,
            "message": "ok",
            "raw": "\n".join(previews),
            "endpoint": "/command",
            "param": "commandText",
            "count": len(cleaned),
            "page_id_used": page_id_used,
            "page_id_fallback": page_id_fallback,
        }

    def _request_single_command(self, command: str, tolerate_error_text: bool = False) -> dict[str, Any]:
        ray = self.cfg.get("ray5", {})
        endpoint = str(ray.get("command_endpoint", "/command"))
        url = self._base() + endpoint
        params = {"commandText": command}
        page_id_used: str | None = None
        page_id_fallback = False
        try:
            if callable(self._page_id_getter):
                pid = self._page_id_getter()
                if pid not in (None, ""):
                    page_id_used = str(pid)
        except Exception:
            pass
        if page_id_used is None:
            page_id_used = "0"
            page_id_fallback = True
        params["PAGEID"] = page_id_used
        try:
            resp = self.session.get(url, params=params, timeout=self._timeout())
            text = (resp.text or "").strip()
            lower = text.lower()
            is_error_text = (lower in {"error", "invalid command"} or "invalid command" in lower) and not tolerate_error_text
            ok = bool(resp.status_code == 200 and not is_error_text)
            self.last_debug = {
                "endpoint": endpoint,
                "method": "GET",
                "url": url,
                "params": {"commandText": "<payload>", "PAGEID": params.get("PAGEID")},
                "status_code": resp.status_code,
                "success": ok,
                "preview": (resp.text or "")[:220].replace("\n", "\\n").replace("\r", ""),
                "error": "" if ok else ((resp.text or "").strip() or f"http {resp.status_code}"),
            }
            return {
                "ok": ok,
                "message": "ok" if ok else (text or f"http {resp.status_code}"),
                "raw": resp.text or "",
                "endpoint": endpoint,
                "param": "commandText",
                "count": 1,
                "page_id_used": page_id_used,
                "page_id_fallback": page_id_fallback,
            }
        except requests.RequestException as exc:
            self.last_debug = {
                "endpoint": endpoint,
                "method": "GET",
                "url": url,
                "params": {"commandText": "<payload>", "PAGEID": params.get("PAGEID")},
                "status_code": None,
                "success": False,
                "preview": "",
                "error": str(exc),
            }
            return {
                "ok": False,
                "message": str(exc),
                "raw": "",
                "endpoint": endpoint,
                "param": "commandText",
                "count": 1,
                "page_id_used": page_id_used,
                "page_id_fallback": page_id_fallback,
            }

    def _request_plain_command(self, command: str) -> dict[str, Any]:
        ray = self.cfg.get("ray5", {})
        endpoint = str(ray.get("command_endpoint", "/command"))
        url = self._base() + endpoint
        params = {"plain": command}
        try:
            resp = self.session.get(url, params=params, timeout=self._timeout())
            text = (resp.text or "").strip()
            lower = text.lower()
            is_error_text = lower in {"error", "invalid command"} or "invalid command" in lower
            ok = bool(resp.status_code == 200 and not is_error_text)
            self.last_debug = {
                "endpoint": endpoint,
                "method": "GET",
                "url": url,
                "params": {"plain": "<payload>"},
                "status_code": resp.status_code,
                "success": ok,
                "preview": (resp.text or "")[:220].replace("\n", "\\n").replace("\r", ""),
                "error": "" if ok else ((resp.text or "").strip() or f"http {resp.status_code}"),
            }
            return {
                "ok": ok,
                "message": "ok" if ok else (text or f"http {resp.status_code}"),
                "raw": resp.text or "",
                "endpoint": endpoint,
                "param": "plain",
                "count": 1,
            }
        except requests.RequestException as exc:
            self.last_debug = {
                "endpoint": endpoint,
                "method": "GET",
                "url": url,
                "params": {"plain": "<payload>"},
                "status_code": None,
                "success": False,
                "preview": "",
                "error": str(exc),
            }
            return {"ok": False, "message": str(exc), "raw": "", "endpoint": endpoint, "param": "plain", "count": 1}

    def trigger_live_status(self, page_id: str | None = None) -> dict[str, Any]:
        ray = self.cfg.get("ray5", {})
        endpoint = str(ray.get("command_endpoint", "/command"))
        url = self._base() + endpoint
        params = {"commandText": "?"}
        if page_id not in (None, ""):
            params["PAGEID"] = str(page_id)
        try:
            resp = self.session.get(url, params=params, timeout=self._timeout())
            text = (resp.text or "").strip()
            ok = bool(resp.status_code == 200)
            self.last_debug = {
                "endpoint": endpoint,
                "method": "GET",
                "url": url,
                "params": {"commandText": "?", "PAGEID": params.get("PAGEID")},
                "status_code": resp.status_code,
                "success": ok,
                "preview": (resp.text or "")[:220].replace("\n", "\\n").replace("\r", ""),
                "error": "" if ok else (text or f"http {resp.status_code}"),
            }
            return {"ok": ok, "message": "ok" if ok else (text or f"http {resp.status_code}"), "raw": resp.text or ""}
        except requests.RequestException as exc:
            self.last_debug = {
                "endpoint": endpoint,
                "method": "GET",
                "url": url,
                "params": {"commandText": "?", "PAGEID": params.get("PAGEID")},
                "status_code": None,
                "success": False,
                "preview": "",
                "error": str(exc),
            }
            return {"ok": False, "message": str(exc), "raw": ""}

    def query_status_command(self) -> dict[str, Any]:
        # Console "?" status query should use PAGEID=0 on Ray5/ESP3D command endpoint.
        r = self.trigger_live_status("0")
        return {
            "ok": bool(r.get("ok")),
            "message": str(r.get("message", "ok" if r.get("ok") else "error")),
            "raw": str(r.get("raw", "")),
            "endpoint": "/command",
            "param": "commandText",
            "count": 1,
        }

    def send_command(self, command: str) -> tuple[bool, str]:
        r = self._request_command(command)
        return bool(r.get("ok")), str(r.get("raw", ""))

    def send_gcode(self, commands: str | list[str]) -> dict[str, Any]:
        return self._request_command(commands)

    def home(self, axis: str = "all") -> dict[str, Any]:
        axis_norm = str(axis or "all").strip().lower()
        if axis_norm in {"all", "*", "xyz"}:
            return self._request_command("$H")
        # Many Ray5 controllers only support full home in this API.
        return {"ok": False, "message": f"Partial home '{axis_norm}' not supported by current Ray5 API mode", "raw": ""}

    def unlock(self) -> dict[str, Any]:
        return self.clear_alarm()

    def clear_alarm(self) -> dict[str, Any]:
        m5 = self.send_gcode("M5")
        x = self.send_gcode("$X")
        return {
            "ok": bool(m5.get("ok")) and bool(x.get("ok")),
            "message": "ok" if (m5.get("ok") and x.get("ok")) else "unlock failed",
            "raw": {"M5": m5.get("raw", ""), "$X": x.get("raw", "")},
            "steps": {"M5": m5, "$X": x},
        }

    def move(self, axis: str, distance: float, feedrate: float) -> dict[str, Any]:
        a = str(axis or "").strip().upper()
        if a not in {"X", "Y", "Z"}:
            return {"ok": False, "message": "axis must be x/y/z", "raw": ""}
        cmd = f"$J=G91 {a}{float(distance):.3f} F{float(feedrate):.0f}"
        return self.send_gcode(cmd)

    def laser_off(self) -> dict[str, Any]:
        return self.send_gcode("M5")

    def air_on(self) -> dict[str, Any]:
        if not bool(self.cfg.get("air_assist", {}).get("supported", True)):
            return {"ok": False, "message": "air assist not supported", "raw": ""}
        cmd = str(self.cfg.get("air_assist", {}).get("on_command", "M8"))
        return self.send_gcode(cmd)

    def air_off(self) -> dict[str, Any]:
        if not bool(self.cfg.get("air_assist", {}).get("supported", True)):
            return {"ok": False, "message": "air assist not supported", "raw": ""}
        cmd = str(self.cfg.get("air_assist", {}).get("off_command", "M9"))
        return self.send_gcode(cmd)

    def test_fire(
        self,
        s_value: int,
        duration_ms: int,
        command: str = "M3",
        mode: str = "stationary_m3",
        motion_axis: str = "X",
        motion_mm: float = 1.0,
        motion_feedrate: float = 300.0,
    ) -> dict[str, Any]:
        duration_s = max(0.01, float(duration_ms) / 1000.0)
        cmd = str(command or "M3").strip().upper()
        fire_mode = str(mode or "stationary_m3").strip().lower()
        if cmd not in {"M3", "M4"}:
            return {
                "ok": False,
                "message": f"invalid test fire command: {cmd}",
                "raw": {"on": "", "off": ""},
                "steps": {"M3": {"ok": False, "message": "not sent", "raw": ""}, "M5": {"ok": False, "message": "not sent", "raw": ""}},
            }
        if fire_mode not in {"stationary_m3", "stationary_m4", "motion_pulse"}:
            fire_mode = "stationary_m3"

        if fire_mode == "stationary_m3":
            cmd = "M3"
        elif fire_mode == "stationary_m4":
            cmd = "M4"

        on_result: dict[str, Any] = {"ok": False, "message": "not sent", "raw": ""}
        off_result: dict[str, Any] = {"ok": False, "message": "not sent", "raw": ""}
        steps: dict[str, Any] = {}
        commands: list[str] = []
        try:
            if fire_mode == "motion_pulse":
                axis = str(motion_axis or "X").strip().upper()
                if axis not in {"X", "Y"}:
                    return {
                        "ok": False,
                        "message": f"invalid test fire motion axis: {axis}",
                        "raw": {"on": "", "off": ""},
                        "steps": {"M5": {"ok": False, "message": "not sent", "raw": ""}},
                    }
                move_mm = float(motion_mm)
                feed = max(1.0, float(motion_feedrate))
                commands = [
                    "G91",
                    f"{cmd} S{int(s_value)}",
                    f"G1 {axis}{move_mm:.3f} F{feed:.0f}",
                    "M5",
                    "G90",
                ]
                steps["G91"] = self.send_gcode("G91")
                if not steps["G91"].get("ok"):
                    return {"ok": False, "message": f"test fire failed: {steps['G91'].get('message','G91 failed')}", "raw": {"on": "", "off": ""}, "steps": steps, "commands": commands}
                on_result = self.send_gcode(f"{cmd} S{int(s_value)}")
                steps[cmd] = on_result
                if not on_result.get("ok"):
                    return {
                        "ok": False,
                        "message": f"test fire failed to start: {on_result.get('message', 'unknown')}",
                        "raw": {"on": on_result.get("raw", ""), "off": off_result.get("raw", "")},
                        "steps": steps,
                        "commands": commands,
                    }
                move_cmd = f"G1 {axis}{move_mm:.3f} F{feed:.0f}"
                steps["MOVE"] = self.send_gcode(move_cmd)
                if not steps["MOVE"].get("ok"):
                    return {
                        "ok": False,
                        "message": f"test fire motion failed: {steps['MOVE'].get('message', 'unknown')}",
                        "raw": {"on": on_result.get("raw", ""), "off": off_result.get("raw", "")},
                        "steps": steps,
                        "commands": commands,
                    }
            else:
                commands = [f"{cmd} S{int(s_value)}", "M5"]
                on_result = self.send_gcode(f"{cmd} S{int(s_value)}")
                steps[cmd] = on_result
                if not on_result.get("ok"):
                    return {
                        "ok": False,
                        "message": f"test fire failed to start: {on_result.get('message', 'unknown')}",
                        "raw": {"on": on_result.get("raw", ""), "off": off_result.get("raw", "")},
                        "steps": steps,
                        "commands": commands,
                    }
                time.sleep(duration_s)
        finally:
            off_result = self.send_gcode("M5")
            steps["M5"] = off_result
            if fire_mode == "motion_pulse":
                g90_result = self.send_gcode("G90")
                steps["G90"] = g90_result

        ok = all(bool(step.get("ok")) for step in steps.values()) if steps else False
        page_id_used = None
        page_id_fallback = False
        for step in steps.values():
            if page_id_used is None and step.get("page_id_used") is not None:
                page_id_used = str(step.get("page_id_used"))
            page_id_fallback = page_id_fallback or bool(step.get("page_id_fallback"))
        return {
            "ok": ok,
            "mode": fire_mode,
            "message": "test fire complete" if ok else "test fire completed but one or more steps failed",
            "raw": {"on": on_result.get("raw", ""), "off": off_result.get("raw", "")},
            "steps": steps,
            "commands": commands,
            "page_id_used": page_id_used,
            "page_id_fallback": page_id_fallback,
        }

    def stop_job(self) -> dict[str, Any]:
        ctrl = self.cfg.get("job_control", {}) if isinstance(self.cfg.get("job_control"), dict) else {}
        stop_mode = str(ctrl.get("stop_mode", "hold_only")).strip().lower()
        allow_soft_reset = bool(ctrl.get("allow_soft_reset_stop", False))
        send_laser_off = bool(ctrl.get("stop_sends_laser_off_first", True))
        unlock_after = bool(ctrl.get("stop_unlock_after_reset", False))
        if stop_mode == "disabled":
            return {"ok": False, "message": "Stop is disabled in settings.", "raw": "", "mode": "disabled"}
        if stop_mode == "hold_only":
            result = self.send_gcode("!")
            result["message"] = "Feed hold sent. Job paused, not aborted."
            result["mode"] = "hold_only"
            return result
        if stop_mode == "soft_reset":
            if not allow_soft_reset:
                return {"ok": False, "message": "Soft reset stop is not allowed by settings.", "raw": "", "mode": "soft_reset"}
            steps: dict[str, Any] = {}
            if send_laser_off:
                steps["M5"] = self.send_gcode("M5")
            steps["CTRL_X"] = self.send_gcode("\x18")
            time.sleep(0.3)
            if unlock_after:
                steps["$X"] = self.send_gcode("$X")
            ok = all(bool(v.get("ok")) for v in steps.values()) if steps else False
            return {
                "ok": ok,
                "mode": "soft_reset",
                "message": "Stop/abort sent." if ok else "Stop/abort failed.",
                "steps": steps,
                "raw": {k: v.get("raw", "") for k, v in steps.items()},
            }
        return {"ok": False, "message": f"Unknown stop_mode: {stop_mode}", "raw": "", "mode": stop_mode}

    def pause_job(self) -> dict[str, Any]:
        r = self.send_gcode("!")
        r["message"] = "Pause/feed hold sent."
        return r

    def resume_job(self) -> dict[str, Any]:
        r = self.send_gcode("~")
        r["message"] = "Resume sent."
        return r

    def status(self) -> dict[str, Any]:
        # Ray5 HTTP commandText mode returns "Error" for "?" on some firmware; avoid polling status with it.
        return {"ok": False, "raw": "", "text": "", "parsed": {}, "source": "synthetic"}

    def list_files(self, path: str = "/") -> dict[str, Any]:
        ray = self.cfg.get("ray5", {})
        endpoint = str(ray.get("files_endpoint", "/files"))
        base_path = str(path or ray.get("sd_path", "/") or "/").strip() or "/"
        params = {"path": base_path}
        url = self._base() + endpoint
        try:
            resp = self.session.get(url, params=params, timeout=self._timeout())
            raw_text = resp.text if isinstance(resp.text, str) else ""
            preview = raw_text[:220].replace("\n", "\\n").replace("\r", "")
            self.last_debug = {
                "endpoint": endpoint,
                "method": "GET",
                "url": url,
                "params": params,
                "status_code": resp.status_code,
                "success": bool(resp.ok),
                "preview": preview,
                "error": "",
            }
            if "invalid command" in raw_text.lower():
                self.last_debug["error"] = "Ray5 endpoint returned Invalid command; likely missing/incorrect path parameter."
                return {
                    "ok": False,
                    "error": self.last_debug["error"],
                    "path": base_path,
                    "files": [],
                    "storage": {},
                    "raw": raw_text,
                    "status_code": resp.status_code,
                    "endpoint": endpoint,
                    "params": params,
                    "preview": preview,
                }
            if not resp.ok:
                return {
                    "ok": False,
                    "error": f"http {resp.status_code}",
                    "path": base_path,
                    "files": [],
                    "storage": {},
                    "raw": raw_text,
                    "status_code": resp.status_code,
                    "endpoint": endpoint,
                    "params": params,
                    "preview": preview,
                }
            return self.normalize_file_list_response(raw_text, base_path=base_path)
        except requests.RequestException as exc:
            self.last_debug = {
                "endpoint": endpoint,
                "method": "GET",
                "url": url,
                "params": params,
                "status_code": None,
                "success": False,
                "preview": "",
                "error": str(exc),
            }
            return {
                "ok": False,
                "error": str(exc),
                "path": base_path,
                "files": [],
                "storage": {},
                "raw": "",
                "endpoint": endpoint,
                "params": params,
                "status_code": None,
                "preview": "",
            }

    def connectivity(self) -> dict[str, Any]:
        files = self.list_files()
        if files.get("ok"):
            return {
                "connected": True,
                "endpoint": files.get("endpoint"),
                "status_code": files.get("status_code"),
                "error": "",
                "preview": str(files.get("preview", "")),
                "params": files.get("params"),
            }

        root = self.probe_http()
        return {
            "connected": bool(root.get("ok")),
            "endpoint": "/",
            "status_code": root.get("status_code"),
            "error": root.get("error", "") or files.get("error", ""),
            "preview": root.get("preview", ""),
            "params": None,
        }

    def probe_http(self) -> dict[str, Any]:
        url = self._base() + "/"
        try:
            resp = self.session.get(url, timeout=self._timeout())
            text = resp.text if isinstance(resp.text, str) else ""
            return {
                "ok": bool(resp.ok),
                "status_code": resp.status_code,
                "preview": text[:160].replace("\n", "\\n").replace("\r", ""),
                "error": "",
            }
        except requests.RequestException as exc:
            return {"ok": False, "status_code": None, "preview": "", "error": str(exc)}

    def delete_sd_file(self, filename_or_path: str) -> dict[str, Any]:
        target = str(filename_or_path or "").strip().lstrip("/")
        if not target:
            return {"ok": False, "message": "filename is required", "raw": ""}
        return self._request_command(f"$sd/delete=/{target}")

    def get_device_info(self) -> dict[str, Any]:
        return self._request_plain_command("[ESP420]")

    def keepalive_ping(self) -> dict[str, Any]:
        return self._request_plain_command("[ESP400]")

    def start_sd_file(self, filename_or_path: str) -> dict[str, Any]:
        target = str(filename_or_path or "").strip().lstrip("/")
        if not target:
            return {"ok": False, "message": "filename is required", "raw": ""}
        tpl = str(self.cfg.get("ray5", {}).get("run_command_template", "$sd/runzip=/{filename}"))
        cmd = tpl.format(filename=target)
        return self._request_command(cmd)

    # Backward-compatible wrappers.
    def delete_file(self, filename: str) -> tuple[bool, str]:
        r = self.delete_sd_file(filename)
        return bool(r.get("ok")), str(r.get("raw", ""))

    def start_file(self, filename: str) -> tuple[bool, str]:
        r = self.start_sd_file(filename)
        return bool(r.get("ok")), str(r.get("raw", ""))

    def upload_file(self, path: Path) -> tuple[bool, str]:
        detail = self.upload_file_detailed(path)
        return bool(detail.get("ok")), str(detail.get("upload_response", detail.get("error", "")))

    def upload_file_detailed(self, path: Path) -> dict[str, Any]:
        ray = self.cfg.get("ray5", {})
        up_cfg = self.cfg.get("upload", {})
        endpoint = str(ray.get("upload_endpoint", "/upload"))
        url = self._base() + endpoint
        upload_path = str(ray.get("upload_path", "/") or "/")
        preserve_original = bool(up_cfg.get("preserve_original", True))
        rewrite_enabled = bool(up_cfg.get("screen_compatible_rewrite", False))
        convert_m4_to_m3 = bool(up_cfg.get("convert_m4_to_m3", False))
        normalize_line_endings = bool(up_cfg.get("normalize_line_endings", False))
        force_extension = str(up_cfg.get("force_extension", "") or "").strip().lower().lstrip(".")
        source_bytes = path.read_bytes()
        source_size = len(source_bytes)
        source_sha = hashlib.sha256(source_bytes).hexdigest()
        payload = source_bytes
        rewrite_used = False
        if not preserve_original:
            if rewrite_enabled:
                payload = self._rewrite_for_screen_compatibility(payload, convert_m4_to_m3=convert_m4_to_m3)
                rewrite_used = True
            elif convert_m4_to_m3:
                payload = self._rewrite_for_screen_compatibility(payload, convert_m4_to_m3=True)
                rewrite_used = True
            if normalize_line_endings:
                payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        payload_size = len(payload)
        payload_sha = hashlib.sha256(payload).hexdigest()
        sanitize_filename = bool(up_cfg.get("sanitize_filename", False))
        upload_name = self._build_upload_filename(path.name, force_extension=force_extension, sanitize=sanitize_filename)

        params = {"path": upload_path}
        data = {"path": upload_path, "size": str(len(payload))}
        files = {"file": (upload_name, payload, "application/octet-stream")}
        try:
            resp = self.session.post(
                url,
                params=params,
                data=data,
                files=files,
                timeout=max(20.0, self._timeout()),
                stream=True,
            )
            text = resp.text if isinstance(resp.text, str) else ""
            preview = text[:220].replace("\n", "\\n").replace("\r", "")
            self.last_debug = {
                "endpoint": endpoint,
                "method": "POST",
                "url": url,
                "params": {"path": upload_path, "file_field": "file", "upload_filename": upload_name},
                "status_code": resp.status_code,
                "success": bool(resp.ok and "invalid parameter" not in text.lower()),
                "preview": preview,
                "error": "" if resp.ok else f"http {resp.status_code}",
            }
            if "invalid parameter" in text.lower():
                self.last_debug["error"] = "Invalid parameter"
                return {
                    "ok": False,
                    "error": "Invalid parameter",
                    "upload_status_code": resp.status_code,
                    "upload_response": text,
                    "endpoint": endpoint,
                    "method": "POST",
                    "params": params,
                    "upload_filename": upload_name,
                    "file_field": "file",
                    "file_size": len(payload),
                    "source_size": source_size,
                    "payload_size": payload_size,
                    "preserve_original": preserve_original,
                    "rewrite_used": rewrite_used,
                    "normalize_line_endings": normalize_line_endings,
                    "source_sha256": source_sha,
                    "payload_sha256": payload_sha,
                }
            return {
                "ok": bool(resp.ok),
                "filename": upload_name,
                "upload_status_code": resp.status_code,
                "upload_response": text,
                "endpoint": endpoint,
                "method": "POST",
                "params": params,
                "upload_filename": upload_name,
                "file_field": "file",
                "file_size": len(payload),
                "source_size": source_size,
                "payload_size": payload_size,
                "preserve_original": preserve_original,
                "rewrite_used": rewrite_used,
                "normalize_line_endings": normalize_line_endings,
                "source_sha256": source_sha,
                "payload_sha256": payload_sha,
            }
        except requests.RequestException as exc:
            self.last_debug = {
                "endpoint": endpoint,
                "method": "POST",
                "url": url,
                "params": {"path": upload_path, "file_field": "file", "upload_filename": upload_name},
                "status_code": None,
                "success": False,
                "preview": "",
                "error": str(exc),
            }
            return {
                "ok": False,
                "error": str(exc),
                "upload_status_code": None,
                "upload_response": "",
                "endpoint": endpoint,
                "method": "POST",
                "params": params,
                "upload_filename": upload_name,
                "file_field": "file",
                "file_size": len(payload),
                "source_size": source_size,
                "payload_size": payload_size,
                "preserve_original": preserve_original,
                "rewrite_used": rewrite_used,
                "normalize_line_endings": normalize_line_endings,
                "source_sha256": source_sha,
                "payload_sha256": payload_sha,
            }

    def upload_bytes_to_sd(self, filename: str, data: bytes, path: str = "/") -> dict[str, Any]:
        ray = self.cfg.get("ray5", {})
        endpoint = str(ray.get("upload_endpoint", "/upload"))
        url = self._base() + endpoint
        upload_path = str(path or ray.get("upload_path", "/") or "/")
        upload_name = Path(str(filename or "upload.gcode")).name
        ext = Path(upload_name).suffix.lower()
        if ext not in {".gc", ".nc", ".gcode"}:
            return {"ok": False, "message": f"extension {ext!r} not allowed", "raw": ""}
        payload = bytes(data or b"")
        params = {"path": upload_path}
        form = {"path": upload_path, "size": str(len(payload))}
        files = {"file": (upload_name, payload, "application/octet-stream")}
        try:
            resp = self.session.post(
                url,
                params=params,
                data=form,
                files=files,
                timeout=max(20.0, self._timeout()),
                stream=True,
            )
            text = resp.text if isinstance(resp.text, str) else ""
            preview = text[:220].replace("\n", "\\n").replace("\r", "")
            ok = bool(resp.ok and "invalid parameter" not in text.lower())
            self.last_debug = {
                "endpoint": endpoint,
                "method": "POST",
                "url": url,
                "params": {"path": upload_path, "file_field": "file", "upload_filename": upload_name},
                "status_code": resp.status_code,
                "success": ok,
                "preview": preview,
                "error": "" if ok else (text or f"http {resp.status_code}"),
            }
            return {
                "ok": ok,
                "filename": upload_name,
                "path": upload_path,
                "size": len(payload),
                "message": "Uploaded to SD" if ok else (text or f"http {resp.status_code}"),
                "raw": text,
                "status_code": resp.status_code,
            }
        except requests.RequestException as exc:
            self.last_debug = {
                "endpoint": endpoint,
                "method": "POST",
                "url": url,
                "params": {"path": upload_path, "file_field": "file", "upload_filename": upload_name},
                "status_code": None,
                "success": False,
                "preview": "",
                "error": str(exc),
            }
            return {"ok": False, "filename": upload_name, "path": upload_path, "size": len(payload), "message": str(exc), "raw": ""}

    def _build_upload_filename(self, original_name: str, force_extension: str = "", sanitize: bool = False) -> str:
        base_name = Path(str(original_name or "job.gcode")).name
        original_ext = Path(base_name).suffix.lower() or ".gcode"
        if sanitize:
            stem = Path(base_name).stem
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "job"
            if force_extension:
                return f"{safe}.{force_extension}"
            return f"{safe}{original_ext}"
        if force_extension:
            return f"{Path(base_name).stem}.{force_extension}"
        return base_name

    def _rewrite_for_screen_compatibility(self, content: bytes, convert_m4_to_m3: bool = False) -> bytes:
        text = content.decode("utf-8", errors="ignore")
        out: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(";"):
                continue
            line = re.sub(r"\(.*?\)", "", line).strip()
            if not line:
                continue
            compact = self._compact_gcode_spacing(line)
            if convert_m4_to_m3 and compact.upper() == "M4":
                compact = "M3"
            out.append(compact)
        return ("\n".join(out) + "\n").encode("utf-8")

    def _compact_gcode_spacing(self, line: str) -> str:
        tokens = [tok for tok in re.split(r"\s+", line.strip()) if tok]
        return " ".join(tokens).upper()

    def _extract_status_line(self, text: str) -> str:
        for line in str(text).replace("\r", "\n").split("\n"):
            s = line.strip()
            if s.startswith("<") and s.endswith(">"):
                return s
        m = re.search(r"(<[^>\n]+>)", str(text))
        return m.group(1) if m else ""

    def _parse_status(self, line: str) -> dict[str, Any]:
        out: dict[str, Any] = {"state": "UNKNOWN", "x": None, "y": None, "z": None}
        if not line:
            return out
        parts = line[1:-1].split("|")
        if parts:
            out["state"] = parts[0]
        for p in parts[1:]:
            if p.startswith("MPos:"):
                vals = p.split(":", 1)[1].split(",")
                if len(vals) >= 3:
                    out["x"], out["y"], out["z"] = vals[0], vals[1], vals[2]
        return out

    def normalize_sd_file(self, entry: Any) -> dict[str, Any]:
        name = ""
        path = ""
        shortname = ""
        size_value: str | None = None
        size_bytes: int | None = None
        modified = ""
        is_dir = False
        raw = entry

        if isinstance(entry, dict):
            name = str(entry.get("name") or entry.get("filename") or entry.get("fullname") or "").strip()
            shortname = str(entry.get("shortname") or "").strip()
            raw_path = str(entry.get("path") or "").strip()
            if not raw_path and name:
                raw_path = "/" + name.lstrip("/")
            path = raw_path or ""
            size_raw = entry.get("size")
            if size_raw not in (None, ""):
                size_value = str(size_raw).strip()
            raw_mod = entry.get("datetime") or entry.get("modified") or entry.get("mtime") or entry.get("date")
            modified = str(raw_mod or "").strip()
            is_dir = bool(entry.get("directory") or entry.get("is_directory") or entry.get("isDir"))
            if size_value == "-1":
                is_dir = True
        else:
            name = str(entry or "").strip()
            path = "/" + name.lstrip("/") if name else ""

        lower_name = name.lower()
        if lower_name in {"system volume information", "$recycle.bin"}:
            is_dir = True
        ext = Path(name).suffix.lower()
        file_type = "folder" if is_dir else ("gcode" if ext in {".gcode", ".gc", ".nc", ".txt"} else "unknown")
        if size_value and size_value.isdigit():
            try:
                size_bytes = int(size_value)
            except Exception:
                size_bytes = None
        can_start = (not is_dir) and (file_type in {"gcode"})
        can_delete = (not is_dir) and lower_name not in {"system volume information"}
        display_size = size_value if size_value not in (None, "", "-1") else "---"
        if is_dir:
            display_size = "---"
        return {
            "name": name or "---",
            "shortname": shortname or name or "---",
            "path": path or ("/" + (name or "").lstrip("/")),
            "size": display_size,
            "size_bytes": size_bytes,
            "modified": modified or "---",
            "is_directory": is_dir,
            "type": file_type,
            "can_start": can_start,
            "can_delete": can_delete,
            "raw": raw,
        }

    def normalize_file_list_response(self, raw_response: Any, base_path: str = "/") -> dict[str, Any]:
        parsed: Any = raw_response
        if isinstance(raw_response, str):
            txt = raw_response.strip()
            if txt.startswith("{") or txt.startswith("["):
                try:
                    parsed = json.loads(txt)
                except Exception:
                    return {
                        "ok": False,
                        "error": "response was not valid JSON",
                        "path": base_path,
                        "files": [],
                        "storage": {},
                        "raw": raw_response,
                    }
            else:
                return {
                    "ok": False,
                    "error": "response was plain text",
                    "path": base_path,
                    "files": [],
                    "storage": {},
                    "raw": raw_response,
                    "preview": txt[:220],
                }

        rows: list[Any] = []
        storage = {"total": "---", "used": "---", "occupation": "---", "mode": "---", "status": "---"}
        resp_path = base_path
        if isinstance(parsed, list):
            rows = parsed
        elif isinstance(parsed, dict):
            if isinstance(parsed.get("files"), list):
                rows = parsed.get("files", [])
            else:
                rows = [parsed]
            resp_path = str(parsed.get("path") or base_path or "/")
            storage = {
                "total": str(parsed.get("total") or "---"),
                "used": str(parsed.get("used") or "---"),
                "occupation": str(parsed.get("occupation") or "---"),
                "mode": str(parsed.get("mode") or "---"),
                "status": str(parsed.get("status") or "---"),
            }
        normalized = [self.normalize_sd_file(row) for row in rows]
        return {"ok": True, "path": resp_path or "/", "files": normalized, "storage": storage, "raw": parsed}

    def debug_info(self, config_path: str = "") -> dict[str, Any]:
        ray = self.cfg.get("ray5", {})
        return {
            "config_path": config_path,
            "ray5_host": str(ray.get("host", "")),
            "ray5_port": int(ray.get("port", 8848)),
            "base_url": self._base(),
            "files_endpoint": str(ray.get("files_endpoint", "/files")),
            "files_params": self.last_debug.get("params"),
            "file_list_endpoint_attempted": self.last_debug.get("endpoint"),
            "http_status_code": self.last_debug.get("status_code"),
            "success": bool(self.last_debug.get("success", False)),
            "response_preview": self.last_debug.get("preview", ""),
            "last_error": self.last_debug.get("error", ""),
            "method": self.last_debug.get("method"),
            "url": self.last_debug.get("url"),
        }
