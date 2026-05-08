<img width="1600" height="2301" alt="ray5_dashboard_github_demo" src="https://github.com/user-attachments/assets/12c1ba5d-8ceb-4b87-aa7b-f083c6fd7aa0" />
<img width="1600" height="5340" alt="ray5_settings_github_demo" src="https://github.com/user-attachments/assets/f0df8dcb-9d3f-4788-a0ab-e66fc432d360" />

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
- Setting support so video can default to enabled or disabled
- Disabled-video placeholder when camera preview is turned off
- Dashboard/settings UI cleanup and layout refinements
- Settings page with expanded descriptions and examples
- 3D-printer G-code rejection safety scanner
- Optional sanitized Ray5 diagnostic endpoints
- Ray5 Pilot logo/favicon branding
- Portable Windows startup BAT file
- No old LightBurn TCP bridge

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
- Old LightBurn TCP bridge behavior is intentionally not included.

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
