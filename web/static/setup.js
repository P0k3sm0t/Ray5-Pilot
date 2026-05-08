async function api(url, method='GET', body=null){const opt={method,headers:{}};if(body){opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body)}const r=await fetch(url,opt);return r.json()}
function v(id){return document.getElementById(id)}
function setVal(id,value,fallback=''){const el=v(id);if(!el){console.warn(`Missing settings field: ${id}`);return}el.value=(value??fallback)}
function setChecked(id,value,fallback=false){const el=v(id);if(!el){console.warn(`Missing settings field: ${id}`);return}el.checked=(value??fallback)}
function unwrapConfigResponse(d){
  if (d && d.config && d.config.ray5) return d.config;
  if (d && d.config && d.config.config && d.config.config.ray5) return d.config.config;
  if (d && d.ray5) return d;
  throw new Error("Invalid /api/config response shape");
}
let settingsLoaded = false;

function load(cfg){
  cfg = cfg || {};
  const ray = cfg.ray5 || {};
  const web = cfg.web_ui || {};
  const cam=cfg.camera||{};
  const jobs = cfg.jobs || {};
  const framing = cfg.framing || {};
  const machine = cfg.machine || {};
  const mc = cfg.manual_controls || {};
  const safety = cfg.safety || {};
  const sd = cfg.sd_files || {};
  const up = cfg.upload || {};
  const jc = cfg.job_control || {};
  const st = cfg.status || {};
  const csl = cfg.console || {};

  setVal('ray_host', ray.host, '');
  setVal('ray_port', ray.port, 8848);
  setVal('ray_timeout', ray.request_timeout_seconds ?? ray.timeout ?? 4, 4);
  setVal('web_host', web.host, '127.0.0.1');
  setVal('web_port', web.port, 5050);

  setChecked('cam_enabled', !!cam.enabled, false);
  setChecked('cam_video_enabled', (cam.video_enabled !== false), true);
  setVal('cam_stream', cam.url||cam.stream_url||'', '');
  setVal('cam_snapshot', cam.snapshot_url||'', '');
  setChecked('cam_proxy_enabled', (cam.proxy_enabled!==false), true);
  setVal('cam_proxy_path', cam.proxy_path||'/camera/stream', '/camera/stream');
  setVal('cam_reconnect', cam.reconnect_seconds||5, 5);
  setVal('cam_capture_method', cam.capture_method||'ffmpeg', 'ffmpeg');
  setVal('cam_output_dir', cam.output_dir||'camera_captures', 'camera_captures');
  setVal('cam_filename_prefix', cam.filename_prefix||'ray5_bed', 'ray5_bed');
  setChecked('cam_save_history', !!cam.save_history, false);
  setVal('cam_keep_last', (cam.keep_last??0), 0);
  setChecked('cam_auto_cleanup', (cam.auto_cleanup_on_start!==false), true);
  setChecked('cam_cleanup_capture', (cam.cleanup_on_capture!==false), true);
  setVal('cam_timeout', cam.timeout_seconds||15, 15);
  const rotVal = String((cam.postprocess&&cam.postprocess.rotate_degrees) ?? 90);
  setVal('cam_rot', (['0','90','180','270'].includes(rotVal)?rotVal:'0'), '0');
  setChecked('cam_deskew_enabled', !!(cam.deskew&&cam.deskew.enabled), false);
  setVal('cam_deskew_points', JSON.stringify((cam.deskew&&cam.deskew.source_points)||[]), '[]');
  setVal('cam_deskew_out_w', ((cam.deskew&&cam.deskew.output_size&&cam.deskew.output_size[0])||1200), 1200);
  setVal('cam_deskew_out_h', ((cam.deskew&&cam.deskew.output_size&&cam.deskew.output_size[1])||1200), 1200);
  setChecked('cam_post_enabled', !!(cam.postprocess&&cam.postprocess.enabled), false);
  setVal('cam_scale', ((cam.postprocess&&cam.postprocess.scale)??1.0), 1.0);
  setVal('cam_crop_margin', ((cam.postprocess&&cam.postprocess.center_crop_margin)??0), 0);
  const fs=(cam.postprocess&&cam.postprocess.final_size)||[1200,1200];
  setVal('cam_final_w', fs[0]||1200, 1200);
  setVal('cam_final_h', fs[1]||1200, 1200);
  setVal('cam_dpi', ((cam.postprocess&&cam.postprocess.dpi)??101.6), 101.6);
  const guides=(cam.postprocess&&cam.postprocess.overlay_guides)||{};
  setChecked('cam_guides_enabled', !!guides.enabled, false);
  setChecked('cam_guides_cross', (guides.draw_center_cross!==false), true);
  setChecked('cam_guides_border', (guides.draw_border!==false), true);
  setChecked('cam_guides_corners', (guides.draw_corner_marks!==false), true);
  const oa=(cam.overlay_alignment)||{};
  setChecked('cam_align_enabled', (oa.enabled!==false), true);
  setVal('cam_align_width_mm', (oa.physical_width_mm??300), 300);
  setVal('cam_align_height_mm', (oa.physical_height_mm??300), 300);
  setVal('cam_align_offset_x', (oa.source_offset_x_px ?? oa.offset_x_mm ?? 0), 0);
  setVal('cam_align_offset_y', (oa.source_offset_y_px ?? oa.offset_y_mm ?? 0), 0);
  setVal('cam_align_scale_x', (oa.scale_x??1.0), 1.0);
  setVal('cam_align_scale_y', (oa.scale_y??1.0), 1.0);
  setVal('cam_align_rotation', (oa.fine_rotation_degrees??0.0), 0.0);

  setVal('jobs_imported', jobs.imported_jobs_dir||jobs.imported_jobs_folder||'imported_jobs', 'imported_jobs');
  setVal('jobs_watched', jobs.watched_gcode_dir||jobs.watched_folder||'watched_gcode', 'watched_gcode');
  setVal('jobs_ext', (jobs.allowed_extensions||[]).join(','), '.gcode,.gc,.nc');
  setChecked('jobs_watch_enabled', jobs.watch_enabled!==false, true);
  setVal('jobs_watch_poll', jobs.watch_poll_seconds||3, 3);

  setVal('frame_feed', (framing.feedrate ?? framing.frame_feedrate ?? 3000), 3000);
  setVal('frame_margin', (framing.margin_mm ?? framing.frame_margin_mm ?? 2.0), 2.0);
  setChecked('frame_laser_off', (framing.force_laser_off ?? framing.laser_off_during_frame ?? true), true);
  setChecked('frame_validate_bounds', (framing.validate_bounds ?? true), true);
  setChecked('frame_clamp_bounds', (framing.clamp_to_machine_area ?? true), true);
  setVal('machine_min_x', (machine.min_x ?? 0), 0);
  setVal('machine_min_y', (machine.min_y ?? 0), 0);
  setVal('machine_max_x', (machine.max_x ?? machine.bed_width_mm ?? 390), 390);
  setVal('machine_max_y', (machine.max_y ?? machine.bed_height_mm ?? 360), 360);

  setVal('jog_step', (mc.default_jog_step ?? mc.default_jog_step_mm ?? 10), 10);
  setVal('jog_feed', (mc.default_feedrate ?? 500), 500);
  setChecked('jog_z', (mc.enable_z_jog ?? mc.enable_jog_z ?? false), false);
  setChecked('preset_enabled', (mc.preset_enabled !== false), true);
  setVal('preset_label', (mc.preset_label ?? 'Go To Preset'), 'Go To Preset');
  setVal('preset_x', (mc.preset_x ?? 0), 0);
  setVal('preset_y', (mc.preset_y ?? 0), 0);
  setVal('preset_feedrate', (mc.preset_feedrate ?? 1500), 1500);

  setChecked('safe_test_enable', (safety.test_fire_enabled ?? safety.enable_test_fire ?? false), false);
  setVal('safe_test_mode', (safety.test_fire_mode ?? 'stationary_m4'), 'stationary_m4');
  setVal('safe_test_cmd', (safety.test_fire_command ?? 'M4'), 'M4');
  setVal('safe_s_max', (safety.test_fire_s_max ?? 1000), 1000);
  setVal('safe_power', (safety.test_fire_power ?? 5), 5);
  setVal('safe_power_max', (safety.test_fire_max_power ?? 12), 12);
  const durMs = (safety.test_fire_duration_ms ?? Math.round((safety.test_fire_duration_seconds ?? 0.1)*1000));
  setVal('safe_dur', durMs, 100);
  setVal('safe_dur_max', (safety.test_fire_max_duration_ms ?? 2000), 2000);
  setChecked('safe_reject_3d', (safety.reject_3d_printer_gcode !== false), true);
  setVal('safe_scan_lines', (safety.gcode_safety_scan_lines ?? 5000), 5000);
  setChecked('safe_allow_unknown', (safety.allow_unknown_gcode !== false), true);

  setVal('sd_auto_refresh', sd.auto_refresh_seconds??0, 0);
  setChecked('sd_show_storage', sd.show_storage_summary!==false, true);
  setChecked('sd_enable_start', sd.enable_start!==false, true);
  setChecked('sd_enable_delete', sd.enable_delete!==false, true);
  setChecked('sd_enable_preview', !!sd.enable_preview, false);

  setChecked('upload_preserve_original', (up.preserve_original!==false), true);
  setChecked('upload_sanitize_filename', !!up.sanitize_filename, false);
  setChecked('upload_rewrite', !!up.screen_compatible_rewrite, false);
  setChecked('upload_convert_m4', !!up.convert_m4_to_m3, false);
  setVal('upload_force_ext', up.force_extension||'', '');
  setChecked('upload_normalize_eol', !!up.normalize_line_endings, false);
  setVal('job_stop_mode', (jc.stop_mode || 'soft_reset'), 'soft_reset');
  setChecked('job_allow_soft_reset', !!jc.allow_soft_reset_stop, false);
  setChecked('job_stop_laser_off_first', (jc.stop_sends_laser_off_first !== false), true);
  setChecked('job_stop_unlock_after', !!jc.stop_unlock_after_reset, false);
  setChecked('job_stop_refresh_status', (jc.stop_refresh_status_after !== false), true);

  setChecked('status_prefer_live', (st.prefer_live_status!==false), true);
  setChecked('status_ws_enabled', (st.websocket_enabled!==false), true);
  setChecked('status_debug_logging', !!st.debug_logging, false);
  setVal('status_ws_port', st.websocket_port||8849, 8849);
  setVal('status_ws_path', st.websocket_path||'/', '/');
  setVal('status_ws_subprotocol', st.websocket_subprotocol||'arduino', 'arduino');
  setVal('status_poll_seconds', st.poll_seconds??1.0, 1.0);
  setVal('status_reconnect_seconds', st.reconnect_seconds??3.0, 3.0);
  setVal('status_stale_after', st.stale_after_seconds??5.0, 5.0);
  setChecked('status_synth_fallback', (st.synthetic_fallback_enabled!==false), true);
  setChecked('status_show_source', (st.show_status_source!==false), true);
  setChecked('status_show_pos_source', (st.show_position_source!==false), true);
  setChecked('console_raw_enabled', (csl.raw_command_enabled !== false), true);
  setChecked('console_confirm_dangerous', (csl.confirm_dangerous_raw_commands !== false), true);
}

