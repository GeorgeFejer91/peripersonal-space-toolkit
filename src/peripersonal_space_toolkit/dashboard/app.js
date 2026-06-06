let state = null;
let viewerReady = false;
const activePolls = new Set();
const CUSTOM_TEMPLATE_ID = "__custom__";
const WORKFLOW_STEPS = ["study", "stimulus", "trials", "run", "review"];
const STEP_TARGETS = {
  study: "study",
  stimulus: "stimulus",
  trials: "trials",
  run: "run",
  review: "review"
};
const NEXT_STEP = {
  study: "stimulus",
  stimulus: "trials",
  trials: "run",
  run: "review"
};
const LAYOUT_DEFAULTS = {
  sideWidth: 460,
  previewHeight: 360
};
const LOCAL_BACKEND_DEFAULT = "http://127.0.0.1:8766";

const $ = (id) => document.getElementById(id);
let apiBase = "";

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(apiUrl(path), {
      headers: { "Content-Type": "application/json" },
      ...options
    });
  } catch (error) {
    setConnectionStatus(false);
    throw error;
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch (_err) {
      detail = await response.text();
    }
    setConnectionStatus(false);
    throw new Error(detail);
  }
  setConnectionStatus(true);
  return response.json();
}

function apiUrl(path) {
  if (/^https?:\/\//i.test(path)) return path;
  return `${apiBase}${path}`;
}

function isLocalDashboardOrigin() {
  return ["127.0.0.1", "localhost", "[::1]", "::1"].includes(window.location.hostname);
}

function loadApiBase() {
  const stored = localStorage.getItem("ppsDashboard.apiBase");
  apiBase = stored || (isLocalDashboardOrigin() ? "" : LOCAL_BACKEND_DEFAULT);
  $("backend-url").value = apiBase || window.location.origin;
}

function saveApiBase(value) {
  const trimmed = String(value || "").trim().replace(/\/+$/, "");
  apiBase = trimmed && trimmed !== window.location.origin ? trimmed : "";
  if (apiBase) {
    localStorage.setItem("ppsDashboard.apiBase", apiBase);
  } else {
    localStorage.removeItem("ppsDashboard.apiBase");
  }
  $("backend-url").value = apiBase || window.location.origin;
}

function setConnectionStatus(connected) {
  const status = $("connection-status");
  if (!status) return;
  status.textContent = connected ? "connected" : "disconnected";
  status.className = `status-label ${connected ? "ready" : "required"}`;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => toast.classList.remove("visible"), 3200);
}

function numberValue(id, fallback = 0) {
  const value = Number($(id).value);
  return Number.isFinite(value) ? value : fallback;
}

function parseIntegerList(value) {
  return String(value || "")
    .split(",")
    .map((item) => Number.parseInt(item.trim(), 10))
    .filter((item) => Number.isFinite(item));
}

function parseNumberList(value) {
  return String(value || "")
    .split(",")
    .map((item) => Number.parseFloat(item.trim()))
    .filter((item) => Number.isFinite(item));
}

function formatList(items) {
  return (items || []).join(", ");
}

async function loadState() {
  try {
    state = await api("/api/state");
    renderAll();
    updateViewer();
  } catch (error) {
    reportError(error);
  }
}

function renderAll() {
  if (!state) return;
  renderHeader();
  renderStudy();
  renderStimulus();
  renderTrials();
  renderRun();
  renderReview();
  renderPreviewTables();
  renderWorkflow();
}

function renderHeader() {
  $("design-title").textContent = state.design.name || "Untitled PPS design";
}

function renderStudy() {
  const select = $("template-select");
  select.innerHTML = "";
  const customOption = document.createElement("option");
  customOption.value = CUSTOM_TEMPLATE_ID;
  customOption.textContent = "Custom design (define manually)";
  customOption.selected = !state.selected_template;
  select.appendChild(customOption);
  for (const template of state.templates) {
    const option = document.createElement("option");
    option.value = template.template_id;
    option.textContent = template.citation_label;
    option.selected = template.template_id === state.selected_template;
    select.appendChild(option);
  }
  $("design-name").value = state.design.name || "";
  const current = state.templates.find((item) => item.template_id === state.selected_template);
  const lines = [];
  if (current) {
    lines.push(`<div>${escapeHtml(current.citation_label)}</div>`);
    if (current.doi) {
      lines.push(
        `<div>DOI: <a href="${escapeAttr(doiUrl(current.doi))}" target="_blank" rel="noopener noreferrer">${escapeHtml(current.doi)}</a></div>`
      );
    }
    if (current.notes) lines.push(`<div>${escapeHtml(current.notes)}</div>`);
  } else {
    lines.push("<div>Custom design selected.</div>");
    lines.push("<div>Define the trajectory, timing, audio, trial assembly, and session settings manually.</div>");
  }
  $("profile-summary").innerHTML = lines.join("");
}

