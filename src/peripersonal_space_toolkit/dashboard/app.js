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
const LOCAL_BACKEND_DEFAULT = "http://127.0.0.1:8766";
const PANEL_RESIZE_SNAP_PX = 8;
const PANEL_HEIGHT_MIN = 150;
const PANEL_HEIGHT_MAX = 1000;
const SPLIT_DEFAULTS = {
  sideWidth: 460,
  ordersWidth: 420
};
const SPLIT_LIMITS = {
  sideWidth: { min: 320, max: 760 },
  ordersWidth: { min: 300, max: 760 }
};
const PROCEDURAL_NOISE_TYPES = [
  { value: "white", label: "White" },
  { value: "pink", label: "Pink" },
  { value: "blue", label: "Blue" },
  { value: "violet", label: "Violet" },
  { value: "brown", label: "Brown" }
];
const IMPORTED_AUDIO_HANDLING = [
  { value: "spatialize", label: "Dry tone -> make looming" },
  { value: "preserve", label: "Already looming / control" },
  { value: "prestimulus", label: "Prestimulus cue" }
];
const TRAJECTORY_FIELD_IDS = [
  "start-distance",
  "end-distance",
  "start-rotation",
  "end-rotation",
  "movement-duration",
  "start-hold",
  "end-hold"
];

const $ = (id) => document.getElementById(id);
let apiBase = "";
let templateLoadInFlight = false;
let pendingAudioImportMode = "preserve";

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
  renderProfileSummary();
}

function renderProfileSummary() {
  const selectedId = $("template-select").value;
  const current = state.templates.find((item) => item.template_id === selectedId);
  const href = current?.doi ? doiUrl(current.doi) : "";
  const summary = $("profile-summary");
  summary.hidden = !href;
  summary.innerHTML = href
    ? `<a href="${escapeAttr(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(href)}</a>`
    : "";
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
  renderGeneratedNoiseSelect();
  renderNoiseTable();
  renderAudioTable();
  renderSourceCounts();
}

function renderGeneratedNoiseSelect() {
  const select = $("generated-noise-select");
  const current = select.value;
  select.innerHTML = '<option value="">Add generated noise...</option>';
  for (const item of PROCEDURAL_NOISE_TYPES) {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = item.label;
    select.appendChild(option);
  }
  select.value = PROCEDURAL_NOISE_TYPES.some((item) => item.value === current) ? current : "";
}

function renderNoiseTable() {
  const list = $("noise-list");
  list.innerHTML = "";
  for (const noise of state.design.noises || []) {
    const selectedNoise = String(noise.noise_type || "pink").toLowerCase();
    const card = document.createElement("div");
    card.className = "source-card noise-source-card";
    card.innerHTML = `
      <div class="source-card-heading">
        <strong>${escapeHtml(noiseTypeLabel(selectedNoise))} noise</strong>
        <button type="button" data-remove-noise>Remove</button>
      </div>
      <div class="source-card-fields">
        <div class="field-row">
          <label>Label</label>
          <input data-field="label" value="${escapeAttr(noise.label || "")}">
        </div>
        <div class="field-row">
          <label>Noise color</label>
          <select data-field="noise_type">
          ${PROCEDURAL_NOISE_TYPES.map((item) => `<option value="${item.value}" ${item.value === selectedNoise ? "selected" : ""}>${item.label}</option>`).join("")}
          </select>
        </div>
        <div class="field-row">
          <label>Azimuth</label>
          <input data-field="azimuth_deg" type="number" step="1" value="${Number(noise.azimuth_deg || 0)}">
        </div>
        <div class="field-row">
          <label>Elevation</label>
          <input data-field="elevation_deg" type="number" step="1" value="${Number(noise.elevation_deg || 0)}">
        </div>
        <div class="field-row">
          <label>Gain</label>
          <input data-field="gain" type="number" step="0.05" min="0.01" value="${Number(noise.gain || 1)}">
        </div>
      </div>
    `;
    list.appendChild(card);
  }
}

