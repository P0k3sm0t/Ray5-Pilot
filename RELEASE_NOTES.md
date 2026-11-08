# Ray5 Pilot V1.2.5 - Workflow and Stability Update

V1.2.5 improves everyday usability, responsiveness, and recovery while preserving the file-based Ray5 workflow and existing machine controls.

## Highlights

- Organized Dashboard, Settings, GRBL, and ESP32 interfaces with consistent sidebar navigation.
- Manual controls beside the camera, Connection Status underneath, diagonal jog arrows, and globally accessible Stop Job.
- Clear separation of local Imported Jobs and Ray5 SD Files, including Frame, Upload, Upload + Run, and machine-file Start/Delete actions.
- Reviewed firmware edits, pending-change tracking, backups, read-back verification, and clearer failure messages.
- Updated README, wiki guidance, and full-page screenshots with a camera placeholder and example imported job.

## Fixes and Reliability

- Complete GRBL settings-read checks and a retry for incomplete dumps, rather than treating partial output as a successful settings table or backup.
- Fresh ESP32 live-status query handling instead of inferring controller state from HTTP acknowledgements.
- Improved Stop/reset response handling and cancellation of unsent frame/batch commands. Real firmware errors, including HTTP 200 error replies, remain visible.
- Faster unchanged-job refreshes and less watcher hashing, with bounded G-code scans, modal/inch-coordinate fixes, and invalid-number rejection.
- Safer concurrent config saves, bounded HTTP/MJPEG snapshots, camera resource cleanup, and corrected snapshot retention behavior.
- Coalesced dashboard reads and bounded read timeouts without automatically retrying machine actions.
- Updater package validation, unsafe-activity/duplicate-install guards, recovery/rollback improvements, and support for replacing a locked Windows launcher.
- EXE launcher delegates to the BAT's project-local virtual environment and dependency setup.
- Release packaging validates required files, excludes private/runtime data, generates a SHA-256 sidecar, and protects existing output from accidental overwrite.

## Validation

- 112 offline Python regression tests passed.
- Isolated Settings, GRBL, ESP32, and Dashboard browser checks passed.
- ZIP/checksum, updater-compatible extraction, and isolated main-page rendering checks passed.
- Supervised laser-off motion/Stop and read-only GRBL/ESP32 checks were performed during development without firmware-setting changes.

## Requirements and Safety

- Extract the entire package. Python must already be installed on PATH; the EXE is a launcher, not bundled Python. First-time dependency setup needs internet access.
- ffmpeg must be installed separately and available on PATH for ffmpeg camera capture and MP4 timelapse output.
- A complete fresh-PC EXE first-run/dependency-install/browser-launch test remains pending. Packaging checks alone do not establish that result.
- Back up local config and unreleased work before updating. File rollback does not reverse package changes already made by pip.
- Updater preservation and normal startup snapshot cleanup are separate: configured cleanup can still remove snapshots after restart.
- Soft-reset Stop may leave the controller alarmed and require safe Unlock/Home recovery. Network Stop is not a physical emergency stop.
- Keep Pilot local, supervise the laser, verify framing, and keep camera reference images on non-output layers.

Local config, credentials, captures, logs, backups, virtual environments, and generated job files are intentionally excluded from the release ZIP.
