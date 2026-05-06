from __future__ import annotations

import io
import json
import logging
import os
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw


class CameraCaptureError(RuntimeError):
    pass


def mask_camera_url(url: str) -> str:
    try:
        parsed = urlsplit(str(url or "").strip())
    except Exception:
        return ""
    if not parsed.scheme or not parsed.netloc:
        return str(url or "")
    if parsed.username is None and parsed.password is None:
        return urlunsplit(parsed)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    auth = "****:****@" + host
    return urlunsplit((parsed.scheme, auth, parsed.path, parsed.query, parsed.fragment))


def offline_frame_jpeg(message: str = "Camera unavailable") -> bytes:
    img = Image.new("RGB", (1280, 720), (28, 32, 40))
    draw = ImageDraw.Draw(img)
    draw.text((40, 40), "Ray5 Pilot Camera", fill=(220, 225, 235))
    draw.text((40, 90), message[:140], fill=(240, 180, 180))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()


class CameraManager:
    def __init__(self, cfg: dict[str, Any], base_dir: Path) -> None:
        self.log = logging.getLogger("CameraManager")
        self.cfg = cfg
        self.base_dir = base_dir
        self.session = requests.Session()
        self.session.trust_env = False
        self.camera = cfg.get("camera", {}) if isinstance(cfg.get("camera"), dict) else {}
        self.output_dir = (base_dir / str(self.camera.get("output_dir", "camera_captures"))).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.filename_prefix = str(self.camera.get("filename_prefix", "ray5_bed")) or "ray5_bed"
        self.save_history = bool(self.camera.get("save_history", False))
        self.keep_last = max(0, int(self.camera.get("keep_last", 0)))
        self.auto_cleanup_on_start = bool(self.camera.get("auto_cleanup_on_start", True))
        self.cleanup_on_capture = bool(self.camera.get("cleanup_on_capture", True))
        self.latest_raw_name = str(self.camera.get("latest_raw_name", "latest_raw.jpg")) or "latest_raw.jpg"
        self.latest_processed_name = str(self.camera.get("latest_processed_name", "latest.jpg")) or "latest.jpg"
        self.timeout_seconds = max(1.0, float(self.camera.get("timeout_seconds", 15)))
        self.latest_raw_path = self.output_dir / self.latest_raw_name
        self.latest_path = self.output_dir / self.latest_processed_name
        self.latest_instructions_path = self.output_dir / "latest_lightburn_instructions.txt"
        self.last_capture_debug: dict[str, Any] = {}

    def enabled(self) -> bool:
        return bool(self.camera.get("enabled", False))

    def stream_url(self) -> str:
        return str(self.camera.get("url") or self.camera.get("stream_url") or "").strip()

    def snapshot_url(self) -> str:
        return str(self.camera.get("snapshot_url") or "").strip()

    def proxy_enabled(self) -> bool:
        return bool(self.camera.get("proxy_enabled", True))

    def proxy_path(self) -> str:
        return str(self.camera.get("proxy_path", "/camera/stream")).strip() or "/camera/stream"

    def reconnect_seconds(self) -> float:
        return max(1.0, float(self.camera.get("reconnect_seconds", 5)))

    def capture_method(self) -> str:
        return str(self.camera.get("capture_method", "ffmpeg")).strip().lower()

    def capture(self, reason: str = "manual") -> Path:
        self._reload_camera_config()
        if not self.enabled():
            raise CameraCaptureError("camera is disabled")
        if self.cleanup_on_capture and not self.save_history:
            self.cleanup_snapshots(mode="capture", keep_latest=False)
        content = self._capture_bytes()
        raw_image = Image.open(io.BytesIO(content)).convert("RGB")
        raw_w, raw_h = raw_image.size
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.latest_raw_path = self.output_dir / self.latest_raw_name
        self.latest_path = self.output_dir / self.latest_processed_name
        raw_image.save(self.latest_raw_path, format="JPEG", quality=90)
        self.log.info("[CAMERA] Raw snapshot saved: %s", self._camera_display_path(self.latest_raw_path))
        self.log.info("[CAMERA] Raw image size: %sx%s", raw_w, raw_h)
        corrected = self._create_corrected_from_raw()
        out_path = self.latest_path
        if self.save_history:
            ts_processed = self.output_dir / f"{self.filename_prefix}_{ts}.jpg"
            ts_raw = self.output_dir / f"{self.filename_prefix}_{ts}_raw.jpg"
            raw_image.save(ts_raw, format="JPEG", quality=90)
            if self.latest_path.exists():
                ts_processed.write_bytes(self.latest_path.read_bytes())
        self._write_overlay_instructions()
        self._prune_old()
        removed = 0
        if not self.save_history:
            removed = self.cleanup_snapshots(mode="capture", keep_latest=True)
            self.log.info("[CAMERA] Cleanup removed %s old image(s)", removed)
        processed_size = [0, 0]
        try:
            with Image.open(self.latest_path) as final_img:
                processed_size = [int(final_img.size[0]), int(final_img.size[1])]
        except Exception:
            pass
        self.last_capture_debug.update(
            {
                "reason": reason,
                "raw_size": [int(raw_w), int(raw_h)],
                "processed_size": processed_size,
                "latest_raw_path": str(self.latest_raw_path),
                "latest_path": str(self.latest_path),
                "deskew_enabled": bool(self.camera.get("deskew", {}).get("enabled", False)),
                "source_points_count": len(self.camera.get("deskew", {}).get("source_points", []) or []),
                "deskew_output_size": self.camera.get("deskew", {}).get("output_size", [1200, 1200]),
                "deskew_skip_reason": corrected.get("warning", "" if corrected.get("deskew_applied") else "enabled=false"),
                "deskew_applied": bool(corrected.get("deskew_applied", False)),
                "postprocess_applied": bool(corrected.get("postprocess_applied", False)),
                "instructions_exists": self.latest_instructions_path.exists(),
            }
        )
        return out_path

    def _reload_camera_config(self) -> None:
        cfg_path = self.base_dir / "config.json"
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return
        camera = data.get("camera", {})
        if isinstance(camera, dict):
            self.camera = camera
            self.output_dir = (self.base_dir / str(self.camera.get("output_dir", "camera_captures"))).resolve()
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.filename_prefix = str(self.camera.get("filename_prefix", "ray5_bed")) or "ray5_bed"
            self.save_history = bool(self.camera.get("save_history", False))
            self.keep_last = max(0, int(self.camera.get("keep_last", 0)))
            self.auto_cleanup_on_start = bool(self.camera.get("auto_cleanup_on_start", True))
            self.cleanup_on_capture = bool(self.camera.get("cleanup_on_capture", True))
            self.latest_raw_name = str(self.camera.get("latest_raw_name", "latest_raw.jpg")) or "latest_raw.jpg"
            self.latest_processed_name = str(self.camera.get("latest_processed_name", "latest.jpg")) or "latest.jpg"
            self.timeout_seconds = max(1.0, float(self.camera.get("timeout_seconds", 15)))

    def _capture_bytes(self) -> bytes:
        snap = self.snapshot_url()
        if snap:
            return self._capture_http_snapshot(snap)
        stream = self.stream_url()
        if not stream:
            raise CameraCaptureError("camera URL not configured")
        method = self.capture_method()
        if method == "ffmpeg":
            return self._capture_ffmpeg(stream)
        return self._capture_opencv_frame(stream)

    def _capture_http_snapshot(self, url: str) -> bytes:
        try:
            resp = self.session.get(url, timeout=self.timeout_seconds, stream=True)
        except requests.RequestException as exc:
            raise CameraCaptureError(f"http snapshot failed: {exc}") from exc
        if not resp.ok:
            raise CameraCaptureError(f"http snapshot failed ({resp.status_code})")
        ctype = str(resp.headers.get("Content-Type", "")).lower()
        data = resp.content
        if "multipart" in ctype:
            boundary = b"\xff\xd8"
            start = data.find(boundary)
            if start >= 0:
                end = data.find(b"\xff\xd9", start)
                if end > start:
                    return data[start : end + 2]
        return data

    def _capture_ffmpeg(self, stream_url: str) -> bytes:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise CameraCaptureError("ffmpeg not found in PATH")
        tmp = self.output_dir / f".tmp_capture_{int(time.time())}.jpg"
        cmd = [
            ffmpeg,
            "-y",
            "-rtsp_transport",
            "tcp",
            "-i",
            stream_url,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(tmp),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=self.timeout_seconds + 8)
        except subprocess.TimeoutExpired as exc:
            raise CameraCaptureError("ffmpeg capture timed out") from exc
        except subprocess.CalledProcessError as exc:
            raise CameraCaptureError(f"ffmpeg capture failed: {exc.stderr.decode(errors='ignore')[:180]}") from exc
        if not tmp.exists():
            raise CameraCaptureError("ffmpeg did not produce output")
        data = tmp.read_bytes()
        tmp.unlink(missing_ok=True)
        return data

    def _capture_opencv_frame(self, stream_url: str) -> bytes:
        cap = cv2.VideoCapture(stream_url)
        try:
            ok, frame = cap.read()
            if not ok or frame is None:
                raise CameraCaptureError("opencv failed to read frame")
            ok, buf = cv2.imencode(".jpg", frame)
            if not ok:
                raise CameraCaptureError("opencv encode failed")
            return bytes(buf)
        finally:
            cap.release()

    def _dpi(self) -> float:
        pp = self.camera.get("postprocess", {}) if isinstance(self.camera.get("postprocess"), dict) else {}
        return float(pp.get("dpi", 101.6))

    def _create_corrected_from_raw(self) -> dict[str, Any]:
        deskew = self.camera.get("deskew", {}) if isinstance(self.camera.get("deskew"), dict) else {}
        image = cv2.imread(str(self.latest_raw_path))
        if image is None:
            self.latest_path.write_bytes(self.latest_raw_path.read_bytes())
            return {"deskew_applied": False, "postprocess_applied": False}
        deskew_applied = False
        postprocess_applied = False
        if bool(deskew.get("enabled", False)):
            source_points = deskew.get("source_points", [])
            self.log.info("[CAMERA] Deskew enabled")
            self.log.info("[CAMERA] Deskew source points: %s", len(source_points) if isinstance(source_points, list) else 0)
            try:
                src_points = np.array(self._parse_deskew_source_points(source_points), dtype="float32")
                out_w, out_h = self._parse_deskew_output_size(deskew.get("output_size", [1200, 1200]))
                self.log.info("[CAMERA] Deskew output size: %sx%s", out_w, out_h)
                dst_points = np.array(
                    [[0.0, 0.0], [float(out_w), 0.0], [float(out_w), float(out_h)], [0.0, float(out_h)]],
                    dtype="float32",
                )
                matrix = cv2.getPerspectiveTransform(src_points, dst_points)
                image = cv2.warpPerspective(image, matrix, (out_w, out_h))
                deskew_applied = True
                self.log.info("[CAMERA] Deskew applied")
            except Exception as exc:
                self.log.warning("[CAMERA] Deskew failed, using raw image as latest.jpg: %s", exc)
                self.latest_path.write_bytes(self.latest_raw_path.read_bytes())
                return {"deskew_applied": False, "postprocess_applied": False, "warning": str(exc)}
        else:
            self.log.info("[CAMERA] Deskew skipped: enabled=false")
        try:
            image, postprocess_applied = self._apply_postprocess(image)
        except Exception as exc:
            self.log.warning("[CAMERA] Postprocess failed, using deskewed image as latest.jpg: %s", exc)
        post = self.camera.get("postprocess", {}) if isinstance(self.camera.get("postprocess"), dict) else {}
        if bool(post.get("overlay_guides", {}).get("enabled", False)):
            image = self._draw_overlay_guides(image)
            self.log.info("[CAMERA] Overlay guides drawn")
        if not cv2.imwrite(str(self.latest_path), image):
            raise CameraCaptureError(f"failed to write final image {self.latest_path}")
        self._write_dpi_metadata(self.latest_path)
        self.log.info("[CAMERA] Final image saved: %s", self._camera_display_path(self.latest_path))
        return {"deskew_applied": deskew_applied, "postprocess_applied": postprocess_applied}

    def _apply_postprocess(self, image: Any) -> tuple[Any, bool]:
        post = self.camera.get("postprocess", {}) if isinstance(self.camera.get("postprocess"), dict) else {}
        if not bool(post.get("enabled", False)):
            return image, False
        final_w, final_h = self._parse_deskew_output_size(post.get("final_size", [1200, 1200]), default=(1200, 1200))
        scale = float(post.get("scale", 1.0))
        crop_margin = int(post.get("center_crop_margin", 0))
        rotate_degrees_raw = int(post.get("rotate_degrees", 0))
        rotate_degrees = rotate_degrees_raw
        if rotate_degrees == -90:
            rotate_degrees = 270
        if rotate_degrees not in {0, 90, 180, 270}:
            self.log.warning("[CAMERA] Invalid rotate_degrees=%s, using 0", rotate_degrees_raw)
            rotate_degrees = 0
        rot_label = {0: "0 (none)", 90: "90 degrees CCW", 180: "180 degrees", 270: "270 degrees CCW / 90 degrees CW"}[rotate_degrees]
        self.log.info("[CAMERA] Processed overlay rotation: %s", rot_label)
        if scale != 1.0:
            h, w = image.shape[:2]
            scaled_w = int(w * scale)
            scaled_h = int(h * scale)
            image = cv2.resize(image, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)
            start_x = max((scaled_w - final_w) // 2, 0)
            start_y = max((scaled_h - final_h) // 2, 0)
            image = image[start_y:start_y + final_h, start_x:start_x + final_w]
        if crop_margin > 0:
            h, w = image.shape[:2]
            if crop_margin * 2 < h and crop_margin * 2 < w:
                cropped = image[crop_margin:h - crop_margin, crop_margin:w - crop_margin]
                image = cv2.resize(cropped, (final_w, final_h), interpolation=cv2.INTER_LINEAR)
        if rotate_degrees == 90:
            image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
            self.log.info("[CAMERA] Rotated final image 90 degrees CCW")
        elif rotate_degrees == 180:
            image = cv2.rotate(image, cv2.ROTATE_180)
            self.log.info("[CAMERA] Rotated final image 180 degrees")
        elif rotate_degrees == 270:
            image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
            self.log.info("[CAMERA] Rotated final image 270 degrees")
        if image.shape[1] != final_w or image.shape[0] != final_h:
            image = cv2.resize(image, (final_w, final_h), interpolation=cv2.INTER_LINEAR)
        self.log.info(
            "[CAMERA] Postprocess applied: scale=%s crop_margin=%s final_size=%sx%s",
            scale,
            crop_margin,
            final_w,
            final_h,
        )
        return image, True

    def _draw_overlay_guides(self, image: Any) -> Any:
        post = self.camera.get("postprocess", {}) if isinstance(self.camera.get("postprocess"), dict) else {}
        guides = post.get("overlay_guides", {}) if isinstance(post.get("overlay_guides", {}), dict) else {}
        canvas = image.copy()
        h, w = canvas.shape[:2]
        line_color = (40, 40, 40)
        line_thickness = 1
        if bool(guides.get("draw_border", True)):
            cv2.rectangle(canvas, (0, 0), (w - 1, h - 1), line_color, line_thickness, lineType=cv2.LINE_AA)
        if bool(guides.get("draw_center_cross", True)):
            cx = w // 2
            cy = h // 2
            cv2.line(canvas, (cx, 0), (cx, h - 1), line_color, line_thickness, lineType=cv2.LINE_AA)
            cv2.line(canvas, (0, cy), (w - 1, cy), line_color, line_thickness, lineType=cv2.LINE_AA)
        if bool(guides.get("draw_corner_marks", True)):
            mark = max(10, min(w, h) // 30)
            cv2.line(canvas, (0, 0), (mark, 0), line_color, line_thickness, lineType=cv2.LINE_AA)
            cv2.line(canvas, (0, 0), (0, mark), line_color, line_thickness, lineType=cv2.LINE_AA)
            cv2.line(canvas, (w - 1, 0), (w - 1 - mark, 0), line_color, line_thickness, lineType=cv2.LINE_AA)
            cv2.line(canvas, (w - 1, 0), (w - 1, mark), line_color, line_thickness, lineType=cv2.LINE_AA)
            cv2.line(canvas, (w - 1, h - 1), (w - 1 - mark, h - 1), line_color, line_thickness, lineType=cv2.LINE_AA)
            cv2.line(canvas, (w - 1, h - 1), (w - 1, h - 1 - mark), line_color, line_thickness, lineType=cv2.LINE_AA)
            cv2.line(canvas, (0, h - 1), (mark, h - 1), line_color, line_thickness, lineType=cv2.LINE_AA)
            cv2.line(canvas, (0, h - 1), (0, h - 1 - mark), line_color, line_thickness, lineType=cv2.LINE_AA)
        return canvas

    def _prune_old(self) -> None:
        if not self.save_history:
            return
        files = sorted(self.output_dir.glob(f"{self.filename_prefix}_*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[self.keep_last :] if self.keep_last > 0 else files:
            old.unlink(missing_ok=True)

    def _write_overlay_instructions(self) -> None:
        post = self.camera.get("postprocess", {}) if isinstance(self.camera.get("postprocess"), dict) else {}
        final_size = post.get("final_size", [1200, 1200])
        dpi = float(post.get("dpi", 101.6))
        mm_w = (float(final_size[0]) / dpi) * 25.4 if isinstance(final_size, list) and len(final_size) == 2 else 300.0
        mm_h = (float(final_size[1]) / dpi) * 25.4 if isinstance(final_size, list) and len(final_size) == 2 else 300.0
        txt = (
            "Ray5 Pilot Overlay Helper\n"
            "1) Drag latest.jpg into LightBurn.\n"
            f"2) Confirm import size is about {mm_w:.2f} mm x {mm_h:.2f} mm.\n"
            "3) Put camera image on a non-output layer and lock it.\n"
            "4) Use absolute coordinates.\n"
            "5) Place artwork over the material.\n"
            "6) Always frame before start.\n"
        )
        self.latest_instructions_path.write_text(txt, encoding="utf-8")
        self.log.info("[CAMERA] LightBurn instructions written")

    def open_capture_folder(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(self.output_dir))  # type: ignore[attr-defined]
        else:
            webbrowser.open(self.output_dir.as_uri())

    def cleanup_old_startup_snapshots(self) -> None:
        if not self.auto_cleanup_on_start:
            return
        self.cleanup_snapshots(mode="startup", keep_latest=False)

    def cleanup_snapshots(self, mode: str = "startup", keep_latest: bool = False) -> int:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        keep = {
            self.latest_raw_name.lower(),
            self.latest_processed_name.lower(),
            "latest_overlay.jpg",
            "latest_lightburn_instructions.txt",
        } if keep_latest else {"latest_lightburn_instructions.txt"}
        removed = 0
        for p in self.output_dir.iterdir():
            if not p.is_file():
                continue
            low = p.name.lower()
            if low in keep:
                continue
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            try:
                p.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    def _write_dpi_metadata(self, final_path: Path) -> None:
        try:
            dpi = self._dpi()
            with Image.open(final_path) as image:
                image.save(final_path, dpi=(dpi, dpi))
            self.log.info("[CAMERA] DPI metadata written: %s", dpi)
        except Exception as exc:
            self.log.warning("[CAMERA] Failed to write DPI metadata: %s", exc)

    def _camera_display_path(self, path: Path) -> str:
        return f"{self.output_dir.name}/{path.name}"

    def _parse_deskew_source_points(self, source_points: Any) -> list[list[float]]:
        if not isinstance(source_points, list) or len(source_points) != 4:
            raise CameraCaptureError("deskew.source_points must contain exactly 4 [x,y] points")
        parsed: list[list[float]] = []
        for point in source_points:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise CameraCaptureError("each deskew.source_points entry must be [x,y]")
            parsed.append([float(point[0]), float(point[1])])
        return parsed

    def _parse_deskew_output_size(self, output_size: Any, default: tuple[int, int] | None = None) -> tuple[int, int]:
        if not isinstance(output_size, (list, tuple)) or len(output_size) != 2:
            if default is not None:
                return default
            raise CameraCaptureError("deskew.output_size must be [width,height]")
        width = int(output_size[0])
        height = int(output_size[1])
        if width <= 0 or height <= 0:
            raise CameraCaptureError("deskew.output_size values must be > 0")
        return width, height

    def list_snapshots(self, limit: int = 100) -> list[dict[str, Any]]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, Any]] = []
        candidates: list[Path] = []
        if not self.save_history:
            for n in [self.latest_processed_name, self.latest_raw_name]:
                p = self.output_dir / n
                if p.exists():
                    candidates.append(p)
        else:
            candidates = sorted(self.output_dir.glob("*.jpg"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]
        for p in candidates:
            s = p.stat()
            is_raw = p.name.lower() == self.latest_raw_name.lower() or p.name.lower().endswith("_raw.jpg")
            rows.append(
                {
                    "name": p.name,
                    "size_bytes": s.st_size,
                    "modified": s.st_mtime,
                    "type": "raw" if is_raw else "processed",
                    "is_latest": p.name.lower() in {self.latest_processed_name.lower(), self.latest_raw_name.lower()},
                    "url": f"/api/snapshots/open/{p.name}",
                    "download_url": f"/api/snapshots/download/{p.name}",
                }
            )
        return rows

    def safe_snapshot_path(self, filename: str) -> Path:
        p = (self.output_dir / filename).resolve()
        if self.output_dir not in p.parents:
            raise CameraCaptureError("invalid snapshot path")
        if not p.exists():
            raise CameraCaptureError("snapshot not found")
        return p

    def config_status(self) -> dict[str, Any]:
        self._reload_camera_config()
        deskew = self.camera.get("deskew", {}) if isinstance(self.camera.get("deskew"), dict) else {}
        post = self.camera.get("postprocess", {}) if isinstance(self.camera.get("postprocess"), dict) else {}
        points = deskew.get("source_points", []) if isinstance(deskew.get("source_points", []), list) else []
        output_size = deskew.get("output_size", [1200, 1200])
        final_size = post.get("final_size", [1200, 1200])
        latest_raw = self.output_dir / self.latest_raw_name
        latest = self.output_dir / self.latest_processed_name
        return {
            "deskew_enabled": bool(deskew.get("enabled", False)),
            "source_points_count": len(points),
            "source_points": points,
            "output_size": output_size,
            "postprocess_enabled": bool(post.get("enabled", False)),
            "final_size": final_size,
            "latest_raw_exists": latest_raw.exists(),
            "latest_exists": latest.exists(),
        }


def mjpeg_generator(rtsp_url: str, reconnect_seconds: float = 5.0) -> Iterator[bytes]:
    delay = max(1.0, float(reconnect_seconds))
    while True:
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            frame = offline_frame_jpeg("Camera stream unavailable")
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(delay)
            continue
        try:
            while True:
                ok, img = cap.read()
                if not ok or img is None:
                    break
                ok_enc, buf = cv2.imencode(".jpg", img)
                if not ok_enc:
                    continue
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + bytes(buf) + b"\r\n"
        finally:
            cap.release()
        frame = offline_frame_jpeg("Reconnecting camera...")
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(delay)
