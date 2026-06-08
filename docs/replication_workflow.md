# Replication Workflow

This workflow describes the public, reusable path for reproducing the Study 5 audio-tactile PPS task or adapting it with the stimulus designer.

## 1. Install

Run the Windows setup script from the repository root:

```powershell
.\windows\Setup_Windows_App.ps1
```

The script creates a local virtual environment and installs the package in editable mode.

## 2. Review Or Edit The Design

Open the stimulus designer:

```bat
windows\Launch_Stimulus_Designer.bat
```

Use the Stimulus Design tab for study profiles, noise types, custom looming files, prestimulus files, and trajectory geometry. The trajectory editor exposes `Starting Point` and `End Point` controls as distance from the listener in cm plus full 0-360 degree rotation around the listener, then previews the linear path in an embedded 3D scene. Study profiles preload published trajectory/noise parameters; the fixed FABIAN/TU SOFA HRIR path is handled under the hood. Use the Trial Assembler tab for SOAs, spatial values, repetitions, catch trials, baseline trials, block structure, generated trial previews, participant schedules, and background randomization. Use the Experiment Runner tab to render missing looming WAVs, prepare a participant session package, stress-test the preferred audio route, run Focus Mode, and review immediate event/response/QC outputs.

## 3. Generate Stimuli

Run a dry-run first:

```powershell
pps-generate --dry-run
```

Then generate participant sequences when required inputs are available:

```powershell
pps-generate --participants 50
```

Generated WAVs and participant sequences are written under `artifacts/`, which is ignored by Git.

## 4. Run The Experiment

For designed experiments, use the Qt `Experiment Runner` tab:

1. Enter `Participant`.
2. Press `Render` if the tab reports `Render required`.
3. Press `Prepare`.
4. Press `Stress Audio` on the test PC before real sessions.
5. Press `Start Focus Mode`.

The integrated runner writes session outputs under `local_data\sessions\<participant_id>_<timestamp>\`.

For designed experiments, use `events.csv` / `events.xdf` and the optional `PPSMarkers` LSL stream as the primary timing record. Hardware loopback WAVs are the fail-safe QC trace of what actually reached the physical outputs, including the low-level tactile-channel response marker.

The legacy Study 5 runner remains available:

List audio devices:

```powershell
pps-run --list-devices
```

Start the runner:

```powershell
pps-run
```

Local recordings, demographics, settings, and session outputs belong under `local_data/`, which is ignored by Git.

## 5. Decode Loopback Recordings

```powershell
pps-decode --input-dir local_data\loopback_recordings --output-dir artifacts\decoded
```

The decoder writes diagnostics and final CSV outputs under `artifacts/`.

## 6. Analyze The Deidentified Sample

```powershell
pps-analyze --sample
```

The sample command writes summary tables under `artifacts/analysis`.

## 7. Audit Before Publication

```powershell
python tools\release_audit.py
pytest
```

The audit checks required public files, seed assets, study templates, release boundaries, and private path leaks.
