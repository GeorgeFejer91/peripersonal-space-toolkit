let state = null;
let viewerReady = false;
const activePolls = new Set();
const CUSTOM_TEMPLATE_ID = "__custom__";
const WORKFLOW_STEPS = ["study", "stimulus", "trials", "baseline", "run", "review"];
const STEP_TARGETS = {
  study: "study",
  stimulus: "stimulus",
  trials: "trials",
  baseline: "baseline",
  run: "run",
  review: "review"
};
const NEXT_STEP = {
  study: "stimulus",
  stimulus: "trials",
  trials: "baseline",
  baseline: "run",
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
  { value: "prestimulus", label: "Instruction snippet" }
];
const STIMULUS_SNIPPET_PLACEMENTS = [
  { value: "before", label: "Before stimulus" },
  { value: "after", label: "After stimulus" }
];
const BASELINE_STRATEGY_NOTES = {
  "": {
    label: "Baseline decision required",
    note: "Choose the baseline family before preparing a custom run."
  },
  none: {
    label: "No baseline trials",
    note: "Use when the profile does not need tactile-only or timing-anchor baseline trials."
  },
  tactile_only: {
    label: "Tactile-only timing anchors",
    note: "Canzoneri-style T0/T6 and several PPS profiles use tactile trials without the looming source, often before/after or at matched timing anchors."
  },
  soa_zero: {
    label: "Tactile at sound onset / SOA 0",
    note: "Use a synchronous timing anchor when the baseline/control is defined by tactile delivery at auditory onset."
  },
  sound_offset: {
    label: "Tactile at sound offset / end",
    note: "Use a late timing anchor when the baseline/control samples tactile detection at the end of the looming window."
  },
  custom: {
    label: "Custom baseline timing values",
    note: "Use for paper-specific tactile-only timings such as pre-sound and post-sound anchors or full SOA-matched baseline sets."
  }
};
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
let pendingBakeRecipe = null;
let activeTrialRowPreviewAudio = null;

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
    // HTTP errors still mean the companion answered; only fetch failures are disconnected.
    setConnectionStatus(true);
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
  renderBaseline();
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
  renderPreloadAssetStatus();
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

function renderPreloadAssetStatus() {
  const badge = $("preload-asset-status");
  if (!badge) return;
  const selectedId = $("template-select").value;
  if (!selectedId || selectedId === CUSTOM_TEMPLATE_ID) {
    badge.hidden = true;
    return;
  }
  const current = state.templates.find((item) => item.template_id === selectedId);
  const status = current?.preload_asset_status || state.preload_inventory || {};
  const value = status.status || "not_indexed";
  const ready = Boolean(status.ready);
  badge.hidden = false;
  badge.textContent = ready
    ? `${status.ready_asset_count || status.asset_count || 0} local assets`
    : value === "recipe_only"
      ? "recipe only"
      : value.replace(/_/g, " ");
  badge.className = `status-label ${ready ? "ready" : value === "recipe_only" ? "" : "required"}`;
  badge.title = status.message || "";
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
  renderBakePanel();
  renderNoiseTable();
  renderAudioTable();
  refreshAssemblyTargetOptions();
  renderSourceCounts();
  renderStimulusFeedback();
}

function renderGeneratedNoiseSelect() {
  const select = $("generated-noise-select");
  const current = select.value;
  select.innerHTML = '<option value="">Choose noise to bake...</option>';
  for (const item of PROCEDURAL_NOISE_TYPES) {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = item.label;
    select.appendChild(option);
  }
  select.value = PROCEDURAL_NOISE_TYPES.some((item) => item.value === current) ? current : "";
}

function renderBakePanel() {
  const status = $("bake-status");
  const button = $("bake-stimulus");
  if (!status || !button) return;
  if (!pendingBakeRecipe) {
    status.textContent = "No source staged";
    status.className = "status-label required";
    button.disabled = true;
    return;
  }
  const label = pendingBakeRecipe.label || pendingBakeRecipe.audio?.label || noiseTypeLabel(pendingBakeRecipe.noise_type);
  $("bake-label").value = label || "";
  $("bake-gain").value = Number(pendingBakeRecipe.gain || pendingBakeRecipe.audio?.gain || 1);
  const kind = pendingBakeRecipe.kind === "imported_audio" ? audioRoleTitle(pendingBakeRecipe.render_mode) : `${noiseTypeLabel(pendingBakeRecipe.noise_type)} noise`;
  status.textContent = `Staged: ${kind}`;
  status.className = "status-label ready";
  button.disabled = false;
}

