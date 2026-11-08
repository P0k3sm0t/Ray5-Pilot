# Docs

The main [README](../README.md) covers startup and current workflows. User guides are maintained in the separate [project wiki](https://github.com/P0k3sm0t/Ray5-Pilot/wiki), whose local checkout is separate from the application repository.

Current working-copy verification records:

- [Performance and stability audit](AUDIT_2026-11-08.md), including supervised laser-off motion/Stop checks and complete GRBL settings-read follow-up.
- [Updater verification](UPDATER_TEST_2026-11-08.md), including isolated recovery tests and preservation/rollback limits.

Historical test counts describe their respective checkpoints. The later packaging checkpoint passed 112 Python tests plus ZIP/checksum, updater extraction, and isolated main-page rendering checks. These are not a completed fresh Windows EXE first-run/dependency-install/browser-launch test; that attempt stopped before installation.

Local test artifacts remain under ignored `build/`. No documentation change publishes a release or changes `VERSION`. Avoid machine-local IPs, credentials, personal paths, captures, logs, and generated jobs in public documentation.
