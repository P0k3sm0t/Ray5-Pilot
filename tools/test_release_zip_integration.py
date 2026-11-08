"""Build/inspect the real package in ignored build/, without updating live Pilot."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import make_release_zip as release
import updater


SMOKE_TEST = r'''
import json
import socket
from unittest.mock import patch
def no_network(*args, **kwargs):
    raise AssertionError("Package smoke test must not contact hardware or network")
with patch.object(socket.socket, "connect", no_network), patch.object(socket.socket, "connect_ex", no_network):
    import app
    app.app.config["TESTING"] = True
    client = app.app.test_client()
    pages = {}
    for route in ("/", "/setup", "/machine-settings", "/esp32"):
        response = client.get(route)
        assert response.status_code == 200, (route, response.status_code)
        pages[route] = response.status_code
    for file in (app.BASE_DIR / "web/static").rglob("*"):
        if file.is_file():
            url = "/static/" + file.relative_to(app.BASE_DIR / "web/static").as_posix()
            assert client.get(url).status_code == 200, url
    assert app._read_local_version() == (app.BASE_DIR / "VERSION").read_text().strip()
    print(json.dumps({"pages": pages, "network_disabled": True, "version": app._read_local_version()}))
'''


def fingerprint(paths):
    return {str(p): {"sha256": release._sha256_file(p), "mtime_ns": p.stat().st_mtime_ns}
            for p in paths if p.is_file()}


def main():
    root = release.PROJECT_ROOT
    protected = [root / "VERSION", root / "config.json", root / "Ray5 Pilot.exe"]
    protected += [p for p in (root / "dist").glob("*") if p.is_file()]
    before = fingerprint(protected)
    # A distinct test folder avoids replacing even an earlier test artifact.
    output = root / "build/release-package-test" / time.strftime("%Y%m%d_%H%M%S")
    release.main(["--output-dir", str(output)])
    version = release._release_version()
    archive = output / f"Ray5-Pilot-v{version}.zip"
    digest = release._sha256_file(archive)
    assert archive.with_suffix(".zip.sha256.txt").read_text().strip() == digest + "  " + archive.name
    expected, _ = release._iter_included_files()
    prefix = f"Ray5-Pilot-v{version}/"
    with zipfile.ZipFile(archive) as zf:
        assert zf.testzip() is None
        assert len(zf.namelist()) == len(set(zf.namelist()))
        for source in expected:
            rel = source.relative_to(root).as_posix()
            assert zf.read(prefix + rel) == source.read_bytes(), rel
        exe = release._pick_executable()
        assert exe is not None, "Windows release should include the launcher"
        assert hashlib.sha256(zf.read(prefix + "Ray5 Pilot.exe")).hexdigest() == release._sha256_file(exe)
        for name in zf.namelist():
            rel = Path(name).relative_to(prefix.rstrip("/"))
            assert not release._should_exclude(root / rel), name
        file_count = len(zf.namelist())

    with tempfile.TemporaryDirectory(prefix="ray5_package_smoke_") as temp:
        extracted = Path(temp) / "extracted"
        updater._safe_extract_zip(archive, extracted, lambda _: None)
        source = updater._detect_source_root(extracted, lambda _: None)
        for rel in updater.REQUIRED_TEMPLATE_PATHS:
            assert (source / rel).is_file(), rel
        for file in source.rglob("*.py"):
            compile(file.read_text(encoding="utf-8-sig"), str(file), "exec")
        # Never copy the live config. This config is created only in the temporary extraction.
        safe = json.loads((source / "config.example.json").read_text(encoding="utf-8-sig"))
        safe["ray5"]["host"] = "YOUR_RAY5_IP"
        safe["camera"].update(enabled=False, video_enabled=False, auto_capture_on_start=False, auto_cleanup_on_start=False)
        safe["jobs"]["watch_enabled"] = False
        safe["status"]["websocket_enabled"] = False
        safe["timelapse"]["enabled"] = False
        (source / "config.json").write_text(json.dumps(safe), encoding="utf-8")
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        environment.pop("PYTHONPATH", None)
        smoke = subprocess.run([sys.executable, "-c", SMOKE_TEST], cwd=source, env=environment,
                               capture_output=True, text=True, timeout=45,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if smoke.returncode:
            raise AssertionError("Extracted package smoke test failed: " + smoke.stderr[-4000:])
        pages = json.loads(smoke.stdout.strip().splitlines()[-1])

    assert fingerprint(protected) == before, "Existing release/config/version/launcher changed"
    report = {"passed": True, "test_zip": str(archive), "sha256": digest,
              "files_verified_against_source": len(expected), "archive_file_count": file_count,
              "launcher_hash_verified": True, "updater_extraction_verified": True,
              "extracted_package_smoke_test": pages, "existing_release_files_unchanged": True,
              "firmware_commands_sent": 0, "release_published": False}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