function renderStimulus() {
  const controls = state.trajectory_controls || {};
  $("start-distance").value = controls.start_distance_cm ?? 110;
  $("end-distance").value = controls.end_distance_cm ?? 10;
  $("start-rotation").value = controls.start_rotation_deg ?? 0;
  $("end-rotation").value = controls.end_rotation_deg ?? 0;
  $("movement-duration").value = controls.movement_duration_s ?? 3;
  $("start-hold").value = controls.start_hold_s ?? 0.5;
  $("end-hold").value = controls.end_hold_s ?? 0.5;
  syncPreviewModeControls($("preview-mode").value || "2d");
  renderNoiseTable();
  renderAudioTable();
}

function renderNoiseTable() {
  const body = $("noise-table").querySelector("tbody");
  body.innerHTML = "";
  for (const noise of state.design.noises || []) {
    const row = body.insertRow();
    row.innerHTML = `
      <td><input data-field="label" value="${escapeAttr(noise.label || "")}"></td>
      <td>
        <select data-field="noise_type">
          ${["pink", "blue", "white", "brown"].map((item) => `<option value="${item}" ${item === noise.noise_type ? "selected" : ""}>${item}</option>`).join("")}
        </select>
      </td>
      <td><input data-field="azimuth_deg" type="number" step="1" value="${Number(noise.azimuth_deg || 0)}"></td>
      <td><input data-field="elevation_deg" type="number" step="1" value="${Number(noise.elevation_deg || 0)}"></td>
      <td><input data-field="gain" type="number" step="0.05" min="0.01" value="${Number(noise.gain || 1)}"></td>
      <td class="remove-cell"><button type="button" data-remove-noise>Remove</button></td>
    `;
  }
}

function renderAudioTable() {
  const body = $("audio-table").querySelector("tbody");
  body.innerHTML = "";
  const rows = [
    ...(state.design.custom_looming_files || []).map((item) => ({ ...item, use: "looming" })),
    ...(state.design.prestimulus_files || []).map((item) => ({ ...item, use: "prestimulus" }))
  ];
  for (const audio of rows) {
    const row = body.insertRow();
    row.innerHTML = `
      <td>
        <select data-field="use">
          <option value="looming" ${audio.use === "looming" ? "selected" : ""}>looming</option>
          <option value="prestimulus" ${audio.use === "prestimulus" ? "selected" : ""}>prestimulus</option>
        </select>
      </td>
      <td><input data-field="label" value="${escapeAttr(audio.label || "")}"></td>
      <td><input data-field="path" value="${escapeAttr(audio.path || "")}"></td>
      <td><input data-field="target_duration_s" type="number" min="0.1" step="0.1" value="${Number(audio.target_duration_s || 4)}"></td>
      <td class="remove-cell"><button type="button" data-remove-audio>Remove</button></td>
    `;
  }
}

function renderTrials() {
  const protocol = state.design.protocol || {};
  $("repetitions").value = protocol.repetitions_per_condition ?? 1;
  $("participants").value = protocol.participants ?? 1;
  $("blocks").value = protocol.blocks ?? 1;
  $("catch-percent").value = protocol.catch_trial_percentage ?? 0;
  $("soa-values").value = formatList(protocol.soa_values_ms);
  $("spatial-values").value = formatList(protocol.spatial_values_cm);
  $("pair-spatial").checked = Boolean(protocol.pair_spatial_values_with_soas);

  const summary = $("protocol-summary");
  summary.innerHTML = "";
  for (const [key, value] of Object.entries(state.protocol_summary || {})) {
    const item = document.createElement("div");
    item.className = "summary-item";
    item.innerHTML = `<span>${humanize(key)}</span><strong>${value}</strong>`;
    summary.appendChild(item);
  }
}

