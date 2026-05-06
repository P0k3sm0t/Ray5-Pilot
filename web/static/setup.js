async function api(url, method='GET', body=null){const opt={method,headers:{}};if(body){opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body)}const r=await fetch(url,opt);return r.json()}
function v(id){return document.getElementById(id)}

function load(cfg){
  v('ray_host').value=cfg.ray5.host;
  v('ray_port').value=cfg.ray5.port;
  v('ray_timeout').value=cfg.ray5.request_timeout_seconds ?? cfg.ray5.timeout ?? 4;
  v('web_host').value=cfg.web_ui.host;
  v('web_port').value=cfg.web_ui.port;

  const cam=cfg.camera||{};
  v('cam_enabled').checked=!!cam.enabled;
  v('cam_stream').value=cam.url||cam.stream_url||'';
  v('cam_snapshot').value=cam.snapshot_url||'';
  v('cam_proxy_enabled').checked=(cam.proxy_enabled!==false);
  v('cam_proxy_path').value=cam.proxy_path||'/camera/stream';
  v('cam_reconnect').value=cam.reconnect_seconds||5;
  v('cam_capture_method').value=cam.capture_method||'ffmpeg';
  v('cam_output_dir').value=cam.output_dir||'camera_captures';
  v('cam_filename_prefix').value=cam.filename_prefix||'ray5_bed';
  v('cam_save_history').checked=!!cam.save_history;
  v('cam_keep_last').value=(cam.keep_last??0);
  v('cam_auto_cleanup').checked=(cam.auto_cleanup_on_start!==false);
  v('cam_cleanup_capture').checked=(cam.cleanup_on_capture!==false);
  v('cam_timeout').value=cam.timeout_seconds||15;
  const rotVal = String((cam.postprocess&&cam.postprocess.rotate_degrees) ?? 90);
  v('cam_rot').value=(['0','90','180','270'].includes(rotVal)?rotVal:'0');
  v('cam_deskew_enabled').checked=!!(cam.deskew&&cam.deskew.enabled);
  v('cam_deskew_points').value=JSON.stringify((cam.deskew&&cam.deskew.source_points)||[]);
  v('cam_deskew_out_w').value=((cam.deskew&&cam.deskew.output_size&&cam.deskew.output_size[0])||1200);
  v('cam_deskew_out_h').value=((cam.deskew&&cam.deskew.output_size&&cam.deskew.output_size[1])||1200);
  v('cam_post_enabled').checked=!!(cam.postprocess&&cam.postprocess.enabled);
  v('cam_scale').value=((cam.postprocess&&cam.postprocess.scale)??1.0);
  v('cam_crop_margin').value=((cam.postprocess&&cam.postprocess.center_crop_margin)??0);
  const fs=(cam.postprocess&&cam.postprocess.final_size)||[1200,1200];
  v('cam_final_w').value=fs[0]||1200;
  v('cam_final_h').value=fs[1]||1200;
  v('cam_dpi').value=((cam.postprocess&&cam.postprocess.dpi)??101.6);
  const guides=(cam.postprocess&&cam.postprocess.overlay_guides)||{};
  v('cam_guides_enabled').checked=!!guides.enabled;
  v('cam_guides_cross').checked=(guides.draw_center_cross!==false);
  v('cam_guides_border').checked=(guides.draw_border!==false);
  v('cam_guides_corners').checked=(guides.draw_corner_marks!==false);

  v('jobs_imported').value=cfg.jobs.imported_jobs_dir||cfg.jobs.imported_jobs_folder||'imported_jobs';
  v('jobs_watched').value=cfg.jobs.watched_gcode_dir||cfg.jobs.watched_folder||'watched_gcode';
  v('jobs_ext').value=(cfg.jobs.allowed_extensions||[]).join(',');
  v('jobs_watch_enabled').checked=cfg.jobs.watch_enabled!==false;
  v('jobs_watch_poll').value=cfg.jobs.watch_poll_seconds||3;

  v('frame_feed').value=(cfg.framing.feedrate ?? cfg.framing.frame_feedrate ?? 3000);
  v('frame_margin').value=(cfg.framing.margin_mm ?? cfg.framing.frame_margin_mm ?? 2.0);
  v('frame_laser_off').checked=(cfg.framing.force_laser_off ?? cfg.framing.laser_off_during_frame ?? true);
  v('frame_validate_bounds').checked=(cfg.framing.validate_bounds ?? true);
  v('frame_clamp_bounds').checked=(cfg.framing.clamp_to_machine_area ?? true);
  const machine=cfg.machine||{};
  v('machine_min_x').value=(machine.min_x ?? 0);
  v('machine_min_y').value=(machine.min_y ?? 0);
  v('machine_max_x').value=(machine.max_x ?? machine.bed_width_mm ?? 390);
  v('machine_max_y').value=(machine.max_y ?? machine.bed_height_mm ?? 360);
  v('machine_bed_w').value=(machine.bed_width_mm ?? 390);
  v('machine_bed_h').value=(machine.bed_height_mm ?? 360);

  const mc=cfg.manual_controls||{};
  v('jog_step').value=(mc.default_jog_step ?? mc.default_jog_step_mm ?? 10);
  v('jog_feed').value=(mc.default_feedrate ?? 500);
  v('jog_z').checked=(mc.enable_z_jog ?? mc.enable_jog_z ?? false);
  v('preset_enabled').checked=(mc.preset_enabled !== false);
  v('preset_label').value=(mc.preset_label ?? 'Go To Preset');
  v('preset_x').value=(mc.preset_x ?? 0);
  v('preset_y').value=(mc.preset_y ?? 0);
  v('preset_feedrate').value=(mc.preset_feedrate ?? 1500);

  v('safe_test_enable').checked=(cfg.safety.test_fire_enabled ?? cfg.safety.enable_test_fire);
  v('safe_power').value=cfg.safety.test_fire_power;
  v('safe_power_max').value=cfg.safety.test_fire_max_power ?? 5;
  const durMs = (cfg.safety.test_fire_duration_ms ?? Math.round((cfg.safety.test_fire_duration_seconds ?? 0.1)*1000));
  v('safe_dur').value=durMs;
  v('safe_dur_max').value=cfg.safety.test_fire_max_duration_ms ?? 500;

  const sd=cfg.sd_files||{};
  v('sd_auto_refresh').value=sd.auto_refresh_seconds??0;
  v('sd_show_storage').checked=sd.show_storage_summary!==false;
  v('sd_enable_start').checked=sd.enable_start!==false;
  v('sd_enable_delete').checked=sd.enable_delete!==false;
  v('sd_enable_preview').checked=!!sd.enable_preview;

  const up=cfg.upload||{};
  v('upload_preserve_original').checked=(up.preserve_original!==false);
  v('upload_sanitize_filename').checked=!!up.sanitize_filename;
  v('upload_rewrite').checked=!!up.screen_compatible_rewrite;
  v('upload_convert_m4').checked=!!up.convert_m4_to_m3;
  v('upload_force_ext').value=up.force_extension||'';
  v('upload_normalize_eol').checked=!!up.normalize_line_endings;

  const st=cfg.status||{};
  v('status_prefer_live').checked=(st.prefer_live_status!==false);
  v('status_ws_enabled').checked=(st.websocket_enabled!==false);
  v('status_debug_logging').checked=!!st.debug_logging;
  v('status_ws_port').value=st.websocket_port||8849;
  v('status_ws_path').value=st.websocket_path||'/';
  v('status_ws_subprotocol').value=st.websocket_subprotocol||'arduino';
  v('status_poll_seconds').value=st.poll_seconds??1.0;
  v('status_reconnect_seconds').value=st.reconnect_seconds??3.0;
  v('status_stale_after').value=st.stale_after_seconds??5.0;
  v('status_synth_fallback').checked=(st.synthetic_fallback_enabled!==false);
  v('status_show_source').checked=(st.show_status_source!==false);
  v('status_show_pos_source').checked=(st.show_position_source!==false);
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
      bed_width_mm:Number(v('machine_bed_w').value),
      bed_height_mm:Number(v('machine_bed_h').value)
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
      test_fire_power:Number(v('safe_power').value),
      test_fire_max_power:Number(v('safe_power_max').value)||5,
      test_fire_duration_ms:Number(v('safe_dur').value),
      test_fire_max_duration_ms:Number(v('safe_dur_max').value)||500,
      test_fire_duration_seconds:Number(v('safe_dur').value)/1000
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
  }
}

