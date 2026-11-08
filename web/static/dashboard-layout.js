/* Presentation only: move the original card nodes without replacing their controls. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const required = ['dashboardShell','dashboardOriginalCards','dashboardNav','dashboardTopActions',
    'dashboardCameraSlot','dashboardJobsSlot','dashboardManualSlot','dashboardStatusSlot','dashboardConsoleSlot',
    'dashboardLibrarySlot','dashboardTimelapseSlot','dashboardConsoleFullSlot','dashboardStatusFullSlot',
    'machineStateBadge','dashboardUnlock','dashboardMachineAlert','dashboardMachineAlertText','dashboardClearLockout','dashboardMessage',
    'dashboardWorkspaceView','dashboardFilesView','dashboardTimelapseView','dashboardDiagnosticsView',
    'cameraCard','manualControlsCard','statusCard','importedJobsCard','sdFilesCard','timelapseCard','consoleCard','stop'];
  const missing = required.filter(id => !el(id));
  if (missing.length) {
    console.warn('Dashboard layout unavailable; keeping the original controls:', missing.join(', '));
    return;
  }
  const cards = {
    camera:el('cameraCard'), manual:el('manualControlsCard'), status:el('statusCard'),
    imported:el('importedJobsCard'), sd:el('sdFilesCard'), timelapse:el('timelapseCard'), console:el('consoleCard'),
  };
  const pages = ['workspace','files','camera','timelapse','console'];
  let page = 'workspace';
  let fileTab = 'imported';
  const fileGroup = document.createElement('div');
  fileGroup.id = 'dashboardFileGroup';
  const tabs = document.createElement('div');
  tabs.className = 'dashboard-file-tabs';
  tabs.setAttribute('role','tablist');
  tabs.setAttribute('aria-label','File source');
  for (const [id,label,card] of [['imported','Imported Jobs',cards.imported],['sd','Ray5 SD Files',cards.sd]]) {
    const button = document.createElement('button');
    button.id = 'dashboardFileTab_' + id;
    button.type = 'button';
    button.textContent = label;
    button.dataset.fileTab = id;
    button.setAttribute('role','tab');
    button.setAttribute('aria-controls',card.id);
    card.setAttribute('role','tabpanel');
    card.setAttribute('aria-labelledby',button.id);
    button.addEventListener('click',() => selectFileTab(id));
    tabs.appendChild(button);
  }
  fileGroup.append(tabs,cards.imported,cards.sd);
  el('dashboardTopActions').appendChild(el('stop'));
  el('dashboardCameraSlot').appendChild(cards.camera);
  el('dashboardManualSlot').appendChild(cards.manual);
  el('dashboardTimelapseSlot').appendChild(cards.timelapse);

  function selectFileTab(id) {
    fileTab = id;
    for (const button of tabs.children) button.setAttribute('aria-selected',String(button.dataset.fileTab === id));
    cards.imported.hidden = id !== 'imported';
    cards.sd.hidden = id !== 'sd';
  }
  function mount(slot,node) {
    // Do not reinsert a card when it is already in its destination.
    if (node.parentElement !== el(slot)) el(slot).appendChild(node);
  }
  function showPage(next,updateHash=true) {
    if (!pages.includes(next)) next = 'workspace';
    page = next;
    mount(next === 'files' ? 'dashboardLibrarySlot' : 'dashboardJobsSlot',fileGroup);
    mount(next === 'console' ? 'dashboardConsoleFullSlot' : 'dashboardConsoleSlot',cards.console);
    mount(next === 'console' ? 'dashboardStatusFullSlot' : 'dashboardStatusSlot',cards.status);
    document.querySelectorAll('[data-dashboard-view]').forEach(view => view.hidden = view.dataset.dashboardView !== next);
    // Keep the media node connected; resize its existing workspace for the Camera view.
    el('dashboardWorkspaceView').hidden = next !== 'workspace' && next !== 'camera';
    el('dashboardWorkspaceView').classList.toggle('dashboard-camera-mode',next === 'camera');
    document.querySelectorAll('#dashboardNav button').forEach(button => button.setAttribute('aria-pressed',String(button.dataset.dashboardPage === next)));
    if (updateHash) history.replaceState(null,'','#'+next);
  }
  el('dashboardNav').querySelectorAll('button').forEach(button => {
    button.addEventListener('click',() => showPage(button.dataset.dashboardPage));
  });
  window.addEventListener('hashchange',() => showPage(location.hash.slice(1),false));
  document.addEventListener('ray5:playback',() => showPage('workspace'));

  function relayClick(from,to) {
    const source = el(from),target = el(to);
    if (!source || !target) return;
    source.addEventListener('click',() => {if (!target.disabled) target.click();});
    const sync = () => source.disabled = target.disabled;
    new MutationObserver(sync).observe(target,{attributes:true,attributeFilter:['disabled']});
    sync();
  }
  relayClick('dashboardUnlock','unlock');
  el('dashboardClearLockout').addEventListener('click',() => el('clearCommLossLockoutBtn')?.click());
  document.addEventListener('ray5:status',event => {
    const data = event.detail || {};
    const state = String(data.state || 'Unknown');
    const alarm = /^alarm|locked/i.test(state);
    const offline = !!data.offline;
    const badge = el('machineStateBadge');
    badge.textContent = offline ? 'Disconnected' : state;
    badge.dataset.kind = offline || alarm || data.lockout ? 'danger' : /^idle$/i.test(state) ? 'idle' : /run|jog|home|upload|hold/i.test(state) ? 'busy' : 'unknown';
    el('dashboardUnlock').hidden = !alarm;
    const alert = el('dashboardMachineAlert');
    alert.hidden = !offline && !alarm && !data.lockout;
    el('dashboardMachineAlertText').textContent = data.lockout
      ? data.message || 'Communication was lost during a job. Verify the Ray5 screen and machine state before clearing the safety lockout.'
      : alarm ? 'Machine is alarmed or locked. Verify that the head can move safely before using Home or Unlock.'
      : offline ? 'Machine status is unavailable. Check the Ray5 connection before sending motion or job commands.' : '';
    el('dashboardClearLockout').hidden = !data.lockout;
  });

  // A Stop response remains visible even when Manual Controls are on another section.
  const messages = ['manualMsg','jobsMsg','sdMsg','timelapseMsg','consoleCommandStatus'];
  for (const id of messages) {
    const target = el(id);
    if (!target) continue;
    let last = target.textContent;
    new MutationObserver(() => {
      const text = target.textContent.trim();
      if (text && text !== last) el('dashboardMessage').textContent = text;
      last = text;
    }).observe(target,{childList:true,subtree:true,characterData:true});
  }
  selectFileTab(fileTab);
  showPage(location.hash.slice(1) || page,false);
  el('dashboardOriginalCards').hidden = true;
  el('dashboardShell').hidden = false;
  document.body.classList.add('dashboard-ready');
  console.info('Dashboard layout loaded; existing controls preserved');
})();