function collect(){
  const finalW=Number(v('cam_final_w').value)||1200;
  const finalH=Number(v('cam_final_h').value)||1200;
  let deskewPoints=[];
  try{ deskewPoints = JSON.parse(v('cam_deskew_points').value||'[]'); }catch(_e){ deskewPoints=[]; }
  return {
    ray5:{host:v('ray_host').value.trim(),port:Number(v('ray_port').value),timeout:Number(v('ray_timeout').value),request_timeout_seconds:Number(v('ray_timeout').value),sd_path:'/'},
    web_ui:{host:v('web_host').value.trim(),port:Number(v('web_port').value)},
    camera:{
      enabled:v('cam_enabled').checked,
      video_enabled:v('cam_video_enabled').checked,
      url:v('cam_stream').value.trim(),
      stream_url:'',
      snapshot_url:v('cam_snapshot').value.trim(),
      proxy_enabled:v('cam_proxy_enabled').checked,
      proxy_path:v('cam_proxy_path').value.trim()||'/camera/stream',
      mask_credentials:true,
      reconnect_seconds:Number(v('cam_reconnect').value)||5,
      capture_method:v('cam_capture_method').value.trim()||'ffmpeg',
      output_dir:v('cam_output_dir').value.trim()||'camera_captures',
      filename_prefix:v('cam_filename_prefix').value.trim()||'ray5_bed',
      save_history:v('cam_save_history').checked,
      keep_last:Number(v('cam_keep_last').value)||0,
      auto_cleanup_on_start:v('cam_auto_cleanup').checked,
      cleanup_on_capture:v('cam_cleanup_capture').checked,
      latest_raw_name:'latest_raw.jpg',
      latest_processed_name:'latest.jpg',
      auto_capture_on_start:false,
      timeout_seconds:Number(v('cam_timeout').value)||15,
      deskew:{
        enabled:v('cam_deskew_enabled').checked,
        source_points:Array.isArray(deskewPoints)?deskewPoints:[],
        output_size:[Number(v('cam_deskew_out_w').value)||1200,Number(v('cam_deskew_out_h').value)||1200]
      },
      postprocess:{
        enabled:v('cam_post_enabled').checked,
        scale:Number(v('cam_scale').value)||1.0,
        center_crop_margin:Number(v('cam_crop_margin').value)||0,
        rotate_degrees:Number(v('cam_rot').value)||0,
        final_size:[finalW,finalH],
        dpi:Number(v('cam_dpi').value)||101.6,
        overlay_guides:{
          enabled:v('cam_guides_enabled').checked,
          draw_center_cross:v('cam_guides_cross').checked,
          draw_border:v('cam_guides_border').checked,
          draw_corner_marks:v('cam_guides_corners').checked
        }
      },
      overlay_alignment:{
        enabled:v('cam_align_enabled').checked,
        physical_width_mm:Number(v('cam_align_width_mm').value)||300,
        physical_height_mm:Number(v('cam_align_height_mm').value)||300,
        source_offset_x_px:Number(v('cam_align_offset_x').value)||0,
        source_offset_y_px:Number(v('cam_align_offset_y').value)||0,
        offset_x_mm:0,
        offset_y_mm:0,
        scale_x:Number(v('cam_align_scale_x').value)||1.0,
        scale_y:Number(v('cam_align_scale_y').value)||1.0,
        fine_rotation_degrees:Number(v('cam_align_rotation').value)||0.0
      }
    },
    jobs:{imported_jobs_dir:v('jobs_imported').value.trim(),watched_gcode_dir:v('jobs_watched').value.trim(),watch_enabled:v('jobs_watch_enabled').checked,watch_poll_seconds:Number(v('jobs_watch_poll').value),allowed_extensions:v('jobs_ext').value.split(',').map(s=>s.trim()).filter(Boolean)},
    framing:{
      feedrate:Number(v('frame_feed').value),
      margin_mm:Number(v('frame_margin').value),
      force_laser_off:v('frame_laser_off').checked,
      validate_bounds:v('frame_validate_bounds').checked,
      clamp_to_machine_area:v('frame_clamp_bounds').checked,
      frame_feedrate:Number(v('frame_feed').value),
      frame_margin_mm:Number(v('frame_margin').value),
      laser_off_during_frame:v('frame_laser_off').checked
    },
    machine:{
      min_x:Number(v('machine_min_x').value),
      min_y:Number(v('machine_min_y').value),
      max_x:Number(v('machine_max_x').value),
      max_y:Number(v('machine_max_y').value),
      bed_width_mm:Number(v('machine_max_x').value),
      bed_height_mm:Number(v('machine_max_y').value)
    },
    manual_controls:{
      default_jog_step:Number(v('jog_step').value),
      default_jog_step_mm:Number(v('jog_step').value),
      default_feedrate:Number(v('jog_feed').value),
      enable_z_jog:v('jog_z').checked,
      enable_jog_z:v('jog_z').checked,
      preset_enabled:v('preset_enabled').checked,
      preset_label:v('preset_label').value.trim() || 'Go To Preset',
      preset_x:Number(v('preset_x').value),
      preset_y:Number(v('preset_y').value),
      preset_feedrate:Number(v('preset_feedrate').value)
    },
    safety:{
      test_fire_enabled:v('safe_test_enable').checked,
      enable_test_fire:v('safe_test_enable').checked,
      test_fire_mode:(v('safe_test_mode').value.trim() || 'stationary_m4'),
      test_fire_power_is_percent:true,
      test_fire_command:(v('safe_test_cmd').value.trim().toUpperCase() || 'M3'),
      test_fire_s_max:Number(v('safe_s_max').value)||1000,
      test_fire_power:Number(v('safe_power').value),
      test_fire_max_power:Number(v('safe_power_max').value)||12,
      test_fire_duration_ms:Number(v('safe_dur').value),
      test_fire_max_duration_ms:Number(v('safe_dur_max').value)||2000,
      test_fire_duration_seconds:Number(v('safe_dur').value)/1000,
      reject_3d_printer_gcode:v('safe_reject_3d').checked,
      gcode_safety_scan_lines:Number(v('safe_scan_lines').value)||5000,
      allow_unknown_gcode:v('safe_allow_unknown').checked
    },
    sd_files:{
      auto_refresh_seconds:Number(v('sd_auto_refresh').value)||0,
      show_storage_summary:v('sd_show_storage').checked,
      enable_start:v('sd_enable_start').checked,
      enable_delete:v('sd_enable_delete').checked,
      enable_preview:v('sd_enable_preview').checked
    },
    upload:{
      preserve_original:v('upload_preserve_original').checked,
      sanitize_filename:v('upload_sanitize_filename').checked,
      screen_compatible_rewrite:v('upload_rewrite').checked,
      convert_m4_to_m3:v('upload_convert_m4').checked,
      force_extension:v('upload_force_ext').value.trim(),
      normalize_line_endings:v('upload_normalize_eol').checked,
      start_after_upload:false
    },
    job_control:{
      stop_mode:v('job_stop_mode').value || 'soft_reset',
      allow_soft_reset_stop:v('job_allow_soft_reset').checked,
      stop_sends_laser_off_first:v('job_stop_laser_off_first').checked,
      stop_unlock_after_reset:v('job_stop_unlock_after').checked,
      stop_refresh_status_after:v('job_stop_refresh_status').checked,
    },
    status:{
      prefer_live_status:v('status_prefer_live').checked,
      websocket_enabled:v('status_ws_enabled').checked,
      debug_logging:v('status_debug_logging').checked,
      websocket_port:Number(v('status_ws_port').value)||8849,
      websocket_path:v('status_ws_path').value.trim()||'/',
      websocket_subprotocol:v('status_ws_subprotocol').value.trim()||'arduino',
      poll_seconds:Number(v('status_poll_seconds').value)||1.0,
      reconnect_seconds:Number(v('status_reconnect_seconds').value)||3.0,
      stale_after_seconds:Number(v('status_stale_after').value)||5.0,
      synthetic_fallback_enabled:v('status_synth_fallback').checked,
      show_status_source:v('status_show_source').checked,
      show_position_source:v('status_show_pos_source').checked
    },
    console:{
      raw_command_enabled:v('console_raw_enabled').checked,
      confirm_dangerous_raw_commands:v('console_confirm_dangerous').checked
    },
  }
}