async function init(){
  const d=await api('/api/config');
  load(d.config);
  const saveBtn = v('saveCfg');
  const host = String((d.config?.ray5?.host)||'').trim();
  if(host.toUpperCase()==='YOUR_RAY5_IP'){
    v('saveOut').textContent='Settings are showing placeholder Ray5 host. Do not save until config.json is loaded correctly.';
    if(saveBtn) saveBtn.disabled = true;
  } else {
    if(saveBtn) saveBtn.disabled = false;
  }
  saveBtn.onclick=async()=>{
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
    const testDurMax = Number(v('safe_dur_max').value)||500;
    const testPower = Number(v('safe_power').value);
    const testPowerMax = Number(v('safe_power_max').value)||5;

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

    const payload = collect();
    payload.safety.test_fire_duration_ms = Math.min(payload.safety.test_fire_duration_ms, payload.safety.test_fire_max_duration_ms);
    payload.safety.test_fire_power = Math.min(payload.safety.test_fire_power, payload.safety.test_fire_max_power);
    payload.safety.test_fire_duration_seconds = payload.safety.test_fire_duration_ms/1000;
    const r=await api('/api/config','POST',payload);
    v('saveOut').textContent=r.ok?'Config saved successfully':('Save failed: '+(r.error||'unknown error'));
  };
}
init();