function renderRun() {
  const isCustom = Boolean(state.custom_workflow && state.custom_workflow.is_custom);
  $("participant-id").value = state.participant_id || (isCustom ? "" : "P001");
  const preflight = state.preflight || {};
  const ready = Boolean(preflight.ready && state.session);
  const pill = $("readiness-pill");
  pill.textContent = ready ? "ready" : "required";
  pill.className = `status-label ${ready ? "ready" : "required"}`;

  const rows = [
    ["Design", preflight.valid_design],
    ["Participant", preflight.participant_ready],
    ["Stimuli", preflight.render_ready],
    ["Schedule", preflight.schedule_ready],
    ["Prepared session", Boolean(state.session)]
  ];
  $("readiness-list").innerHTML = rows
    .map(([label, ok]) => `<div class="status-row"><strong>${label}</strong><span>${ok ? "ready" : "required"}</span></div>`)
    .join("");
  $("focus-action").disabled = !state.session;
}

function renderWorkflow() {
  const workflow = state.custom_workflow || { is_custom: false, steps: [] };
  document.body.classList.toggle("custom-mode", Boolean(workflow.is_custom));
  const pill = $("workflow-pill");
  const activeStep = workflow.current_step || "review";
  const activeIndex = WORKFLOW_STEPS.indexOf(activeStep);
  const unlockedIndex = workflow.is_custom && activeIndex >= 0 ? activeIndex : WORKFLOW_STEPS.length - 1;

  pill.textContent = workflow.is_custom
    ? workflow.ready_to_prepare ? "custom ready" : `${stepLabel(activeStep)} required`
    : "profile loaded";
  pill.className = `status-label ${workflow.is_custom && !workflow.ready_to_prepare ? "required" : "ready"}`;

  const stepMap = new Map((workflow.steps || []).map((step) => [step.id, step]));
  for (const stepId of WORKFLOW_STEPS) {
    const index = WORKFLOW_STEPS.indexOf(stepId);
    const step = stepMap.get(stepId) || { id: stepId, complete: !workflow.is_custom, missing: [] };
    const locked = Boolean(workflow.is_custom && index > unlockedIndex);
    const current = Boolean(workflow.is_custom && stepId === activeStep);
    const complete = Boolean(step.complete);
    const link = document.querySelector(`[data-step-link="${stepId}"]`);
    const stateLabel = document.querySelector(`[data-step-state="${stepId}"]`);
    const badges = document.querySelectorAll(`[data-step-badge="${stepId}"]`);

    if (link) {
      link.classList.toggle("locked", locked);
      link.classList.toggle("current", current);
      link.classList.toggle("complete", complete);
      link.setAttribute("aria-disabled", String(locked));
    }
    if (stateLabel) {
      stateLabel.textContent = complete ? "ok" : String(index + 1);
    }
    for (const badge of badges) {
      badge.textContent = locked ? "locked" : complete ? "ready" : "required";
      badge.className = `step-badge ${locked ? "locked" : complete ? "complete" : current ? "current" : ""}`;
    }
  }

  for (const panel of document.querySelectorAll("[data-step-panel]")) {
    const stepId = panel.dataset.stepPanel;
    const locked = Boolean(workflow.is_custom && WORKFLOW_STEPS.indexOf(stepId) > unlockedIndex);
    panel.classList.toggle("locked", locked);
    for (const control of panel.querySelectorAll("input, select, button")) {
      if (locked) {
        if (!control.disabled) {
          control.dataset.workflowLockDisabled = "true";
        }
        control.disabled = true;
      } else if (control.dataset.workflowLockDisabled === "true") {
        control.disabled = false;
        delete control.dataset.workflowLockDisabled;
      }
    }
  }

  if (workflow.is_custom) {
    $("render-action").disabled = !workflow.ready_to_render;
    $("stress-action").disabled = !workflow.ready_to_render;
    $("prepare-action").disabled = !workflow.ready_to_prepare || !Boolean(state.preflight && state.preflight.render_ready);
    $("focus-action").disabled = !state.session || !workflow.ready_to_prepare;
  }
  updateActiveNav();
}

function renderReview() {
  const session = state.session;
  if (session) {
    $("session-summary").textContent = [
      `Prepared session: ${session.session_id}`,
      `Output: ${session.session_dir}`,
      `Manifest: ${session.manifest_path}`,
      `Blocks: ${session.blocks.length}`
    ].join("\n");
  } else {
    const render = state.render || {};
    $("session-summary").textContent = [
      `Render status: ${render.status || "missing"}`,
      `Render engine: ${render.render_engine || "not available"}`,
      `Rendered WAVs: ${render.wav_count || 0}`,
      `Render dir: ${render.render_dir || ""}`
    ].join("\n");
  }

  const jobs = state.jobs || [];
  $("job-list").innerHTML = jobs.length
    ? jobs.map(renderJob).join("")
    : `<div class="summary-text">No dashboard jobs yet.</div>`;
}

