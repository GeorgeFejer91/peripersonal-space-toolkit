---
name: html-dashboard-orchestrator
description: Use when Codex changes an HTML/browser dashboard that controls local software through a companion backend, especially the PPS Toolkit dashboard. Applies to UI controls, static assets, local companion APIs, dashboard/backend schemas, GitHub Pages-hosted orchestrator pages, launcher behavior, privacy boundaries, Playwright/browser validation, and project-memory updates.
---

# HTML Dashboard Orchestrator

Use this workflow to change a browser-based GUI that is an orchestrator for local programs. The browser may be local or hosted on GitHub Pages, but the trusted work stays in the local backend.

## Core Rule

Keep the browser UI as a decision surface only. Do not move validated timing, stimulus rendering, file storage, participant data, audio stress, session preparation, or native Focus Mode execution into browser JavaScript.

In this repo:

- Dashboard assets live in `src/peripersonal_space_toolkit/dashboard/`.
- The embedded trajectory viewer lives in `src/peripersonal_space_toolkit/viewer/`.
- The companion backend lives in `src/peripersonal_space_toolkit/dashboard_app.py`.
- Experiment schemas and render behavior live in `src/peripersonal_space_toolkit/design.py` and `src/peripersonal_space_toolkit/render_backend.py`.
- Preload asset readiness lives in `assets/preloads/preload_inventory.json`; the browser may display status, but the local companion verifies, downloads, or bakes profile assets.
- Preload profile file cabinets live under `assets/preloads/<template_id>/` and should mirror the dashboard decision segments (`01_profile`, `02_looming_stimuli`, `03_baseline_strategy`, `04_trial_designer`, `05_run_setup`). Rebuild them with `tools/build_preload_catalog.py` when preload sources, trajectories, or metadata change.
- Public/hosted static behavior must still use relative assets and connect to `127.0.0.1` for backend actions.

## Workflow

1. Classify the change.
   - UI-only: layout, labels, controls, visual state, panel sizing, viewer interaction.
   - Orchestration: UI calls existing backend action.
   - Contract: UI needs new saved fields, API payloads, render config, session manifest, or tests.
   - Boundary-sensitive: file imports, online-hosted page behavior, participant/session data, timing, audio device, render/start actions.

2. Trace the contract before editing.
   - Find existing IDs, event listeners, API endpoints, dataclasses, render config rows, and tests with `rg`.
   - Reuse local patterns before adding abstractions.
   - Preserve unrelated dirty worktree changes. Stage selectively when needed.

3. Keep the UI lab-oriented.
   - Build dense, quiet researcher controls rather than marketing/AI-dashboard surfaces.
   - Prefer explicit control groups, segmented buttons, tables, status chips, splitters, and direct manipulation.
   - Do not add visible instructional prose when the control itself can be clear.
   - Keep one-page navigation and direct panel resizing behavior intact.
   - Treat one-page website sections as workflow segments. Each segment should represent one natural user decision stage, and panels should stay localized to the segment where that decision is made.
   - Do not let unrelated controls share a segment just because they fit on screen. Move participant/session/run controls, previews, backend feedback, or review panes to the functional segment that owns them.
   - For the PPS dashboard, preserve the sequence: profile decision, looming-stimulus builder, baseline strategy, trial sequence design, trial-block design, run setup, then review. The looming-stimulus builder owns trajectory controls, preview, Stimulus Type Selection, source staging/baking, baked-source cards, and bake/render feedback. The baseline segment owns only the compact forced strategy choice: exactly one checkbox/card for no baseline, matched SOA anchors, sound-onset/min-SOA anchors, sound-offset/max-SOA anchors, or profile-defined custom timing anchors. Do not show baseline percentages, timing editors, trial counts, or duration analytics in Segment 3. Trial Sequence Design owns only within-trial sequence and randomization logic: preloaded custom clips/fixed clips, row-level sequence events, jitter timing events, and source selection inside randomizer events. Keep it visually minimal with plus controls where rows/events can be added and small `x` controls to remove them. Do not put repetitions, block count, SOA count math, per-source counters, baseline counters, catch counters, or total-trial summaries in Segment 4. Trial-Block Design owns SOA values, repetitions, block count, block-level counterbalancing, catch/baseline/audio-tactile amounts, trial preview, and duration/count summaries. Segment 4 rows are left-to-right event sequences; allow fixed events, jitter events, and one or more randomizer events in sequence. Jitter events are silent timing gaps with comma-separated millisecond values, assigned in a balanced cycle across generated rows and recorded in CSV/manifests without multiplying SOA/source trial counts.
   - In Stimulus Type Selection, use the researcher-facing categories `Generate Looming Noise`, `Custom Looming Tone`, and `Custom Audio Clip`. Generated looming noise and custom looming tones are staged for backend baking; custom audio clips are preserved local source clips for later trial use rather than spatialized looming stimuli.
   - In Trial Designer, use `Custom Clips` for fixed audio row elements. Do not call this area `Instruction Snippets`, and do not expose a separate instruction-snippet import button. Study 5 should preload inhale/exhale custom clips so row assembly can use them immediately.
   - Preserve the active Study 5 preload shape: four frontal looming noise sources in the generated/prebaked source inventory plus two gray non-looming custom clips in Trial Designer. Do not store Study 5 pink/blue/white/brown looming WAVs as custom audio clips in the active design.
   - Keep the profile DOI box DOI-only. For published-study preloads, place any replication caveat in a separate notice below the DOI: these profiles recreate reported study parameters within the local toolkit and are not the authors' exact original stimulus set.
   - For durable preload/catalog data, mirror this segmentation in local folders. Profile-level metadata belongs in `01_profile`; prebaked source WAVs, source recipes, tone types, and trajectory snapshots belong in `02_looming_stimuli`; baseline/catch defaults belong in `03_baseline_strategy`; trial rows/SOAs/snippets belong in `04_trial_designer`; participant/randomization defaults belong in `05_run_setup`.
   - When published-profile metadata declares representable motion-direction factors, expand them into concrete preload source assets and trajectory snapshots. Do not let a paper with left-to-right/right-to-left, looming/receding, front/back, rear-left/rear-right, or spherical 3D boundary paths display as one representative baked trajectory unless the missing direction is explicitly unsupported and documented. If direction is already encoded by the baked source assets, prevent scheduler double-crossing by treating the source trajectory as the direction factor.
   - Treat baked/preloaded source cards as an experiment stimulus inventory. When adding or editing source cards, preserve each source's own `trajectory_snapshot`; do not make baked-source displays silently follow later global trajectory edits. Keep source-card visuals compact and metadata-oriented, arrange them as a wrapped grid when space allows, color-code cards by noise/tone type, and let imported/custom audio expose a persisted box-color/tone selector. Render source trajectory representations inside the embedded Three.js trajectory viewer in both 2D and 3D modes, using color-coded overlay paths and parallel multi-color traces when different tones share one trajectory.
   - Treat each Trial Designer row as one row-level trial type: all fixed, jitter, and randomizer events in the row define that unique `trial_type_label`, and rows are scheduled sequentially top-to-bottom inside the block. Keep visible labels aligned with this mental model even if internal schema names still use `trial_strips`.

