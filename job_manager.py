from __future__ import annotations

import hashlib
import math
import re
import shutil
import time
from pathlib import Path
from typing import Any

from gcode_safety import validate_laser_gcode_safety


class JobManager:
    def __init__(self, base_dir: Path, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        jobs = cfg.get("jobs", {})
        self.imported_dir = (base_dir / str(jobs.get("imported_jobs_dir") or jobs.get("imported_jobs_folder", "imported_jobs"))).resolve()
        self.watched_dir = (base_dir / str(jobs.get("watched_gcode_dir") or jobs.get("watched_folder", "watched_gcode"))).resolve()
        self.rejected_dir = (base_dir / "rejected_jobs").resolve()
        self.delete_watched_after_import = bool(jobs.get("delete_watched_after_import", True))
        self.allowed = {str(x).lower() for x in jobs.get("allowed_extensions", [".gcode", ".nc", ".gc"])}
        self.imported_dir.mkdir(parents=True, exist_ok=True)
        self.watched_dir.mkdir(parents=True, exist_ok=True)
        self.rejected_dir.mkdir(parents=True, exist_ok=True)
        self._watch_state: dict[str, tuple[int, int]] = {}
        self._imported_signatures: set[tuple[str, int, str]] = set()
        self._currently_importing: set[str] = set()
        limits = cfg.get("limits", {}) if isinstance(cfg.get("limits"), dict) else {}
        self.max_upload_bytes = int(float(limits.get("max_gcode_upload_mb", 50)) * 1024 * 1024)
        self.max_bounds_parse_bytes = int(float(limits.get("max_bounds_parse_mb", 50)) * 1024 * 1024)

    def validate_gcode_bytes(self, filename: str, content: bytes) -> dict[str, Any]:
        return validate_laser_gcode_safety(content, filename, self.cfg)

    def validate_gcode_path(self, path: Path) -> dict[str, Any]:
        return validate_laser_gcode_safety(path, path.name, self.cfg)

    def safe_imported_path(self, filename: str) -> Path:
        p = (self.imported_dir / str(filename or "")).resolve()
        if self.imported_dir not in p.parents:
            raise ValueError("Invalid imported job path")
        return p

    def _safe_target(self, name: str) -> Path:
        base = Path(name).name
        stem = Path(base).stem
        suffix = Path(base).suffix
        candidate = self.imported_dir / base
        if not candidate.exists():
            return candidate
        idx = 1
        while True:
            c = self.imported_dir / f"{stem}_{idx}{suffix}"
            if not c.exists():
                return c
            idx += 1

    def _file_sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def list_jobs(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in sorted(self.imported_dir.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_file() or p.suffix.lower() not in self.allowed:
                continue
            s = p.stat()
            bounds = self.parse_bounds_path(p)
            out.append(
                {
                    "name": p.name,
                    "filename": p.name,
                    "size_bytes": s.st_size,
                    "size": s.st_size,
                    "modified": s.st_mtime,
                    "bounds": bounds,
                    "bounds_warning": (
                        "Bounds unknown"
                        if not bounds
                        else ("; ".join(bounds.get("warnings", [])) if bounds.get("warnings") else None)
                    ),
                }
            )
        return out

    def import_file(self, src_path: Path) -> dict[str, Any]:
        if src_path.suffix.lower() not in self.allowed:
            raise ValueError("File extension not allowed")
        if src_path.stat().st_size > self.max_upload_bytes:
            raise ValueError(f"File exceeds upload limit ({self.max_upload_bytes} bytes)")
        safety = self.validate_gcode_path(src_path)
        if not safety.get("ok"):
            raise ValueError(
                f"Blocked: this looks like 3D printer G-code, not laser G-code. "
                f"reason={safety.get('reason','')} matches={','.join(safety.get('matches',[]))}"
            )
        target = self._safe_target(src_path.name)
        target.write_bytes(src_path.read_bytes())
        s = target.stat()
        self._imported_signatures.add((target.name.lower(), s.st_size, self._file_sha256(target)))
        return {
            "name": target.name,
            "filename": target.name,
            "size_bytes": s.st_size,
            "modified": s.st_mtime,
            "bounds": self.parse_bounds_path(target),
        }

    def import_uploaded_bytes(self, filename: str, content: bytes) -> dict[str, Any]:
        ext = Path(filename).suffix.lower()
        if ext not in self.allowed:
            raise ValueError("File extension not allowed")
        if len(content) > self.max_upload_bytes:
            raise ValueError(f"File exceeds upload limit ({self.max_upload_bytes} bytes)")
        safety = self.validate_gcode_bytes(filename, content)
        if not safety.get("ok"):
            raise ValueError(
                f"Blocked: this looks like 3D printer G-code, not laser G-code. "
                f"reason={safety.get('reason','')} matches={','.join(safety.get('matches',[]))}"
            )
        target = self._safe_target(filename)
        target.write_bytes(content)
        s = target.stat()
        self._imported_signatures.add((target.name.lower(), s.st_size, self._file_sha256(target)))
        return {
            "name": target.name,
            "filename": target.name,
            "size_bytes": s.st_size,
            "modified": s.st_mtime,
            "bounds": self.parse_bounds_path(target),
        }

    def poll_watched_imports(self) -> list[dict[str, Any]]:
        imported: list[dict[str, Any]] = []
        if self.imported_dir.resolve() == self.watched_dir.resolve():
            raise RuntimeError("watched_gcode_dir and imported_jobs_dir cannot be the same folder")
        self.watched_dir.mkdir(parents=True, exist_ok=True)
        for p in sorted(self.watched_dir.glob("*")):
            if not p.is_file() or p.suffix.lower() not in self.allowed:
                continue
            key = str(p.resolve()).lower()
            if key in self._currently_importing:
                continue
            try:
                stat = p.stat()
            except OSError:
                continue
            if stat.st_size <= 0:
                continue
            stamp = int(stat.st_mtime)
            current = (stat.st_size, stamp)
            previous = self._watch_state.get(key)
            self._watch_state[key] = current
            if previous is None or previous != current:
                continue
            self._currently_importing.add(key)
            try:
                meta = self._import_watched_file(p)
                if meta:
                    imported.append(meta)
            finally:
                self._currently_importing.discard(key)
        return imported

    def _import_watched_file(self, src: Path) -> dict[str, Any] | None:
        if src.suffix.lower() not in self.allowed:
            return None
        if not src.exists():
            return None
        # size-stability guard for files still being written
        try:
            s1 = src.stat().st_size
            if s1 <= 0:
                return None
            time.sleep(0.2)
            s2 = src.stat().st_size
            if s1 != s2 or s2 <= 0:
                return None
        except OSError:
            return None

        try:
            sha = self._file_sha256(src)
        except OSError as exc:
            # File may still be writing/locked; retry next poll cycle.
            print(f"[WATCHER] Hash read deferred for {src.name}: {exc}")
            return None
        except Exception as exc:
            print(f"[WATCHER] Hash read failed for {src.name}: {exc}")
            return None

        target_primary = (self.imported_dir / Path(src.name).name).resolve()
        if self.imported_dir not in target_primary.parents:
            return None
        target = target_primary
        if target_primary.exists():
            try:
                existing_sig = (target_primary.name.lower(), target_primary.stat().st_size, self._file_sha256(target_primary))
            except OSError:
                existing_sig = None
            src_sig = (target_primary.name.lower(), s2, sha)
            if existing_sig is not None and src_sig == existing_sig:
                # Same watched content already imported to same target file; skip.
                return None
            target = self._safe_target(src.name)

        if src.stat().st_size > self.max_upload_bytes:
            return None
        safety = self.validate_gcode_path(src)
        if not safety.get("ok"):
            rej_target = self._safe_rejected_target(src.name)
            try:
                shutil.move(str(src), str(rej_target))
            except OSError:
                pass
            return {
                "name": src.name,
                "filename": src.name,
                "rejected": True,
                "detected_type": safety.get("detected_type", "3d_printer"),
                "reason": safety.get("reason", ""),
                "matches": safety.get("matches", []),
                "rejected_path": str(rej_target),
            }
        shutil.copy2(src, target)
        if not target.exists() or target.stat().st_size <= 0:
            return None
        if self.delete_watched_after_import:
            try:
                src.unlink()
            except OSError:
                pass
        s = target.stat()
        try:
            imported_sha = self._file_sha256(target)
            self._imported_signatures.add((target.name.lower(), s.st_size, imported_sha))
        except Exception:
            # If hashing imported copy fails unexpectedly, keep import success path.
            pass
        return {
            "name": target.name,
            "filename": target.name,
            "size_bytes": s.st_size,
            "modified": s.st_mtime,
            "bounds": self.parse_bounds_path(target),
            "source_name": src.name,
            "removed_source": self.delete_watched_after_import,
        }

    def _safe_rejected_target(self, name: str) -> Path:
        base = Path(name).name
        stem = Path(base).stem
        suffix = Path(base).suffix
        candidate = self.rejected_dir / base
        if not candidate.exists():
            return candidate
        stamp = time.strftime("%Y%m%d_%H%M%S")
        idx = 1
        while True:
            c = self.rejected_dir / f"{stem}_{stamp}_{idx:02d}{suffix}"
            if not c.exists():
                return c
            idx += 1

    def delete_job(self, filename: str) -> None:
        p = self.safe_imported_path(filename)
        if p.exists():
            p.unlink()

    def parse_bounds(self, filename: str) -> dict[str, Any] | None:
        p = self.safe_imported_path(filename)
        if not p.exists():
            return None
        return self.parse_bounds_path(p)

    def parse_bounds_path(self, p: Path) -> dict[str, Any] | None:
        try:
            if p.stat().st_size > self.max_bounds_parse_bytes:
                return None
        except OSError:
            return None
        text = p.read_text(encoding="utf-8", errors="ignore")
        comment_bounds = self._parse_lightburn_bounds_comment(text)
        if comment_bounds is not None:
            return comment_bounds

        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        x = y = 0.0
        g92_offset_x = 0.0
        g92_offset_y = 0.0
        absolute = True
        motion = re.compile(r"([A-Z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", re.IGNORECASE)
        finish_marker_seen = False
        laser_off_mode = False
        warnings: list[str] = []
        for line in text.splitlines():
            raw = line.strip()
            low = raw.lower()
            if raw.startswith(";"):
                if any(tok in low for tok in ("return to user-defined finish", "return to finish", "finish position", "park", "parking", " end")):
                    finish_marker_seen = True
                continue
            if finish_marker_seen:
                continue
            clean = self._strip_comments(line).upper().strip()
            if not clean:
                continue
            if clean in {"M2", "M30"}:
                break
            g_match = re.search(r"\bG0*([0-9]+)\b", clean)
            g_num = int(g_match.group(1)) if g_match else None
            g_is_motion = g_num in {0, 1, 2, 3}
            g_is_arc = g_num in {2, 3}
            g_cw = g_num == 2

            if re.search(r"\bM5\b", clean) or re.search(r"\bM9\b", clean):
                laser_off_mode = True
            if re.search(r"\bS\s*0(?:\.0+)?\b", clean):
                laser_off_mode = True

            # Resume from laser-off travel mode when explicit laser-on power is set.
            if re.search(r"\bM[34]\b", clean):
                s_resume = re.search(r"\bS\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\b", clean)
                if s_resume:
                    try:
                        if float(s_resume.group(1)) > 0:
                            laser_off_mode = False
                    except ValueError:
                        pass
            if g_num in {1, 2, 3}:
                s_resume = re.search(r"\bS\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\b", clean)
                if s_resume:
                    try:
                        if float(s_resume.group(1)) > 0:
                            laser_off_mode = False
                    except ValueError:
                        pass

            if "G90" in clean:
                absolute = True
            if "G91" in clean:
                absolute = False
            tokens = {m.group(1).upper(): float(m.group(2)) for m in motion.finditer(clean)}
            g92_match = re.search(r"\bG\s*92(?:\.\d+)?\b", clean)
            if g92_match:
                # G92 remaps the current work coordinate without motion. Keep machine-space
                # tracking stable by updating offsets used for future absolute moves.
                if "X" in tokens:
                    g92_offset_x = x - tokens["X"]
                if "Y" in tokens:
                    g92_offset_y = y - tokens["Y"]
                continue
            if "X" not in tokens and "Y" not in tokens:
                continue
            if not g_is_motion:
                continue
            start_x, start_y = x, y
            nx, ny = x, y
            if absolute:
                if "X" in tokens:
                    nx = tokens["X"] + g92_offset_x
                if "Y" in tokens:
                    ny = tokens["Y"] + g92_offset_y
            else:
                if "X" in tokens:
                    nx = x + tokens["X"]
                if "Y" in tokens:
                    ny = y + tokens["Y"]
            if g_is_arc:
                if ("I" in tokens or "J" in tokens):
                    cx = start_x + float(tokens.get("I", 0.0))
                    cy = start_y + float(tokens.get("J", 0.0))
                    r = math.hypot(start_x - cx, start_y - cy)
                    if not laser_off_mode:
                        min_x, min_y, max_x, max_y = self._include_point(min_x, min_y, max_x, max_y, start_x, start_y)
                        min_x, min_y, max_x, max_y = self._include_point(min_x, min_y, max_x, max_y, nx, ny)
                        min_x, min_y, max_x, max_y = self._include_arc_extrema(
                            min_x, min_y, max_x, max_y, start_x, start_y, nx, ny, cx, cy, r, clockwise=g_cw
                        )
                else:
                    if "R" in tokens:
                        warn = "Arc bounds approximated; framing may be slightly inaccurate for this file."
                        if warn not in warnings:
                            warnings.append(warn)
                    if not laser_off_mode:
                        min_x, min_y, max_x, max_y = self._include_point(min_x, min_y, max_x, max_y, start_x, start_y)
                        min_x, min_y, max_x, max_y = self._include_point(min_x, min_y, max_x, max_y, nx, ny)
            else:
                if not laser_off_mode:
                    min_x, min_y, max_x, max_y = self._include_point(min_x, min_y, max_x, max_y, nx, ny)
            x, y = nx, ny

        if min_x == float("inf") or min_y == float("inf"):
            return None
        out: dict[str, Any] = {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y, "source": "motion_parse"}
        if warnings:
            out["warnings"] = warnings
        return out

    def _include_point(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
        px: float,
        py: float,
    ) -> tuple[float, float, float, float]:
        return min(min_x, px), min(min_y, py), max(max_x, px), max(max_y, py)

    def _include_arc_extrema(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        cx: float,
        cy: float,
        r: float,
        clockwise: bool,
    ) -> tuple[float, float, float, float]:
        start_a = self._norm_angle(math.atan2(start_y - cy, start_x - cx))
        end_a = self._norm_angle(math.atan2(end_y - cy, end_x - cx))
        for a in (0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0):
            if self._angle_on_sweep(a, start_a, end_a, clockwise):
                px = cx + r * math.cos(a)
                py = cy + r * math.sin(a)
                min_x, min_y, max_x, max_y = self._include_point(min_x, min_y, max_x, max_y, px, py)
        return min_x, min_y, max_x, max_y

    def _norm_angle(self, ang: float) -> float:
        two = 2.0 * math.pi
        out = ang % two
        if out < 0:
            out += two
        return out

    def _angle_on_sweep(self, test: float, start: float, end: float, clockwise: bool) -> bool:
        eps = 1e-9
        two = 2.0 * math.pi
        if clockwise:
            sweep = (start - end) % two
            dist = (start - test) % two
            return dist <= sweep + eps
        sweep = (end - start) % two
        dist = (test - start) % two
        return dist <= sweep + eps

    def _parse_lightburn_bounds_comment(self, text: str) -> dict[str, float] | None:
        pat = re.compile(
            r"Bounds:\s*X([-+]?\d+(?:\.\d+)?)\s*Y([-+]?\d+(?:\.\d+)?)\s*to\s*X([-+]?\d+(?:\.\d+)?)\s*Y([-+]?\d+(?:\.\d+)?)",
            re.IGNORECASE,
        )
        for line in text.splitlines():
            m = pat.search(line)
            if not m:
                continue
            x1, y1, x2, y2 = (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
            return {
                "min_x": min(x1, x2),
                "min_y": min(y1, y2),
                "max_x": max(x1, x2),
                "max_y": max(y1, y2),
                "source": "lightburn_bounds_comment",
            }
        return None

    def _strip_comments(self, line: str) -> str:
        no_paren = re.sub(r"\(.*?\)", "", line)
        if ";" in no_paren:
            no_paren = no_paren.split(";", 1)[0]
        return no_paren

    def frame_commands(self, filename: str, cfg: dict[str, Any], margin: float | None = None, feed: float | None = None) -> dict[str, Any]:
        b = self.parse_bounds(filename)
        if not b:
            raise ValueError("Could not determine XY bounds for this job.")
        framing = cfg.get("framing", {})
        machine = cfg.get("machine", {})

        margin_value = float(margin if margin is not None else framing.get("margin_mm", 2.0))
        feed_value = float(feed if feed is not None else framing.get("feedrate", 3000))
        validate_bounds = bool(framing.get("validate_bounds", True))
        clamp_to_machine = bool(framing.get("clamp_to_machine_area", False))
        force_laser_off = bool(framing.get("force_laser_off", True))
        min_x = float(machine.get("min_x", 0))
        min_y = float(machine.get("min_y", 0))
        max_x = float(machine.get("max_x", machine.get("bed_width_mm", 390)))
        max_y = float(machine.get("max_y", machine.get("bed_height_mm", 360)))

        job_min_x = float(b["min_x"])
        job_min_y = float(b["min_y"])
        job_max_x = float(b["max_x"])
        job_max_y = float(b["max_y"])
        requested_min_x = job_min_x - margin_value
        requested_min_y = job_min_y - margin_value
        requested_max_x = job_max_x + margin_value
        requested_max_y = job_max_y + margin_value

        job_outside = job_min_x < min_x or job_min_y < min_y or job_max_x > max_x or job_max_y > max_y
        if validate_bounds and job_outside:
            raise ValueError(
                f"Job bounds are outside machine area: X {job_min_x:.3f}..{job_max_x:.3f} "
                f"Y {job_min_y:.3f}..{job_max_y:.3f}"
            )

        safe_min_x = requested_min_x
        safe_min_y = requested_min_y
        safe_max_x = requested_max_x
        safe_max_y = requested_max_y
        requested_outside = safe_min_x < min_x or safe_min_y < min_y or safe_max_x > max_x or safe_max_y > max_y
        clamped = False
        if requested_outside:
            if not clamp_to_machine:
                raise ValueError(
                    f"Frame would move outside machine area: X {requested_min_x:.3f}..{requested_max_x:.3f} "
                    f"Y {requested_min_y:.3f}..{requested_max_y:.3f}"
                )
            clamped = True
            safe_min_x = max(min_x, safe_min_x)
            safe_min_y = max(min_y, safe_min_y)
            safe_max_x = min(max_x, safe_max_x)
            safe_max_y = min(max_y, safe_max_y)

        points = [
            (safe_min_x, safe_min_y),
            (safe_max_x, safe_min_y),
            (safe_max_x, safe_max_y),
            (safe_min_x, safe_max_y),
            (safe_min_x, safe_min_y),
        ]
        cmds = [
            "M5",
            "G21",
            "G90",
            f"G0 X{points[0][0]:.3f} Y{points[0][1]:.3f} F{feed_value:.0f}",
            f"G1 X{points[1][0]:.3f} Y{points[1][1]:.3f} F{feed_value:.0f}",
            f"G1 X{points[2][0]:.3f} Y{points[2][1]:.3f} F{feed_value:.0f}",
            f"G1 X{points[3][0]:.3f} Y{points[3][1]:.3f} F{feed_value:.0f}",
            f"G1 X{points[4][0]:.3f} Y{points[4][1]:.3f} F{feed_value:.0f}",
            "M5",
        ]
        return {
            "commands": cmds,
            "points": points,
            "force_laser_off": force_laser_off,
            "job_bounds": {"min_x": job_min_x, "min_y": job_min_y, "max_x": job_max_x, "max_y": job_max_y},
            "requested_frame_bounds": {
                "min_x": requested_min_x,
                "min_y": requested_min_y,
                "max_x": requested_max_x,
                "max_y": requested_max_y,
            },
            "safe_frame_bounds": {"min_x": safe_min_x, "min_y": safe_min_y, "max_x": safe_max_x, "max_y": safe_max_y},
            "clamped": clamped,
            "bounds_source": str(b.get("source", "unknown")),
            "margin_mm": margin_value,
            "feedrate": feed_value,
            "machine_bounds": {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y},
        }