function renderPreviewTables() {
  const trialRows = state.trial_preview || [];
  $("trial-count").textContent = `${trialRows.length} shown`;
  fillTable("trial-table", trialRows, ["block", "trial", "type", "phase", "soa_ms", "space_cm", "tactile_site", "noise"]);

  const orderRows = state.participant_orders || [];
  $("order-count").textContent = `${orderRows.length} shown`;
  fillTable("order-table", orderRows, ["participant", "block_order"]);
}

function fillTable(id, rows, keys) {
  const body = $(id).querySelector("tbody");
  body.innerHTML = "";
  for (const row of rows) {
    const tr = body.insertRow();
    for (const key of keys) {
      const cell = tr.insertCell();
      cell.textContent = row[key] ?? "";
    }
  }
}

function renderJob(job) {
  const detail = job.result ? JSON.stringify(job.result, null, 2) : (job.error || job.message || "");
  return `
    <div class="job-item">
      <strong><span>${humanize(job.kind)}</span><span>${job.status}</span></strong>
      <div class="muted">${job.message || ""}</div>
      ${detail ? `<pre>${escapeHtml(detail)}</pre>` : ""}
    </div>
  `;
}

function collectPayload() {
  const design = clone(state.design);
  design.name = $("design-name").value.trim() || "Untitled PPS design";
  design.noises = collectNoises();
  const audio = collectAudioFiles();
  design.custom_looming_files = audio.looming;
  design.prestimulus_files = audio.prestimulus;
  design.protocol = {
    ...(design.protocol || {}),
    repetitions_per_condition: Math.max(1, Math.round(numberValue("repetitions", 1))),
    soa_values_ms: parseIntegerList($("soa-values").value),
    spatial_values_cm: parseNumberList($("spatial-values").value),
    pair_spatial_values_with_soas: $("pair-spatial").checked,
    catch_trial_percentage: numberValue("catch-percent", 0),
    blocks: Math.max(1, Math.round(numberValue("blocks", 1))),
    participants: Math.max(1, Math.round(numberValue("participants", 1)))
  };
  return {
    participant_id: $("participant-id").value.trim() || (state.custom_workflow?.is_custom ? "" : "P001"),
    design,
    trajectory_controls: {
      start_distance_cm: numberValue("start-distance", 110),
      end_distance_cm: numberValue("end-distance", 10),
      start_rotation_deg: numberValue("start-rotation", 0),
      end_rotation_deg: numberValue("end-rotation", 0),
      movement_duration_s: numberValue("movement-duration", 3),
      start_hold_s: numberValue("start-hold", 0.5),
      end_hold_s: numberValue("end-hold", 0.5)
    }
  };
}

function collectNoises() {
  return [...$("noise-table").querySelectorAll("tbody tr")].map((row) => {
    const field = (name) => row.querySelector(`[data-field="${name}"]`);
    return {
      label: field("label").value.trim() || "Noise",
      noise_type: field("noise_type").value,
      azimuth_deg: Number(field("azimuth_deg").value || 0),
      elevation_deg: Number(field("elevation_deg").value || 0),
      gain: Number(field("gain").value || 1)
    };
  });
}

function collectAudioFiles() {
  const result = { looming: [], prestimulus: [] };
  for (const row of $("audio-table").querySelectorAll("tbody tr")) {
    const field = (name) => row.querySelector(`[data-field="${name}"]`);
    const item = {
      label: field("label").value.trim() || "Audio file",
      path: field("path").value.trim(),
      target_duration_s: Number(field("target_duration_s").value || 4)
    };
    if (field("use").value === "prestimulus") {
      result.prestimulus.push(item);
    } else {
      result.looming.push(item);
    }
  }
  return result;
}

async function applyDesign() {
  state = await api("/api/design", {
    method: "POST",
    body: JSON.stringify(collectPayload())
  });
  renderAll();
  updateViewer();
  showToast("Design applied");
}

async function continueWorkflowStep(stepId) {
  state = await api("/api/design", {
    method: "POST",
    body: JSON.stringify(collectPayload())
  });
  renderAll();
  updateViewer();
  const step = getWorkflowStep(stepId);
  if (!step || step.complete) {
    const next = NEXT_STEP[stepId];
    if (next) {
      scrollToStep(next);
    }
    showToast("Step saved");
    return;
  }
  showToast(step.missing.join(" "));
  scrollToStep(stepId);
}

