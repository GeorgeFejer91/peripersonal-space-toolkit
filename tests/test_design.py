from __future__ import annotations

from pathlib import Path

import pytest

from peripersonal_space_toolkit import designer_app
from peripersonal_space_toolkit.design import (
    default_design,
    export_protocol_csv,
    export_trajectory_csv,
    load_design,
    protocol_summary,
    save_design,
    trajectory_points,
    validate_design,
)
from peripersonal_space_toolkit.templates import load_templates


def test_default_design_matches_four_second_study5_timing():
    design = default_design()
    assert validate_design(design) == []
    assert design.trajectory.movement_duration_s == 3.0
    assert design.trajectory.total_duration_s == 4.0
    points = trajectory_points(design.trajectory, samples=5)
    assert points[0]["radius_m"] == pytest.approx(1.1)
    assert points[-1]["radius_m"] == pytest.approx(0.1)


def test_design_json_round_trip_and_trajectory_export(tmp_path: Path):
    design = default_design()
    design_path = tmp_path / "design.json"
    csv_path = tmp_path / "trajectory.csv"
    save_design(design, design_path)
    loaded = load_design(design_path)
    assert loaded.noises[0].noise_type == "pink"

    export_trajectory_csv(loaded, csv_path, samples=7)
    text = csv_path.read_text(encoding="utf-8")
    assert "time_s,radius_m,azimuth_deg" in text
    assert len(text.strip().splitlines()) == 8


def test_protocol_summary_and_export_use_repetitions_soas_spatial_values_and_catches(tmp_path: Path):
    design = default_design()
    design.protocol.repetitions_per_condition = 2
    design.protocol.soa_values_ms = [100, 300]
    design.protocol.spatial_values_cm = [90.0, 70.0]
    design.protocol.pair_spatial_values_with_soas = True
    design.protocol.catch_trial_percentage = 20.0
    design.protocol.include_baseline_trials = True
    design.protocol.respiratory_phases = ["Inhale"]
    design.protocol.blocks = 3
    design.protocol.participants = 4

    summary = protocol_summary(design)
    assert summary["audio_tactile_trials"] == 16
    assert summary["baseline_trials"] == 4
    assert summary["catch_trials"] == 5
    assert summary["total_trials"] == 25
    assert summary["trials_per_block"] == 9
    assert summary["total_participant_trials"] == 100

    protocol_path = tmp_path / "protocol.csv"
    export_protocol_csv(design, protocol_path)
    text = protocol_path.read_text(encoding="utf-8")
    assert "Audio-Tactile" in text
    assert "Catch" in text


def test_protocol_can_use_full_factorial_soa_by_spatial_values():
    design = default_design()
    design.noises = design.noises[:1]
    design.protocol.soa_values_ms = [100, 300]
    design.protocol.spatial_values_cm = [40.0, 80.0, 120.0]
    design.protocol.pair_spatial_values_with_soas = False
    design.protocol.include_baseline_trials = False
    design.protocol.catch_trial_percentage = 0.0
    design.protocol.respiratory_phases = ["Any"]
    summary = protocol_summary(design)
    assert summary["audio_tactile_trials"] == 6
    assert summary["total_trials"] == 6


def test_all_study_templates_load_and_summarize():
    templates = load_templates(Path(__file__).resolve().parents[1] / "study_templates")
    assert len(templates) >= 5
    verified = {template.verification_status for template in templates}
    assert "verified" in verified
    assert "partial" in verified
    for template in templates:
        warnings = validate_design(template.design)
        assert all("Unsupported" not in warning for warning in warnings)
        summary = protocol_summary(template.design)
        assert summary["total_trials"] > 0
        assert template.citation
        assert template.source_url


def test_designer_parser_can_be_built_without_opening_window():
    parser = designer_app.build_arg_parser()
    args = parser.parse_args(["--design", "configs/stimulus_design.example.json"])
    assert args.design.name == "stimulus_design.example.json"
