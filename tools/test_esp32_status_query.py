"""Exercise the actual status route without importing app startup or touching hardware."""
import ast
from pathlib import Path
import re
import threading
import time
import unittest
from unittest.mock import Mock

from flask import Flask, jsonify, request


class Esp32StatusQueryTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.ray5 = Mock()
        self.ray5.trigger_live_status.return_value = {"ok": True, "raw": "Error"}
        self.monitor = Mock()
        self.monitor.get_page_id.return_value = "7"
        self.monitor.is_connected.return_value = True
        self.monitor.get_lines_since.return_value = ["<Idle|MPos:0.000,0.000|FS:0,0>"]
        self.clock = Mock()
        self.clock.time.return_value = 100.0
        self.clock.monotonic.side_effect = lambda: time.monotonic()
        self.clock.sleep.side_effect = lambda _: None
        self.ns = {
            "app": self.app, "Any": object, "app_state_lock": threading.RLock(),
            "status_monitor": self.monitor, "ray5": self.ray5, "time": self.clock,
            "re": re, "console": Mock(), "jsonify": jsonify, "request": request,
            "_require_ray5_configured": lambda: None,
        }
        source = Path(__file__).resolve().parents[1] / "app.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        names = {"_query_esp32_live_status", "api_esp32_command", "_esp32_offline_payload"}
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.assertEqual(len(functions), len(names))
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), self.ns)
        self.client = self.app.test_client()

    def query(self):
        return self.ns["_query_esp32_live_status"](timeout_seconds=0)

    def post(self, command):
        return self.client.post("/api/esp32/command", json={"command": command})

    def test_http_error_with_fresh_websocket_report_succeeds(self):
        result = self.query()
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "websocket")
        self.assertFalse(result["synthetic"])
        self.monitor.get_lines_since.assert_called_once_with(100.0)
        self.ray5.trigger_live_status.assert_called_once_with("7")
        self.ray5.send_gcode.assert_not_called()

    def test_newest_report_and_all_controller_states(self):
        for state in ("Idle", "Run", "Alarm", "Jog", "Hold:0", "Door:1", "Home", "Check", "Sleep"):
            with self.subTest(state=state):
                line = f"<{state}|MPos:12.5,0.0|FS:0,0>"
                self.monitor.get_lines_since.return_value = ["ok", "<Idle|FS:0,0>", line]
                self.assertEqual(self.query()["raw"], line)

    def test_stale_cache_never_counts_as_success(self):
        self.monitor.get_latest_status.return_value = {"state": "Idle", "stale": False}
        self.monitor.get_lines_since.return_value = []
        self.assertFalse(self.query()["ok"])
        self.monitor.get_latest_status.assert_not_called()

    def test_http_status_does_not_require_websocket(self):
        self.ns["status_monitor"] = None
        self.ray5.trigger_live_status.return_value = {"ok": True, "raw": "<Idle|FS:0,0>\nok"}
        result = self.query()
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "http")

    def test_no_websocket_does_not_claim_mainboard_online(self):
        for monitor in (None, self.monitor):
            with self.subTest(monitor=monitor is not None):
                self.ns["status_monitor"] = monitor
                self.monitor.is_connected.return_value = False
                self.assertFalse(self.query()["ok"])

    def test_malformed_or_non_status_lines_not_accepted(self):
        self.monitor.get_lines_since.return_value = ["ok", "[MSG:Idle]", "<Idle>", "ALARM:1"]
        self.assertFalse(self.query()["ok"])

    def test_http_failure_is_not_hidden_by_live_websocket(self):
        self.ray5.trigger_live_status.return_value = {"ok": False, "message": "HTTP 500", "raw": "Error"}
        response = self.post("?")
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json["offline"])
        self.monitor.get_lines_since.assert_not_called()

    def test_route_reports_live_status_success(self):
        response = self.post("?")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"])
        self.assertEqual(response.json["result"]["source"], "websocket")
        self.assertTrue(response.json["result"]["raw"].startswith("<Idle|"))

    def test_reachable_esp32_without_status_is_not_reported_offline(self):
        self.ns["status_monitor"] = None
        response = self.post("?")
        self.assertEqual(response.status_code, 504)
        self.assertFalse(response.json["ok"])
        self.assertFalse(response.json["offline"])
        self.assertTrue(response.json["status_unavailable"])

    def test_transport_exception_stays_visible(self):
        self.ray5.trigger_live_status.side_effect = TimeoutError("read timeout")
        response = self.post("?")
        self.assertEqual(response.status_code, 503)
        self.assertIn("read timeout", response.json["error"])

    def test_non_status_commands_keep_existing_path_and_errors(self):
        for command in ("M8", "M9", "$I", "$X", "$110=24000", "?\nM3"):
            for ok in (True, False):
                with self.subTest(command=command, ok=ok):
                    self.ray5.send_gcode.return_value = {"ok": ok, "message": "ok" if ok else "Error"}
                    response = self.post(command)
                    self.assertEqual(response.status_code, 200 if ok else 503)
                    self.ray5.send_gcode.assert_called_with(command)
        self.ray5.trigger_live_status.assert_not_called()

    def test_waits_for_delayed_new_report(self):
        self.monitor.get_lines_since.side_effect = [[], ["<Idle|FS:0,0>"]]
        self.assertTrue(self.ns["_query_esp32_live_status"](timeout_seconds=1)["ok"])
        self.clock.sleep.assert_called_once_with(0.05)

    def test_empty_command_rejected_without_upstream_call(self):
        self.assertEqual(self.post("").status_code, 400)
        self.ray5.trigger_live_status.assert_not_called()
        self.ray5.send_gcode.assert_not_called()


if __name__ == "__main__":
    unittest.main()
