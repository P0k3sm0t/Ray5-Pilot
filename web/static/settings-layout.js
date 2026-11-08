/* Reorganize existing controls without changing their IDs or configuration mapping. */
(() => {
  const root = document.querySelector('.settings-page');
  const sections = document.getElementById('settingsSections');
  const nav = document.getElementById('settingsNav');
  if (!root || !sections || !nav) return;

  const categories = [
    {id:'connection', title:'Connection', description:'Connect to the Ray5 and choose how Pilot receives live status.', cards:['Ray5 Network', 'Status / Live Status']},
    {id:'camera', title:'Camera & Alignment', description:'Connect the camera, calibrate the bed, then fine-tune your overlay.', cards:['Camera', 'Camera Processing / Deskew', 'Camera Overlay Alignment']},
    {id:'jobs', title:'Jobs & Files', description:'Manage watched-folder imports, upload preferences, and Ray5 SD files.', cards:['Imported Jobs', 'Upload', 'SD Files']},
    {id:'motion', title:'Motion & Framing', description:'Set usable bed limits, frame defaults, and manual movement preferences.', cards:['Framing', 'Manual Controls']},
    {id:'safety', title:'Safety & Job Control', description:'Review laser test limits, file validation, and Stop behavior.', cards:['Safety', 'Job Control', 'G-code Safety Scanner', 'Live Console']},
    {id:'app', title:'App & Updates', description:'Configure Pilot hosting, timelapse recording, updates, and support.', cards:['Web UI', 'Timelapse', 'Support']},
    {id:'advanced', title:'Advanced', description:'Less common options and diagnostics for troubleshooting.', cards:['Diagnostics']},
  ];
  const cards = new Map(Array.from(sections.children).map(card => [card.querySelector('h3')?.textContent.trim(), card]));

  // Keep each existing label and its help together when moving or collapsing fields.
  cards.forEach(card => {
    Array.from(card.children).filter(el => el.tagName === 'LABEL').forEach(label => {
      const row = document.createElement('div');
      row.className = 'settings-field';
      if (label.querySelector('input[type="checkbox"]')) row.classList.add('settings-toggle');
      label.before(row);
      row.appendChild(label);
      let next = row.nextElementSibling;
      while (next?.matches('p.field-help')) {
        const help = next;
        next = next.nextElementSibling;
        row.appendChild(help);
      }
      const input = label.querySelector('input,select,textarea');
      if (input) {
        label.htmlFor = input.id;
        if (/url|folder|directory|points|prefix|label/i.test(label.textContent)) row.classList.add('settings-field-wide');
      }
    });
  });

  function newCard(title) {
    const card = document.createElement('section');
    card.className = 'card';
    const heading = document.createElement('h3');
    heading.textContent = title;
    card.appendChild(heading);
    cards.set(title, card);
    return card;
  }
  function moveFields(destination, ids) {
    ids.forEach(id => {
      const row = document.getElementById(id)?.closest('.settings-field');
      if (row) destination.appendChild(row);
    });
  }
  function detail(card, title, ids) {
    if (!card) return;
    const details = document.createElement('details');
    details.className = 'settings-details';
    const summary = document.createElement('summary');
    summary.textContent = title;
    details.appendChild(summary);
    moveFields(details, ids);
    card.appendChild(details);
  }

  const network = cards.get('Ray5 Network');
  const liveStatus = cards.get('Status / Live Status');
  moveFields(liveStatus, ['status_active_poll_seconds', 'status_ws_ping_interval', 'status_ws_ping_timeout']);
  const diagnostics = newCard('Diagnostics');
  moveFields(diagnostics, ['status_debug_logging', 'status_show_source', 'status_show_pos_source']);
  detail(liveStatus, 'Advanced connection tuning', ['status_ws_path', 'status_ws_subprotocol', 'status_active_poll_seconds', 'status_reconnect_seconds', 'status_stale_after', 'status_ws_ping_interval', 'status_ws_ping_timeout', 'status_prefer_live']);
  detail(cards.get('Camera'), 'Advanced camera connection', ['cam_proxy_enabled', 'cam_proxy_path', 'cam_reconnect', 'cam_rtsp_transport', 'cam_capture_method', 'cam_timeout']);
  const snapshotCard = newCard('Snapshots & History');
  moveFields(snapshotCard, ['cam_output_dir', 'cam_save_history']);
  detail(snapshotCard, 'History & cleanup options', ['cam_filename_prefix', 'cam_keep_last', 'cam_auto_cleanup', 'cam_cleanup_capture']);
  categories[1].cards.push('Snapshots & History');
  detail(cards.get('Camera Processing / Deskew'), 'Image processing & guides', ['cam_deskew_points', 'cam_deskew_out_w', 'cam_deskew_out_h', 'cam_post_enabled', 'cam_scale', 'cam_crop_margin', 'cam_final_w', 'cam_final_h', 'cam_dpi', 'cam_guides_enabled', 'cam_guides_cross', 'cam_guides_border', 'cam_guides_corners']);
  const alignment = cards.get('Camera Overlay Alignment');
  detail(alignment, 'Fine alignment correction', ['cam_align_offset_x', 'cam_align_offset_y', 'cam_align_scale_x', 'cam_align_scale_y', 'cam_align_rotation']);
  const calibrationActions = document.createElement('div');
  calibrationActions.className = 'settings-inline-actions';
  const calibration = document.createElement('a');
  calibration.className = 'camera-link-btn';
  calibration.href = '/camera/calibration';
  calibration.target = '_blank';
  calibration.rel = 'noopener';
  calibration.textContent = 'Open camera calibration';
  calibrationActions.appendChild(calibration);
  const preview = document.createElement('a');
  preview.className = 'camera-link-btn';
  preview.href = '/api/camera/snapshot';
  preview.target = '_blank';
  preview.rel = 'noopener';
  preview.textContent = 'View latest overlay';
  calibrationActions.appendChild(preview);
  cards.get('Camera Processing / Deskew').appendChild(calibrationActions);
  detail(cards.get('Imported Jobs'), 'Watch timing', ['jobs_watch_poll']);
  detail(cards.get('Upload'), 'Advanced upload compatibility', ['upload_sanitize_filename', 'upload_rewrite', 'upload_convert_m4', 'upload_force_ext', 'upload_normalize_eol']);
  const scanner = newCard('G-code Safety Scanner');
  const scannerTitle = cards.get('Upload')?.querySelector('h4');
  if (scannerTitle) {
    const help = scannerTitle.nextElementSibling;
    if (help?.matches('p.field-help')) scanner.appendChild(help);
    scannerTitle.remove();
  }
  moveFields(scanner, ['safe_reject_3d', 'safe_scan_lines', 'safe_allow_unknown']);
  detail(cards.get('Manual Controls'), 'Preset position button', ['preset_enabled', 'preset_label', 'preset_x', 'preset_y', 'preset_feedrate']);
  detail(cards.get('Job Control'), 'Advanced recovery', ['job_stop_unlock_after']);
  if (network) network.querySelector('h3').textContent = 'Ray5 connection';
  if (liveStatus) liveStatus.querySelector('h3').textContent = 'Live machine status';

  const assigned = new Set();
  categories.forEach(category => {
    const panel = document.createElement('section');
    panel.id = `settings-${category.id}`;
    panel.className = 'settings-category';
    panel.setAttribute('aria-labelledby', `settings-nav-${category.id}`);
    category.cards.forEach(title => {
      const card = cards.get(title);
      if (card) { panel.appendChild(card); assigned.add(card); }
    });
    sections.appendChild(panel);
    const button = document.createElement('button');
    button.id = `settings-nav-${category.id}`;
    button.type = 'button';
    button.textContent = category.title;
    button.setAttribute('aria-controls', panel.id);
    button.addEventListener('click', () => selectCategory(category.id));
    nav.appendChild(button);
  });
  // Any future card remains accessible even if it has not been assigned a category.
  cards.forEach(card => {
    if (!assigned.has(card)) document.getElementById('settings-advanced').appendChild(card);
  });

  function selectCategory(id) {
    const selected = categories.find(category => category.id === id) || categories[0];
    categories.forEach(category => {
      document.getElementById(`settings-${category.id}`).hidden = category !== selected;
      document.getElementById(`settings-nav-${category.id}`).setAttribute('aria-pressed', String(category === selected));
    });
    document.getElementById('settingsCategoryTitle').textContent = selected.title;
    document.getElementById('settingsCategoryDescription').textContent = selected.description;
  }
  selectCategory('connection');
  root.querySelector('.settings-sidebar').hidden = false;
  document.getElementById('settingsCategoryHeading').hidden = false;
  root.classList.add('settings-organized');

  const dirtyLabel = document.getElementById('settingsDirtyState');
  const discard = document.getElementById('discardCfg');
  let baseline = [];
  let pendingSave = null;
  let dirty = false;
  function snapshot() {
    return Array.from(sections.querySelectorAll('input,select,textarea')).map(el => ({el, value:el.value, checked:el.checked}));
  }
  function updateDirty() {
    if (!baseline.length) return;
    dirty = baseline.some(({el, value, checked}) => el.type === 'checkbox' ? el.checked !== checked : el.value !== value);
    dirtyLabel.textContent = dirty ? 'Unsaved changes' : 'All changes saved';
    discard.disabled = !dirty;
  }
  document.addEventListener('settings:loaded', () => {
    baseline = snapshot();
    updateDirty();
  });
  document.addEventListener('settings:saved', () => {
    baseline = pendingSave || snapshot();
    pendingSave = null;
    updateDirty();
  });
  document.addEventListener('settings:saving', () => { pendingSave = snapshot(); });
  document.addEventListener('settings:save-error', () => { pendingSave = null; updateDirty(); });
  document.addEventListener('settings:load-error', () => {
    dirtyLabel.textContent = 'Settings unavailable';
    discard.disabled = true;
  });
  sections.addEventListener('input', updateDirty);
  sections.addEventListener('change', updateDirty);
  discard.addEventListener('click', () => {
    baseline.forEach(({el, value, checked}) => { el.value = value; if (el.type === 'checkbox') el.checked = checked; });
    document.getElementById('saveOut').textContent = 'Unsaved changes discarded.';
    updateDirty();
  });
  window.addEventListener('beforeunload', event => {
    if (dirty) { event.preventDefault(); event.returnValue = ''; }
  });
})();
