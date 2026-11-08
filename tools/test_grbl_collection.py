"""Offline tests for response ordering and complete GRBL settings collection."""
import ast
from pathlib import Path
import re
import threading
import unittest
from unittest.mock import Mock


class Clock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return 1000 + self.now

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class GrblCollectionTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.client = Mock()
        self.client._base.return_value = "http://device.test:8848"
        self.client.send_gcode.return_value = {"ok":True,"raw":"ok","message":"ok"}
        self.monitor = Mock()
        self.monitor.get_lines_since.return_value = []
        self.state = {"job_id":"read1","running":True,"complete_device":"","complete_keys":[]}
        self.core = frozenset({"0","10","30","31","32","100","101","110","111","120","121","130","131"})
        self.ns = {
            "Any":object,"re":re,"time":self.clock,"ray5":self.client,"status_monitor":self.monitor,
            "app_state_lock":threading.RLock(),"firmware_read_lock":threading.RLock(),
            "firmware_settings_collect_lock":threading.RLock(),"firmware_settings_collect_state":self.state,
            "GRBL_CORE_SETTING_KEYS":self.core,"GRBL_SETTING_INFO":{},"console":Mock(),
            "_parse_grbl_identity_raw":Mock(return_value={"ok":True,"raw":"[VER:test]"}),
        }
        source=Path(__file__).resolve().parents[1]/"app.py"
        tree=ast.parse(source.read_text(encoding="utf-8-sig"))
        names={"_parse_machine_settings_raw","_collect_grbl_reply","_collect_machine_settings_raw",
               "_collect_grbl_identity_raw","_firmware_settings_collect_worker"}
        functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
        self.assertEqual(len(functions),len(names))
        exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),"exec"),self.ns)

    def settings(self, keys=None):
        return [f"${key}=0" for key in sorted(keys or self.core,key=int)]

    def timeline(self, events):
        self.monitor.get_lines_since.side_effect=lambda since: [line for delay,lines in events
            if 1000+delay>=since and delay<=self.clock.now for line in lines]

    def collect(self, max_lines=200):
        return self.ns["_collect_machine_settings_raw"](timeout_seconds=2,max_lines=max_lines)

    def test_preceding_ack_does_not_finish_first_partial_chunk(self):
        self.timeline([(0,["ok"]),(0.05,["$0=3","$1=250"]),(0.3,self.settings(self.core-{"0"})),(0.35,["ok"])])
        raw,_,failed=self.collect()
        self.assertFalse(failed)
        self.assertIn("$131=",raw)
        self.assertGreaterEqual(self.clock.now,0.7)

    def test_stray_ack_after_partial_chunk_cannot_hide_missing_core_settings(self):
        self.timeline([(0.05,["$0=3","$1=250","ok"]),(0.65,self.settings(self.core-{"0"})+["ok"])])
        raw,_,failed=self.collect()
        self.assertFalse(failed)
        self.assertIn("$131=",raw)

    def test_last_known_firmware_specific_keys_required_for_same_device(self):
        self.state.update(complete_device=self.client._base(),complete_keys=list(self.core|{"135"}))
        self.timeline([(0.05,self.settings()+["ok"]),(0.65,["$135=100","ok"])])
        raw,_,failed=self.collect()
        self.assertFalse(failed)
        self.assertIn("$135=100",raw)

    def test_expected_keys_do_not_leak_to_different_device(self):
        self.state.update(complete_device="http://other.test:8848",complete_keys=list(self.core|{"999"}))
        self.timeline([(0.05,self.settings()+["ok"])])
        self.assertFalse(self.collect()[2])

    def test_http_ack_before_sideband_is_not_a_terminator(self):
        self.timeline([(0.05,self.settings())])
        self.assertTrue(self.collect()[2])

    def test_later_setting_after_ack_requires_a_new_trailing_ack(self):
        self.timeline([(0.05,self.settings()+["ok"]),(0.2,["$135=10"])])
        self.assertTrue(self.collect()[2])

    def test_missing_core_keys_fails_even_with_trailing_ack(self):
        self.timeline([(0.05,["$0=3","$1=250","ok"])])
        raw,message,failed=self.collect()
        self.assertTrue(failed)
        self.assertIn("$0=3",raw)
        self.assertIn("Incomplete",message)

    def test_status_polls_do_not_keep_a_complete_settings_reply_open(self):
        self.timeline([(0.05,self.settings()+["ok"])]+[(i/10,["<Idle|FS:0,0>"]) for i in range(1,20)])
        self.assertFalse(self.collect()[2])
        self.assertLess(self.clock.now,1)

    def test_full_http_reply_works_without_websocket(self):
        self.ns["status_monitor"]=None
        self.client.send_gcode.return_value={"ok":True,"raw":"\n".join(self.settings()+["ok"])}
        self.assertFalse(self.collect()[2])

    def test_bare_http_error_needs_complete_fresh_sideband_proof(self):
        self.client.send_gcode.return_value={"ok":False,"raw":"Error"}
        self.timeline([(0.05,self.settings()+["ok"])])
        self.assertFalse(self.collect()[2])

    def test_transport_failure_stays_a_failure(self):
        self.client.send_gcode.return_value={"ok":False,"raw":"","message":"read timeout"}
        raw,message,failed=self.collect()
        self.assertTrue(failed)
        self.assertIn("timeout",message)
        self.monitor.get_lines_since.assert_not_called()

    def test_old_websocket_lines_are_not_reused(self):
        self.timeline([(-1,self.settings()+["ok"])])
        self.assertTrue(self.collect()[2])

    def test_output_truncation_cannot_publish_missing_settings(self):
        self.timeline([(0.05,self.settings()+["ok"])])
        self.assertTrue(self.collect(max_lines=3)[2])

    def test_identity_waits_for_its_own_trailing_ack_and_final_payload(self):
        self.timeline([(0,["ok"]),(0.05,["[VER:1.3a:test]"]),(0.2,["[Board:Ray5]"]),(0.3,["ok"])])
        raw,_,failed=self.ns["_collect_grbl_identity_raw"](timeout_seconds=1)
        self.assertFalse(failed)
        self.assertIn("[Board:Ray5]",raw)
        self.assertGreaterEqual(self.clock.now,0.6)

    def test_worker_retries_partial_read_and_only_publishes_complete_result(self):
        complete="\n".join(self.settings()+["ok"])
        collect=Mock(side_effect=[("$0=3\nok","Incomplete",True),(complete,"ok",False)])
        self.ns["_collect_machine_settings_raw"]=collect
        self.ns["_collect_grbl_identity_raw"]=Mock(return_value=("[VER:test]\nok","ok",False))
        self.ns["_firmware_settings_collect_worker"]("read1")
        self.assertEqual(collect.call_count,2)
        self.assertTrue(self.state["ok"])
        self.assertEqual(len(self.state["settings"]),len(self.core))
        self.assertEqual(set(self.state["complete_keys"]),self.core)

    def test_worker_never_reports_partial_read_as_success_after_retry(self):
        self.state.update(complete_device=self.client._base(),complete_keys=list(self.core))
        self.ns["_collect_machine_settings_raw"]=Mock(return_value=("$0=3\nok","Incomplete",True))
        identity=Mock();self.ns["_collect_grbl_identity_raw"]=identity
        self.ns["_firmware_settings_collect_worker"]("read1")
        self.assertFalse(self.state["ok"])
        self.assertTrue(self.state["timed_out"])
        self.assertEqual(self.state["settings"],[])
        self.assertEqual(set(self.state["complete_keys"]),self.core)
        identity.assert_not_called()


if __name__=="__main__":
    unittest.main()
