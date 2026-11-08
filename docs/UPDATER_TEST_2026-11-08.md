# Updater verification - November 8, 2026

No release was created, no version was bumped, no firmware settings were written,
and no release package was installed over the working Pilot project. Installation
and rollback tests used throwaway folders, local HTTP servers, and an isolated
Python environment. The real machine was not moved or fired.

## Live checks

- The Settings update section loaded without JavaScript errors and reported
  current/latest version 1.2.4, no update available, and hid the install button.
- The published v1.2.4 ZIP was downloaded into a temporary folder, not installed.
  Its 9,666,292 bytes matched the advertised SHA-256. Source-root detection,
  VERSION, requirements.txt and all four required templates passed validation.
- The working Ray5 remained Idle at X0/Y0, FS:0,0.

## Bugs fixed

- Download, checksum and archive failures now record failed status and restart the
  unchanged app instead of exiting outside recovery handling.
- Copy/dependency failures restore overwritten files and remove newly created
  files. A failed rollback leaves backups intact and does not launch mixed files.
- Dependency installation failures no longer claim update success.
- Failed attempts do not rotate away previous good backups or create empty backup
  sessions before any application files need backing up.
- Parent-exit timeout now blocks installation. Windows PID detection parses CSV
  instead of relying on an English tasklist message.
- Package validation checks required templates, requirements, requested VERSION
  and Python syntax before copying application files. Destination paths must stay
  within the project. ZIP traversal/drive/alternate-stream paths are rejected.
- Restart-launch failure rolls files back and attempts to launch the old app.
- A running Windows launcher can lock Ray5 Pilot.exe after app.py exits. The
  updater can rename that mapped image, install the replacement, and preserve the
  old image while still in use. Any retained *.bak file is ignored by Git.
- Duplicate update launches are blocked. Machine activity, uploads, timelapse
  recording/saving, communication lockout, and laser-test activity block updates.
  A laser test cannot start after an update has reserved the handoff.

## Tests

The complete offline Python suite passes 98 tests, including updater transactions,
metadata parsing, API handoff guards and recovery failures. Calls to dangerous
machine operations are mocked; nothing fires during those tests.

Five integration cases pass with actual local HTTP, process-exit waiting and
restarts where applicable:

1. Valid package: backs up old files and starts the new temporary version.
2. Bad checksum: preserves files and starts the old temporary version.
3. Dependency failure: rolls files back and starts the old temporary version.
4. Actual Pilot source in a sanitized temporary installation: updates and starts
   with the expected test version. Camera, watcher, test-fire and machine access
   are disabled; snapshot startup cleanup is disabled for preservation assertions.
5. Windows mapped-EXE lock: reproduces the lock with a temporary native executable
   and verifies launcher replacement while the old process is still running.

Config, environment, snapshots, logs and job preservation are checked. The
integration dependency environment is temporary; no packages are installed into
the working Pilot environment.

```text
.venv\Scripts\python.exe -m unittest discover -s tools -p "test_*.py"
.venv\Scripts\python.exe tools/test_updater_integration.py
```

Local reports and screenshots are in ignored build/updater-integration/.

## Later packaging checkpoint

The subsequent release-builder checks passed 14 additional offline tests (112
Python tests total), verified all 60 test-ZIP entries against current source and
launcher bytes, checked the SHA-256 sidecar and updater extraction, and rendered
Dashboard, Settings, GRBL, and ESP32 from a temporary extraction with network
access blocked. Existing release artifacts, local config and VERSION were unchanged.

The test ZIP is only an isolated build artifact, not a published release or an
installation over the live project. A requested clean Windows EXE first-run test
stopped before installation/browser verification; do not count that as passed.

## Limits

- No real in-place update was applied to the working project: that would overwrite
  unreleased changes. The production install button was not pressed.
- File rollback does not reverse changes pip might already have made to an
  environment. A failed dependency install may require environment repair.
- Abrupt power loss, arbitrary disk failure, antivirus interference and all future
  release/runtime combinations are not guaranteed by these tests. Backups remain
  important. A child-process launch is not a full production HTTP-health check.
- A mapped launcher *.bak may remain until its owning launcher process exits.
- Snapshot preservation by the updater is separate from Pilot's configured
  startup snapshot cleanup, which still operates normally after a restart.
- Update only while the laser and all transfers are safely stopped. Network Stop
  is not a physical emergency stop.