function renderAudioTable() {
  const body = $("audio-table").querySelector("tbody");
  body.innerHTML = "";
  const rows = [
    ...(state.design.custom_looming_files || []).map((item) => ({ ...item, audio_role: item.render_mode || "preserve" })),
    ...(state.design.prestimulus_files || []).map((item) => ({ ...item, audio_role: "prestimulus" }))
  ];
  for (const audio of rows) {
    const row = body.insertRow();
    const role = String(audio.audio_role || audio.use || audio.render_mode || "preserve").toLowerCase();
    row.innerHTML = `
      <td>
        <select data-field="audio_role">
          ${IMPORTED_AUDIO_HANDLING.map((item) => `<option value="${item.value}" ${item.value === role ? "selected" : ""}>${item.label}</option>`).join("")}
        </select>
      </td>
      <td><input data-field="label" value="${escapeAttr(audio.label || "")}"></td>
      <td><input data-field="path" value="${escapeAttr(audio.path || "")}"></td>
      <td><input data-field="target_duration_s" type="number" min="0.1" step="0.1" value="${Number(audio.target_duration_s || 4)}"></td>
      <td><input data-field="gain" type="number" min="0.01" step="0.05" value="${Number(audio.gain || 1)}"></td>
      <td class="remove-cell"><button type="button" data-remove-audio>Remove</button></td>
    `;
  }
}

