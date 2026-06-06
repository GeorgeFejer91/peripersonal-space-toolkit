from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from peripersonal_space_toolkit.design import ProtocolSpec, default_design
from peripersonal_space_toolkit.session_runner import (
    SessionRunnerController,
    prepare_run_package,
    preflight_run_package,
)


def _compact_design():
    design = default_design()
    design.noises = design.noises[:1]
    design.protocol = ProtocolSpec(
        repetitions_per_condition=1,
        soa_values_ms=[300],
        spatial_values_cm=[100.0],
        pair_spatial_values_with_soas=True,
        auditory_motion_directions=["looming"],
        tactile_sites=["hand"],
        catch_trial_percentage=0.0,
        include_baseline_trials=False,
        respiratory_phases=["Inhale"],
        blocks=1,
        participants=1,
        random_seed=20250604,
    )
    return design


def _render_dir(tmp_path: Path) -> Path:
    render_dir = tmp_path / "rendered"
    render_dir.mkdir()
    wav_path = render_dir / "looming_pink_frontal.wav"
    data = np.zeros((441, 3), dtype=np.float32)
    sf.write(wav_path, data, 44100)
    (render_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "schema": "pps-render-manifest.v1",
                "status": "rendered_reference",
                "wav_outputs": [{"path": str(wav_path), "sha256": "test"}],
            }
        ),
        encoding="utf-8",
    )
    return render_dir


def test_preflight_reports_missing_render_and_ready_state(tmp_path: Path):
    design = _compact_design()

    missing = preflight_run_package(design, "P001", render_dir=tmp_path / "missing")
    assert missing.participant_ready
    assert not missing.render_ready
    assert not missing.ready

    ready = preflight_run_package(design, "P001", render_dir=_render_dir(tmp_path))
    assert ready.render_ready
    assert ready.schedule_ready
    assert ready.ready
    assert ready.rendered_wavs[0].channels == 3


def test_prepare_run_package_writes_manifest_protocol_and_blocks(tmp_path: Path):
    design = _compact_design()
    package = prepare_run_package(
        design,
        "Subject 01",
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )

    assert package.participant_id == "Subject_01"
    assert package.session_dir.name == "Subject_01_20260102_030405"
    assert package.design_path.exists()
    assert package.protocol_path.exists()
    assert package.manifest_path.exists()
    assert len(package.blocks) == 1
    assert package.blocks[0].manifest_path.exists()
    assert package.blocks[0].wav_path.exists()

    manifest = json.loads(package.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "pps-run-session.v1"
    assert manifest["audio_route"]["channels"] == 3

    with package.blocks[0].manifest_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert rows[0]["Participant_ID"] == "Subject_01"
    assert rows[0]["Trial_Type"] == "Audio-Tactile"


class _MockAudioEngine:
    def __init__(self):
        self.played: list[str] = []
        self.stopped = False
        self.paused = False
        self.click_metadata: dict[str, object] = {}
        self.marker_gain = None
        self.recordings: list[str] = []
        self.on_audio_started = None

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None) -> bool:
        self.played.append(path)
        if audio_event_callback:
            audio_event_callback(
                {
                    "event_type": "audio_sample_zero",
                    "unix_time": 100.0,
                    "monotonic_time": 10.0,
                    "sample_index": 0,
                    "sample_rate": 44100,
                }
            )
            if self.on_audio_started:
                self.on_audio_started()
            if self.click_metadata:
                audio_event_callback(
                    {
                        "event_type": "response_marker_start",
                        "unix_time": 100.02,
                        "monotonic_time": 10.02,
                        "sample_index": 1,
                        "sample_rate": 44100,
                        "marker_channel": 2,
                        "marker_gain": self.marker_gain,
                        **self.click_metadata,
                    }
                )
        if progress_callback:
            progress_callback(0.0)
            progress_callback(0.01)
        return not self.stopped

    def stop(self) -> None:
        self.stopped = True

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def trigger_click(self, metadata=None, marker_gain=None) -> None:
        self.click_metadata = dict(metadata or {})
        self.marker_gain = marker_gain

    def start_recording(self, output_path=None) -> bool:
        self.recordings.append(str(output_path))
        return True

    def stop_recording(self, output_path=None, interrupted=False):
        return np.zeros((10, 3), dtype=np.float32)


def test_session_runner_controller_writes_events_and_analysis(tmp_path: Path):
    design = _compact_design()
    package = prepare_run_package(
        design,
        "P001",
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    engine = _MockAudioEngine()
    controller = SessionRunnerController(package, audio_engine=engine)
    engine.on_audio_started = lambda: controller.log_click(x=10, y=12)

    result = controller.run()

    assert result.completed
    assert engine.played == [str(package.blocks[0].wav_path)]
    assert result.events_csv.exists()
    assert result.events_xdf.exists()
    assert result.analysis_outputs["responses"].exists()
    assert result.analysis_outputs["timing_qc"].exists()
    events_text = result.events_csv.read_text(encoding="utf-8")
    assert "session_start" in events_text
    assert "audio_sample_zero" in events_text
    assert "tactile_onset" in events_text
    assert "response_marker_start" in events_text

    qc_text = result.analysis_outputs["timing_qc"].read_text(encoding="utf-8")
    assert "marker_minus_mouse_ms" in qc_text
    assert "0.05" in events_text
    assert result.recording_paths
