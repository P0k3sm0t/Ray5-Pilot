# Ray5 Pilot v1.0.0

A local Flask web controller for Longer Ray5 laser engravers using the ESP3D-style HTTP/WebSocket interface.

## Features
- Dashboard web UI
- Live Ray5 status via ESP3D WebSocket port 8849
- X/Y live MPos display
- Manual controls with jog pad
- Unlock / Clear Alarm using M5 + $X
- Preset move button
- Imported Jobs workflow: import, frame, upload, upload + run, delete
- Direct SD card upload
- SD card file list, start, delete, refresh
- Camera stream proxy
- Calibrated camera snapshot overlay for LightBurn/material alignment
- Camera deskew/postprocess/rotation/source-offset alignment settings
- Camera Overlay Alignment card
- Live Console with smart auto-scroll
- Settings page
- No old LightBurn TCP bridge

## Setup
1. Download/clone Ray5-Pilot.
2. Run Start_Ray5_Pilot.bat.
3. Edit config.json or open Settings.
4. Set Ray5 IP.
5. Optional: configure RTSP camera URL.
6. Restart Ray5 Pilot.
7. Open http://127.0.0.1:5050.

## Important Network Details
- Ray5 HTTP port: 8848
- Ray5 live status WebSocket port: 8849
- WebSocket path: /
- WebSocket subprotocol: arduino

## Safety Warning
- Ray5 Pilot controls a laser engraver.
- Always supervise laser operation.
- Keep laser enclosure/eye protection/air assist/fire safety in place.
- Default web host is 127.0.0.1 for local-only use.
- Do not expose this app to the internet.
- No authentication is currently included.
- Binding to 0.0.0.0 allows LAN devices to access machine-control endpoints.

## Notes
- config.json is local/private and is not committed.
- config.example.json is only a template.
- Old LightBurn TCP bridge behavior is intentionally not included.
