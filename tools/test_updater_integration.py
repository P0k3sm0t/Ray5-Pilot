"""Real HTTP/pip/restart updater tests in throwaway installs; never touches live Pilot."""
import argparse
from copy import deepcopy
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
import shutil
from pathlib import Path
import socket
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
from unittest.mock import patch
from urllib.request import urlopen
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import updater
from config_manager import DEFAULT_CONFIG


APP = b'''import json, pathlib, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
root = pathlib.Path(__file__).resolve().parent
config = json.loads((root / "config.json").read_text())
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"version":(root / "VERSION").read_text().strip()}).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)
        if self.path == "/shutdown": threading.Thread(target=self.server.shutdown,daemon=True).start()
    def log_message(self, *args): pass
server = HTTPServer(("127.0.0.1", config["fixture_port"]), Handler)
server.serve_forever()
server.server_close()
'''


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def wait_version(port, expected, pilot=False):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        try:
            endpoint='/api/status' if pilot else '/'
            with urlopen(f'http://127.0.0.1:{port}{endpoint}',timeout=2) as response:
                version=json.load(response)['app_version' if pilot else 'version']
            if version==expected:return
        except (OSError,ValueError):pass
        time.sleep(0.1)
    raise AssertionError(f'Temporary app did not restart with {expected}')


def run_case(folder, mode, python):
    root=folder/mode;root.mkdir()
    pilot=mode=='pilot_success'
    success=mode in {'success','pilot_success'}
    port=free_port()
    config=json.dumps({'fixture_port':port,'personal_value':'fixture-only','backups':{'max_keep_backups':15}}).encode()
    originals={'app.py':APP,'VERSION':b'0.0.1','config.json':config,'config.example.json':b'{}','requirements.txt':b'# old fixture\n',
               'camera_captures/latest.jpg':b'keep image','imported_jobs/keep.gc':b'M5\n'}
    for rel in updater.REQUIRED_TEMPLATE_PATHS:originals[rel]=b'old template'
    if pilot:
        project=Path(__file__).resolve().parents[1]
        for file in project.glob('*.py'):originals[file.name]=file.read_bytes()
        for file in (project/'web').rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts:originals[file.relative_to(project).as_posix()]=file.read_bytes()
        safe=deepcopy(DEFAULT_CONFIG)
        safe['web_ui'].update(host='127.0.0.1',port=port,debug=False)
        safe['ray5']['host']='YOUR_RAY5_IP'
        safe['camera'].update(enabled=False,video_enabled=False,auto_capture_on_start=False,auto_cleanup_on_start=False)
        safe['jobs']['watch_enabled']=False
        safe['status']['websocket_enabled']=False
        safe['safety'].update(test_fire_enabled=False,enable_test_fire=False)
        safe['timelapse']['enabled']=False
        config=json.dumps(safe).encode()
        originals['config.json']=config
        originals['config.example.json']=json.dumps(safe).encode()
    for rel,content in originals.items():
        target=root/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as package:
        files={'app.py':APP+b'\n# updated fixture\n','VERSION':b'0.0.2','config.example.json':b'{}',
               'requirements.txt':b'ray5-fixture-nonexistent-package==999999\n' if mode=='pip_failure' else b'# no dependencies\n',
               'new_module.py':b'added = True\n','config.json':b'{}'}
        for rel in updater.REQUIRED_TEMPLATE_PATHS:files[rel]=b'new template'
        if pilot:
            files.update({rel:content for rel,content in originals.items() if rel.endswith('.py') or rel.startswith('web/')})
            files['config.example.json']=originals['config.example.json']
        for rel,content in files.items():package.writestr('fixture-release/'+rel,content)
    payload=archive.getvalue();downloads=[]
    class Download(BaseHTTPRequestHandler):
        def do_GET(self):
            downloads.append(self.path)
            self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Download)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    real_popen=subprocess.Popen
    flags={'creationflags':getattr(subprocess,'CREATE_NO_WINDOW',0)} if os.name=='nt' else {}
    old=real_popen([str(python),'app.py'],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**flags)
    children=[]; timer_errors=[]
    def launch(*args,**kwargs):
        if os.name=='nt':kwargs['creationflags']=getattr(subprocess,'CREATE_NO_WINDOW',0)
        child=real_popen(*args,**kwargs)
        command=args[0] if args else kwargs.get('args',[])
        if 'app.py' in command:children.append(child)
        return child
    def stop_old():
        try:
            if pilot:old.terminate()
            else:
                with urlopen(f'http://127.0.0.1:{port}/shutdown',timeout=3):pass
            old.wait(timeout=5)
        except Exception as exc:timer_errors.append(str(exc))
    try:
        wait_version(port,'0.0.1',pilot)
        timer=threading.Timer(0.5,stop_old);timer.start()
        expected_hash='0'*64 if mode=='checksum_failure' else hashlib.sha256(payload).hexdigest()
        args=argparse.Namespace(project_root=str(root),python_exe=str(python),parent_pid=old.pid,
            source_url=f'http://127.0.0.1:{server.server_port}/update.zip',expected_sha256=expected_hash,
            current_version='0.0.1',remote_version='0.0.2')
        log=io.StringIO()
        with contextlib.redirect_stdout(log),patch.dict(os.environ,{'PIP_NO_INDEX':'1','PIP_DISABLE_PIP_VERSION_CHECK':'1'}),patch('updater.subprocess.Popen',side_effect=launch):
            code=updater._run(args)
        timer.join(timeout=6)
        assert not timer_errors,timer_errors
        expected='0.0.2' if success else '0.0.1'
        wait_version(port,expected,pilot)
        status=json.loads((root/'update_logs/update_status.json').read_text())
        assert status['ok']==success
        assert code==(0 if success else 1)
        assert (root/'config.json').read_bytes()==config
        assert (root/'camera_captures/latest.jpg').read_bytes()==b'keep image'
        assert (root/'imported_jobs/keep.gc').read_bytes()==b'M5\n'
        assert downloads==['/update.zip']
        if not success:
            for rel,content in originals.items():assert (root/rel).read_bytes()==content,rel
            assert not (root/'new_module.py').exists()
        return {'case':mode,'passed':True,'updater_exit':code,'restarted_version':expected,
                'real_http_download':True,'real_parent_exit_wait':True,'real_restart':True,
                'private_files_preserved':True,'failure_rolled_back':mode=='pip_failure'}
    finally:
        for process in [old,*children]:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        server.shutdown();server.server_close();thread.join(timeout=3)


