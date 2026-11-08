"""Isolated regression tests for Ray5 Ctrl-X acknowledgement; no hardware calls."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
from ray5_client import Ray5Client


class StopRealtimeTests(unittest.TestCase):
    def client(self, replies, **control):
        client = Ray5Client({
            "ray5": {"host": "192.0.2.10", "port": 8848},
            "job_control": {"stop_mode": "soft_reset", "allow_soft_reset_stop": True,
                            "stop_sends_laser_off_first": True, "stop_unlock_after_reset": False, **control},
        })
        client.session.get = Mock(side_effect=[
            item if isinstance(item, Exception) else Mock(status_code=item[0], text=item[1])
            for item in replies
        ])
        return client

    def stop(self, client):
        with patch("ray5_client.time.sleep"):
            return client.stop_job()

    def commands(self, client):
        return [call.kwargs["params"]["commandText"] for call in client.session.get.call_args_list]

    def test_observed_200_bare_error_reset_is_delivered(self):
        client = self.client([(200, ""), (200, "Error")])
        result = self.stop(client)
        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "Stop/abort sent.")
        self.assertEqual(self.commands(client), ["M5", "\x18"])
        self.assertEqual(result["steps"]["CTRL_X"]["raw"], "Error")
        self.assertTrue(result["steps"]["CTRL_X"]["reset_response_quirk"])

    def test_normal_reset_ack(self):
        for body in ("", "ok"):
            with self.subTest(body=body):
                result = self.stop(self.client([(200, "ok"), (200, body)]))
                self.assertTrue(result["ok"])
                self.assertFalse(result["steps"]["CTRL_X"]["reset_response_quirk"])

    def test_http_failure_is_not_tolerated(self):
        for status in (400, 404, 500, 503):
            with self.subTest(status=status):
                result = self.stop(self.client([(200, "ok"), (status, "Error")]))
                self.assertFalse(result["ok"])
                self.assertFalse(result["steps"]["CTRL_X"]["reset_response_quirk"])

    def test_invalid_command_is_not_tolerated(self):
        for body in ("Invalid command", "Error: invalid command"):
            with self.subTest(body=body):
                result = self.stop(self.client([(200, "ok"), (200, body)]))
                self.assertFalse(result["ok"])
                self.assertEqual(result["steps"]["CTRL_X"]["raw"], body)

    def test_normal_commands_reject_prefixed_firmware_errors(self):
        for body in ("Error: Another interface is busy", "error:9", "ERROR : Alarm lock", "Error failed to open file"):
            with self.subTest(body=body):
                client = self.client([(200, body)])
                result = client.send_gcode("[ESP220]/test.gc")
                self.assertFalse(result["ok"])
                self.assertEqual(result["message"], body)

    def test_reset_exception_only_accepts_bare_error_not_prefixed_error(self):
        client = self.client([(200, "ok"), (200, "Error: Another interface is busy")])
        result = self.stop(client)
        self.assertFalse(result["ok"])
        self.assertFalse(result["steps"]["CTRL_X"]["reset_response_quirk"])

    def test_timeout_is_not_tolerated(self):
        result = self.stop(self.client([(200, "ok"), requests.Timeout("test timeout")]))
        self.assertFalse(result["ok"])
        self.assertIn("test timeout", result["steps"]["CTRL_X"]["message"])

    def test_laser_off_failure_is_not_tolerated(self):
        client = self.client([(200, "Error"), (200, "Error")])
        result = self.stop(client)
        self.assertFalse(result["ok"])
        self.assertFalse(result["steps"]["M5"]["ok"])
        self.assertTrue(result["steps"]["CTRL_X"]["ok"])
        self.assertEqual(self.commands(client), ["M5", "\x18"])

    def test_exception_requires_explicit_reset_opt_in(self):
        client = self.client([(200, "Error"), (200, "Error")])
        self.assertFalse(client._request_single_command("\x18")["ok"])
        self.assertFalse(client._request_single_command("G1 X1", tolerate_reset_error=True)["ok"])

    def test_unlock_order_is_unchanged_when_configured(self):
        client = self.client([(200, "ok"), (200, "Error"), (200, "ok")], stop_unlock_after_reset=True)
        self.assertTrue(self.stop(client)["ok"])
        self.assertEqual(self.commands(client), ["M5", "\x18", "$X"])

    def test_prohibited_stop_never_sends_commands(self):
        for control in ({"stop_mode": "disabled"}, {"allow_soft_reset_stop": False}):
            with self.subTest(control=control):
                client = self.client([], **control)
                self.assertFalse(self.stop(client)["ok"])
                self.assertEqual(self.commands(client), [])

    def test_hold_only_sequence_is_unchanged(self):
        client = self.client([(200, "ok")], stop_mode="hold_only")
        self.assertTrue(self.stop(client)["ok"])
        self.assertEqual(self.commands(client), ["!"])

    def test_stop_cancels_remaining_frame_batch_lines(self):
        client = self.client([(200, "ok"), (200, "ok"), (200, "Error")])
        original_send = client._request_single_command
        def send(command, **kwargs):
            result = original_send(command, **kwargs)
            if command == "G1 X1":
                self.assertTrue(self.stop(client)["ok"])
            return result
        client._request_single_command = send
        result = client.send_gcode(["G1 X1", "G1 X2", "G1 X3"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["cancelled"])
        self.assertEqual(self.commands(client), ["G1 X1", "M5", "\x18"])

    def test_feed_hold_cancels_remaining_batch_but_future_commands_are_allowed(self):
        client = self.client([(200, "ok")] * 4, stop_mode="hold_only")
        original_send = client._request_single_command
        def send(command, **kwargs):
            result = original_send(command, **kwargs)
            if command == "G1 X1":
                self.stop(client)
            return result
        client._request_single_command = send
        self.assertTrue(client.send_gcode(["G1 X1", "G1 X2"])["cancelled"])
        self.assertTrue(client.send_gcode(["M5", "G90"])["ok"])
        self.assertEqual(self.commands(client), ["G1 X1", "!", "M5", "G90"])


if __name__ == "__main__":
    unittest.main()