async function init(){
  const saveBtn = v('saveCfg');
  try{
    const d=await api('/api/config');
    const cfg=unwrapConfigResponse(d);
    load(cfg);
    settingsLoaded = true;
    const host = String((cfg?.ray5?.host)||'').trim();
    if(host.toUpperCase()==='YOUR_RAY5_IP'){
      v('saveOut').textContent='Settings are showing placeholder Ray5 host. Do not save until config.json is loaded correctly.';
      if(saveBtn) saveBtn.disabled = true;
    } else {
      if(saveBtn) saveBtn.disabled = false;
    }
  }catch(err){
    settingsLoaded = false;
    if(v('saveOut')) v('saveOut').textContent=`Settings failed to load: ${err && err.message ? err.message : err}`;
    if(saveBtn) saveBtn.disabled = true;
    console.error('Settings init failed', err);
  }
  saveBtn.onclick=async()=>{
    if(!settingsLoaded){
      v('saveOut').textContent='Save blocked: Settings did not load correctly.';
      return;
    }
    const rayHost = v('ray_host').value.trim();
    const webHost = v('web_host').value.trim();
    const rayPort = Number(v('ray_port').value);
    const webPort = Number(v('web_port').value);
    const jobsImported = v('jobs_imported').value.trim();
    const jobsWatched = v('jobs_watched').value.trim();
    const presetFeed = Number(v('preset_feedrate').value);
    const presetX = Number(v('preset_x').value);
    const presetY = Number(v('preset_y').value);
    const machineMinX = Number(v('machine_min_x').value);
    const machineMinY = Number(v('machine_min_y').value);
    const machineMaxX = Number(v('machine_max_x').value);
    const machineMaxY = Number(v('machine_max_y').value);
    const camEnabled = v('cam_enabled').checked;
    const camStream = v('cam_stream').value.trim();
    const camSnapshot = v('cam_snapshot').value.trim();
    const testDur = Number(v('safe_dur').value);
    const testDurMax = Number(v('safe_dur_max').value)||2000;
    const testPower = Number(v('safe_power').value);
    const testPowerMax = Number(v('safe_power_max').value)||12;

    if(!rayHost){ v('saveOut').textContent='Save failed: ray5 host cannot be empty'; return; }
    if(!webHost){ v('saveOut').textContent='Save failed: web host cannot be empty'; return; }
    if(!(rayPort>=1 && rayPort<=65535)){ v('saveOut').textContent='Save failed: Ray5 port must be 1-65535'; return; }
    if(!(webPort>=1 && webPort<=65535)){ v('saveOut').textContent='Save failed: Web UI port must be 1-65535'; return; }
    if(!jobsImported){ v('saveOut').textContent='Save failed: imported jobs folder cannot be empty'; return; }
    if(!jobsWatched){ v('saveOut').textContent='Save failed: watched folder cannot be empty'; return; }
    if(!(presetFeed > 0)){ v('saveOut').textContent='Save failed: preset feedrate must be positive'; return; }
    if(Number.isFinite(machineMinX) && Number.isFinite(machineMaxX) && machineMinX <= machineMaxX){
      if(presetX < machineMinX || presetX > machineMaxX){ v('saveOut').textContent='Save failed: preset X is outside machine limits'; return; }
    }
    if(Number.isFinite(machineMinY) && Number.isFinite(machineMaxY) && machineMinY <= machineMaxY){
      if(presetY < machineMinY || presetY > machineMaxY){ v('saveOut').textContent='Save failed: preset Y is outside machine limits'; return; }
    }
    if(camEnabled && !camStream && !camSnapshot){ v('saveOut').textContent='Save failed: camera enabled requires stream or snapshot URL'; return; }
    if(testDur > testDurMax){ v('saveOut').textContent='Save failed: test fire duration exceeds max duration'; return; }
    if(testPower > testPowerMax){ v('saveOut').textContent='Save failed: test fire power exceeds max power'; return; }
    const testMode = (v('safe_test_mode').value || '').trim();
    if(testMode && !['stationary_m3','stationary_m4'].includes(testMode)){ v('saveOut').textContent='Save failed: invalid test fire mode'; return; }
    const testCmd = (v('safe_test_cmd').value || '').trim().toUpperCase();
    if(testCmd && testCmd !== 'M3' && testCmd !== 'M4'){ v('saveOut').textContent='Save failed: test fire command must be M3 or M4'; return; }

    const payload = collect();
    payload.safety.test_fire_duration_ms = Math.min(payload.safety.test_fire_duration_ms, payload.safety.test_fire_max_duration_ms);
    payload.safety.test_fire_power = Math.min(payload.safety.test_fire_power, payload.safety.test_fire_max_power);
    payload.safety.test_fire_duration_seconds = payload.safety.test_fire_duration_ms/1000;
    const r=await api('/api/config','POST',payload);
    v('saveOut').textContent=r.ok?'Config saved successfully':('Save failed: '+(r.error||'unknown error'));
  };
}
init();
