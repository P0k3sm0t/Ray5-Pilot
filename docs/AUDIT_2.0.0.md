# Ray5 Pilot V2.0.0 Audit

## Scope

Reviewed the unreleased SD framing and camera-page work plus application routes,
HTTP/WebSocket handling, frame/Stop behavior, job imports/watchers, camera capture,
timelapse, configuration, launchers, updater, package filtering, and frontend wiring.
Existing controller routes and layout were preserved rather than replacing the
application with an untested rewrite.

## Findings Addressed

| Area | Finding | Fix |
|---|---|---|
| SD framing | Native file download can return HTTP 200 HTML | Require actual G-code; use verified read-only ESP221 fallback, never Run or a local filename match |
| Camera viewers | Each viewer opened a separate upstream decoder/connection | Shared latest-frame publisher, bounded storage, and brief idle grace across dashboard/pop-out handoff |
| Timelapse | A temporary capture failure stayed marked as Error after recovery | Successful recording clears the transient error; stream callbacks feed the current camera cache after component reload |
| RTSP | Open/read could block without explicit bounds | Five-second OpenCV/FFmpeg open/read timeouts for RTSP |
| Snapshots | Capture-time deletion happened before the next frame was captured; direct writes could expose incomplete images | Stage raw/processed images, publish complete files with atomic replacement, clean only after success, respect cleanup disablement |
| Imports | Same-name concurrent imports could overwrite each other; watcher copies could expose partial or changing files | Serialize target selection/publication, stage writes, and verify watched-copy digest before publishing/removing source |
| API inputs | Non-object JSON and invalid frame numeric input could cause route errors | Reject malformed request objects before actions; return a clear validation error for bad frame numbers |
| Air assist | Cached pre-command accessory flags could undo commanded Off; missing accessory field after M9 was ignored | Process only newer reports, recognize all-accessories-off after support is observed; no duplicate M9 workaround |
| Diagnostics | A localhost Host header could bypass a remote-address-only debug policy | Trust the actual peer address, not the supplied Host header |
| Camera URL masking | Malformed port could raise during status formatting | Handle invalid URLs without credential exposure; bracket IPv6 addresses correctly |
| Startup | Forced pip upgrade/setup and hardcoded early browser launch repeated on every start | Fingerprinted requirements/package/import checks skip unchanged pip setup; app opens configured URL once ready |
| UI/assets | New camera tools and updated scripts needed release cache invalidation | Shared camera theme, centered jog labels, responsive controls, and 2.0.0 asset versions |

## Validation

- Offline Python regressions cover existing behavior and each newly fixed edge case.
- Isolated browser suites cover Settings, GRBL, ESP32, Dashboard, and camera tools;
  they preserve existing control IDs and exercise desktop/mobile layouts and errors.
- A supervised SD-frame check retrieved actual machine file contents and completed
  a 94 x 94 mm frame at feed 700. The laser remained off and the machine returned
  to Idle. This was performed before the release audit, with no firmware writes.
- The pump-only hardware check sent M8 and a single M9 while Idle with laser power
  zero. Fresh reports showed A:F on, then no accessory flag after M9. A final M9
  cleanup was sent after observation; it was not needed to obtain the first Off
  report. Physical pump behavior should still be checked if it disagrees with GRBL.
- The real-camera handoff check used one reader for dashboard/pop-out subscribers,
  captured four temporary timelapse frames, and produced an MP4 with ffmpeg. No
  machine commands, personal image publication, or local config changes occurred.
- Packaging checks verify required assets, archive integrity, checksum, private-file
  exclusions, updater extraction, and isolated rendering with network access blocked.
- An extracted Windows EXE was launched with a fresh virtual environment and safe
  placeholder config on a separate port. Dependency installation/imports and six
  pages passed; browser auto-open was disabled to keep the test isolated. A cached
  follow-up setup check rejected any attempted pip invocation and passed.

Validation artifacts stay in ignored `build/`, not in the public release. The final
release notes record the completed suite counts and packaging results.

## Remaining Limits

- This is a local single-user Flask application without authentication, not an
  Internet-facing production control service. Keep it bound to loopback unless
  accepting the LAN risk. A network Stop is not a physical emergency stop.
- Bounds parsing is not a complete interpreter for arbitrary macros, subprograms,
  transforms, or every arc mode. Verify material, origin, workspace, and travel.
- HTTP acknowledgements and GRBL accessory flags do not prove a physical relay or
  electrical pump is functioning. Do not defeat electrical or laser safeguards.
- Real-camera checks validate the tested source, not uninterrupted availability or
  every firmware/camera/browser combination. External camera applications can still
  consume separate connections. A failed source may require refresh/reconnection.
- Snapshot publication is atomic per image, not a filesystem transaction spanning
  both images. Configured startup cleanup remains separate and may remove images;
  copy valuable images outside the managed output folder.
- Python and ffmpeg are separate system requirements. The EXE is a launcher, not a
  bundled Python runtime. A clean install on a different physical PC is not proven
  by local extraction/bootstrap tests alone. First dependency setup requires internet.
- Updater rollback protects application files and local runtime/config data, but
  cannot reverse package changes made by pip or guarantee recovery from power loss.