function renderSourceCounts() {
  const generated = $("noise-list").querySelectorAll(".noise-source-card").length;
  const audioRows = [...$("audio-table").querySelectorAll("tbody tr")];
  const imported = audioRows.filter((row) => row.querySelector('[data-field="audio_role"]')?.value !== "prestimulus").length;
  const prestimulus = audioRows.filter((row) => row.querySelector('[data-field="audio_role"]')?.value === "prestimulus").length;
  const total = generated + imported + prestimulus;
  $("source-counts").textContent = `${total} source${total === 1 ? "" : "s"}`;
  $("source-counts").className = `status-label ${generated || imported ? "ready" : "required"}`;
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
  return [...$("noise-list").querySelectorAll(".noise-source-card")].map((card) => {
    const field = (name) => card.querySelector(`[data-field="${name}"]`);
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
    const role = field("audio_role").value;
    const item = {
      label: field("label").value.trim() || "Audio file",
      path: field("path").value.trim(),
      target_duration_s: Number(field("target_duration_s").value || 4),
      render_mode: role === "spatialize" ? "spatialize" : "preserve",
      gain: Number(field("gain").value || 1)
    };
    if (role === "prestimulus") {
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
  if (templateLoadInFlight) return;
  const select = $("template-select");
  const id = select.value;
  if (!id) return;
  templateLoadInFlight = true;
  select.disabled = true;
  try {
    state = await api(`/api/templates/${encodeURIComponent(id)}/load`, { method: "POST" });
    renderAll();
    updateViewer();
    showToast(id === CUSTOM_TEMPLATE_ID ? "Custom design started" : "Profile loaded");
  } finally {
    templateLoadInFlight = false;
    $("template-select").disabled = false;
  }
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
  const payload = trajectoryPayloadFromControls();
  syncPreviewModeControls(payload.preview_mode);
  frame.contentWindow.updateTrajectory(payload);
}

function setPreviewMode(mode) {
  const nextMode = mode === "3d" ? "3d" : "2d";
  $("preview-mode").value = nextMode;
  syncPreviewModeControls(nextMode);
  updateViewer();
}

function currentTrajectoryControls() {
  return {
    start_distance_cm: clampNumber(numberValue("start-distance", 110), 1, 1000, 110),
    end_distance_cm: clampNumber(numberValue("end-distance", 10), 1, 1000, 10),
    start_rotation_deg: normalizeRotationDeg(numberValue("start-rotation", 0)),
    end_rotation_deg: normalizeRotationDeg(numberValue("end-rotation", 0)),
    movement_duration_s: Math.max(0.1, numberValue("movement-duration", 3)),
    start_hold_s: Math.max(0, numberValue("start-hold", 0.5)),
    end_hold_s: Math.max(0, numberValue("end-hold", 0.5))
  };
}

function trajectoryPayloadFromControls() {
  const controls = currentTrajectoryControls();
  const start = pointFromDistanceRotation(controls.start_distance_cm, controls.start_rotation_deg);
  const end = pointFromDistanceRotation(controls.end_distance_cm, controls.end_rotation_deg);
  const pathLength = distance3d(start, end);
  const radius = Math.max(0.1, controls.start_distance_cm / 100, controls.end_distance_cm / 100);
  return {
    ...clone(state.viewer_payload || {}),
    preview_mode: $("preview-mode").value || "2d",
    radius_m: radius,
    path_length_m: pathLength,
    movement_duration_s: controls.movement_duration_s,
    start,
    end,
    controls
  };
}

function pointFromDistanceRotation(distanceCm, rotationDeg) {
  const radiusM = distanceCm / 100;
  const radians = (normalizeSignedRotationDeg(rotationDeg) * Math.PI) / 180;
  return {
    x_m: radiusM * Math.sin(radians),
    y_m: radiusM * Math.cos(radians),
    z_m: 0
  };
}

function distance3d(start, end) {
  const dx = Number(start.x_m || 0) - Number(end.x_m || 0);
  const dy = Number(start.y_m || 0) - Number(end.y_m || 0);
  const dz = Number(start.z_m || 0) - Number(end.z_m || 0);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

function normalizeRotationDeg(value) {
  const rotation = Number(value);
  if (!Number.isFinite(rotation)) return 0;
  return ((rotation % 360) + 360) % 360;
}

function normalizeSignedRotationDeg(value) {
  return ((normalizeRotationDeg(value) + 180) % 360) - 180;
}

function applyTrajectoryControlUpdate(controls) {
  const fields = {
    start_distance_cm: "start-distance",
    end_distance_cm: "end-distance",
    start_rotation_deg: "start-rotation",
    end_rotation_deg: "end-rotation",
    movement_duration_s: "movement-duration",
    start_hold_s: "start-hold",
    end_hold_s: "end-hold"
  };
  for (const [key, id] of Object.entries(fields)) {
    if (controls[key] === undefined) continue;
    $(id).value = formatTrajectoryValue(key, controls[key]);
  }
  state.trajectory_controls = { ...(state.trajectory_controls || {}), ...currentTrajectoryControls() };
  updateViewer();
}

function formatTrajectoryValue(key, value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "";
  const decimals = key.endsWith("_deg") || key.endsWith("_cm") ? 1 : 2;
  return String(Number(numeric.toFixed(decimals)));
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

function loadResizableLayoutSettings() {
  applySplitSetting("sideWidth", Number(localStorage.getItem(splitStorageKey("sideWidth"))) || SPLIT_DEFAULTS.sideWidth, false);
  applySplitSetting("ordersWidth", Number(localStorage.getItem(splitStorageKey("ordersWidth"))) || SPLIT_DEFAULTS.ordersWidth, false);
  initializeResizablePanels();
}

function initializeResizablePanels() {
  for (const panel of document.querySelectorAll("[data-resizable-panel]")) {
    const panelId = panel.dataset.panelId || panel.id;
    const storedHeight = Number(localStorage.getItem(panelStorageKey(panelId)));
    if (Number.isFinite(storedHeight) && storedHeight > 0) {
      setPanelHeight(panel, storedHeight, false);
    }
    if (panel.querySelector(":scope > .panel-resize-handle")) continue;
    const handle = document.createElement("div");
    handle.className = "panel-resize-handle";
    handle.setAttribute("role", "separator");
    handle.setAttribute("aria-orientation", "horizontal");
    handle.setAttribute("aria-label", `Resize ${panelId.replaceAll("-", " ")} panel`);
    handle.tabIndex = 0;
    handle.addEventListener("pointerdown", (event) => startPanelResize(event, panel, handle));
    handle.addEventListener("keydown", (event) => resizePanelFromKeyboard(event, panel));
    panel.appendChild(handle);
  }
}

function setPanelHeight(panel, value, persist = true) {
  const panelId = panel.dataset.panelId || panel.id;
  const height = snapNumber(clampNumber(Number(value), PANEL_HEIGHT_MIN, PANEL_HEIGHT_MAX, PANEL_HEIGHT_MIN));
  panel.style.setProperty("--panel-user-height", `${height}px`);
  panel.classList.add("user-sized");
  if (persist) {
    localStorage.setItem(panelStorageKey(panelId), String(height));
  }
  if (panel.dataset.panelId === "trajectory-preview") {
    window.requestAnimationFrame(updateViewer);
  }
}

function startPanelResize(event, panel, handle) {
  if (event.button !== 0) return;
  event.preventDefault();
  const startY = event.clientY;
  const startHeight = panel.getBoundingClientRect().height;
  document.body.classList.add("resizing-panel");
  handle.classList.add("active");

  const onMove = (moveEvent) => {
    setPanelHeight(panel, startHeight + moveEvent.clientY - startY, false);
  };
  const onUp = (upEvent) => {
    setPanelHeight(panel, startHeight + upEvent.clientY - startY, true);
    document.body.classList.remove("resizing-panel");
    handle.classList.remove("active");
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
  };

  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}

function resizePanelFromKeyboard(event, panel) {
  if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
  event.preventDefault();
  const direction = event.key === "ArrowDown" ? 1 : -1;
  const currentHeight = panel.getBoundingClientRect().height;
  setPanelHeight(panel, currentHeight + direction * PANEL_RESIZE_SNAP_PX, true);
}

function wireSplitters() {
  for (const gutter of document.querySelectorAll("[data-resize-gutter]")) {
    gutter.addEventListener("pointerdown", (event) => startSplitterResize(event, gutter));
    gutter.addEventListener("keydown", (event) => resizeSplitterFromKeyboard(event, gutter));
  }
}

function startSplitterResize(event, gutter) {
  if (event.button !== 0) return;
  event.preventDefault();
  const key = splitKeyForGutter(gutter);
  const container = gutter.closest(".grid, .table-grid");
  const rect = container.getBoundingClientRect();
  document.body.classList.add("resizing-layout");
  gutter.classList.add("active");

  const onMove = (moveEvent) => {
    applySplitSetting(key, rect.right - moveEvent.clientX, false, rect);
  };
  const onUp = (upEvent) => {
    applySplitSetting(key, rect.right - upEvent.clientX, true, rect);
    document.body.classList.remove("resizing-layout");
    gutter.classList.remove("active");
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
  };

  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}

function resizeSplitterFromKeyboard(event, gutter) {
  if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
  event.preventDefault();
  const key = splitKeyForGutter(gutter);
  const direction = event.key === "ArrowLeft" ? 1 : -1;
  const cssVar = key === "sideWidth" ? "--side-column-width" : "--orders-column-width";
  const current = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue(cssVar));
  applySplitSetting(key, current + direction * PANEL_RESIZE_SNAP_PX, true, gutter.closest(".grid, .table-grid").getBoundingClientRect());
}

function applySplitSetting(key, value, persist = true, containerRect = null) {
  const limits = splitLimitsFor(key, containerRect);
  const width = snapNumber(clampNumber(Number(value), limits.min, limits.max, SPLIT_DEFAULTS[key]));
  const cssVar = key === "sideWidth" ? "--side-column-width" : "--orders-column-width";
  document.documentElement.style.setProperty(cssVar, `${width}px`);
  if (persist) {
    localStorage.setItem(splitStorageKey(key), String(width));
  }
  if (key === "sideWidth") {
    window.requestAnimationFrame(updateViewer);
  }
}

function splitLimitsFor(key, containerRect = null) {
  const limits = SPLIT_LIMITS[key];
  const width = containerRect ? containerRect.width : window.innerWidth - 260;
  const reserved = key === "sideWidth" ? 430 : 320;
  return {
    min: limits.min,
    max: Math.max(limits.min, Math.min(limits.max, width - reserved))
  };
}

function splitKeyForGutter(gutter) {
  return gutter.dataset.resizeGutter === "tables" ? "ordersWidth" : "sideWidth";
}

function splitStorageKey(key) {
  return `ppsDashboard.split.${key}`;
}

function panelStorageKey(panelId) {
  return `ppsDashboard.panelHeight.${panelId}`;
}

function snapNumber(value, step = PANEL_RESIZE_SNAP_PX) {
  return Math.round(value / step) * step;
}

function clampNumber(value, min, max, fallback) {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

function addNoiseRow(noiseType = "pink") {
  const type = PROCEDURAL_NOISE_TYPES.some((item) => item.value === noiseType) ? noiseType : "pink";
  state.design.noises = state.design.noises || [];
  const label = noiseTypeLabel(type);
  state.design.noises.push({
    label: `${label} noise`,
    noise_type: type,
    azimuth_deg: 0,
    elevation_deg: 0,
    gain: 1
  });
  renderNoiseTable();
  renderSourceCounts();
}

function noiseTypeLabel(noiseType) {
  return PROCEDURAL_NOISE_TYPES.find((item) => item.value === noiseType)?.label || "Generated";
}

function addAudioRow(renderMode = "preserve") {
  state.design.custom_looming_files = state.design.custom_looming_files || [];
  state.design.custom_looming_files.push({
    label: renderMode === "spatialize" ? "Dry custom tone" : "Already looming audio",
    path: "",
    target_duration_s: 4,
    render_mode: renderMode === "spatialize" ? "spatialize" : "preserve",
    gain: 1
  });
  renderAudioTable();
  renderSourceCounts();
}

function openAudioPicker(renderMode) {
  pendingAudioImportMode = renderMode === "spatialize" ? "spatialize" : "preserve";
  $("audio-file-input").click();
}

async function importAudioFromPicker() {
  const input = $("audio-file-input");
  const file = input.files && input.files[0];
  input.value = "";
  if (!file) return;
  const contentBase64 = await fileToBase64(file);
  const imported = await api("/api/audio/import", {
    method: "POST",
    body: JSON.stringify({
      filename: file.name,
      content_base64: contentBase64,
      use: "looming",
      render_mode: pendingAudioImportMode
    })
  });
  state.design.custom_looming_files = state.design.custom_looming_files || [];
  state.design.custom_looming_files.push(imported.audio);
  renderAudioTable();
  renderSourceCounts();
  showToast("Audio imported locally");
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",").pop() : result);
    });
    reader.addEventListener("error", () => reject(reader.error || new Error("Could not read audio file")));
    reader.readAsDataURL(file);
  });
}

