# Web UI Demo Screenshots
### Dashboard

<a href="https://github.com/user-attachments/assets/310f0630-182f-42ac-8b9e-2949695c9b33">
  <img src="https://github.com/user-attachments/assets/310f0630-182f-42ac-8b9e-2949695c9b33" width="420" alt="Ray5 Pilot dashboard screenshot">
</a>

### Settings

<a href="https://github.com/user-attachments/assets/d5e1bc64-a3af-42f4-b7d1-dc81d31deb76">
  <img src="https://github.com/user-attachments/assets/d5e1bc64-a3af-42f4-b7d1-dc81d31deb76" width="420" alt="Ray5 Pilot settings screenshot">
</a>

### Firmware Settings

<a href="https://github.com/user-attachments/assets/758234ab-6f16-41f5-8d09-a1403b6bb6fb">
  <img src="https://github.com/user-attachments/assets/758234ab-6f16-41f5-8d09-a1403b6bb6fb" width="420" alt="Ray5 Pilot firmware settings screenshot">
</a>

### Overlay Accuracy Preview

<a href="https://github.com/user-attachments/assets/c6f0f90b-7a65-46d2-88ff-bce0b0c6a276">
  <img src="https://github.com/user-attachments/assets/c6f0f90b-7a65-46d2-88ff-bce0b0c6a276" width="420" alt="Ray5 Pilot overlay accuracy preview">
</a>

### Output Layer Note

Make sure **Output** is not selected so the reference image is not included in the laser job.

<a href="https://github.com/user-attachments/assets/a683917f-615b-4a31-be19-4062e4554d1e">
  <img src="https://github.com/user-attachments/assets/a683917f-615b-4a31-be19-4062e4554d1e" width="420" alt="Output disabled reference image example">
</a>

# Ray5 Pilot
A local Flask web controller for Longer Ray5 laser engravers using the ESP3D-style HTTP/WebSocket interface.

## Features
- Dashboard, Settings, and Firmware Settings web UI
- Live Ray5 status via ESP3D WebSocket port 8849
- Back up, edit, and save firmware settings
- System check / health status
- X/Y live MPos/WPos display
- Manual controls with jog pad
- Pause, Resume, and true Stop/Abort controls
- Communication-loss safety lockout for active or recently started jobs
- Status card safety warning when Ray5 communication is lost during a possible active job
- SD Card Files auto-refresh pauses during active/busy machine states
- Background timelapse stop/save/build handling to keep status polling responsive
- Timelapse final frame delay after normal job completion for parked-head final images
- Improved live camera stream lifecycle handling to reduce duplicate/stale stream requests
- Improved Pause/Resume handling for GRBL real-time commands
- Stop Job defaults to M5 + Ctrl-X soft reset
- Unlock / Clear Alarm using M5 + $X
- Preset move button
- Watched folder for saving G-code files directly for auto-import
- Imported Jobs workflow: import, frame, upload, upload + run, delete
- Direct SD card upload
- Auto-shorten long filenames when enabled
- SD card file list, start, delete, and refresh
- Timelapse with manual start and automatic job-mode start from Imported Upload + Run or SD Start
- Camera stream proxy for RTSP or HTTP feeds
- Calibrated camera snapshot overlay for laser software/material alignment
- Camera deskew/postprocess/rotation/source-offset alignment settings
- Camera Overlay Alignment card with source X/Y offset and scaling explanations
- Live Console with smart auto-scroll
- Send commands through the web/manual console area
- Enable/Disable Video button near the camera controls
- Full-size pop-out window for live camera video
- Disabled-video placeholder when camera preview is turned off
- Settings page with expanded descriptions and examples
- 3D-printer G-code rejection safety scanner
- Optional sanitized Ray5 diagnostic endpoints
- Portable Windows BAT and EXE launcher options
- Wiki pages for setup, usage, troubleshooting, and feature help

Firmware Settings was previously labeled Machine Settings.

## Setup
1. Download/clone Ray5-Pilot.
2. Run Start_Ray5_Pilot.bat or Ray5 Pilot.exe.
3. Edit config.json or open Settings.
4. Set Ray5 IP.
5. Optional: configure RTSP camera URL.
6. Restart Ray5 Pilot.
7. Open http://127.0.0.1:5050 if it does not automatically open.

### Launcher Options

Ray5 Pilot can be started manually with `python app.py`, or by using one of the included launch helpers.

#### BAT Launcher

The `.bat` launcher is a simple Windows batch file that starts Ray5 Pilot from the project folder. It opens a console window so you can see logs and errors while the app is running.

This is useful for troubleshooting because the commands are easy to inspect or edit.

#### EXE Launcher

`Ray5 Pilot.exe` is an optional Windows launcher for easier daily startup. It starts Ray5 Pilot from the project folder, keeps a console window available for logs, and opens the web interface at:

```text
http://127.0.0.1:5050
```

The EXE launcher is a convenience launcher, not a full standalone installer. Python, the Ray5 Pilot project files, and the required dependencies are still needed.

Advanced users can still start Ray5 Pilot manually with:

