"""Offline release packaging checks. Builds only in temporary directories."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import make_release_zip as release
import updater


class ReleaseZipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.out = Path(self.temp.name) / "output"
        self.addCleanup(patch.stopall)
        patch.object(release, "PROJECT_ROOT", self.root).start()
        patch.object(release, "DIST_DIR", self.root / "dist").start()
        for rel in release.REQUIRED_FILES:
            self.write(rel, "# fixture\n")
        self.write("VERSION", "1.2.4\n")
        self.write("config.example.json", "{}\n")
        self.write("README.md", "Public instructions\n")
        self.write("tools/public.py", "# public helper\n")
        self.write("web/static/dashboard.css", "body {}\n")
        self.write("Ray5 Pilot.exe", "fixture launcher")
        self.archive = self.out / "Ray5-Pilot-v1.2.4.zip"
        self.checksum = self.out / "Ray5-Pilot-v1.2.4.zip.sha256.txt"

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def build(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return release.main(["--output-dir", str(self.out), *args])

    def test_package_layout_content_checksum_and_modes(self):
        self.assertEqual(self.build(), 0)
        with zipfile.ZipFile(self.archive) as zf:
            self.assertIsNone(zf.testzip())
            names = zf.namelist()
            self.assertEqual(len(names), len(set(names)))
            for rel in (*release.REQUIRED_FILES, "tools/public.py", "web/static/dashboard.css", "Ray5 Pilot.exe"):
                member = "Ray5-Pilot-v1.2.4/" + rel
                self.assertEqual(zf.read(member), (self.root / rel).read_bytes())
            self.assertEqual(zf.getinfo("Ray5-Pilot-v1.2.4/start-ray5-pilot.sh").external_attr >> 16, 0o755)
            self.assertEqual(zf.getinfo("Ray5-Pilot-v1.2.4/app.py").external_attr >> 16, 0o644)
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.assertEqual(self.checksum.read_text(), digest + "  " + self.archive.name + "\n")

    def test_private_files_excluded_even_inside_included_directories(self):
        private = ["config.json", "tools/secret_terms.local.txt", "tools/.env", "tools/.env.production",
                   "tools/stale.tmp", "web/config.json", "web/private.bak", "web/private.bak.123", "tools/cache.pyc",
                   "web/.ENV", "tools/CONFIG.JSON", "tools/OLD.LOG", "web/secret~"]
        private += [f"tools/{name}/private.txt" for name in release.EXCLUDE_DIR_NAMES]
        private += ["web/LOGS/private.txt", "web/Snapshots/private.txt"]
        for rel in private:
            self.write(rel, "PRIVATE_SENTINEL_DO_NOT_PACKAGE")
        self.build()
        with zipfile.ZipFile(self.archive) as zf:
            for name in zf.namelist():
                self.assertNotIn(b"PRIVATE_SENTINEL_DO_NOT_PACKAGE", zf.read(name), name)
        self.assertTrue((self.root / "config.json").exists())

    def test_public_secret_terms_example_is_retained(self):
        self.write("tools/secret_terms.local.example.txt", "# placeholders only\n")
        self.build()
        with zipfile.ZipFile(self.archive) as zf:
            self.assertIn("Ray5-Pilot-v1.2.4/tools/secret_terms.local.example.txt", zf.namelist())

    def test_missing_required_file_aborts_before_writing(self):
        for rel in ("launcher.py", "updater.py", "requirements.txt", "web/templates/esp32.html"):
            with self.subTest(rel=rel):
                original = (self.root / rel).read_bytes()
                (self.root / rel).unlink()
                with self.assertRaisesRegex(RuntimeError, "missing required files"):
                    self.build()
                self.assertFalse(self.archive.exists())
                (self.root / rel).write_bytes(original)

    def test_invalid_or_missing_version_does_not_build(self):
        for version in ("", "../private", "1.2.4/secret", "unknown", "1.2.4\nother"):
            with self.subTest(version=version):
                self.write("VERSION", version)
                with self.assertRaises(ValueError):
                    self.build()
        (self.root / "VERSION").unlink()
        with self.assertRaisesRegex(RuntimeError, "VERSION"):
            self.build()
        self.assertFalse(self.archive.exists())

    def test_prerelease_version_supported(self):
        self.write("VERSION", "1.2.4-beta.1\n")
        self.build()
        self.assertTrue((self.out / "Ray5-Pilot-v1.2.4-beta.1.zip").is_file())

    def test_existing_artifacts_not_overwritten_without_force(self):
        self.build()
        original = self.archive.read_bytes(), self.checksum.read_bytes()
        self.write("app.py", "# changed\n")
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual((self.archive.read_bytes(), self.checksum.read_bytes()), original)

    def test_explicit_force_replaces_artifacts(self):
        self.build()
        self.write("app.py", "# changed\n")
        self.build("--force")
        with zipfile.ZipFile(self.archive) as zf:
            self.assertEqual(zf.read("Ray5-Pilot-v1.2.4/app.py"), (self.root / "app.py").read_bytes())
        self.assertTrue(self.checksum.read_text().startswith(hashlib.sha256(self.archive.read_bytes()).hexdigest()))

    def test_build_failure_preserves_previous_outputs_and_removes_staging(self):
        self.build()
        original = self.archive.read_bytes(), self.checksum.read_bytes()
        with patch.object(release, "_write_file_with_mode", side_effect=OSError("simulated read failure")):
            with self.assertRaisesRegex(OSError, "simulated read failure"):
                self.build("--force")
        self.assertEqual((self.archive.read_bytes(), self.checksum.read_bytes()), original)
        self.assertFalse(list(self.out.glob("release-stage-*")))

    def test_dist_launcher_priority_and_root_fallback(self):
        self.assertEqual(release._pick_executable(), self.root / "Ray5 Pilot.exe")
        self.write("dist/Ray5 Pilot.exe", "dist launcher")
        self.build()
        with zipfile.ZipFile(self.archive) as zf:
            self.assertEqual(zf.read("Ray5-Pilot-v1.2.4/Ray5 Pilot.exe"), b"dist launcher")

    def test_source_only_build_warns_if_no_executable(self):
        (self.root / "Ray5 Pilot.exe").unlink()
        messages = io.StringIO()
        with contextlib.redirect_stdout(messages):
            release.main(["--output-dir", str(self.out)])
        self.assertIn("source-only", messages.getvalue())
        with zipfile.ZipFile(self.archive) as zf:
            self.assertNotIn("Ray5-Pilot-v1.2.4/Ray5 Pilot.exe", zf.namelist())

    def test_external_and_private_resolved_paths_are_excluded(self):
        path = self.root / "web" / "apparently-public.txt"
        real_resolve = Path.resolve
        for target in (Path(self.temp.name) / "outside.txt", self.root / "config.json"):
            def resolve(p, *args, **kwargs):
                return target if p == path else real_resolve(p, *args, **kwargs)
            with patch.object(Path, "resolve", resolve):
                self.assertTrue(release._should_exclude(path))

    def test_old_timestamp_is_zip_compatible(self):
        path = self.root / "app.py"
        os.utime(path, (1, 1))
        self.build()
        with zipfile.ZipFile(self.archive) as zf:
            self.assertEqual(zf.getinfo("Ray5-Pilot-v1.2.4/app.py").date_time[0], 1980)

    def test_updater_accepts_generated_zip_without_installing_it(self):
        self.build()
        extracted = Path(self.temp.name) / "extracted"
        updater._safe_extract_zip(self.archive, extracted, lambda _: None)
        source = updater._detect_source_root(extracted, lambda _: None)
        self.assertEqual(source.name, "Ray5-Pilot-v1.2.4")
        for rel in updater.REQUIRED_TEMPLATE_PATHS:
            self.assertTrue((source / rel).is_file())
        self.assertEqual((source / "VERSION").read_text().strip(), "1.2.4")


if __name__ == "__main__":
    unittest.main()
