async function api(url, method = "GET", body = null) {
  const opt = {method, headers:{"X-Ray5-Pilot-Request":"1"}};
  if (body) {opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body);}
  const response = await fetch(url, opt);
  return response.json();
}
function esc(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}
const ms = id => document.getElementById(id);
let settingsRows = [];
let rawBackupText = "";
let grblVersionInfo = {};
let collectPollTimer = null;
let collectPollStartedAt = 0;
let settingsReady = false;
let saving = false;
let activeCategory = "motion";
let reviewing = false;
let reviewedChanges = null;
let lastReadAt = null;
const COLLECT_POLL_MS = 800;
const COLLECT_POLL_TIMEOUT_MS = 90000;
// Safety check compatibility marker: "Reading firmware settings..."
const CATEGORIES = [
  ["motion", "Motion & Travel", "Steps, speeds, acceleration, and available travel."],
  ["homing", "Homing & Limits", "Limit detection, homing speeds, and pull-off distance."],
  ["laser", "Laser", "Laser mode and the S-value range."],
  ["controller", "Controller", "Signals, reporting, and firmware-specific settings."],
  ["all", "All settings", "All returned settings remain accessible by their GRBL code."],
  ["diagnostics", "Diagnostics", "Technical replies from the most recent controller read."],
];
const AXIS_MASKS = new Set(["2", "3", "23"]);
const BOOLS = new Set(["4", "5", "6", "13", "20", "21", "22", "32"]);
const Z_SETTINGS = new Set(["102", "112", "122", "132"]);
const SETTING_HELP = {
  0:"Duration of each step pulse.", 1:"Delay before idle stepper drivers are disabled.",
  2:"Select axes whose step pulse signal is inverted.", 3:"Select axes whose direction signal is inverted.",
  4:"Invert the stepper enable signal.", 5:"Invert limit input signals.", 6:"Invert the probe input signal.",
  10:"Firmware status-report selection. This mask is not an axis selector.",
  11:"Controller parameter for cornering behavior.", 12:"Tolerance used when approximating arcs.",
  13:"Use inches in controller reports.", 20:"Check motion against configured travel limits.",
  21:"React to physical limit inputs.", 22:"Enable the controller homing cycle.",
  23:"Select axes whose homing direction is inverted. X=1, Y=2, Z=4.",
  24:"Speed used for the homing locate pass.", 25:"Speed used for the initial homing seek.",
  26:"Debounce delay for homing switches.", 27:"Pull-away distance after a homing switch triggers.",
  30:"Full-scale spindle or laser S command value.", 31:"Minimum configured spindle or laser S command value.",
  32:"Enable GRBL laser mode.",
  100:"Steps used for one millimeter of X travel.", 101:"Steps used for one millimeter of Y travel.",
  102:"Firmware-reported Z calibration; not normally used on a two-axis Ray5.",
  110:"Maximum feedrate along X.", 111:"Maximum feedrate along Y.", 112:"Firmware-reported maximum Z feedrate.",
  120:"How quickly X motion changes speed.", 121:"How quickly Y motion changes speed.", 122:"Firmware-reported Z acceleration.",
  130:"Configured travel range along X.", 131:"Configured travel range along Y.", 132:"Firmware-reported Z travel range.",
};