```cmd
python app.py
```

## Manual setup and run without the `.bat` file

Ray5 Pilot can be started manually from Command Prompt without using the included batch file.

### 1. Open Command Prompt in the Ray5 Pilot folder

Open the folder where Ray5 Pilot is saved, then right-click and open Command Prompt or Terminal there.

Or open Command Prompt and run:

```cmd
cd "C:\path\to\Ray5-Pilot"
```

Example:

```cmd
cd "C:\Users\YourName\Documents\GitHub\Ray5-Pilot"
```

### 2. Make sure Python and pip are available

Check Python:

```cmd
python --version
```

Check pip:

```cmd
python -m pip --version
```

If pip is missing, install/enable it with:

```cmd
python -m ensurepip --upgrade
```

Then upgrade pip:

```cmd
python -m pip install --upgrade pip
```

### 3. Install Ray5 Pilot requirements

From inside the Ray5 Pilot folder, run:

```cmd
python -m pip install -r requirements.txt
```

### Release Validation

Run before release:

```cmd
python tools/safety_check.py
```

### 4. Start Ray5 Pilot

Run:

```cmd
python app.py
```

Leave this Command Prompt window open while using Ray5 Pilot.

### 5. Open Ray5 Pilot in a web browser

Open your browser and go to:

```text
http://127.0.0.1:5050
```

If the app prints a different address or port in the Command Prompt window, use the address shown there instead.

### 6. Stop Ray5 Pilot

To stop Ray5 Pilot, click inside the Command Prompt window and press:

```text
CTRL + C
```

## Network details
- Ray5 HTTP port: 8848
- Ray5 live status WebSocket port: 8849
- WebSocket path: /
- WebSocket subprotocol: arduino

## Stop/Pause behavior
- Pause sends GRBL feed hold: !
- Resume sends GRBL cycle start: ~
- Stop Job defaults to M5 followed by Ctrl-X soft reset to terminate the run.
- Users can change Stop Mode to hold_only in Settings if they prefer pause-only behavior.

## Communication-loss safety behavior
If Ray5 Pilot loses communication with the Ray5 while a job may be active, recently started, running, paused, holding, jogging, or in an uncertain state, Ray5 Pilot enters a communication-loss safety lockout.

During this lockout:

- Automatic SD refresh is paused.
- System-check SD probing is skipped.
- Status/WebSocket reconnect attempts continue.
- Manual Stop Job and safety-related controls remain available.
- Ray5 Pilot does not automatically send laser-on, resume, test-fire, or other job-start commands.
- The user must verify the Ray5 screen and machine state before clearing the warning.

The safety lockout is intentionally conservative. It is designed to prevent Ray5 Pilot from resuming normal automatic behavior immediately after a reconnect when the machine state may still need to be checked physically.

## Camera overlay notes
- latest_raw.jpg is the raw camera snapshot.
- latest.jpg is the processed laser software overlay.
- Adjust scaling first
- Source X offset px moves the selected camera source area before deskew.
- Positive Source X samples farther right in the raw image.
- Negative Source X samples farther left.
- Positive Source Y samples farther down.
- Negative Source Y samples farther up.
- Use small offset values like 10 or 20 px and retest.


## 3D-printer G-code safety scanner
- Blocks obvious 3D-printer slicer files before import/upload/run.
- Looks for hotend/bed temperature commands, extrusion E moves, slicer metadata, and printer-only commands.
- Does not replace user judgment.
- Always verify files before running a laser job.

## Debug diagnostics
- /api/debug/ray5/device-info
- /api/debug/ray5/keepalive
- /api/debug/ray5/settings-info
- Diagnostic responses are sanitized to mask passwords, keys, tokens, secrets, credentials, and auth-like values.
- Keep Ray5 Pilot bound to 127.0.0.1 unless you understand the risk.

## Config notes
- config.json is local/private and is not committed.
- config.example.json is only a template.

## Ray5 screen filename note
Ray5 Pilot can upload files with long filenames, but the Longer Ray5 touchscreen may not display long filenames clearly. If you want to select and run a file directly from the Ray5 screen, keep the full filename **24 characters or less, including the extension**.

Ray5 Pilot also includes an Upload setting to automatically shorten long filenames. When enabled, uploaded filenames longer than 24 characters are shortened to **24 characters or less** while preserving the file extension when possible.

Example:
`test_grid_390x360.gcode`  
`large_alignment_grid_390x360_final.gcode` may upload successfully, but may not display clearly on the Ray5 screen.

## Timelapse final frame delay note
Ray5 Pilot includes a Timelapse setting called **Final frame delay after job ends (seconds)**. This setting waits briefly after a normal job completion before capturing one final timelapse frame.

This is useful when your G-code parks the laser head away from the material at the end of the job, because the final timelapse frame can show the completed work area instead of the head still over the material.

Set this value to `0` to keep immediate stop/build behavior.