function removeRowFromButton(button) {
  button.closest("tr").remove();
  renderSourceCounts();
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
  $("template-select").addEventListener("change", () => {
    renderProfileSummary();
    loadTemplate().catch(reportError);
  });
  $("render-action").addEventListener("click", () => startRender().catch(reportError));
  $("prepare-action").addEventListener("click", () => prepareSession().catch(reportError));
  $("stress-action").addEventListener("click", () => stressAudio().catch(reportError));
  $("focus-action").addEventListener("click", () => startFocus().catch(reportError));
  $("generated-noise-select").addEventListener("change", () => {
    const selectedNoise = $("generated-noise-select").value;
    if (!selectedNoise) return;
    addNoiseRow(selectedNoise);
    $("generated-noise-select").value = "";
  });
  $("add-audio-spatialize").addEventListener("click", () => addAudioRow("spatialize"));
  $("add-audio-preserve").addEventListener("click", () => addAudioRow("preserve"));
  $("import-audio-spatialize").addEventListener("click", () => openAudioPicker("spatialize"));
  $("import-audio-preserve").addEventListener("click", () => openAudioPicker("preserve"));
  $("audio-file-input").addEventListener("change", () => importAudioFromPicker().catch(reportError));
  $("reset-camera").addEventListener("click", () => {
    const frame = $("trajectory-frame");
    if (frame.contentWindow.resetTrajectoryCamera) frame.contentWindow.resetTrajectoryCamera();
  });
  $("preview-mode").addEventListener("change", () => setPreviewMode($("preview-mode").value));
  for (const id of TRAJECTORY_FIELD_IDS) {
    $(id).addEventListener("input", updateViewer);
  }
  wireSplitters();
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
  window.addEventListener("message", (event) => {
    const frame = $("trajectory-frame");
    if (event.source !== frame.contentWindow) return;
    const data = event.data || {};
    if (data.type !== "pps-trajectory-control-change") return;
    applyTrajectoryControlUpdate(data.controls || {});
  });
  $("trajectory-frame").addEventListener("load", () => {
    viewerReady = true;
    updateViewer();
  });
  document.addEventListener("click", (event) => {
    if (event.target.matches("[data-remove-noise], [data-remove-audio]")) {
      removeRowFromButton(event.target);
    }
  });
  document.addEventListener("change", (event) => {
    if (event.target.matches('[data-field="audio_role"]')) {
      renderSourceCounts();
    }
    if (event.target.matches('.noise-source-card [data-field="noise_type"]')) {
      const card = event.target.closest(".noise-source-card");
      const title = card?.querySelector(".source-card-heading strong");
      if (title) title.textContent = `${noiseTypeLabel(event.target.value)} noise`;
    }
  });
}

function reportError(error) {
  console.error(error);
  showToast(error.message || String(error));
}

loadApiBase();
loadResizableLayoutSettings();
wireEvents();
loadState().catch(reportError);
