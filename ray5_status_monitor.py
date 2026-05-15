from __future__ import annotations

import threading
import time
import re
from collections import deque
from typing import Any

import websocket


class Ray5StatusMonitor:
    def __init__(self, ray5_client: Any, cfg: dict[str, Any], logger: Any | None = None) -> None:
        self.ray5 = ray5_client
        self.cfg = cfg
        self.log = logger
        status_cfg = cfg.get("status", {}) if isinstance(cfg.get("status"), dict) else {}
        ray = cfg.get("ray5", {}) if isinstance(cfg.get("ray5"), dict) else {}
        self.host = str(ray.get("host", "")).strip()
        self.ws_enabled = bool(status_cfg.get("websocket_enabled", True))
        self.ws_port = int(status_cfg.get("websocket_port", 8849))
        self.ws_path = str(status_cfg.get("websocket_path", "/") or "/")
        self.subprotocol = str(status_cfg.get("websocket_subprotocol", "arduino") or "").strip()
        self.debug_logging = bool(status_cfg.get("debug_logging", False))
        self.poll_seconds = max(0.2, float(status_cfg.get("poll_seconds", 1.0)))
        self.reconnect_seconds = max(1.0, float(status_cfg.get("reconnect_seconds", 3.0)))
        self.stale_after_seconds = max(1.0, float(status_cfg.get("stale_after_seconds", 5.0)))

        self._thread: threading.Thread | None = None
        self._poll_thread: threading.Thread | None = None
        self._ws_app: websocket.WebSocketApp | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._ws_connected = False
        self._page_id: str | None = None
        self._latest_status: dict[str, Any] | None = None
        self._last_live_ts: float | None = None
        self._active_error: str | None = None
        self._last_error: str | None = None
        self._last_disconnect_error: str | None = None
        self._reconnect_count = 0
        self._last_reconnect_time: float | None = None
        self._announced_live = False
        self._last_raw_message: str | None = None
        self._last_raw_status: str | None = None
        self._last_parse_error: str | None = None
        self._poll_count = 0
        self._status_trigger_count = 0
        self._status_line_count = 0
        self._last_wco: dict[str, float | None] = {"x": None, "y": None, "z": None}
        self._recent_lines: deque[tuple[float, str]] = deque(maxlen=800)

    def start(self) -> None:
        if not self.ws_enabled or not self.host or self.host.upper() == "YOUR_RAY5_IP":
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ray5-status-monitor")
        self._thread.start()
        if not self._poll_thread or not self._poll_thread.is_alive():
            self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name="ray5-status-poller")
            self._poll_thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            app = self._ws_app
        try:
            if app is not None:
                app.close()
        except Exception:
            pass
        try:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)
        except Exception:
            pass
        with self._lock:
            self._ws_connected = False
            self._page_id = None
            self._ws_app = None
            self._active_error = None
        try:
            if self._poll_thread and self._poll_thread.is_alive():
                self._poll_thread.join(timeout=2.0)
        except Exception:
            pass

    def get_page_id(self) -> str | None:
        with self._lock:
            return self._page_id

    def get_latest_status(self) -> dict[str, Any] | None:
        with self._lock:
            if self._latest_status is None:
                return None
            d = dict(self._latest_status)
            d["websocket_connected"] = self._ws_connected
            d["websocket_page_id"] = self._page_id
            d["last_error"] = self._active_error
            if self._last_live_ts is not None:
                age = time.time() - self._last_live_ts
                d["stale"] = age > self.stale_after_seconds
                d["age_seconds"] = age
            else:
                d["stale"] = True
                d["age_seconds"] = None
            return d

    def is_connected(self) -> bool:
        with self._lock:
            return self._ws_connected

    def get_debug_info(self) -> dict[str, Any]:
        with self._lock:
            age = (time.time() - self._last_live_ts) if self._last_live_ts is not None else None
            return {
                "monitor_exists": True,
                "websocket_enabled": self.ws_enabled,
                "websocket_connected": self._ws_connected,
                "page_id": self._page_id,
                "last_raw_message": self._last_raw_message,
                "last_raw_status": self._last_raw_status,
                "last_status_age_seconds": age,
                "last_parse_error": self._last_parse_error,
                "poll_count": self._poll_count,
                "status_trigger_count": self._status_trigger_count,
                "status_line_count": self._status_line_count,
                "latest_status": dict(self._latest_status) if isinstance(self._latest_status, dict) else None,
                "active_error": self._active_error,
                "last_error": self._last_error,
                "last_disconnect_error": self._last_disconnect_error,
                "reconnect_count": self._reconnect_count,
                "last_reconnect_time": self._last_reconnect_time,
            }

    def get_lines_since(self, since_ts: float) -> list[str]:
        cutoff = float(since_ts or 0.0)
        with self._lock:
            return [line for ts, line in self._recent_lines if ts >= cutoff]

    def _run(self) -> None:
        while not self._stop.is_set():
            ws_url = f"ws://{self.host}:{self.ws_port}{self.ws_path}"
            self._log(f"Ray5 WebSocket connecting: {ws_url}")

            def on_open(_ws: websocket.WebSocketApp) -> None:
                with self._lock:
                    self._ws_connected = True
                    self._active_error = None
                self._log("Ray5 WebSocket connected")

            def on_message(_ws: websocket.WebSocketApp, message: Any) -> None:
                self._handle_message(message)

            def on_error(_ws: websocket.WebSocketApp, error: Any) -> None:
                err_s = str(error)
                with self._lock:
                    self._active_error = err_s
                    self._last_error = err_s
                    self._last_disconnect_error = err_s
                if "10053" in err_s or "ConnectionAbortedError" in err_s:
                    self._log("Ray5 WebSocket connection aborted; reconnecting", level="warn")
                else:
                    self._log(f"Ray5 WebSocket error: {error}", level="warn")

            def on_close(_ws: websocket.WebSocketApp, _code: Any, msg: Any) -> None:
                msg_s = str(msg or "")
                with self._lock:
                    self._ws_connected = False
                    if msg_s:
                        self._active_error = msg_s
                        self._last_error = msg_s
                        self._last_disconnect_error = msg_s
                if "10053" in msg_s or "ConnectionAbortedError" in msg_s:
                    self._log("Ray5 WebSocket connection aborted; reconnecting", level="warn")
                else:
                    self._log(f"Ray5 WebSocket disconnected: {msg}", level="warn")

            ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                subprotocols=[self.subprotocol] if self.subprotocol else None,
            )
            with self._lock:
                self._ws_app = ws

            try:
                ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as exc:
                with self._lock:
                    self._active_error = str(exc)
                    self._last_error = str(exc)
                self._log(f"Ray5 WebSocket run failed: {exc}", level="warn")

            if self._stop.wait(self.reconnect_seconds):
                break
            with self._lock:
                self._reconnect_count += 1
                self._last_reconnect_time = time.time()
            self._log(f"Ray5 WebSocket reconnecting in {self.reconnect_seconds:.0f}s", level="warn")

    def _poll_loop(self) -> None:
        if self.debug_logging:
            self._log("[STATUS] poller thread started")
        while not self._stop.is_set():
            with self._lock:
                self._poll_count += 1
                ws_connected = self._ws_connected
            if not ws_connected:
                if self._stop.wait(self.poll_seconds):
                    break
                continue
            page_id = self.get_page_id()
            if page_id in (None, ""):
                if self.debug_logging:
                    self._log("[STATUS] poll skipped: no PAGEID yet")
                if self._stop.wait(self.poll_seconds):
                    break
                continue
            if self.debug_logging:
                self._log(f"[STATUS] trigger sent: commandText=? PAGEID={page_id}")
            result = self.ray5.trigger_live_status(page_id)
            with self._lock:
                self._status_trigger_count += 1
            status_code = self.ray5.last_debug.get("status_code")
            preview = str(self.ray5.last_debug.get("preview", "") or "").strip()
            ignored = bool(status_code == 200 and preview.lower() in {"error", "invalid command"})
            if self.debug_logging:
                self._log(
                    f"[STATUS] trigger HTTP result: status={status_code} body={preview!r} ignored={'true' if ignored else 'false'}"
                )
            if not result.get("ok"):
                with self._lock:
                    err = str(result.get("message") or "status trigger failed")
                    self._last_error = err
                    live_age_ok = self._last_live_ts is not None and ((time.time() - self._last_live_ts) <= self.stale_after_seconds)
                    if (not self._ws_connected) or (not live_age_ok):
                        self._active_error = err
            if self._stop.wait(self.poll_seconds):
                break

    def _handle_message(self, message: Any) -> None:
        if isinstance(message, bytes):
            text = message.decode("utf-8", errors="replace")
        else:
            text = str(message)
        with self._lock:
            self._last_raw_message = text[:500]
        lines = text.replace("\r", "\n").split("\n")
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            with self._lock:
                self._recent_lines.append((time.time(), line))
            if line.startswith("CURRENT_ID:"):
                pid = line.split(":", 1)[1].strip()
                with self._lock:
                    self._page_id = pid
                self._log(f"Ray5 WebSocket PAGEID: {pid}")
                continue
            if line.startswith("ACTIVE_ID:") or line.startswith("PING:"):
                continue
            status_line = self._extract_status_line(line)
            if status_line:
                try:
                    parsed = self._parse_status_line(status_line)
                    with self._lock:
                        self._latest_status = parsed
                        self._last_live_ts = time.time()
                        self._last_raw_status = status_line
                        self._last_parse_error = None
                        self._active_error = None
                        self._status_line_count += 1
                    if not self._announced_live:
                        self._announced_live = True
                        self._log(f"Ray5 live status active: {status_line[:160]}")
                    if self.debug_logging:
                        self._log(f"[STATUS] ws raw: {status_line[:160]}")
                        self._log(
                            "[STATUS] parsed live status: "
                            f"state={parsed.get('state')} "
                            f"mpos={parsed.get('machine_position',{}).get('x')},"
                            f"{parsed.get('machine_position',{}).get('y')},"
                            f"{parsed.get('machine_position',{}).get('z')}"
                        )
                except Exception as exc:
                    with self._lock:
                        self._last_parse_error = str(exc)
                        self._active_error = str(exc)
                        self._last_error = str(exc)
                    self._log(f"Ray5 live status parse failed: {exc} raw={status_line[:160]}", level="warn")
                continue
            if line.lower().startswith("alarm"):
                with self._lock:
                    if self._latest_status is None:
                        self._latest_status = {}
                    self._latest_status["state"] = "ALARM"
                    self._latest_status["alarm_message"] = line
                    self._last_live_ts = time.time()
                continue

    def _extract_status_line(self, line: str) -> str:
        s = str(line).strip()
        if s.startswith("<") and s.endswith(">"):
            return s
        m = re.search(r"(<[^>\n]+>)", s)
        return m.group(1).strip() if m else ""

    def _parse_status_line(self, line: str) -> dict[str, Any]:
        state = "UNKNOWN"
        mpos = {"x": None, "y": None, "z": None}
        wco = {"x": None, "y": None, "z": None}
        wpos = {"x": None, "y": None, "z": None}
        wco_seen = False
        wpos_seen = False
        feed = None
        spindle = None
        parts = line[1:-1].split("|")
        if parts:
            state = parts[0]
        for part in parts[1:]:
            if part.startswith("MPos:"):
                vals = part.split(":", 1)[1].split(",")
                if len(vals) >= 2:
                    mpos["x"] = self._to_float(vals[0])
                    mpos["y"] = self._to_float(vals[1])
                    if len(vals) >= 3:
                        mpos["z"] = self._to_float(vals[2])
            elif part.startswith("WCO:"):
                vals = part.split(":", 1)[1].split(",")
                if len(vals) >= 2:
                    wco["x"] = self._to_float(vals[0])
                    wco["y"] = self._to_float(vals[1])
                    if len(vals) >= 3:
                        wco["z"] = self._to_float(vals[2])
                    if (wco["x"] is not None) or (wco["y"] is not None) or (wco["z"] is not None):
                        wco_seen = True
            elif part.startswith("WPos:"):
                vals = part.split(":", 1)[1].split(",")
                if len(vals) >= 2:
                    wpos["x"] = self._to_float(vals[0])
                    wpos["y"] = self._to_float(vals[1])
                    if len(vals) >= 3:
                        wpos["z"] = self._to_float(vals[2])
                    if (wpos["x"] is not None) or (wpos["y"] is not None) or (wpos["z"] is not None):
                        wpos_seen = True
            elif part.startswith("FS:"):
                vals = part.split(":", 1)[1].split(",")
                if len(vals) >= 1:
                    feed = self._to_float(vals[0])
                if len(vals) >= 2:
                    spindle = self._to_float(vals[1])

        # Cache latest WCO values because firmware may emit WCO only occasionally.
        if wco_seen:
            with self._lock:
                self._last_wco = {
                    "x": wco.get("x"),
                    "y": wco.get("y"),
                    "z": wco.get("z"),
                }
        else:
            with self._lock:
                cached_wco = dict(self._last_wco)
            if (cached_wco.get("x") is not None) or (cached_wco.get("y") is not None) or (cached_wco.get("z") is not None):
                wco = cached_wco

        wco_available = (wco.get("x") is not None) and (wco.get("y") is not None)
        wpos_calculated = False
        if (not wpos_seen) and wco_available and (mpos.get("x") is not None) and (mpos.get("y") is not None):
            wpos["x"] = float(mpos["x"]) - float(wco["x"])
            wpos["y"] = float(mpos["y"]) - float(wco["y"])
            if (mpos.get("z") is not None) and (wco.get("z") is not None):
                wpos["z"] = float(mpos["z"]) - float(wco["z"])
            wpos_calculated = True

        has_w = (wpos.get("x") is not None) or (wpos.get("y") is not None)
        has_m = (mpos.get("x") is not None) or (mpos.get("y") is not None)
        has_wco = wco_available
        if wpos_calculated and has_m and has_wco:
            coordinate_source_label = "MPos + WCO"
        elif has_w and has_m and has_wco:
            coordinate_source_label = "WPos + MPos + WCO"
        elif has_w and has_m:
            coordinate_source_label = "WPos + MPos"
        elif has_m and has_wco:
            coordinate_source_label = "MPos + WCO"
        elif has_w:
            coordinate_source_label = "WPos"
        elif has_m:
            coordinate_source_label = "MPos"
        else:
            coordinate_source_label = "—"

        return {
            "state": state,
            "machine_position": mpos,
            "work_offset": wco,
            "work_position": wpos,
            "wco_available": wco_available,
            "wpos_calculated": wpos_calculated,
            "coordinate_source_label": coordinate_source_label,
            "feed": feed,
            "spindle": spindle,
            "raw_status": line,
            "timestamp": time.time(),
            "status_source": "live_websocket",
            "position_source": "live_websocket",
        }

    def _to_float(self, v: Any) -> float | None:
        try:
            return float(str(v).strip())
        except Exception:
            return None

    def _log(self, msg: str, level: str = "info") -> None:
        if not self.log:
            return
        try:
            self.log.add(level, msg)
        except Exception:
            pass
