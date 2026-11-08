


<img width="2400" height="2807" alt="01-dashboard-full" src="https://github.com/user-attachments/assets/ffa26d1b-f13b-46e4-bbfd-7f8e50e070c6" />

<img width="2400" height="1811" alt="02-settings-full" src="https://github.com/user-attachments/assets/d6cbe383-4fd3-41de-88a6-917165bb4179" />

<img width="2400" height="1893" alt="03-grbl-full" src="https://github.com/user-attachments/assets/ad5208fc-b1f0-49af-8489-88eea3aa00f6" />

<img width="2400" height="1686" alt="04-esp32-full" src="https://github.com/user-attachments/assets/3a3e1331-ea86-4c8f-94da-9b092cea4cb9" />



# Ray5 Pilot

A local, file-based controller for the Longer Ray5 using its ESP3D-style HTTP and WebSocket interfaces. Design in your laser software, export G-code, then use Pilot to frame, upload, run, and monitor it.

**Documentation status:** the usage sections describe the current working copy, including changes not yet published. `VERSION` remains `1.2.4`; the historical release notes below do not announce these changes as a new release.

- [Getting started](https://github.com/P0k3sm0t/Ray5-Pilot/wiki/Getting-Started)
- [Dashboard guide](https://github.com/P0k3sm0t/Ray5-Pilot/wiki/Dashboard)
- [Settings reference](https://github.com/P0k3sm0t/Ray5-Pilot/wiki/Settings)
- [Troubleshooting](https://github.com/P0k3sm0t/Ray5-Pilot/wiki/Troubleshooting)

## Web UI Demo Screenshots

These screenshots illustrate earlier builds; use the workflow sections below for the current sidebar layout and control locations.
### Dashboard

<a href="https://github.com/user-attachments/assets/f01bfa7e-c205-4ba6-a21e-b0cdf8155320">
  <img src="https://github.com/user-attachments/assets/f01bfa7e-c205-4ba6-a21e-b0cdf8155320" width="420" alt="Ray5 Pilot dashboard screenshot">
</a>

### Settings

<a href="https://github.com/user-attachments/assets/c9ab85da-c22a-471f-a403-151bad736fe1">
  <img src="https://github.com/user-attachments/assets/c9ab85da-c22a-471f-a403-151bad736fe1" width="420" alt="Ray5 Pilot settings screenshot">
</a>

### GRBL Settings

<a href="https://github.com/user-attachments/assets/7feac8cb-c26b-4ad5-b767-cf576de72868">
  <img src="https://github.com/user-attachments/assets/7feac8cb-c26b-4ad5-b767-cf576de72868" width="420" alt="Ray5 Pilot firmware settings screenshot">
</a>

### ESP32 Settings

<a href="https://github.com/user-attachments/assets/1742ba9b-e8f6-490c-adab-dcc286533380">
  <img src="https://github.com/user-attachments/assets/1742ba9b-e8f6-490c-adab-dcc286533380" width="420" alt="Ray5 Pilot firmware settings screenshot">
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

## Overview
A local Flask web controller for Longer Ray5 laser engravers using the ESP3D-style HTTP/WebSocket interface.

## Features

- Dashboard, Settings, GRBL, and ESP32 / ESP3D web UI
- Live Ray5 status via ESP3D WebSocket port 8849
- Reported X/Y coordinates and status diagnostics, when fresh controller data is available
- System check / health status
- Manual controls with jog pad
- Pause, Resume, and true Stop/Abort controls
- Improved Pause/Resume handling for GRBL real-time commands
- Stop Job defaults to M5 + Ctrl-X soft reset
- Unlock / Clear Alarm using M5 + $X
- Preset move button
- Live Console with smart auto-scroll
- Send commands through the web/manual console area

### GRBL Settings

- Read, back up, edit, and save Ray5/GRBL settings
- GRBL page replaces the older Firmware Settings page name
- Automatic local GRBL backup before saving setting changes
- Manual GRBL backup download
- GRBL backup files stored under `backups/grbl/`
- GRBL backup retention with newest backups kept automatically

### ESP32 / ESP3D Settings

- ESP32 / ESP3D page for Ray5 ESP3D information and EEPROM settings
- ESP3D info display from `[ESP800]`
- EEPROM/settings table from `[ESP400]`
- Edit and save ESP32 EEPROM settings through `[ESP401]`
- Automatic local ESP32 backup before saving setting changes
- Manual ESP32 backup download
- ESP32 backup files stored under `backups/esp32/`
- ESP32 WebSocket status summary with PAGEID, state, MPos, feed/spindle, and raw status
- ESP32 command box for G-code `commandText` commands and ESP commands

### Jobs, SD Card, and Imports

- Watched folder for saving G-code files directly for auto-import
- Imported Jobs workflow: import, frame, upload, upload + run, delete
- Direct SD card upload
- SD card file list, start, delete, and refresh
- SD Card Files auto-refresh pauses during active/busy machine states
- Auto-shorten long filenames when enabled
- Communication-loss safety lockout for active or recently started jobs
- Status card safety warning when Ray5 communication is lost during a possible active job
- 3D-printer G-code rejection safety scanner

### Timelapse and Camera

- Timelapse with manual start and automatic job-mode start from Imported Upload + Run or SD Start
- Background timelapse stop/save/build handling to keep status polling responsive
- Timelapse final frame delay after normal job completion for parked-head final images
- Camera stream proxy for RTSP or HTTP feeds
- Improved live camera stream lifecycle handling to reduce duplicate/stale stream requests
- Calibrated camera snapshot overlay for laser software/material alignment
- Camera deskew/postprocess/rotation/source-offset alignment settings
- Camera Overlay Alignment card with source X/Y offset and scaling explanations
- Enable/Disable Video button near the camera controls
- Full-size pop-out window for live camera video
- Disabled-video placeholder when camera preview is turned off

### Backups and Release Packaging

- Centralized backup folder structure:
  - `backups/esp32/`
  - `backups/grbl/`
  - `backups/updates/`
- Backup retention limit with configurable `max_keep_backups`
- Release zip builder script: `tools/make_release_zip.py`
- Release zip includes `Ray5 Pilot.exe`
- Release zip excludes runtime folders, backups, logs, `.git`, caches, and `config.json`
- SHA256 checksum `.txt` generated with each release zip

To test packaging without replacing anything in `dist`, run:

```powershell
python tools/make_release_zip.py --output-dir build/release-package-test
python -m unittest tools.test_release_zip
```

The ZIP contains the current application, web assets, launchers, and updater. Local
config, `.env` files, secret-term lists, temporary files, and runtime folders are
excluded. Packaging does not change `VERSION`, install an update, or publish a
release. Existing output files are protected; use a different output directory or
explicitly pass `--force` to replace a previously generated ZIP and checksum.

### Tools and Support

- Optional sanitized Ray5 diagnostic endpoints
- Portable Windows BAT and EXE launcher options
- Ray5 emulator support for offline Pilot testing
- Settings page with expanded descriptions and examples
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


## Cross-platform compatibility

Ray5 Pilot is a local Python/Flask web app and can run on multiple operating systems when Python and the required packages are available.

### Supported startup paths

| Operating system | Recommended startup | Manual startup |
|---|---|---|
| Windows | `Start_Ray5_Pilot.bat` or `Ray5 Pilot.exe` | `python app.py` |
| Linux | `./start-ray5-pilot.sh` | `python3 app.py` |
| macOS | `./start-ray5-pilot.sh` | `python3 app.py` |

The web interface opens at:

```text
http://127.0.0.1:5050
```

Ray5 Pilot is intended to stay local to the computer running it. Keep the web host set to `127.0.0.1` unless you understand the risk of allowing other devices on your network to access machine-control endpoints.

### Cross-platform notes

- Windows uses the included `.bat` launcher or optional `.exe` launcher.
- Linux/macOS can use `start-ray5-pilot.sh`.
- Linux may require `python3-venv` before the launcher can create a virtual environment.
- The Linux/macOS launcher creates `.venv`, installs requirements, creates `config.json` from `config.example.json` if needed, opens the Web UI when possible, and starts Ray5 Pilot.
- Cross-platform folder opening is handled through `platform_utils.py`.
- Camera snapshot and timelapse capture prefer the live preview frame when available, then fall back to the configured capture method.
- RTSP camera URLs are preserved exactly as entered in `config.json`; Ray5 Pilot only handles credential encoding at runtime when needed for ffmpeg fallback.
- Camera passwords should not be shared publicly, and logs should not expose raw or encoded RTSP passwords.

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

The EXE launcher runs `Start_Ray5_Pilot.bat`, which creates a local `.venv` and installs `requirements.txt` before starting the app. Python and the complete extracted project are still required. First startup requires internet access to install the packages, including OpenCV (`cv2`). Both launchers use this same environment.

The current BAT checks/upgrades pip and installs requirements on each launch. It opens the browser before Flask is guaranteed ready: wait for startup and reload if necessary. The launcher URL is fixed at 5050; after changing `web_ui.port`, open the configured URL manually. Python is not bundled, and ffmpeg for RTSP fallback/MP4 creation is a separate PATH dependency.

If an older EXE fails with `ModuleNotFoundError: No module named 'cv2'`, run `Start_Ray5_Pilot.bat` from the extracted project folder. It installs the dependencies and starts Pilot using `.venv`. Continue using the BAT until you replace the old EXE with the updated launcher; installing packages into `.venv` does not repair an old EXE that selects a different Python installation.

To rebuild the EXE from its source in a development environment:

```cmd
python -m pip install pyinstaller
python -m PyInstaller --clean --onefile --name "Ray5 Pilot" --icon web/static/favicon.ico launcher.py
copy /y "dist\Ray5 Pilot.exe" "Ray5 Pilot.exe"
```

Advanced users can still start Ray5 Pilot manually with:

```cmd
python app.py
```


#### Linux/macOS Shell Launcher

`start-ray5-pilot.sh` is the recommended launcher for Linux and macOS users.

First make the script executable if needed:

```bash
chmod +x start-ray5-pilot.sh
```

Then run:

```bash
./start-ray5-pilot.sh
```

The script will:

- change into the Ray5 Pilot folder,
- check for `python3`,
- create `.venv` if it does not exist,
- verify that pip works inside `.venv`,
- install `requirements.txt`,
- create `config.json` from `config.example.json` if missing,
- open `http://127.0.0.1:5050` when possible,
- start `app.py`.

If the script reports that venv/pip support is missing on Debian/Ubuntu-based Linux, run:

```bash
sudo apt update
sudo apt install python3-venv python3-pip
rm -rf .venv
./start-ray5-pilot.sh
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

Upgrade pip inside the virtual environment in the next step, not a different Python installation.

### 3. Create an isolated environment and install requirements

From inside the Ray5 Pilot folder, run:

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist config.json copy config.example.json config.json
```

Do not replace an existing `config.json`. The EXE/BAT launchers perform this setup for you; a manual `python app.py` launch does not install dependencies or open the browser.

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


## Manual setup and run on Linux/macOS

Ray5 Pilot can also be started manually from a terminal without using `start-ray5-pilot.sh`.

### 1. Open a terminal in the Ray5 Pilot folder

```bash
cd "/path/to/Ray5-Pilot"
```

### 2. Install venv support if needed

On Debian/Ubuntu-based Linux systems:

```bash
sudo apt update
sudo apt install python3-venv python3-pip
```

### 3. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install requirements

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 5. Create a local config if needed

```bash
cp config.example.json config.json
```

Then edit `config.json` or use the Settings page to set the Ray5 IP address and optional camera URL.

### 6. Start Ray5 Pilot

```bash
python app.py
```

Leave the terminal open while using Ray5 Pilot.

### 7. Open the Web UI

```text
http://127.0.0.1:5050
```

### 8. Stop Ray5 Pilot

Press:

```text
CTRL + C
```


## Network details
- Ray5 HTTP port: 8848
- Ray5 live status WebSocket port: 8849
- WebSocket path: /
- WebSocket subprotocol: arduino

Port 8848 is HTTP/API, not a raw GRBL/Tibbo listener. Pilot is a file-based web controller, not the separate LightBurn TCP/virtual-COM bridge. Keep the two projects and their ports/configs separate.

## Stop/Pause behavior
- Pause sends GRBL feed hold: !
- Resume sends GRBL cycle start: ~
- Stop Job defaults to M5 followed by Ctrl-X soft reset to terminate the run.
- Users can change Stop Mode to hold_only in Settings if they prefer pause-only behavior.
- Stop cancels the unsent remainder of an existing command batch. It cannot undo motion already accepted by the controller or guarantee delivery during a network failure.
- After a reset, inspect the machine and recover with Unlock/Home as appropriate. Network Stop is not a physical emergency stop.

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
- Physical overlay width/height can determine the written DPI. Verify imported size, disable Output on the image layer, and lock the reference before exporting G-code.
- The default snapshot folder is `camera_captures/`. Startup cleanup can remove old snapshots, including latest images, before an optional new capture; copy images you need elsewhere first.
- With history enabled, `keep_last: 0` means unlimited timestamped history. Capture-time retention protects `latest.jpg` and `latest_raw.jpg`; this is separate from startup cleanup.
- Video disabled does not mean the camera is disabled: snapshots and timelapse can use the configured fallback capture method. RTSP fallback using ffmpeg requires ffmpeg on PATH.
- Multiple live viewers still use separate camera connections. Close unused tabs/popouts if the camera becomes overloaded.


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

### Organized Settings page

Settings now uses category navigation: Connection, Camera & Alignment, Jobs & Files, Motion & Framing, Safety & Job Control, App & Updates, and Advanced. On narrow screens, category buttons wrap above the settings.

Camera connection tuning, snapshot cleanup, image processing, preset moves, upload compatibility, and recovery options are in expandable groups. Existing settings and help text remain available. GRBL firmware and ESP32 configuration keep their separate pages.

Changes remain pending when you switch categories. The bottom Save settings bar stays available while scrolling. Discard changes restores the last loaded or successfully saved values. Saving failures leave edits pending so you can retry. Restart Pilot after changing its Web UI host or port. Update checks run independently so they cannot hold up loading or saving settings.

For development, `node tools/test_settings_ui.cjs` runs the settings browser regression test with Playwright installed. Set `PLAYWRIGHT_MODULE` or `PLAYWRIGHT_CHROMIUM` if using an existing Playwright installation or Chromium executable. It uses an isolated local API fixture, checks category navigation, preserved field IDs, Save/Discard/error behavior, and responsive layouts, and writes screenshots to `build/settings-ui-test/`. It does not contact a Ray5 or change your local config.

## Dashboard workflow

The dashboard matches the Settings, GRBL, and ESP32 pages with sidebar navigation:

- **Workspace** keeps Camera & Overlay above the job actions, with Manual Controls beside the video and Connection Status below the controls. The diagonal jog buttons use arrows. Live Console stays below the workspace.
- **Jobs & SD Files** offers a full-width view of the same Imported Jobs and Ray5 SD Files tabs. Local imported jobs retain Frame, Upload, Upload + Run, and Delete. Machine SD files retain their existing Start/Delete, upload, storage, and selection tools. Upload does not mean Upload + Run.
- **Camera & Alignment** expands the same camera view. Snapshot/Open Folder/Open Latest/Open Raw remain below the feed. Reload, Test Camera, Calibrate Overlay, Open Video, and video enable/disable are under Video & alignment tools.
- **Timelapse** keeps manual capture, playback, multi-file deletion, recoverable sessions, and frame cleanup. Play brings the existing video player into the workspace.
- **Console & Diagnostics** provides the existing command sender/history and controller/system details. Reported position and connection details remain available in an expandable section.

Stop Job stays in the top action bar across sections. Alarm/unlock and communication-loss safety recovery remain available, with a global warning when needed. Laser test controls are expandable and keep the configured limits and confirmation behavior. Switching views preserves the original controls, file selections, and inputs; it does not recreate the cards or detach the camera/video node.

Some Ray5 firmware executes Ctrl-X but responds with HTTP 200 and the bare text `Error`. Soft-reset Stop now recognizes only that specific reset acknowledgement; the raw reply remains available. HTTP failures, timeouts, invalid-command replies, and laser-off command failures are not suppressed. Stop still uses the configured command sequence and may leave the controller alarmed until Unlock/Home. `python tools/test_stop_realtime.py` runs the isolated response-handling regression tests with the normal requirements installed.

For development, `node tools/test_dashboard_ui.cjs` runs the actual dashboard scripts against isolated API fixtures (using the same optional `PLAYWRIGHT_MODULE` and `PLAYWRIGHT_CHROMIUM` settings as the other UI tests). It covers preserved IDs, all eight jog directions, Home/preset/center, air assist, pause/resume/Stop, confirmed laser-test requests, imported and SD file actions, snapshots, calibration, video controls, timelapse/recovery, console/history, alarm/lockout recovery, and responsive layouts. Media playback is stubbed; real camera playback and physical motion still require supervised hardware verification. Screenshots go to `build/dashboard-ui-test/`. No laser is contacted and no local configuration is changed.

## GRBL page workflow

The GRBL page groups controller settings into Motion & Travel, Homing & Limits, Laser, Controller, All settings, and Diagnostics. Search by description or `$` code across every category. Z-axis settings are hidden by default in grouped views and remain available through search or Show Z-axis settings. Firmware-specific settings remain editable as raw numbers rather than being assigned guessed controls.

Read from Ray5 before editing. Edit values locally, use Changed only to inspect pending edits, and select Review changes to see current values, requested values, and exact GRBL commands. No writes occur until Apply reviewed changes is selected. The existing backend makes an automatic backup before writing; the UI then reads the controller again and marks matching values Verified. Failed, missing, or mismatched values retain their requested edits and show an explanation. If the verification read fails, another successful read is required before applying again. Refreshing with pending edits asks before replacing them.

Controller reads wait for an acknowledgement after the settings payload and a short settle interval. They require the standard core settings and, for the same device, the last complete key set. An incomplete read is retried once, then reported as failed rather than publishing a partial settings table or backup. Raw partial output remains available for diagnosis; do not change firmware settings just to fix a read timeout.

Download backup contains the last successfully loaded controller settings, not pending edits. Discard changes or a row's Undo restores its last controller value. Identity/network information and raw replies are available in collapsed sections.

For development, `node tools/test_grbl_ui.cjs` runs the isolated Playwright test (with the same optional `PLAYWRIGHT_MODULE` and `PLAYWRIGHT_CHROMIUM` settings as the Settings test). It exercises firmware reads, reviewed writes, automatic-backup failure responses, partial writes, read-back mismatches, timeouts, draft retention, downloads, and responsive layouts. It does not contact a laser. Screenshots are written to `build/grbl-ui-test/`.

## ESP32 page workflow

The ESP32 page separates Device Overview, Wi-Fi & Network, Device Services, Sensors & Hardware, Backups & Compare, and Advanced Tools. These are the Ray5 Wi-Fi module's settings, not Pilot's local configuration. Fields, options, and ranges come from the device; firmware-specific settings remain searchable in Advanced Tools.

Edits stay pending across categories. Choose **Review changes**, inspect the requested values, then **Apply reviewed changes**. Network changes require acknowledgement because they may disconnect Pilot. Non-secret values are read back to verify a write; failed or unverified edits remain pending. Passwords require explicit replacement, stay hidden in reviews and diagnostic displays, and are reported as accepted rather than read-back verified.

Backups & Compare can create/download a backup, view masked contents, and compare non-secret settings without writing anything. Verify the download is saved locally before relying on it. The existing automatic backup still runs before writes. Masked backups do not restore stored passwords.

Overview shows the last HTTP read and the age of the WebSocket status. Stale or missing controller reports show Unknown rather than a misleading Idle state. Use **Read from device** to refresh. Manual commands are locked until explicitly enabled in Advanced Tools; commands other than a status query require confirmation.

The ESP32 command tool's `?` query uses the fresh live-status collection path. An HTTP acknowledgement alone is not proof that GRBL is offline or idle. If no fresh controller report arrives, show the failure/unknown state and check the WebSocket connection rather than relying on an old report.

For development, `node tools/test_esp32_ui.cjs` runs isolated Playwright tests with the same optional `PLAYWRIGHT_MODULE` and `PLAYWRIGHT_CHROMIUM` settings described above. Coverage includes navigation, firmware metadata validation, draft retention, password masking, backup comparisons/downloads, reviewed saves, partial failures, read-back verification, offline states, and desktop/mobile layouts. Screenshots are saved to `build/esp32-ui-test/`. No laser is contacted and no real EEPROM is changed.

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

## Current working-copy changes (not released)

- Organized Dashboard, Settings, GRBL, and ESP32 workflows, with preserved job/machine controls and reviewed firmware edits.
- Fixed incomplete GRBL reads, ESP32 status-query reporting, Stop response handling, and reporting of HTTP 200 firmware errors such as an interface-busy failure.
- Reduced repeated bounds parsing and watcher hashing. Improved bounded G-code scans, modal/inch coordinate handling, numeric validation, config-save isolation, snapshot resource cleanup, and dashboard read scheduling.
- Hardened updater validation/recovery, duplicate and unsafe update guards, dependency-failure rollback, and replacement of a locked Windows launcher. File rollback does not undo pip's environment changes; backups are still necessary.
- Hardened release packaging with private-file exclusions, required-file validation, a separate test-output option, and explicit overwrite protection. The EXE launcher delegates dependency setup to the BAT and project-local `.venv`.

Offline checks passed 112 Python tests, packaging/checksum verification, updater-compatible extraction, and rendering of the four main pages from an isolated extracted copy. Supervised laser-off motion and read-only GRBL/ESP32 checks are recorded in `docs/AUDIT_2026-11-08.md`; updater isolation/recovery checks are in `docs/UPDATER_TEST_2026-11-08.md`.

**Not yet verified:** a complete fresh Windows EXE first-run/dependency-install/browser-launch test. The later attempt stopped before installation; package checks alone do not prove that workflow on another PC. No release has been made for these working-copy changes.

Developer checks, using the project's installed requirements:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tools -p 'test_*.py'
node tools/test_dashboard_reads.cjs
.venv/Scripts/python.exe tools/test_release_zip_integration.py
```

The packaging integration check builds under ignored `build/release-package-test/`, verifies current files and checksum, and tests a temporary extraction without hardware/network access. It does not install over the working app. Hardware tests are opt-in and must not be included in routine test runs.

## Ray5 Pilot v1.2.4
Ray5 Pilot v1.2.4 is a quick follow-up release to v1.2.3. It fixes release-package and update-related issues found during final fresh ZIP testing.

### Fixed
- Fixed first-run Settings behavior so a fresh install can save the Ray5 IP after `config.json` is created from `config.example.json`.
- Fixed release ZIP validation so `tools/safety_check.py` can run from an extracted release package without requiring `.git` or `.gitignore`.
- Hardened updater ZIP extraction to avoid unsafe ZIP paths during update installs.
- Preserved Linux executable permissions for `start-ray5-pilot.sh` in the release ZIP.
- Cleaned up placeholder/default values used in example configuration files.
- Confirmed release ZIP packaging excludes local/private runtime files such as `config.json`, logs, `.git`, `__pycache__`, `dist`, captures, timelapse output, and job folders.

### Why this release came so soon after v1.2.3

v1.2.3 added the main cross-platform camera, timelapse, Linux launcher, and release packaging improvements. During fresh Windows and Linux ZIP testing, a few packaging and first-run setup issues were found that should be fixed before wider use. v1.2.4 ships those cleanup fixes so new users have a smoother first-run experience and the updater/release package checks are more reliable.

## Ray5 Pilot v1.2.3
Ray5 Pilot v1.2.3 is a stability and cross-platform cleanup release focused on camera capture, timelapse reliability, Linux launcher support, release packaging, and status monitor configuration.

### Highlights
- Added a cross-platform file/folder open helper for Windows, Linux, and macOS.
- Added a Linux/macOS launcher script: `start-ray5-pilot.sh`.
- Improved Linux startup by creating and validating a Python virtual environment before launching.
- Added release ZIP packaging support for the Linux launcher and platform helper files.
- Improved manual camera snapshots so they use the live preview frame first when available.
- Improved timelapse frame capture so it uses the same safe camera capture path instead of calling removed/private capture methods.
- Preserved RTSP camera config exactly as entered by the user.
- Improved ffmpeg RTSP handling by trying the raw URL first and only using encoded credential fallback on authentication-related failures.
- Hardened ffmpeg error logging so RTSP usernames/passwords are not exposed in logs.
- Added status monitor settings to the Settings page:
  - Active Job Poll Interval
  - WebSocket Ping Interval
  - WebSocket Ping Timeout
- Added config defaults for the new status monitor settings in both `config.example.json` and `DEFAULT_CONFIG`.
- Updated safety checks to cover repo/release inclusion, platform open handling, camera snapshot architecture, timelapse capture path, ffmpeg hardening, and config key coverage.

### Camera and Timelapse Improvements
Manual snapshots now prefer the latest live preview frame when the camera preview is active. This avoids opening a second RTSP/ffmpeg connection when the app already has a valid camera frame.

Timelapse capture now uses a public camera capture path and supports the same cache-first behavior. This fixes the regression where timelapse could fail with a missing `_capture_bytes` method after the camera capture refactor.

### Linux Support
The new `start-ray5-pilot.sh` launcher helps Linux users start Ray5 Pilot more easily. It creates a `.venv` if needed, checks that pip is available, installs requirements, creates `config.json` from `config.example.json` if missing, opens the Web UI when possible, and starts the app.

On Debian/Ubuntu-based systems, users may need to install venv support first:

```bash
sudo apt update
sudo apt install python3-venv python3-pip
```

Then make the launcher executable and start Ray5 Pilot:

```bash
chmod +x start-ray5-pilot.sh
./start-ray5-pilot.sh
```

## v1.2.2 — Long Job Stability Update
Ray5 Pilot v1.2.2 focuses on improving stability during longer SD card jobs by reducing unnecessary traffic to the Ray5 ESP32 web interface.

### What Changed
- Reduced background ESP32 load during active jobs.
- System-check SD card probing is skipped while a job is running.
- Live status polling now slows down during active jobs instead of polling every second.
- WebSocket automatic ping is disabled by default.
- Ray5 HTTP requests are serialized through a shared request lock to avoid overlapping requests.
- Status card **Run Time** now displays in `HH:MM:SS` format instead of raw seconds.
- Pre-release safety checks now verify the long-job ESP32 load-reduction protections.

### Why This Matters
Some Ray5 users may see the WebSocket/status connection drop during longer jobs, especially after the machine has been running for a while. The job may continue on the Ray5, but Ray5 Pilot can lose live status updates and enter a communication safety lockout.

This update reduces repeated SD card/file checks, slows active-job status polling, disables extra WebSocket ping traffic, and prevents multiple Ray5 HTTP requests from hitting the ESP32 at the same time.

### Expected Result
During longer SD card jobs, Ray5 Pilot should be gentler on the Ray5 ESP32 and should maintain live status more reliably.

The Status card should continue to show:

- State
- Connection
- Progress
- File
- Run Time
- Timelapse state
- System check information

### Notes
If communication is lost while a job may still be active, Ray5 Pilot will still trigger the communication safety lockout. This is intentional. Always verify the Ray5 screen and machine state before clearing the safety lockout.

The safety lockout is not removed in this update. This release only reduces the chance of unnecessary connection drops during longer jobs.

## v1.2.1
Ray5 Pilot v1.2.1 focuses on final Dashboard status polish, improved laser/air/job reporting, stronger emulator compatibility, and release-safety checks.

### Added
- Added native Ray5 SD start command support using `[ESP220]/filename`.
  - SD Start and Upload + Run now use the shared SD run command builder.
  - Default Ray5 behavior now uses `[ESP220]` mode.
  - Legacy `$sd/run` and `$sd/runzip` modes remain available through config fallback.

- Added improved live job progress handling.
  - Ray5 Pilot now prefers fresh live websocket `Run` status lines containing `SD:<percent>,<file>`.
  - Progress now matches Ray5 native ESP32 status output.
  - Normal job completion still infers `100.00%` if needed.

- Added Pilot-local Run Time tracking.
  - Run Time now starts near zero when the job actually enters `Run`.
  - Ray5 `time:` status values are preserved separately as controller time, but are no longer used as Dashboard job runtime.
  - Pause/Hold and Resume behavior are handled by the local timer.

- Added improved Laser status display.
  - Dashboard now shows a simple `Laser: On` or `Laser: Off`.
  - Added separate `Laser Power` display based on commanded laser power when available.
  - Uses `$30` max laser/spindle value for percent conversion, with a default fallback.
  - Smooths brief zero-power samples during active jobs to prevent flickering.

- Added stronger emulator support.
  - Emulator now supports realistic Upload + Run and SD Start behavior.
  - Supports `[ESP220]/filename`, `$sd/run`, and `$sd/runzip`.
  - Simulates line-by-line G-code execution, SD progress, elapsed time, position updates, accessory flags, pause, resume, stop/alarm, unlock, and `$G` state.

- Added final safety-check coverage for v1.2.1 behavior.
  - Covers ESP220 SD run support.
  - Covers Upload + Run emulator compatibility.
  - Covers live Run+SD progress snapshots.
  - Covers local Run Time tracking.
  - Covers air pump and laser accessory flag parsing.
  - Covers Laser Power display behavior.
  - Covers clean file-name display in the Dashboard.

### Changed
- Cleaned up the Dashboard Status card.
  - Removed `Coordinate source`.
  - Removed `Machine status update`.
  - File names now hide the leading slash in the UI while keeping backend paths unchanged.

- Improved Air Pump display behavior.
  - `A:F` and `A:SF` indicate Air Pump On.
  - `A:S` indicates laser active with Air Pump Off.
  - Normal job completion sets Air Pump Off.
  - Missing `A:` fields no longer force a false state change.

- Improved Laser Power behavior.
  - Laser Power no longer relies only on instantaneous `FS` samples.
  - Commanded `S` values are tracked when available.
  - Brief `FS=0` samples during active jobs no longer make the Dashboard look like the laser power is constantly dropping out.

- Improved Upload + Run compatibility.
  - Upload + Run no longer gets blocked by devices or emulators that return `404` on `/` while still accepting commands/files.
  - Emulator-style upload success responses are accepted when the upload returns HTTP 2xx and no error marker.

### Fixed
- Fixed Upload + Run not starting jobs against the emulator after upload.
- Fixed SD Start progress showing tiny values when the wrong start method was used.
- Fixed Dashboard Run Time showing high Ray5 controller time instead of actual job runtime.
- Fixed Air Pump staying On after normal job completion.
- Fixed file display showing `/filename.gc` instead of `filename.gc`.
- Fixed Laser status flickering between On and Off during active laser jobs.
- Fixed Laser Power appearing misleadingly as zero when the laser job was still actively using a commanded power value.

### Notes
- Laser status is based on Ray5 status flags and command tracking. It is not physical electrical feedback from the laser module.
- Laser Power is based on commanded `S` values and `$30` max power when available. It is not a measured optical output value.
- Run Time is measured locally by Ray5 Pilot from observed job state transitions.
- Progress is based on Ray5 live `SD:<percent>,<file>` websocket status when available.

## v1.2.0
Ray5 Pilot v1.2.0 focuses on reliability, update handling, safer backups, improved GRBL and ESP32 status visibility, and stronger local-app hardening.

### Added
- Added a **GRBL Version** card to the GRBL page.
  - Collects `$I` identity/version information during GRBL refresh.
  - Displays firmware version, options, board, machine, software version, wavelength, working size, STA network info, and AP network info.
  - Includes a collapsed raw `$I` output section.
  - Redacts sensitive values such as AP password from raw identity output.

- Added **Air Pump** status tracking to the Dashboard status card.
  - Tracks `M8` as Air Pump On.
  - Tracks `M9` as Air Pump Off.
  - Parses `$G` parser state to confirm `M8` / `M9` when available.
  - Shows the air pump state as `On`, `Off`, or `Unknown`.

- Added a safe `/api/status/live` endpoint for UI websocket status display.
  - Provides only the status fields needed by the UI.
  - Keeps internal debug details out of normal page data.

- Added config-gated debug endpoints.
  - Debug endpoints now default to disabled.
  - Debug endpoints can be enabled in config when needed.
  - Optional localhost-only behavior is supported.

- Added a simple state-changing request guard.
  - POST, PUT, PATCH, and DELETE requests now require a Ray5 Pilot request header.
  - Helps reduce accidental or cross-site triggering of machine-control endpoints.

- Added minimal HTTP security headers.
  - Adds `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`.
  - Adds no-store cache headers for sensitive API/debug-style routes.

### Changed
- Updated the self-updater to use a package-driven copy system.
  - The updater now installs files included in the release package instead of relying on a fixed old allowlist.
  - New shipped files, templates, static assets, and tools are copied automatically.
  - Runtime/user files remain protected.

- Improved updater safety.
  - `config.json` is preserved during updates.
  - Runtime folders such as backups, logs, captures, timelapse, watched jobs, imported jobs, rejected jobs, and update work folders are protected.
  - Existing files are backed up before overwrite.
  - New files are logged during update.
  - Zero-copy updates are treated as failures.
  - Required templates are validated after update copy.

- Improved release packaging.
  - Release zip builder uses the `VERSION` file automatically.
  - Release zips use a single top-level folder for updater compatibility.
  - Release zips include `Ray5 Pilot.exe`, `VERSION`, app files, tools, templates, and static assets.
  - Release zips exclude runtime folders, backups, logs, caches, and `config.json`.
  - SHA256 checksum files are generated automatically.

- Improved ESP32 WebSocket Status display.
  - The ESP32 page now reads the safe status payload correctly.
  - WebSocket connected state, PAGEID, state, MPos, WPos, feed, spindle, reconnect count, and last raw status display correctly.

- Improved ESP32 backup safety.
  - ESP32 manual backups and automatic pre-save backups now redact sensitive values before writing to disk.
  - Passwords, pass fields, tokens, keys, secrets, and auth values are masked.
  - Sensitive `raw_value` fields are no longer stored in plaintext.

- Improved update asset safety.
  - GitHub release ZIP and checksum URLs are now validated before the updater is launched.
  - SHA256 verification remains in place.

### Fixed
- Fixed ESP32 WebSocket Status card incorrectly showing disconnected even when websocket status was live.
- Fixed the updater missing new files added after older releases.
- Fixed release packaging so future files included in the release zip are installed automatically.
- Fixed sensitive ESP32 backup data being stored in plaintext.
- Fixed update handling that could previously report success when no files were copied.
- Fixed 1.1.8-to-newer update compatibility issues caused by older updater behavior.
- Fixed missing-template risk for the ESP32 page by keeping an embedded fallback for older updater compatibility.

### Safety and Reliability Notes
- ESP32 and GRBL saves continue to create automatic local backups before writing settings.
- ESP32 backups now redact sensitive values before being written to disk.
- Debug endpoints are now disabled by default.
- State-changing requests now require a Ray5 Pilot request header.
- The Air Pump status is a command/parser-state tracker. It shows what the controller was told or reports through parser state; it is not physical electrical feedback from the pump.
- Existing user configuration and runtime folders are preserved during updates.

## v1.1.9
This release focuses on the new ESP32 / ESP3D tools, safer settings workflows, backup improvements, GRBL page cleanup, and release packaging.

### Added
- Added a new **ESP32 / ESP3D** page.
- Added ESP3D information display using `[ESP800]`.
- Added ESP32 EEPROM/settings display using `[ESP400]`.
- Added live ESP32 websocket status display with PAGEID, machine state, MPos, feed/spindle, and raw status.
- Added ESP32 command box support for both G-code commands and ESP commands.
- Added editable ESP32 EEPROM settings table.
- Added ESP32 EEPROM save support using `[ESP401]`.
- Added automatic local backups before saving ESP32 settings.
- Added automatic local backups before saving GRBL settings.
- Added backup organization under one root folder:
  - `backups/esp32/`
  - `backups/grbl/`
  - `backups/updates/`
- Added backup retention with `max_keep_backups`, defaulting to the latest 15 backups per category.
- Added a release zip builder script: `tools/make_release_zip.py`.
- Added SHA256 checksum generation for release zips.
- Added release packaging support for including `Ray5 Pilot.exe`.

### Changed
- Renamed **Firmware Settings** to **GRBL** throughout the user-facing UI and documentation.
- Updated the GRBL settings page layout to better match the ESP32 page style.
- Updated the ESP32 page to open in an editable settings layout similar to the GRBL page.
- Cleaned up ESP32 page styling with dark-theme inputs, compact rows, improved table width, and cleaner status badges.
- Simplified ESP32 backup controls to use a single **Download Backup** workflow.
- ESP32 and GRBL saves now create an internal backup automatically before writing settings.
- Release zip creation now excludes development/runtime files such as `.git`, `__pycache__`, `backups`, logs, runtime folders, and `config.json`.
- Updated README wording from “Firmware Settings” to “GRBL” where appropriate.

### Fixed
- Fixed ESP32 ESP command transport to use `commandText=` for Ray5-compatible ESP commands.
- Fixed ESP32 EEPROM option display so values no longer show as `[object Object]`.
- Fixed ESP32 info parsing so raw `[ESP800]` output is parsed into useful fields.
- Fixed backup folder handling after reorganizing backup paths.
- Fixed ESP32 and GRBL save visibility so save results show clearer status and backup information.
- Fixed release zip missing `Ray5 Pilot.exe`.
- Fixed release zip missing SHA256 checksum output.

### Safety Improvements
- ESP32 and GRBL settings are backed up automatically before save operations.
- Save operations abort if the automatic backup fails.
- Sensitive ESP32 values such as passwords remain masked in the UI and logs.
- Backup folders are ignored from release/source packaging.
- Backup retention prevents backup folders from growing indefinitely.

### Notes
- The **GRBL** page was previously called **Firmware Settings**.
- Manual **Download Backup** creates a user copy, while automatic backups are stored locally before settings are written.
- Existing old backup folders are not deleted automatically.

## Ray5 Pilot v1.1.8
### Highlights
- Added configurable RTSP transport handling for camera streams with **Auto**, **TCP**, and **UDP** options.
- Added a new **RTSP transport** setting in the Settings page Camera card.
- Default RTSP transport is now **TCP**, which is recommended for Wi-Fi cameras to reduce corrupted H.264 frames and FFmpeg/OpenCV decode warnings.
- FFmpeg camera capture now applies `-rtsp_transport tcp` or `-rtsp_transport udp` for RTSP camera URLs when selected.
- Live Dashboard video and **Open Video** streaming now apply the RTSP transport setting for RTSP camera URLs through the OpenCV/FFmpeg live-stream path.
- Auto mode leaves RTSP transport unforced and preserves the previous camera behavior.
- HTTP/MJPEG camera URLs are unchanged and are not affected by the RTSP transport setting.
- Snapshot and timelapse frame capture inherit the RTSP transport behavior when using the FFmpeg/RTSP camera path.
- Moved Firmware Settings `$$` collection into a background read/poll flow so the page stays responsive while settings are collected.
- Added locked watcher-state helpers so watched-folder status updates are handled safely across watcher/API paths.
- Improved G-code bounds parsing around `M0` / `M1` program-pause commands so stale laser-on modal state does not carry across a pause unless the laser is explicitly re-enabled afterward.
- Added Timelapse recovery support for leftover `session_*` frame folders when video building fails, FFmpeg is unavailable, or Ray5 Pilot exits before saving.
- Added recoverable timelapse session detection with **Recover Video** and **Delete Frames** actions in the Timelapse card.
- Timelapse session folders are deleted only after a recovered/built MP4 exists and has a non-zero size; failed builds preserve frames.
- Updated Imported Jobs **Refresh** so it checks the watched folder immediately, imports any new valid files, refreshes the card, and reports when no new watched-folder files are found.
- Expanded debug scrubbing for ESP/Ray5/Wi-Fi-style sensitive fields such as SSID, password, Wi-Fi, station, and access-point keys.
- Added an updater parent-process wait timeout so the updater does not wait forever if Ray5 Pilot fails to exit cleanly.
- Expanded `tools/safety_check.py` with checks for RTSP transport hardening, Firmware Settings background collection, watcher-state locking, G-code pause/bounds handling, timelapse recovery, Imported Jobs watched-folder refresh behavior, debug-token hardening, and updater wait-timeout markers.

### Notes

This release focuses on camera stability, background task responsiveness, watched-folder reliability, safer G-code bounds parsing, timelapse recovery, and additional release-safety validation.

For RTSP cameras, **TCP** is now the default transport because it is usually more reliable over Wi-Fi. If a camera does not work well with TCP, switch:

```text
Settings → Camera → RTSP transport
```

## Ray5 Pilot v1.1.7.1
### Hotfix
- Improved Unlock / Clear Alarm for Ray5 hard-limit alarms by using a staged Ctrl-X reset, laser-off, unlock, and status refresh sequence.
- Keeps the existing safety behavior of sending M5 laser-off before unlock.
- Adds/updates safety_check.py coverage for the hard-limit alarm clear sequence.

## Ray5 Pilot v1.1.7
### Highlights
- Improved large-file Upload and Upload+Run reliability when the Ray5 temporarily becomes busy while writing files to SD.
- Added an upload-busy status state so expected upload/write pauses no longer appear as false offline connection loss.
- Status card now switches to Uploading / Busy immediately when Upload, Upload+Run, or SD Upload is started.
- Upload+Run now verifies the uploaded file on the SD card after timeout/reconnect before blocking the start.
- Upload+Run now blocks auto-start if SD verification finds a reliable file-size mismatch, helping avoid running a possibly incomplete G-code file.
- Added a size-aware upload timeout for larger G-code files without changing normal request timeouts globally.
- Serialized SD file-listing requests during upload-related operations to reduce overlapping `/files` calls while the Ray5 is busy.
- Updated Upload+Run frontend messages to show in-progress and backend result messages more clearly.
- Added Timelapse status to the Dashboard Status card, including Disabled, Idle, Armed, Running, Paused, Saving, Error, and unavailable states.
- Renamed the Dashboard video pop-out button from “Pop Out Video” to “Open Video” for clearer wording.
- Consolidated backend timelapse status-label logic so the Status card and timelapse runtime use the same label source.
- Improved upload-busy cleanup so unexpected Upload+Run exceptions clear the busy state instead of waiting for the timeout.
- Improved release checksum parsing by preferring checksum lines that match the expected ZIP filename before falling back to broad single-hash parsing.
- Added and expanded `tools/safety_check.py` coverage for Upload+Run hardening, upload-busy status, Timelapse status, and release/update hardening markers.

## Ray5 Pilot v1.1.6
### Highlights
- Improved large-file Upload and Upload+Run behavior when the Ray5 becomes temporarily busy while writing to SD.
- Added an upload-busy status state so expected upload/write pauses no longer appear as false offline connection loss.
- Status card now switches to Uploading / Busy immediately when Upload, Upload+Run, or SD Upload is started.
- Upload+Run now verifies the uploaded file on the SD card after timeout/reconnect before blocking the start.
- Added a size-aware upload timeout for larger G-code files without changing normal request timeouts globally.
- Serialized SD file-listing requests during upload-related operations to reduce overlapping `/files` calls.
- Updated Upload+Run frontend messages to show in-progress and backend result messages more clearly.
- Added `tools/safety_check.py` coverage for Upload+Run hardening markers.

## Ray5 Pilot v1.1.5
### Highlights
- Added support for `*.sha256.txt` release checksum sidecar assets, with fallback to GitHub release asset digest metadata.
- Improved GitHub update-check diagnostics for 403/rate-limit and missing release metadata cases.
- Hardened in-app update installability checks while continuing to block `main.zip` / `refs/heads/main` install paths.
- Improved G-code bounds parsing for G92, bare G92, and G92.1 coordinate-offset behavior.
- Fixed laser-on bounds parsing so motion segments include both the start point and destination point.
- Updated `tools/safety_check.py` with static checks for updater/checksum and parser hardening.

## v1.1.4
### Highlights
- Final tagged-release updater verification release for in-app update packaging flow.
- Confirmed in-app update install uses GitHub release ZIP assets with SHA-256 digest verification.
- Added support for `*.sha256.txt` release checksum sidecar assets, with fallback to GitHub release asset digest metadata.
- Confirmed in-app update install rejects main-branch archives such as `refs/heads/main` / `main.zip`.
- Confirmed missing release ZIP/checksum metadata shows a clear blocked-install message instead of a false internet-check failure when GitHub release metadata is reachable.
- Confirmed Settings Support card only shows **Update Ray5 Pilot** when `update_installable` is true.
- Confirmed `Ray5 Pilot.exe` remains excluded from git source tracking expectations while still allowed for packaged release ZIP assets.
- Confirmed no-hardware release validation via `tools/safety_check.py`, including local secret denylist support through `tools/secret_terms.local.txt` (git-ignored) and `tools/secret_terms.local.example.txt`.

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
