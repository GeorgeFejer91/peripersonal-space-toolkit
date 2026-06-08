from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from peripersonal_space_toolkit.design import (
    AudioFileSpec,
    NoiseDefinition,
    ProtocolSpec,
    TrialStripElementSpec,
    TrialStripSpec,
    block_trial_rows,
    default_design,
    design_from_dict,
    design_to_dict,
    export_protocol_csv,
)
from peripersonal_space_toolkit.session_runner import prepare_run_package


def _filmstrip_design(source_count: int = 4):
    design = default_design()
    colors = ["pink", "blue", "white", "brown"][:source_count]
    design.noises = [NoiseDefinition(label=color.title(), noise_type=color) for color in colors]
    design.prestimulus_files = [
        AudioFileSpec(label="Inhale", path="local_data/audio/inhale.wav", motion_mode="stationary"),
        AudioFileSpec(label="Exhale", path="local_data/audio/exhale.wav", motion_mode="stationary"),
    ]
    source_labels = [noise.label for noise in design.noises]
    design.protocol = ProtocolSpec(
        repetitions_per_condition=1,
        soa_values_ms=[100, 200, 300, 400, 500],
        spatial_values_cm=[],
        pair_spatial_values_with_soas=False,
        auditory_motion_directions=["looming"],
        tactile_sites=["hand"],
        catch_trial_percentage=0.0,
        include_baseline_trials=False,
        respiratory_phases=[],
        blocks=1,
        participants=2,
        random_seed=20250604,
        trial_strips=[
            TrialStripSpec(
                strip_id="inhale-row",
                label="Inhale event",
                elements=[
                    TrialStripElementSpec(kind="fixed_audio", label="Inhale", source_label="Inhale"),
                    TrialStripElementSpec(kind="looming_stimulus", label="Looming Stimulus", source_labels=source_labels, randomized=True),
                ],
            ),
            TrialStripSpec(
                strip_id="exhale-row",
                label="Exhale event",
                elements=[
                    TrialStripElementSpec(kind="fixed_audio", label="Exhale", source_label="Exhale"),
                    TrialStripElementSpec(kind="looming_stimulus", label="Looming Stimulus", source_labels=source_labels, randomized=True),
                ],
            ),
        ],
    )
    return design


def test_trial_strips_round_trip_and_interleave_within_block_event_sequences():
    design = design_from_dict(design_to_dict(_filmstrip_design()))

    rows = block_trial_rows(design)

    assert len(rows) == 2 * 4 * 5
    assert rows[0]["trial_strip_label"] == "Inhale event"
    assert rows[1]["trial_strip_label"] == "Exhale event"
    assert rows[2]["trial_strip_label"] == "Inhale event"
    assert rows[3]["trial_strip_label"] == "Exhale event"
    assert sum(1 for row in rows if row["trial_strip_label"] == "Inhale event") == 20
    assert sum(1 for row in rows if row["trial_strip_label"] == "Exhale event") == 20
    assert all(" | " in row["sequence_labels"] for row in rows)


def test_trial_strips_repetitions_and_catches_disable_tactile():
    design = _filmstrip_design(source_count=1)
    design.protocol.soa_values_ms = [250]
    design.protocol.repetitions_per_condition = 2
    design.protocol.catch_trial_percentage = 50

    rows = block_trial_rows(design)
    noncatch = [row for row in rows if row["trial_type"] == "Audio-Tactile"]
    catches = [row for row in rows if row["trial_type"] == "Catch"]

    assert len(noncatch) == 4
    assert len(catches) == 4
    assert all(row["tactile_enabled"] is True for row in noncatch)
    assert all(row["tactile_enabled"] is False for row in catches)


def test_filmstrip_protocol_csv_and_block_manifest_include_sequence_columns(tmp_path: Path):
    design = _filmstrip_design(source_count=1)
    design.protocol.soa_values_ms = [250]
    design.protocol.participants = 1
    render_dir = tmp_path / "render"
    render_dir.mkdir()
    wav_path = render_dir / "looming_pink.wav"
    sf.write(wav_path, np.zeros((441, 3), dtype=np.float32), 44100)

    protocol_path = tmp_path / "protocol.csv"
    export_protocol_csv(design, protocol_path)
    protocol_rows = list(csv.DictReader(protocol_path.open(encoding="utf-8")))

    assert protocol_rows[0]["trial_strip_label"] in {"Inhale event", "Exhale event"}
    assert protocol_rows[0]["sequence_labels"]
    assert protocol_rows[0]["tactile_enabled"] == "True"

    package = prepare_run_package(
        design,
        "P001",
        render_dir=render_dir,
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 6, 7, 12, 0, 0),
    )
    block_rows = list(csv.DictReader(package.blocks[0].manifest_path.open(encoding="utf-8")))

    assert "Trial_Strip_Label" in block_rows[0]
    assert "Sequence_Labels" in block_rows[0]
    assert "Tactile_Enabled" in block_rows[0]
    assert block_rows[0]["Sequence_Labels"]
