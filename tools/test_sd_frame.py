"""Read-only SD download and laser-off framing regressions. Hardware I/O is mocked."""
import ast
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock

import requests
from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_manager import DEFAULT_CONFIG
from job_manager import JobManager
from ray5_client import Ray5Client

GCODE = b"G21\nG90\nG0 X10 Y20\nM3 S10\nG1 X50 Y20\nG1 X50 Y60\nM5\nM2\n"


class SDDownloadTests(unittest.TestCase):
    def client(self, data=GCODE, status=200, headers=None):
        client = Ray5Client({"ray5": {"host": "fixture.test", "port": 8848}})
        response = Mock(status_code=status, headers=headers or {})
        response.iter_content.return_value = [data]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        client.session.get = Mock(return_value=response)
        return client, response

    def test_real_download_path_encoding_case_and_content_type(self):
        client, response = self.client(headers={"Content-Type": "text/html, text/html"})
        result = client.read_sd_file("/Folder/Case #1.gc", 4096)
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"], GCODE)
        self.assertEqual(result["sha256"], hashlib.sha256(GCODE).hexdigest())
        self.assertEqual(client.session.get.call_args.args[0], "http://fixture.test:8848/SD/Folder/Case%20%231.gc")
        self.assertFalse(client.session.get.call_args.kwargs["allow_redirects"])
        self.assertEqual(result["source"], "sd_http")
        client.session.get.assert_called_once()
        response.__exit__.assert_called_once()

    def test_http_200_html_json_empty_and_non_gcode_never_accepted(self):
        for data in (b"<HTML>Unknown page: /SD/test.gc</HTML>", b"  <!DOCTYPE html>", b'{"files":[]}', b"[error]", b"", b"Error: failed"):
            with self.subTest(data=data):
                client, response = self.client(data)
                result = client.read_sd_file("/test.gc", 4096)
                self.assertFalse(result["ok"])
                self.assertTrue(result["download_unavailable"])
                self.assertNotIn("data", result)
                self.assertEqual(response.__exit__.call_count, 2)

    def test_esp221_reads_actual_sd_file_when_native_download_is_missing(self):
        client, missing = self.client(b"<HTML>Unknown page</HTML>")
        _, downloaded = self.client(GCODE, headers={"Content-Type": "text/html, text/html"})
        client.session.get.side_effect = [missing, downloaded]
        result = client.read_sd_file("/Folder/Case #1.gc", 4096)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "esp221_sd_read")
        self.assertEqual(result["data"], GCODE)
        self.assertEqual(result["sha256"], hashlib.sha256(GCODE).hexdigest())
        calls = client.session.get.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].args[0], "http://fixture.test:8848/command")
        self.assertEqual(calls[1].kwargs["params"], {"plain": "[ESP221]/Folder/Case #1.gc"})
        self.assertFalse(calls[1].kwargs["allow_redirects"])
        missing.__exit__.assert_called_once()
        downloaded.__exit__.assert_called_once()

    def test_esp221_errors_partial_content_and_missing_files_never_move(self):
        for content in (b"Error: invalid command", b"SD Card Busy", b"No SD Card", b"Failed to open file",
                        GCODE + b"error: read failed\n", GCODE + b"<HTML>error</HTML>\n",
                        GCODE + b"[MSG:read failed]\n"):
            with self.subTest(content=content):
                client, missing = self.client(b"<HTML>Unknown page</HTML>")
                _, downloaded = self.client(content)
                client.session.get.side_effect = [missing, downloaded]
                self.assertFalse(client.read_sd_file("/Case job.gc", 4096)["ok"])
                self.assertEqual(client.session.get.call_args.kwargs["params"], {"plain": "[ESP221]/Case job.gc"})

    def test_esp221_transfer_failure_is_not_accepted_as_a_partial_job(self):
        client, missing = self.client(status=404)
        _, downloaded = self.client()
        def partial(_block_size):
            yield GCODE[:30]
            raise requests.exceptions.ChunkedEncodingError("Incomplete file response")
        downloaded.iter_content.side_effect = partial
        client.session.get.side_effect = [missing, downloaded]
        result = client.read_sd_file("/Case job.gc", 4096)
        self.assertFalse(result["ok"])
        self.assertNotIn("data", result)
        self.assertIn("Incomplete", result["message"])
        downloaded.__exit__.assert_called_once()

    def test_bad_paths_rejected_without_network(self):
        client, _ = self.client()
        for target in ("", "/../test.gc", "/folder/../test.gc", "/folder/./test.gc", "https://other.test/test.gc", "C:\\test.gc", "/test.gc\nM3", "/[ESP220]test.gc", "/folder", "/test.gz", "/test.txt"):
            self.assertFalse(client.read_sd_file(target, 4096)["ok"], target)
        client.session.get.assert_not_called()

    def test_redirect_and_http_errors_rejected_without_following(self):
        for status in (302, 404, 500):
            client, response = self.client(status=status)
            self.assertFalse(client.read_sd_file("/test.gc", 4096)["ok"])
            response.iter_content.assert_not_called()

    def test_size_limits_close_response_without_draining(self):
        client, response = self.client(headers={"Content-Length": "10000"})
        self.assertFalse(client.read_sd_file("/test.gc", 50)["ok"])
        client.session.get.assert_called_once()
        response.iter_content.assert_not_called()
        client, response = self.client()
        response.iter_content.return_value = [b"G1 X", b"0" * 50]
        self.assertFalse(client.read_sd_file("/test.gc", 12)["ok"])
        response.__exit__.assert_called_once()

    def test_timeout_and_binary_data_are_clean_failures(self):
        client, _ = self.client()
        client.session.get.side_effect = requests.Timeout("fixture timeout")
        self.assertIn("timeout", client.read_sd_file("/test.gc", 4096)["message"])
        for data in (b"\xff\x00", b"G1 X10\x00"):
            client, _ = self.client(data)
            self.assertFalse(client.read_sd_file("/test.gc", 4096)["ok"])

    def test_stop_before_frame_replay_cancels_every_move(self):
        client, _ = self.client()
        generation = client.command_generation()
        client._batch_cancel_generation += 1
        result = client.send_gcode(["M5", "G0 X10 Y10", "M5"], expected_generation=generation)
        self.assertTrue(result["cancelled"])
        client.session.get.assert_not_called()


class SDFrameRouteTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.cfg = deepcopy(DEFAULT_CONFIG)
        self.manager = JobManager(Path(temp.name), self.cfg)
        self.ray5 = Mock(spec=Ray5Client)
        self.ray5.command_generation.return_value = 7
        self.ray5.list_files.return_value = {"ok": True, "path": "/Folder", "files": [{"name": "Case job.gc", "path": "/Folder/Case job.gc", "is_directory": False}]}
        self.download = {"ok": True, "data": GCODE, "sha256": hashlib.sha256(GCODE).hexdigest()}
        self.ray5.read_sd_file.return_value = self.download
        self.ray5.send_gcode.return_value = {"ok": True, "raw": "ok"}
        self.live = {"state": "Idle", "websocket_connected": True, "stale": False, "age_seconds": .2}
        monitor = Mock()
        monitor.get_latest_status.side_effect = lambda: self.live
        app = Flask(__name__)
        self.ns = {"app": app, "Any": object, "jsonify": jsonify, "request": request, "Path": Path, "math": math,
                   "tempfile": tempfile, "app_state_lock": threading.RLock(), "status_monitor": monitor,
                   "sd_frame_lock": threading.Lock(), "ray5": self.ray5, "jobs": self.manager, "cfg": self.cfg,
                   "console": Mock(), "_require_ray5_configured": lambda: None, "_is_ray5_comm_busy": lambda: False,
                   "_snapshot_upload_transfer_state": lambda: {}, "_laser_test_requests": 0,
                   "_update_launching": False, "_update_shutdown_started": False, "ray5_comm_safety_state": {}}
        tree = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8-sig"))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"_sd_frame_ready_error", "api_files_frame"}]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), self.ns)
        self.client = app.test_client()

    def frame(self, **overrides):
        return self.client.post("/api/files/frame", json={"filename": "Case job.gc", "path": "/Folder", "confirmed": True, **overrides})

    def test_downloaded_job_is_analyzed_not_executed_uploaded_or_imported(self):
        response = self.frame()
        self.assertEqual(response.status_code, 200, response.json)
        self.ray5.read_sd_file.assert_called_once_with("/Folder/Case job.gc", self.manager.max_bounds_parse_bytes)
        batch = self.ray5.send_gcode.call_args_list[0]
        self.assertEqual(batch.kwargs, {"expected_generation": 7})
        commands = batch.args[0]
        self.assertEqual(commands[0], "M5")
        self.assertEqual(commands[-1], "M5")
        self.assertTrue(any(command.startswith("G1") for command in commands))
        self.assertFalse(any(command.startswith(("M3", "M4", "M8")) for command in commands))
        self.ray5.start_sd_file.assert_not_called()
        self.ray5.upload_bytes_to_sd.assert_not_called()
        self.assertEqual(list(self.manager.imported_dir.iterdir()), [])

    def test_html_or_unreadable_file_never_falls_back_or_moves(self):
        self.ray5.read_sd_file.return_value = {"ok": False, "download_unavailable": True, "message": "Web page instead of G-code. No motion sent."}
        response = self.frame()
        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json["download_unavailable"])
        self.ray5.send_gcode.assert_not_called()

    def test_confirmation_and_current_listing_are_required(self):
        self.assertEqual(self.frame(confirmed=False).status_code, 400)
        self.ray5.list_files.assert_not_called()
        self.assertEqual(self.frame(filename="other.gc").status_code, 400)
        self.ray5.read_sd_file.assert_not_called()
        self.ray5.send_gcode.assert_not_called()

    def test_offline_stale_alarm_or_busy_status_blocks_before_read(self):
        for update in ({"websocket_connected": False}, {"stale": True}, {"age_seconds": 6}, {"age_seconds": float("nan")}, {"age_seconds": -1}, {"state": "Alarm"}, {"state": "Run"}, {"state": "Hold"}, {"state": "Home"}):
            with self.subTest(update=update):
                old = self.live.copy()
                self.live.update(update)
                self.assertEqual(self.frame().status_code, 409)
                self.live = old
        self.ray5.read_sd_file.assert_not_called()
        self.ray5.send_gcode.assert_not_called()

    def test_lockout_laser_activity_update_and_transfer_block(self):
        for key in ("_laser_test_requests", "_update_launching", "_update_shutdown_started"):
            self.ns[key] = True
            self.assertEqual(self.frame().status_code, 409)
            self.ns[key] = False
        self.ns["ray5_comm_safety_state"] = {"comm_lost_during_job": True}
        self.assertEqual(self.frame().status_code, 409)
        self.ray5.send_gcode.assert_not_called()

    def test_fresh_status_is_rechecked_after_download(self):
        def read(*args):
            self.live["stale"] = True
            return self.download
        self.ray5.read_sd_file.side_effect = read
        self.assertEqual(self.frame().status_code, 409)
        self.ray5.send_gcode.assert_not_called()

    def test_directory_and_bad_path_rejected(self):
        self.assertEqual(self.frame(path="/../private").status_code, 400)
        self.ray5.list_files.return_value["files"][0]["is_directory"] = True
        self.assertEqual(self.frame().status_code, 400)
        self.ray5.read_sd_file.assert_not_called()

    def test_subdirectory_is_preserved_when_listing_has_only_name(self):
        entry = self.ray5.list_files.return_value["files"][0]
        entry.update(path="/Case job.gc", raw={"name": "Case job.gc"})
        self.assertEqual(self.frame().status_code, 200)
        self.assertEqual(self.ray5.read_sd_file.call_args.args[0], "/Folder/Case job.gc")

    def test_printer_files_bad_bounds_and_invalid_feed_never_move(self):
        for content in (b"M104 S200\nG1 X10 Y20 E1\n", b"M5\n", GCODE.replace(b"X50", b"X999")):
            self.ray5.read_sd_file.return_value = self.download | {"data": content}
            self.assertEqual(self.frame().status_code, 400)
        self.ray5.read_sd_file.return_value = self.download
        self.assertEqual(self.frame(feed="bad").status_code, 400)
        self.ray5.send_gcode.assert_not_called()

    def test_upstream_error_and_stop_cancellation_report_failure_and_force_off(self):
        self.ray5.send_gcode.side_effect = [{"ok": False, "cancelled": True, "message": "Command batch canceled by Stop."}, {"ok": True}]
        response = self.frame()
        self.assertEqual(response.status_code, 502)
        self.assertIn("Stop", response.json["message"])
        self.assertEqual(self.ray5.send_gcode.call_args.args, ("M5",))

    def test_stop_during_download_cancels_replay_in_real_client(self):
        client = Ray5Client(self.cfg)
        client.list_files = Mock(return_value=self.ray5.list_files.return_value)
        def download(*args):
            with client._batch_state_lock:
                client._batch_cancel_generation += 1
            return self.download
        client.read_sd_file = download
        client._request_single_command = Mock(return_value={"ok": True})
        self.ns["ray5"] = client
        response = self.frame()
        self.assertEqual(response.status_code, 502)
        self.assertIn("Stop", response.json["message"])
        client._request_single_command.assert_called_once_with("M5")

    def test_parallel_frame_and_config_change_are_blocked(self):
        lock = self.ns["sd_frame_lock"]
        lock.acquire()
        try:
            self.assertEqual(self.frame().status_code, 409)
        finally:
            lock.release()
        def download(*args):
            self.ns["cfg"] = deepcopy(self.cfg)
            return self.download
        self.ray5.read_sd_file.side_effect = download
        self.assertEqual(self.frame().status_code, 409)
        self.ray5.send_gcode.assert_not_called()

    def test_final_off_failure_is_not_reported_as_success(self):
        self.ray5.send_gcode.side_effect = [{"ok": True}, {"ok": False}]
        response = self.frame()
        self.assertEqual(response.status_code, 502)
        self.assertIn("laser-off", response.json["message"])

    def test_sd_bounds_validation_cannot_be_disabled_by_imported_frame_settings(self):
        self.cfg["framing"].update(validate_bounds=False, force_laser_off=False)
        self.ray5.read_sd_file.return_value = self.download | {"data": GCODE.replace(b"X50", b"X999")}
        self.assertEqual(self.frame().status_code, 400)
        self.ray5.send_gcode.assert_not_called()


if __name__ == "__main__":
    unittest.main()