function renderNoiseTable() {
  const list = $("noise-list");
  list.innerHTML = "";
  for (const noise of state.design.noises || []) {
    const selectedNoise = String(noise.noise_type || "pink").toLowerCase();
    const wav = renderedWavForLabel(noise.label || `${noiseTypeLabel(selectedNoise)} noise`);
    const card = document.createElement("div");
    card.className = "source-card noise-source-card";
    card.innerHTML = `
      <div class="source-card-heading">
        <strong>${escapeHtml(noiseTypeLabel(selectedNoise))} noise</strong>
        <div class="source-card-actions">
          ${sourceFolderAction(wav?.path)}
          <button type="button" data-remove-noise>Remove</button>
        </div>
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
  const list = $("audio-list");
  list.innerHTML = "";
  const customFiles = state.design.custom_looming_files || [];
  const snippets = state.design.prestimulus_files || [];
  const rows = [
    ...customFiles.map((item) => ({
      ...item,
      audio_role: item.render_mode || "preserve",
    })),
    ...snippets.map((item) => ({
      ...item,
      audio_role: "prestimulus",
    }))
  ];
  for (const audio of rows) {
    const role = String(audio.audio_role || audio.use || audio.render_mode || "preserve").toLowerCase();
    const placement = normalizeSnippetPlacement(audio.placement);
    const targetSource = audio.target_source_label || "";
    const phase = audio.phase || "";
    const card = document.createElement("div");
    card.className = "source-card audio-source-card";
    card.dataset.audioRole = role;
    card.innerHTML = `
      <div class="source-card-heading">
        <strong>${escapeHtml(audioRoleTitle(role))}</strong>
        <div class="source-card-actions">
          ${sourceFolderAction(audio.path)}
          <button type="button" data-remove-audio>Remove</button>
        </div>
      </div>
      <div class="source-card-fields audio-source-fields">
        <div class="field-row">
          <label>Source handling</label>
          <select data-field="audio_role">
            ${IMPORTED_AUDIO_HANDLING.map((item) => `<option value="${item.value}" ${item.value === role ? "selected" : ""}>${item.label}</option>`).join("")}
          </select>
        </div>
        <div class="field-row">
          <label>Label</label>
          <input data-field="label" value="${escapeAttr(audio.label || "")}">
        </div>
        <div class="field-row audio-path-field">
          <label>Local path</label>
          <input data-field="path" value="${escapeAttr(audio.path || "")}">
        </div>
        <div class="field-row assembly-only">
          <label>Placement</label>
          <select data-field="placement">
            ${STIMULUS_SNIPPET_PLACEMENTS.map((item) => `<option value="${item.value}" ${item.value === placement ? "selected" : ""}>${item.label}</option>`).join("")}
          </select>
        </div>
        <div class="field-row assembly-only">
          <label>Attach to</label>
          <select data-field="target_source_label" data-selected-target="${escapeAttr(targetSource)}">
            ${stimulusTargetOptionsFromDesign(targetSource)}
          </select>
        </div>
        <div class="field-row assembly-only">
          <label>Phase</label>
          <select data-field="phase">
            ${stimulusPhaseOptions(phase)}
          </select>
        </div>
        <div class="field-row assembly-only">
          <label>Gap s</label>
          <input data-field="gap_s" type="number" min="0" step="0.05" value="${Number(audio.gap_s || 0)}">
        </div>
        <div class="field-row">
          <label>Target s</label>
          <input data-field="target_duration_s" type="number" min="0.1" step="0.1" value="${Number(audio.target_duration_s || 4)}">
        </div>
        <div class="field-row">
          <label>Gain</label>
          <input data-field="gain" type="number" min="0.01" step="0.05" value="${Number(audio.gain || 1)}">
        </div>
      </div>
    `;
    list.appendChild(card);
  }
}

function sourceFolderAction(path) {
  if (!path) return "";
  return `<button type="button" class="source-folder-link" data-open-folder="${escapeAttr(path)}">Open Folder</button>`;
}

function renderedWavForLabel(label) {
  const target = normalizeSourceKey(label);
  if (!target) return null;
  return (state.render?.wavs || []).find((wav) => {
    const keys = [
      wav.label,
      wav.path,
      String(wav.path || "").split(/[\\/]/).pop(),
      String(wav.path || "").split(/[\\/]/).pop()?.replace(/^looming_/i, "").replace(/\.[^.]+$/, ""),
    ];
    return keys.some((key) => normalizeSourceKey(key) === target);
  }) || null;
}

function normalizeSourceKey(value) {
  return String(value || "")
    .replace(/^looming[_\s-]*/i, "")
    .replace(/\.[^.]+$/, "")
    .replace(/[_-]+/g, " ")
    .trim()
    .toLowerCase();
}

function renderSourceCounts() {
  const generated = $("noise-list").querySelectorAll(".noise-source-card").length;
  const audioCards = [...$("audio-list").querySelectorAll(".audio-source-card")];
  const imported = audioCards.filter((card) => card.querySelector('[data-field="audio_role"]')?.value !== "prestimulus").length;
  const prestimulus = audioCards.filter((card) => card.querySelector('[data-field="audio_role"]')?.value === "prestimulus").length;
  const stimulusSources = generated + imported;
  const sourceLabel = `${stimulusSources} baked source${stimulusSources === 1 ? "" : "s"}`;
  const snippetLabel = prestimulus ? ` + ${prestimulus} snippet${prestimulus === 1 ? "" : "s"}` : "";
  $("source-counts").textContent = `${sourceLabel}${snippetLabel}`;
  $("source-counts").className = `status-label ${stimulusSources ? "ready" : "required"}`;
}

function renderStimulusFeedback() {
  const status = $("stimulus-render-status");
  const summary = $("stimulus-feedback-summary");
  const list = $("stimulus-feedback-list");
  if (!status || !summary || !list) return;

  const render = state.render || {};
  const wavCount = Number(render.wav_count || 0);
  status.textContent = wavCount ? `${wavCount} local WAV${wavCount === 1 ? "" : "s"}` : "waiting";
  status.className = `status-label ${wavCount ? "ready" : "required"}`;

  const rows = [
    ["Baked WAVs", wavCount ? `${wavCount} ready` : "none"],
    ["Render engine", render.render_engine || "not run"],
    ["Output folder", render.render_dir ? "available" : "pending"]
  ];
  summary.innerHTML = rows
    .map(([label, value]) => `<div class="status-row"><strong>${label}</strong><span>${escapeHtml(value)}</span></div>`)
    .join("");

  const jobs = (state.jobs || []).filter((job) => ["stimulus_bake", "render"].includes(job.kind)).slice(0, 4);
  list.innerHTML = jobs.length
    ? jobs.map(renderJob).join("")
    : `<div class="summary-text">No stimulus jobs yet.</div>`;
}

function stimulusTargetOptionsFromDesign(selected = "") {
  const options = stimulusSourceOptionsFromDesign();
  return renderOptionList(options, selected);
}

function stimulusSourceOptionsFromDesign() {
  const options = [{ value: "", label: "Every stimulus source" }];
  const seen = new Set([""]);
  for (const noise of state.design.noises || []) {
    addStimulusSourceOption(options, seen, noise.label || `${noiseTypeLabel(noise.noise_type)} noise`);
  }
  for (const audio of state.design.custom_looming_files || []) {
    addStimulusSourceOption(options, seen, audio.label || audioRoleTitle(audio.render_mode || "preserve"));
  }
  return options;
}

function stimulusSourceOptionsFromDom() {
  const options = [{ value: "", label: "Every stimulus source" }];
  const seen = new Set([""]);
  for (const card of $("noise-list").querySelectorAll(".noise-source-card")) {
    const label = card.querySelector('[data-field="label"]')?.value || "Generated noise";
    addStimulusSourceOption(options, seen, label);
  }
  for (const card of $("audio-list").querySelectorAll(".audio-source-card")) {
    const role = card.querySelector('[data-field="audio_role"]')?.value;
    if (role === "prestimulus") continue;
    const label = card.querySelector('[data-field="label"]')?.value || audioRoleTitle(role);
    addStimulusSourceOption(options, seen, label);
  }
  return options;
}

function addStimulusSourceOption(options, seen, label) {
  const value = String(label || "").trim();
  if (!value || seen.has(value)) return;
  seen.add(value);
  options.push({ value, label: value });
}

function stimulusPhaseOptions(selected = "") {
  const phases = state.design.protocol?.respiratory_phases || ["Inhale", "Exhale"];
  const options = [{ value: "", label: "Any phase" }];
  const seen = new Set([""]);
  for (const phase of phases) {
    const value = String(phase || "").trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    options.push({ value, label: value });
  }
  return renderOptionList(options, selected);
}

function renderOptionList(options, selected = "") {
  const selectedValue = String(selected || "");
  return options
    .map((item) => `<option value="${escapeAttr(item.value)}" ${item.value === selectedValue ? "selected" : ""}>${escapeHtml(item.label)}</option>`)
    .join("");
}

function refreshAssemblyTargetOptions() {
  const options = stimulusSourceOptionsFromDom();
  for (const select of document.querySelectorAll('[data-field="target_source_label"]')) {
    const selected = select.value || select.dataset.selectedTarget || "";
    select.innerHTML = renderOptionList(options, selected);
    select.value = options.some((item) => item.value === selected) ? selected : "";
    select.dataset.selectedTarget = select.value;
  }
}

function normalizeSnippetPlacement(value) {
  return value === "after" ? "after" : "before";
}

function renderTrials() {
  const protocol = state.design.protocol || {};
  $("repetitions").value = protocol.repetitions_per_condition ?? 1;
  $("blocks").value = protocol.blocks ?? 1;
  $("catch-percent").value = protocol.catch_trial_percentage ?? 0;
  $("soa-values").value = formatList(protocol.soa_values_ms);
  renderTrialStrips();

  const summary = $("protocol-summary");
  summary.innerHTML = "";
  for (const [key, value] of Object.entries(state.protocol_summary || {})) {
    const item = document.createElement("div");
    item.className = "summary-item";
    item.innerHTML = `<span>${humanize(key)}</span><strong>${value}</strong>`;
    summary.appendChild(item);
  }
}

function renderBaseline() {
  const protocol = state.design.protocol || {};
  const savedStrategy = protocol.include_baseline_trials === false
    ? "none"
    : (protocol.baseline_strategy || "tactile_only");
  $("baseline-strategy").value = savedStrategy;
  $("baseline-percent").value = savedStrategy === "none" ? 0 : (protocol.baseline_trial_percentage ?? 0);
  $("baseline-soa-values").value = formatList(protocol.baseline_soa_values_ms || []);
  updateBaselineDecision();
}

function currentBaselineStrategy() {
  return $("baseline-strategy").value || "";
}

function derivedBaselineTimingsMs(strategy = currentBaselineStrategy()) {
  if (strategy === "none" || !strategy) return [];
  if (strategy === "soa_zero") return [0];
  if (strategy === "sound_offset") {
    const controls = currentTrajectoryControls();
    return [Math.round((controls.start_hold_s + controls.movement_duration_s + controls.end_hold_s) * 1000)];
  }
  const custom = parseIntegerList($("baseline-soa-values").value);
  if (custom.length) return custom;
  return parseIntegerList($("soa-values").value);
}

function eventSequenceAudioCountPerBlock() {
  const soaCount = parseIntegerList($("soa-values").value).length;
  const repetitions = Math.max(1, Math.round(numberValue("repetitions", 1)));
  const fallbackSourceCount = Math.max(1, stimulusSourceDetailsFromDom().length);
  let total = 0;
  const rows = [...$("filmstrip-list").querySelectorAll(".filmstrip-row")];
  if (!rows.length) return fallbackSourceCount * soaCount * repetitions;
  for (const row of rows) {
    const slot = row.querySelector('.filmstrip-element[data-element-kind="looming_stimulus"]');
    const selected = slot ? slot.querySelectorAll('[data-element-field="source_labels"] option:checked').length : 0;
    total += Math.max(1, selected || fallbackSourceCount) * soaCount * repetitions;
  }
  return total;
}

function baselineCountEstimate() {
  const strategy = currentBaselineStrategy();
  const blocks = Math.max(1, Math.round(numberValue("blocks", 1)));
  if (!strategy || strategy === "none") {
    return { strategy, timings: [], perBlock: 0, total: 0, actualPercent: 0, audioPerBlock: eventSequenceAudioCountPerBlock() };
  }
  const timings = derivedBaselineTimingsMs(strategy);
  const repetitions = Math.max(1, Math.round(numberValue("repetitions", 1)));
  const tactileSiteCount = Math.max(1, (state.design.protocol?.tactile_sites || ["hand"]).length);
  const rowCount = Math.max(1, $("filmstrip-list").querySelectorAll(".filmstrip-row").length);
  const candidates = Math.max(0, rowCount * repetitions * tactileSiteCount * timings.length);
  const audioCount = Math.max(0, eventSequenceAudioCountPerBlock());
  const percent = Math.max(0, Math.min(99, numberValue("baseline-percent", 0)));
  const perBlock = percent > 0 && audioCount > 0
    ? Math.max(1, Math.ceil(audioCount * percent / (100 - percent)))
    : candidates;
  const denominator = Math.max(1, audioCount + perBlock);
  return {
    strategy,
    timings,
    perBlock,
    total: perBlock * blocks,
    actualPercent: Math.round((1000 * perBlock / denominator)) / 10,
    audioPerBlock: audioCount,
  };
}

function estimatedTrialSeconds() {
  const controls = currentTrajectoryControls();
  const soundWindow = controls.start_hold_s + controls.movement_duration_s + controls.end_hold_s;
  const firstStrip = state.design.protocol?.trial_strips?.[0];
  const fixedLabels = (firstStrip?.elements || [])
    .filter((element) => element.kind === "fixed_audio")
    .map((element) => element.source_label || element.label)
    .filter(Boolean);
  const fixedSeconds = fixedLabels.reduce((total, label) => {
    const clip = (state.design.prestimulus_files || []).find((item) => item.label === label);
    return total + Number(clip?.target_duration_s || 0);
  }, 0);
  return Math.max(0.1, fixedSeconds + soundWindow);
}

function updateBaselineDecision() {
  const strategy = currentBaselineStrategy();
  const status = $("baseline-status");
  const valid = strategy && (strategy === "none" || numberValue("baseline-percent", 0) > 0);
  status.textContent = valid ? "ready" : "required";
  status.className = `status-label ${valid ? "ready" : "required"}`;

  const note = BASELINE_STRATEGY_NOTES[strategy] || BASELINE_STRATEGY_NOTES[""];
  $("baseline-literature").innerHTML = `<strong>${escapeHtml(note.label)}</strong><span>${escapeHtml(note.note)}</span>`;

  const timingField = $("baseline-soa-values");
  const customTiming = strategy === "custom" || strategy === "tactile_only";
  timingField.disabled = !customTiming;
  timingField.closest(".field-row").classList.toggle("muted-control", !customTiming);
  if (strategy === "none") $("baseline-percent").value = 0;

  const estimate = baselineCountEstimate();
  const summary = $("baseline-summary");
  const blocks = Math.max(1, Math.round(numberValue("blocks", 1)));
  const catchPercent = Math.max(0, Math.min(99, numberValue("catch-percent", 0)));
  const catchPerBlock = estimate.audioPerBlock > 0 && catchPercent > 0
    ? Math.ceil(estimate.audioPerBlock * catchPercent / (100 - catchPercent))
    : 0;
  const liveTrials = (estimate.audioPerBlock + estimate.perBlock + catchPerBlock) * blocks;
  const participantMinutes = Math.round((liveTrials * estimatedTrialSeconds() / 60) * 10) / 10;
  summary.innerHTML = "";
  const rows = {
    timing_values_ms: estimate.timings.length ? estimate.timings.join(", ") : "none",
    baseline_trials_per_block: estimate.perBlock,
    baseline_trials_total: estimate.total,
    actual_baseline_percent: `${estimate.actualPercent}%`,
    estimated_participant_minutes: participantMinutes,
  };
  for (const [key, value] of Object.entries(rows)) {
    const item = document.createElement("div");
    item.className = "summary-item";
    item.innerHTML = `<span>${humanize(key)}</span><strong>${escapeHtml(String(value))}</strong>`;
    summary.appendChild(item);
  }
}

function renderTrialStrips() {
  const list = $("filmstrip-list");
  if (!list) return;
  const strips = state.design.protocol?.trial_strips || [];
  list.innerHTML = "";
  if (!strips.length) {
    list.innerHTML = `<div class="filmstrip-empty">No event sequences.</div>`;
    return;
  }
  strips.forEach((strip, index) => list.appendChild(renderTrialStripRow(strip, index)));
  updateFilmstripCounts();
}

function renderTrialStripRow(strip, index) {
  const row = document.createElement("div");
  row.className = "filmstrip-row";
  row.dataset.stripIndex = String(index);
  row.innerHTML = `
    <div class="filmstrip-row-header">
      <button type="button" class="filmstrip-preview-button" data-preview-strip="${index}" title="Prelisten event sequence" aria-label="Prelisten event sequence">&#9658;</button>
      <div class="field-row">
        <label>Event label</label>
        <input data-strip-field="label" value="${escapeAttr(strip.label || `Event ${index + 1}`)}">
      </div>
      <div class="filmstrip-row-actions">
        <span class="filmstrip-count" data-strip-count></span>
        <button type="button" data-strip-move="up">Up</button>
        <button type="button" data-strip-move="down">Down</button>
        <button type="button" data-add-strip-element="fixed_audio">Add Clip</button>
        <button type="button" data-add-strip-element="looming_stimulus">Add Looming Stimulus</button>
        <button type="button" data-remove-strip>Remove Event</button>
      </div>
    </div>
    <div class="filmstrip-sequence"></div>
  `;
  const sequence = row.querySelector(".filmstrip-sequence");
  for (const [elementIndex, element] of (strip.elements || []).entries()) {
    sequence.appendChild(renderTrialStripElement(element, elementIndex));
  }
  return row;
}

function renderTrialStripElement(element, index) {
  const sourceType = element.kind === "fixed_audio" ? "fixed_audio" : "looming_stimulus";
  const card = document.createElement("div");
  card.className = `filmstrip-element ${sourceType.replace("_", "-")} ${filmstripNoiseClass(element)}`;
  card.dataset.elementIndex = String(index);
  card.dataset.elementKind = sourceType;
  const title = sourceType === "fixed_audio" ? "Fixed audio clip" : "Looming Stimulus";
  const sourceControl = sourceType === "fixed_audio"
    ? `<select data-element-field="source_label">${fixedAudioOptions(element.source_label || "")}</select>`
    : `<select data-element-field="source_labels" multiple>${loomingSourceOptions(element.source_labels || [])}</select>`;
  card.innerHTML = `
    <div class="filmstrip-element-heading">
      <span>${title}</span>
      <button type="button" data-remove-strip-element>Remove</button>
    </div>
    <div class="field-row">
      <label>Label</label>
      <input data-element-field="label" value="${escapeAttr(element.label || title)}">
    </div>
    <div class="field-row">
      <label>Source</label>
      ${sourceControl}
    </div>
    <div class="field-row inline-check">
      <input data-element-field="randomized" type="checkbox" ${element.randomized ? "checked" : ""}>
      <label>Randomized</label>
    </div>
  `;
  return card;
}

function filmstripNoiseClass(element) {
  const labels = element.source_labels || [];
  const firstLabel = labels[0] || element.source_label || "";
  const source = stimulusSourceDetailsFromDom().find((item) => item.label === firstLabel);
  return source?.noise_type ? `noise-${String(source.noise_type).toLowerCase()}` : "";
}

function fixedAudioOptions(selected = "") {
  const options = [{ value: "", label: "Select clip" }];
  for (const item of fixedAudioSourceOptions()) options.push(item);
  return renderOptionList(options, selected);
}

function loomingSourceOptions(selected = []) {
  const selectedSet = new Set(selected || []);
  return stimulusSourceDetailsFromDom()
    .map((item) => `<option value="${escapeAttr(item.label)}" ${selectedSet.has(item.label) ? "selected" : ""}>${escapeHtml(item.label)}</option>`)
    .join("");
}

function fixedAudioSourceOptions() {
  const options = [];
  for (const card of $("audio-list").querySelectorAll(".audio-source-card")) {
    const role = card.querySelector('[data-field="audio_role"]')?.value;
    if (role !== "prestimulus") continue;
    const label = card.querySelector('[data-field="label"]')?.value.trim();
    if (label) options.push({ value: label, label });
  }
  return options;
}

function stimulusSourceDetailsFromDom() {
  const sources = [];
  for (const card of $("noise-list").querySelectorAll(".noise-source-card")) {
    const label = card.querySelector('[data-field="label"]')?.value.trim() || "Generated noise";
    sources.push({
      label,
      noise_type: card.querySelector('[data-field="noise_type"]')?.value || "pink",
    });
  }
  for (const card of $("audio-list").querySelectorAll(".audio-source-card")) {
    const role = card.querySelector('[data-field="audio_role"]')?.value;
    if (role === "prestimulus") continue;
    const label = card.querySelector('[data-field="label"]')?.value.trim() || audioRoleTitle(role);
    sources.push({ label, noise_type: "custom_audio" });
  }
  return sources;
}

function collectTrialStrips() {
  const strips = [];
  for (const [stripIndex, row] of [...$("filmstrip-list").querySelectorAll(".filmstrip-row")].entries()) {
    const label = row.querySelector('[data-strip-field="label"]')?.value.trim() || `Row ${stripIndex + 1}`;
    const elements = [];
    for (const [elementIndex, card] of [...row.querySelectorAll(".filmstrip-element")].entries()) {
      const kind = card.dataset.elementKind === "fixed_audio" ? "fixed_audio" : "looming_stimulus";
      const item = {
        element_id: `row-${stripIndex + 1}-element-${elementIndex + 1}`,
        kind,
        label: card.querySelector('[data-element-field="label"]')?.value.trim() || (kind === "fixed_audio" ? "Fixed audio clip" : "Looming Stimulus"),
        source_label: "",
        source_labels: [],
        randomized: Boolean(card.querySelector('[data-element-field="randomized"]')?.checked),
      };
      if (kind === "fixed_audio") {
        item.source_label = card.querySelector('[data-element-field="source_label"]')?.value || "";
      } else {
        item.source_labels = [...card.querySelectorAll('[data-element-field="source_labels"] option:checked')].map((option) => option.value);
      }
      elements.push(item);
    }
    strips.push({
      strip_id: `strip-${stripIndex + 1}`,
      label,
      elements,
    });
  }
  return strips;
}

function updateFilmstripCounts() {
  const soaCount = parseIntegerList($("soa-values").value).length;
  const repetitions = Math.max(1, Math.round(numberValue("repetitions", 1)));
  for (const row of $("filmstrip-list").querySelectorAll(".filmstrip-row")) {
    const count = row.querySelector("[data-strip-count]");
    const slot = row.querySelector('.filmstrip-element[data-element-kind="looming_stimulus"]');
    const selected = slot ? slot.querySelectorAll('[data-element-field="source_labels"] option:checked').length : 0;
    const sourceCount = selected || stimulusSourceDetailsFromDom().length;
    const total = sourceCount * Math.max(soaCount, 0) * repetitions;
    count.textContent = `${sourceCount} stimuli x ${soaCount} SOAs x ${repetitions} reps = ${total} events/block`;
  }
  updateBaselineDecision();
}

async function previewFilmstripRow(button) {
  const row = button.closest(".filmstrip-row");
  if (!row) return;
  state.design.protocol = state.design.protocol || {};
  state.design.protocol.trial_strips = collectTrialStrips();
  const payload = collectPayload();
  payload.strip_index = Number(row.dataset.stripIndex || 0);
  button.disabled = true;
  button.classList.add("playing");
  let started = false;
  try {
    const preview = await api("/api/trials/preview-row", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    if (activeTrialRowPreviewAudio) {
      activeTrialRowPreviewAudio.pause();
      activeTrialRowPreviewAudio = null;
    }
    const audio = new Audio(apiUrl(`${preview.url}?v=${Date.now()}`));
    activeTrialRowPreviewAudio = audio;
    audio.addEventListener("ended", () => button.classList.remove("playing"), { once: true });
    audio.addEventListener("pause", () => button.classList.remove("playing"), { once: true });
    await audio.play();
    started = true;
    showToast(`Preview: ${preview.sequence.join(" | ")}`);
  } catch (error) {
    button.classList.remove("playing");
    throw error;
  } finally {
    if (!started) button.classList.remove("playing");
    button.disabled = false;
  }
}

function setTrialStrips(strips) {
  state.design.protocol = state.design.protocol || {};
  state.design.protocol.trial_strips = strips;
  renderTrialStrips();
}

function addFilmstripRow() {
  const strips = collectTrialStrips();
  strips.push({
    strip_id: `strip-${strips.length + 1}`,
    label: `Event ${strips.length + 1}`,
    elements: [defaultFilmstripElement("looming_stimulus")],
  });
  setTrialStrips(strips);
}

function defaultFilmstripElement(kind) {
  if (kind === "fixed_audio") {
    const firstClip = fixedAudioSourceOptions()[0]?.value || "";
    return {
      element_id: "",
      kind: "fixed_audio",
      label: firstClip || "Fixed audio clip",
      source_label: firstClip,
      source_labels: [],
      randomized: false,
    };
  }
  return {
    element_id: "",
    kind: "looming_stimulus",
    label: "Looming Stimulus",
    source_label: "",
    source_labels: [],
    randomized: true,
  };
}

function addFilmstripElement(button, kind) {
  const row = button.closest(".filmstrip-row");
  const stripIndex = Number(row?.dataset.stripIndex || -1);
  const strips = collectTrialStrips();
  if (!strips[stripIndex]) return;
  strips[stripIndex].elements.push(defaultFilmstripElement(kind));
  setTrialStrips(strips);
}

function removeFilmstripRow(button) {
  const row = button.closest(".filmstrip-row");
  const stripIndex = Number(row?.dataset.stripIndex || -1);
  const strips = collectTrialStrips();
  if (stripIndex < 0) return;
  strips.splice(stripIndex, 1);
  setTrialStrips(strips);
}

function moveFilmstripRow(button, direction) {
  const row = button.closest(".filmstrip-row");
  const stripIndex = Number(row?.dataset.stripIndex || -1);
  const targetIndex = direction === "up" ? stripIndex - 1 : stripIndex + 1;
  const strips = collectTrialStrips();
  if (!strips[stripIndex] || !strips[targetIndex]) return;
  const [item] = strips.splice(stripIndex, 1);
  strips.splice(targetIndex, 0, item);
  setTrialStrips(strips);
}

function removeFilmstripElement(button) {
  const row = button.closest(".filmstrip-row");
  const card = button.closest(".filmstrip-element");
  const stripIndex = Number(row?.dataset.stripIndex || -1);
  const elementIndex = Number(card?.dataset.elementIndex || -1);
  const strips = collectTrialStrips();
  if (!strips[stripIndex] || elementIndex < 0) return;
  strips[stripIndex].elements.splice(elementIndex, 1);
  setTrialStrips(strips);
}

function syncFilmstripSourceOptions() {
  for (const select of document.querySelectorAll('[data-element-field="source_label"]')) {
    const selected = select.value;
    select.innerHTML = fixedAudioOptions(selected);
    select.value = [...select.options].some((option) => option.value === selected) ? selected : "";
  }
  for (const select of document.querySelectorAll('[data-element-field="source_labels"]')) {
    const selected = [...select.selectedOptions].map((option) => option.value);
    select.innerHTML = loomingSourceOptions(selected);
  }
  updateFilmstripCounts();
}

function renderRun() {
  const isCustom = Boolean(state.custom_workflow && state.custom_workflow.is_custom);
  $("participants").value = state.design.protocol?.participants ?? 1;
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
  fillTable("trial-table", trialRows, ["block", "trial", "type", "phase", "soa_ms", "space_cm", "tactile_site", "sequence"]);

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
  const trialStrips = collectTrialStrips();
  const legacySpatial = design.protocol?.spatial_values_cm?.length
    ? design.protocol.spatial_values_cm
    : [numberValue("end-distance", 10)];
  const baselineStrategy = currentBaselineStrategy();
  const baselineTimings = baselineStrategy === "tactile_only" || baselineStrategy === "custom"
    ? parseIntegerList($("baseline-soa-values").value)
    : [];
  design.protocol = {
    ...(design.protocol || {}),
    repetitions_per_condition: Math.max(1, Math.round(numberValue("repetitions", 1))),
    soa_values_ms: parseIntegerList($("soa-values").value),
    spatial_values_cm: legacySpatial,
    pair_spatial_values_with_soas: false,
    catch_trial_percentage: numberValue("catch-percent", 0),
    include_baseline_trials: Boolean(baselineStrategy && baselineStrategy !== "none"),
    baseline_strategy: baselineStrategy,
    baseline_trial_percentage: baselineStrategy === "none" ? 0 : numberValue("baseline-percent", 0),
    baseline_soa_values_ms: baselineTimings,
    blocks: Math.max(1, Math.round(numberValue("blocks", 1))),
    participants: Math.max(1, Math.round(numberValue("participants", 1))),
    trial_strips: trialStrips
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
  for (const card of $("audio-list").querySelectorAll(".audio-source-card")) {
    const field = (name) => card.querySelector(`[data-field="${name}"]`);
    const role = field("audio_role").value;
    const item = {
      label: field("label").value.trim() || "Audio file",
      path: field("path").value.trim(),
      target_duration_s: Number(field("target_duration_s").value || 4),
      render_mode: role === "spatialize" ? "spatialize" : "preserve",
      gain: Number(field("gain").value || 1),
      placement: normalizeSnippetPlacement(field("placement")?.value),
      target_source_label: field("target_source_label")?.value.trim() || "",
      phase: field("phase")?.value.trim() || "",
      gap_s: Math.max(0, Number(field("gap_s")?.value || 0))
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

async function startBakeStimulus() {
  const recipe = collectBakeRecipe();
  if (!recipe) {
    showToast("Choose a noise or local audio source first");
    return;
  }
  const payload = collectPayload();
  payload.bake_recipe = recipe;
  const job = await api("/api/stimulus/bake", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  showToast("Stimulus bake started");
  pollJob(job.job_id);
  await loadState();
}

async function openLocalFolder(path) {
  if (!path) return;
  await api("/api/local/open-folder", {
    method: "POST",
    body: JSON.stringify({ path })
  });
  showToast("Opened local folder");
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
      if (job.status === "succeeded" && job.kind === "stimulus_bake") {
        pendingBakeRecipe = null;
        $("generated-noise-select").value = "";
        renderBakePanel();
      }
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

function callTrajectoryViewer(method, ...args) {
  const frame = $("trajectory-frame");
  const fn = frame.contentWindow?.[method];
  if (typeof fn === "function") fn(...args);
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
  const container = gutter.closest(".grid, .table-grid, .stimulus-grid, .run-grid");
  if (!container) return;
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
  const container = gutter.closest(".grid, .table-grid, .stimulus-grid, .run-grid");
  if (!container) return;
  applySplitSetting(key, current + direction * PANEL_RESIZE_SNAP_PX, true, container.getBoundingClientRect());
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

function stageGeneratedNoise(noiseType = "pink") {
  const type = PROCEDURAL_NOISE_TYPES.some((item) => item.value === noiseType) ? noiseType : "pink";
  const label = `${noiseTypeLabel(type)} noise`;
  pendingBakeRecipe = {
    kind: "generated_noise",
    noise_type: type,
    label,
    gain: Number($("bake-gain")?.value || 1)
  };
  $("bake-label").value = label;
  renderBakePanel();
  showToast(`${noiseTypeLabel(type)} noise staged`);
}

function stageImportedAudioForBake(audio, renderMode) {
  const mode = renderMode === "spatialize" ? "spatialize" : "preserve";
  pendingBakeRecipe = {
    kind: "imported_audio",
    render_mode: mode,
    label: audio.label || (mode === "spatialize" ? "Dry custom tone" : "Already looming / control"),
    audio,
    gain: Number(audio.gain || 1)
  };
  $("bake-label").value = pendingBakeRecipe.label;
  renderBakePanel();
}

function collectBakeRecipe() {
  if (!pendingBakeRecipe) return null;
  const recipe = clone(pendingBakeRecipe);
  recipe.label = $("bake-label").value.trim() || recipe.label || "Baked stimulus";
  recipe.gain = Math.max(0.01, Number($("bake-gain").value || recipe.gain || 1));
  if (recipe.audio) {
    recipe.audio = {
      ...recipe.audio,
      label: recipe.label,
      gain: recipe.gain
    };
  }
  return recipe;
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
  refreshAssemblyTargetOptions();
  syncFilmstripSourceOptions();
  renderSourceCounts();
}

function noiseTypeLabel(noiseType) {
  return PROCEDURAL_NOISE_TYPES.find((item) => item.value === noiseType)?.label || "Generated";
}

function audioRoleTitle(role) {
  if (role === "spatialize") return "Dry custom tone";
  if (role === "prestimulus") return "Instruction snippet";
  return "Already looming / control";
}

function openAudioPicker(renderMode) {
  pendingAudioImportMode = ["spatialize", "prestimulus"].includes(renderMode) ? renderMode : "preserve";
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
      use: pendingAudioImportMode === "prestimulus" ? "prestimulus" : "looming",
      render_mode: pendingAudioImportMode === "spatialize" ? "spatialize" : "preserve",
      placement: "before",
      target_source_label: "",
      phase: "",
      gap_s: 0
    })
  });
  if (pendingAudioImportMode === "prestimulus") {
    state.design.prestimulus_files = state.design.prestimulus_files || [];
    state.design.prestimulus_files.push({ ...imported.audio, placement: "before", target_source_label: "", phase: "", gap_s: 0 });
    renderAudioTable();
    refreshAssemblyTargetOptions();
    syncFilmstripSourceOptions();
    renderSourceCounts();
    showToast("Instruction snippet imported locally");
  } else {
    stageImportedAudioForBake(imported.audio, pendingAudioImportMode);
    showToast("Audio staged for baking");
  }
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

function removeSourceCard(button) {
  const card = button.closest(".source-card");
  if (card) card.remove();
  refreshAssemblyTargetOptions();
  syncFilmstripSourceOptions();
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
  $("bake-stimulus").addEventListener("click", () => startBakeStimulus().catch(reportError));
  $("prepare-action").addEventListener("click", () => prepareSession().catch(reportError));
  $("stress-action").addEventListener("click", () => stressAudio().catch(reportError));
  $("focus-action").addEventListener("click", () => startFocus().catch(reportError));
  $("generated-noise-select").addEventListener("change", () => {
    const selectedNoise = $("generated-noise-select").value;
    if (!selectedNoise) return;
    stageGeneratedNoise(selectedNoise);
  });
  $("bake-label").addEventListener("input", () => {
    if (pendingBakeRecipe) pendingBakeRecipe.label = $("bake-label").value.trim();
  });
  $("bake-gain").addEventListener("input", () => {
    if (pendingBakeRecipe) pendingBakeRecipe.gain = Math.max(0.01, Number($("bake-gain").value || 1));
  });
  $("import-audio-spatialize").addEventListener("click", () => openAudioPicker("spatialize"));
  $("import-audio-preserve").addEventListener("click", () => openAudioPicker("preserve"));
  $("import-audio-prestimulus").addEventListener("click", () => openAudioPicker("prestimulus"));
  $("audio-file-input").addEventListener("change", () => importAudioFromPicker().catch(reportError));
  $("add-strip-row").addEventListener("click", () => addFilmstripRow());
  $("soa-values").addEventListener("input", updateFilmstripCounts);
  $("repetitions").addEventListener("input", updateFilmstripCounts);
  $("blocks").addEventListener("input", updateBaselineDecision);
  $("baseline-strategy").addEventListener("change", updateBaselineDecision);
  $("baseline-percent").addEventListener("input", updateBaselineDecision);
  $("baseline-soa-values").addEventListener("input", updateBaselineDecision);
  $("reset-camera").addEventListener("click", () => {
    callTrajectoryViewer("resetTrajectoryCamera");
  });
  $("fit-radius-camera").addEventListener("click", () => callTrajectoryViewer("fitTrajectoryRadius"));
  $("zoom-in-camera").addEventListener("click", () => callTrajectoryViewer("zoomTrajectoryCamera", "in"));
  $("zoom-out-camera").addEventListener("click", () => callTrajectoryViewer("zoomTrajectoryCamera", "out"));
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
    const previewButton = event.target.closest?.("[data-preview-strip]");
    if (previewButton) {
      previewFilmstripRow(previewButton).catch(reportError);
      return;
    }
    if (event.target.matches("[data-open-folder]")) {
      openLocalFolder(event.target.dataset.openFolder).catch(reportError);
      return;
    }
    if (event.target.matches("[data-remove-noise], [data-remove-audio]")) {
      removeSourceCard(event.target);
    }
    if (event.target.matches("[data-remove-strip]")) {
      removeFilmstripRow(event.target);
    }
    if (event.target.matches("[data-remove-strip-element]")) {
      removeFilmstripElement(event.target);
    }
    if (event.target.matches("[data-add-strip-element]")) {
      addFilmstripElement(event.target, event.target.dataset.addStripElement);
    }
    if (event.target.matches("[data-strip-move]")) {
      moveFilmstripRow(event.target, event.target.dataset.stripMove);
    }
  });
  document.addEventListener("input", (event) => {
    const card = event.target.closest?.(".source-card");
    if (card && event.target.matches('[data-field="label"]')) {
      refreshAssemblyTargetOptions();
      syncFilmstripSourceOptions();
    }
    if (event.target.closest?.(".filmstrip-row")) {
      state.design.protocol.trial_strips = collectTrialStrips();
      updateFilmstripCounts();
    }
  });
  document.addEventListener("change", (event) => {
    if (event.target.matches('[data-field="audio_role"]')) {
      const card = event.target.closest(".audio-source-card");
      const title = card?.querySelector(".source-card-heading strong");
      if (card) card.dataset.audioRole = event.target.value;
      if (title) title.textContent = audioRoleTitle(event.target.value);
      refreshAssemblyTargetOptions();
      syncFilmstripSourceOptions();
      renderSourceCounts();
    }
    if (event.target.matches('.noise-source-card [data-field="noise_type"]')) {
      const card = event.target.closest(".noise-source-card");
      const title = card?.querySelector(".source-card-heading strong");
      if (title) title.textContent = `${noiseTypeLabel(event.target.value)} noise`;
      syncFilmstripSourceOptions();
    }
    if (event.target.closest?.(".filmstrip-row")) {
      state.design.protocol.trial_strips = collectTrialStrips();
      updateFilmstripCounts();
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
