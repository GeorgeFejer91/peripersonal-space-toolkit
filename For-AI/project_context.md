# Project Context

## Aims

The toolkit should make audio-tactile PPS experiments reusable, reproducible, and publishable. The near-term aim is a ready-to-use Windows app for Study 5 and closely related audio-tactile PPS designs. The broader aim is a single program that can recreate published audio-tactile PPS paradigms by configuring stimuli, trial structure, runner behavior, and analysis settings.

## Audience

Primary users are cognitive neuroscience and psychology researchers who need to run, replicate, or adapt audio-tactile PPS experiments without editing Python scripts. Secondary users are developers and AI agents maintaining the toolkit.

## In Scope

- Generated or imported looming/prestimulus audio assets.
- Noise definitions, azimuth/elevation, SOFA/HRIR planning, trajectory radius/path/speed, and tactile cue timing.
- Trial design with repetitions, SOAs, spatial values, tactile sites, catch/baseline settings, blocks, and participant schedules.
- Automatic reproducible randomization in the background.
- Windows experiment running, audio/tactile channel routing, loopback recording, and local session outputs.
- Low-latency audio-device stress testing for synchronized binaural left/right plus tactile output.
- Loopback decoding and deidentified sample analysis.
- Study templates for published audio-tactile PPS paradigms when publication metadata is sufficient.
- Documentation and release audits that support a public GitHub repository.

## Out Of Scope

- Raw participant recordings or name-bearing outputs in Git.
- Generated participant WAVs and local session artifacts in Git.
- APKs, VR source code, or headset-specific app builds unless a future project explicitly adds them.
- Redistribution of SOFA/HRIR files, background music, proprietary sound sets, or other third-party assets unless rights are verified.
- Full visual/VR/social PPS reconstruction unless those details directly affect audio-tactile timing, spatial audio, tactile cues, responses, or analysis.

## Current Architecture

- `src/peripersonal_space_toolkit/` contains the Python package and command entry points.
- Public CLIs are `pps-generate`, `pps-run`, `pps-design`, `pps-dashboard`, `pps-focus`, `pps-render-design`, `pps-audio-stress`, `pps-decode`, and `pps-analyze`.
- `configs/` contains example experiment and stimulus-design settings.
- `Example-configs/` may contain reference archives for external-study stimulus-generation materials; verify redistribution rights before treating any bundled third-party WAVs or scripts as public release assets.
- `study_templates/` contains preloadable literature-backed template JSON files.
- `assets/` contains only small owned seed assets intended for publication.
- `src/peripersonal_space_toolkit/assets/` contains packaged app identity assets such as the PPS Toolkit SVG/PNG/ICO logo used by Qt windows, the dashboard desktop shortcut, and the local dashboard favicon.
- `data/sample/` contains deidentified sample CSVs.
- `artifacts/`, `local_data/`, and `models/` are ignored local/generated folders.

## GUI Direction

The GUI should be researcher-friendly and should not expose implementation details as primary design choices. Users should define the experiment they want; the toolkit should handle reproducible mechanics such as randomization, participant block-order schedules, and validation in the background.

Randomization is documentation-relevant, not a normal GUI tool. The intended default is no-immediate-repeat trial ordering within blocks and counterbalanced participant block order, supporting any number of user-defined blocks.

The standard researcher-facing GUI is now the local HTML dashboard. It is launched with `pps-dashboard` or `windows\Launch_HTML_Dashboard.bat`, binds to `127.0.0.1`, opens in the user's default browser, and uses a small FastAPI backend to call the existing Python design, render, session-preparation, audio-stress, and native Focus Mode paths. This browser dashboard is not an online service and should not move validated participant timing into browser JavaScript; use `pps-focus` for timing-sensitive native participant runs from prepared session manifests.

The dashboard should behave as a one-page local app: a fixed floating left rail, smooth section navigation, and user-adjustable panel sizing controls. Custom mode is not an open-ended freeform page; selecting `Custom design (define manually)` should force the researcher through Study Profile, Stimulus Design, Trial Assembly, Run Preparation, and Review in order. Render/prepare/run actions must stay locked until the custom design contains the minimum runnable profile fields.

The same dashboard can be published as a GitHub Pages static site from the repository root. In hosted mode, the page uses relative static assets and connects to the local companion backend at `http://127.0.0.1:8766` by default. The companion backend is still the only trusted process allowed to render, prepare sessions, stress audio, and launch Focus Mode. GitHub Pages must not be treated as an installer or timing engine; it can offer a software download/setup link and then communicate with the local backend after the user starts it.

The PySide6/Qt designer remains available as `pps-design` / `windows\Launch_Stimulus_Designer.bat` for comparison and fallback. Keep its nested `QSplitter` workspaces and embedded local Three.js trajectory viewer working, but new researcher-facing workflow polish should prefer the HTML dashboard unless the user asks for Qt specifically.

Published-study profiles should look and behave like paper-level preloads, not anonymous parameter presets. The GUI should show citation-like author/year/title labels, keep the current/selected paper annotation visible, and allow BibTeX/CSL JSON citation export from template metadata.

## Privacy And Publication Boundary

The public repo is a toolkit plus deidentified sample-data package. It is not a full study archive. Before publishing, run the release audit and tests. Do not weaken release safeguards without a clear reason and corresponding documentation update.