## Safety warning
- Ray5 Pilot controls a laser engraver.
- Always supervise laser operation.
- Keep laser enclosure/eye protection/air assist/fire safety in place.
- Default web host is 127.0.0.1 for local-only use.
- Do not expose this app to the internet.
- No authentication is currently included.
- Binding to 0.0.0.0 allows LAN devices to access machine-control endpoints.
- Stop/Abort uses soft reset by default; verify behavior on your machine with a safe test job.
- Changing machine settings can affect motion limits, homing, acceleration, travel, and laser behavior. Back up your settings first and change only values you understand.
- If communication is lost during a job, Ray5 Pilot enters a safety lockout and requires the user to verify the Ray5 screen/machine state before normal automatic behavior resumes.
- Ray5 Pilot does not automatically send laser-on, resume, or test-fire commands after reconnecting.
- During communication-loss lockout, automatic SD refresh/system-check SD probing is paused.

## Liability disclaimer

Ray5 Pilot is provided as-is and is used at your own risk. This software controls a laser engraver, and incorrect configuration, machine behavior, G-code, camera alignment, firmware settings, or user operation can cause fire, equipment damage, material damage, personal injury, or other hazards.

The author/contributors are not responsible for damage, injury, loss, failed jobs, machine misconfiguration, unsafe operation, or any other consequences resulting from the use or misuse of this software.

Always supervise laser operation, verify all files and settings before running a job, keep proper fire safety equipment nearby, use appropriate eye protection/enclosure/ventilation, and test all machine-control features carefully on your own hardware before relying on them.

## v1.1.3
### Highlights
- Improved communication-loss safety lockout for active/recent jobs.
- Added Clear Safety Lockout support.
- Paused SD auto-refresh and SD system-check probing during unsafe/locked-out machine states.
- Cleaned up camera/video stream lifecycle handling.
- Improved video pop-out behavior.
- Prevented video enable/disable from restarting unrelated watcher/WebSocket/runtime services.
- Consolidated Video / Camera messages into the correct message area.
- Added setup guards and clean messages for Enable Video, Pop Out Video, Calibrate Overlay, Take Snapshot, Open Latest, and Open Raw.
- Moved timelapse stop/save/build work into a background worker.
- Added `timelapse.final_capture_delay_seconds` with default/range handling.
- Improved final timelapse frame reliability with capture locking, unique filenames, and retry logic.
- Made Manual Start Timelapse safer by requiring live Ray5 `Run` state.
- Added confirmation for Manual Stop Timelapse.
- Fixed real-time GRBL pause/resume command handling for `!` and `~`.
- Renamed user-facing “Machine Settings” wording to “Firmware Settings” while keeping internal routes/API/files unchanged.
- Reworked Settings Support card into Support and Update columns.
- Removed manual Check for Updates button and reused startup/cached update status.
- Settings Support card now reads the same cached GitHub update-check state as the Status card and no longer uses stale updater/apply-update status for normal availability display.
- GitHub update status now refreshes at startup and when Settings opens, with stale-safe background refresh while Ray5 Pilot is running.
- In-app update install now uses tagged release ZIP assets with SHA-256 digest verification.
- In-app update install is blocked when release checksum metadata is unavailable.
- Updated Longer support link to `https://eu.longer.net/pages/download-firmware`.
- Added/updated `tools/safety_check.py` for no-hardware release validation.
- Updated wiki/release documentation package for v1.1.3 wording and support changes.

### Validation
This release should be validated with:

```powershell
python -m py_compile app.py updater.py ray5_client.py config_manager.py job_manager.py camera_manager.py console_log.py calibrate_camera.py ray5_status_monitor.py gcode_safety.py tools/safety_check.py
node --check web/static/app.js
node --check web/static/setup.js
node --check web/static/machine_settings.js
python -m json.tool config.example.json
python tools/safety_check.py
```

## v1.1.2
### Added
- Added a communication-loss safety lockout for active or recently started Ray5 jobs.
- Added tracking for recent job activity from Imported Jobs Start and SD Start.
- Added a Status card safety warning when Ray5 Pilot loses communication while a job may still be active.
- Added a **Clear Safety Lockout** action so the user must verify the Ray5 screen/machine state before normal automatic behavior resumes.
- Added backend communication-safety state reporting through `/api/status`.
- Added camera stream client connect/disconnect logging with active client counts.
- Added guarded background handling for job-mode timelapse stop/save/build work.
- Added duplicate-prevention flags for background timelapse stop/build tasks.
- Added a configurable Timelapse final frame delay after normal job completion.
- Added Timelapse setting **Final frame delay after job ends (seconds)** so Ray5 Pilot can wait briefly for the laser head to park before capturing the final timelapse frame.
- Manual Start Timelapse is blocked if a timelapse is already armed, running, paused, stopping, or building.
- Renamed user-facing **Machine Settings** wording to **Firmware Settings** for clarity while preserving the existing route/API/file names for compatibility.

