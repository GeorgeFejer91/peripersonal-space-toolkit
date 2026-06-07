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
   - For the PPS dashboard, preserve the sequence: profile decision, looming-stimulus builder, trial designer, then run/session review. The looming-stimulus builder owns trajectory controls, preview, source staging/baking, baked-source cards, and bake/render feedback; the trial designer owns filmstrip rows, SOAs, repetitions, blocks, catch percentage, and trial preview.

4. Keep source and file handling local.
   - File selection may happen in browser, but import/store/process must happen through the local companion backend.
   - Store local copies under ignored paths such as `local_data/` or `artifacts/`.
   - Never upload stimulus files, participant data, generated WAVs, or experiment artifacts to hosted services.
   - Distinguish baked/imported material from material the backend should transform.

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

## References

Read `references/orchestrator-checklist.md` when planning a substantial dashboard change or when the change involves API contracts, file imports, hosted pages, render/session behavior, or privacy boundaries.
