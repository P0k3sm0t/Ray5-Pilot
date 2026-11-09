# Docs

The main [README](../README.md) covers startup and current workflows. User guides are maintained in the separate [project wiki](https://github.com/P0k3sm0t/Ray5-Pilot/wiki), whose local checkout is separate from the application repository.

Current working-copy verification records:

- [V2.0.0 release audit](AUDIT_2.0.0.md), including SD framing, camera handoff/timelapse, pump status, startup, and concurrency fixes.
- [Performance and stability audit](AUDIT_2026-11-08.md), including supervised laser-off motion/Stop checks and complete GRBL settings-read follow-up.
- [Updater verification](UPDATER_TEST_2026-11-08.md), including isolated recovery tests and preservation/rollback limits.

Historical test counts describe their respective checkpoints. V2.0.0 passed 153 Python regressions, five browser suites, ZIP/checksum/updater checks, and a local fresh-venv Windows EXE install serving six pages on an isolated port. Browser opening was disabled in that isolated install; dispatch/readiness has fixture tests. A clean install on a different physical PC remains unverified.

Local test artifacts remain under ignored `build/`. No documentation change publishes a release or changes `VERSION`. Avoid machine-local IPs, credentials, personal paths, captures, logs, and generated jobs in public documentation.
