<img width="1440" height="2298" alt="ray5_pilot_dashboard_screenshot" src="https://github.com/user-attachments/assets/25582ae1-ad2a-43f3-bcbe-e65f4d51ffe1" />
<img width="1440" height="6155" alt="ray5_pilot_settings_screenshot" src="https://github.com/user-attachments/assets/277e5b54-8db4-417c-9d10-0725c7917f8f" />

# Ray5 Pilot v1.0.1

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

## v1.0.1
- Added expanded Settings page descriptions and examples.
- Added Camera Overlay Alignment guidance for source X/Y offsets.
- Added 3D-printer G-code rejection safety scanning for SD upload, watched-folder import, manual import, Imported Jobs upload, and Upload + Run.
- Added sanitized Ray5 debug diagnostics endpoints.
- Sanitized ESP400 settings output so passwords/secrets are masked.
- Set Stop Job default behavior to true abort using M5 + Ctrl-X soft reset.
- Added Ray5 Pilot favicon/logo branding.
- Improved release safety around local-only config and private runtime files.
