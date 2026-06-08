let state = null;
let viewerReady = false;
const activePolls = new Set();
const CUSTOM_TEMPLATE_ID = "__custom__";
const PROFILE_RECREATION_NOTICE =
  "Be aware: this is not the exact stimulus set used in the original study. This preload recreates the study's reported parameters within this interface, using the toolkit's local rendering and bundled profile assets.";
const WORKFLOW_STEPS = ["study", "stimulus", "baseline", "trials", "block", "run", "review"];
const STEP_TARGETS = {
  study: "study",
  stimulus: "stimulus",
  baseline: "baseline",
  trials: "trials",
  block: "block",
  run: "run",
  review: "review"
};
const NEXT_STEP = {
  study: "stimulus",
  stimulus: "baseline",
  baseline: "trials",
  trials: "block",
  block: "run",
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
const STIMULUS_TRAJECTORY_COLORS = {
  pink: "#d783b5",
  blue: "#4b7fc4",
  white: "#d8dde2",
  brown: "#8b623f",
  violet: "#8364b9",
  custom_audio: "#246b55",
  preserve: "#246b55",
  spatialize: "#246b55",
  prestimulus: "#7b8288"
};
const SOURCE_COLOR_OPTIONS = [
  { value: "pink", label: "Pink" },
  { value: "blue", label: "Blue" },
  { value: "white", label: "White" },
  { value: "brown", label: "Brown" },
  { value: "violet", label: "Violet" },
  { value: "custom_audio", label: "Green / custom" }
];
const IMPORTED_AUDIO_HANDLING = [
  { value: "spatialize", label: "Custom looming tone" },
  { value: "preserve", label: "Custom audio clip" }
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
    label: "Matched SOA anchors",
    note: "Tactile-only controls use the same timing anchors as the SOA values in the randomizer."
  },
  soa_zero: {
    label: "Sound onset / min SOA",
    note: "Baseline tactile cues occur at auditory onset, giving a synchronous/minimum-timing anchor."
  },
  sound_offset: {
    label: "Sound offset / max SOA",
    note: "Baseline tactile cues occur at the end of the sound window, giving a late/maximum-timing anchor."
  },
  custom: {
    label: "Custom timing anchors",
    note: "Baseline tactile cues use profile-specific timing anchors carried by the design/template."
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
const cssEscape = (value) => (window.CSS && window.CSS.escape ? window.CSS.escape(String(value)) : String(value).replace(/["\\]/g, "\\$&"));
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
  renderBaseline();
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
  const notice = $("profile-recreation-notice");
  if (notice) {
    const showNotice = Boolean(href && selectedId && selectedId !== CUSTOM_TEMPLATE_ID);
    notice.hidden = !showNotice;
    notice.textContent = showNotice ? PROFILE_RECREATION_NOTICE : "";
  }
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
  select.innerHTML = '<option value="">Choose noise type to bake...</option>';
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
    const localPath = noise.prebaked_path || wav?.path || "";
    const card = document.createElement("div");
    card.className = "source-card noise-source-card";
    applySourceCardColor(card, selectedNoise);
    card.innerHTML = `
      <div class="source-card-heading">
        <strong>${escapeHtml(noiseTypeLabel(selectedNoise))} noise</strong>
        <div class="source-card-actions">
          ${sourceFolderAction(localPath)}
          <button type="button" data-remove-noise>Remove</button>
        </div>
      </div>
      ${stimulusTrajectoryHiddenFields(noise, selectedNoise, "generated_noise")}
      <input data-field="prebaked_path" type="hidden" value="${escapeAttr(localPath)}">
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
  const snippetList = $("snippet-list");
  list.innerHTML = "";
  snippetList.innerHTML = "";
  const customFiles = state.design.custom_looming_files || [];
  const snippets = state.design.prestimulus_files || [];
  const rows = [
    ...customFiles.map((item) => ({
      ...item,
      audio_role: item.render_mode || "preserve",
      target_list: list,
    })),
    ...snippets.map((item) => ({
      ...item,
      audio_role: "prestimulus",
      target_list: snippetList,
    }))
  ];
  for (const audio of rows) {
    const role = String(audio.audio_role || audio.use || audio.render_mode || "preserve").toLowerCase();
    const placement = normalizeSnippetPlacement(audio.placement);
    const targetSource = audio.target_source_label || "";
    const phase = audio.phase || "";
    const colorKey = role === "prestimulus" ? "prestimulus" : (audio.tone_type || audio.noise_type || "custom_audio");
    const motionMode = String(audio.motion_mode || (role === "prestimulus" ? "stationary" : "looming")).toLowerCase();
    const card = document.createElement("div");
    card.className = "source-card audio-source-card";
    card.dataset.audioRole = role;
    applySourceCardColor(card, colorKey);
    card.innerHTML = `
      <div class="source-card-heading">
        <strong>${escapeHtml(audioRoleTitle(role))}</strong>
        <div class="source-card-actions">
          ${sourceFolderAction(audio.path)}
          <button type="button" data-remove-audio>Remove</button>
        </div>
      </div>
      ${stimulusTrajectoryHiddenFields(audio, colorKey, role === "prestimulus" ? "fixed_audio" : "imported_audio")}
      <input data-field="path" type="hidden" value="${escapeAttr(audio.path || "")}">
      <input data-field="motion_mode" type="hidden" value="${escapeAttr(motionMode)}">
      ${role === "prestimulus" ? `<input data-field="audio_role" type="hidden" value="prestimulus">` : ""}
      ${role === "prestimulus" ? `<input data-field="tone_type" type="hidden" value="${escapeAttr(colorKey)}">` : ""}
      <div class="source-card-fields audio-source-fields">
        ${role === "prestimulus" ? "" : `
        <div class="field-row">
          <label>Source handling</label>
          <select data-field="audio_role">
            ${IMPORTED_AUDIO_HANDLING.map((item) => `<option value="${item.value}" ${item.value === role ? "selected" : ""}>${item.label}</option>`).join("")}
          </select>
        </div>
        `}
        ${role === "prestimulus" ? "" : `
        <div class="field-row source-color-field">
          <label>Box color</label>
          <select data-field="tone_type">
            ${sourceColorOptions(colorKey)}
          </select>
        </div>
        `}
        <div class="field-row">
          <label>Label</label>
          <input data-field="label" value="${escapeAttr(audio.label || "")}">
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
    audio.target_list.appendChild(card);
  }
}

function stimulusTrajectoryHiddenFields(source, colorKey = "custom_audio", sourceKind = "") {
  const snapshot = trajectorySnapshotForSource(source, colorKey, sourceKind);
  const rawValue = escapeAttr(JSON.stringify(snapshot || {}));
  return `<input data-field="trajectory_snapshot" type="hidden" value="${rawValue}">`;
}

function stimulusTrajectoryTrace(source, colorKey = "custom_audio", sourceKind = "") {
  const snapshot = trajectorySnapshotForSource(source, colorKey, sourceKind);
  const rawValue = escapeAttr(JSON.stringify(snapshot || {}));
  if (!snapshot || sourceKind === "fixed_audio") return `<input data-field="trajectory_snapshot" type="hidden" value="${rawValue}">`;
  const colors = trajectoryColorSet(snapshot, colorKey);
  const color = colors[0] || sourceColor(colorKey);
  const gradient = trajectoryGradient(colors);
  const start = Number(snapshot.start_distance_cm || 0);
  const end = Number(snapshot.end_distance_cm || 0);
  const startRot = Number(snapshot.start_rotation_deg || 0);
  const endRot = Number(snapshot.end_rotation_deg || 0);
  const duration = Number(snapshot.movement_duration_s || 0);
  const holdStart = Number(snapshot.start_hold_s || 0);
  const holdEnd = Number(snapshot.end_hold_s || 0);
  const path = Number(snapshot.path_length_m || Math.abs(start - end) / 100);
  const title = `${start || "?"} -> ${end || "?"} cm`;
  const detail = `${startRot} -> ${endRot} deg, ${duration}s move`;
  const shared = colors.length > 1 ? `shared path, ${colors.length} tones` : "";
  return `
    <div class="stimulus-trajectory-trace" style="--trajectory-color: ${escapeAttr(color)}; --trajectory-gradient: ${escapeAttr(gradient)}">
      <input data-field="trajectory_snapshot" type="hidden" value="${rawValue}">
      <div class="stimulus-trajectory-line" aria-hidden="true">
        <span class="trajectory-dot start"></span>
        <span class="trajectory-dot end"></span>
      </div>
      <div class="stimulus-trajectory-text">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(detail)}</span>
        <span>${escapeHtml(`${path.toFixed(2)} m path, holds ${holdStart}s/${holdEnd}s`)}</span>
        ${shared ? `<span>${escapeHtml(shared)}</span>` : ""}
      </div>
    </div>
  `;
}

function trajectoryColorSet(snapshot, fallbackKey = "custom_audio") {
  const fallback = sourceColor(fallbackKey);
  const groupKey = trajectoryGroupKey(snapshot);
  if (!groupKey || !state?.design) return [fallback];
  const colors = [];
  for (const source of stimulusInventorySources()) {
    const sourceSnapshot = trajectorySnapshotForSource(source, source.color_key, source.source_kind);
    if (trajectoryGroupKey(sourceSnapshot) !== groupKey) continue;
    const color = sourceColor(source.color_key);
    if (!colors.includes(color)) colors.push(color);
  }
  if (!colors.includes(fallback)) colors.unshift(fallback);
  return colors.length ? colors : [fallback];
}

function stimulusInventorySources() {
  return [
    ...(state?.design?.noises || []).map((source) => ({
      ...source,
      source_kind: "generated_noise",
      color_key: source.noise_type || "pink"
    })),
    ...(state?.design?.custom_looming_files || []).map((source) => ({
      ...source,
      source_kind: "imported_audio",
      color_key: source.tone_type || source.noise_type || "custom_audio"
    }))
  ];
}

function trajectoryGroupKey(snapshot = {}) {
  if (!snapshot || snapshot.start_distance_cm === undefined || snapshot.end_distance_cm === undefined) return "";
  const fields = [
    "start_distance_cm",
    "end_distance_cm",
    "start_rotation_deg",
    "end_rotation_deg",
    "movement_duration_s",
    "start_hold_s",
    "end_hold_s"
  ];
  const controlKey = fields.map((field) => roundedKeyPart(snapshot[field])).join("|");
  const start = snapshot.start || {};
  const end = snapshot.end || {};
  const coordinateKey = ["x_m", "y_m", "z_m"]
    .map((field) => `${roundedKeyPart(start[field])}:${roundedKeyPart(end[field])}`)
    .join("|");
  return `${controlKey}|${coordinateKey}`;
}

function roundedKeyPart(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(4) : "";
}

function sourceColor(key = "custom_audio") {
  return STIMULUS_TRAJECTORY_COLORS[String(key || "").toLowerCase()] || STIMULUS_TRAJECTORY_COLORS.custom_audio;
}

function sourceColorOptions(selected = "custom_audio") {
  const selectedValue = String(selected || "custom_audio").toLowerCase();
  return SOURCE_COLOR_OPTIONS.map((item) =>
    `<option value="${escapeAttr(item.value)}" ${item.value === selectedValue ? "selected" : ""}>${escapeHtml(item.label)}</option>`
  ).join("");
}

function applySourceCardColor(card, colorKey = "custom_audio") {
  if (!card) return;
  const color = sourceColor(colorKey);
  card.style.setProperty("--source-card-color", color);
  card.style.setProperty("--source-card-color-soft", colorWithAlpha(color, 0.12));
}

function colorWithAlpha(hex, alpha = 0.12) {
  const match = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(String(hex || ""));
  if (!match) return `rgba(36, 107, 85, ${alpha})`;
  const [, r, g, b] = match;
  return `rgba(${Number.parseInt(r, 16)}, ${Number.parseInt(g, 16)}, ${Number.parseInt(b, 16)}, ${Math.max(0, Math.min(1, alpha))})`;
}

function trajectoryGradient(colors = []) {
  const safeColors = (colors.length ? colors : [sourceColor("custom_audio")]).map((color) => color || sourceColor("custom_audio"));
  if (safeColors.length === 1) return safeColors[0];
  const stops = [];
  const width = 100 / safeColors.length;
  safeColors.forEach((color, index) => {
    const start = Math.round(index * width * 10) / 10;
    const end = Math.round((index + 1) * width * 10) / 10;
    stops.push(`${color} ${start}%`, `${color} ${end}%`);
  });
  return `linear-gradient(90deg, ${stops.join(", ")})`;
}

function trajectorySnapshotForSource(source = {}, colorKey = "custom_audio", sourceKind = "") {
  const snapshot = source.trajectory_snapshot && typeof source.trajectory_snapshot === "object"
    ? clone(source.trajectory_snapshot)
    : {};
  if (snapshot.start_distance_cm !== undefined && snapshot.end_distance_cm !== undefined) {
    return snapshot;
  }
  if (sourceKind === "fixed_audio") return {};
  if (String(source.motion_mode || "").toLowerCase() === "stationary") return {};
  const controls = state.trajectory_controls || currentTrajectoryControls();
  return {
    schema: "pps-stimulus-trajectory.v1",
    label: source.label || "",
    source_kind: sourceKind,
    noise_type: colorKey,
    start_distance_cm: controls.start_distance_cm,
    end_distance_cm: controls.end_distance_cm,
    start_rotation_deg: controls.start_rotation_deg,
    end_rotation_deg: controls.end_rotation_deg,
    movement_duration_s: controls.movement_duration_s,
    start_hold_s: controls.start_hold_s,
    end_hold_s: controls.end_hold_s,
    path_length_m: Math.max(0, Math.abs(Number(controls.start_distance_cm || 0) - Number(controls.end_distance_cm || 0)) / 100),
  };
}

function readJsonField(field) {
  if (!field) return {};
  try {
    const value = JSON.parse(field.value || "{}");
    return value && typeof value === "object" ? value : {};
  } catch (_error) {
    return {};
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
  const snippetCards = [...$("snippet-list").querySelectorAll(".audio-source-card")];
  const imported = audioCards.length;
  const prestimulus = snippetCards.length;
  const stimulusSources = generated + imported;
  const sourceLabel = `${stimulusSources} local source${stimulusSources === 1 ? "" : "s"}`;
  $("source-counts").textContent = sourceLabel;
  $("source-counts").className = `status-label ${stimulusSources ? "ready" : "required"}`;
  if ($("snippet-counts")) {
    $("snippet-counts").textContent = `${prestimulus} clip${prestimulus === 1 ? "" : "s"}`;
    $("snippet-counts").className = `status-label ${prestimulus ? "ready" : "required"}`;
  }
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
  $("soa-values").value = formatList(protocol.soa_values_ms);
  $("block-soa-values").value = formatList(protocol.soa_values_ms);
  renderTrialStrips();
  renderProtocolSummary();
}

function renderProtocolSummary() {
  const summary = $("protocol-summary");
  summary.innerHTML = "";
  const blocks = Math.max(1, Math.round(numberValue("blocks", state.design.protocol?.blocks || 1)));
  const participants = Math.max(1, Math.round(numberValue("participants", state.design.protocol?.participants || 1)));
  const composition = blockCompositionEstimate();
  const totalTrials = composition.totalPerBlock * blocks;
  const participantMinutes = Math.round((totalTrials * estimatedTrialSeconds() / 60) * 10) / 10;
  const baselineDenominator = Math.max(1, composition.audioPerBlock + composition.baselinePerBlock);
  const rows = {
    audio_tactile_trials: composition.audioPerBlock * blocks,
    baseline_trials: composition.baselinePerBlock * blocks,
    catch_trials: composition.catchPerBlock * blocks,
    total_trials: totalTrials,
    blocks,
    trials_per_block: composition.totalPerBlock,
    min_trials_per_block: composition.totalPerBlock,
    max_trials_per_block: composition.totalPerBlock,
    participants,
    total_participant_trials: totalTrials * participants,
    baseline_actual_percent: Math.round((1000 * composition.baselinePerBlock / baselineDenominator)) / 10,
    estimated_participant_minutes: participantMinutes,
    estimated_all_participants_hours: Math.round((participantMinutes * participants / 60) * 10) / 10,
  };
  for (const [key, value] of Object.entries(rows)) {
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
  $("catch-percent").value = protocol.catch_trial_percentage ?? 0;
  $("baseline-percent").value = savedStrategy === "none" ? 0 : (protocol.baseline_trial_percentage ?? 0);
  $("baseline-soa-values").value = formatList(protocol.baseline_soa_values_ms || []);
  setBaselineStrategy(savedStrategy);
  updateBaselineDecision();
}

function currentBaselineStrategy() {
  return $("baseline-strategy").value || "none";
}

function baselineOptionInputs() {
  return [...document.querySelectorAll('input[name="baseline-option"]')];
}

function setBaselineStrategy(strategy) {
  const nextStrategy = strategy || "none";
  $("baseline-strategy").value = nextStrategy;
  if ($("baseline-strategy").value !== nextStrategy) $("baseline-strategy").value = "none";
  $("baseline-enabled").checked = nextStrategy !== "none";
  syncBaselineStrategyControls();
}

function syncBaselineStrategyControls() {
  const strategy = $("baseline-strategy").value || "none";
  $("baseline-strategy").value = strategy;
  $("baseline-enabled").checked = strategy !== "none";
  for (const input of baselineOptionInputs()) {
    input.disabled = false;
    input.checked = input.value === strategy;
    input.closest(".baseline-option-card")?.classList.toggle("active", input.checked);
    input.closest(".baseline-option-card")?.classList.remove("disabled");
  }
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
  return blockCompositionEstimate().audioPerBlock;
}

function tactileSiteCount() {
  return Math.max(1, (state.design.protocol?.tactile_sites || ["hand"]).length);
}

function rowSourceCount(row) {
  const fallbackSourceCount = Math.max(1, stimulusSourceDetailsFromDom().length);
  const slot = row.querySelector('.filmstrip-element[data-element-kind="looming_stimulus"]');
  let selected = 0;
  if (slot) {
    const checkboxes = slot.querySelectorAll('input[data-element-field="source_labels"]:checked');
    const selectedOptions = slot.querySelectorAll('select[data-element-field="source_labels"] option:checked');
    selected = checkboxes.length || selectedOptions.length;
  }
  return Math.max(1, selected || fallbackSourceCount);
}

function rowAudioCountPerBlock(row) {
  const soaCount = parseIntegerList($("soa-values").value).length;
  const repetitions = Math.max(1, Math.round(numberValue("repetitions", 1)));
  return rowSourceCount(row) * Math.max(soaCount, 0) * repetitions * tactileSiteCount();
}

function defaultRowMix() {
  const catchPercent = Math.max(0, Math.min(99, numberValue("catch-percent", 0)));
  const baselinePercent = currentBaselineStrategy() === "none"
    ? 0
    : Math.max(0, Math.min(99, numberValue("baseline-percent", 0)));
  return {
    audioTactile: Math.max(1, 100 - catchPercent - baselinePercent),
    catch: catchPercent,
    baseline: baselinePercent,
  };
}

function rowMixFromRow(row) {
  const defaults = defaultRowMix();
  const field = (name) => row.querySelector(`[data-strip-field="${name}"]`);
  const catchValue = field("catch_percentage")?.value;
  const baselineValue = currentBaselineStrategy() === "none" ? 0 : field("baseline_percentage")?.value;
  const audioValue = field("audio_tactile_percentage")?.value;
  const catchPercent = catchValue === undefined || catchValue === ""
    ? defaults.catch
    : Math.max(0, Math.min(100, Number(catchValue || 0)));
  const baselinePercent = baselineValue === undefined || baselineValue === ""
    ? defaults.baseline
    : Math.max(0, Math.min(100, Number(baselineValue || 0)));
  const audioTactilePercent = audioValue === undefined || audioValue === ""
    ? Math.max(0, 100 - catchPercent - baselinePercent)
    : Math.max(0, Math.min(100, Number(audioValue || 0)));
  return {
    audioTactile: audioTactilePercent,
    catch: catchPercent,
    baseline: baselinePercent,
    total: audioTactilePercent + catchPercent + baselinePercent,
  };
}

function applyBaselineDefaultToTrialRows() {
  const baselinePercent = currentBaselineStrategy() === "none"
    ? 0
    : Math.max(0, Math.min(99, numberValue("baseline-percent", 0)));
  for (const row of $("filmstrip-list").querySelectorAll(".filmstrip-row")) {
    const catchField = row.querySelector('[data-strip-field="catch_percentage"]');
    const baselineField = row.querySelector('[data-strip-field="baseline_percentage"]');
    const audioField = row.querySelector('[data-strip-field="audio_tactile_percentage"]');
    if (!baselineField || !audioField) continue;
    const catchPercent = Math.max(0, Math.min(99, Number(catchField?.value || 0)));
    baselineField.value = String(baselinePercent);
    audioField.value = String(Math.max(1, 100 - catchPercent - baselinePercent));
  }
}

function syncRandomizerSoaInputs(sourceInput) {
  const value = sourceInput?.value ?? $("soa-values").value;
  $("soa-values").value = value;
  if ($("block-soa-values") && $("block-soa-values") !== sourceInput) {
    $("block-soa-values").value = value;
  }
}

function rowExtraCount(audioCount, extraPercent, audioPercent) {
  if (audioCount <= 0 || extraPercent <= 0) return 0;
  return Math.ceil(audioCount * extraPercent / Math.max(0.1, audioPercent));
}

function rowCompositionCounts(row) {
  const audioPerBlock = rowAudioCountPerBlock(row);
  const mix = rowMixFromRow(row);
  const catchPerBlock = rowExtraCount(audioPerBlock, mix.catch, mix.audioTactile);
  const baselinePerBlock = currentBaselineStrategy() === "none"
    ? 0
    : rowExtraCount(audioPerBlock, mix.baseline, mix.audioTactile);
  return {
    mix,
    audioPerBlock,
    catchPerBlock,
    baselinePerBlock,
    totalPerBlock: audioPerBlock + catchPerBlock + baselinePerBlock,
  };
}

function blockCompositionEstimate() {
  const rows = [...$("filmstrip-list").querySelectorAll(".filmstrip-row")];
  if (!rows.length) {
    const soaCount = parseIntegerList($("soa-values").value).length;
    const repetitions = Math.max(1, Math.round(numberValue("repetitions", 1)));
    const audioPerBlock = Math.max(1, stimulusSourceDetailsFromDom().length) * Math.max(soaCount, 0) * repetitions * tactileSiteCount();
    const mix = defaultRowMix();
    const catchPerBlock = rowExtraCount(audioPerBlock, mix.catch, mix.audioTactile);
    const baselinePerBlock = currentBaselineStrategy() === "none"
      ? 0
      : rowExtraCount(audioPerBlock, mix.baseline, mix.audioTactile);
    return {
      audioPerBlock,
      catchPerBlock,
      baselinePerBlock,
      totalPerBlock: audioPerBlock + catchPerBlock + baselinePerBlock,
      rows: [],
    };
  }
  const composition = {
    audioPerBlock: 0,
    catchPerBlock: 0,
    baselinePerBlock: 0,
    totalPerBlock: 0,
    rows: [],
  };
  for (const row of rows) {
    const rowCounts = rowCompositionCounts(row);
    composition.audioPerBlock += rowCounts.audioPerBlock;
    composition.catchPerBlock += rowCounts.catchPerBlock;
    composition.baselinePerBlock += rowCounts.baselinePerBlock;
    composition.totalPerBlock += rowCounts.totalPerBlock;
    composition.rows.push(rowCounts);
  }
  return composition;
}

function baselineCountEstimate() {
  const strategy = currentBaselineStrategy();
  const blocks = Math.max(1, Math.round(numberValue("blocks", 1)));
  const composition = blockCompositionEstimate();
  if (!strategy || strategy === "none") {
    return { strategy, timings: [], perBlock: 0, total: 0, actualPercent: 0, audioPerBlock: composition.audioPerBlock, composition };
  }
  const timings = derivedBaselineTimingsMs(strategy);
  const perBlock = composition.baselinePerBlock;
  const denominator = Math.max(1, composition.totalPerBlock);
  return {
    strategy,
    timings,
    perBlock,
    total: perBlock * blocks,
    actualPercent: Math.round((1000 * perBlock / denominator)) / 10,
    audioPerBlock: composition.audioPerBlock,
    composition,
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
  syncBaselineStrategyControls();
  const strategy = currentBaselineStrategy();
  const status = $("baseline-status");
  const valid = Boolean(strategy);
  status.textContent = valid ? "ready" : "required";
  status.className = `status-label ${valid ? "ready" : "required"}`;
  if (strategy === "none") $("baseline-percent").value = 0;
}

function renderTrialStrips() {
  const list = $("filmstrip-list");
  if (!list) return;
  const strips = state.design.protocol?.trial_strips || [];
  list.innerHTML = "";
  if (!strips.length) {
    list.innerHTML = `
      <button type="button" class="trial-row-empty" data-add-empty-row aria-label="Add first trial row">
        <span>+</span>
      </button>
    `;
    return;
  }
  strips.forEach((strip, index) => list.appendChild(renderTrialStripRow(strip, index)));
  updateFilmstripCounts();
}

function stripMixValues(strip = {}) {
  const protocol = state.design.protocol || {};
  const catchPercent = strip.catch_percentage ?? protocol.catch_trial_percentage ?? 0;
  const baselineFallback = protocol.include_baseline_trials === false
    ? 0
    : (protocol.baseline_trial_percentage ?? 0);
  const baselinePercent = strip.baseline_percentage ?? baselineFallback;
  const audioTactilePercent = strip.audio_tactile_percentage ?? Math.max(0, 100 - catchPercent - baselinePercent);
  return {
    audioTactile: Math.round(Number(audioTactilePercent || 0) * 10) / 10,
    catch: Math.round(Number(catchPercent || 0) * 10) / 10,
    baseline: Math.round(Number(baselinePercent || 0) * 10) / 10,
  };
}

function renderTrialStripRow(strip, index) {
  const row = document.createElement("div");
  const mix = stripMixValues(strip);
  row.className = "filmstrip-row";
  row.dataset.stripIndex = String(index);
  row.innerHTML = `
    <div class="filmstrip-row-header">
      <button type="button" class="filmstrip-preview-button" data-preview-strip="${index}" title="Prelisten trial type" aria-label="Prelisten trial type">&#9658;</button>
      <div class="trial-row-order">
        <strong>Row ${index + 1}</strong>
        <span>${rowOrderText(index)}</span>
      </div>
      <div class="field-row">
        <label>Trial type label</label>
        <input data-strip-field="label" value="${escapeAttr(strip.label || `Trial type ${index + 1}`)}">
      </div>
      <div class="filmstrip-row-actions">
        <button type="button" class="icon-action" data-strip-move="up" title="Move row up" aria-label="Move row up">^</button>
        <button type="button" class="icon-action" data-strip-move="down" title="Move row down" aria-label="Move row down">v</button>
        <button type="button" class="icon-action danger" data-remove-strip title="Remove trial sequence row" aria-label="Remove trial sequence row">x</button>
      </div>
    </div>
    <div class="filmstrip-row-mix state-only" aria-label="Trial type row composition">
      <div class="field-row">
        <label>Audio-tactile %</label>
        <input data-strip-field="audio_tactile_percentage" type="number" min="0" max="100" step="1" value="${escapeAttr(mix.audioTactile)}">
      </div>
      <div class="field-row">
        <label>Catch %</label>
        <input data-strip-field="catch_percentage" type="number" min="0" max="100" step="1" value="${escapeAttr(mix.catch)}">
      </div>
      <div class="field-row">
        <label>Baseline %</label>
        <input data-strip-field="baseline_percentage" type="number" min="0" max="100" step="1" value="${escapeAttr(mix.baseline)}">
      </div>
    </div>
    <div class="filmstrip-sequence"></div>
  `;
  const sequence = row.querySelector(".filmstrip-sequence");
  for (const [elementIndex, element] of (strip.elements || []).entries()) {
    sequence.appendChild(renderTrialStripElement(element, elementIndex));
    sequence.appendChild(renderAddEventControl(index, elementIndex + 1, strip));
  }
  if (!(strip.elements || []).length) {
    sequence.appendChild(renderAddEventControl(index, 0, strip, true));
  }
  return row;
}

function rowOrderText(index) {
  return index === 0 ? "plays first" : `plays after row ${index}`;
}

function renderTrialStripElement(element, index) {
  const sourceType = element.kind === "fixed_audio" ? "fixed_audio" : "looming_stimulus";
  const card = document.createElement("div");
  card.className = `filmstrip-element sequence-event ${sourceType.replace("_", "-")} ${filmstripNoiseClass(element)}`;
  card.dataset.elementIndex = String(index);
  card.dataset.elementKind = sourceType;
  card.innerHTML = sourceType === "fixed_audio"
    ? renderFixedBlock(element)
    : renderRandomizerBlock(element);
  return card;
}

function renderAddEventControl(rowIndex, insertAfter, strip = {}, isEmpty = false) {
  const wrapper = document.createElement("div");
  wrapper.className = `sequence-event-add ${isEmpty ? "empty-row-add" : ""}`;
  const hasRandomizer = (strip.elements || []).some((element) => element.kind === "looming_stimulus");
  wrapper.innerHTML = `
    <button type="button" class="sequence-event-add-symbol" title="Add sequence event" aria-label="Add sequence event">+</button>
    <div class="sequence-event-add-menu" aria-label="Add sequence event type">
      <button type="button" data-add-strip-element="fixed_audio" data-insert-after="${insertAfter}">Fixed</button>
      <button type="button" data-add-strip-element="looming_stimulus" data-insert-after="${insertAfter}" ${hasRandomizer ? "disabled title=\"One randomizer event per row is supported for now.\"" : ""}>Randomizer</button>
    </div>
  `;
  return wrapper;
}

function renderFixedBlock(element) {
  const title = "Fixed event";
  return `
    <div class="filmstrip-element-heading">
      <span>${title}</span>
      <button type="button" class="icon-action danger" data-remove-strip-element title="Remove event" aria-label="Remove event">x</button>
    </div>
    <div class="field-row">
      <label>Clip</label>
      <select data-element-field="source_label">${fixedAudioOptions(element.source_label || "")}</select>
    </div>
    <input data-element-field="label" type="hidden" value="${escapeAttr(element.label || element.source_label || title)}">
    <div class="sequence-event-note">Always plays this clip at this position.</div>
  `;
}

function renderRandomizerBlock(element) {
  const title = "Randomizer event";
  const selected = normalizedRandomizerSelection(element);
  return `
    <div class="filmstrip-element-heading">
      <span>${title}</span>
      <button type="button" class="icon-action danger" data-remove-strip-element title="Remove event" aria-label="Remove event">x</button>
    </div>
    <div class="sequence-event-note">Randomizes across the selected stimulus sources at this point in the sequence.</div>
    <div class="randomizer-source-list" data-randomizer-source-list>
      ${randomizerSourceRows(selected)}
    </div>
    <input data-element-field="label" type="hidden" value="${escapeAttr(element.label || "Randomizer event")}">
    <input data-element-field="randomized" type="hidden" value="true">
  `;
}

function normalizedRandomizerSelection(element = {}) {
  const allLabels = stimulusSourceDetailsFromDom().map((item) => item.label);
  const saved = (element.source_labels || []).filter(Boolean);
  return new Set(saved.length ? saved : allLabels);
}

function randomizerSourceRows(selectedSet) {
  const sources = stimulusSourceDetailsFromDom();
  if (!sources.length) {
    return `<div class="randomizer-empty">Bake or import a stimulus source first.</div>`;
  }
  const rows = sources.map((source) => `
    <label class="randomizer-source-row ${source.noise_type ? `noise-${escapeAttr(String(source.noise_type).toLowerCase())}` : ""}">
      <span>
        <input data-element-field="source_labels" type="checkbox" value="${escapeAttr(source.label)}" ${selectedSet.has(source.label) ? "checked" : ""}>
        ${escapeHtml(source.label)}
      </span>
    </label>
  `);
  return rows.join("");
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
  for (const card of $("snippet-list").querySelectorAll(".audio-source-card")) {
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
    sources.push({ label, noise_type: card.querySelector('[data-field="tone_type"]')?.value || "custom_audio" });
  }
  return sources;
}

function collectTrialStrips() {
  const strips = [];
  for (const [stripIndex, row] of [...$("filmstrip-list").querySelectorAll(".filmstrip-row")].entries()) {
    const label = row.querySelector('[data-strip-field="label"]')?.value.trim() || `Trial type ${stripIndex + 1}`;
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
        item.label = item.source_label || item.label;
      } else {
        const checked = [...card.querySelectorAll('input[data-element-field="source_labels"]:checked')].map((input) => input.value);
        const selected = [...card.querySelectorAll('select[data-element-field="source_labels"] option:checked')].map((option) => option.value);
        item.source_labels = checked.length ? checked : selected;
        item.randomized = true;
      }
      elements.push(item);
    }
    strips.push({
      strip_id: `strip-${stripIndex + 1}`,
      label,
      audio_tactile_percentage: Number(row.querySelector('[data-strip-field="audio_tactile_percentage"]')?.value || 0),
      catch_percentage: Number(row.querySelector('[data-strip-field="catch_percentage"]')?.value || 0),
      baseline_percentage: Number(row.querySelector('[data-strip-field="baseline_percentage"]')?.value || 0),
      elements,
    });
  }
  return strips;
}

function updateFilmstripCounts() {
  for (const row of $("filmstrip-list").querySelectorAll(".filmstrip-row")) {
    const rowCounts = rowCompositionCounts(row);
    const mixValid = Math.abs(rowCounts.mix.total - 100) <= 0.5 && rowCounts.mix.audioTactile > 0;
    row.classList.toggle("mix-warning", !mixValid);
  }
  renderProtocolSummary();
  updateBaselineDecision();
}

function updateRandomizerBlockCounts(row, rowCounts, soaCount, repetitions) {
  renderProtocolSummary();
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
    label: `Trial type ${strips.length + 1}`,
    ...(() => {
      const mix = defaultRowMix();
      return {
        audio_tactile_percentage: mix.audioTactile,
        catch_percentage: mix.catch,
        baseline_percentage: mix.baseline,
      };
    })(),
    elements: [],
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
    label: "Randomizer event",
    source_label: "",
    source_labels: stimulusSourceDetailsFromDom().map((item) => item.label),
    randomized: true,
  };
}

function addFilmstripElement(button, kind) {
  const row = button.closest(".filmstrip-row");
  const stripIndex = Number(row?.dataset.stripIndex || -1);
  const strips = collectTrialStrips();
  if (!strips[stripIndex]) return;
  if (kind === "looming_stimulus" && strips[stripIndex].elements.some((element) => element.kind === "looming_stimulus")) {
    showToast("One randomizer event per row is supported for now.");
    return;
  }
  const insertAfter = Number(button.dataset.insertAfter ?? strips[stripIndex].elements.length);
  const index = Math.max(0, Math.min(strips[stripIndex].elements.length, insertAfter));
  strips[stripIndex].elements.splice(index, 0, defaultFilmstripElement(kind));
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
  syncRandomizerSourceLists();
  updateFilmstripCounts();
}

function syncRandomizerSourceLists() {
  for (const block of document.querySelectorAll('.filmstrip-element[data-element-kind="looming_stimulus"]')) {
    const selected = new Set([...block.querySelectorAll('input[data-element-field="source_labels"]:checked')].map((input) => input.value));
    const fallback = selected.size ? selected : normalizedRandomizerSelection({ source_labels: [] });
    const list = block.querySelector("[data-randomizer-source-list]");
    if (list) list.innerHTML = randomizerSourceRows(fallback);
  }
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
  renderProtocolSummary();
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
  fillTable("trial-table", trialRows, ["block", "trial", "type", "trial_type", "soa_ms", "space_cm", "tactile_site", "sequence"]);

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
  const trajectoryControls = currentTrajectoryControls();
  design.name = $("design-name").value.trim() || "Untitled PPS design";
  design.noises = collectNoises();
  const audio = collectAudioFiles();
  design.custom_looming_files = audio.looming;
  design.prestimulus_files = audio.prestimulus;
  const trialStrips = collectTrialStrips();
  const legacySpatial = design.protocol?.spatial_values_cm?.length
    ? design.protocol.spatial_values_cm
    : [trajectoryControls.end_distance_cm];
  const baselineStrategy = currentBaselineStrategy();
  const baselineTimings = baselineStrategy === "tactile_only" || baselineStrategy === "custom"
    ? parseIntegerList($("baseline-soa-values").value)
    : [];
  design.protocol = {
    ...(design.protocol || {}),
    repetitions_per_condition: Math.max(1, Math.round(numberValue("repetitions", 1))),
    soa_values_ms: parseIntegerList($("block-soa-values").value || $("soa-values").value),
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
    trajectory_controls: trajectoryControls
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
      gain: Number(field("gain").value || 1),
      prebaked_path: field("prebaked_path")?.value.trim() || "",
      trajectory_snapshot: readJsonField(field("trajectory_snapshot"))
    };
  });
}

function collectAudioFiles() {
  const result = { looming: [], prestimulus: [] };
  const cards = [
    ...$("audio-list").querySelectorAll(".audio-source-card"),
    ...$("snippet-list").querySelectorAll(".audio-source-card"),
  ];
  for (const card of cards) {
    const field = (name) => card.querySelector(`[data-field="${name}"]`);
    const role = field("audio_role").value;
    const item = {
      label: field("label").value.trim() || "Audio file",
      path: field("path").value.trim(),
      target_duration_s: Number(field("target_duration_s").value || 4),
      render_mode: role === "spatialize" ? "spatialize" : "preserve",
      tone_type: field("tone_type")?.value.trim() || "",
      gain: Number(field("gain").value || 1),
      placement: normalizeSnippetPlacement(field("placement")?.value),
      target_source_label: field("target_source_label")?.value.trim() || "",
      phase: field("phase")?.value.trim() || "",
      gap_s: Math.max(0, Number(field("gap_s")?.value || 0)),
      motion_mode: field("motion_mode")?.value || (role === "prestimulus" ? "stationary" : "looming"),
      trajectory_snapshot: readJsonField(field("trajectory_snapshot"))
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
    movement_duration_s: clampNumber(numberValue("movement-duration", 3), 0.1, 30, 3),
    start_hold_s: clampNumber(numberValue("start-hold", 0.5), 0, 30, 0.5),
    end_hold_s: clampNumber(numberValue("end-hold", 0.5), 0, 30, 0.5)
  };
}

function trajectoryPayloadFromControls() {
  const controls = currentTrajectoryControls();
  const start = pointFromDistanceRotation(controls.start_distance_cm, controls.start_rotation_deg);
  const end = pointFromDistanceRotation(controls.end_distance_cm, controls.end_rotation_deg);
  const pathLength = distance3d(start, end);
  const sourceTrajectories = sourceTrajectoriesFromDom();
  const sourceRadius = maxSourceTrajectoryRadius(sourceTrajectories);
  const radius = Math.max(0.1, controls.start_distance_cm / 100, controls.end_distance_cm / 100, sourceRadius);
  return {
    ...clone(state.viewer_payload || {}),
    preview_mode: $("preview-mode").value || "2d",
    radius_m: radius,
    path_length_m: pathLength,
    movement_duration_s: controls.movement_duration_s,
    start,
    end,
    controls,
    source_trajectories: sourceTrajectories
  };
}

function sourceTrajectoriesFromDom() {
  const rows = [];
  for (const card of $("noise-list").querySelectorAll(".noise-source-card")) {
    const field = (name) => card.querySelector(`[data-field="${name}"]`);
    const label = field("label")?.value.trim() || "Generated noise";
    const toneType = field("noise_type")?.value || "pink";
    const snapshot = readJsonField(field("trajectory_snapshot"));
    const row = sourceTrajectoryRow({
      label,
      sourceKind: "generated_noise",
      toneType,
      localPath: field("prebaked_path")?.value || "",
      snapshot
    });
    if (row) rows.push(row);
  }
  for (const card of $("audio-list").querySelectorAll(".audio-source-card")) {
    const field = (name) => card.querySelector(`[data-field="${name}"]`);
    const role = field("audio_role")?.value || "preserve";
    if (role === "prestimulus") continue;
    const label = field("label")?.value.trim() || audioRoleTitle(role);
    const toneType = field("tone_type")?.value || "custom_audio";
    const row = sourceTrajectoryRow({
      label,
      sourceKind: "imported_audio",
      toneType,
      localPath: field("path")?.value || "",
      snapshot: readJsonField(field("trajectory_snapshot"))
    });
    if (row) rows.push(row);
  }
  return rows.length ? rows : clone(state.viewer_payload?.source_trajectories || []);
}

function sourceTrajectoryRow({ label, sourceKind, toneType, localPath, snapshot }) {
  if (!snapshot || !snapshot.start || !snapshot.end) return null;
  return {
    label,
    source_kind: sourceKind,
    tone_type: toneType,
    color_hex: sourceColor(toneType),
    local_path: localPath,
    trajectory_snapshot: snapshot,
    start: snapshot.start,
    end: snapshot.end,
    path_length_m: snapshot.path_length_m,
    movement_duration_s: snapshot.movement_duration_s
  };
}

function maxSourceTrajectoryRadius(rows = []) {
  let radius = 0;
  for (const row of rows) {
    for (const point of [row.start, row.end]) {
      if (!point) continue;
      const value = Math.sqrt(Number(point.x_m || 0) ** 2 + Number(point.y_m || 0) ** 2 + Number(point.z_m || 0) ** 2);
      if (Number.isFinite(value)) radius = Math.max(radius, value);
    }
  }
  return radius;
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
    label: audio.label || audioRoleTitle(mode),
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
  if (role === "spatialize") return "Custom looming tone";
  if (role === "prestimulus") return "Custom clip";
  return "Custom audio clip";
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
      motion_mode: pendingAudioImportMode === "preserve" || pendingAudioImportMode === "prestimulus" ? "stationary" : "looming",
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
    showToast("Custom clip imported locally");
  } else if (pendingAudioImportMode === "preserve") {
    state.design.custom_looming_files = state.design.custom_looming_files || [];
    state.design.custom_looming_files.push({
      ...imported.audio,
      render_mode: "preserve",
      motion_mode: "stationary",
      tone_type: imported.audio.tone_type || "custom_audio",
      trajectory_snapshot: {}
    });
    pendingBakeRecipe = null;
    renderBakePanel();
    renderAudioTable();
    refreshAssemblyTargetOptions();
    syncFilmstripSourceOptions();
    renderSourceCounts();
    updateViewer();
    showToast("Custom audio clip imported locally");
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
  $("import-audio-prestimulus")?.addEventListener("click", () => openAudioPicker("prestimulus"));
  $("audio-file-input").addEventListener("change", () => importAudioFromPicker().catch(reportError));
  $("add-strip-row").addEventListener("click", () => addFilmstripRow());
  $("soa-values").addEventListener("input", updateFilmstripCounts);
  $("block-soa-values").addEventListener("input", () => {
    syncRandomizerSoaInputs($("block-soa-values"));
    updateFilmstripCounts();
  });
  $("repetitions").addEventListener("input", updateFilmstripCounts);
  $("blocks").addEventListener("input", updateFilmstripCounts);
  $("participants").addEventListener("input", renderProtocolSummary);
  $("catch-percent").addEventListener("input", updateFilmstripCounts);
  $("baseline-enabled").addEventListener("change", () => {
    const previous = $("baseline-strategy").value;
    const nextStrategy = $("baseline-enabled").checked
      ? (previous && previous !== "none" ? previous : "tactile_only")
      : "none";
    setBaselineStrategy(nextStrategy);
    if (nextStrategy === "none") applyBaselineDefaultToTrialRows();
    updateFilmstripCounts();
  });
  $("baseline-strategy").addEventListener("change", () => {
    const nextStrategy = $("baseline-strategy").value || "none";
    setBaselineStrategy(nextStrategy);
    if (nextStrategy === "none") applyBaselineDefaultToTrialRows();
    updateFilmstripCounts();
  });
  for (const input of baselineOptionInputs()) {
    input.addEventListener("change", () => {
      if (!input.checked) {
        setBaselineStrategy(currentBaselineStrategy());
        return;
      }
      const nextStrategy = input.value || "none";
      setBaselineStrategy(nextStrategy);
      if (nextStrategy === "none") applyBaselineDefaultToTrialRows();
      updateFilmstripCounts();
    });
  }
  $("baseline-percent").addEventListener("input", () => {
    applyBaselineDefaultToTrialRows();
    updateFilmstripCounts();
  });
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
    if (event.target.matches("[data-add-empty-row]") || event.target.closest?.("[data-add-empty-row]")) {
      addFilmstripRow();
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
      updateViewer();
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
      const motionField = card?.querySelector('[data-field="motion_mode"]');
      if (motionField) {
        motionField.value = event.target.value === "preserve" || event.target.value === "prestimulus" ? "stationary" : "looming";
      }
      applySourceCardColor(card, event.target.value === "prestimulus" ? "prestimulus" : card?.querySelector('[data-field="tone_type"]')?.value || "custom_audio");
      refreshAssemblyTargetOptions();
      syncFilmstripSourceOptions();
      renderSourceCounts();
      updateViewer();
    }
    if (event.target.matches('.audio-source-card [data-field="tone_type"]')) {
      const card = event.target.closest(".audio-source-card");
      applySourceCardColor(card, event.target.value);
      syncFilmstripSourceOptions();
      updateViewer();
    }
    if (event.target.matches('.noise-source-card [data-field="noise_type"]')) {
      const card = event.target.closest(".noise-source-card");
      const title = card?.querySelector(".source-card-heading strong");
      if (title) title.textContent = `${noiseTypeLabel(event.target.value)} noise`;
      applySourceCardColor(card, event.target.value);
      syncFilmstripSourceOptions();
      updateViewer();
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
