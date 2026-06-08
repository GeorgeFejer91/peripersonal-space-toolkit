from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from peripersonal_space_toolkit.dashboard_app import DashboardController, create_app
from peripersonal_space_toolkit.design import ProtocolSpec, default_design, design_to_dict, save_design


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


def _client(tmp_path: Path) -> TestClient:
    design_path = tmp_path / "design.json"
    render_dir = tmp_path / "rendered"
    render_dir.mkdir()
    wav_path = render_dir / "looming_pink_frontal.wav"
    sf.write(wav_path, np.zeros((441, 3), dtype=np.float32), 44100)
    (render_dir / "render_manifest.json").write_text(
        json.dumps({"schema": "pps-render-manifest.v1", "status": "rendered_reference"}),
        encoding="utf-8",
    )
    save_design(_compact_design(), design_path)
    controller = DashboardController(
        design_path=design_path,
        render_dir=render_dir,
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
    )
    return TestClient(create_app(controller))


def test_dashboard_static_assets_include_baseline_segment():
    dashboard_files = files("peripersonal_space_toolkit.dashboard")
    html = dashboard_files.joinpath("index.html").read_text(encoding="utf-8")
    app_js = dashboard_files.joinpath("app.js").read_text(encoding="utf-8")

    assert "Baseline Strategy" in html
    assert 'data-step-link="baseline"' in html
    assert 'id="baseline-enabled"' in html
    assert 'id="baseline-strategy"' in html
    assert 'id="baseline-options"' in html
    assert 'id="baseline-percent"' in html
    assert 'id="catch-percent"' in html
    assert 'id="baseline-soa-values"' in html
    assert "No baseline trials" in html
    assert 'type="checkbox" name="baseline-option"' in html
    assert "Use baseline trials" not in html
    assert "Matched SOA anchors" in html
    assert "Sound onset / min SOA" in html
    assert "Sound offset / max SOA" in html
    assert "Trial Sequence Design" in html
    assert "Trial-Block Design" in html
    assert "Default baseline %" not in html
    assert "Default catch %" not in html
    assert "Continue To Baseline" in html
    assert html.index("Baseline Strategy") < html.index("Trial Sequence Design") < html.index("Trial-Block Design")
    assert "BASELINE_STRATEGY_NOTES" in app_js
    assert "renderBaseline" in app_js
    assert "baselineCountEstimate" in app_js
    assert "blockCompositionEstimate" in app_js
    assert "baseline_trial_percentage" in app_js


def test_dashboard_saves_baseline_strategy_and_updates_summary(tmp_path: Path):
    client = _client(tmp_path)
    design = _compact_design()
    design.protocol.include_baseline_trials = True
    design.protocol.baseline_strategy = "soa_zero"
    design.protocol.baseline_trial_percentage = 20.0

    updated = client.post("/api/design", json={"participant_id": "P001", "design": design_to_dict(design)}).json()

    protocol = updated["design"]["protocol"]
    summary = updated["protocol_summary"]
    assert protocol["include_baseline_trials"] is True
    assert protocol["baseline_strategy"] == "soa_zero"
    assert protocol["baseline_trial_percentage"] == pytest.approx(20.0)
    assert summary["baseline_trials"] == 1
    assert summary["baseline_actual_percent"] == pytest.approx(50.0)
    assert "estimated_participant_minutes" in summary