### Changed
- Improved live camera stream lifecycle handling to prevent duplicate or stale `/camera/stream` requests.
- Centralized Dashboard live-video start/stop behavior so stream state is managed consistently across Enable/Disable Video, Pop Out Video, refresh, error handling, placeholder display, and timelapse playback.
- Dashboard video now stops cleanly when the feed is popped out, disabled, unavailable, or replaced by timelapse playback.
- Improved `/camera/stream` cleanup visibility by wrapping the stream generator with connect/disconnect tracking.
- Paused SD Card Files auto-refresh while the Ray5 is in active/busy states such as `Run`, `Hold`, `Jog`, or `Door`.
- Paused SD Card Files auto-refresh during communication-loss safety lockout.
- Manual SD Refresh remains available, but auto-refresh no longer repeatedly hits the Ray5 SD endpoint while the controller may be busy or unreachable.
- SD auto-refresh now resumes after the machine returns to a safe non-busy state, with a short delay to avoid hammering the controller.
- Moved long job-mode timelapse stop/save/build work out of `/api/status` and into a guarded background worker.
- `/api/status` now stays responsive while timelapse output is being stopped, saved, or built.
- Preserved existing job-mode timelapse behavior for `Run`, `Hold`, resume, and terminal/Idle stop states.
- Job-mode timelapse can now capture one final frame after the Ray5 reports `Idle`, allowing end-of-job park moves to finish before the final image is saved.
- Improved Pause and Resume handling for GRBL real-time commands.
- Pause `!` and Resume `~` are now treated as successful when the command is successfully sent, even if the Ray5/ESP3D endpoint does not return a normal `ok` response.
- Improved Manual Controls messaging so successful Pause/Resume actions no longer show misleading `Error:` messages.

### Safety / Reliability
- If communication is lost while a job may be active, Ray5 Pilot now enters a safety lockout instead of immediately resuming automatic SD/system-check behavior when the connection returns.
- During communication-loss lockout, automatic SD refresh and system-check SD probing are skipped.
- Ray5 Pilot does **not** automatically send `M3`, `M4`, Resume, Test Fire, or other laser-on commands during reconnect.
- The safety lockout does **not** auto-send `M5`; the user must verify the machine state and use the proper controls if needed.
- Manual Stop Job and safety-related controls remain available during lockout.
- SD refresh failures now clear loading/in-progress state cleanly so the SD Card Files card does not stay stuck on busy.
- Timelapse stop/build queueing prevents duplicate background workers for the same timelapse session.
- `/api/status` no longer blocks on long timelapse output processing.
- Final timelapse frame delay is skipped for unsafe or uncertain stop reasons such as offline, alarm, door, sleep, not configured, or communication-loss lockout.

### Fixed
- Fixed repeated/stale Dashboard camera stream starts that could happen around video toggle, pop-out, refresh, error, and timelapse playback transitions.
- Fixed possible duplicate live camera streams between the Dashboard and pop-out video window.
- Fixed SD Card Files auto-refresh continuing during active jobs and causing the card to get stuck on busy.
- Fixed SD Card Files auto-refresh continuing during Ray5 communication loss.
- Fixed job-mode timelapse stop/build work blocking status polling.
- Fixed misleading Pause/Resume failure messages when the machine actually paused or resumed correctly.
- Fixed Manual Controls showing messages such as `Error: Resume sent.` or `Error: Error` for successful real-time Pause/Resume commands.

### Notes
- The communication-loss safety lockout is intentionally conservative. If Ray5 Pilot loses communication while a job may still be active, verify the Ray5 screen and machine state before clearing the warning.
- SD auto-refresh is paused during active/busy states to avoid stressing the Ray5 controller while a job is running.
- Manual SD Refresh is still available when needed, but automatic refresh behavior is now more cautious.
- Timelapse output still builds as before, but long stop/save/build work now runs outside the status request path.
- Pause and Resume use GRBL real-time commands, which may not return a normal `ok` response from the Ray5/ESP3D HTTP endpoint even when they work correctly.
- Set Timelapse final frame delay to `0` to keep immediate stop/build behavior.

## v1.1.1
### Added
- Added live video pop-out support for the Dashboard **Video / Camera** card.
- Added Dashboard placeholder behavior while live video is popped out.
- Added automatic Dashboard live video restore when the pop-out window is closed.
- Added `web/templates/camera_popout.html` for the standalone live video pop-out page.
- Added a 100 mm option to the Manual Controls **Step (mm)** dropdown.
- Added fixed Manual Controls feedrate options:
  - 500
  - 1000
  - 1500
  - 2000
  - 2500
  - 3000
- Added automatic Timelapse card refresh after a successful timelapse is created.
- Added support for keeping completed timelapse playback visible in the Video / Camera card after playback ends.
- Added atomic `config.json` save behavior to reduce the chance of config corruption during interrupted saves.
- Added machine dimension validation so invalid `machine.min_x/max_x` or `machine.min_y/max_y` values are rejected.
- Added safer updater logging for Python/virtual-environment detection during requirements installation.
- Added updater cleanup/rotation behavior for update work, backup, and log folders.
- Added camera external-open URL scheme validation.
- Added guard logic to prevent launching multiple camera calibration subprocesses at once.
- Added version ranges to `requirements.txt`.

