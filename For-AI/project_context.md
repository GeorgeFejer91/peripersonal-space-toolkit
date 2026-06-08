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
- `assets/preloads/` contains the public preload asset inventory and the segment-mirrored preload catalog. Each preload profile has its own folder with `01_profile/`, `02_looming_stimuli/`, `03_baseline_strategy/`, `04_trial_designer/`, and `05_run_setup/` so the local file-cabinet structure mirrors the HTML dashboard workflow. `02_looming_stimuli/` contains approved/generated auditory-only prebaked WAVs plus source and trajectory metadata. If a profile declares representable direction factors such as left-to-right/right-to-left, looming/receding, front/back, rear-left/rear-right, or spherical 3D boundary directions, the preload catalog should expand them into separate source assets and trajectory snapshots rather than displaying only one representative path. If those assets already encode direction, schedule generation should use the source label/trajectory as the direction factor and avoid crossing the same directions again.
- `src/peripersonal_space_toolkit/assets/` contains packaged app identity assets such as the PPS Toolkit SVG/PNG/ICO logo used by Qt windows, the dashboard desktop shortcut, and the local dashboard favicon.
- `data/sample/` contains deidentified sample CSVs.
- `artifacts/`, `local_data/`, and `models/` are ignored local/generated folders.

## GUI Direction

The GUI should be researcher-friendly and should not expose implementation details as primary design choices. Users should define the experiment they want; the toolkit should handle reproducible mechanics such as randomization, participant block-order schedules, and validation in the background.

Randomization is documentation-relevant, not a normal GUI tool. The intended default is no-immediate-repeat trial ordering within blocks and counterbalanced participant block order, supporting any number of user-defined blocks.

The standard researcher-facing GUI is now the local HTML dashboard. It is launched with `pps-dashboard` or `windows\Launch_HTML_Dashboard.bat`, binds to `127.0.0.1`, opens in the user's default browser, and uses a small FastAPI backend to call the existing Python design, render, session-preparation, audio-stress, and native Focus Mode paths. This browser dashboard is not an online service and should not move validated participant timing into browser JavaScript; use `pps-focus` for timing-sensitive native participant runs from prepared session manifests.

The dashboard should behave as a one-page local app: a fixed floating left rail, smooth section navigation, and user-adjustable panel sizing through direct workspace splitters/gutters and panel-edge handles rather than left-rail sliders. Custom mode is not an open-ended freeform page; selecting `Custom design (define manually)` should force the researcher through Study Profile, Stimulus Design, Baseline Strategy, Trial Assembly, Run Preparation, and Review in order. Render/prepare/run actions must stay locked until the custom design contains the minimum runnable profile fields.

The HTML dashboard should be organized as sequential decision segments rather than a mixed dashboard. Segment 1 is the profile decision: published preload versus custom design and study-level naming. Segment 2 is the looming stimuli builder: trajectory numeric controls, 2D/3D preview, source staging/baking, baked-source lists, and backend feedback about local bake/render progress. Segment 3 is baseline strategy: a compact forced choice of exactly one established baseline tactic, using mutually exclusive checkbox/cards for no baseline, matched SOA anchors, sound-onset/min-SOA anchors, sound-offset/max-SOA anchors, or profile-defined custom timing anchors. It should not show trial amounts, percentages, duration estimates, or a long analytics panel. Segment 4 is Trial Sequence Design: preloaded custom clips/fixed clips plus row-level trial sequence and randomization logic only. It should stay visually minimal, using plus affordances where rows/events can be added and small `x` controls for removals. Do not put repetitions, block count, SOA count math, per-source counters, baseline counters, catch counters, or trial-total summaries in Segment 4. Fixed events select one saved custom clip and always play it at that sequence position. Jitter events are silent timing gaps with comma-separated millisecond values, assigned in a balanced cycle across generated rows and recorded in CSV/manifests without multiplying SOA/source trial counts. Randomizer events select one or more previously created stimulus sources and define the randomization source set; rows may contain more than one randomizer event when the researcher is building a longer left-to-right sequence. The backend stores this as `protocol.trial_strips` with `fixed_audio`, `jitter`, and `looming_stimulus` elements. Rows define row-level trial types: all events in one row create one unique `trial_type_label`, and rows are scheduled sequentially top-to-bottom inside each block. Segment 5 is Trial-Block Design: SOA values, repetitions, block count, block-level counterbalancing, catch/baseline/audio-tactile amounts, trial preview, and duration/count summaries. Participant count, participant ID, session preparation, participant order preview, jobs, and review stay lower in Run Setup and Review.

