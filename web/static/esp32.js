/* ESP32 settings use the existing HTTP APIs. No device actions occur during navigation. */
const ep = id => document.getElementById(id);
const ESP_SECTIONS = [
  ['overview','Device Overview'], ['network','Wi-Fi & Network'], ['services','Device Services'],
  ['hardware','Sensors & Hardware'], ['backups','Backups & Compare'], ['advanced','Advanced Tools'],
];
const NETWORK_SENSITIVE_PATHS = new Set(['Sta/SSID','Sta/Password','Sta/IPMode','Sta/IP','Sta/Gateway','Sta/Netmask','AP/SSID','AP/Password','AP/IP','AP/Channel','Radio/Mode','Http/Port','Http/Enable']);
let eepromSettings = [];
let dirty = new Map();
let rowStatus = new Map();
let backupList = [];
let deviceInfo = null;
let wsInfo = null;
let wsReceivedAt = 0;
let activeSection = 'overview';
let espBusy = false;
let eepromReady = false;
let reviewing = false;
let reviewedChanges = null;
let sessionBackupDownloaded = false;
let wsRefreshing = false;
let lastReadAt = null;
const secretValues = new Set();
const pageConfig = JSON.parse(ep('espPageConfig').textContent);

function sensitive(value) { return /pass|token|key|secret|credential|auth|pwd/i.test(String(value || '')); }
function isSensitive(setting) { return sensitive(`${setting.group || setting.F || ''} ${setting.path || setting.P || ''} ${setting.label || setting.H || ''}`); }
function maskSensitiveText(value) {
  let text = String(value ?? '');
  for (const secret of Array.from(secretValues).sort((a,b) => b.length-a.length)) if (secret) text = text.split(secret).join('[redacted]');
  return text.replace(/((?:password|pass|token|secret|credential|pwd)\s*[:=]\s*)([^\r\n,}\]]+)/ig, '$1[redacted]')
    .replace(/\b((?:rtsp|https?):\/\/)[^/\s@]+@/ig, '$1[redacted]@');
}
function sanitize(value) {
  if (Array.isArray(value)) return value.map(sanitize);
  if (value && typeof value === 'object') {
    const secretRow = isSensitive(value);
    return Object.fromEntries(Object.entries(value).map(([key,item]) => [key,
      sensitive(key) || (secretRow && ['value','raw_value','V','current','backup','command','response','message','raw'].includes(key)) ? '[redacted]' : sanitize(item)
    ]));
  }
  if (typeof value === 'string') {
    try { if (/^[\s]*[\[{]/.test(value)) return JSON.stringify(sanitize(JSON.parse(value)), null, 2); } catch (_) { /* Plain controller reply. */ }
    return maskSensitiveText(value);
  }
  return value;
}
function safeJson(value) { return JSON.stringify(sanitize(value), null, 2); }
function rememberSecrets(settings) {
  settings.filter(isSensitive).forEach(setting => {
    for (const value of [setting.raw_value,setting.value,setting.V]) if (value && !/^[*]+$|^\[.*\]$/.test(String(value))) secretValues.add(String(value));
  });
}
function logRaw(label, data) {
  const entry = `[${new Date().toLocaleTimeString()}] ${label}\n${safeJson(data)}\n\n`;
  ep('rawLog').textContent = (entry + ep('rawLog').textContent).slice(0, 40000);
}
function setMsg(text) { ep('msg').textContent = maskSensitiveText(text); }
async function api(url, method='GET', body=null) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  const options = {method, signal:controller.signal, headers:{'X-Ray5-Pilot-Request':'1'}};
  if (body !== null) { options.headers['Content-Type']='application/json'; options.body=JSON.stringify(body); }
  try {
    const response=await fetch(url,options);
    const data=await response.json();
    return {...data,_http_status:response.status};
  } catch (err) { return {ok:false,error:err.name==='AbortError'?'Request timed out.':`Request failed: ${err.message || err}`,_http_status:0}; }
  finally { clearTimeout(timer); }
}
function groupFor(setting) {
  const path=setting.path || '';
  if (/^(Sta|AP|Radio)\//i.test(path)) return 'network';
  if (/^(System|Http|Telnet)\//i.test(path)) return 'services';
  if (/^(Flame|Accel)\//i.test(path)) return 'hardware';
  return 'advanced';
}
function optionPairs(setting) {
  return (Array.isArray(setting.options)?setting.options:[]).flatMap(option => option && typeof option==='object' ? Object.entries(option).map(([label,value])=>({label,value:String(value)})) : []);
}
function currentValue(setting) { return String(setting.raw_value ?? setting.value ?? ''); }
function displayValue(setting, value) {
  if (isSensitive(setting)) return 'Hidden (unchanged)';
  return optionPairs(setting).find(option=>option.value===String(value))?.label || String(value);
}
function validIP(value) {
  if (value.includes(':')) { try { return new URL(`http://[${value}]`).hostname.startsWith('['); } catch (_) { return false; } }
  return /^\d{1,3}(\.\d{1,3}){3}$/.test(value) && value.split('.').every(part=>Number(part)<=255 && (part==='0'||!part.startsWith('0')));
}
function validationError(setting, value) {
  value=String(value);
  if (/[\x00-\x1f\x7f]/.test(value)) return 'Control characters are not allowed.';
  const type=String(setting.type || '').toUpperCase();
  const hasMin=setting.min!==null && setting.min!==undefined && String(setting.min)!=='';
  const hasMax=setting.size_or_max!==null && setting.size_or_max!==undefined && String(setting.size_or_max)!=='';
  if (type==='S') {
    if (hasMin && Array.from(value).length<Number(setting.min)) return `Enter at least ${setting.min} characters.`;
    if (hasMax && Array.from(value).length>Number(setting.size_or_max)) return `Use at most ${setting.size_or_max} characters.`;
  } else if (type==='I'||type==='B') {
    if (!/^-?\d+(\.\d+)?$/.test(value) || !Number.isFinite(Number(value))) return 'Enter a number.';
    if (hasMin && Number(value)<Number(setting.min)) return `Minimum: ${setting.min}.`;
    if (hasMax && Number(value)>Number(setting.size_or_max)) return `Maximum: ${setting.size_or_max}.`;
    const options=optionPairs(setting);
    if (options.length && !options.some(option=>option.value===value)) return 'Choose a firmware-supported option.';
  } else if (type==='A' && !validIP(value)) return 'Enter a valid IP address.';
  return '';
}
function changesList() { return eepromSettings.filter(setting=>dirty.has(setting.path)).map(setting=>({path:setting.path,type:setting.type,value:dirty.get(setting.path)})); }
function hasErrors() { return eepromSettings.some(setting=>dirty.has(setting.path)&&validationError(setting,dirty.get(setting.path))); }
function updateControls() {
  ep('changedBadge').textContent=dirty.size?`${dirty.size} pending change${dirty.size===1?'':'s'}`:'No pending changes';
  ep('saveChanges').disabled=espBusy||!eepromReady||!dirty.size||hasErrors();
  ep('saveChanges').textContent=dirty.size?`Review ${dirty.size} change${dirty.size===1?'':'s'}`:'Review changes';
  ep('discardChanges').disabled=espBusy||!dirty.size;
  ep('espApply').disabled=espBusy||!eepromReady||!reviewedChanges?.length||
    (reviewedChanges.some(change=>NETWORK_SENSITIVE_PATHS.has(change.path))&&!ep('espNetworkAck').checked)||
    (!sessionBackupDownloaded&&!ep('espBackupAck').checked);
  ep('espBack').disabled=espBusy;
  ['refreshAll','refreshInfo','refreshEeprom','refreshWs','backupEeprom','openNative','espCommandsEnabled'].forEach(id=>ep(id).disabled=espBusy);
  ['backupSelect','loadBackup','compareBackup'].forEach(id=>ep(id).disabled=espBusy||!backupList.length);
  document.querySelectorAll('#espCategories button').forEach(button=>{
    button.disabled=espBusy;
    button.setAttribute('aria-pressed',String(button.dataset.section===activeSection));
    button.querySelector('span:last-child').textContent=eepromSettings.some(setting=>groupFor(setting)===button.dataset.section&&dirty.has(setting.path))?'Edited':'';
  });
  document.querySelectorAll('.esp-value,.esp-secret-enable,.esp-undo').forEach(input=>{
    input.disabled=espBusy||!eepromReady||input.dataset.staticDisabled==='true';
  });
  ['gcodeCmd','espCmd','sendGcode','sendEsp'].forEach(id=>ep(id).disabled=espBusy||!ep('espCommandsEnabled').checked);
  ep('espReadState').textContent=espBusy?'Working...':eepromReady?`EEPROM read at ${lastReadAt.toLocaleTimeString()}`:'EEPROM unavailable / read required';
}
function showSection(section) {
  activeSection=section;reviewing=false;reviewedChanges=null;
  ep('espReview').hidden=true;
  document.querySelectorAll('[data-panel]').forEach(panel=>panel.hidden=panel.dataset.panel!==section);
  renderEeprom();updateControls();
}
function kvGrid(element, rows) {
  element.replaceChildren();
  rows.forEach(([label,value])=>{
    const row=document.createElement('div');row.className='esp-kv';
    const name=document.createElement('span'),text=document.createElement('span');name.textContent=label;text.textContent=value??'Unavailable';
    row.append(name,text);element.appendChild(row);
  });
}
function renderHealth() {
  const age=typeof wsInfo?.last_status_age_seconds==='number' ? wsInfo.last_status_age_seconds+(Date.now()-wsReceivedAt)/1000 : null;
  const connected=wsInfo?.websocket_connected===true;
  const fresh=connected&&age!==null&&age>=0&&age<=5;
  kvGrid(ep('espHealth'),[
    ['ESP32 HTTP / API',deviceInfo?.ok?`Responded at ${deviceInfo.http_host || 'configured host'}:${deviceInfo.http_port || 'unknown port'}`:'Unavailable / not read'],
    ['WebSocket status',!connected?'Disconnected / not available':fresh?`Receiving (${age.toFixed(1)}s old)`:'Connected; waiting for fresh status'],
    ['Controller state',fresh?String(wsInfo.latest_status?.state || 'Unknown'):'Unknown'],
    ['Wi-Fi network',eepromReady?eepromSettings.find(setting=>setting.path==='Sta/SSID')?.value || 'Not reported':'Unavailable'],
  ]);
}
async function loadInfo() {
  const data=await api('/api/esp32/info');deviceInfo=data;
  ep('espInfoRaw').textContent=safeJson(data.raw || data);
  kvGrid(ep('espInfoGrid'),[['Hostname',data.ok?data.hostname:'Unavailable'],['Firmware',data.ok?data.fw_version:'Unavailable'],['Hardware',data.ok?data.fw_hw:'Unavailable'],['Axes',data.ok?data.axis:'Unavailable'],['Primary storage',data.ok?data.primary_sd:'Unavailable']]);
  kvGrid(ep('espMoreInfo'),[['Firmware target',data.fw_target],['Authentication',data.authentication],['Secondary storage',data.secondary_sd],['WebSocket port',data.websocket_port],['Web communication',data.web_communication],['WebSocket addresses',Array.isArray(data.websocket_ips)?data.websocket_ips.join(', '):data.websocket_ip]]);
  logRaw(data.ok?'Device info':'Device info unavailable',data);renderHealth();
  return data;
}
async function loadWsStatus() {
  if(wsRefreshing)return;
  wsRefreshing=true;
  try {
    wsInfo=await api('/api/status/live');wsReceivedAt=Date.now();
    ep('wsAdvanced').textContent=safeJson(wsInfo);
    kvGrid(ep('wsInfoGrid'),[['Connected',String(wsInfo.websocket_connected===true)],['PAGEID',wsInfo.page_id],['Active ID',wsInfo.active_id],['Last status',maskSensitiveText(wsInfo.last_raw_status || 'Not received')],['Reconnect count',wsInfo.reconnect_count]]);
    renderHealth();
  } finally {wsRefreshing=false;}
}
function cleanSettings(settings) {
  rememberSecrets(settings);
  return settings.filter(setting=>setting.path).map(setting=>{
    const cleaned={...setting,path:String(setting.path)};
    if(isSensitive(setting)){cleaned.raw_value='';cleaned.value='[hidden]';}
    return cleaned;
  });
}
async function loadEeprom(attempts=null) {
  const data=await api('/api/esp32/eeprom');
  if(!data.ok||!Array.isArray(data.settings)||!data.settings.length){
    eepromReady=false;
    if(attempts)attempts.forEach((attempt,path)=>{
      if(!attempt.ok)rowStatus.set(path,`Failed: ${attempt.message}`);
      else if(isSensitive(eepromSettings.find(setting=>setting.path===path)||{}))rowStatus.set(path,'Accepted; secret value hidden (not read-back verified).');
      else rowStatus.set(path,'Not verified: device read unavailable. Reconnect and read again.');
    });
    renderEeprom();renderHealth();
    throw new Error(data.error || 'No EEPROM settings returned.');
  }
  const incoming=cleanSettings(data.settings),previous=new Map(eepromSettings.map(setting=>[setting.path,setting]));
  if(attempts){
    const returned=new Map(incoming.map(setting=>[setting.path,setting]));
    attempts.forEach((attempt,path)=>{
      const setting=returned.get(path);
      if(!attempt.ok){rowStatus.set(path,maskSensitiveText(`Failed: ${attempt.message}`));return;}
      if(isSensitive(previous.get(path)||{})){dirty.delete(path);rowStatus.set(path,'Accepted; secret value hidden (not read-back verified).');return;}
      if(!setting){rowStatus.set(path,'Not verified: setting missing from read-back.');return;}
      const equal=String(currentValue(setting))===String(attempt.value)||(['I','B'].includes(setting.type)&&Number(currentValue(setting))===Number(attempt.value));
      if(equal){dirty.delete(path);rowStatus.set(path,'Verified on device.');}
      else rowStatus.set(path,`Not verified: device reports ${maskSensitiveText(displayValue(setting,currentValue(setting)))}.`);
    });
    attempts.forEach((_,path)=>{if(!returned.has(path)&&previous.has(path))incoming.push(previous.get(path));});
  }
  eepromSettings=incoming;eepromReady=true;lastReadAt=new Date();
  logRaw('EEPROM read',{settings:incoming,raw:data.raw});renderEeprom();renderHealth();
  return data;
}
function fieldGroups(section) {
  if(section==='network')return [['Router connection (Station mode)',setting=>/^Sta\//i.test(setting.path)],['Access point & radio',setting=>/^(AP|Radio)\//i.test(setting.path)]];
  if(section==='services')return [['Name & web API',setting=>/^(System|Http)\//i.test(setting.path)],['Other services',setting=>/^Telnet\//i.test(setting.path)]];
  return [['Firmware-reported sensor parameters',setting=>groupFor(setting)==='hardware']];
}
function addPanelFields(section,target) {
  target.replaceChildren();
  fieldGroups(section).forEach(([title,predicate])=>{
    const settings=eepromSettings.filter(predicate);if(!settings.length)return;
    const panel=document.createElement('section');panel.className='esp-panel';
    const h=document.createElement('h3');h.textContent=title;panel.appendChild(h);
    const grid=document.createElement('div');grid.className='esp-field-grid';settings.forEach(setting=>grid.appendChild(renderField(setting)));
    panel.appendChild(grid);target.appendChild(panel);
  });
  if(!target.children.length){const message=document.createElement('p');message.className='esp-muted';message.textContent=eepromReady?'No settings in this category were reported by the firmware.':'Read EEPROM settings from the device to begin. Existing edits are kept if a read fails.';target.appendChild(message);}
}
function updateField(setting,wrapper) {
  const changed=dirty.has(setting.path);wrapper.classList.toggle('esp-dirty',changed);
  wrapper.querySelector('.esp-undo').hidden=!changed;
  const error=changed?validationError(setting,dirty.get(setting.path)):'';
  wrapper.querySelector('.esp-field-error').textContent=error;
  wrapper.querySelector('.esp-field-error').hidden=!error;
  wrapper.querySelector('.esp-row-status').textContent=rowStatus.get(setting.path)||'';
  const input=wrapper.querySelector('.esp-value');if(input)input.setAttribute('aria-invalid',String(!!error));
}
function renderField(setting) {
  const path=setting.path,changed=dirty.has(path),value=changed?dirty.get(path):currentValue(setting),secret=isSensitive(setting);
  const wrapper=document.createElement('div');wrapper.className='esp-field-wrap';wrapper.dataset.path=path;
  if(secret)wrapper.classList.add('esp-secret');
  if(setting.type==='S')wrapper.classList.add('esp-wide');
  const id='espValue_'+encodeURIComponent(path);
  let input;
  if(secret){
    const label=document.createElement('label');label.className='esp-check';
    const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.className='esp-secret-enable';checkbox.checked=changed;
    checkbox.setAttribute('aria-label',`Change ${setting.label || path}`);
    label.append(checkbox,document.createTextNode(`Change ${setting.label || path}`));wrapper.appendChild(label);
    const hint=document.createElement('p');hint.className='esp-field-help';hint.textContent='Stored value is hidden. Leave unchanged unless replacing it.';wrapper.appendChild(hint);
    checkbox.addEventListener('change',()=>{if(checkbox.checked)dirty.set(path,'');else dirty.delete(path);rowStatus.delete(path);reviewedChanges=null;renderEeprom();});
    if(changed){input=document.createElement('input');input.type='password';input.autocomplete='new-password';input.value=String(dirty.get(path));input.placeholder='New value';}
  }else{
    const label=document.createElement('label');label.className='esp-field';label.htmlFor=id;label.textContent=setting.label || path;
    const source=document.createElement('span');source.className='esp-field-path';source.textContent=path;label.appendChild(source);wrapper.appendChild(label);
    const options=optionPairs(setting);
    input=document.createElement(options.length?'select':'input');
    if(options.length){
      if(!options.some(option=>option.value===String(value)))options.unshift({label:`Firmware value ${value}`,value:String(value)});
      options.forEach(option=>{const el=document.createElement('option');el.value=option.value;el.textContent=`${option.label} (${option.value})`;input.appendChild(el);});
    }else{input.type='text';input.autocomplete='off';input.spellcheck=false;if(setting.type==='I')input.inputMode='decimal';}
    input.value=String(value);
  }
  if(input){
    input.id=id;input.className='esp-value';input.setAttribute('aria-label',`New value for ${path}`);
    if(['Sta/IP','Sta/Gateway','Sta/Netmask'].includes(path)){
      const mode=eepromSettings.find(row=>row.path==='Sta/IPMode');
      input.dataset.staticDisabled=String(!!mode && String(dirty.get(mode.path)??currentValue(mode))==='0');
    }
    wrapper.appendChild(input);
    input.addEventListener(input.tagName==='SELECT'?'change':'input',()=>{
      if(!secret&&input.value===currentValue(setting))dirty.delete(path);else dirty.set(path,input.value);
      rowStatus.delete(path);reviewedChanges=null;updateField(setting,wrapper);
      if(path==='Sta/IPMode')renderEeprom();else updateControls();
    });
  }
  const current=document.createElement('p');current.className='esp-field-current';current.textContent=secret?'Current value: hidden':`On device: ${displayValue(setting,currentValue(setting))}`;wrapper.appendChild(current);
  const range=document.createElement('p');range.className='esp-field-help';
  const bounds=[setting.min,setting.size_or_max].map(value=>value===undefined||value===null?'':String(value));
  range.textContent=setting.type==='S'&&bounds.some(Boolean)?`Length reported by firmware: ${bounds[0]||'0'}–${bounds[1]||'unlimited'} characters.`:bounds.some(Boolean)?`Firmware range: ${bounds[0]||'unspecified'}–${bounds[1]||'unspecified'}.`:'';
  wrapper.appendChild(range);
  const undo=document.createElement('button');undo.type='button';undo.className='esp-undo';undo.textContent='Undo this change';undo.addEventListener('click',()=>{dirty.delete(path);rowStatus.delete(path);reviewedChanges=null;renderEeprom();});
  const error=document.createElement('p');error.className='esp-field-error';const status=document.createElement('p');status.className='esp-row-status';
  wrapper.append(undo,error,status);updateField(setting,wrapper);return wrapper;
}
function renderEeprom() {
  // Only mount the active editor; drafts live in the Map, not hidden duplicate inputs.
  const targets={network:'espNetworkFields',services:'espServiceFields',hardware:'espHardwareFields',advanced:'eepromBody'};
  Object.entries(targets).forEach(([section,id])=>{if(section!==activeSection)ep(id).replaceChildren();});
  if(['network','services','hardware'].includes(activeSection))addPanelFields(activeSection,ep({network:'espNetworkFields',services:'espServiceFields',hardware:'espHardwareFields'}[activeSection]));
  if(activeSection==='advanced'){
    const body=ep('eepromBody'),query=ep('eepromFilter').value.trim().toLowerCase();body.replaceChildren();
    const settings=eepromSettings.filter(setting=>`${setting.path} ${setting.label} ${isSensitive(setting)?'':currentValue(setting)}`.toLowerCase().includes(query));
    settings.forEach(setting=>{const row=document.createElement('div');row.className='esp-eeprom-row';row.appendChild(renderField(setting));body.appendChild(row);});
    if(!settings.length)body.textContent=eepromReady?'No returned settings match this search.':'EEPROM settings unavailable. Read from the device to begin.';
  }
  updateControls();
}
async function readDevice(eeprom=true) {
  if(espBusy)return;
  if(eeprom&&dirty.size&&!confirm('Read from device and replace unsaved edits?'))return;
  await withBusy(async()=>{
    if(eeprom){await loadEeprom();dirty.clear();rowStatus.clear();reviewing=false;reviewedChanges=null;showSection(activeSection);}
    await loadInfo();await loadWsStatus();await loadBackups();
    setMsg('Device read complete. See Overview for connection health.');
  });
}
async function withBusy(action) {
  if(espBusy)return;
  espBusy=true;updateControls();
  try{await action();}catch(err){setMsg(err.message||String(err));}
  finally{espBusy=false;renderEeprom();updateControls();}
}
async function loadBackups() {
  const data=await api('/api/esp32/eeprom/backups');
  if(!data.ok){backupList=[];ep('backupSelect').replaceChildren();ep('backupStatus').textContent=maskSensitiveText(data.error||'Backup list unavailable.');updateControls();return;}
  const previous=ep('backupSelect').value;backupList=Array.isArray(data.backups)?data.backups:[];ep('backupSelect').replaceChildren();
  backupList.forEach(backup=>{const option=document.createElement('option');option.value=backup.name;option.textContent=`${backup.name} (${backup.setting_count ?? '?'} settings)`;ep('backupSelect').appendChild(option);});
  if(backupList.some(backup=>backup.name===previous))ep('backupSelect').value=previous;
  ep('backupStatus').textContent=backupList.length?`Latest backup: ${backupList[0].name}`:'No backups available.';updateControls();
}
async function createBackup() {
  await withBusy(async()=>{
    const data=await api('/api/esp32/eeprom/backup','POST',{});
    if(!data.ok||!data.backup_file)throw new Error(data.error||'Backup creation failed.');
    await loadBackups();
    const a=document.createElement('a');a.href=`/api/esp32/eeprom/backups/${encodeURIComponent(data.backup_file)}/download`;
    document.body.appendChild(a);a.click();a.remove();sessionBackupDownloaded=true;
    logRaw('Backup created',data);setMsg('Backup created; download requested. Confirm it is saved on your computer.');
  });
}
async function viewBackup() {
  await withBusy(async()=>{
    const name=ep('backupSelect').value;if(!name)throw new Error('Select a backup first.');
    const data=await api('/api/esp32/eeprom/backups/'+encodeURIComponent(name));if(!data.ok)throw new Error(data.error||'Backup unavailable.');
    ep('backupView').textContent=safeJson(data.data||data);ep('espBackupDetails').hidden=false;ep('espBackupDetails').open=true;
  });
}
async function compareBackup() {
  await withBusy(async()=>{
    const name=ep('backupSelect').value;if(!name)throw new Error('Select a backup first.');
    const data=await api('/api/esp32/eeprom/compare?backup='+encodeURIComponent(name));if(!data.ok)throw new Error(data.error||'Comparison failed.');
    const target=ep('backupDiff');target.replaceChildren();
    const differences=(Array.isArray(data.differences)?data.differences:[]).filter(row=>!isSensitive(row));
    const head=document.createElement('div');head.className='esp-comparison-head';['Setting','In backup','On device'].forEach(text=>{const span=document.createElement('span');span.textContent=text;head.appendChild(span);});target.appendChild(head);
    differences.forEach(row=>{const el=document.createElement('div');el.className='esp-comparison-row';[row.path,`Backup: ${row.backup ?? '(not present)'}`,`Device: ${row.current ?? '(not present)'}`].forEach(text=>{const span=document.createElement('span');span.textContent=maskSensitiveText(text);el.appendChild(span);});target.appendChild(el);});
    const note=document.createElement('p');note.className='esp-muted';note.textContent=differences.length?`${differences.length} non-secret differences. Passwords are not compared.`:'No differences in non-secret settings. Passwords are not compared.';target.appendChild(note);
    ep('espComparison').hidden=false;setMsg('Read-only comparison complete. No settings changed.');
  });
}
function reviewChanges() {
  if(espBusy||!eepromReady||!dirty.size||hasErrors())return;
  reviewedChanges=changesList().map(change=>({...change}));
  eepromSettings.filter(setting=>isSensitive(setting)&&dirty.has(setting.path)).forEach(setting=>{if(dirty.get(setting.path))secretValues.add(String(dirty.get(setting.path)));});
  const list=ep('espReviewList');list.replaceChildren();
  reviewedChanges.forEach(change=>{
    const setting=eepromSettings.find(row=>row.path===change.path),item=document.createElement('div');item.className='esp-review-item';
    const name=document.createElement('strong');name.textContent=setting.label||change.path;
    const path=document.createElement('p');path.className='esp-field-path';path.textContent=change.path;
    const value=document.createElement('p');value.textContent=isSensitive(setting)?'Secret value will be replaced (hidden).':`${displayValue(setting,currentValue(setting))} → ${displayValue(setting,change.value)}`;
    item.append(name,path,value);list.appendChild(item);
  });
  reviewing=true;document.querySelectorAll('[data-panel]').forEach(panel=>panel.hidden=true);ep('espReview').hidden=false;
  const network=reviewedChanges.some(change=>NETWORK_SENSITIVE_PATHS.has(change.path));
  ep('espNetworkWarning').hidden=!network;ep('espNetworkAckWrap').hidden=!network;ep('espNetworkAck').checked=false;
  ep('espReviewBackup').textContent=sessionBackupDownloaded?'A backup download was requested this session. An automatic backup is also attempted before writing.':'No backup download requested this session. You can go back to Backups & Compare before applying.';
  ep('espBackupAckWrap').hidden=sessionBackupDownloaded;ep('espBackupAck').checked=false;
  updateControls();ep('espReviewTitle').scrollIntoView({block:'nearest'});
}
async function saveChanges() {
  if(espBusy||!reviewing||!reviewedChanges?.length||ep('espApply').disabled)return;
  if(JSON.stringify(changesList())!==JSON.stringify(reviewedChanges)){reviewChanges();return;}
  const changes=reviewedChanges.map(change=>({...change}));
  await withBusy(async()=>{
    const data=await api('/api/esp32/eeprom/save','POST',{changes,backup_required:!sessionBackupDownloaded,allow_network_changes:changes.some(change=>NETWORK_SENSITIVE_PATHS.has(change.path))&&ep('espNetworkAck').checked});
    logRaw('EEPROM write results',data);
    if(!Array.isArray(data.results)||!data.results.length)throw new Error([data.error||'No write results received. Edits remain pending.',data.backup?.error].filter(Boolean).join(' '));
    const results=new Map([...data.results,...(Array.isArray(data.failed)?data.failed:[])].map(result=>[result.path,result]));
    const attempts=new Map(changes.map(change=>{
      const result=results.get(change.path);
      return [change.path,{...change,ok:!!result?.ok,message:maskSensitiveText(result?.response||result?.message||'No write result received.')}];
    }));
    attempts.forEach((attempt,path)=>{
      const setting=eepromSettings.find(row=>row.path===path);
      rowStatus.set(path,attempt.ok?'Accepted; awaiting read-back.':`Failed: ${attempt.message}`);
      if(attempt.ok&&isSensitive(setting)){dirty.delete(path);rowStatus.set(path,'Accepted; secret hidden (not read-back verified).');}
    });
    reviewing=false;reviewedChanges=null;showSection(activeSection);setMsg('Writes returned. Reading device to verify non-secret values...');
    try{await loadEeprom(attempts);}catch(err){setMsg(`Read-back unavailable. Network changes may have disconnected Pilot. Reconnect and read again. ${err.message}`);return;}
    const verified=changes.filter(change=>rowStatus.get(change.path)==='Verified on device.').length;
    const acceptedSecrets=changes.filter(change=>rowStatus.get(change.path)?.startsWith('Accepted; secret')).length;
    const failed=changes.length-verified-acceptedSecrets;
    ep('saveSummary').textContent=`${verified} verified, ${acceptedSecrets} secret changes accepted, ${failed} failed or unverified.`;
    setMsg(failed?'Failed or unverified changes remain pending.':'Changes processed. Secret values remain hidden.');
  });
}
function openNative() {
  const target=deviceInfo?.native_url||pageConfig.native_url||(deviceInfo?.http_host?`http://${deviceInfo.http_host}:${deviceInfo.http_port||8848}`:'');
  try {const parsed=new URL(target);if(!['http:','https:'].includes(parsed.protocol))throw new Error();window.open(parsed.href,'_blank','noopener,noreferrer');}
  catch(_){setMsg('No valid HTTP native page URL is available. Read device info or check configuration.');}
}
async function sendManual(kind) {
  if(espBusy||!ep('espCommandsEnabled').checked)return;
  const command=ep(kind==='grbl'?'gcodeCmd':'espCmd').value.trim();if(!command)return;
  if(command!=='?'&&!confirm('Send this manual command to the device? It may move, unlock, reset, or run the laser.'))return;
  await withBusy(async()=>{
    const data=await api(kind==='grbl'?'/api/esp32/command':'/api/esp32/esp-command','POST',kind==='grbl'?{command}:{cmd:command});
    const secretCommand=sensitive(command);
    const message=secretCommand?(data.ok?'Command accepted (secret response hidden).':'Command failed (secret response hidden).'):safeJson(data);
    ep(kind==='grbl'?'gcodeLast':'espLast').textContent=message;
    logRaw(kind==='grbl'?'GRBL manual result':'ESP3D manual result',secretCommand?{ok:!!data.ok,details:'Secret command and response hidden.'}:data);
    setMsg(data.ok?'Command accepted.':secretCommand?'Command failed; secret details hidden.':data.error||data.message||'Command failed.');
    if(secretCommand)ep(kind==='grbl'?'gcodeCmd':'espCmd').value='';
  });
}
function init() {
  ESP_SECTIONS.forEach(([id,title])=>{
    const button=document.createElement('button');button.type='button';button.dataset.section=id;
    const name=document.createElement('span'),state=document.createElement('span');name.textContent=title;state.className='esp-category-edited';button.append(name,state);
    button.addEventListener('click',()=>{if(!espBusy)showSection(id);});ep('espCategories').appendChild(button);
  });
  ep('refreshAll').onclick=()=>readDevice(true);ep('refreshInfo').onclick=()=>withBusy(loadInfo);ep('refreshEeprom').onclick=()=>readDevice(true);ep('refreshWs').onclick=()=>withBusy(loadWsStatus);
  ep('openNative').onclick=openNative;ep('backupEeprom').onclick=createBackup;ep('loadBackup').onclick=viewBackup;ep('compareBackup').onclick=compareBackup;
  ep('eepromFilter').oninput=renderEeprom;ep('espCommandsEnabled').onchange=updateControls;
  ep('sendGcode').onclick=()=>sendManual('grbl');ep('sendEsp').onclick=()=>sendManual('esp');
  ep('saveChanges').onclick=reviewChanges;ep('espApply').onclick=saveChanges;ep('espBack').onclick=()=>showSection(activeSection);
  ['espNetworkAck','espBackupAck'].forEach(id=>ep(id).onchange=updateControls);
  ep('discardChanges').onclick=()=>{dirty.clear();rowStatus.clear();ep('saveSummary').textContent='';showSection(activeSection);setMsg('Unsaved changes discarded.');};
  ep('clearRawLog').onclick=()=>ep('rawLog').textContent='';
  window.addEventListener('beforeunload',event=>{if(dirty.size||espBusy){event.preventDefault();event.returnValue='';}});
  showSection('overview');renderHealth();
  withBusy(async()=>{
    await loadInfo();
    try{await loadEeprom();}catch(err){setMsg(err.message);}
    await loadWsStatus();await loadBackups();
  });
  setInterval(()=>{if(activeSection==='overview'&&!reviewing){renderHealth();}},1000);
}
init();
