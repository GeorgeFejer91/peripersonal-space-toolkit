from __future__ import annotations

from pathlib import Path

import pytest

from peripersonal_space_toolkit import designer_app
from peripersonal_space_toolkit.design import (
    default_design,
    export_trajectory_csv,
    load_design,
    save_design,
    trajectory_points,
    validate_design,
)


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


def test_designer_parser_can_be_built_without_opening_window():
    parser = designer_app.build_arg_parser()
    args = parser.parse_args(["--design", "configs/stimulus_design.example.json"])
    assert args.design.name == "stimulus_design.example.json"
