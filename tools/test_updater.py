"""Updater transactions and API guards in temporary installs. No real Pilot shutdown."""
import argparse
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import updater
from flask import Flask, jsonify, request


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"install";self.root.mkdir()
        self.original={"app.py":b"version = 'old'\n","VERSION":b"0.0.1\n","requirements.txt":b"# old\n"}
        for rel in updater.REQUIRED_TEMPLATE_PATHS:self.original[rel]=b"old template"
        for rel,data in self.original.items():
            file=self.root/rel;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
        self.private={"config.json":b'{"backups":{"max_keep_backups":15},"personal":"keep"}',
                      ".env":b"LOCAL=keep","camera_captures/latest.jpg":b"image","timelapse/keep.mp4":b"video",
                      "imported_jobs/keep.gc":b"M5","watched_gcode/keep.gc":b"M5","logs/keep.log":b"log",
                      "snapshots/keep.png":b"image",".venv/keep.txt":b"environment"}
        for rel,data in self.private.items():
            file=self.root/rel;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data)
        self.package={"app.py":b"version = 'new'\n","VERSION":b"0.0.2\n","config.example.json":b"{}",
                      "requirements.txt":b"# fixture: no dependencies\n","00_new.py":b"added = True\n"}
        for rel in updater.REQUIRED_TEMPLATE_PATHS:self.package[rel]=b"new template"

    def archive(self,package=None,prefix=""):
        out=io.BytesIO()
        with zipfile.ZipFile(out,"w") as z:
            for rel,data in (self.package if package is None else package).items():z.writestr(prefix+rel,data)
        return out.getvalue()

    def run_update(self,package=None,prefix="",sha=None,pip_result=0,download_error=None,copy=None,restart_error=None,parent_error=None):
        data=self.archive(package,prefix)
        args=argparse.Namespace(project_root=str(self.root),python_exe=sys.executable,parent_pid=0,
            source_url="http://fixture.test/update.zip",expected_sha256=hashlib.sha256(data).hexdigest() if sha is None else sha,
            current_version="0.0.1",remote_version="0.0.2")
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.download=stack.enter_context(patch("updater.urlrequest.urlopen",side_effect=download_error,return_value=io.BytesIO(data)))
            self.pip=stack.enter_context(patch("updater.subprocess.run",return_value=Mock(returncode=pip_result,stdout="",stderr="fixture error")))
            self.restart=stack.enter_context(patch("updater.subprocess.Popen",side_effect=restart_error))
            stack.enter_context(patch("updater._safe_wait_for_parent_exit",side_effect=parent_error))
            if copy:stack.enter_context(patch("updater._copy_file",side_effect=copy))
            result=updater._run(args)
        status=json.loads((self.root/"update_logs/update_status.json").read_text())
        for rel,expected in self.private.items():self.assertEqual((self.root/rel).read_bytes(),expected,rel)
        return result,status

    def assert_original_restored(self):
        for rel,data in self.original.items():self.assertEqual((self.root/rel).read_bytes(),data,rel)
        self.assertFalse((self.root/"00_new.py").exists())

    def test_valid_flat_package_and_backups_preserve_local_data(self):
        package={**self.package,**{rel:b"must not replace" for rel in self.private}}
        result,status=self.run_update(package)
        self.assertEqual(result,0);self.assertTrue(status["ok"])
        self.assertEqual((self.root/"VERSION").read_text().strip(),"0.0.2")
        self.assertTrue((self.root/"00_new.py").exists())
        backups=list((self.root/"backups/updates").glob("update_*"));self.assertEqual(len(backups),1)
        for rel,data in self.original.items():self.assertEqual((backups[0]/rel).read_bytes(),data)
        self.assertFalse((self.root/"update_work").exists())
        self.restart.assert_called_once()

    def test_nested_release_root_detected(self):
        result,status=self.run_update(prefix="Ray5-Pilot-test/")
        self.assertEqual(result,0);self.assertTrue(status["ok"])

    def test_checksum_mismatch_records_failure_and_restarts_original(self):
        result,status=self.run_update(sha="0"*64)
        self.assertEqual(result,1);self.assertFalse(status["ok"])
        self.assertIn("checksum mismatch",status["message"])
        self.assert_original_restored();self.restart.assert_called_once();self.pip.assert_not_called()

    def test_failed_download_does_not_rotate_away_good_backups(self):
        self.private['config.json']=b'{"backups":{"max_keep_backups":1},"personal":"keep"}'
        (self.root/'config.json').write_bytes(self.private['config.json'])
        backup=self.root/'backups/updates/update_previous';backup.mkdir(parents=True)
        (backup/'app.py').write_bytes(b'valuable previous backup')
        result,_=self.run_update(sha='0'*64)
        self.assertEqual(result,1)
        self.assertEqual((backup/'app.py').read_bytes(),b'valuable previous backup')

    def test_missing_checksum_refused_before_download(self):
        result,status=self.run_update(sha="")
        self.assertEqual(result,1);self.assertIn("Missing expected SHA-256",status["message"])
        self.download.assert_not_called();self.assert_original_restored()

    def test_network_failure_reports_and_recovers(self):
        result,status=self.run_update(download_error=OSError("offline"))
        self.assertEqual(result,1);self.assertFalse(status["ok"])
        self.assert_original_restored();self.restart.assert_called_once()

    def test_corrupt_archive_reports_failure_and_keeps_original(self):
        with patch.object(self,'archive',return_value=b'not a zip file'):
            result,status=self.run_update()
        self.assertEqual(result,1);self.assertFalse(status['ok']);self.assert_original_restored()
        self.restart.assert_called_once()

    def test_missing_template_is_rejected_before_copy(self):
        package=dict(self.package);package.pop(updater.REQUIRED_TEMPLATE_PATHS[-1])
        result,status=self.run_update(package)
        self.assertEqual(result,1);self.assertIn("template missing",status["message"])
        self.assert_original_restored()

    def test_wrong_package_version_rejected(self):
        result,status=self.run_update({**self.package,"VERSION":b"0.0.3"})
        self.assertEqual(result,1);self.assertIn("VERSION",status["message"]);self.assert_original_restored()

    def test_bad_python_rejected_before_copy(self):
        result,status=self.run_update({**self.package,"app.py":b"def broken(:\n"})
        self.assertEqual(result,1);self.assertFalse(status["ok"]);self.assert_original_restored()

    def test_partial_copy_rolls_back_even_the_failed_destination(self):
        original_copy=updater._copy_file;failed=False
        def copy(src,dst):
            nonlocal failed
            if dst==self.root/"app.py" and not failed:
                failed=True;dst.write_text("partial write");raise OSError("simulated disk failure")
            original_copy(src,dst)
        result,status=self.run_update(copy=copy)
        self.assertEqual(result,1);self.assertFalse(status["ok"]);self.assert_original_restored()
        self.restart.assert_called_once()

    def test_pip_failure_rolls_back_instead_of_claiming_success(self):
        result,status=self.run_update(pip_result=1)
        self.assertEqual(result,1);self.assertIn("Dependency",status["message"]);self.assert_original_restored()

    def test_failed_rollback_never_restarts_mixed_files(self):
        original_copy=updater._copy_file
        def copy(src,dst):
            if dst==self.root/'app.py':
                dst.write_text('partial write');raise OSError('destination stays locked')
            original_copy(src,dst)
        result,status=self.run_update(copy=copy)
        self.assertEqual(result,1);self.assertIn('rollback was incomplete',status['message'])
        self.restart.assert_not_called()
        backup=next((self.root/'backups/updates').glob('update_*'))
        self.assertEqual((backup/'app.py').read_bytes(),self.original['app.py'])

    def test_parent_exit_failure_never_overwrites_or_starts_duplicate_pilot(self):
        result,status=self.run_update(parent_error=RuntimeError("parent still running after timeout"))
        self.assertEqual(result,1);self.assertIn("still running after",status["message"])
        self.assert_original_restored();self.download.assert_not_called();self.restart.assert_not_called()

    def test_restart_failure_rolls_back_and_attempts_original_app(self):
        result,status=self.run_update(restart_error=[OSError("cannot launch"),Mock()])
        self.assertEqual(result,1);self.assertFalse(status["ok"]);self.assert_original_restored()
        self.assertEqual(self.restart.call_count,2)

    def test_archive_traversal_rejected(self):
        for name in ("../escape.py","..\\escape.py","/escape.py","C:/escape.py","file:stream"):
            with self.subTest(name=name):
                archive=self.root/"bad.zip";archive.write_bytes(self.archive({name:b"bad"}))
                with self.assertRaises(RuntimeError):updater._safe_extract_zip(archive,self.root/"extract",lambda _:None)

    def test_parent_timeout_is_a_failure_not_permission_to_copy(self):
        with patch("updater._is_process_running",return_value=True),patch("updater.time.sleep"),patch("updater.time.monotonic",side_effect=[0,0,2]):
            with self.assertRaisesRegex(RuntimeError,"still running after"):
                updater._safe_wait_for_parent_exit(123,1,lambda _:None)


class UpdateApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/"updater.py").write_text("# fixture")
        self.app=Flask(__name__)
        info={"ok":True,"update_available":True,"current_version":"0.0.1","latest_version":"0.0.2",
              "source_zip_url":"https://github.com/P0k3sm0t/Ray5-Pilot/releases/download/v0.0.2/fixture.zip",
              "source_zip_sha256":"a"*64,"checksum_url":""}
        self.ns={"app":self.app,"Any":object,"jsonify":jsonify,"request":request,"app_state_lock":threading.RLock(),
            "_update_launching":False,"_update_shutdown_started":False,"BASE_DIR":self.root,
            "_laser_test_requests":0,"laser_runtime_state":{"active":False},
            "_check_source_update":Mock(return_value=info),"_update_github_check_cache_from_result":lambda value,**_:value,
            "_get_machine_state_for_update_guard":Mock(return_value="Idle"),"_timelapse_normalize_state":lambda s:s.split(':')[0],
            "_snapshot_upload_transfer_state":Mock(return_value={}),"_timelapse_snapshot_state":Mock(return_value={}),
            "_snapshot_comm_safety_state":Mock(return_value={}),"_read_local_version":lambda:"0.0.1",
            "console":Mock(),"subprocess":Mock(),"_delayed_process_exit":Mock(),"sys":sys,"os":os,"re":re}
        self.ns.update(cfg={"safety":{"test_fire_enabled":True}},ray5=Mock(),
            _require_ray5_configured=lambda:None,_set_laser_commanded_s=Mock(),_set_laser_test_active=Mock())
        tree=ast.parse((Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8-sig"))
        names={"api_github_apply_update","api_test_fire","_is_trusted_github_release_asset_url","_normalize_version_text","_parse_version_parts","_compare_versions","_extract_sha256_from_text"}
        functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
        exec(compile(ast.Module(body=functions,type_ignores=[]),"app.py","exec"),self.ns)
        self.client=self.app.test_client()

    def test_valid_apply_handoff_only_once(self):
        self.assertEqual(self.client.post('/api/github/apply-update').status_code,200)
        self.assertEqual(self.client.post('/api/github/apply-update').status_code,409)
        self.ns['subprocess'].Popen.assert_called_once()
        self.ns['_delayed_process_exit'].assert_called_once()

    def test_all_busy_states_block_shutdown(self):
        for state in ('Run','Hold:0','Jog','Home','Door:1'):
            with self.subTest(state=state):
                self.ns['_get_machine_state_for_update_guard'].return_value=state
                self.assertEqual(self.client.post('/api/github/apply-update').status_code,409)
        self.ns['subprocess'].Popen.assert_not_called()

    def test_upload_timelapse_and_safety_lockout_block_update(self):
        for name,value in (('_snapshot_upload_transfer_state',{'upload_in_progress':True}),
                           ('_timelapse_snapshot_state',{'build_in_progress':True}),
                           ('_snapshot_comm_safety_state',{'comm_lost_during_job':True})):
            self.ns[name].return_value=value
            self.assertEqual(self.client.post('/api/github/apply-update').status_code,409)
            self.ns[name].return_value={}
        self.ns['subprocess'].Popen.assert_not_called()

    def test_stationary_laser_or_pending_test_blocks_update_while_idle(self):
        self.ns['_laser_test_requests']=1
        self.assertEqual(self.client.post('/api/github/apply-update').status_code,409)
        self.ns['_laser_test_requests']=0
        self.ns['laser_runtime_state']['active']=True
        self.assertEqual(self.client.post('/api/github/apply-update').status_code,409)
        self.ns['subprocess'].Popen.assert_not_called()

    def test_laser_test_blocked_during_update_without_upstream_calls(self):
        self.ns['_update_launching']=True
        self.assertEqual(self.client.post('/api/laser/test-fire',json={}).status_code,409)
        self.ns['ray5'].test_fire.assert_not_called()
        self.ns['_set_laser_commanded_s'].assert_not_called()

    def test_laser_request_counter_clears_even_if_the_mock_sender_fails(self):
        def fail(**kwargs):
            self.assertEqual(self.ns['_laser_test_requests'],1)
            raise RuntimeError('simulated sender failure')
        self.ns['ray5'].test_fire.side_effect=fail
        self.assertEqual(self.client.post('/api/laser/test-fire',json={}).status_code,500)
        self.ns['ray5'].test_fire.assert_called_once()
        self.assertEqual(self.ns['_laser_test_requests'],0)

    def test_untrusted_or_main_branch_assets_are_rejected(self):
        info=self.ns['_check_source_update'].return_value
        for url in ('https://example.test/update.zip','https://github.com/P0k3sm0t/Ray5-Pilot/archive/refs/heads/main.zip'):
            info['source_zip_url']=url
            self.assertGreaterEqual(self.client.post('/api/github/apply-update').status_code,400)
        self.ns['subprocess'].Popen.assert_not_called()

    def test_launch_failure_does_not_shutdown_and_allows_retry(self):
        self.ns['subprocess'].Popen.side_effect=OSError('launch blocked')
        self.assertEqual(self.client.post('/api/github/apply-update').status_code,500)
        self.assertFalse(self.ns['_update_launching']);self.ns['_delayed_process_exit'].assert_not_called()

    def test_version_and_checksum_formats(self):
        self.assertEqual(self.ns['_compare_versions']('v1.2.4','1.2.5'),-1)
        self.assertEqual(self.ns['_compare_versions']('1.2.4','1.2.4.0'),0)
        digest='a'*64
        for text in (digest, 'sha256:'+digest, digest+'  fixture.zip'):
            self.assertEqual(self.ns['_extract_sha256_from_text'](text,'fixture.zip'),digest)


if __name__=='__main__':unittest.main()