async function loadTemplate() {
  const id = $("template-select").value;
  if (!id) return;
  state = await api(`/api/templates/${encodeURIComponent(id)}/load`, { method: "POST" });
  renderAll();
  updateViewer();
  showToast(id === CUSTOM_TEMPLATE_ID ? "Custom design started" : "Profile loaded");
}

async function startRender() {
  if (!ensureWorkflowAction("ready_to_render")) return;
  const job = await api("/api/render", {
    method: "POST",
    body: JSON.stringify(collectPayload())
  });
  showToast("Render job started");
  pollJob(job.job_id);
  await loadState();
}

async function prepareSession() {
  if (!ensureWorkflowAction("ready_to_prepare")) return;
  state = await api("/api/session/prepare", {
    method: "POST",
    body: JSON.stringify(collectPayload())
  });
  renderAll();
  updateViewer();
  showToast("Session prepared");
}

async function stressAudio() {
  if (!ensureWorkflowAction("ready_to_render")) return;
  const job = await api("/api/audio/stress", { method: "POST" });
  showToast("Audio stress job started");
  pollJob(job.job_id);
  await loadState();
}

async function startFocus() {
  if (!ensureWorkflowAction("ready_to_prepare")) return;
  const job = await api("/api/focus/start", { method: "POST" });
  showToast("Native Focus Mode launching");
  pollJob(job.job_id);
  await loadState();
}

async function pollJob(jobId) {
  if (!jobId || activePolls.has(jobId)) return;
  activePolls.add(jobId);
  for (;;) {
    await delay(900);
    const job = await api(`/api/jobs/${jobId}`);
    await loadState();
    if (job.status === "succeeded" || job.status === "failed") {
      activePolls.delete(jobId);
      showToast(`${humanize(job.kind)} ${job.status}`);
      break;
    }
  }
}

function updateViewer() {
  if (!state || !viewerReady) return;
  const frame = $("trajectory-frame");
  const payload = clone(state.viewer_payload || {});
  payload.preview_mode = $("preview-mode").value || "2d";
  syncPreviewModeControls(payload.preview_mode);
  frame.contentWindow.updateTrajectory(payload);
}

function setPreviewMode(mode) {
  const nextMode = mode === "3d" ? "3d" : "2d";
  $("preview-mode").value = nextMode;
  syncPreviewModeControls(nextMode);
  updateViewer();
}

function syncPreviewModeControls(mode) {
  const current = mode === "3d" ? "3d" : "2d";
  for (const button of document.querySelectorAll("[data-preview-mode]")) {
    button.classList.toggle("active", button.dataset.previewMode === current);
    button.setAttribute("aria-pressed", String(button.dataset.previewMode === current));
  }
}

function getWorkflowStep(stepId) {
  return (state.custom_workflow?.steps || []).find((step) => step.id === stepId);
}

function ensureWorkflowAction(key) {
  const workflow = state.custom_workflow || {};
  if (!workflow.is_custom || workflow[key]) return true;
  const missing = workflow.missing || [];
  showToast(missing.length ? missing.join(" ") : "Complete the custom design steps first.");
  scrollToStep(workflow.current_step || "study");
  return false;
}

function stepLabel(stepId) {
  return (getWorkflowStep(stepId)?.label || humanize(stepId)).toLowerCase();
}

