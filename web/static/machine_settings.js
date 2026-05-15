async function api(url, method = "GET", body = null) {
  const opt = { method, headers: {} };
  if (body) {
    opt.headers["Content-Type"] = "application/json";
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(url, opt);
  return r.json();
}

function esc(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

let settingsRows = [];
let rawBackupText = "";

function setRawOutput(text) {
  const el = document.getElementById("msRaw");
  if (!el) return;
  el.textContent = String(text || "").trim();
}

function setMsg(text, cls = "muted") {
  const el = document.getElementById("msMsg");
  if (!el) return;
  el.className = `small ${cls}`;
  el.textContent = text;
}

function changedRows() {
  return settingsRows.filter((r) => String(r.new_value) !== String(r.value));
}

function updateButtons() {
  const changed = changedRows().length > 0;
  const save = document.getElementById("msSave");
  const reset = document.getElementById("msReset");
  if (save) save.disabled = !changed;
  if (reset) reset.disabled = !changed;
}

function setRowChangedState(idx, inputEl) {
  if (!Number.isFinite(idx) || !settingsRows[idx]) return;
  const row = settingsRows[idx];
  const tr = inputEl?.closest("tr");
  const statusCell = tr?.querySelector(".machine-setting-status");
  const changed = String(row.new_value) !== String(row.value);
  if (tr) tr.classList.toggle("machine-setting-changed", changed);
  if (statusCell && row.status) {
    statusCell.textContent = "";
  }
}

function renderTable() {
  const body = document.getElementById("msBody");
  if (!body) return;
  if (!settingsRows.length) {
    body.innerHTML = '<tr><td colspan="6" class="muted">No machine settings found.</td></tr>';
    updateButtons();
    return;
  }
  body.innerHTML = "";
  settingsRows.forEach((row, idx) => {
    const changed = String(row.new_value) !== String(row.value);
    const tr = document.createElement("tr");
    if (changed) tr.classList.add("machine-setting-changed");
    tr.innerHTML = `
      <td><code>${esc(row.code)}</code></td>
      <td>${esc(row.description)}</td>
      <td><code>${esc(row.value)}</code></td>
      <td><input data-idx="${idx}" class="machine-setting-input" value="${esc(row.new_value)}"></td>
      <td>${esc(row.unit || "—")}<div class="muted small">${esc(row.notes || "—")}</div></td>
      <td class="small machine-setting-status">${esc(row.status || "")}</td>
    `;
    body.appendChild(tr);
  });
  updateButtons();
}

async function loadSettings(options = {}) {
  const opts = typeof options === "boolean" ? { showMsg: options } : (options || {});
  const showMsg = opts.showMsg !== false;
  const preserveMessage = opts.preserveMessage === true;
  if (showMsg && !preserveMessage) setMsg("Loading machine settings...", "muted");
  const r = await api("/api/machine-settings");
  setRawOutput(r.raw || "");
  if (!r.ok) {
    if (!preserveMessage) setMsg(r.error || "Failed to load machine settings.", "error");
    settingsRows = [];
    renderTable();
    return;
  }
  rawBackupText = String(r.raw || "");
  settingsRows = (r.settings || []).map((x) => ({
    ...x,
    new_value: String(x.value || ""),
    status: "",
  }));
  renderTable();
  if (!preserveMessage) setMsg(r.message || `Loaded ${settingsRows.length} setting(s).`, "muted");
}

function buildBackupContent() {
  const now = new Date();
  const ts = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
  return `Ray5 Machine Settings Backup\nGenerated: ${ts}\n\n${rawBackupText || ""}\n`;
}

function downloadBackup() {
  const now = new Date();
  const stamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}_${String(now.getHours()).padStart(2, "0")}${String(now.getMinutes()).padStart(2, "0")}${String(now.getSeconds()).padStart(2, "0")}`;
  const filename = `ray5_machine_settings_backup_${stamp}.txt`;
  const blob = new Blob([buildBackupContent()], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function resetUnsaved() {
  settingsRows = settingsRows.map((r) => ({ ...r, new_value: String(r.value || ""), status: "" }));
  renderTable();
  setMsg("Unsaved changes reset.", "muted");
}

async function saveChanges() {
  const changes = changedRows().map((r) => ({ key: r.key, value: String(r.new_value).trim() }));
  if (!changes.length) return;
  const commands = changes.map((c) => `$${c.key}=${c.value}`);
  const confirmText = `Apply ${changes.length} machine setting change(s)?\n\n${commands.join("\n")}\n\nChanging controller settings can affect motion, limits, homing, and laser behavior. Continue?`;
  if (!confirm(confirmText)) return;
  setMsg("Saving changed settings...", "muted");
  const res = await api("/api/machine-settings", "POST", { changes });
  const byKey = new Map((res.results || []).map((x) => [String(x.key), x]));
  settingsRows = settingsRows.map((r) => {
    const rr = byKey.get(String(r.key));
    if (!rr) return { ...r, status: "" };
    const ok = !!rr.ok;
    return {
      ...r,
      value: ok ? String(r.new_value) : r.value,
      status: ok ? "Saved" : `Error: ${rr.message || "failed"}`,
    };
  });
  renderTable();
  const saveMsg = res.message || (res.ok ? "Saved settings." : "Some settings failed to save.");
  const saveMsgClass = res.ok ? "muted" : "error";
  setMsg(saveMsg, saveMsgClass);
  await loadSettings({ showMsg: false, preserveMessage: true });
  setMsg(saveMsg, saveMsgClass);
}

function init() {
  const tableBody = document.getElementById("msBody");
  if (tableBody) {
    tableBody.addEventListener("input", (ev) => {
      const target = ev.target;
      if (!(target instanceof HTMLInputElement)) return;
      if (!target.classList.contains("machine-setting-input")) return;
      const idx = Number(target.getAttribute("data-idx"));
      if (!Number.isFinite(idx) || !settingsRows[idx]) return;
      settingsRows[idx].new_value = target.value;
      settingsRows[idx].status = "";
      setRowChangedState(idx, target);
      updateButtons();
    });
  }
  document.getElementById("msRefresh").onclick = () => loadSettings({ showMsg: true });
  document.getElementById("msDownload").onclick = () => downloadBackup();
  document.getElementById("msSave").onclick = () => saveChanges();
  document.getElementById("msReset").onclick = () => resetUnsaved();
  loadSettings({ showMsg: true });
}

init();
