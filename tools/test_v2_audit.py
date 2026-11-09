"""V2 release regressions. Temporary files and fixture frames only; no hardware/network."""
import ast
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from camera_manager import CameraCaptureError, CameraManager, SharedCameraStream, _open_video_capture_with_rtsp_transport, mask_camera_url
from job_manager import JobManager
from tools import prepare_environment
from platform_utils import open_dashboard_when_ready


def functions(*names):
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8-sig"))
    return ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])


class TemporaryTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def camera(self, cleanup=True):
        return CameraManager({"camera": {"enabled": True, "cleanup_on_capture": cleanup,
            "overlay_alignment": {"enabled": False}, "postprocess": {"enabled": False}}}, self.root)

    @staticmethod
    def jpeg():
        file = io.BytesIO()
        Image.new("RGB", (32, 24), "green").save(file, format="JPEG")
        return file.getvalue()


class SnapshotTests(TemporaryTest):
    def test_failed_capture_preserves_last_good_images_and_history(self):
        camera = self.camera()
        for name in ("latest.jpg", "latest_raw.jpg", "older.jpg"):
            (camera.output_dir / name).write_bytes(b"previous")
        with patch.object(camera, "_capture_bytes_with_source", side_effect=CameraCaptureError("offline")):
            with self.assertRaises(CameraCaptureError):
                camera.capture()
        self.assertTrue(all(p.read_bytes() == b"previous" for p in camera.output_dir.iterdir()))

    def test_failed_processing_never_publishes_partial_images(self):
        camera = self.camera()
        camera.latest_path.write_bytes(b"previous final")
        camera.latest_raw_path.write_bytes(b"previous raw")
        with patch.object(camera, "_capture_bytes_with_source", return_value=(self.jpeg(), "fixture")), \
             patch.object(camera, "_create_corrected_from_raw", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                camera.capture()
        self.assertEqual(camera.latest_path.read_bytes(), b"previous final")
        self.assertEqual(camera.latest_raw_path.read_bytes(), b"previous raw")
        self.assertFalse(list(camera.output_dir.glob(".snapshot-*")))

    def test_cleanup_runs_only_after_success_and_respects_disable(self):
        camera = self.camera(cleanup=False)
        old = camera.output_dir / "older.jpg"
        old.write_bytes(b"keep until success")
        with patch.object(camera, "_capture_bytes_with_source", return_value=(self.jpeg(), "fixture")):
            camera.capture()
            self.assertTrue(old.exists())
            camera.cleanup_on_capture = True
            camera.capture()
        self.assertFalse(old.exists())
        for file in (camera.latest_path, camera.latest_raw_path):
            with Image.open(file) as image:
                image.verify()


class ImportTests(TemporaryTest):
    def test_parallel_same_name_imports_are_distinct_and_complete(self):
        manager = JobManager(self.root, {})
        contents = [f"M3 S10\nG1 X{n+1} Y10\nM5\n".encode() for n in range(16)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(lambda data: manager.import_uploaded_bytes("same.gc", data), contents))
        self.assertEqual(len({r["name"] for r in rows}), 16)
        self.assertEqual({p.read_bytes() for p in manager.imported_dir.glob("*.gc")}, set(contents))
        self.assertFalse(list(manager.imported_dir.glob("*.tmp")))

    def test_watched_file_changed_during_copy_is_not_published_or_removed(self):
        manager = JobManager(self.root, {})
        file = manager.watched_dir / "changed.gc"
        file.write_bytes(b"M3 S10\nG1 X10 Y10\nM5\n")
        with patch("job_manager.time.sleep"), patch("job_manager.shutil.copy2", side_effect=lambda src, dst: Path(dst).write_bytes(b"changed")):
            self.assertIsNone(manager._import_watched_file(file))
        self.assertTrue(file.exists())
        self.assertEqual(list(manager.imported_dir.iterdir()), [])


class CameraHandoffTests(TemporaryTest):
    def test_popout_handoff_shares_reader_and_timelapse_uses_live_frames(self):
        camera = self.camera()
        hub = SharedCameraStream(idle_seconds=.03)
        self.addCleanup(hub.close)
        closed = threading.Event()
        opened = []
        jpeg = self.jpeg()
        def factory(stop):
            opened.append(1)
            try:
                while not stop.is_set():
                    camera.update_live_frame(jpeg)
                    yield jpeg
                    stop.wait(.005)
            finally:
                closed.set()
        dashboard = hub.subscribe(("fixture-camera",), factory)
        popout = hub.subscribe(("fixture-camera",), factory)
        next(dashboard)
        next(popout)
        dashboard.close()
        next(popout)
        with patch.object(camera, "_capture_ffmpeg", side_effect=AssertionError("Must not open a second RTSP reader")):
            target = self.root / "session" / "frame.jpg"
            camera.capture_timelapse_frame_to(target, source="raw")
            with Image.open(target) as image:
                image.verify()
        self.assertEqual(len(opened), 1)
        self.assertFalse(closed.is_set())
        popout.close()
        # Closing/reopening a viewer within the grace period keeps the recorder cache warm.
        restored = hub.subscribe(("fixture-camera",), factory)
        next(restored)
        self.assertEqual(len(opened), 1)
        restored.close()
        self.assertTrue(closed.wait(2))

    def test_unconsumed_stream_does_not_start_reader(self):
        hub = SharedCameraStream()
        factory = Mock()
        stream = hub.subscribe(("fixture",), factory)
        stream.close()
        factory.assert_not_called()
        self.assertEqual(hub._sources, {})

    def test_rtsp_open_and_read_have_bounded_timeouts(self):
        with patch("camera_manager.cv2.VideoCapture") as capture:
            _open_video_capture_with_rtsp_transport("rtsp://camera.test/stream", "tcp")
        options = capture.call_args.args[2]
        self.assertEqual(options[1::2], [5000, 5000])

    def test_timelapse_error_clears_after_a_successful_retry(self):
        state = {"active": True, "session_dir": str(self.root / "session")}
        camera = Mock()
        camera.capture_timelapse_frame_to.side_effect = [RuntimeError("handoff gap"), None]
        stop = Mock()
        stop.is_set.side_effect = [False, False, True]
        stop.wait.return_value = False
        ns = {"timelapse_state": state, "timelapse_lock": threading.RLock(), "timelapse_stop_event": stop,
              "timelapse_capture_lock": threading.RLock(), "Path": Path, "time": time, "camera": camera,
              "console": Mock(), "_set_camera_check_result": Mock(), "_timelapse_output_dir": lambda: self.root}
        exec(compile(functions("_timelapse_worker"), "app.py", "exec"), ns)
        ns["_timelapse_worker"]()
        self.assertEqual(camera.capture_timelapse_frame_to.call_count, 2)
        self.assertEqual(state["error"], "")
        self.assertEqual(state["snapshot_count"], 1)


class RequestTests(unittest.TestCase):
    def test_one_air_off_click_cannot_be_undone_by_cached_on_status(self):
        ns = {"air_pump_state": {}, "time": time, "math": __import__("math"),
              "app_state_lock": threading.RLock(), "console": Mock()}
        exec(compile(functions("_set_air_pump_state", "_track_air_pump_from_accessory_state"), "app.py", "exec"), ns)
        track = ns["_track_air_pump_from_accessory_state"]
        before = time.time()
        track("F", before)
        self.assertEqual(ns["air_pump_state"]["state"], "on")
        ns["_set_air_pump_state"]("off", "command")
        track("F", before)  # Dashboard refreshed before the post-M9 status arrived.
        self.assertEqual(ns["air_pump_state"]["state"], "off")
        track("", time.time() + .01)
        self.assertEqual(ns["air_pump_state"]["state"], "off")
        self.assertEqual(ns["air_pump_state"]["source"], "accessory_state")
        track("F", before)
        self.assertEqual(ns["air_pump_state"]["state"], "off")

    def test_local_debug_guard_does_not_trust_spoofed_host(self):
        app = Flask(__name__)
        ns = {"request": request}
        exec(compile(functions("_is_local_request"), "app.py", "exec"), ns)
        with app.test_request_context("/", base_url="http://localhost", environ_base={"REMOTE_ADDR": "203.0.113.5"}):
            self.assertFalse(ns["_is_local_request"]())
        with app.test_request_context("/", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            self.assertTrue(ns["_is_local_request"]())

    def test_malformed_camera_port_does_not_crash_status_or_leak_credentials(self):
        self.assertEqual(mask_camera_url("rtsp://USERNAME:PASSWORD@camera.test:bad/stream"), "")
        self.assertEqual(mask_camera_url("rtsp://USERNAME:PASSWORD@[::1]:554/stream"), "rtsp://****:****@[::1]:554/stream")

    def test_nonobject_or_invalid_json_blocked_before_action(self):
        app = Flask(__name__)
        ns = {"app": app, "request": request, "jsonify": jsonify, "console": Mock()}
        exec(compile(functions("guard_state_changing_requests"), "app.py", "exec"), ns)
        action = Mock(return_value={"ok": True})
        app.add_url_rule("/action", endpoint="action", view_func=lambda: action(), methods=["POST"])
        client = app.test_client()
        for body in ("[]", "null", "false", '"text"', "{broken"):
            response = client.post("/action", data=body, content_type="application/json", headers={"X-Ray5-Pilot-Request": "1"})
            self.assertEqual(response.status_code, 400)
        action.assert_not_called()
        self.assertEqual(client.post("/action", json={}, headers={"X-Ray5-Pilot-Request": "1"}).status_code, 200)

    def test_invalid_imported_frame_numbers_are_not_route_500s(self):
        app = Flask(__name__)
        ray5 = Mock()
        ns = {"app": app, "Any": object, "request": request, "jsonify": jsonify, "cfg": {},
              "ray5": ray5, "jobs": Mock(), "console": Mock(), "_require_ray5_configured": lambda: None}
        exec(compile(functions("api_jobs_frame"), "app.py", "exec"), ns)
        for body in ({"feed": "bad"}, {"margin": None}):
            self.assertEqual(app.test_client().post("/api/jobs/frame", json=body).status_code, 400)
        ray5.send_gcode.assert_not_called()


class SetupTests(TemporaryTest):
    def test_browser_opens_once_at_configured_port_only_after_ready(self):
        response = Mock(status=200)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.side_effect = [OSError("not ready"), response]
        with patch("platform_utils.urlrequest.build_opener", return_value=opener), \
             patch("platform_utils.webbrowser.open", return_value=True) as browser, patch("platform_utils.time.sleep"):
            self.assertTrue(open_dashboard_when_ready("0.0.0.0", 19050))
        browser.assert_called_once_with("http://127.0.0.1:19050/", new=2)
        self.assertEqual(opener.open.call_count, 2)

    def test_first_setup_installs_then_cached_launch_is_offline(self):
        (self.root / "requirements.txt").write_text("Flask>=3,<4\n")
        runner = Mock(return_value=Mock(returncode=0))
        state = self.root / "venv"
        with patch.object(prepare_environment, "signature", return_value={"packages": {"Flask": "3"}, "hash": "first"}):
            self.assertTrue(prepare_environment.prepare(self.root, state, runner))
            self.assertTrue(any("pip" in c.args[0] for c in runner.call_args_list))
            runner.reset_mock()
            self.assertFalse(prepare_environment.prepare(self.root, state, runner))
            self.assertEqual(len(runner.call_args_list), 1)
            self.assertNotIn("pip", runner.call_args.args[0])
        with patch.object(prepare_environment, "signature", return_value={"packages": {"Flask": "3"}, "hash": "changed"}):
            self.assertTrue(prepare_environment.prepare(self.root, state, runner))

    def test_install_failure_never_marks_environment_ready(self):
        (self.root / "requirements.txt").write_text("Flask>=3,<4\n")
        runner = Mock(side_effect=subprocess.CalledProcessError(1, "pip"))
        with self.assertRaises(subprocess.CalledProcessError):
            prepare_environment.prepare(self.root, self.root / "venv", runner)
        self.assertFalse((self.root / "venv/.ray5_pilot_dependencies.json").exists())


if __name__ == "__main__":
    unittest.main()