function scrollToStep(stepId) {
  const target = $(STEP_TARGETS[stepId] || stepId);
  if (target) {
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function updateActiveNav() {
  let active = "study";
  const viewportTop = 96;
  for (const stepId of WORKFLOW_STEPS) {
    const target = $(STEP_TARGETS[stepId]);
    if (!target) continue;
    if (target.getBoundingClientRect().top <= viewportTop) {
      active = stepId;
    }
  }
  for (const link of document.querySelectorAll("[data-step-link]")) {
    link.classList.toggle("active", link.dataset.stepLink === active);
  }
}

function loadLayoutSettings() {
  const sideWidth = clampNumber(Number(localStorage.getItem("ppsDashboard.sideWidth")), 360, 640, LAYOUT_DEFAULTS.sideWidth);
  const previewHeight = clampNumber(Number(localStorage.getItem("ppsDashboard.previewHeight")), 300, 620, LAYOUT_DEFAULTS.previewHeight);
  applyLayoutSettings({ sideWidth, previewHeight });
}

function applyLayoutSettings({ sideWidth, previewHeight }) {
  document.documentElement.style.setProperty("--side-column-width", `${sideWidth}px`);
  document.documentElement.style.setProperty("--preview-height", `${previewHeight}px`);
  $("layout-side-width").value = String(sideWidth);
  $("layout-preview-height").value = String(previewHeight);
  $("layout-side-width-value").textContent = `${sideWidth}px`;
  $("layout-preview-height-value").textContent = `${previewHeight}px`;
}

function updateLayoutSetting(key, value) {
  const next = {
    sideWidth: Number($("layout-side-width").value),
    previewHeight: Number($("layout-preview-height").value)
  };
  next[key] = Number(value);
  localStorage.setItem(`ppsDashboard.${key}`, String(next[key]));
  applyLayoutSettings(next);
}

function clampNumber(value, min, max, fallback) {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

function addNoiseRow() {
  state.design.noises = state.design.noises || [];
  state.design.noises.push({
    label: "New noise",
    noise_type: "pink",
    azimuth_deg: 0,
    elevation_deg: 0,
    gain: 1
  });
  renderNoiseTable();
}

function addAudioRow() {
  state.design.custom_looming_files = state.design.custom_looming_files || [];
  state.design.custom_looming_files.push({
    label: "Audio file",
    path: "",
    target_duration_s: 4
  });
  renderAudioTable();
}

function removeRowFromButton(button) {
  button.closest("tr").remove();
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function humanize(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("\n", " ");
}

function doiUrl(value) {
  const doi = String(value || "").trim();
  if (/^https?:\/\//i.test(doi)) {
    return doi;
  }
  return `https://doi.org/${doi.replace(/^doi:\s*/i, "")}`;
}

function wireEvents() {
  $("refresh-state").addEventListener("click", () => loadState().catch(reportError));
  $("refresh-jobs").addEventListener("click", () => loadState().catch(reportError));
  $("apply-design").addEventListener("click", () => applyDesign().catch(reportError));
  $("connect-backend").addEventListener("click", () => {
    saveApiBase($("backend-url").value);
    loadState().catch(reportError);
  });
  $("backend-url").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      saveApiBase($("backend-url").value);
      loadState().catch(reportError);
    }
  });
  $("load-template").addEventListener("click", () => loadTemplate().catch(reportError));
  $("render-action").addEventListener("click", () => startRender().catch(reportError));
  $("prepare-action").addEventListener("click", () => prepareSession().catch(reportError));
  $("stress-action").addEventListener("click", () => stressAudio().catch(reportError));
  $("focus-action").addEventListener("click", () => startFocus().catch(reportError));
  $("add-noise").addEventListener("click", addNoiseRow);
  $("add-audio").addEventListener("click", addAudioRow);
  $("reset-camera").addEventListener("click", () => {
    const frame = $("trajectory-frame");
    if (frame.contentWindow.resetTrajectoryCamera) frame.contentWindow.resetTrajectoryCamera();
  });
  $("preview-mode").addEventListener("change", () => setPreviewMode($("preview-mode").value));
  $("layout-side-width").addEventListener("input", () => updateLayoutSetting("sideWidth", $("layout-side-width").value));
  $("layout-preview-height").addEventListener("input", () => updateLayoutSetting("previewHeight", $("layout-preview-height").value));
  for (const button of document.querySelectorAll("[data-preview-mode]")) {
    button.addEventListener("click", () => setPreviewMode(button.dataset.previewMode));
  }
  for (const button of document.querySelectorAll("[data-continue-step]")) {
    button.addEventListener("click", () => continueWorkflowStep(button.dataset.continueStep).catch(reportError));
  }
  for (const link of document.querySelectorAll("[data-step-link]")) {
    link.addEventListener("click", (event) => {
      const stepId = link.dataset.stepLink;
      if (link.classList.contains("locked")) {
        event.preventDefault();
        showToast("Complete the current custom step first.");
        scrollToStep(state.custom_workflow?.current_step || "study");
      } else {
        event.preventDefault();
        scrollToStep(stepId);
      }
    });
  }
  window.addEventListener("scroll", updateActiveNav, { passive: true });
  $("trajectory-frame").addEventListener("load", () => {
    viewerReady = true;
    updateViewer();
  });
  document.addEventListener("click", (event) => {
    if (event.target.matches("[data-remove-noise], [data-remove-audio]")) {
      removeRowFromButton(event.target);
    }
  });
}

function reportError(error) {
  console.error(error);
  showToast(error.message || String(error));
}

loadApiBase();
loadLayoutSettings();
wireEvents();
loadState().catch(reportError);
