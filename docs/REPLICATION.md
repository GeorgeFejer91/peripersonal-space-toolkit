# Replication Guide

## 1. Prepare Inputs

The repository includes the small reusable seed assets, spoken instruction WAVs, click cue, master blocks, and deidentified sample analysis files.

The following files are expected locally if you regenerate the full locked Study 5 stimulus set:

- `assets\0. Head-Related Impulse Response (HRIR) model\FABIAN_HRIR_measured_HATO_0.sofa`
- optional pregenerated looming files in `assets\1. Looming Stimuli\`
- optional licensed background music

## 2. Generate Stimuli

Check paths without writing files:

```powershell
.\.venv\Scripts\pps-generate.exe --dry-run
```

Generate from the HRIR file:

```powershell
.\.venv\Scripts\pps-generate.exe --participants 50
```

Or use pregenerated looming WAVs:

```powershell
.\.venv\Scripts\pps-generate.exe --use-pregenerated-looming --participants 50
```

Generated stimuli are written under `artifacts\stimuli\` and are intentionally ignored by Git.

## 3. Design Custom Stimuli

To draft variants before generating or piloting them:

```bat
windows\Launch_Stimulus_Designer.bat
```

The designer has separate `Stimulus Design`, `Trial Assembler`, and `Experiment Runner` tabs. It uses the fixed FABIAN/TU SOFA HRIR path under the hood, while the GUI focuses on experimenter-facing controls: study profile, noise types, custom looming and prestimulus audio files, `Starting Point`/`End Point` distance in cm, full 0-360 degree endpoint rotation around the listener, movement timing, 2D/3D trajectory preview, SOA/spatial timing, trial assembly, participant session preparation, Focus Mode running, and immediate review/QC. The default trajectory is horizontal on the listener head/ear plane; endpoint height offsets are available only in deliberate `3D orbit` mode. Block contents stay fixed across participants, while participant block order is randomized or counterbalanced from the saved seed. Use `Save Settings` for local repeated runs, and keep published JSON design files with your protocol materials when running a non-default variant.

The `Render Looming WAVs` action and `pps-render-design` create one WAV per noise definition with channels 0/1 as binaural audio and channel 2 as the vibrotactile cue track. If a native 3DTI executable is installed, the adapter uses it. If not, the bundled Python SOFA/FABIAN reference renderer still produces WAVs from the same saved trajectory/SOA design and labels the manifest as `rendered_reference`.

## 4. Run The Experiment

For the current Qt-designed experiment, use the `Experiment Runner` tab. It prepares `local_data\sessions\<participant_id>_<timestamp>\`, writes the design, protocol schedule, session manifest, per-block manifests/WAVs, event CSV/XDF, and immediate analysis outputs.

The primary reaction-time source is the direct event/LSL timing stream. Physical loopback recordings are retained as backup QC, including the low-gain tactile-channel response marker for recovering mouse-click timing if event logging fails.

The legacy runner remains available for the locked Study 5 flow:

```bat
windows\Launch_PPS_App.bat
```

Use `--stimuli-dir`, `--instructions-dir`, `--recordings-dir`, or `--background-music` to override paths for a specific lab setup.

## 5. Decode Recordings

```powershell
.\.venv\Scripts\pps-decode.exe --input-dir local_data\loopback_recordings --output-dir artifacts\decoded
```

Decoded outputs are written under `artifacts\decoded\`.

## 6. Analyze Sample Data

```powershell
.\.venv\Scripts\pps-analyze.exe --sample
```

This writes a compact facilitation summary to `artifacts\analysis\sample_facilitation_summary.csv`.
