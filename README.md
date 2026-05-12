#Web Ui
<img width="2200" height="2681" alt="ray5_dashboard_demo_nocut" src="https://github.com/user-attachments/assets/952c8af7-6515-4712-a038-abe9f87b6d5b" />
<img width="2200" height="5744" alt="ray5_settings_demo_nocut" src="https://github.com/user-attachments/assets/3830e510-fd5c-4978-bf61-80d4d955680f" />
#Overlay Preview
<img width="1279" height="761" alt="overlay preview" src="https://github.com/user-attachments/assets/77777e23-7bee-4c1e-8914-bbff1fb05a02" />
#Make sure output is NOT selected so it wont include the image.
<img width="1279" height="761" alt="overlay preview 1" src="https://github.com/user-attachments/assets/7c6d36e4-194b-4501-b53d-559bb5820f51" />

# Ray5 Pilot

A local Flask web controller for Longer Ray5 laser engravers using the ESP3D-style HTTP/WebSocket interface.

## Features
- Dashboard web UI
- Live Ray5 status via ESP3D WebSocket port 8849
- X/Y live MPos display
- Manual controls with jog pad
- Pause, Resume, and true Stop/Abort controls
- Stop Job defaults to M5 + Ctrl-X soft reset
- Unlock / Clear Alarm using M5 + $X
- Preset move button
- Imported Jobs workflow: import, frame, upload, upload + run, delete
- Direct SD card upload
- SD card file list, start, delete, refresh
- Camera stream proxy
- Calibrated camera snapshot overlay for LightBurn/material alignment
- Camera deskew/postprocess/rotation/source-offset alignment settings
- Camera Overlay Alignment card with source X/Y offset explanations
- Live Console with smart auto-scroll
- Send commands through the web/manual console area
- Enable/Disable Video button near the camera controls
- Disabled-video placeholder when camera preview is turned off
- Settings page with expanded descriptions and examples
- 3D-printer G-code rejection safety scanner
- Optional sanitized Ray5 diagnostic endpoints
- Portable Windows startup BAT file

## Setup
1. Download/clone Ray5-Pilot.
2. Run Start_Ray5_Pilot.bat.
3. Edit config.json or open Settings.
4. Set Ray5 IP.
5. Optional: configure RTSP camera URL.
6. Restart Ray5 Pilot.
7. Open http://127.0.0.1:5050.

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

## Camera overlay notes
- latest_raw.jpg is the raw camera snapshot.
- latest.jpg is the processed LightBurn overlay.
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

## Safety warning
- Ray5 Pilot controls a laser engraver.
- Always supervise laser operation.
- Keep laser enclosure/eye protection/air assist/fire safety in place.
- Default web host is 127.0.0.1 for local-only use.
- Do not expose this app to the internet.
- No authentication is currently included.
- Binding to 0.0.0.0 allows LAN devices to access machine-control endpoints.
- Stop/Abort uses soft reset by default; verify behavior on your machine with a safe test job.

## Config notes
- config.json is local/private and is not committed.
- config.example.json is only a template.

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
