"""Offline audit regressions. All files are temporary; all machine I/O is mocked."""
import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camera_manager import CameraCaptureError, CameraManager, mjpeg_generator
from config_manager import ConfigManager, DEFAULT_CONFIG
from gcode_safety import _safe_text_lines, validate_laser_gcode_safety
from job_manager import JobManager
from flask import Flask, jsonify, request


LASER = b"M3 S10\nG1 X10 Y10\nG1 X20 Y20\nM5\n"


class TemporaryFiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)


class JobAuditTests(TemporaryFiles):
    def manager(self, **options):
        return JobManager(self.root, {"jobs": options})

    def test_unchanged_bounds_parsed_once_and_returned_as_independent_values(self):
        manager = self.manager()
        file = manager.imported_dir / "job.gc"
        file.write_bytes(LASER)
        with patch.object(manager, "_parse_bounds_uncached", wraps=manager._parse_bounds_uncached) as parse:
            first = manager.list_jobs()
            first[0]["bounds"]["min_x"] = -999
            for _ in range(5):
                self.assertNotEqual(manager.list_jobs()[0]["bounds"]["min_x"], -999)
            self.assertEqual(parse.call_count, 1)

    def test_same_size_rewrite_invalidates_bounds(self):
        manager = self.manager()
        file = manager.imported_dir / "job.gc"
        file.write_bytes(LASER)
        before = manager.parse_bounds_path(file)
        file.write_bytes(LASER.replace(b"X20", b"X30"))
        stat = file.stat()
        os.utime(file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
        self.assertNotEqual(before["max_x"], manager.parse_bounds_path(file)["max_x"])
        file.unlink()
        self.assertIsNone(manager.parse_bounds_path(file))
        self.assertEqual(manager.list_jobs(), [])

    def test_bounds_cache_is_bounded(self):
        manager = self.manager()
        for index in range(260):
            file = manager.imported_dir / f"{index}.gc"
            file.write_bytes(LASER)
            manager.parse_bounds_path(file)
        self.assertEqual(len(manager._bounds_cache), 256)

    def test_unknown_bounds_are_cached(self):
        manager = self.manager()
        file = manager.imported_dir / "unknown.gc"
        file.write_bytes(b"M5\n")
        with patch.object(manager, "_parse_bounds_uncached", wraps=manager._parse_bounds_uncached) as parse:
            self.assertIsNone(manager.parse_bounds_path(file))
            self.assertIsNone(manager.parse_bounds_path(file))
            self.assertEqual(parse.call_count, 1)

    def test_watcher_does_not_rehash_unchanged_retained_files(self):
        manager = self.manager(delete_watched_after_import=False)
        source = manager.watched_dir / "watched.gc"
        source.write_bytes(LASER)
        with patch("job_manager.time.sleep"), patch.object(manager, "_file_sha256", wraps=manager._file_sha256) as hashed:
            self.assertEqual(manager.poll_watched_imports(), [])
            self.assertEqual(len(manager.poll_watched_imports()), 1)
            count = hashed.call_count
            for _ in range(5):
                self.assertEqual(manager.poll_watched_imports(), [])
            self.assertEqual(hashed.call_count, count)
            (manager.imported_dir / "watched.gc").unlink()
            self.assertEqual(len(manager.poll_watched_imports()), 1)
            source.unlink()
            manager.poll_watched_imports()
            self.assertEqual(manager._watch_state, {})
            self.assertEqual(manager._watch_completed, {})

    def test_watcher_notices_fast_same_size_updates(self):
        manager = self.manager(delete_watched_after_import=False)
        source = manager.watched_dir / "watched.gc"
        source.write_bytes(LASER)
        with patch("job_manager.time.sleep"):
            manager.poll_watched_imports()
            manager.poll_watched_imports()
            source.write_bytes(LASER.replace(b"X20", b"X30"))
            stat = source.stat()
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
            self.assertEqual(manager.poll_watched_imports(), [])
            self.assertEqual(len(manager.poll_watched_imports()), 1)

    def test_oversize_watched_file_not_hashed(self):
        manager = self.manager()
        manager.max_upload_bytes = 5
        (manager.watched_dir / "oversize.gc").write_bytes(LASER)
        with patch.object(manager, "_file_sha256") as hashed:
            manager.poll_watched_imports()
            manager.poll_watched_imports()
            hashed.assert_not_called()

    def test_framing_rejects_nonfinite_and_invalid_inputs(self):
        manager = self.manager()
        file = manager.imported_dir / "job.gc"
        file.write_bytes(LASER)
        for options in ({"feed":math.nan}, {"feed":math.inf}, {"feed":0}, {"margin":math.nan}, {"margin":-2}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                manager.frame_commands(file.name, {}, **options)
        self.assertEqual(manager.frame_commands(file.name, {}, feed=700, margin=0)["commands"][0], "M5")

    def test_modal_xy_moves_and_inches_have_correct_bounds(self):
        manager = self.manager()
        file = manager.imported_dir / "modal.gc"
        file.write_bytes(b"G20\nM3 S10\nG1 X1 Y1\nX2 Y3\nM5\n")
        bounds = manager.parse_bounds_path(file)
        self.assertAlmostEqual(bounds["max_x"], 50.8)
        self.assertAlmostEqual(bounds["max_y"], 76.2)

    def test_coolant_off_does_not_truncate_laser_bounds(self):
        manager = self.manager()
        file = manager.imported_dir / "coolant.gc"
        file.write_bytes(b"M3 S10\nG1 X10 Y10\nM9\nG1 X30 Y40\nM5\n")
        self.assertEqual(manager.parse_bounds_path(file)["max_y"],40)

    def test_arc_center_mode_does_not_change_relative_distance_mode(self):
        manager = self.manager()
        file = manager.imported_dir / "relative.gc"
        file.write_bytes(b"G91\nM3 S10\nG1 X10 Y10\nG90.1\nG1 X20 Y20\nM5\n")
        self.assertEqual(manager.parse_bounds_path(file)["max_x"],30)


class SafetyAuditTests(TemporaryFiles):
    def test_scan_stops_reading_after_configured_lines(self):
        stream = io.StringIO("M5\nG1 X1 Y1\nM104 S200\n")
        stream.close = Mock()
        with patch.object(Path, "open", return_value=stream), patch.object(Path, "read_text", side_effect=AssertionError("Must not read whole file")):
            self.assertEqual(len(_safe_text_lines(self.root / "huge.gc", 2)), 2)
            self.assertLess(stream.tell(), len(stream.getvalue()))

    def test_single_or_compact_extrusion_rejected(self):
        for line in (b"G1 E1", b"G1X10Y10E1", b"g01 x10 e.5", b"N10 G1X10E-1", b"G0X10E1"):
            with self.subTest(line=line):
                self.assertFalse(validate_laser_gcode_safety(line, "test.gc", {})["ok"])

    def test_extrusion_text_in_comments_not_motion(self):
        for line in (b"M3 S10\nG1 X10 Y10 ; E1", b"M3 S10\nG1 X10 Y10 (E1)"):
            self.assertTrue(validate_laser_gcode_safety(line, "test.gc", {})["ok"])

    def test_bytes_scan_limit_and_line_endings(self):
        config = {"safety":{"gcode_safety_scan_lines":2}}
        for separator in (b"\n", b"\r\n", b"\r"):
            content = separator.join([b"M5", b"G1 X1 Y1", b"M104 S200"])
            self.assertTrue(validate_laser_gcode_safety(content, "test.gc", config)["ok"])


class ConfigAuditTests(TemporaryFiles):
    def test_loaded_defaults_not_shared_with_other_loads(self):
        manager = ConfigManager(self.root)
        before = deepcopy(DEFAULT_CONFIG)
        loaded = manager.load()
        loaded["camera"]["deskew"]["source_points"].append([1,2])
        loaded["jobs"]["allowed_extensions"].append(".bad")
        self.assertEqual(DEFAULT_CONFIG, before)
        self.assertEqual(manager.load(), before)

    def test_concurrent_partial_saves_preserve_all_updates(self):
        manager = ConfigManager(self.root)
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(lambda index: manager.save({"audit":{str(index):index}}), range(30)))
        self.assertEqual(len(manager.load()["audit"]), 30)
        self.assertEqual(list(self.root.glob("*.tmp")), [])
        json.loads(manager.config_path.read_text())

    def test_non_object_config_does_not_crash_load(self):
        manager = ConfigManager(self.root)
        manager.config_path.write_text("[]")
        self.assertEqual(manager.load(), DEFAULT_CONFIG)

    def test_bad_numbers_rejected_without_replacing_config(self):
        manager = ConfigManager(self.root)
        manager.save({"audit":"original"})
        original = manager.config_path.read_bytes()
        for value in (math.nan, math.inf, -math.inf):
            config = deepcopy(DEFAULT_CONFIG)
            config["machine"]["max_x"] = value
            self.assertFalse(manager.validate(config)[0])
            with self.assertRaises(ValueError):
                manager.save(config)
            self.assertEqual(manager.config_path.read_bytes(), original)

    def test_failed_replace_preserves_old_config_and_removes_temp(self):
        manager = ConfigManager(self.root)
        manager.save({"audit":"original"})
        original = manager.config_path.read_bytes()
        with patch("config_manager.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                manager.save({"audit":"new"})
        self.assertEqual(manager.config_path.read_bytes(), original)
        self.assertEqual(list(self.root.glob("*.tmp")), [])


class CameraAuditTests(TemporaryFiles):
    def manager(self, chunks, multipart=True):
        manager = CameraManager({}, self.root)
        response = Mock(ok=True, headers={"Content-Type":"multipart/x-mixed-replace" if multipart else "image/png"})
        response.iter_content.return_value = iter(chunks)
        response.content = property(lambda _: (_ for _ in ()).throw(AssertionError("Must not drain stream")))
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        manager.session.get = Mock(return_value=context)
        return manager, context

    def test_mjpeg_returns_first_frame_without_reading_forever(self):
        def chunks():
            yield b"--frame\r\n\xff"
            yield b"\xd8jpeg\xff"
            yield b"\xd9\r\n--next"
            raise AssertionError("Must stop after the first JPEG")
        manager, context = self.manager(chunks())
        self.assertEqual(manager._capture_http_snapshot("http://camera.test/stream"), b"\xff\xd8jpeg\xff\xd9")
        context.__exit__.assert_called_once()

    def test_plain_snapshot_and_incomplete_mjpeg_close_response(self):
        manager, context = self.manager([b"png1",b"png2"], multipart=False)
        self.assertEqual(manager._capture_http_snapshot("http://camera.test/snapshot"), b"png1png2")
        context.__exit__.assert_called_once()
        manager, context = self.manager([b"no image"])
        with self.assertRaises(CameraCaptureError):
            manager._capture_http_snapshot("http://camera.test/stream")
        context.__exit__.assert_called_once()

    def test_oversize_snapshot_is_bounded(self):
        manager, context = self.manager([b"a" * (21*1024*1024)], multipart=False)
        with self.assertRaisesRegex(CameraCaptureError, "20 MB"):
            manager._capture_http_snapshot("http://camera.test/snapshot")
        context.__exit__.assert_called_once()

    def test_failed_video_capture_released(self):
        cap = Mock()
        cap.isOpened.return_value = False
        with patch("camera_manager._open_video_capture_with_rtsp_transport", return_value=cap):
            stream = mjpeg_generator("rtsp://camera.test/stream")
            next(stream)
            stream.close()
        cap.release.assert_called_once()

    def test_zero_retention_keeps_history_and_latest_files(self):
        manager = CameraManager({"camera":{"save_history":True,"keep_last":0}}, self.root)
        for name in ("latest.jpg","latest_raw.jpg","ray5_bed_20260101_120000.jpg"):
            (manager.output_dir / name).write_bytes(b"image")
        manager._prune_old()
        self.assertEqual(len(manager.list_snapshots()),3)

    def test_retention_never_deletes_latest_even_with_matching_prefix(self):
        manager = CameraManager({"camera":{"save_history":True,"keep_last":1,"filename_prefix":"latest"}}, self.root)
        for name in ("latest.jpg","latest_raw.jpg","latest_20260101.jpg","latest_20260102.jpg"):
            (manager.output_dir / name).write_bytes(b"image")
        manager._prune_old()
        self.assertTrue(manager.latest_path.exists())
        self.assertTrue(manager.latest_raw_path.exists())
        self.assertEqual(len(manager.list_snapshots()),3)


class MoveAuditTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        self.ray5 = Mock()
        self.ray5.laser_off.return_value = {"ok":False,"message":"Error"}
        self.ray5.move.return_value = {"ok":True}
        self.ray5.send_gcode.return_value = {"ok":True}
        self.cfg = {"manual_controls":{"force_laser_off_before_move":True}}
        ns = {"app":app,"Any":object,"jsonify":jsonify,"request":request,"math":math,
              "cfg":self.cfg,"ray5":self.ray5,"console":Mock(),"_require_ray5_configured":lambda:None}
        tree = ast.parse((Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8-sig"))
        node = next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name == "api_move")
        exec(compile(ast.Module(body=[node],type_ignores=[]),"app.py","exec"),ns)
        self.client = app.test_client()

    def test_failed_laser_off_blocks_single_axis_and_diagonal_jog(self):
        for body in ({"axis":"x","distance":1}, {"dx":1,"dy":1}):
            response = self.client.post("/api/move",json=body)
            self.assertEqual(response.status_code,503)
            self.assertIn("laser-off",response.json["message"])
        self.ray5.move.assert_not_called()
        self.ray5.send_gcode.assert_not_called()

    def test_success_preserves_jog_behavior(self):
        self.ray5.laser_off.return_value = {"ok":True}
        self.assertTrue(self.client.post("/api/move",json={"axis":"x","distance":2,"feedrate":700}).json["ok"])
        self.ray5.move.assert_called_with(axis="x",distance=2,feedrate=700)
        self.assertTrue(self.client.post("/api/move",json={"dx":1,"dy":1,"feedrate":700}).json["ok"])
        self.ray5.send_gcode.assert_called_with("$J=G91 G21 X1.000 Y1.000 F700")

    def test_invalid_numbers_cannot_reach_machine(self):
        for body in ({"axis":"x","distance":"bad"},{"dx":"nan"},{"axis":"x","feedrate":0},{"dy":"inf"}):
            self.assertEqual(self.client.post("/api/move",json=body).status_code,400)
        self.ray5.laser_off.assert_not_called()
        self.ray5.move.assert_not_called()
        self.ray5.send_gcode.assert_not_called()


if __name__ == "__main__":
    unittest.main()
