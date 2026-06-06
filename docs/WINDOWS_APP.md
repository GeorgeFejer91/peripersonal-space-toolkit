# Windows App Guide

This toolkit is designed to run as a local Windows experiment app from a cloned or downloaded repository.

## Setup

Run once:

```powershell
.\windows\Setup_Windows_App.ps1
```

The script creates `.venv`, installs the toolkit in editable mode, installs test and TTS extras, and creates local runtime folders.

## Launch

```bat
windows\Launch_HTML_Dashboard.bat
```

Create a desktop shortcut:

```powershell
.\windows\Create_Desktop_Shortcut.ps1
```

The shortcut uses the packaged PPS Toolkit icon and opens the standard local
browser dashboard. The Qt designer and native Focus Mode also set the same icon
at runtime so their window/taskbar entries do not fall back to the generic
Python icon.

Open the Qt stimulus design layer for comparison:

```bat
windows\Launch_Stimulus_Designer.bat
```

Run the legacy locked Study 5 participant app directly only when that
compatibility path is needed:

```bat
windows\Launch_PPS_App.bat
```

The HTML dashboard is the standard researcher-facing interface. It runs as a
local browser UI on `127.0.0.1`, launched by Python/FastAPI, and keeps
rendering, session packaging, audio stress tests, and participant running in
Python/native backend code rather than in an online service. The Qt designer
remains available as a comparison and fallback path. The dashboard keeps a
fixed floating one-page navigation rail, exposes panel sizing controls in that
rail, and uses a sequential custom-design workflow before run actions unlock.

The same HTML interface can be hosted on GitHub Pages. For that workflow, start
the local companion backend and use the website as the visible UI:

```bat
windows\Start_Website_Companion.bat
```

See [GitHub Pages Dashboard](GITHUB_PAGES_DASHBOARD.md).

Useful launch variants:

```bat
windows\Launch_PPS_App.bat --stimuli-dir artifacts\stimuli\10.Participant_Sequences
windows\Launch_PPS_App.bat --background-music C:\path\to\licensed_music.wav
windows\Launch_PPS_App.bat --recordings-dir D:\PPS_Recordings
windows\Launch_HTML_Dashboard.bat --port 8770
windows\Launch_HTML_Dashboard.bat --no-browser
windows\Start_Website_Companion.bat --web-origin https://example.github.io
```

## Audio Device Check

```bat
windows\List_Audio_Devices.bat
```

For rendered binaural+tactile files, run the silent routing stress test:

```bat
windows\Stress_Audio_Device.bat
```

The locked Study 5 runner uses the original stereo routing:

- left channel: tactile/vibration output
- right channel: auditory stimulus output

The configurable trajectory renderer writes generated looming WAVs with three
channels:

- channel 0: binaural left ear
- channel 1: binaural right ear
- channel 2: vibrotactile cue track

Those rendered files require one synchronized 3+ channel output device. On the
lab Komplete setup, use `Komplete Audio ASIO Driver`; the Windows `Output 1/2`
and `Output 3/4` pairs are legacy-only. See
[Audio Routing And Stress Test](AUDIO_ROUTING_STRESS_TEST.md).

The runner keeps one persistent ASIO output stream open and mixes instructions,
blocks, background audio, and click/tactile feedback into that stream. This is
required because the Komplete ASIO driver is effectively single-client in this
setup.

The app also supports WASAPI loopback recording on Windows when `pyaudiowpatch` is available.

## Local Data

The app writes runtime settings, demographics, and loopback recordings under `local_data\` by default. That folder is ignored by Git and should not be published.
