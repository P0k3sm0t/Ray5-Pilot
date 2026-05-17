async function api(url, method='GET', body=null){
  const opt={method,headers:{}};
  if(body){opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body)}
  const r=await fetch(url,opt);
  return r.json();
}

function fmtPos(v){return (v===null||v===undefined||v==='')?'---':v}
function fmtNum(v, digits=3){
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(digits) : '—';
}
function statusAgeText(seconds){
  const n = Number(seconds);
  if(!Number.isFinite(n) || n < 0) return '—';
  return `${Math.round(n)}s ago`;
}
function axisStatusLine(axis, wVal, mVal){
  const w = Number(wVal);
  const m = Number(mVal);
  const hasW = Number.isFinite(w);
  const hasM = Number.isFinite(m);
  if(hasW && hasM) return `${axis}: W ${w.toFixed(3)} / M ${m.toFixed(3)}`;
  if(hasW) return `${axis}: W ${w.toFixed(3)}`;
  if(hasM) return `${axis}: M ${m.toFixed(3)}`;
  return `${axis}: —`;
}
function yesNoUnknown(v){
  if(v === true) return 'Yes';
  if(v === false) return 'No';
  return 'Unknown';
}
function esc(v){return String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'","&#39;")}
function btn(t,fn){const b=document.createElement('button');b.textContent=t;b.onclick=fn;return b}
function fmtBounds(b){if(!b||b.min_x===undefined||b.min_x===null)return 'Bounds unknown';return `X[${b.min_x.toFixed(3)}..${b.max_x.toFixed(3)}] Y[${b.min_y.toFixed(3)}..${b.max_y.toFixed(3)}]`;}
function humanSize(bytes){
  const n = Number(bytes);
  if(!Number.isFinite(n) || n < 0) return '---';
  if(n < 1024) return `${n} B`;
  if(n < 1024*1024) return `${(n/1024).toFixed(1)} KB`;
  return `${(n/(1024*1024)).toFixed(1)} MB`;
}
function shortDate(ts){
  const n = Number(ts);
  if(!Number.isFinite(n) || n <= 0) return '---';
  return new Date(n*1000).toLocaleString([], {year:'2-digit', month:'numeric', day:'numeric', hour:'numeric', minute:'2-digit'});
}

function normalizeName(name){
  return String(name || '').trim();
}

let consoleAutoScroll = true;
const consoleBottomThreshold = 40;
let cameraActivePath = '';
const cameraPlaceholderPath = '/static/camera_placeholder.svg';
let cameraVideoEnabled = true;
let cameraDisplayMode = 'placeholder'; // live | placeholder | timelapse
const selectedImportedJobs = new Set();
let lastImportedJobs = [];
const selectedTimelapseFiles = new Set();
let currentTimelapseItems = [];
let timelapseRuntimeState = null;

function setTimelapseMessage(message){
  const msg = document.getElementById('timelapseMsg');
  if(msg) msg.textContent = String(message || '');
}

function isConsoleNearBottom(el){
  if(!el) return true;
  return (el.scrollHeight - el.scrollTop - el.clientHeight) < consoleBottomThreshold;
}

function ensureConsoleJumpButton(){
  let jumpBtn = document.getElementById('consoleJumpLatest');
  if(jumpBtn) return jumpBtn;
  const consoleEl = document.getElementById('console');
  if(!consoleEl || !consoleEl.parentElement) return null;
  jumpBtn = document.createElement('button');
  jumpBtn.id = 'consoleJumpLatest';
  jumpBtn.textContent = 'Jump to latest';
  jumpBtn.className = 'btn-sm';
  jumpBtn.style.display = 'none';
  jumpBtn.style.marginTop = '8px';
  jumpBtn.onclick = () => {
    consoleAutoScroll = true;
    consoleEl.scrollTop = consoleEl.scrollHeight;
    jumpBtn.style.display = 'none';
  };
  consoleEl.parentElement.appendChild(jumpBtn);
  return jumpBtn;
}

function updateConsoleJumpButton(){
  const jumpBtn = document.getElementById('consoleJumpLatest');
  if(!jumpBtn) return;
  jumpBtn.style.display = consoleAutoScroll ? 'none' : 'inline-block';
}

async function refreshStatus(){
  const d=await api('/api/status');
  const mpos = d.machine_position || d.position || {};
  const wpos = d.work_position || {};
  const wco = d.work_offset || {};
  const srcRaw = String(d.status_source || '').trim().toLowerCase();
  const isOfflineFallback = srcRaw === 'offline' || srcRaw === 'fallback_offline' || srcRaw === 'synthetic' || !d.online;
  const stateText = d.display_state || d.state_base || d.machine_state_label || d.state || 'Unknown';
  const pageId = (d.websocket_page_id===null || d.websocket_page_id===undefined || d.websocket_page_id==='') ? '—' : String(d.websocket_page_id);
  const feedText = isOfflineFallback ? '0' : ((d.feed===null || d.feed===undefined) ? '—' : fmtNum(d.feed, 0));
  const laserText = isOfflineFallback ? '0' : ((d.spindle===null || d.spindle===undefined) ? '—' : fmtNum(d.spindle, 0));
  const alarmText = d.alarm_status || ((String(d.state_base||d.state||'').toLowerCase()==='alarm') ? 'Active' : (d.online ? 'Clear' : 'Unknown'));
  const jobText = d.job_status || 'Unknown';
  const sourceText = isOfflineFallback ? 'fallback_offline' : (d.status_source || 'unknown');
  const coordSourceText = isOfflineFallback ? '—' : (d.coordinate_source_label || '—');
  const connectionText = isOfflineFallback ? 'Offline' : (d.connection_status || ((d.online && sourceText === 'live_websocket') ? 'Online' : 'Offline'));
  const lastUpdateText = isOfflineFallback ? '—' : statusAgeText(d.last_update_age_seconds);
  const appVersionText = String(d.app_version || 'unknown');
  const us = (d && d.update_status) ? d.update_status : {};
  let updateText = 'Unable to check';
  if(us && us.checked === false){
    updateText = 'Checking...';
  } else if(us && typeof us.message === 'string' && us.message.trim()){
    updateText = us.message.trim();
  }
  const xLine = isOfflineFallback ? 'X: 0.000' : axisStatusLine('X', wpos.x, mpos.x);
  const yLine = isOfflineFallback ? 'Y: 0.000' : axisStatusLine('Y', wpos.y, mpos.y);
  const hasWco = !isOfflineFallback && !!d.wco_available && Number.isFinite(Number(wco.x)) && Number.isFinite(Number(wco.y));
  const wcoLine = hasWco ? `WCO: X ${Number(wco.x).toFixed(3)} / Y ${Number(wco.y).toFixed(3)}` : 'WCO: —';
  const stateDisplay = isOfflineFallback ? 'Offline' : stateText;
  const pageDisplay = isOfflineFallback ? '—' : pageId;
  const sc = (d && d.system_check) ? d.system_check : {};
  const sdWorkingNow = (sc.sd_card_list_working === true);
  const httpReachableNow = (sc.ray5_http_reachable === true);
  const sdWorkingTransition = (lastSystemSdWorking !== true) && sdWorkingNow;
  const httpTransition = (lastSystemHttpReachable !== true) && httpReachableNow;
  lastSystemSdWorking = sc.sd_card_list_working;
  lastSystemHttpReachable = sc.ray5_http_reachable;
  if((sdWorkingTransition || httpTransition) && !sdAutoRefreshInProgress){
    const now = Date.now();
    if((now - lastSdAutoRefreshAt) >= SD_AUTO_REFRESH_MIN_INTERVAL_MS){
      lastSdAutoRefreshAt = now;
      loadSdFiles({preserveMessage:true, auto:true}).catch(()=>{});
    }
  }
  document.getElementById('status').innerHTML = `
    <div class="status-top">
      <div>State: <b>${esc(stateDisplay)}</b></div>
      <div>PageID: <b>${esc(pageDisplay)}</b></div>
    </div>
    <div class="status-grid">
      <div>${esc(xLine)}</div>
      <div>${esc(yLine)}</div>
      <div>${esc(wcoLine)}</div>
      <div>Feed: <b>${esc(feedText)}</b></div>
      <div>Laser: <b>${esc(laserText)}</b></div>
    </div>
    <div class="status-safety">
      <div>Alarm: <b>${esc(alarmText)}</b></div>
      <div>Job: <b>${esc(jobText)}</b></div>
      <div>Connection: <b>${esc(connectionText)}</b></div>
    </div>
    <div class="status-foot muted small">
      <div>Source: ${esc(sourceText)}</div>
      <div>Coordinate source: ${esc(coordSourceText)}</div>
      <div>Last update: ${esc(lastUpdateText)}</div>
      <div>Version: ${esc(appVersionText)}</div>
      <div>Update: ${esc(updateText)}</div>
      <div style="margin-top:4px;"><b>System check</b></div>
      <div>Ray5 host configured: ${esc(yesNoUnknown(sc.ray5_host_configured))}</div>
      <div>Ray5 HTTP reachable: ${esc(yesNoUnknown(sc.ray5_http_reachable))}</div>
      <div>Ray5 WebSocket reachable: ${esc(yesNoUnknown(sc.ray5_websocket_reachable))}</div>
      <div>PAGEID captured: ${esc(yesNoUnknown(sc.page_id_captured))}</div>
      <div>SD card list working: ${esc(yesNoUnknown(sc.sd_card_list_working))}</div>
      <div>Camera URL configured: ${esc(yesNoUnknown(sc.camera_url_configured))}</div>
      <div>Camera test passed: ${esc(yesNoUnknown(sc.camera_test_passed))}</div>
    </div>
  `;

  const cam=document.getElementById('cam');
  const timelapsePlayer = document.getElementById('timelapsePlayer');
  const msg=document.getElementById('camMsg');
  const off=document.getElementById('cameraOffline');
  const statusLine=document.getElementById('cameraStatusLine');
  const cameraStatus=document.getElementById('cameraStatus');
  const videoToggleBtn = document.getElementById('camVideoToggle');
  cameraVideoEnabled = (d.camera_video_enabled !== false);
  if(d.timelapse_state){
    timelapseRuntimeState = d.timelapse_state;
    updateTimelapseRuntimeUi();
  }
  if(videoToggleBtn) videoToggleBtn.textContent = cameraVideoEnabled ? 'Disable Video' : 'Enable Video';

  const showPlaceholder = (text) => {
    if(timelapsePlayer){
      timelapsePlayer.pause();
      timelapsePlayer.removeAttribute('src');
      timelapsePlayer.style.display='none';
    }
    cam.removeAttribute('src');
    cameraActivePath = '';
    cam.src = cameraPlaceholderPath;
    cam.style.opacity='1';
    cam.style.display='block';
    if(off) off.style.display='none';
    if(msg) msg.textContent = text;
    if(statusLine) statusLine.textContent = text;
    if(cameraStatus) cameraStatus.textContent = text;
    cameraDisplayMode = 'placeholder';
  };

  const showLive = (path) => {
    if(timelapsePlayer){
      timelapsePlayer.pause();
      timelapsePlayer.removeAttribute('src');
      timelapsePlayer.style.display='none';
    }
    cam.style.display='block';
    cam.style.opacity='1';
    if(cameraActivePath !== path || !cam.getAttribute('src')){
      cameraActivePath = path;
      cam.src = cameraActivePath + '?_=' + Date.now();
    }
    if(off) off.style.display='none';
    cameraDisplayMode = 'live';
  };

  if(cameraDisplayMode === 'timelapse'){
    if(cam) cam.style.display='none';
    if(timelapsePlayer) timelapsePlayer.style.display='block';
    return;
  }

  if(!cameraVideoEnabled){
    showPlaceholder('Camera video disabled.');
  } else if(!d.camera_configured){
    showPlaceholder('Camera not configured.');
  } else if(d.camera_preview_supported){
    const nextPath = (d.camera_proxy_path||'/camera/stream');
    showLive(nextPath);
    msg.textContent='Camera: '+(d.camera_url_masked||'configured');
    if(cameraStatus) cameraStatus.textContent = msg.textContent;
    if(statusLine) statusLine.textContent='Camera source: '+(d.camera_url_masked||'configured');
  } else {
    showPlaceholder('Camera stream unavailable.');
  }
}

function updateTimelapseRuntimeUi(){
  const startBtn = document.getElementById('timelapseStart');
  const stopBtn = document.getElementById('timelapseStop');
  const s = timelapseRuntimeState || {};
  if(startBtn){
    startBtn.disabled = (!s.enabled) || !!s.active || !!s.armed;
  }
  if(stopBtn){
    stopBtn.disabled = !s.active && !s.armed;
  }
}

async function refreshConsole(){
  const consoleEl = document.getElementById('console');
  const wasNearBottom = isConsoleNearBottom(consoleEl);
  consoleAutoScroll = consoleAutoScroll && wasNearBottom;
  const d=await api('/api/console');
  consoleEl.textContent=(d.items||[]).slice(-120).map(x=>`[${x.ts}] ${x.level} ${x.message}`).join('\n');
  if(consoleAutoScroll){
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }
  updateConsoleJumpButton();
}

async function refreshJobs(opts={}){
  const preserveMessage = !!(opts && opts.preserveMessage);
  const d=await api('/api/jobs');
  const el=document.getElementById('jobsBody');
  const msg=document.getElementById('jobsMsg');
  const watch=document.getElementById('jobWatchInfo');
  el.innerHTML='';
  watch.textContent = 'Watching: watched_gcode | Extensions: .gcode, .gc, .nc';
  const jobs = d.jobs||[];
  const currentNames = new Set(jobs.map(j => String(j.name||j.filename||'')));
  for(const name of Array.from(selectedImportedJobs)){
    if(!currentNames.has(name)) selectedImportedJobs.delete(name);
  }
  lastImportedJobs = jobs;
  if(!jobs.length){
    const tr=document.createElement('tr');
    tr.innerHTML='<td colspan="6" class="muted small">No imported jobs yet. Import a .gcode, .gc, or .nc file, or drop one into the watched folder.</td>';
    el.append(tr);
    if(!preserveMessage) msg.textContent='Loaded 0 imported job(s)';
    updateImportedSelectionUi();
    return;
  }
  jobs.forEach(j=>{
    const row=document.createElement('tr');
    const mod = shortDate(j.modified);
    const size = humanSize(j.size_bytes ?? j.size);
    const name = j.name||j.filename||'unknown';
    const bounds = j.bounds;
    const isSelected = selectedImportedJobs.has(name);
    if(isSelected) row.classList.add('job-row-selected');
    const selectTd = document.createElement('td');
    selectTd.className = 'job-select-cell';
    const selectBox = document.createElement('input');
    selectBox.type = 'checkbox';
    selectBox.className = 'job-select-checkbox';
    selectBox.checked = isSelected;
    selectBox.setAttribute('aria-label', `Select ${name}`);
    selectBox.onclick = (ev)=>{
      ev.stopPropagation();
      if(selectBox.checked) selectedImportedJobs.add(name);
      else selectedImportedJobs.delete(name);
      row.classList.toggle('job-row-selected', selectBox.checked);
      updateImportedSelectionUi();
    };
    selectTd.append(selectBox);
    const boundsHtml = (bounds && bounds.min_x!==null && bounds.min_x!==undefined)
      ? `<div class="job-bounds">X: ${bounds.min_x.toFixed(0)}-${bounds.max_x.toFixed(0)}<br>Y: ${bounds.min_y.toFixed(0)}-${bounds.max_y.toFixed(0)}</div>`
      : `<span class="muted small">Bounds unknown</span>`;
    const actions=document.createElement('td');
    actions.className='job-actions';
    const frameBtn=btn('Frame', async()=>{
      frameBtn.disabled = true;
      try{
        const r = await api('/api/jobs/frame','POST',{filename:name});
        msg.textContent = r.ok ? (r.message || 'Frame complete') : ('Frame failed: '+(r.error||''));
        await refreshConsole();
      } finally {
        frameBtn.disabled = false;
      }
    });
    const uploadBtn=btn('Upload',()=>api('/api/jobs/upload','POST',{filename:name}).then((r)=>{msg.textContent=r.ok?'Upload complete':'Upload failed'; refreshConsole(); loadSdFiles();} ));
    const runBtn=btn('Upload + Run',()=>{
      if(manualCfg.confirm_dangerous_actions && !confirm('Upload and run '+(j.name||j.filename)+' ?')) return;
      api('/api/jobs/start','POST',{filename:name}).then((r)=>{msg.textContent=r.ok?'Start command sent':'Start failed'; refreshConsole(); refreshStatus(); loadSdFiles();});
    });
    const delBtn=btn('Delete',async()=>{if(!confirm('Delete local imported job '+name+' ?')) return; const res = await fetch('/api/jobs/'+encodeURIComponent(name),{method:'DELETE'}); let data={ok:false}; try{data=await res.json();}catch(_e){} msg.textContent = data.ok ? (`Deleted imported file: ${name}`) : (`Delete failed: ${data.error||'unknown'}`); await refreshJobs({preserveMessage:true}); await refreshConsole();});
    frameBtn.classList.add('btn-sm');
    uploadBtn.classList.add('btn-sm');
    runBtn.classList.add('btn-sm');
    delBtn.classList.add('btn-sm','danger');
    actions.append(frameBtn, uploadBtn, runBtn, delBtn);
    row.innerHTML = `
      <td><div class="job-file-name" title="${esc(name)}">${esc(name)}</div></td>
      <td>${esc(size)}</td>
      <td>${esc(mod)}</td>
      <td>${boundsHtml}</td>
    `;
    row.prepend(selectTd);
    row.append(actions);
    el.append(row);
  });
  if(!preserveMessage) msg.textContent = `Loaded ${jobs.length} imported job(s)`;
  updateImportedSelectionUi();
}

function updateTimelapseSelectionUi(){
  const selectedCountEl = document.getElementById('timelapseSelectedCount');
  const deleteBtn = document.getElementById('timelapseDeleteSelected');
  const clearBtn = document.getElementById('timelapseClearSelection');
  const selectAll = document.getElementById('timelapseSelectAll');
  const selected = selectedTimelapseFiles.size;
  const total = currentTimelapseItems.length;
  if(selectedCountEl) selectedCountEl.textContent = `${selected} selected`;
  if(deleteBtn) deleteBtn.disabled = selected === 0;
  if(clearBtn) clearBtn.disabled = selected === 0;
  if(selectAll){
    selectAll.checked = total > 0 && selected === total;
    selectAll.indeterminate = selected > 0 && selected < total;
  }
}

async function setCameraVideoEnabled(enabled){
  const r = await api('/api/camera/video-enabled','POST',{enabled: !!enabled});
  if(r && r.ok){
    cameraVideoEnabled = !!r.enabled;
    const toggle = document.getElementById('camVideoToggle');
    if(toggle) toggle.textContent = cameraVideoEnabled ? 'Disable Video' : 'Enable Video';
  }
  return r;
}

function stopTimelapsePlayback(showPlaceholder=true){
  const player = document.getElementById('timelapsePlayer');
  const cam = document.getElementById('cam');
  if(player){
    player.pause();
    player.removeAttribute('src');
    player.style.display='none';
  }
  if(cam) cam.style.display='block';
  if(showPlaceholder){
    cameraDisplayMode = 'placeholder';
    if(cam){
      cam.removeAttribute('src');
      cam.src = cameraPlaceholderPath;
    }
    const msg = document.getElementById('camMsg');
    if(msg) msg.textContent = 'Camera video disabled.';
  }
}

async function playTimelapse(item){
  const player = document.getElementById('timelapsePlayer');
  const cam = document.getElementById('cam');
  const msg = document.getElementById('camMsg');
  if(!player || !cam) return;
  await setCameraVideoEnabled(false);
  cameraDisplayMode = 'timelapse';
  cam.style.display='none';
  cam.removeAttribute('src');
  player.style.display='block';
  player.src = item.url;
  player.onended = ()=>{
    stopTimelapsePlayback(true);
  };
  player.onerror = ()=>{
    stopTimelapsePlayback(true);
    if(msg) msg.textContent = 'Timelapse playback failed.';
  };
  try{
    await player.play();
  }catch(_err){
    if(msg) msg.textContent = 'Timelapse ready. Press play.';
  }
  if(msg) setTimelapseMessage(`Playing timelapse: ${item.name}`);
}

async function deleteSelectedTimelapses(){
  const names = Array.from(selectedTimelapseFiles);
  if(!names.length) return;
  const confirmText = names.length === 1
    ? `Delete timelapse '${names[0]}'?`
    : `Delete ${names.length} selected timelapse files?`;
  if(!confirm(confirmText)) return;
  const delBtn = document.getElementById('timelapseDeleteSelected');
  if(delBtn) delBtn.disabled = true;
  setTimelapseMessage('Deleting selected timelapse file(s)...');
  try{
    const r = await api('/api/timelapses/delete','POST',{filenames:names});
    const failed = Array.isArray(r.failed) ? r.failed : [];
    if(failed.length){
      const failedNames = new Set(failed.map(f => normalizeName(f.filename)));
      for(const n of names){
        if(!failedNames.has(n)) selectedTimelapseFiles.delete(n);
      }
    }else{
      selectedTimelapseFiles.clear();
    }
    setTimelapseMessage(r.message || (r.ok ? 'Deleted timelapse files.' : 'Some timelapse files failed to delete.'));
    await loadTimelapses({preserveMessage:true});
  }catch(err){
    setTimelapseMessage(`Timelapse delete failed: ${String(err)}`);
  }finally{
    updateTimelapseSelectionUi();
  }
}

async function loadTimelapseState(){
  const d = await api('/api/timelapse/state');
  if(d && d.ok){
    timelapseRuntimeState = d.state || null;
    updateTimelapseRuntimeUi();
  }
}

async function startTimelapseManual(){
  const r = await api('/api/timelapse/start','POST',{job_source:'manual'});
  timelapseRuntimeState = r.state || timelapseRuntimeState;
  updateTimelapseRuntimeUi();
  setTimelapseMessage(r.message || (r.ok ? 'Timelapse started.' : 'Timelapse start failed.'));
}

async function stopTimelapseManual(){
  const stopBtn = document.getElementById('timelapseStop');
  setTimelapseMessage('Stopping timelapse...');
  if(stopBtn) stopBtn.disabled = true;
  try{
    const r = await api('/api/timelapse/stop','POST',{});
    timelapseRuntimeState = r.state || timelapseRuntimeState;
    updateTimelapseRuntimeUi();
    await loadTimelapseState();
    await loadTimelapses({preserveMessage:true});
    setTimelapseMessage(r.message || (r.ok ? 'Timelapse stopped.' : 'Timelapse stop failed.'));
  }catch(err){
    setTimelapseMessage(`Failed to stop timelapse: ${String(err)}`);
  }finally{
    if(stopBtn) stopBtn.disabled = !((timelapseRuntimeState && (timelapseRuntimeState.active || timelapseRuntimeState.armed)));
  }
}

async function loadTimelapses(opts={}){
  const preserveMessage = !!(opts && opts.preserveMessage);
  const body = document.getElementById('timelapseBody');
  if(!body) return;
  if(!preserveMessage) setTimelapseMessage('Loading timelapses...');
  body.innerHTML = '';
  const d = await api('/api/timelapses');
  if(!d.ok){
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="5" class="muted small">Unable to load timelapse files.</td>';
    body.append(tr);
    if(!preserveMessage) setTimelapseMessage(`Timelapse refresh failed: ${d.message || d.error || 'unknown'}`);
    currentTimelapseItems = [];
    selectedTimelapseFiles.clear();
    updateTimelapseSelectionUi();
    return;
  }
  const items = Array.isArray(d.items) ? d.items : [];
  const liveNames = new Set(items.map(x => normalizeName(x.name || x.filename)));
  for(const name of Array.from(selectedTimelapseFiles)){
    if(!liveNames.has(name)) selectedTimelapseFiles.delete(name);
  }
  currentTimelapseItems = items.map(it => ({
    name: normalizeName(it.name || it.filename),
    size_bytes: Number(it.size_bytes || 0),
    modified: Number(it.modified || 0),
    url: String(it.url || ''),
  })).filter(it => it.name);
  if(!currentTimelapseItems.length){
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="5" class="muted small">No timelapse videos found.</td>';
    body.append(tr);
    if(!preserveMessage) setTimelapseMessage('Loaded 0 timelapse file(s).');
    updateTimelapseSelectionUi();
    return;
  }
  currentTimelapseItems.forEach(item => {
    const row = document.createElement('tr');
    if(selectedTimelapseFiles.has(item.name)) row.classList.add('timelapse-row-selected');
    const selectTd = document.createElement('td');
    selectTd.className = 'timelapse-select-cell';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = selectedTimelapseFiles.has(item.name);
    cb.setAttribute('aria-label', `Select ${item.name}`);
    cb.onclick = (ev)=>{
      ev.stopPropagation();
      if(cb.checked) selectedTimelapseFiles.add(item.name);
      else selectedTimelapseFiles.delete(item.name);
      row.classList.toggle('timelapse-row-selected', cb.checked);
      updateTimelapseSelectionUi();
    };
    selectTd.append(cb);
    const actions = document.createElement('td');
    const playBtn = btn('Play', ()=>playTimelapse(item));
    playBtn.classList.add('btn-sm');
    actions.append(playBtn);
    row.innerHTML = `
      <td><div class="job-file-name" title="${esc(item.name)}">${esc(item.name)}</div></td>
      <td>${esc(humanSize(item.size_bytes))}</td>
      <td>${esc(shortDate(item.modified))}</td>
    `;
    row.prepend(selectTd);
    row.append(actions);
    body.append(row);
  });
  if(!preserveMessage) setTimelapseMessage(`Loaded ${currentTimelapseItems.length} timelapse file(s).`);
  updateTimelapseSelectionUi();
}

function updateImportedSelectionUi(){
  const selectedCountEl = document.getElementById('jobsSelectedCount');
  const deleteBtn = document.getElementById('jobsDeleteSelected');
  const clearBtn = document.getElementById('jobsClearSelection');
  const selectAll = document.getElementById('jobsSelectAll');
  const selected = selectedImportedJobs.size;
  const total = lastImportedJobs.length;
  if(selectedCountEl) selectedCountEl.textContent = `${selected} selected`;
  if(deleteBtn) deleteBtn.disabled = selected === 0;
  if(clearBtn) clearBtn.disabled = selected === 0;
  if(selectAll){
    selectAll.checked = total > 0 && selected === total;
    selectAll.indeterminate = selected > 0 && selected < total;
  }
}

async function deleteSelectedImportedJobs(){
  const names = Array.from(selectedImportedJobs);
  if(!names.length) return;
  const confirmText = names.length === 1
    ? `Delete imported file '${names[0]}'?`
    : `Delete ${names.length} selected imported files?`;
  if(!confirm(confirmText)) return;
  const msg=document.getElementById('jobsMsg');
  const deleteBtn=document.getElementById('jobsDeleteSelected');
  if(deleteBtn) deleteBtn.disabled = true;
  msg.textContent = 'Deleting selected imported files...';
  try{
    const result = await api('/api/imported-files/delete','POST',{filenames:names});
    const failed = Array.isArray(result.failed) ? result.failed : [];
    const deleted = Array.isArray(result.deleted) ? result.deleted : [];
    if(failed.length){
      const failedNames = new Set(failed.map(x => String((x && x.filename) || '')));
      for(const name of names){
        if(!failedNames.has(name)) selectedImportedJobs.delete(name);
      }
      msg.textContent = result.message || `Deleted ${deleted.length} imported file(s), ${failed.length} failed.`;
    }else{
      selectedImportedJobs.clear();
      msg.textContent = result.message || `Deleted ${deleted.length} imported file(s).`;
    }
    await refreshJobs({preserveMessage:true});
    await refreshConsole();
  }catch(err){
    msg.textContent = `Delete selected failed: ${String(err)}`;
  }finally{
    updateImportedSelectionUi();
  }
}

async function loadSnapshots(){
  const d = await api('/api/snapshots');
  const info = document.getElementById('latestSnapshotInfo');
  const openLatest = document.getElementById('openLatestSnapshot');
  const dlLatest = document.getElementById('downloadLatestSnapshot');
  const openRaw = document.getElementById('openLatestRaw');
  const dlRaw = document.getElementById('downloadLatestRaw');
  if(!d.ok){
    info.textContent = 'Snapshots unavailable.';
    return;
  }
  const items = d.items || [];
  const processed = items.find(x=>x.type==='processed' && x.is_latest) || items.find(x=>x.type==='processed');
  const raw = items.find(x=>x.type==='raw' && x.is_latest) || items.find(x=>x.type==='raw');
  if(processed){
    info.textContent = `${processed.name} (${processed.size_bytes||'---'} bytes)`;
    openLatest.href = processed.url;
    dlLatest.href = processed.download_url;
  } else {
    info.textContent = 'No snapshot yet';
    openLatest.removeAttribute('href');
    dlLatest.removeAttribute('href');
  }
  if(raw){
    openRaw.href = raw.url;
    dlRaw.href = raw.download_url;
  } else {
    openRaw.removeAttribute('href');
    dlRaw.removeAttribute('href');
  }
}

let currentSdPath = '/';
let sdPreviewSupported = false;
let sdEnableStart = true;
let sdEnableDelete = true;
const selectedSdFiles = new Map();
let currentSdFiles = [];
let lastSystemSdWorking = null;
let lastSystemHttpReachable = null;
let sdAutoRefreshInProgress = false;
let lastSdAutoRefreshAt = 0;
const SD_AUTO_REFRESH_MIN_INTERVAL_MS = 15000;

function sdFileKey(file){
  const name = String((file && file.name) || '').trim();
  const path = String((file && file.path) || '').trim();
  return `${path}|${name}`;
}

function updateSdSelectionUi(){
  const selectedCountEl = document.getElementById('sdSelectedCount');
  const deleteBtn = document.getElementById('sdDeleteSelected');
  const clearBtn = document.getElementById('sdClearSelection');
  const selectAll = document.getElementById('sdSelectAll');
  const selected = selectedSdFiles.size;
  const selectable = currentSdFiles.filter(f => !!f.can_delete);
  const totalSelectable = selectable.length;
  if(selectedCountEl) selectedCountEl.textContent = `${selected} selected`;
  if(deleteBtn) deleteBtn.disabled = selected === 0;
  if(clearBtn) clearBtn.disabled = selected === 0;
  if(selectAll){
    selectAll.checked = totalSelectable > 0 && selected === totalSelectable;
    selectAll.indeterminate = selected > 0 && selected < totalSelectable;
  }
}

function selectSdFile(file){
  const d = document.getElementById('sdDetails');
  d.innerHTML = `
    <div><b>Selected:</b> ${esc(file.name||'---')}</div>
    <div>Size: ${esc(file.size||'---')}</div>
    <div>Modified: ${esc(file.modified||'---')}</div>
    <div>Type: ${esc(file.type||'unknown')}</div>
    <div>Path: ${esc(file.path||'---')}</div>
    <div>Can start: ${file.can_start?'yes':'no'}</div>
    <div>Can delete: ${file.can_delete?'yes':'no'}</div>
    <div>${sdPreviewSupported?'Preview optional for this API.':'Preview unavailable for this Ray5 API.'}</div>
  `;
}

async function startSdFile(filename, path='/'){
  if(manualCfg.confirm_dangerous_actions && !confirm('Start SD file '+filename+' ?')) return;
  const r = await api('/api/files/start','POST',{filename, path});
  document.getElementById('sdMsg').textContent = r.ok ? ('Started: '+filename) : ('Start failed: '+(r.message||r.error||'unknown'));
  await refreshConsole();
  await refreshStatus();
}

async function deleteSdFile(filename, path='/'){
  if(!confirm('Delete SD file '+filename+' ?')) return;
  const r = await api('/api/files/delete','POST',{filename, path});
  document.getElementById('sdMsg').textContent = r.ok ? ('Deleted: '+filename) : ('Delete failed: '+(r.message||r.error||'unknown'));
  await loadSdFiles({preserveMessage:true});
  await refreshConsole();
}

async function deleteSelectedSdFiles(){
  const selected = Array.from(selectedSdFiles.values());
  if(!selected.length) return;
  const confirmText = selected.length === 1
    ? `Delete SD card file '${selected[0].name}'?`
    : `Delete ${selected.length} selected SD card files?`;
  if(!confirm(confirmText)) return;
  const msgEl = document.getElementById('sdMsg');
  const delBtn = document.getElementById('sdDeleteSelected');
  if(delBtn) delBtn.disabled = true;
  msgEl.textContent = 'Deleting selected SD file(s)...';
  try{
    const r = await api('/api/sd-files/delete','POST',{
      files: selected.map(f => ({name: f.name, path: f.path})),
      path: currentSdPath || '/',
    });
    const failed = Array.isArray(r.failed) ? r.failed : [];
    if(failed.length){
      const failedKeys = new Set(failed.map(item => `${String(item.path || '')}|${String(item.filename || item.name || '')}`));
      for(const [k] of selectedSdFiles){
        if(!failedKeys.has(k)) selectedSdFiles.delete(k);
      }
    }else{
      selectedSdFiles.clear();
    }
    msgEl.textContent = r.message || (r.ok ? 'Deleted selected SD files.' : 'Some SD files could not be deleted.');
    await loadSdFiles({preserveMessage:true});
    await refreshConsole();
  }catch(err){
    msgEl.textContent = `Delete selected failed: ${String(err)}`;
  }finally{
    updateSdSelectionUi();
  }
}

async function stopJob(){
  const c = manualCfg.confirm_dangerous_actions ? confirm('Stop current job?') : true;
  if(!c) return;
  const r = await api('/api/stop','POST',{});
  document.getElementById('sdMsg').textContent = r.ok ? 'Stop sent.' : ('Stop failed: '+(r.message||r.error||'unknown'));
  await refreshStatus();
  await refreshConsole();
}

function renderSdFiles(d){
  const filesEl=document.getElementById('sdFilesBody');
  const storageEl=document.getElementById('sdStorage');
  const pathEl=document.getElementById('sdPath');
  filesEl.innerHTML='';
  currentSdPath = d.path || '/';
  pathEl.textContent = currentSdPath;
  const st = d.storage || {};
  storageEl.innerHTML = `
    <div class="sd-storage-item"><div class="k">Total</div><div class="v">${esc(st.total||'---')}</div></div>
    <div class="sd-storage-item"><div class="k">Used</div><div class="v">${esc(st.used||'---')}</div></div>
    <div class="sd-storage-item"><div class="k">Occupation</div><div class="v">${esc(st.occupation||'---')}</div></div>
    <div class="sd-storage-item"><div class="k">Mode</div><div class="v">${esc(st.mode||'---')}</div></div>
    <div class="sd-storage-item"><div class="k">Status</div><div class="v">${esc(st.status||'---')}</div></div>
  `;
  const files = d.files||[];
  currentSdFiles = files;
  const liveKeys = new Set(files.filter(f => !!f.can_delete).map(sdFileKey));
  for(const key of Array.from(selectedSdFiles.keys())){
    if(!liveKeys.has(key)) selectedSdFiles.delete(key);
  }
  if(!files.length){
    const tr=document.createElement('tr');
    tr.innerHTML='<td colspan="6" class="sd-muted">No SD files found.</td>';
    filesEl.append(tr);
    updateSdSelectionUi();
    return;
  }
  files.forEach(f=>{
    const row=document.createElement('tr');
    const name=f.name||'---';
    const key = sdFileKey(f);
    const selected = selectedSdFiles.has(key);
    if(selected) row.classList.add('sd-row-selected');
    const typeLabel = f.is_directory ? 'Folder / Protected' : ((f.type||'unknown')==='gcode' ? 'G-code' : (f.type||'unknown'));
    const sizeVal = (!f.size || f.size==='-1') ? '---' : f.size;
    const modVal = (!f.modified || f.modified==='') ? '---' : f.modified;
    const selectTd = document.createElement('td');
    selectTd.className = 'sd-select-cell';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = selected;
    cb.disabled = !f.can_delete;
    cb.setAttribute('aria-label', `Select ${name}`);
    cb.onclick = (ev)=>{
      ev.stopPropagation();
      if(cb.checked && f.can_delete) selectedSdFiles.set(key, {name, path: String(f.path || name)});
      else selectedSdFiles.delete(key);
      row.classList.toggle('sd-row-selected', cb.checked);
      updateSdSelectionUi();
    };
    selectTd.append(cb);
    const actionTd = document.createElement('td');
    actionTd.className='sd-actions';
    if(sdEnableStart && f.can_start){
      const startBtn=btn('Start',()=>startSdFile(name, currentSdPath));
      startBtn.classList.add('btn-sm');
      actionTd.append(startBtn);
    }
    if(sdEnableDelete && f.can_delete){
      const delBtn=btn('Delete',()=>deleteSdFile(name, currentSdPath));
      delBtn.classList.add('btn-sm','danger');
      actionTd.append(delBtn);
    }
    if(actionTd.children.length===0){
      const p=document.createElement('span');
      p.className='sd-protected';
      p.textContent='Protected';
      actionTd.append(p);
    }
    row.innerHTML = `
      <td class="sd-file-name">${esc(name)}</td>
      <td>${esc(sizeVal)}</td>
      <td>${esc(modVal)}</td>
      <td>${esc(typeLabel)}</td>
    `;
    row.prepend(selectTd);
    row.append(actionTd);
    row.onclick=(ev)=>{
      const t = ev.target;
      if(t && (t.closest('button') || t.closest('input') || t.closest('label'))) return;
      selectSdFile(f);
    };
    filesEl.append(row);
  });
  updateSdSelectionUi();
}

async function loadSdFiles(opts={}){
  if(sdAutoRefreshInProgress) return;
  const preserveMessage = !!(opts && opts.preserveMessage);
  sdAutoRefreshInProgress = true;
  const msgEl = document.getElementById('sdMsg');
  try{
    if(!preserveMessage) msgEl.textContent = 'Loading SD files...';
    const d = await api('/api/files?path='+encodeURIComponent(currentSdPath||'/'));
    if(!d.ok){
      if(!preserveMessage) msgEl.textContent = 'SD refresh failed: '+(d.error||'unknown');
      document.getElementById('sdFilesBody').innerHTML = '<tr><td colspan="6" class="sd-muted">Unable to load SD files.</td></tr>';
      return;
    }
    renderSdFiles(d);
    if(!preserveMessage) msgEl.textContent = `Loaded ${ (d.files||[]).length } item(s).`;
  } finally {
    sdAutoRefreshInProgress = false;
  }
}

let manualBusy = false;
let manualCfg = {
  confirm_dangerous_actions: true,
  enable_z_jog: false,
  test_fire_enabled: false,
  preset_enabled: true,
  preset_label: 'Go To Preset',
  test_fire_s_value: 50,
  test_fire_duration_ms: 100,
  raw_command_enabled: true,
  confirm_dangerous_raw_commands: true
};
const rawCommandHistory = [];
let rawCommandHistoryIndex = -1;

function isDangerousRawCommand(cmd){
  const s = String(cmd || '').trim();
  if(!s) return false;
  const u = s.toUpperCase();
  if(u === '?' || u === '$G' || u === '$I' || u === 'M5') return false;
  if(/(^|\s)(M3|M4|G0|G1|G2|G3|\$X|\$H|RUNZIP|M8|M9)\b/i.test(s)) return true;
  if(/(\$SD\/RUN|\$SD\/RUNZIP|\$SD\/RUN=|\$SD\/RUNZIP=|\$SD\/RUNZIP=\/)/i.test(s)) return true;
  if(/CTRL-?X|\^X|\\X18|SOFT_RESET/i.test(s)) return true;
  if(/M[34].*S\s*\d+/i.test(s)) return true;
  return false;
}

async function sendRawConsoleCommand(){
  const input = document.getElementById('consoleCommandInput');
  const sendBtn = document.getElementById('consoleCommandSend');
  const statusEl = document.getElementById('consoleCommandStatus');
  if(!input || !sendBtn || !statusEl) return;
  if(sendBtn.disabled) return;
  const command = String(input.value || '').trim();
  if(!command){
    statusEl.textContent = 'Enter a command first.';
    return;
  }
  if(manualCfg.confirm_dangerous_raw_commands && isDangerousRawCommand(command)){
    const ok = confirm(`Send raw command '${command}'? This may move the laser or trigger machine actions.`);
    if(!ok) return;
  }
  sendBtn.disabled = true;
  statusEl.textContent = 'Sending...';
  try{
    const r = await api('/api/console/command','POST',{command});
    if(r.ok){
      statusEl.textContent = `Sent: ${r.command}`;
      if(rawCommandHistory.length === 0 || rawCommandHistory[rawCommandHistory.length-1] !== command){
        rawCommandHistory.push(command);
        if(rawCommandHistory.length > 20) rawCommandHistory.shift();
      }
      rawCommandHistoryIndex = rawCommandHistory.length;
      input.value = '';
    }else{
      statusEl.textContent = `Failed: ${r.message || 'unknown error'}`;
    }
    await refreshConsole();
    await refreshStatus();
  }catch(err){
    statusEl.textContent = `Failed: ${String(err)}`;
  }finally{
    sendBtn.disabled = false;
  }
}
let jobImportBusy = false;
function setManualBusy(state){
  manualBusy = state;
  document.querySelectorAll('#homeAll,#unlock,#xMinus,#xPlus,#yMinus,#yPlus,#xyMinusPlus,#xyPlusPlus,#xyMinusMinus,#xyPlusMinus,#centerBed,#airOn,#airOff,#testFire,#stop,#pauseBtn,#resumeBtn,#presetMoveBtn').forEach(el=>{if(el)el.disabled=state;});
}

async function manualCall(url, body=null, confirmText=''){
  if(manualBusy) return;
  if(confirmText && !confirm(confirmText)) return;
  setManualBusy(true);
  try{
    const r = await api(url,'POST',body);
    let msg = r.ok ? 'OK: '+(r.message||'command sent') : 'Error: '+(r.message||r.error||'request failed');
    if(r && r.ok && url === '/api/laser/test-fire'){
      const sVal = Number(r.s_value);
      const dur = Number(r.duration_ms);
      const cmd = String(r.command || 'M4').trim();
      if(Number.isFinite(sVal) && Number.isFinite(dur)){
        msg = `Test fire complete: ${cmd} S${sVal} / ${dur} ms`;
      }
    }
    document.getElementById('manualMsg').textContent = msg;
    await refreshConsole();
    await refreshStatus();
  } finally {
    setManualBusy(false);
  }
}

function currentStep(){ return Number(document.getElementById('jogStep').value || 10); }
function currentFeed(){ return Number(document.getElementById('jogFeed').value || 3000); }

async function loadManualConfig(){
  try{
    const d = await api('/api/config');
    const cfg = d.config || {};
    const mc = cfg.manual_controls || {};
    const safety = cfg.safety || {};
    const sdCfg = cfg.sd_files || {};
    const consoleCfg = cfg.console || {};
    manualCfg = {
      confirm_dangerous_actions: (safety.confirm_dangerous_actions !== false),
      enable_z_jog: !!(mc.enable_z_jog ?? mc.enable_jog_z ?? false),
      test_fire_enabled: !!(safety.test_fire_enabled ?? safety.enable_test_fire ?? false),
      preset_enabled: (mc.preset_enabled !== false),
      preset_label: String(mc.preset_label || 'Go To Preset'),
      test_fire_s_value: Number(safety.test_fire_s_value ?? 50),
      test_fire_duration_ms: Number(safety.test_fire_duration_ms ?? 1000),
      raw_command_enabled: (consoleCfg.raw_command_enabled !== false),
      confirm_dangerous_raw_commands: (consoleCfg.confirm_dangerous_raw_commands !== false)
    };
    sdPreviewSupported = !!sdCfg.enable_preview;
    sdEnableStart = sdCfg.enable_start !== false;
    sdEnableDelete = sdCfg.enable_delete !== false;

    const stepSel = document.getElementById('jogStep');
    const feedSel = document.getElementById('jogFeed');
    const steps = Array.isArray(mc.jog_steps) && mc.jog_steps.length ? mc.jog_steps : [0.1,1,5,10,50];
    const feeds = Array.isArray(mc.feedrates) && mc.feedrates.length ? mc.feedrates : [500,1000,3000,6000];
    stepSel.innerHTML = '';
    feedSel.innerHTML = '';
    steps.forEach(s=>{ const o=document.createElement('option'); o.value=String(s); o.textContent=String(s); stepSel.append(o); });
    feeds.forEach(f=>{ const o=document.createElement('option'); o.value=String(f); o.textContent=String(f); feedSel.append(o); });
    stepSel.value = String(mc.default_jog_step ?? mc.default_jog_step_mm ?? 10);
    feedSel.value = String(mc.default_feedrate ?? 3000);
    if(!steps.map(String).includes(stepSel.value)){ stepSel.value = String(steps[0]); }
    if(!feeds.map(String).includes(feedSel.value)){ feedSel.value = String(feeds[0]); }

    const testFire = document.getElementById('testFire');
    if(testFire){
      testFire.disabled = !manualCfg.test_fire_enabled;
      if(!manualCfg.test_fire_enabled) testFire.title = 'Disabled by safety settings';
    }
    const presetBtn = document.getElementById('presetMoveBtn');
    const presetRow = document.getElementById('presetRow');
    if(presetBtn) presetBtn.textContent = manualCfg.preset_label || 'Go To Preset';
    if(presetRow) presetRow.style.display = manualCfg.preset_enabled ? 'flex' : 'none';
    const cmdWrap = document.getElementById('consoleCommandWrap');
    const cmdStatus = document.getElementById('consoleCommandStatus');
    const cmdInput = document.getElementById('consoleCommandInput');
    const cmdSend = document.getElementById('consoleCommandSend');
    if(cmdWrap) cmdWrap.style.display = manualCfg.raw_command_enabled ? 'block' : 'none';
    if(cmdInput) cmdInput.disabled = !manualCfg.raw_command_enabled;
    if(cmdSend) cmdSend.disabled = !manualCfg.raw_command_enabled;
    if(cmdStatus && !manualCfg.raw_command_enabled){
      cmdStatus.textContent = 'Raw console command sender is disabled in Settings.';
    }
  } catch(_err){
    // keep defaults if config fetch fails
  }
}

function bind(){
  const cam=document.getElementById('cam');
  const calibrationModal = document.getElementById('camera-calibration-modal');
  const calibrationFrame = document.getElementById('camera-calibration-frame');
  const closeCalibrationBtn = document.getElementById('close-calibration-modal');
  const openCalibrationWindowBtn = document.getElementById('open-calibration-window');
  const calibrationUrl = '/camera/calibration';
  const cameraStatus=document.getElementById('camera-test-status');
  let cameraTestStatusToken = 0;
  const setCameraTestStatus = (message, kind='muted', autoClearMs=0)=>{
    if(!cameraStatus) return;
    cameraStatus.textContent = message || '';
    cameraStatus.classList.remove('ok','warn','error','muted');
    cameraStatus.classList.add(kind || 'muted');
    if(autoClearMs > 0 && message){
      const token = ++cameraTestStatusToken;
      setTimeout(()=>{
        if(!cameraStatus) return;
        if(token !== cameraTestStatusToken) return;
        cameraStatus.textContent = '';
        cameraStatus.classList.remove('ok','warn','error');
        cameraStatus.classList.add('muted');
      }, autoClearMs);
    }
  };
  document.getElementById('camRefresh').onclick=()=>{
    if(!cameraVideoEnabled){
      setCameraTestStatus('Camera video is disabled. Enable video first.', 'warn', 8000);
      return;
    }
    const path = cameraActivePath || '/camera/stream';
    cam.src = path + '?_=' + Date.now();
    setCameraTestStatus('Camera stream reloaded.', 'muted', 5000);
    refreshConsole();
  };
  const camTestBtn = document.getElementById('camTest');
  camTestBtn.onclick=async()=>{
    camTestBtn.disabled = true;
    setCameraTestStatus('Testing camera...', 'muted');
    try{
      const r = await api('/api/camera/test','POST');
      if(r && r.ok){
        setCameraTestStatus('Camera test passed.', 'ok', 10000);
      }else{
        setCameraTestStatus(`Camera test failed: ${(r && (r.error || r.message)) || 'Unknown error'}`, 'error', 10000);
      }
      refreshConsole();
    }catch(err){
      const errMsg = (err && err.message) ? err.message : String(err || 'Network error');
      setCameraTestStatus(`Camera test failed: ${errMsg}`, 'error', 10000);
    }finally{
      camTestBtn.disabled = false;
    }
  };
  document.getElementById('camCapture').onclick=()=>api('/api/camera/capture','POST').then((r)=>{refreshConsole();loadSnapshots();if(r.ok)document.getElementById('camMsg').textContent='Snapshot saved: '+r.filename;});
  document.getElementById('snapOpenFolder').onclick=()=>api('/api/snapshots/open-folder','POST').then(refreshConsole);
  const openCalibrationModal = ()=>{
    if(!calibrationModal || !calibrationFrame) return;
    calibrationFrame.src = calibrationUrl;
    calibrationModal.classList.remove('hidden');
    calibrationModal.setAttribute('aria-hidden', 'false');
  };
  const closeCalibrationModal = ()=>{
    if(!calibrationModal || !calibrationFrame) return;
    calibrationModal.classList.add('hidden');
    calibrationModal.setAttribute('aria-hidden', 'true');
    calibrationFrame.src = '';
  };
  document.getElementById('camCalibrate').onclick=()=>{
    openCalibrationModal();
    document.getElementById('camMsg').textContent='Calibration opened.';
  };
  if(closeCalibrationBtn){
    closeCalibrationBtn.onclick=()=>closeCalibrationModal();
  }
  if(calibrationModal){
    calibrationModal.onclick=(ev)=>{
      if(ev.target === calibrationModal) closeCalibrationModal();
    };
  }
  if(openCalibrationWindowBtn){
    openCalibrationWindowBtn.onclick=()=>{
      const win = window.open(calibrationUrl, 'ray5_camera_calibration', 'popup=yes,width=1200,height=850,resizable=yes,scrollbars=yes');
      if(win) win.focus();
    };
  }
  document.addEventListener('keydown', (ev)=>{
    if(ev.key === 'Escape' && calibrationModal && !calibrationModal.classList.contains('hidden')){
      closeCalibrationModal();
    }
  });
  document.getElementById('camVideoToggle').onclick=async()=>{
    const nextEnabled = !cameraVideoEnabled;
    const r = await setCameraVideoEnabled(nextEnabled);
    if(!r.ok){
      setCameraTestStatus(`Camera video toggle failed: ${r.message || 'unknown error'}`, 'error', 10000);
      return;
    }
    if(cameraVideoEnabled){
      stopTimelapsePlayback(false);
      cameraDisplayMode = 'live';
      const path = cameraActivePath || '/camera/stream';
      cam.removeAttribute('src');
      cam.src = path + '?_=' + Date.now();
      setCameraTestStatus('Camera video enabled.', 'ok', 8000);
    }else{
      stopTimelapsePlayback(true);
      cam.removeAttribute('src');
      cameraActivePath = '';
      cam.src = cameraPlaceholderPath;
      setCameraTestStatus('Camera video disabled.', 'muted', 8000);
    }
    refreshConsole();
    refreshStatus();
  };
  cam.onerror=()=>{
    if((cam.src||'').includes('camera_placeholder.svg')) return;
    cam.removeAttribute('src');
    cameraActivePath = '';
    cam.src = cameraPlaceholderPath;
    cam.style.opacity='1';
    cam.style.display='block';
    const off=document.getElementById('cameraOffline');
    if(off) off.style.display='none';
    document.getElementById('camMsg').textContent='Camera stream unavailable.';
    setCameraTestStatus('Camera stream unavailable.', 'error', 10000);
  };
  cam.onload=()=>{
    if((cam.src||'').includes('camera_placeholder.svg')) return;
  };

  document.getElementById('importBtn').onclick=async()=>{
    if(jobImportBusy) return;
    const f=document.getElementById('jobFile').files[0];if(!f)return;
    jobImportBusy = true;
    document.getElementById('importBtn').disabled = true;
    const fd=new FormData();fd.append('file',f);
    try{
      const r = await fetch('/api/jobs/import',{method:'POST',body:fd});
      const data = await r.json();
      document.getElementById('jobsMsg').textContent=data.ok?'Import complete':'Import failed: '+(data.error||'unknown');
      if(data.ok){
        await refreshJobs({preserveMessage:true});
      }
      await refreshConsole();
    } finally {
      jobImportBusy = false;
      document.getElementById('importBtn').disabled = false;
    }
  };
  document.getElementById('jobsRefresh').onclick=refreshJobs;
  const timelapseRefresh = document.getElementById('timelapseRefresh');
  if(timelapseRefresh) timelapseRefresh.onclick = loadTimelapses;
  const timelapseStart = document.getElementById('timelapseStart');
  if(timelapseStart) timelapseStart.onclick = startTimelapseManual;
  const timelapseStop = document.getElementById('timelapseStop');
  if(timelapseStop) timelapseStop.onclick = stopTimelapseManual;
  const timelapseSelectAll = document.getElementById('timelapseSelectAll');
  if(timelapseSelectAll){
    timelapseSelectAll.onchange = ()=>{
      if(timelapseSelectAll.checked){
        selectedTimelapseFiles.clear();
        currentTimelapseItems.forEach(item=>selectedTimelapseFiles.add(item.name));
      }else{
        selectedTimelapseFiles.clear();
      }
      loadTimelapses();
    };
  }
  const timelapseClearSelection = document.getElementById('timelapseClearSelection');
  if(timelapseClearSelection){
    timelapseClearSelection.onclick = ()=>{
      selectedTimelapseFiles.clear();
      loadTimelapses();
    };
  }
  const timelapseDeleteSelected = document.getElementById('timelapseDeleteSelected');
  if(timelapseDeleteSelected){
    timelapseDeleteSelected.onclick = deleteSelectedTimelapses;
  }
  const selectAllJobs = document.getElementById('jobsSelectAll');
  if(selectAllJobs){
    selectAllJobs.onchange = ()=>{
      if(selectAllJobs.checked){
        selectedImportedJobs.clear();
        lastImportedJobs.forEach(j => selectedImportedJobs.add(String(j.name||j.filename||'')));
      }else{
        selectedImportedJobs.clear();
      }
      refreshJobs();
    };
  }
  const clearSelectionBtn = document.getElementById('jobsClearSelection');
  if(clearSelectionBtn){
    clearSelectionBtn.onclick = ()=>{
      selectedImportedJobs.clear();
      refreshJobs();
    };
  }
  const deleteSelectedBtn = document.getElementById('jobsDeleteSelected');
  if(deleteSelectedBtn){
    deleteSelectedBtn.onclick = deleteSelectedImportedJobs;
  }

  document.getElementById('homeAll').onclick=()=>manualCall('/api/home',{axis:'all'});
  document.getElementById('presetMoveBtn').onclick=()=>manualCall('/api/preset-move',{});
  document.getElementById('unlock').onclick=()=>manualCall('/api/unlock',{});

  document.getElementById('xMinus').onclick=()=>manualCall('/api/move',{axis:'x',distance:-currentStep(),feedrate:currentFeed()});
  document.getElementById('xPlus').onclick=()=>manualCall('/api/move',{axis:'x',distance:currentStep(),feedrate:currentFeed()});
  document.getElementById('yMinus').onclick=()=>manualCall('/api/move',{axis:'y',distance:-currentStep(),feedrate:currentFeed()});
  document.getElementById('yPlus').onclick=()=>manualCall('/api/move',{axis:'y',distance:currentStep(),feedrate:currentFeed()});
  document.getElementById('xyMinusPlus').onclick=()=>manualCall('/api/move',{dx:-currentStep(),dy:currentStep(),feedrate:currentFeed()});
  document.getElementById('xyPlusPlus').onclick=()=>manualCall('/api/move',{dx:currentStep(),dy:currentStep(),feedrate:currentFeed()});
  document.getElementById('xyMinusMinus').onclick=()=>manualCall('/api/move',{dx:-currentStep(),dy:-currentStep(),feedrate:currentFeed()});
  document.getElementById('xyPlusMinus').onclick=()=>manualCall('/api/move',{dx:currentStep(),dy:-currentStep(),feedrate:currentFeed()});
  document.getElementById('centerBed').onclick=()=>manualCall('/api/manual/center',{});
  document.getElementById('airOn').onclick=()=>manualCall('/api/air/on',{});
  document.getElementById('airOff').onclick=()=>manualCall('/api/air/off',{});
  document.getElementById('testFire').onclick=()=>{
    const confirmText = manualCfg.confirm_dangerous_actions ? 'Run low-power test fire?' : '';
    return manualCall(
      '/api/laser/test-fire',
      {s_value: manualCfg.test_fire_s_value || 50, duration_ms: manualCfg.test_fire_duration_ms || 1000},
      confirmText
    );
  };
  document.getElementById('pauseBtn').onclick=()=>manualCall('/api/pause',{},manualCfg.confirm_dangerous_actions?'Pause current job?':'');
  document.getElementById('resumeBtn').onclick=()=>manualCall('/api/resume',{});
  document.getElementById('stop').onclick=()=>manualCall('/api/stop',{},manualCfg.confirm_dangerous_actions?'Stop current job?':'');

  const consoleEl = document.getElementById('console');
  if(consoleEl){
    ensureConsoleJumpButton();
    consoleEl.addEventListener('scroll', ()=>{
      consoleAutoScroll = isConsoleNearBottom(consoleEl);
      updateConsoleJumpButton();
    });
  }

  document.getElementById('consoleClear').onclick=()=>api('/api/console/clear','POST').then(()=>{
    consoleAutoScroll = true;
    return refreshConsole();
  });
  const cmdInput = document.getElementById('consoleCommandInput');
  const cmdSend = document.getElementById('consoleCommandSend');
  if(cmdSend) cmdSend.onclick = sendRawConsoleCommand;
  if(cmdInput){
    cmdInput.addEventListener('keydown', (ev)=>{
      if(ev.key === 'Enter'){
        ev.preventDefault();
        sendRawConsoleCommand();
        return;
      }
      if(ev.key === 'ArrowUp'){
        if(!rawCommandHistory.length) return;
        ev.preventDefault();
        if(rawCommandHistoryIndex < 0) rawCommandHistoryIndex = rawCommandHistory.length - 1;
        else rawCommandHistoryIndex = Math.max(0, rawCommandHistoryIndex - 1);
        cmdInput.value = rawCommandHistory[rawCommandHistoryIndex] || '';
        return;
      }
      if(ev.key === 'ArrowDown'){
        if(!rawCommandHistory.length) return;
        ev.preventDefault();
        rawCommandHistoryIndex = Math.min(rawCommandHistory.length, rawCommandHistoryIndex + 1);
        cmdInput.value = rawCommandHistoryIndex >= rawCommandHistory.length ? '' : (rawCommandHistory[rawCommandHistoryIndex] || '');
      }
    });
  }
  document.getElementById('filesRefresh').onclick=loadSdFiles;
  const sdSelectAll = document.getElementById('sdSelectAll');
  if(sdSelectAll){
    sdSelectAll.onchange = ()=>{
      if(sdSelectAll.checked){
        selectedSdFiles.clear();
        currentSdFiles.forEach(f=>{
          if(f.can_delete){
            selectedSdFiles.set(sdFileKey(f), {name: String(f.name||''), path: String(f.path || f.name || '')});
          }
        });
      }else{
        selectedSdFiles.clear();
      }
      loadSdFiles();
    };
  }
  const sdClearSelection = document.getElementById('sdClearSelection');
  if(sdClearSelection){
    sdClearSelection.onclick = ()=>{
      selectedSdFiles.clear();
      loadSdFiles();
    };
  }
  const sdDeleteSelected = document.getElementById('sdDeleteSelected');
  if(sdDeleteSelected){
    sdDeleteSelected.onclick = deleteSelectedSdFiles;
  }
  document.getElementById('sdUploadBtn').onclick=async()=>{
    const input = document.getElementById('sdUploadFile');
    const btnEl = document.getElementById('sdUploadBtn');
    const msgEl = document.getElementById('sdMsg');
    const file = input && input.files ? input.files[0] : null;
    if(!file){
      msgEl.textContent = 'Choose a file first.';
      return;
    }
    const name = (file.name || '').toLowerCase();
    if(!(name.endsWith('.gc') || name.endsWith('.nc') || name.endsWith('.gcode'))){
      msgEl.textContent = 'Only .gc, .nc, .gcode are allowed.';
      return;
    }
    btnEl.disabled = true;
    msgEl.textContent = 'Uploading...';
    try{
      const fd = new FormData();
      fd.append('file', file);
      fd.append('path', currentSdPath || '/');
      const r = await fetch('/api/files/upload', {method:'POST', body: fd});
      const data = await r.json();
      if(data.ok){
        msgEl.textContent = `Uploaded to SD: ${data.filename}`;
        await loadSdFiles();
        await refreshConsole();
      }else{
        msgEl.textContent = `Upload failed: ${data.message||'unknown error'}`;
        await refreshConsole();
      }
    }catch(err){
      msgEl.textContent = `Upload failed: ${String(err)}`;
    }finally{
      btnEl.disabled = false;
    }
  };
  document.getElementById('sdStop').onclick=stopJob;
}

bind();
loadManualConfig();
refreshStatus();refreshJobs();loadSdFiles();loadTimelapses();loadTimelapseState();refreshConsole();loadSnapshots();
setInterval(refreshStatus,3000);
setInterval(refreshConsole,5000);
setInterval(()=>refreshJobs({preserveMessage:true}),5000);
