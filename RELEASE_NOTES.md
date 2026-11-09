# Ray5 Pilot V2.0.0 - Performance, Stability, and Camera Workflows

Ray5 Pilot 2.0 consolidates the file-based Ray5 workflow with SD-file framing,
site-matched camera tools, a shared camera pipeline, faster repeat startup, and
audited stability fixes. Existing control routes and local configuration remain
compatible; this is not a firmware update or a replacement of working controls.

## Highlights

- **Frame files already on SD:** retrieves the actual selected G-code using the
  native download or verified read-only ESP221 fallback, then generates a confirmed
  laser-off rectangle. No source-job execution, upload, or local filename-match fallback.
- **Shared camera streaming:** Dashboard/pop-out viewers share one reader and a
  bounded latest-frame buffer. Handoff keeps timelapse's frame cache warm instead
  of opening another RTSP reader for each viewer. Recovered capture errors clear.
- **Refreshed camera pages:** consistent Pilot theme, centered controls, responsive
  live-video view, connection feedback, and clearer embedded/standalone four-corner
  calibration with draft/save/reset guidance. Jog button labels/arrows are centered.
- **Faster repeat launches:** successful dependency setup is cached in the virtual
  environment. Changed/broken packages are checked again; unchanged launches skip
  pip/network setup. The app opens the configured browser URL once the server is ready.

## Reliability and Audit Fixes

- Preserve last good snapshots on capture/processing failure; stage image writes
  and clean capture history only after success. Respect disabled capture cleanup.
- Serialize concurrent imports and publish complete files atomically. Watched
  sources changed during copying are retried rather than imported/deleted unsafely.
- Reject malformed/non-object JSON and bad frame numeric inputs before actions,
  instead of returning route errors.
- Fix Air Off status reverting to On from cached accessory reports. Fresh reports
  without the accessory field correctly confirm Off after support is observed.
  No blind duplicate M9 command workaround was added.
- Bound RTSP open/read times, keep camera cache callbacks valid after component
  reload, handle malformed camera URLs safely, and enforce local debug access by
  actual peer address rather than a spoofable Host header.
- Keep complete GRBL reads, Stop/reset handling, updater recovery guards, and
  private/runtime-file exclusions from the previous stability work.

## Validation

- 153 offline Python regressions passed.
- Settings, GRBL, ESP32, Dashboard, and camera-tool browser suites passed with
  desktop/mobile layouts and no JavaScript runtime errors.
- Actual SD file retrieval and a supervised 94 x 94 mm frame at feed 700 completed
  with laser power reported zero and a final Idle state during development.
- A pump-only Idle test confirmed a single M9 removed the Ray5's air-assist flag.
- Real-camera handoff used one reader, saved four temporary timelapse frames, and
  built an MP4. No machine commands or local config changes occurred in that check.
- Release ZIP integrity/checksum, required assets, private-file filtering, updater
  extraction, clean-package safety scanning, and isolated page rendering passed.
- The extracted Windows EXE created a fresh virtual environment, installed all
  dependencies, and served all six pages on an isolated port. Automatic browser
  opening was disabled for this test; readiness/browser dispatch has fixture coverage.

## Upgrade and Safety

- Back up local config, important captures, and unreleased work before updating.
  Existing config/runtime data is excluded from the ZIP and protected by the updater.
  Normal configured startup snapshot cleanup is separate and can still remove images.
- Extract the complete package. Python must already be installed; the EXE is a
  launcher, not bundled Python. First dependency setup requires internet. ffmpeg is
  installed separately for ffmpeg capture and MP4 output.
- A clean install on a different physical PC remains unverified; local package and
  bootstrap checks do not prove every Windows/Python/environment combination.
- SD framing requires successful contents retrieval, fresh live Idle status,
  valid bounds, and confirmation. File-list success alone is insufficient. Bounds
  parsing is not a full interpreter for arbitrary G-code; verify travel physically.
- Network Stop is not a physical emergency stop; firmware-accepted movement cannot
  be retracted. Supervise the laser and keep camera references on non-output layers.
- Controller flags are not proof of a physical pump/relay's electrical behavior.
  If hardware disagrees, inspect safely rather than repeatedly clicking controls.
- Pilot remains an unauthenticated local single-user tool. Keep it off the Internet.
  Updater file rollback cannot undo pip changes or guarantee recovery from power loss.

See `docs/AUDIT_2.0.0.md` for the audit scope, findings, and remaining limitations.