### Changed
- Renamed the Settings **GitHub / Support** card to **Support**.
- Renamed the Status card timestamp label from **Last update** to **Machine status update** so it is clear the timestamp refers to Ray5/machine communication.
- Improved live video pop-out behavior so the main Dashboard does not show two live feeds at once.
- Improved watched-folder auto-import behavior so same-name files can be imported again after the previous imported copy was deleted.
- Improved watched-folder filename conflict handling with numeric suffixes such as `test_1.gcode` and `test_2.gcode`.
- Improved Settings reload behavior so an active timelapse is stopped cleanly before runtime camera/status/job objects are replaced.
- Improved updater restart behavior by keeping the new Windows console restart flow for better `CTRL+C` behavior.
- Improved README wording, launcher notes, and manual setup formatting.
- Updated Manual Controls feedrate dropdown values to a cleaner fixed set.
- Hid `System Volume Information` from the SD Card Files list.
- Hardened `web_ui.debug` behavior so debug mode is blocked/rejected on non-localhost host bindings.

### Safety / Reliability
- `config.json` is now written through a temporary file and atomically replaced.
- Invalid machine work-area limits are rejected before save.
- Flask debug mode is prevented on non-local bindings to reduce risk if users expose the app on a LAN.
- External camera opening now only allows expected camera/browser URL schemes.
- Camera calibration launch is protected against repeated rapid subprocess starts.
- The updater now logs whether requirements are being installed inside a likely virtual environment or into the current Python environment.
- Update temporary files, backups, and logs now have safer cleanup/retention behavior.
- `System Volume Information` is hidden only from the SD Card Files UI; Ray5 Pilot does not delete or modify that folder.

### Notes
- The live video pop-out uses Ray5 Pilot’s existing camera stream/proxy behavior and does not expose direct camera credentials.
- Timelapse playback now remains visible after playback completes until live video is re-enabled or another timelapse is selected.
- Watched-folder imports no longer treat a previously imported filename as permanently blocked after the imported copy is deleted.
- The root `Ray5 Pilot.exe` launcher is allowed in the repository while general build artifacts remain ignored.
- `__pycache__/` may appear when Python runs, but it is ignored and should not be committed.

## v1.1.0
### Added
- Added a controlled **Update Ray5 Pilot** workflow from the Settings page.
- Added an **Update Ray5 Pilot** button in the GitHub / Support card that appears only when an update is available.
- Added a separate `updater.py` script to perform updates after the main app shuts down.
- Added post-update status reporting so the Settings page can show whether the last update succeeded or failed after Ray5 Pilot restarts.
- Added local update logs and status output under `update_logs/`.
- Added automatic Settings page reconnect/refresh behavior after an update restart.
- Added app **Version** display to the Dashboard Status card.
- Added startup **Update** status display to the Dashboard Status card.
- Added a one-time startup update check that compares the local `VERSION` file against the GitHub main-branch `VERSION`.
- Added support for detecting dotted versions such as `1.0.9.1` and `1.1.0`.
- Added support for including the official root `Ray5 Pilot.exe` launcher in the repository while keeping build artifacts ignored.

### Changed
- **Check for Updates** now compares the local `VERSION` file against the GitHub main-branch `VERSION` file.
- The update workflow now matches the **Download Latest Source** behavior by using the GitHub main branch source ZIP.
- The updater now backs up current source files before replacing them.
- The updater copies only allowlisted Ray5 Pilot source/UI files.
- The updater preserves local/private files and runtime folders.
- The updater now restarts Ray5 Pilot in a new Windows console so `CTRL+C` should stop the restarted app normally.
- The Settings page now waits for Ray5 Pilot to come back online after an update and reloads automatically when reachable.
- The Dashboard Status card now reports the current app version and cached update status.
- Version comparison now handles variable-length dotted versions and leading `v` values.

### Safety / Update Behavior
- Updates are never installed silently.
- Checking for updates does not download, install, or modify files.
- Updating requires the user to click **Update Ray5 Pilot** and confirm before anything is changed.
- Ray5 Pilot blocks the update if the Ray5 appears to be running or paused.
- The updater preserves:
  - `config.json`
  - runtime folders
  - camera captures
  - timelapse output
  - imported jobs
  - watched G-code files
  - rejected jobs
  - logs
  - local-only build folders
- The updater backs up current files before copying new source files.
- After updating, Ray5 Pilot restarts and reports update success or failure in the GitHub / Support card.

### Notes
- The self-update feature downloads the latest source ZIP from the GitHub main branch.
- The updater is intended for normal source/UI updates, not full installer-style upgrades.
- If an update fails, check the update log in `update_logs/`.
- Manual download remains available through **Download Latest Source**.
- The included `Ray5 Pilot.exe` is a launcher convenience, not a full standalone installer. Python and project dependencies are still required unless a future packaged installer is added.

## v1.0.9
### Added
- Added a controlled **Update Ray5 Pilot** workflow from the Settings page.
- Added an **Update Ray5 Pilot** button in the GitHub / Support card that appears only when an update is available.
- Added a separate `updater.py` script to handle update operations after the main app shuts down.
- Added post-update status reporting so the Settings page can show whether the last update succeeded or failed after Ray5 Pilot restarts.
- Added local update log/status output under `update_logs/`.

