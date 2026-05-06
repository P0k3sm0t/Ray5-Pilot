async function api(url, method='GET', body=null){
  const opt={method,headers:{}};
  if(body){opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body)}
  const r=await fetch(url,opt);
  return r.json();
}

function fmtPos(v){return (v===null||v===undefined||v==='')?'---':v}
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

let consoleAutoScroll = true;
const consoleBottomThreshold = 40;
let cameraActivePath = '';

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
  document.getElementById('status').innerHTML = `
    <div>Online: <b>${d.online?'Yes':'No'}</b></div>
    <div>WebSocket: <b>${d.websocket_connected?'Connected':'Disconnected'}</b></div>
    <div>PAGEID: <b>${fmtPos(d.websocket_page_id)}</b></div>
    <div>State: <b>${d.machine_state_label||d.state||d.machine_state||'UNKNOWN'}</b></div>
    <div>MPos X: ${fmtPos(mpos.x)} Y: ${fmtPos(mpos.y)}</div>
    <div>Feed: ${fmtPos(d.feed)} Spindle: ${fmtPos(d.spindle)}</div>
    <div>Status Source: ${d.status_source||'unknown'}</div>
    <div>Position Source: ${d.position_source||'unknown'}</div>
    <div>Alarm: ${fmtPos(d.alarm_message)}</div>
    <div>Last Error: ${fmtPos(d.last_error)}</div>
  `;

  const cam=document.getElementById('cam');
  const msg=document.getElementById('camMsg');
  const off=document.getElementById('cameraOffline');
  const statusLine=document.getElementById('cameraStatusLine');
  if(d.camera_preview_supported){
    cam.style.opacity='1';
    const nextPath = (d.camera_proxy_path||'/camera/stream');
    if(cameraActivePath !== nextPath || !cam.getAttribute('src')){
      cameraActivePath = nextPath;
      cam.src = cameraActivePath + '?_=' + Date.now();
    }
    msg.textContent='Camera: '+(d.camera_url_masked||'configured');
    statusLine.textContent='Camera source: '+(d.camera_url_masked||'configured');
    off.style.display='none';
    cam.style.display='block';
  } else {
    cam.removeAttribute('src');
    cameraActivePath = '';
    cam.style.opacity='0.35';
    msg.textContent='Camera unavailable or disabled.';
    statusLine.textContent='Camera unavailable or disabled.';
    off.style.display='block';
    cam.style.display='none';
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

async function refreshJobs(){
  const d=await api('/api/jobs');
  const el=document.getElementById('jobsBody');
  const msg=document.getElementById('jobsMsg');
  const watch=document.getElementById('jobWatchInfo');
  el.innerHTML='';
  watch.textContent = 'Watching: watched_gcode | Extensions: .gcode, .gc, .nc';
  const jobs = d.jobs||[];
  if(!jobs.length){
    const tr=document.createElement('tr');
    tr.innerHTML='<td colspan="5" class="muted small">No imported jobs yet. Import a .gcode, .gc, or .nc file, or drop one into the watched folder.</td>';
    el.append(tr);
    msg.textContent='Loaded 0 imported job(s)';
    return;
  }
  jobs.forEach(j=>{
    const row=document.createElement('tr');
    const mod = shortDate(j.modified);
    const size = humanSize(j.size_bytes ?? j.size);
    const name = j.name||j.filename||'unknown';
    const bounds = j.bounds;
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
    const delBtn=btn('Delete',()=>{if(!confirm('Delete local imported job '+name+' ?')) return; fetch('/api/jobs/'+encodeURIComponent(name),{method:'DELETE'}).then(()=>{refreshJobs();refreshConsole();});});
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
    row.append(actions);
    el.append(row);
  });
  msg.textContent = `Loaded ${jobs.length} imported job(s)`;
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
  await loadSdFiles();
  await refreshConsole();
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
  if(!files.length){
    const tr=document.createElement('tr');
    tr.innerHTML='<td colspan="5" class="sd-muted">No SD files found.</td>';
    filesEl.append(tr);
    return;
  }
  files.forEach(f=>{
    const row=document.createElement('tr');
    const name=f.name||'---';
    const typeLabel = f.is_directory ? 'Folder / Protected' : ((f.type||'unknown')==='gcode' ? 'G-code' : (f.type||'unknown'));
    const sizeVal = (!f.size || f.size==='-1') ? '---' : f.size;
    const modVal = (!f.modified || f.modified==='') ? '---' : f.modified;
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
    row.append(actionTd);
    row.onclick=(ev)=>{ if(ev.target.tagName!=='BUTTON') selectSdFile(f); };
    filesEl.append(row);
  });
}

async function loadSdFiles(){
  const msgEl = document.getElementById('sdMsg');
  msgEl.textContent = 'Loading SD files...';
  const d = await api('/api/files?path='+encodeURIComponent(currentSdPath||'/'));
  if(!d.ok){
    msgEl.textContent = 'SD refresh failed: '+(d.error||'unknown');
    document.getElementById('sdFilesBody').innerHTML = '<tr><td colspan="5" class="sd-muted">Unable to load SD files.</td></tr>';
    return;
  }
  renderSdFiles(d);
  msgEl.textContent = `Loaded ${ (d.files||[]).length } item(s).`;
}

let manualBusy = false;
let manualCfg = {
  confirm_dangerous_actions: true,
  enable_z_jog: false,
  test_fire_enabled: false,
  preset_enabled: true,
  preset_label: 'Go To Preset',
  test_fire_power: 1,
  test_fire_duration_ms: 100
};
let jobImportBusy = false;
function setManualBusy(state){
  manualBusy = state;
  document.querySelectorAll('#homeAll,#unlock,#xMinus,#xPlus,#yMinus,#yPlus,#airOn,#airOff,#testFire,#stop,#pauseBtn,#resumeBtn,#presetMoveBtn').forEach(el=>{if(el)el.disabled=state;});
}

async function manualCall(url, body=null, confirmText=''){
  if(manualBusy) return;
  if(confirmText && !confirm(confirmText)) return;
  setManualBusy(true);
  try{
    const r = await api(url,'POST',body);
    document.getElementById('manualMsg').textContent = r.ok ? 'OK: '+(r.message||'command sent') : 'Error: '+(r.message||r.error||'request failed');
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
    manualCfg = {
      confirm_dangerous_actions: (safety.confirm_dangerous_actions !== false),
      enable_z_jog: !!(mc.enable_z_jog ?? mc.enable_jog_z ?? false),
      test_fire_enabled: !!(safety.test_fire_enabled ?? safety.enable_test_fire ?? false),
      preset_enabled: (mc.preset_enabled !== false),
      preset_label: String(mc.preset_label || 'Go To Preset'),
      test_fire_power: Number(safety.test_fire_power ?? 1),
      test_fire_duration_ms: Number(safety.test_fire_duration_ms ?? 100)
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
  } catch(_err){
    // keep defaults if config fetch fails
  }
}

function bind(){
  const cam=document.getElementById('cam');
  document.getElementById('camRefresh').onclick=()=>{
    const path = cameraActivePath || '/camera/stream';
    cam.src = path + '?_=' + Date.now();
  };
  document.getElementById('camTest').onclick=()=>api('/api/camera/test','POST').then(refreshConsole);
  document.getElementById('camCapture').onclick=()=>api('/api/camera/capture','POST').then((r)=>{refreshConsole();loadSnapshots();if(r.ok)document.getElementById('camMsg').textContent='Snapshot saved: '+r.filename;});
  document.getElementById('snapOpenFolder').onclick=()=>api('/api/snapshots/open-folder','POST').then(refreshConsole);
  document.getElementById('camCalibrate').onclick=()=>api('/api/camera/calibration/run','POST').then((r)=>{refreshConsole();document.getElementById('camMsg').textContent=r.ok?'Calibration launched':(r.error||'Calibration failed');});
  cam.onerror=()=>{
    document.getElementById('camMsg').textContent='Camera unavailable or disabled.';
    const off=document.getElementById('cameraOffline');
    if(off) off.style.display='block';
    cam.style.display='none';
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
      refreshJobs();refreshConsole();
    } finally {
      jobImportBusy = false;
      document.getElementById('importBtn').disabled = false;
    }
  };
  document.getElementById('jobsRefresh').onclick=refreshJobs;

  document.getElementById('homeAll').onclick=()=>manualCall('/api/home',{axis:'all'});
  document.getElementById('presetMoveBtn').onclick=()=>manualCall('/api/preset-move',{},manualCfg.confirm_dangerous_actions?'Move to preset position?':'');
  document.getElementById('unlock').onclick=()=>manualCall('/api/unlock',{});

  document.getElementById('xMinus').onclick=()=>manualCall('/api/move',{axis:'x',distance:-currentStep(),feedrate:currentFeed()});
  document.getElementById('xPlus').onclick=()=>manualCall('/api/move',{axis:'x',distance:currentStep(),feedrate:currentFeed()});
  document.getElementById('yMinus').onclick=()=>manualCall('/api/move',{axis:'y',distance:-currentStep(),feedrate:currentFeed()});
  document.getElementById('yPlus').onclick=()=>manualCall('/api/move',{axis:'y',distance:currentStep(),feedrate:currentFeed()});
  document.getElementById('airOn').onclick=()=>manualCall('/api/air/on',{});
  document.getElementById('airOff').onclick=()=>manualCall('/api/air/off',{});
  document.getElementById('testFire').onclick=()=>{
    const confirmText = manualCfg.confirm_dangerous_actions ? 'Run low-power test fire?' : '';
    return manualCall(
      '/api/laser/test-fire',
      {power: manualCfg.test_fire_power || 1, duration_ms: manualCfg.test_fire_duration_ms || 100},
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
  document.getElementById('filesRefresh').onclick=loadSdFiles;
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
refreshStatus();refreshJobs();loadSdFiles();refreshConsole();loadSnapshots();
setInterval(refreshStatus,3000);
setInterval(refreshConsole,5000);