The same dashboard can be published as a GitHub Pages static site from the repository root. In hosted mode, the page uses relative static assets and connects to the local companion backend at `http://127.0.0.1:8766` by default. The companion backend is still the only trusted process allowed to render, prepare sessions, stress audio, and launch Focus Mode. GitHub Pages must not be treated as an installer or timing engine; it can offer a software download/setup link and then communicate with the local backend after the user starts it.

The browser dashboard is an orchestrator only. It must not upload stimulus files, participant data, generated WAVs, or experiment artifacts to an online service. File-selection/import controls should hand the chosen file to the local companion backend, which stores local copies under ignored local paths and then uses those local paths in the design/render/session pipeline.

Imported dashboard audio sources must distinguish dry tones that the backend spatializes along the selected trajectory from already looming/control audio that should be preserved as baked local audio.

Audio generation is a pre-run workflow, not a participant-run workflow. The dashboard should let researchers bake looming auditory stimuli early from the selected trajectory and source material through the local 3DTI/reference backend. This bake stage is auditory-only/binaural; tactile cue channels are not part of the baked source stimulus and should be introduced later from the trial/SOA schedule during final session or block preparation. Each baked or preloaded stimulus source should retain a source-level `trajectory_snapshot` so the GUI can show the actual trajectories used in the experiment, even if the researcher later edits the global trajectory controls. Native participant timing should consume already prepared WAVs and manifests rather than generating, spatializing, or assembling stimuli during the timed run.

Preload profiles should advertise their asset state through `assets/preloads/preload_inventory.json`. The inventory is safe for GitHub/GitHub Pages publication because it contains hashes, relative paths, source recipes, trajectory snapshots, segment paths, and retrieval policy, not participant data. The local companion backend verifies, downloads, or bakes assets; the browser surface only displays the status and requests the local action. Every preload profile should have a file-cabinet catalog under `assets/preloads/<template_id>/`, with segment folders matching the dashboard workflow. Use `tools/build_preload_catalog.py` to rebuild the catalogs and inventory after template/source changes. Study 5 is the working local profile and ships with exactly four active frontal looming noise sources under `assets/preloads/study5_box_breathing_pps/02_looming_stimuli/`; in the active design these are `NoiseDefinition` rows with `prebaked_path`, not custom audio clips. Its bundled spoken instruction WAVs under `assets/breathing/` include both synthetic British English Kokoro `bf_emma` assets and decoded original Study 5 instruction audio variants; raw MP3s and local source paths stay out of Git. The active Study 5 dashboard preload should expose exactly two non-looming custom clips, `Inhale instruction` and `Exhale instruction`, as Trial Designer fixed clips. The Looming Stimuli Builder owns trajectory/source baking only. All preload profiles should load with source-level trajectory inventory available to the embedded Three.js trajectory preview; if older template JSON lacks source-level snapshots, the local companion may fill them from the profile trajectory at load time. Source cards should remain compact inventory records with hidden path metadata plus visible local companion actions such as Open Folder; full local paths should not be shown as editable dashboard text. 2D and 3D trajectory representations belong inside the trajectory viewer canvas.

The PySide6/Qt designer remains available as `pps-design` / `windows\Launch_Stimulus_Designer.bat` for comparison and fallback. Keep its nested `QSplitter` workspaces and embedded local Three.js trajectory viewer working, but new researcher-facing workflow polish should prefer the HTML dashboard unless the user asks for Qt specifically.

Published-study profiles should look and behave like paper-level preloads, not anonymous parameter presets. The GUI should show citation-like author/year/title labels, keep the current/selected paper annotation visible, and allow BibTeX/CSL JSON citation export from template metadata. In the HTML dashboard, the DOI box itself should contain only the clickable DOI URL, and a separate notice below it should remind researchers that published-study preloads are local recreations of reported study parameters inside this toolkit, not the exact original stimulus set used by the authors.

## Privacy And Publication Boundary

The public repo is a toolkit plus deidentified sample-data package. It is not a full study archive. Before publishing, run the release audit and tests. Do not weaken release safeguards without a clear reason and corresponding documentation update.
