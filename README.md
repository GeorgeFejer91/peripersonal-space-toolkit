# Peripersonal Space Toolkit

A Windows-ready toolkit for running and reproducing the Study 5 audio-tactile peripersonal-space experiment. The repository packages the experiment runner, stimulus-generation pipeline, decoding helpers, small deidentified sample data, and Kokoro-generated spoken instruction assets.

The default layout keeps source files public and keeps participant data local. Runtime recordings, demographics, generated stimuli, and model downloads are written to ignored folders.

## Quick Start On Windows

1. Open PowerShell in the repository root.
2. Run:

```powershell
.\windows\Setup_Windows_App.ps1
```

3. List audio devices:

```bat
windows\List_Audio_Devices.bat
```

For rendered binaural+tactile stimuli, verify one synchronized 3+ channel output
stream:

```bat
windows\Stress_Audio_Device.bat
```

4. Generate experiment stimuli. The standardized FABIAN/TU HRIR file is bundled
   under:

```text
assets\0. Head-Related Impulse Response (HRIR) model\FABIAN_HRIR_measured_HATO_0.sofa
```

Then run:

```powershell
.\.venv\Scripts\pps-generate.exe --participants 50
```

5. Launch the standard local dashboard:

```bat
windows\Launch_HTML_Dashboard.bat
```

The dashboard opens in your default browser from `127.0.0.1`. It is a local
researcher-facing UI for study/profile selection, custom designs, trajectory
controls, trial assembly, render, prepare, audio stress, native Focus Mode
launch, and review.

The same HTML interface can also be published as a static GitHub Pages site.
In that mode, start the trusted local companion backend first:

```bat
windows\Start_Website_Companion.bat
```

Then open the Pages URL. The hosted page connects back to
`http://127.0.0.1:8766` for local render/session/focus operations; the website
itself cannot silently install packages or run experiments without the local
companion. See [docs/GITHUB_PAGES_DASHBOARD.md](docs/GITHUB_PAGES_DASHBOARD.md).

Open the Qt stimulus designer for comparison:

```bat
windows\Launch_Stimulus_Designer.bat
```

Run the legacy locked Study 5 participant app directly only when you need that
compatibility path:

```bat
windows\Launch_PPS_App.bat
```

The designer can preload bundled published-study profiles from `study_templates\`; the current stress-test library contains 20 profiles that fill trajectory, timing, and noise fields while the standardized FABIAN HRIR renderer resource stays under the hood. See [docs/PARADIGM_LIBRARY.md](docs/PARADIGM_LIBRARY.md) and [docs/PUBLISHED_PARADIGM_STRESS_TEST.md](docs/PUBLISHED_PARADIGM_STRESS_TEST.md).

Optional: create a desktop shortcut for the launcher:

```powershell
.\windows\Create_Desktop_Shortcut.ps1
```

## Spoken Audio Assets

The bundled spoken instruction WAV files are generated with Kokoro ONNX and are exactly 4.000 seconds long at 44.1 kHz. To regenerate them:

```bat
windows\Regenerate_Spoken_Assets.bat
```

The Kokoro model files download into `models\kokoro\`, which is ignored by Git. Only the generated study WAV files and manifest are intended for publication.

## Public Commands

```powershell
pps-generate --dry-run
pps-generate --participants 50
pps-dashboard
pps-run --list-devices
pps-run
pps-design
pps-audio-stress --device-query Komplete
pps-latency-validate specs
pps-latency-validate calibrate --establish-baseline
pps-render-design --design study_templates\pfeiffer_2018_lateral_perihead_left_to_right.json --output-dir artifacts\rendered_pfeiffer --seed 2018
pps-decode --input-dir local_data\loopback_recordings
pps-analyze --sample
pps-focus --session-manifest local_data\sessions\P001_YYYYMMDD_HHMMSS\session_manifest.json
```

`pps-render-design` writes a render config, trajectory samples, QC CSV, manifest, and generated WAVs. It uses the native 3DTI executable when available; otherwise it uses the bundled Python SOFA/FABIAN reference renderer and marks the manifest as `rendered_reference`.

`pps-latency-validate` writes the Komplete/Woojer wiring plan and runs electrical loopback validation for the synchronized output 1/2/3 route. See [docs/EXPERIMENT_LATENCY_VALIDATION.md](docs/EXPERIMENT_LATENCY_VALIDATION.md).

`pps-dashboard` starts a local-only browser dashboard at `127.0.0.1` for researcher-facing design, render, prepare, and review decisions. The dashboard uses a fixed one-page navigation rail, adjustable preview/panel sizing controls, and a sequential custom-design workflow that blocks run actions until the minimum runnable experiment profile is filled in. The existing Qt designer remains available as `pps-design`; the timing-sensitive participant Focus Mode remains native/Python-backed through `pps-focus`.

Verify the bundled Pfeiffer-style profile and render handoff:

```powershell
python tools\verify_pfeiffer_profile.py
```

## One-Bundle Release

For a public archive or Zenodo deposit, create a reviewed source-and-assets bundle:

```powershell
python tools\make_release_bundle.py
```

The bundle includes the app source, Windows launch/setup scripts, study profiles,
the pinned 3DTI source snapshot, the bundled FABIAN SOFA file, attribution/license
notes, and a `bundle_manifest.json` with SHA256 hashes. It excludes local runtime
data, generated render outputs, downloaded model files, and private reference
archives.

## Repository Layout

```text
assets\breathing\        Kokoro-generated 4-second spoken WAVs
assets\click\            Click/tactile cue seed asset
assets\0. Head-Related...\FABIAN_HRIR_measured_HATO_0.sofa
                         Bundled standardized FABIAN/TU HRIR resource
assets\master_blocks\    Study block templates
configs\                 Example experiment and stimulus-design configs
data\sample\             Deidentified sample analysis CSVs
docs\                    Hardware setup, replication, privacy, Windows, protocol, and paradigm notes
For-AI\                  Project memory and required context for future AI agents
src\                     Python package and command entry points
study_templates\         Literature-backed preloadable study profiles
tests\                   Smoke and release-readiness tests
third_party\             Pinned third-party source snapshots and renderer wrapper boundary
tools\                   Asset generation and release audit scripts
windows\                 Ready-to-use Windows setup and launch scripts
```

## AI Agent Context

Future AI agents and maintainers should start with [AGENTS.md](AGENTS.md) and [For-AI/README.md](For-AI/README.md). The `For-AI\` folder records current project aims, scope, evolving goals, and update rules for keeping that context current.

## Privacy And Release Boundaries

Do not commit participant recordings, demographics, raw exports, or generated local experiment output. The ignored folders `local_data\`, `artifacts\`, and `models\` are intended for local use only. See [docs/hardware_setup.md](docs/hardware_setup.md), [docs/AUDIO_ROUTING_STRESS_TEST.md](docs/AUDIO_ROUTING_STRESS_TEST.md), [docs/replication_workflow.md](docs/replication_workflow.md), and [docs/privacy_boundary.md](docs/privacy_boundary.md). Run this before publishing a release:

```powershell
python tools\release_audit.py
python tools\make_release_bundle.py
pytest
```

## License

Source code is released under the MIT License. Deidentified sample data and documentation are released under CC BY 4.0 unless a file states otherwise. Third-party source snapshots and redistributable HRTF assets have their own license and attribution notes in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