function categoryFor(row) {
  const key = Number(row.key);
  if ([100,101,102,110,111,112,120,121,122,130,131,132].includes(key)) return "motion";
  if (key >= 20 && key <= 27) return "homing";
  if (key >= 30 && key <= 32) return "laser";
  return "controller";
}
function editorType(row) {
  if (BOOLS.has(row.key) && ["0", "1"].includes(String(Number(row.value)))) return "boolean";
  const number = Number(row.new_value);
  if (AXIS_MASKS.has(row.key) && Number.isInteger(number) && number >= 0 && number <= 7) return "mask";
  return "numeric";
}
function isChanged(row) {return String(row.new_value).trim() !== String(row.value).trim();}
function displayValue(row, value) {
  return BOOLS.has(row.key) && [0,1].includes(Number(value)) ? `${Number(value) === 1 ? "On" : "Off"} (${value})` : String(value);
}
function changedRows() {return settingsRows.filter(isChanged);}
function validationError(row) {
  const value = String(row.new_value).trim();
  if (!/^-?\d+(\.\d+)?$/.test(value) || !Number.isFinite(Number(value))) return "Enter a number, without units or command text.";
  if (BOOLS.has(row.key) && ![0, 1].includes(Number(value))) return "Choose On (1) or Off (0).";
  return "";
}
function busy() {return saving || !!window.__firmwareCollectRunning;}
function setMsg(text, cls = "muted") {
  ms("msMsg").className = `small ${cls}`;
  ms("msMsg").textContent = text;
}
function setRawOutput(text) {ms("msRaw").textContent = String(text || "").trim();}
function renderGrblVersion(info) {
  grblVersionInfo = info || {};
  const pairs = {
    gvFirmwareVersion:info.firmware_version, gvOptions:info.options, gvSoftware:info.software,
    gvWavelength:info.wavelength, gvWorkingSize:info.working_size?.label, gvBoard:info.board, gvMachine:info.machine,
    gvStaSsid:info.sta?.ssid, gvStaIp:info.sta?.ip, gvStaMac:info.sta?.mac,
    gvApSsid:info.ap?.ssid, gvApIp:info.ap?.ip, gvApMac:info.ap?.mac,
  };
  Object.entries(pairs).forEach(([id, value]) => {ms(id).textContent = String(value || "");});
  ms("msVersionRaw").textContent = String(info.raw || "").trim();
  ms("msVersionMsg").textContent = info.ok ? "" : (info.error || "No GRBL version information available.");
  ms("msDeviceSummary").textContent = [info.machine, info.firmware_version && `GRBL ${info.firmware_version}`, info.working_size?.label].filter(Boolean).join(" · ") || "Machine & firmware details";
}
function updateButtons() {
  const changes = changedRows();
  const invalid = changes.some(row => validationError(row));
  ms("msSave").disabled = busy() || !settingsReady || !changes.length || invalid;
  ms("msSave").textContent = changes.length ? `Review ${changes.length} change${changes.length === 1 ? "" : "s"}` : "Review changes";
  ms("msReset").disabled = busy() || !changes.length;
  ms("msRefresh").disabled = busy();
  ms("msDownload").disabled = !rawBackupText || busy();
  ms("msApply").disabled = busy() || !settingsReady || !reviewedChanges?.length || invalid;
  ms("msBack").disabled = busy();
  ms("msPending").textContent = changes.length ? `${changes.length} pending change${changes.length === 1 ? "" : "s"}` : "No pending changes";
  ms("msReadState").textContent = saving ? "Applying / verifying..." : window.__firmwareCollectRunning ? "Reading controller..." : settingsReady ? `Read at ${lastReadAt?.toLocaleTimeString() || "unknown time"}` : "Read required before applying";
  document.querySelectorAll(".machine-setting-input, .grbl-mask input, .grbl-undo").forEach(el => {el.disabled = busy() || !settingsReady;});
  document.querySelectorAll("#msCategories button").forEach(button => {
    const category = button.dataset.category;
    const rows = category === "all" ? settingsRows : settingsRows.filter(row => categoryFor(row) === category);
    button.querySelector(".grbl-category-count").textContent = category === "diagnostics" ? "" : `${rows.length}${rows.some(isChanged) ? " • edited" : ""}`;
    button.setAttribute("aria-pressed", String(category === activeCategory));
    button.disabled = busy();
  });
  ["msSearch", "msChangedOnly", "msShowZ"].forEach(id => {ms(id).disabled = busy();});
}
function setView() {
  const term = ms("msSearch").value.trim();
  ms("msReview").hidden = !reviewing;
  ms("msEditor").hidden = reviewing || (activeCategory === "diagnostics" && !term);
  ms("msDiagnostics").hidden = reviewing || activeCategory !== "diagnostics" || !!term;
}
function filteredRows() {
  const term = ms("msSearch").value.trim().toLowerCase();
  return settingsRows.filter(row => {
    const matches = term ? `${row.code} ${row.key} ${row.description} ${row.unit} ${row.notes} ${SETTING_HELP[row.key] || ""}`.toLowerCase().includes(term)
      : (activeCategory === "all" || categoryFor(row) === activeCategory) && (!Z_SETTINGS.has(row.key) || ms("msShowZ").checked);
    return matches && (!ms("msChangedOnly").checked || isChanged(row));
  });
}
function setRowChangedState(row, element) {
  const box = element.closest(".grbl-setting-row");
  if (!box) return;
  box.classList.toggle("machine-setting-changed", isChanged(row));
  box.querySelector(".grbl-undo").hidden = !isChanged(row);
  const error = validationError(row);
  box.querySelector(".grbl-row-error").textContent = error;
  box.querySelector(".grbl-row-error").hidden = !error;
  box.querySelector(".machine-setting-status").textContent = row.status || "";
  if (element.matches("input:not([type=checkbox]),select")) element.setAttribute("aria-invalid", String(!!error));
}
function editRow(row, input) {
  row.new_value = input.value;
  row.status = "";
  reviewedChanges = null;
  setRowChangedState(row, input);
  updateButtons();
}
function renderTable() {
  setView();
  const category = CATEGORIES.find(item => item[0] === activeCategory);
  const searching = !!ms("msSearch").value.trim();
  ms("msShowZ").closest("label").hidden = searching || !["motion", "all"].includes(activeCategory);
  ms("msCategoryTitle").textContent = searching ? "Search results" : category[1];
  ms("msCategoryDescription").textContent = searching ? "Searching all categories, including hidden Z-axis settings." : category[2];
  const body = ms("msBody");
  body.replaceChildren();
  const rows = filteredRows();
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "grbl-empty";
    empty.textContent = !settingsRows.length ? "No GRBL settings loaded. Read from Ray5 to begin." : "No settings match this view.";
    body.appendChild(empty);
  }
  rows.forEach(row => {
    const box = document.createElement("div");
    box.className = "grbl-setting-row" + (isChanged(row) ? " machine-setting-changed" : "");
    box.dataset.key = row.key;
    const name = document.createElement("div");
    const help = row.notes && row.notes !== "—" ? row.notes : SETTING_HELP[row.key];
    name.innerHTML = `<div class="grbl-setting-name"><code>${esc(row.code)}</code>${esc(row.description)}</div>${help ? `<p class="grbl-setting-help">${esc(help)}</p>` : ""}`;
    const current = document.createElement("div");
    current.className = "grbl-current";
    current.innerHTML = `<span class="grbl-current-caption">On controller</span><span>${esc(displayValue(row, row.value))}</span><div class="grbl-unit">${esc(row.unit || "")}</div>`;
    const editor = document.createElement("div");
    editor.className = "grbl-new-value";
    const type = editorType(row);
    if (type === "mask") {
      const fieldset = document.createElement("fieldset");
      fieldset.className = "grbl-mask";
      fieldset.innerHTML = '<legend>New axis mask</legend><div class="grbl-mask-options"></div>';
      const raw = document.createElement("span"); raw.className = "grbl-unit"; raw.textContent = `GRBL value: ${row.new_value}`;
      ["X", "Y", "Z"].forEach((axis, bit) => {
        const label = document.createElement("label");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox"; checkbox.checked = !!(Number(row.new_value) & (1 << bit));
        checkbox.dataset.bit = String(1 << bit);
        checkbox.setAttribute("aria-label", `${row.code} ${row.description}: ${axis}`);
        label.append(checkbox, document.createTextNode(axis)); fieldset.querySelector("div").appendChild(label);
        checkbox.addEventListener("change", () => {
          row.new_value = String(Array.from(fieldset.querySelectorAll("input:checked")).reduce((sum, input) => sum + Number(input.dataset.bit), 0));
          row.status = ""; reviewedChanges = null; raw.textContent = `GRBL value: ${row.new_value}`;
          setRowChangedState(row, checkbox); updateButtons();
        });
      });
      editor.append(fieldset, raw);
    } else {
      const input = document.createElement(type === "boolean" ? "select" : "input");
      if (type === "boolean") input.innerHTML = '<option value="1">On (1)</option><option value="0">Off (0)</option>';
      else {input.type = "text"; input.inputMode = "decimal"; input.autocomplete = "off"; input.spellcheck = false;}
      input.id = `msValue_${row.key}`; input.className = "machine-setting-input";
      input.value = type === "boolean" ? String(Number(row.new_value)) : String(row.new_value);
      input.setAttribute("aria-label", `New value for ${row.code} ${row.description}`);
      input.setAttribute("aria-invalid", String(!!validationError(row)));
      input.addEventListener(type === "boolean" ? "change" : "input", () => editRow(row, input));
      editor.appendChild(input);
    }
    const undo = document.createElement("button"); undo.type = "button"; undo.className = "grbl-undo";
    undo.textContent = "Undo this change"; undo.hidden = !isChanged(row);
    undo.addEventListener("click", () => {row.new_value = String(row.value); row.status = ""; reviewedChanges = null; renderTable();});
    const error = document.createElement("span"); error.className = "grbl-row-error"; error.textContent = validationError(row); error.hidden = !error.textContent;
    const status = document.createElement("span"); status.className = "machine-setting-status"; status.textContent = row.status || "";
    editor.append(undo, error, status); box.append(name, current, editor); body.appendChild(box);
  });
  updateButtons();
}