### Changed
- **Check for Updates** now compares the local `VERSION` file against the main-branch `VERSION` file on GitHub.
- The update workflow now matches the **Download Latest Source** behavior by using the GitHub main branch source ZIP.
- The update process now backs up current source files before replacing them.
- The updater copies only allowlisted Ray5 Pilot source/UI files.
- The updater preserves local/private files and runtime folders.

### Safety / Update Behavior
- Updates are never installed silently.
- Checking for updates does not download, install, or modify files.
- Updating requires the user to click **Update Ray5 Pilot** and confirm before anything is changed.
- Ray5 Pilot blocks the update if the Ray5 appears to be running or paused.
- The updater preserves:
  - `config.json`
  - runtime folders
  - camera captures
  - timelapse output
  - imported jobs
  - watched G-code files
  - rejected jobs
  - logs
  - local launcher/build files
- The updater backs up current files before copying the new source files.
- After updating, Ray5 Pilot restarts and reports update success or failure in the GitHub / Support card.

### Notes
- The self-update feature downloads the latest source ZIP from the GitHub main branch.
- The updater is intended for normal source/UI updates, not full installer-style upgrades.
- If an update fails, check the update log in `update_logs/`.
- Manual download is still available through **Download Latest Source**.

## v1.0.8
### Added
- Added a **Support** card to the Settings page.
- Added quick links for:
  - GitHub Repository
  - Open an Issue
  - Wiki Home
  - Check for Updates
  - Download Latest Source
- Added a **Check for Updates** action that compares the local Ray5 Pilot version against the latest GitHub release.
- Added a **Download Latest Source** link that opens the latest source ZIP from the main branch.

### Changed
- Updated the Dashboard layout for a cleaner card flow:
  - Timelapse now spans the full width near the top.
  - Status, Video / Camera, and Manual Controls now sit together in one row.
  - Imported Jobs and SD Card Files now sit side-by-side.
  - Live Console now spans the full width at the bottom.
- Matched the Status, Video / Camera, and Manual Controls card heights so the middle dashboard row looks cleaner.
- Aligned Imported Jobs and SD Card Files so their top edges line up.
- Updated Settings page wording to be more inclusive of general laser software workflows instead of sounding LightBurn-only.
- Updated Settings page cache/version reference for v1.0.8.

### Notes
- The update checker is informational only.
- Ray5 Pilot does not auto-download, auto-install, or modify local files when checking for updates.
- **Download Latest Source** opens the GitHub main-branch source ZIP.
- GitHub Issues can be used to report bugs, request features, or share logs/screenshots when troubleshooting.

## v1.0.7
### Added
- Added a dedicated **Machine Settings** page for Ray5/GRBL controller settings.
- Added Machine Settings navigation links to the Dashboard and Settings pages.
- Added support for reading controller settings with `$$`.
- Added automatic parsing of GRBL-style settings such as `$0=10`, `$30=1000`, `$130=400.000`, and similar.
- Added a uniform editable Machine Settings table with setting number, description, current value, new value, unit/notes, and status.
- Added known descriptions and units for common GRBL settings.
- Added **Download Backup** for raw `$$` machine settings output.
- Added changed-only Machine Settings save support using safe `$number=value` commands.
- Added strict validation for Machine Settings saves to prevent arbitrary commands or reset commands.
- Added a raw `$$` output/debug section to help diagnose devices that return settings asynchronously.
- Added diagonal jog buttons to Manual Controls for all four diagonal directions.
- Added a **Center** button in the jog pad to move the laser head to the configured bed/work-area center.
- Added combined XY jog support so diagonal moves are sent as one jog command instead of two separate axis moves.

### Changed
- Manual Controls now use a full 3x3 jog pad:
  - diagonal jogs in all four corners
  - X/Y jogs on the sides
  - Center button in the middle
- The previous center Home button was moved below the jog pad.
- Home and Go To Preset now sit together in a centered row below the jog pad.
- The preset helper text now reads: “Preset moves to configured X/Y position.”
- Machine Settings now handles Ray5/ESP3D asynchronous `$$` output by collecting WebSocket response lines after the command is sent.
- Machine Settings save results are preserved after refresh instead of being overwritten by “Loaded X setting(s).”
- Camera System Check behavior was tightened so cached `latest.jpg` / `latest_raw.jpg` files no longer mark the camera as working.
- Camera test status is now based on backend-confirmed real camera operations only.
- README screenshot formatting now uses clickable thumbnail-style images.
- README wording was broadened from LightBurn-specific wording to general laser software wording where appropriate.

### Fixed
- Fixed Machine Settings initially loading zero settings when the HTTP command response returned only `ok` and the real `$$` output arrived asynchronously through the WebSocket stream.
- Fixed Machine Settings input fields jumping or losing focus while typing.
- Fixed Machine Settings save messages being overwritten by automatic reload messages.
- Fixed cached camera snapshot serving from incorrectly marking **Camera test passed** as Yes.
- Fixed Manual Controls diagonal jog button labels showing `?` instead of proper diagonal arrows.
- Fixed Manual Controls layout so Home is no longer mixed into the jog pad.
- Fixed diagonal movement so each diagonal button sends one combined XY jog command.