def main():
    with tempfile.TemporaryDirectory(prefix='ray5_updater_test_') as temp:
        folder=Path(temp).resolve()
        environment=folder/'.venv'
        subprocess.run([sys.executable,'-m','venv',str(environment)],check=True,capture_output=True,timeout=90)
        python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        with patch.dict(os.environ,{'PYTHONPATH':sysconfig.get_path('purelib'),'PYTHONDONTWRITEBYTECODE':'1'}):
            results=[run_case(folder,mode,python) for mode in ('success','checksum_failure','pip_failure','pilot_success')]
        if os.name=='nt':
            locked=folder/'locked-launcher';locked.mkdir()
            launcher=locked/'Ray5 Pilot.exe'
            system=Path(os.environ['SystemRoot'])/'System32'
            shutil.copy2(system/'ping.exe',launcher)
            replacement=locked/'replacement.exe';shutil.copy2(system/'hostname.exe',replacement)
            process=subprocess.Popen([str(launcher),'-t','127.0.0.1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                time.sleep(0.2);assert process.poll() is None
                try:shutil.copy2(replacement,launcher)
                except PermissionError:pass
                else:raise AssertionError('Expected Windows running-EXE lock was not reproduced')
                updater._copy_file(replacement,launcher)
                assert launcher.read_bytes()==replacement.read_bytes()
                assert process.poll() is None
                results.append({'case':'windows_locked_launcher','passed':True,'real_running_exe_lock':True})
            finally:
                process.terminate();process.wait(timeout=5)
    output=Path(__file__).resolve().parents[1]/'build/updater-integration'
    output.mkdir(parents=True,exist_ok=True)
    report={'passed':True,'cases':results,'release_installed_over_live_pilot':False,'firmware_commands_sent':0}
    (output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