function renderLoadedSettings(response, verification = null) {
  const previous = new Map(settingsRows.map(row => [row.key, row]));
  rawBackupText = String(response.raw || "");
  setRawOutput(rawBackupText);
  renderGrblVersion(response.grbl_version || {});
  settingsRows = response.settings.map(item => {
    const row = {...item, key:String(item.key), code:item.code || `$${item.key}`, value:String(item.value ?? ""), new_value:String(item.value ?? ""), status:""};
    const attempted = verification?.get(row.key);
    if (attempted) {
      if (attempted.ok && Number(row.value) === Number(attempted.value)) row.status = "Verified on controller";
      else {row.new_value = attempted.value; row.status = attempted.ok ? `Not verified: controller reports ${row.value}` : `Failed: ${attempted.message}`;}
    }
    return row;
  });
  if (verification) {
    const returned = new Set(settingsRows.map(row => row.key));
    verification.forEach((attempted, key) => {
      if (!returned.has(key) && previous.has(key)) settingsRows.push({...previous.get(key), new_value:attempted.value, status:"Not verified: setting missing from controller read"});
    });
  }
  settingsRows.sort((a,b) => Number(a.key) - Number(b.key));
  settingsReady = true; lastReadAt = new Date();
  renderTable();
}
function stopCollectPolling() {
  if (collectPollTimer) {clearTimeout(collectPollTimer); collectPollTimer = null;}
  window.__firmwareCollectRunning = false;
  updateButtons();
}
async function pollCollectStatus(options = {}) {
  while (Date.now() - collectPollStartedAt <= COLLECT_POLL_TIMEOUT_MS) {
    const response = await api("/api/machine-settings/collect/status");
    if (response.running) {
      if (response.raw) setRawOutput(response.raw);
      await new Promise(resolve => {collectPollTimer = setTimeout(resolve, COLLECT_POLL_MS);});
      collectPollTimer = null;
      continue;
    }
    if (response.ok && Array.isArray(response.settings) && response.settings.length) {
      renderLoadedSettings(response, options.verification);
      if (!options.preserveMessage) setMsg(response.message || `Loaded ${settingsRows.length} settings from Ray5.`);
      return true;
    }
    throw new Error(response.error || response.message || "No GRBL settings returned. Please read again.");
  }
  throw new Error("GRBL settings read timed out. Please try again.");
}
async function startCollectAndPoll(options = {}) {
  if (window.__firmwareCollectRunning) return false;
  window.__firmwareCollectRunning = true; settingsReady = false; updateButtons();
  if (!options.preserveMessage) setMsg("Reading GRBL settings...");
  try {
    const response = await api("/api/machine-settings/collect", "POST");
    if (!response.ok) throw new Error(response.error || response.message || "Failed to start GRBL settings read.");
    collectPollStartedAt = Date.now();
    return await pollCollectStatus(options);
  } catch (err) {
    if (options.verification) settingsRows.forEach(row => {if (options.verification.has(row.key)) row.status = "Not verified: controller read failed";});
    setMsg(`${options.verification ? "Write results not verified. " : ""}${err.message || err}`, "error");
    renderTable();
    return false;
  } finally {stopCollectPolling();}
}
async function loadSettings(options = {}) {
  if (busy()) return;
  if (changedRows().length && !confirm("Read from Ray5 and replace your unsaved edits?")) return;
  reviewing = false; reviewedChanges = null; setView();
  await startCollectAndPoll(options);
}
function buildBackupContent() {
  return `Ray5 GRBL Settings Backup\nGenerated: ${new Date().toISOString()}\n\n${rawBackupText || ""}\n`;
}
function downloadBackup() {
  if (!rawBackupText || busy()) return;
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const blob = new Blob([buildBackupContent()], {type:"text/plain;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `ray5_grbl_settings_backup_${stamp}.txt`;
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function resetUnsaved() {
  if (busy()) return;
  settingsRows.forEach(row => {row.new_value = String(row.value); row.status = "";});
  reviewing = false; reviewedChanges = null; renderTable(); setMsg("Unsaved changes discarded.");
}
function reviewChanges() {
  if (busy() || !settingsReady || !changedRows().length || changedRows().some(validationError)) return;
  reviewedChanges = changedRows().map(row => ({key:row.key, value:String(row.new_value).trim()}));
  const list = ms("msReviewList"); list.replaceChildren();
  changedRows().forEach(row => {
    const item = document.createElement("div"); item.className = "grbl-review-item";
    item.innerHTML = `<strong>${esc(row.code)} · ${esc(row.description)}</strong><p>${esc(displayValue(row, row.value))} → ${esc(displayValue(row, row.new_value))} <span class="grbl-muted">${esc(row.unit)}</span></p><code>${esc(row.code)}=${esc(String(row.new_value).trim())}</code>`;
    list.appendChild(item);
  });
  reviewing = true; setView(); updateButtons();
  ms("msReviewTitle").scrollIntoView({block:"nearest"});
  setMsg("Review covers pending edits across every category. Nothing has been sent yet.");
}
async function saveChanges() {
  if (busy() || !settingsReady || !reviewing || !reviewedChanges?.length) return;
  const changes = reviewedChanges.map(change => ({...change}));
  if (JSON.stringify(changes) !== JSON.stringify(changedRows().map(row => ({key:row.key, value:String(row.new_value).trim()})))) {reviewChanges(); return;}
  saving = true; updateButtons(); setMsg("Backing up and saving changed settings...");
  try {
    const res = await api("/api/machine-settings", "POST", {changes});
    if (!Array.isArray(res.results) || !res.results.length) throw new Error(`${res.error || res.message || "No write result returned."}${res.backup?.error ? ` ${res.backup.error}` : ""}`);
    const results = new Map(res.results.map(result => [String(result.key), result]));
    const verification = new Map(changes.map(change => [change.key, {...change, ok:!!results.get(change.key)?.ok, message:results.get(change.key)?.message || "No write result returned"}]));
    settingsRows.forEach(row => {const attempt = verification.get(row.key); if (attempt) row.status = attempt.ok ? "Accepted; waiting for read-back" : `Failed: ${attempt.message}`;});
    reviewing = false; reviewedChanges = null; renderTable();
    setMsg("Write responses received. Reading controller to verify...");
    const verified = await startCollectAndPoll({verification, preserveMessage:true});
    if (verified) {
      const confirmed = settingsRows.filter(row => verification.has(row.key) && row.status === "Verified on controller").length;
      const backup = res.backup?.file ? ` Backup: ${String(res.backup.file).split(/[\\/]/).pop()}.` : "";
      setMsg(`Verified ${confirmed} of ${changes.length} changes.${confirmed < changes.length ? " Unverified or failed values remain pending." : ""}${backup}`, confirmed < changes.length ? "error" : "muted");
    }
  } catch (err) {
    setMsg(`Save failed: ${err.message || err}. Edits remain pending.`, "error");
  } finally {saving = false; updateButtons();}
}
function init() {
  window.__firmwareCollectRunning = false;
  CATEGORIES.forEach(([id, title]) => {
    const button = document.createElement("button"); button.type = "button"; button.dataset.category = id;
    button.innerHTML = `<span>${esc(title)}</span><span class="grbl-category-count"></span>`;
    button.addEventListener("click", () => {if (busy()) return; activeCategory = id; reviewing = false; reviewedChanges = null; ms("msSearch").value = ""; renderTable();});
    ms("msCategories").appendChild(button);
  });
  ms("msSearch").addEventListener("input", () => {reviewing = false; reviewedChanges = null; renderTable();});
  ["msChangedOnly", "msShowZ"].forEach(id => ms(id).addEventListener("change", renderTable));
  ms("msRefresh").onclick = () => loadSettings();
  ms("msDownload").onclick = downloadBackup;
  ms("msReset").onclick = resetUnsaved;
  ms("msSave").onclick = reviewChanges;
  ms("msApply").onclick = saveChanges;
  ms("msBack").onclick = () => {reviewing = false; reviewedChanges = null; renderTable();};
  window.addEventListener("beforeunload", event => {if (changedRows().length || saving) {event.preventDefault(); event.returnValue = "";}});
  renderGrblVersion({ok:false, error:"No GRBL version information available."}); renderTable();
  loadSettings();
}
init();
