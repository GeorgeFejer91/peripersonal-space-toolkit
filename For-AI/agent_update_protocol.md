# Agent Update Protocol

`For-AI/` is tracked project memory. It is not a private scratchpad.

## Required Session Loop

Every AI agent working in this repository must:

1. Read `AGENTS.md`.
2. Read `For-AI/README.md`.
3. Consult `project_context.md` and `evolving_goals.md` before planning or editing.
4. Do the requested work.
5. Before finalizing, decide whether the work was substantive.
6. If substantive, update the relevant `For-AI/` file.
7. In the final response, state whether `For-AI/` was updated.

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