4. Keep source and file handling local.
   - File selection may happen in browser, but import/store/process must happen through the local companion backend.
   - Store local copies under ignored paths such as `local_data/` or `artifacts/`.
   - Never upload stimulus files, participant data, generated WAVs, or experiment artifacts to hosted services.
   - Distinguish baked/imported material from material the backend should transform.
   - Do not expose full local paths as ordinary editable dashboard text. Keep paths as hidden payload metadata and provide explicit local companion actions such as `Open Folder` when researchers need to inspect files on the PC.

5. Update both sides of every new control.
   - HTML: visible control, stable IDs, accessible grouping.
   - CSS: responsive dimensions, no overlap, no one-note palette drift.
   - JS: render existing state, collect payloads, handle events, keep live previews synchronized.
   - Backend: validate payloads, persist schema fields, preserve backward-compatible defaults.
   - Render/session code: record provenance in manifests/QC when behavior changes.

6. Validate like a product surface.
   - Run targeted Python tests for API/schema/render behavior.
   - Smoke-test the dashboard in a browser with the local backend running.
   - For viewer or canvas changes, verify the page is nonblank and interaction updates fields.
   - For static/hosted changes, push or otherwise update the GitHub Pages-facing files and verify the hosted URL with cache-busting query params.

7. Update project memory.
   - Update `For-AI/project_context.md` for durable architecture/boundary changes.
   - Update `For-AI/evolving_goals.md` for active GUI direction and decisions.
   - Update `For-AI/agent_update_protocol.md` when the maintenance workflow itself changes.
   - Keep memory concise and free of private paths, generated data, participant data, and unsupported claims.

## Transfer Pattern

For other projects, map the same roles:

- Static dashboard assets: HTML/CSS/JS files shown to the user.
- Local companion backend: the trusted process that can read files, run native tools, and write local artifacts.
- Domain engine: renderers, runners, validators, schedulers, or other heavy-lift modules.
- Hosted page: optional static UI that must connect back to local companion software.

The safe design pattern is: browser collects decisions, backend validates and acts, domain engine does the heavy work, manifests record what happened.

For UI layout transfer, use workflow segmentation before panel placement:

- Identify the user's required decision stages.
- Give each stage one anchored website section.
- Put only the controls, previews, and status feedback needed for that stage inside that section.
- Keep later-stage setup and review panels lower on the page, even if they are technically related to earlier data.
- Keep navigation, validation gates, and "continue" actions aligned with these same stages.
- When a decision changes the meaning of later counts, make it an earlier explicit stage rather than hiding it in the later editor. For the PPS dashboard, baseline strategy belongs before Trial Sequence Design because it changes the interpretation of later row composition. Trial Sequence Design must remain count-free; Trial-Block Design is where SOAs, repetitions, blocks, catch/baseline/audio-tactile amounts, and duration/trial-count summaries are shown. Jitter values in Trial Sequence Design are sequence timing choices, not trial-count choices: they should be balanced across planned rows and carried into CSV/manifests without crossing every SOA value.

## References

Read `references/orchestrator-checklist.md` when planning a substantial dashboard change or when the change involves API contracts, file imports, hosted pages, render/session behavior, or privacy boundaries.
