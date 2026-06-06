# Agent Update Protocol

`For-AI/` is tracked project memory. It is not a private scratchpad.

## Required Session Loop

Every AI agent working in this repository must:

1. Read `AGENTS.md`.
2. Read `For-AI/README.md`.
3. Consult `project_context.md` and `evolving_goals.md` before planning or editing.
4. Do the requested work.
5. If the work changes the HTML/dashboard web GUI, update the matching online website/static GitHub Pages version in the same change set before finalizing.
6. Before finalizing, decide whether the work was substantive.
7. If substantive, update the relevant `For-AI/` file.
8. In the final response, state whether `For-AI/` was updated.

## What Counts As Substantive

Update `For-AI/` after changes to:

- project aims or scope
- GUI behavior or user workflows
- data schemas, saved settings, templates, or config contracts
- experiment runner behavior
- stimulus generation, decoding, analysis, or event capture
- privacy/publication boundaries
- tests, release checks, or repository structure
- literature-derived goals or supported paradigms

## Web GUI Website Sync

Every change to the new HTML/dashboard web GUI must be reflected on the online website version before the work is considered complete. Future agents should not stop after updating only the local dashboard files. They must also update the hosted/static GitHub Pages-facing files or deployment artifact used by the public website, then verify that the website version still uses relative dashboard/viewer assets and talks to the local companion backend rather than trying to run timing-sensitive experiments in browser JavaScript.

## Local Browser Orchestration Boundary

The HTML dashboard, whether launched locally or served from GitHub Pages, is only an orchestration surface. It must not upload stimulus files, participant data, generated WAVs, or experiment artifacts to an online service. Browser actions that select files, import audio, render stimuli, prepare sessions, stress audio, or launch Focus Mode must be executed by the local companion/backend on the research PC, with files stored in ignored local folders such as `local_data/` or `artifacts/`.

## What To Update

- Update `evolving_goals.md` for new decisions, changed priorities, or backlog changes.
- Update `project_context.md` when the current architecture, scope, or product boundaries change.
- Update this protocol if the maintenance rules themselves change.
- Update `README.md` only when human-facing setup or repo navigation changes.

## What Not To Store

Do not store:

- participant data
- raw recordings
- generated artifacts
- secrets or credentials
- private local paths
- unsupported claims about published studies
- long chat transcripts

Keep entries concise and operational. The goal is to preserve current intent so future agents do not rediscover the same decisions from scratch.