### Notes
- Always use **Download Backup** before changing machine settings.
- Machine Settings save only sends changed rows and only allows validated numeric `$number=value` commands.
- Factory reset commands such as `$RST=$`, `$RST=#`, and `$RST=*` are not exposed on the Machine Settings page.
- Diagonal jog commands use the selected Step and Feedrate values.
- The Center button uses configured machine/work-area limits to calculate the bed center.

## v1.0.6
### Added
- Added Upload setting `auto_shorten_long_filenames` to automatically shorten SD-uploaded filenames longer than 24 characters (including extension) for Ray5 screen readability.
- Added Settings > Upload checkbox: **Auto-shorten long Ray5 filenames**.

### Changed
- Dashboard camera health now updates from backend-confirmed camera operations only.
- Live camera stream health now updates from backend frame-read success/failure in the stream pipeline instead of browser image-load events.
- Settings save now preserves `status.live_status_stale_seconds` invisibly.
- Updated Camera settings label text to **Snapshot history filename prefix** with clarifying help text.

### Fixed
- Fixed System Check inconsistency where `PAGEID captured` or `SD card list working` could remain stale `Yes` while Ray5 was offline.
- Fixed SD Card Files auto-load trigger from System Check transitions when Ray5 comes online after app startup.
- Fixed camera health ambiguity where frontend load events could mark camera test as passed without backend frame confirmation.

## v1.0.5
### Added
- Added automatic Imported Jobs refresh after a successful manual import.
- Added lightweight Imported Jobs auto-refresh while the dashboard is open so watched-folder/background imports appear without pressing Refresh.
- Added clearer Status card layout with State, PageID, X/Y, Feed, Laser, Alarm, Job, Connection, Source, Coordinate source, and Last update.
- Added README note explaining that Ray5 Pilot can upload long filenames, but files intended to be selected from the Ray5 touchscreen should be 24 characters or less including the extension.
- Added manual setup instructions for running Ray5 Pilot without the `.bat` file.

### Changed
- Moved PageID directly under State in the dashboard Status card.
- Updated Status behavior so non-live status is shown as Offline/fallback_offline instead of synthetic.
- Offline fallback now shows zeroed position/feed/laser values instead of stale or synthetic live-looking data.
- Timelapse frame capture is now separated from normal Camera Overlay snapshot files.
- Timelapse raw mode writes directly to the active timelapse session folder without updating `camera_captures/latest_raw.jpg`.
- Timelapse processed mode creates corrected/deskewed frames in memory and writes directly to the timelapse session folder without updating `camera_captures/latest.jpg`.
- Normal Camera Snapshot behavior remains unchanged and still updates `latest.jpg` and `latest_raw.jpg`.
- Removed visible Synthetic fallback setting from the Settings page while preserving the internal config key for compatibility.
- Updated Status settings help text to describe live WebSocket status and offline fallback behavior.

### Fixed
- Fixed Timelapse affecting/overwriting Camera Overlay snapshot files during capture.
- Fixed Imported Jobs card not refreshing automatically after new files were imported.
- Fixed offline/fallback status being able to appear like synthetic live machine status.
- Fixed stale Timelapse CSS targeting removed `#timelapseState`.
- Fixed confusing Synthetic fallback wording in Settings.
- Fixed Status card layout so PageID no longer sits on the far-right side of the card.

### Notes
- Timelapse still supports both image sources: full raw camera frame and overlay-corrected snapshot style.
- Timelapse output is now isolated to timelapse session folders and should not disturb overlay/snapshot files.
- Imported Jobs now refreshes automatically every 5 seconds while the dashboard is open.
- Offline fallback cannot auto-start Timelapse because it no longer reports fake Run/Idle/Hold states.

## v1.0.4
### Added
- Added multi-select file management for Imported Jobs, including Select All, Clear Selection, selected count, and Delete Selected.
- Added multi-select file management for SD Card Files, including Select All, Clear Selection, selected count, and Delete Selected.
- Added a full-width Timelapse dashboard card above the Video/Camera card.
- Added Timelapse file listing, multi-select delete, selected count, and per-file Play controls.
- Added Timelapse playback inside the existing top Video/Camera card.
- Added Timelapse Start and Stop buttons for manual timelapse control.
- Added Timelapse runtime state handling for manual and job-based sessions.
- Added automatic timelapse arming for Imported Upload + Run.
- Added automatic timelapse arming for SD Card Start.
- Added Timelapse settings card with enable/disable, snapshot interval, playback FPS, and image source controls.
- Added Timelapse image source option for overlay-corrected snapshots or full raw camera frames.
- Added separate Timelapse playback FPS so capture interval and final MP4 speed are controlled independently.

### Changed
- Timelapse manual Start/Stop is now button-controlled and independent of printer Idle/Hold/Run state.
- Timelapse job mode now follows Ray5 state: Run starts capture, Hold pauses capture, Run resumes capture, and Idle stops/saves.
- Timelapse MP4 generation now uses playback FPS instead of snapshot interval as frame timing.
- Timelapse session folders now use stable session IDs and matching video filenames.
- Successful Timelapse MP4 builds now safely clean up the matching session frame folder.
- Deleting Timelapse videos now also attempts to safely delete the matching session folder when a matching session ID exists.
- Timelapse messages now use one bottom message line in the Timelapse card instead of multiple status locations.
- Camera postprocess scaling now works as source-area scaling before deskew when deskew is enabled, preventing black borders when scaling the overlay view.
- Camera calibration click mapping now uses displayed image bounds so embedded calibration clicks align correctly.
- Test Fire defaults and help text now use S50 as the safe default value instead of S200.
- Settings now preserve hidden/internal Timelapse values such as output directory instead of overwriting them during save.
- Config example coverage was aligned with current default configuration keys.

### Fixed
- Fixed embedded Camera Calibration marker offset when the calibration image is resized inside the dashboard.
- Fixed camera postprocess scale appearing to do nothing when using values below 1.0.
- Fixed Timelapse manual sessions stopping early when the printer was Idle.
- Fixed Timelapse Stop messages being overwritten by automatic refresh messages.
- Fixed Timelapse delete messages being overwritten by refresh messages.
- Fixed Imported Jobs and SD Card Files delete messages being overwritten by refresh messages.
- Fixed Timelapse Stop handling so in-progress captures are handled more safely before building output.
- Fixed camera capture race risk between manual snapshots and Timelapse captures by adding capture locking.
- Fixed Timelapse disabled behavior so disabled Timelapse does not start or arm.
- Fixed missing/default configuration inconsistencies between config manager defaults and config.example.json.
- Fixed remaining S200 wording/fallback inconsistencies in Settings.

### Notes
- Timelapse must be enabled in Settings before manual or automatic Timelapse capture will run.
- Imported Upload Only does not arm Timelapse.
- Imported Upload + Run and SD Card Start arm Timelapse automatically when enabled.
- Manual Start Timelapse starts capture directly and Manual Stop Timelapse stops/saves directly.
- If ffmpeg is not available, Timelapse frames are preserved and a warning is shown instead of silently failing to build an MP4.

## v1.0.3
- Fixed Test Fire for Ray5 screen-style stationary M4 behavior.
- Test Fire now uses direct S-value mode and sends the command with PAGEID.
- Test Fire sequence now uses `M4 S<value>` followed by forced `M5` cleanup.
- Simplified the Safety settings card so Test Fire only shows the needed user-facing controls.
- Moved 3D-printer G-code scanner settings from the Safety card to the Upload card.
- Fixed `/api/camera/snapshot` so it no longer calls a nonexistent camera method.
- `/api/camera/snapshot` now returns the latest processed snapshot or a clean JSON message when no snapshot exists.
- Improved watched-folder reload reliability to avoid duplicate watcher threads after repeated settings saves.
- Cleaned duplicate status monitor reload logging.
- Cleaned up Camera card controls and layout.
- Added dashboard camera video enable/disable behavior with a placeholder image.
- Fixed video stream containment so the camera feed cannot overlap the header/banner.
- Added/kept responsive two-column Settings page layout on desktop.
- Moved the Live Console raw command input under the console feed.
- Verified camera calibration route/template alignment for the overlay calibration page.

## v1.0.2
- Added send-command support through the web/manual console area.
- Added Enable Video / Disable Video button near camera controls.
- Added setting support so dashboard video can default to enabled or disabled.
- Added disabled-video placeholder behavior for cleaner dashboard presentation.
- Added dashboard/settings UI cleanup and layout refinements.
- Added missing Ray5-host configured guard to `/api/laser/off`.
- Improved G-code bounds parsing so `M5`, `M9`, and `S0` no longer permanently suppress later valid motion.
- Added `G2/G3` arc awareness and arc-bounds warnings where bounds are approximated.
- Improved camera capture temp-file safety with collision-safe temp filenames and cleanup in `finally`.
- Improved watched-folder duplicate detection with stronger signatures, including SHA256, so changed same-name/same-size files are not skipped.
- Reduced background-thread/global-state race risk with shared app-state locking and safer runtime start/reload/stop behavior.
- Avoided starting watcher/status threads on module import.
- Improved watcher/status monitor lifecycle safety to reduce duplicate background threads during reloads.

## v1.0.1
- Added expanded Settings page descriptions and examples.
- Added Camera Overlay Alignment guidance for source X/Y offsets.
- Added 3D-printer G-code rejection safety scanning for SD upload, watched-folder import, manual import, Imported Jobs upload, and Upload + Run.
- Added sanitized Ray5 debug diagnostics endpoints.
- Sanitized ESP400 settings output so passwords/secrets are masked.
- Set Stop Job default behavior to true abort using M5 + Ctrl-X soft reset.
- Added Ray5 Pilot favicon/logo branding.
- Improved release safety around local-only config and private runtime files.
