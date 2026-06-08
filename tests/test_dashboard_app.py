from __future__ import annotations

import base64
import csv
import json
import math
import time
from importlib.resources import files
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from peripersonal_space_toolkit import dashboard_app
from peripersonal_space_toolkit.dashboard_app import DashboardController, create_app
from peripersonal_space_toolkit.design import (
    AudioFileSpec,
    ProtocolSpec,
    default_design,
    design_from_dict,
    design_to_dict,
    load_design,
    point_from_distance_rotation_height,
    save_design,
    trajectory_point_at_time,
)
from peripersonal_space_toolkit.render_backend import (
    DEFAULT_BACKEND_EXE,
    RenderResult,
    app_to_3dti_coordinates,
    build_render_config,
    render_design_with_3dti,
    sha256_file,
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
    sf.write(wav_path, np.zeros((441, 3), dtype=np.float32), 44100)
    (render_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "schema": "pps-render-manifest.v1",
                "status": "rendered_reference",
                "render_engine": "python-sofa-reference",
                "wav_outputs": [{"path": str(wav_path), "sha256": "test"}],
            }
        ),
        encoding="utf-8",
    )
    return render_dir


def _client(tmp_path: Path) -> TestClient:
    design_path = tmp_path / "design.json"
    save_design(_compact_design(), design_path)
    controller = DashboardController(
        design_path=design_path,
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
    )
    return TestClient(create_app(controller))


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(50):
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["status"] in {"succeeded", "failed"}:
            return data
        time.sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")


def _assert_xyz(actual: dict, expected: dict, *, abs: float = 1e-9) -> None:
    assert actual["x_m"] == pytest.approx(expected["x_m"], abs=abs)
    assert actual["y_m"] == pytest.approx(expected["y_m"], abs=abs)
    assert actual["z_m"] == pytest.approx(expected["z_m"], abs=abs)


def test_dashboard_static_assets_are_packaged():
    dashboard_files = files("peripersonal_space_toolkit.dashboard")
    viewer_files = files("peripersonal_space_toolkit.viewer")
    assert dashboard_files.joinpath("index.html").is_file()
    assert dashboard_files.joinpath("styles.css").is_file()
    assert dashboard_files.joinpath("app.js").is_file()
    assert viewer_files.joinpath("trajectory-viewer.js").is_file()

    html = dashboard_files.joinpath("index.html").read_text(encoding="utf-8")
    app_js = dashboard_files.joinpath("app.js").read_text(encoding="utf-8")
    styles_css = dashboard_files.joinpath("styles.css").read_text(encoding="utf-8")
    viewer_js = viewer_files.joinpath("trajectory-viewer.js").read_text(encoding="utf-8")
    assert 'href="styles.css"' in html
    assert 'src="app.js"' in html
    assert 'src="../viewer/index.html?v=source-trajectory-inventory"' in html
    assert 'id="audio-file-input"' in html
    assert 'id="zoom-in-camera"' in html
    assert 'id="zoom-out-camera"' in html
    assert 'id="fit-radius-camera"' in html
    assert 'id="preload-asset-status"' in html
    assert 'id="profile-recreation-notice"' in html
    assert "Study/profile preload" in html
    assert "Published preload" not in html
    assert "not the exact stimulus set used in the original study" in app_js
    assert 'id="import-audio-spatialize"' in html
    assert 'id="import-audio-preserve"' in html
    assert 'id="import-audio-prestimulus"' not in html
    assert 'id="generated-noise-select"' in html
    assert 'id="bake-stimulus"' in html
    assert 'id="bake-status"' in html
    assert 'id="stimulus-feedback-list"' in html
    assert 'id="stimulus-render-status"' in html
    assert 'id="noise-list"' in html
    assert 'id="audio-list"' in html
    assert 'id="snippet-list"' in html
    assert 'id="snippet-counts"' in html
    assert 'id="assembly-list"' not in html
    assert 'id="builder-add-noise"' not in html
    assert 'id="builder-add-audio"' not in html
    assert 'id="builder-noise-type"' not in html
    assert 'id="source-counts"' in html
    assert 'id="add-audio-spatialize"' not in html
    assert 'id="add-audio-preserve"' not in html
    assert "Stimulus Type Selection" in html
    assert "Looming Stimuli Builder" in html
    assert "Trajectory And Source" in html
    assert "Backend Feedback" in html
    assert "Trial Sequence Design" in html
    assert "Trial-Block Design" in html
    assert html.index("Baseline Strategy") < html.index("Trial Sequence Design") < html.index("Trial-Block Design")
    assert "Single-Trial Sequence Assembly" in html
    assert "Custom Clips" in html
    assert "Trial Sequence Rows" in html
    assert 'aria-label="Add trial sequence row"' in html
    assert "Trial Type" in html
    assert "Baseline Strategy" in html
    assert 'id="baseline-enabled"' in html
    assert 'id="baseline-strategy"' in html
    assert 'id="baseline-options"' in html
    assert 'id="baseline-percent"' in html
    assert 'id="catch-percent"' in html
    assert "No baseline trials" in html
    assert 'type="checkbox" name="baseline-option"' in html
    assert "Use baseline trials" not in html
    assert "Baseline % per row" not in html
    assert "Matched SOA anchors" in html
    assert "Sound onset / min SOA" in html
    assert "Sound offset / max SOA" in html
    assert "Custom timing anchors" in html
    assert "Default baseline %" not in html
    assert "Default catch %" not in html
    assert 'id="baseline-soa-values"' in html
    assert 'id="block-soa-values"' in html
    assert html.index('id="repetitions"') > html.index('id="block"')
    assert html.index('id="blocks"') > html.index('id="block"')
    assert html.index('id="protocol-summary"') > html.index('id="block"')
    assert "Run Setup" in html
    assert html.index('id="participants"') > html.index('id="run"')
    assert "Custom Stimulus Builder" not in html
    assert "Bake Stimulus" in html
    assert "Filmstrip Trial Assembly" not in html
    assert "Add Trial Type" not in html
    assert "Choose noise type to bake" in html
    assert "Add generated noise..." not in html
    assert "Generate Looming Noise" in html
    assert "Custom Looming Tone" in html
    assert "Custom Audio Clip" in html
    assert "grid-auto-rows: 1fr" in styles_css
    assert "Dry Custom Tone" not in html
    assert "Already Looming / Control" not in html
    assert "Add Instruction Clip" not in html
    assert "Instruction Snippets" not in html
    assert "Instruction Snippet" not in app_js
    assert "/api/stimulus/bake" in app_js
    assert "/api/trials/preview-row" in app_js
    assert "data-preview-strip" in app_js
    assert "filmstrip-preview-button" in app_js
    assert "trial-row-empty" in app_js
    assert ".trial-row-empty" in styles_css
    assert "Fixed event" in app_js
    assert "Randomizer event" in app_js
    assert "data-randomizer-soas" not in app_js
    assert "randomizer-count-row" not in app_js
    assert "randomizer-source-row" in app_js
    assert "rowOrderText" in app_js
    assert "plays first" in app_js
    assert "plays after row" in app_js
    assert "Randomizes across the selected stimulus sources" in app_js
    assert "previewFilmstripRow" in app_js
    assert "Prelisten trial type" in app_js
    assert "Trial type label" in app_js
    assert "audio_tactile_percentage" in app_js
    assert "catch_percentage" in app_js
    assert "baseline_percentage" in app_js
    assert "blockCompositionEstimate" in app_js
    assert "Remove trial sequence row" in app_js
    assert "renderProtocolSummary" in app_js
    assert "Row label" not in app_js
    assert "BASELINE_STRATEGY_NOTES" in app_js
    assert "baselineCountEstimate" in app_js
    assert "updateBaselineDecision" in app_js
    assert "renderPreloadAssetStatus" in app_js
    assert "/api/local/open-folder" in app_js
    assert "data-open-folder" in app_js
    assert "Open Folder" in app_js
    assert "HTTP errors still mean the companion answered" in app_js
    assert "renderStimulusFeedback" in app_js
    assert "callTrajectoryViewer" in app_js
    assert "fitTrajectoryRadius" in app_js
    assert "zoomTrajectoryCamera" in app_js
    assert "startBakeStimulus" in app_js
    assert "stageGeneratedNoise" in app_js
    assert "IMPORTED_AUDIO_HANDLING" in app_js
    assert "PROCEDURAL_NOISE_TYPES" in app_js
    assert "STIMULUS_SNIPPET_PLACEMENTS" in app_js
    assert "STIMULUS_MOTION_MODES" not in app_js
    assert "noise-source-card" in app_js
    assert "audio-source-card" in app_js
    assert "stimulusTrajectoryHiddenFields" in app_js
    assert "sourceTrajectoriesFromDom" in app_js
    assert "source_trajectories" in app_js
    assert "stimulusTrajectoryTrace" in app_js
    assert "STIMULUS_TRAJECTORY_COLORS" in app_js
    assert "trajectoryColorSet" in app_js
    assert "trajectoryGradient" in app_js
    assert "trajectory_snapshot" in app_js
    assert "prebaked_path" in app_js
    assert "tone_type" in app_js
    assert "SOURCE_COLOR_OPTIONS" in app_js
    assert "sourceColorOptions" in app_js
    assert "applySourceCardColor" in app_js
    assert "Box color" in app_js
    assert "Local path" not in app_js
    assert "--source-card-color" in styles_css
    assert "grid-template-columns: repeat(auto-fit" in styles_css
    assert ".stimulus-trajectory-trace" in styles_css
    assert ".stimulus-trajectory-line" in styles_css
    assert "--trajectory-gradient" in styles_css
    assert "assembly-list" not in app_js
    assert "dragstart" not in app_js
    assert "START_MARKER_COLOR" in viewer_js
    assert "END_MARKER_COLOR" in viewer_js
    assert "end_marker_color" in viewer_js
    assert "fit2DCameraToRadius" in viewer_js
    assert "TWO_D_RADIUS_PADDING" in viewer_js
    assert "controls.enabled = false" in viewer_js
    assert "activePan2D" in viewer_js
    assert "set2DViewCenter" in viewer_js
    assert "set2DVerticalSpan" in viewer_js
    assert "zoomTrajectoryCamera" in viewer_js
    assert "fitTrajectoryRadius" in viewer_js
    assert "two_d_radius_centered" in viewer_js
    assert "two_d_pan_enabled" in viewer_js
    assert "two_d_zoom_enabled" in viewer_js
    assert "drawSourceTrajectoryInventory" in viewer_js
    assert "source_trajectory_count" in viewer_js
    assert "shared_tone_trajectory_group_count" in viewer_js
    assert "SOURCE_TRAJECTORY_OFFSET_M" in viewer_js
    assert "twoDFitVerticalSpanM" in viewer_js
    assert "radiusChanged" not in viewer_js
    assert "trajectory-viewer.js?v=" in viewer_files.joinpath("index.html").read_text(encoding="utf-8")
    assert "/api/" not in html


def test_dashboard_payload_uses_normalized_trajectory_controls_for_render_and_bake():
    app_js = files("peripersonal_space_toolkit.dashboard").joinpath("app.js").read_text(encoding="utf-8")

    assert "const trajectoryControls = currentTrajectoryControls();" in app_js
    assert "trajectory_controls: trajectoryControls" in app_js
    assert ": [trajectoryControls.end_distance_cm]" in app_js
    assert 'body: JSON.stringify(collectPayload())' in app_js
    assert "payload.bake_recipe = recipe" in app_js
    assert 'movement_duration_s: clampNumber(numberValue("movement-duration", 3), 0.1, 30, 3)' in app_js
    assert 'start_hold_s: clampNumber(numberValue("start-hold", 0.5), 0, 30, 0.5)' in app_js
    assert 'end_hold_s: clampNumber(numberValue("end-hold", 0.5), 0, 30, 0.5)' in app_js


def test_dashboard_gui_to_3dti_config_handoff_stress_grid(tmp_path: Path):
    client = _client(tmp_path)
    control_cases = [
        {"start_distance_cm": 110, "end_distance_cm": 10, "start_rotation_deg": 0, "end_rotation_deg": 0, "movement_duration_s": 3.0, "start_hold_s": 0.5, "end_hold_s": 0.5},
        {"start_distance_cm": 90, "end_distance_cm": 20, "start_rotation_deg": 270, "end_rotation_deg": 0, "movement_duration_s": 1.2, "start_hold_s": 0.1, "end_hold_s": 0.2},
        {"start_distance_cm": 80, "end_distance_cm": 80, "start_rotation_deg": 270, "end_rotation_deg": 90, "movement_duration_s": 0.25, "start_hold_s": 0.0, "end_hold_s": 0.0},
        {"start_distance_cm": 250, "end_distance_cm": 25, "start_rotation_deg": 45, "end_rotation_deg": 315, "movement_duration_s": 4.5, "start_hold_s": 0.25, "end_hold_s": 0.75},
        {"start_distance_cm": 35, "end_distance_cm": 120, "start_rotation_deg": 180, "end_rotation_deg": 360, "movement_duration_s": 2.0, "start_hold_s": 0.05, "end_hold_s": 0.05},
        {"start_distance_cm": 999, "end_distance_cm": 1, "start_rotation_deg": 359.9, "end_rotation_deg": 180.1, "movement_duration_s": 30.0, "start_hold_s": 0.0, "end_hold_s": 0.1},
        {"start_distance_cm": 60, "end_distance_cm": 15, "start_rotation_deg": 135, "end_rotation_deg": 225, "movement_duration_s": 0.5, "start_hold_s": 0.2, "end_hold_s": 0.3},
        {"start_distance_cm": 10, "end_distance_cm": 110, "start_rotation_deg": 90, "end_rotation_deg": 270, "movement_duration_s": 6.0, "start_hold_s": 0.0, "end_hold_s": 0.0},
    ]
    noise_types = ["pink", "blue", "white", "brown", "violet", "pink", "blue", "white"]

    for index, controls in enumerate(control_cases, start=1):
        total_s = controls["start_hold_s"] + controls["movement_duration_s"] + controls["end_hold_s"]
        soas = sorted({max(0, int(round(total_s * fraction * 1000))) for fraction in (0.2, 0.5, 0.8)})
        spatial = [round(100.0 - index * 3.0 - offset, 3) for offset in range(len(soas))]
        design = _compact_design()
        design.name = f"GUI stress handoff {index}"
        design.noises[0].label = f"Stress source {index}"
        design.noises[0].noise_type = noise_types[index - 1]
        design.noises[0].gain = 0.25 + index * 0.1
        design.protocol.soa_values_ms = soas
        design.protocol.spatial_values_cm = spatial
        design.protocol.random_seed = 9000 + index
        payload = {
            "participant_id": f"P{index:03d}",
            "design": design_to_dict(design),
            "trajectory_controls": controls,
        }

        state = client.post("/api/design", json=payload).json()
        loaded = design_from_dict(state["design"])
        saved = load_design(tmp_path / "design.json")
        config = build_render_config(loaded, seed=loaded.protocol.random_seed, output_dir=tmp_path / f"case_{index}", samples_per_second=100.0)
        expected_start = point_from_distance_rotation_height(
            controls["start_distance_cm"], controls["start_rotation_deg"], 0.0
        )
        expected_end = point_from_distance_rotation_height(
            controls["end_distance_cm"], controls["end_rotation_deg"], 0.0
        )
        expected_path_length = math.dist(
            (expected_start["x_m"], expected_start["y_m"], expected_start["z_m"]),
            (expected_end["x_m"], expected_end["y_m"], expected_end["z_m"]),
        )

        assert state["participant_id"] == f"P{index:03d}"
        assert state["validation"] == []
        assert design_to_dict(saved) == state["design"]
        _assert_xyz(state["viewer_payload"]["start"], expected_start)
        _assert_xyz(state["viewer_payload"]["end"], expected_end)
        assert loaded.trajectory.path_length_m == pytest.approx(expected_path_length)
        assert loaded.trajectory.movement_duration_s == pytest.approx(controls["movement_duration_s"])
        assert loaded.trajectory.padding_pre_s == pytest.approx(controls["start_hold_s"])
        assert loaded.trajectory.padding_post_s == pytest.approx(controls["end_hold_s"])
        assert loaded.trajectory.propagation_speed_mps == pytest.approx(expected_path_length / controls["movement_duration_s"])
        assert config["design"] == state["design"]
        assert config["source"]["seed"] == loaded.protocol.random_seed
        assert config["source"]["noises"] == [
                {
                    "label": f"Stress source {index}",
                    "noise_type": noise_types[index - 1],
                    "tone_type": noise_types[index - 1],
                    "gain": pytest.approx(0.25 + index * 0.1),
                }
            ]
        assert config["protocol"]["soa_values_ms"] == soas
        assert config["protocol"]["spatial_values_cm"] == spatial
        assert config["trajectory"]["start_hold_s"] == pytest.approx(controls["start_hold_s"])
        assert config["trajectory"]["movement_duration_s"] == pytest.approx(controls["movement_duration_s"])
        assert config["trajectory"]["end_hold_s"] == pytest.approx(controls["end_hold_s"])
        _assert_xyz(config["trajectory"]["samples"][0], expected_start)
        _assert_xyz(config["trajectory"]["samples"][-1], expected_end)

        mapped_start = app_to_3dti_coordinates(expected_start["x_m"], expected_start["y_m"], expected_start["z_m"])
        assert mapped_start["x_m"] == pytest.approx(expected_start["y_m"])
        assert mapped_start["y_m"] == pytest.approx(-expected_start["x_m"])
        assert mapped_start["z_m"] == pytest.approx(expected_start["z_m"])
        assert len(config["tactile"]["events"]) == len(soas)
        for event, soa_ms, spatial_cm in zip(config["tactile"]["events"], soas, spatial):
            expected_at_tactile = trajectory_point_at_time(loaded.trajectory, soa_ms / 1000.0)
            assert event["soa_ms"] == soa_ms
            assert event["tactile_onset_s"] == pytest.approx(soa_ms / 1000.0)
            assert event["planned_spatial_value_cm"] == pytest.approx(spatial_cm)
            assert event["source_x_at_tactile_m"] == pytest.approx(expected_at_tactile["x_m"])
            assert event["source_y_at_tactile_m"] == pytest.approx(expected_at_tactile["y_m"])
            assert event["source_z_at_tactile_m"] == pytest.approx(expected_at_tactile["z_m"])


def test_dashboard_pages_companion_contract(tmp_path: Path):
    client = _client(tmp_path)

    root = client.get("/", follow_redirects=False)
    assert root.status_code in {302, 307}
    assert root.headers["location"] == "/dashboard/index.html"

    health = client.get("/api/health", headers={"Origin": "https://georgefejer91.github.io"})
    assert health.status_code == 200
    assert health.json()["service"] == "pps-dashboard-companion"
    assert health.headers["access-control-allow-origin"] == "https://georgefejer91.github.io"

    preloads = client.get("/api/preloads").json()
    assert preloads["schema"] == "pps-preload-asset-inventory.v1"
    assert preloads["segments"][0]["folder"] == "01_profile"
    assert len(preloads["profiles"]) >= 21
    assert all(item["status"] == "ready" for item in preloads["profiles"])
    assert all(item["catalog_segments"] for item in preloads["profiles"])
    study5 = next(item for item in preloads["profiles"] if item["template_id"] == "study5_box_breathing_pps")
    assert study5["status"] == "ready"
    assert study5["asset_mode"] == "bundled_local"
    assert study5["catalog_segments"][1]["folder"] == "02_looming_stimuli"

    synced = client.post("/api/preloads/study5_box_breathing_pps/sync").json()
    assert synced["status"] == "ready"
    assert synced["ready_asset_count"] == 4


def test_dashboard_loads_unpublished_study5_preload_with_instruction_events(tmp_path: Path):
    client = _client(tmp_path)

    loaded = client.post("/api/templates/study5_box_breathing_pps/load").json()
    design = loaded["design"]

    assert loaded["selected_template"] == "study5_box_breathing_pps"
    assert design["study_profile_title"] == "Study 5 PPS box-breathing profile"
    assert design["study_profile_reference_parameters"]["publication_status"] == "unpublished_lab_profile"
    assert design["study_profile_reference_parameters"]["looming_assets_bundled"] is True
    assert design["study_profile_reference_parameters"]["custom_clips_preloaded"] is True
    assert loaded["custom_workflow"]["is_custom"] is False
    instruction_labels = [clip["label"] for clip in design["prestimulus_files"]]
    assert instruction_labels[:2] == ["Inhale instruction", "Exhale instruction"]
    assert len(instruction_labels) == 2
    assert all(clip["target_duration_s"] == 4.0 for clip in design["prestimulus_files"])
    assert all(clip["path"].startswith("assets/breathing/") for clip in design["prestimulus_files"])
    assert design["study_profile_reference_parameters"]["default_instruction_asset_variant"] == "british_kokoro"
    assert set(design["study_profile_reference_parameters"]["instruction_asset_variants"]) == {
        "british_kokoro",
        "original_study5",
    }
    custom_clip_assets = design["study_profile_reference_parameters"]["custom_clip_assets"]
    assert [clip["label"] for clip in custom_clip_assets[:2]] == ["Inhale instruction", "Exhale instruction"]
    assert all(clip["duration_s"] == 4.0 for clip in custom_clip_assets)
    assert len(design["prestimulus_files"]) == 2
    assert [asset["label"] for asset in design["noises"]] == [
        "Pink frontal",
        "Blue frontal",
        "White frontal",
        "Brown frontal",
    ]
    assert design["custom_looming_files"] == []
    assert all("/02_looming_stimuli/" in asset["prebaked_path"].replace("\\", "/") for asset in design["noises"])
    assert [asset["noise_type"] for asset in design["noises"]] == ["pink", "blue", "white", "brown"]
    assert len(loaded["viewer_payload"]["source_trajectories"]) == 4
    assert {item["tone_type"] for item in loaded["viewer_payload"]["source_trajectories"]} == {"pink", "blue", "white", "brown"}
    assert all("/02_looming_stimuli/" in item["local_path"].replace("\\", "/") for item in loaded["viewer_payload"]["source_trajectories"])
    assert loaded["preload_inventory"]["status"] == "ready"
    assert loaded["preflight"]["render_ready"] is True

    strips = design["protocol"]["trial_strips"]
    assert [strip["label"] for strip in strips] == ["Inhale trial type", "Exhale trial type"]
    assert [strip["elements"][0]["source_label"] for strip in strips] == ["Inhale instruction", "Exhale instruction"]
    assert all(strip["elements"][1]["randomized"] for strip in strips)
    assert all(strip["elements"][1]["source_labels"] for strip in strips)
    assert loaded["trial_preview"]
    assert loaded["trial_preview"][0]["trial_type"] in {"Inhale trial type", "Exhale trial type"}
    assert loaded["trial_preview"][0]["type"] in {"Audio-Tactile", "Catch", "Baseline"}
    assert any("Inhale instruction | " in row["sequence"] for row in loaded["trial_preview"])
    assert any("Exhale instruction | " in row["sequence"] for row in loaded["trial_preview"])


def test_dashboard_loads_all_preloads_with_trajectory_inventory(tmp_path: Path):
    client = _client(tmp_path)
    root = Path(__file__).resolve().parents[1]
    templates = client.get("/api/state").json()["templates"]

    assert templates
    for template in templates:
        loaded = client.post(f"/api/templates/{template['template_id']}/load").json()
        design = loaded["design"]
        sources = design["noises"] + design["custom_looming_files"]
        viewer_sources = loaded["viewer_payload"]["source_trajectories"]

        assert sources, template["template_id"]
        assert len(viewer_sources) == len(sources), template["template_id"]
        for source in sources:
            local_path = source.get("prebaked_path") or source.get("path") or ""
            assert local_path, (template["template_id"], source.get("label"))
            assert (root / local_path).exists(), (template["template_id"], source.get("label"), local_path)
            snapshot = source.get("trajectory_snapshot") or {}
            assert snapshot.get("schema") == "pps-stimulus-trajectory.v1", (template["template_id"], source.get("label"))
            assert snapshot.get("start_distance_cm") is not None, (template["template_id"], source.get("label"))
            assert snapshot.get("end_distance_cm") is not None, (template["template_id"], source.get("label"))
            assert snapshot.get("movement_duration_s") is not None, (template["template_id"], source.get("label"))
            assert snapshot.get("start") and snapshot.get("end"), (template["template_id"], source.get("label"))
        for viewer_source in viewer_sources:
            assert viewer_source["trajectory_snapshot"]["schema"] == "pps-stimulus-trajectory.v1"
            assert viewer_source["start"] and viewer_source["end"]
            assert viewer_source["color_hex"].startswith("#")
            assert viewer_source["local_path"]


def test_pfeiffer_preload_loads_bilateral_lateral_trajectories(tmp_path: Path):
    client = _client(tmp_path)
    root = Path(__file__).resolve().parents[1]
    template_id = "pfeiffer_2018_lateral_perihead_left_to_right"

    inventory = json.loads((root / "assets" / "preloads" / "preload_inventory.json").read_text(encoding="utf-8"))
    profile = next(item for item in inventory["profiles"] if item["template_id"] == template_id)
    assert len(profile["assets"]) == 2
    assert {asset["direction_label"] for asset in profile["assets"]} == {"left_to_right", "right_to_left"}

    loaded = client.post(f"/api/templates/{template_id}/load").json()
    design = loaded["design"]
    viewer_sources = loaded["viewer_payload"]["source_trajectories"]
    assert len(design["noises"]) == 1
    assert len(design["custom_looming_files"]) == 1
    assert len(viewer_sources) == 2
    assert {item["trajectory_snapshot"]["path_direction"] for item in viewer_sources} == {
        "left_to_right",
        "right_to_left",
    }
    rotations = {
        (
            item["trajectory_snapshot"]["start_rotation_deg"],
            item["trajectory_snapshot"]["end_rotation_deg"],
        )
        for item in viewer_sources
    }
    assert rotations == {(277.125, 82.875), (82.875, 277.125)}
    assert all((root / item["local_path"]).exists() for item in viewer_sources)


def test_lerner_preload_loads_twelve_3d_boundary_directions(tmp_path: Path):
    client = _client(tmp_path)
    root = Path(__file__).resolve().parents[1]
    template_id = "lerner_2021_3d_audio_tactile_boundary"

    inventory = json.loads((root / "assets" / "preloads" / "preload_inventory.json").read_text(encoding="utf-8"))
    profile = next(item for item in inventory["profiles"] if item["template_id"] == template_id)
    assert len(profile["assets"]) == 24
    assert profile["source_recipe_count"] == 24
    assert {asset["direction_label"] for asset in profile["assets"]} == {
        f"direction_{index:02d}" for index in range(1, 13)
    }

    loaded = client.post(f"/api/templates/{template_id}/load").json()
    design = loaded["design"]
    viewer_sources = loaded["viewer_payload"]["source_trajectories"]
    assert len(design["noises"]) == 2
    assert len(design["custom_looming_files"]) == 22
    assert design["protocol"]["auditory_motion_directions"] == ["source_trajectory"]
    assert len(viewer_sources) == 24
    assert {item["tone_type"] for item in viewer_sources} == {"pink", "white"}
    unique_geometries = {
        (
            tuple(item["trajectory_snapshot"]["start"][axis] for axis in ("x_m", "y_m", "z_m")),
            tuple(item["trajectory_snapshot"]["end"][axis] for axis in ("x_m", "y_m", "z_m")),
        )
        for item in viewer_sources
    }
    assert len(unique_geometries) == 12
    assert {item["trajectory_snapshot"]["movement_duration_s"] for item in viewer_sources} == {5.5}
    assert {item["trajectory_snapshot"]["start_distance_cm"] for item in viewer_sources} == {120.0}
    assert {item["trajectory_snapshot"]["end_distance_cm"] for item in viewer_sources} == {1.0}
    assert all((root / item["local_path"]).exists() for item in viewer_sources)


def test_preload_catalog_folders_mirror_dashboard_segments():
    root = Path(__file__).resolve().parents[1]
    inventory = json.loads((root / "assets" / "preloads" / "preload_inventory.json").read_text(encoding="utf-8"))
    expected_segments = [
        "01_profile",
        "02_looming_stimuli",
        "03_baseline_strategy",
        "04_trial_designer",
        "05_run_setup",
    ]
    assert [segment["folder"] for segment in inventory["segments"]] == expected_segments
    for profile in inventory["profiles"]:
        profile_dir = root / "assets" / "preloads" / profile["template_id"]
        assert profile_dir.is_dir()
        assert [segment["folder"] for segment in profile["catalog_segments"]] == expected_segments
        assert (profile_dir / "preload_manifest.json").exists()
        assert (profile_dir / "01_profile" / "profile_metadata.json").exists()
        assert (profile_dir / "02_looming_stimuli" / "stimulus_sources.json").exists()
        assert (profile_dir / "02_looming_stimuli" / "trajectory_inventory.json").exists()
        assert (profile_dir / "03_baseline_strategy" / "baseline_strategy.json").exists()
        assert (profile_dir / "04_trial_designer" / "trial_design.json").exists()
        assert (profile_dir / "05_run_setup" / "run_defaults.json").exists()
        for asset in profile["assets"]:
            path = root / asset["path"]
            assert path.exists()
            assert Path(asset["path"]).parts[-2] == "02_looming_stimuli"
            assert asset["trajectory_snapshot"]["schema"] == "pps-stimulus-trajectory.v1"


def test_dashboard_previews_study5_filmstrip_row_audio_locally(tmp_path: Path):
    client = _client(tmp_path)
    loaded = client.post("/api/templates/study5_box_breathing_pps/load").json()

    preview = client.post(
        "/api/trials/preview-row",
        json={
            "participant_id": "P001",
            "strip_index": 0,
            "design": loaded["design"],
        },
    ).json()

    assert preview["local_only"] is True
    assert preview["auditory_preview_only"] is True
    assert preview["sequence"][0] == "Inhale instruction"
    assert preview["selected_source_label"] in loaded["design"]["protocol"]["trial_strips"][0]["elements"][1]["source_labels"]
    assert preview["url"].startswith("/api/trial-row-previews/")
    preview_path = Path(preview["path"])
    assert preview_path.exists()
    assert preview_path.parent == tmp_path / "previews"
    info = sf.info(str(preview_path))
    assert info.channels == 2
    assert info.samplerate == 44100
    assert info.frames / info.samplerate == pytest.approx(8.0)
    assert client.get(preview["url"]).status_code == 200


def test_dashboard_state_templates_and_design_update(tmp_path: Path):
    client = _client(tmp_path)

    state = client.get("/api/state").json()
    assert state["design"]["name"]
    assert state["templates"]
    assert state["preload_inventory"]["status"] == "ready"
    assert state["render"]["wav_count"] >= 4

    template_id = state["templates"][0]["template_id"]
    loaded = client.post(f"/api/templates/{template_id}/load").json()
    assert loaded["selected_template"] == template_id

    custom = client.post("/api/templates/__custom__/load").json()
    assert custom["selected_template"] == ""
    assert custom["design"]["name"] == "Custom PPS design"
    assert custom["design"]["study_profile_id"] == ""
    assert custom["custom_workflow"]["is_custom"]
    assert not custom["custom_workflow"]["ready_to_render"]
    assert custom["design"]["noises"] == []
    assert custom["design"]["protocol"]["soa_values_ms"] == []

    blocked = client.post("/api/render", json={})
    assert blocked.status_code == 400
    assert "Custom design is incomplete" in blocked.json()["detail"]

    custom["design"]["name"] = "Manual lab approach design"
    custom["design"]["noises"] = [
        {"label": "Manual pink", "noise_type": "pink", "azimuth_deg": 0.0, "elevation_deg": 0.0, "gain": 1.0}
    ]
    custom["design"]["protocol"]["soa_values_ms"] = [300]
    custom["design"]["protocol"]["spatial_values_cm"] = [100.0]
    custom["design"]["protocol"]["trial_strips"] = [
        {
            "strip_id": "strip-1",
            "label": "Manual row",
            "elements": [
                {
                    "element_id": "looming-1",
                    "kind": "looming_stimulus",
                    "label": "Looming Stimulus",
                    "source_labels": ["Manual pink"],
                    "randomized": True,
                }
            ],
        }
    ]
    custom_needs_baseline = client.post("/api/design", json={"participant_id": "", "design": custom["design"]}).json()
    assert not custom_needs_baseline["custom_workflow"]["ready_to_render"]
    assert custom_needs_baseline["custom_workflow"]["current_step"] == "baseline"

    custom["design"]["protocol"]["baseline_strategy"] = "none"
    custom["design"]["protocol"]["baseline_trial_percentage"] = 0.0
    custom["design"]["protocol"]["include_baseline_trials"] = False
    custom["design"]["protocol"]["soa_values_ms"] = []
    custom_needs_block = client.post("/api/design", json={"participant_id": "", "design": custom["design"]}).json()
    assert not custom_needs_block["custom_workflow"]["ready_to_render"]
    assert custom_needs_block["custom_workflow"]["current_step"] == "block"

    custom["design"]["protocol"]["soa_values_ms"] = [300]
    custom_ready = client.post("/api/design", json={"participant_id": "", "design": custom["design"]}).json()
    assert custom_ready["custom_workflow"]["ready_to_render"]
    assert not custom_ready["custom_workflow"]["ready_to_prepare"]
    assert custom_ready["custom_workflow"]["current_step"] == "run"

    custom_run_ready = client.post("/api/design", json={"participant_id": "P042", "design": custom["design"]}).json()
    assert custom_run_ready["custom_workflow"]["ready_to_prepare"]

    loaded = client.post(f"/api/templates/{template_id}/load").json()
    assert loaded["selected_template"] == template_id

    loaded["design"]["name"] = "Browser prototype design"
    updated = client.post(
        "/api/design",
        json={
            "participant_id": "Subject 01",
            "design": loaded["design"],
            "trajectory_controls": {
                "start_distance_cm": 120,
                "end_distance_cm": 20,
                "start_rotation_deg": 0,
                "end_rotation_deg": 15,
                "movement_duration_s": 3,
                "start_hold_s": 0.5,
                "end_hold_s": 0.5,
            },
        },
    ).json()
    assert updated["participant_id"] == "Subject 01"
    assert updated["design"]["name"] == "Browser prototype design"
    assert updated["viewer_payload"]["path_length_m"] > 0


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


def test_dashboard_import_audio_is_local_only(tmp_path: Path):
    client = _client(tmp_path)
    source = tmp_path / "manual_loom.wav"
    sf.write(source, np.zeros((441, 2), dtype=np.float32), 44100)
    payload = {
        "filename": source.name,
        "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
        "use": "looming",
        "render_mode": "spatialize",
    }

    imported = client.post("/api/audio/import", json=payload).json()

    assert imported["local_only"] is True
    assert "online upload" in imported["message"]
    stored = Path(imported["audio"]["path"])
    assert stored.exists()
    assert stored.parent == tmp_path / "imports"
    assert imported["audio"]["label"] == "manual_loom"
    assert imported["audio"]["target_duration_s"] > 0
    assert imported["audio"]["render_mode"] == "spatialize"

    snippet_payload = {
        "filename": source.name,
        "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
        "use": "prestimulus",
        "render_mode": "preserve",
        "placement": "after",
        "target_source_label": "Manual pink",
        "phase": "Inhale",
        "gap_s": 0.25,
        "sequence_order": 3,
        "motion_mode": "stationary",
    }
    snippet = client.post("/api/audio/import", json=snippet_payload).json()

    assert snippet["local_only"] is True
    assert snippet["audio"]["placement"] == "after"
    assert snippet["audio"]["target_source_label"] == "Manual pink"
    assert snippet["audio"]["phase"] == "Inhale"
    assert snippet["audio"]["gap_s"] == 0.25
    assert snippet["audio"]["sequence_order"] == 3
    assert snippet["audio"]["motion_mode"] == "stationary"


def test_dashboard_bake_stimulus_job_adds_source_after_render(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    custom = client.post("/api/templates/__custom__/load").json()
    trajectory_controls = {
        "start_distance_cm": 95.0,
        "end_distance_cm": 15.0,
        "start_rotation_deg": 270.0,
        "end_rotation_deg": 45.0,
        "movement_duration_s": 1.5,
        "start_hold_s": 0.2,
        "end_hold_s": 0.4,
    }
    expected_start = point_from_distance_rotation_height(95.0, 270.0, 0.0)
    expected_end = point_from_distance_rotation_height(15.0, 45.0, 0.0)
    custom["design"]["name"] = "Manual bake design"
    custom["design"]["protocol"]["soa_values_ms"] = [300]
    custom["design"]["protocol"]["spatial_values_cm"] = [100.0]
    custom["design"]["protocol"]["include_baseline_trials"] = False
    custom["design"]["protocol"]["baseline_strategy"] = "none"
    custom["design"]["protocol"]["baseline_trial_percentage"] = 0.0
    custom["design"]["protocol"]["trial_strips"] = [
        {
            "strip_id": "strip-1",
            "label": "Manual row",
            "elements": [
                {
                    "element_id": "looming-1",
                    "kind": "looming_stimulus",
                    "label": "Looming Stimulus",
                    "source_labels": ["Manual blue"],
                    "randomized": True,
                }
            ],
        }
    ]

    def fake_render(design_path, output_dir, *, seed, engine="auto", include_tactile=True, **_kwargs):
        design_data = json.loads(Path(design_path).read_text(encoding="utf-8"))
        label = design_data["noises"][0]["label"]
        wav_path = Path(output_dir) / "looming_manual_blue.wav"
        sf.write(wav_path, np.zeros((441, 2), dtype=np.float32), 44100)
        manifest = Path(output_dir) / "render_manifest.json"
        qc = Path(output_dir) / "render_qc.csv"
        tactile = Path(output_dir) / "render_tactile_events.csv"
        manifest.write_text(
            json.dumps({"status": "rendered_reference", "wav_outputs": [{"path": str(wav_path), "sha256": "test"}]}),
            encoding="utf-8",
        )
        qc.write_text("", encoding="utf-8")
        tactile.write_text("", encoding="utf-8")
        assert label == "Manual blue"
        assert seed == custom["design"]["protocol"]["random_seed"]
        assert engine == "python-sofa-reference"
        assert include_tactile is False
        assert design_data["trajectory"]["start_x_m"] == pytest.approx(expected_start["x_m"])
        assert design_data["trajectory"]["start_y_m"] == pytest.approx(expected_start["y_m"])
        assert design_data["trajectory"]["start_z_m"] == pytest.approx(expected_start["z_m"])
        assert design_data["trajectory"]["end_x_m"] == pytest.approx(expected_end["x_m"])
        assert design_data["trajectory"]["end_y_m"] == pytest.approx(expected_end["y_m"])
        assert design_data["trajectory"]["end_z_m"] == pytest.approx(expected_end["z_m"])
        assert design_data["trajectory"]["propagation_speed_mps"] == pytest.approx(
            math.dist(
                (expected_start["x_m"], expected_start["y_m"], expected_start["z_m"]),
                (expected_end["x_m"], expected_end["y_m"], expected_end["z_m"]),
            )
            / trajectory_controls["movement_duration_s"]
        )
        assert design_data["trajectory"]["padding_pre_s"] == pytest.approx(trajectory_controls["start_hold_s"])
        assert design_data["trajectory"]["padding_post_s"] == pytest.approx(trajectory_controls["end_hold_s"])
        return RenderResult("rendered_reference", 0, Path(output_dir), Path(design_path), manifest, qc, wav_paths=(wav_path,), tactile_events_path=tactile)

    monkeypatch.setattr(dashboard_app.render_backend, "render_design_with_3dti", fake_render)
    job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "",
            "design": custom["design"],
            "trajectory_controls": trajectory_controls,
            "bake_recipe": {"kind": "generated_noise", "noise_type": "blue", "label": "Manual blue", "gain": 0.7},
        },
    ).json()
    done = _wait_job(client, job["job_id"])
    state = client.get("/api/state").json()

    assert done["status"] == "succeeded"
    assert done["result"]["local_only"] is True
    assert done["result"]["include_tactile"] is False
    assert done["result"]["source_kind"] == "generated_noise"
    baked_noise = next(noise for noise in state["design"]["noises"] if noise["label"] == "Manual blue")
    assert baked_noise["noise_type"] == "blue"
    assert baked_noise["trajectory_snapshot"]["start_distance_cm"] == pytest.approx(95.0)
    assert baked_noise["trajectory_snapshot"]["end_distance_cm"] == pytest.approx(15.0)
    assert baked_noise["trajectory_snapshot"]["start_rotation_deg"] == pytest.approx(270.0)
    assert baked_noise["trajectory_snapshot"]["end_rotation_deg"] == pytest.approx(45.0)
    assert done["result"]["source"]["trajectory_snapshot"] == baked_noise["trajectory_snapshot"]
    assert state["render"]["wav_count"] >= 1
    assert state["custom_workflow"]["ready_to_render"] is True


def test_auditory_only_bake_render_writes_stereo_wav(tmp_path: Path):
    design = _compact_design()
    design_path = tmp_path / "design.json"
    render_dir = tmp_path / "render"
    save_design(design, design_path)

    result = dashboard_app.render_backend.render_design_with_3dti(
        design_path,
        render_dir,
        seed=20250604,
        engine="python-sofa-reference",
        include_tactile=False,
    )

    assert result.wav_paths
    assert sf.info(str(result.wav_paths[0])).channels == 2
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["tactile_events"]["enabled"] is False
    assert manifest["tactile_events"]["count"] == 0
    qc_rows = list(csv.DictReader(result.qc_path.open(encoding="utf-8")))
    assert qc_rows[0]["channels"] == "2"
    assert qc_rows[0]["tactile_events"] == "0"
    assert qc_rows[0]["tactile_channel"] == ""


def test_native_3dti_measured_wav_matches_dashboard_lateral_handoff(tmp_path: Path):
    if not DEFAULT_BACKEND_EXE.exists():
        pytest.skip("Native 3DTI renderer wrapper is not built on this machine.")
    client = _client(tmp_path)
    controls = {
        "start_distance_cm": 50.0,
        "end_distance_cm": 50.0,
        "start_rotation_deg": 270.0,
        "end_rotation_deg": 90.0,
        "movement_duration_s": 0.18,
        "start_hold_s": 0.0,
        "end_hold_s": 0.0,
    }
    design = _compact_design()
    design.name = "Native dashboard lateral measured stress"
    design.noises[0].label = "Native lateral source"
    design.protocol.soa_values_ms = [80]
    design.protocol.spatial_values_cm = [50.0]
    design.protocol.random_seed = 777

    state = client.post(
        "/api/design",
        json={
            "participant_id": "P777",
            "design": design_to_dict(design),
            "trajectory_controls": controls,
        },
    ).json()
    design_path = tmp_path / "native_dashboard_design.json"
    save_design(design_from_dict(state["design"]), design_path)

    result = render_design_with_3dti(
        design_path,
        tmp_path / "native_render",
        seed=design.protocol.random_seed,
        engine="native-3dti",
    )

    assert result.status == "rendered_3dti"
    assert result.exit_code == 0
    assert len(result.wav_paths) == 1
    audio, sample_rate = sf.read(result.wav_paths[0], always_2d=True)
    expected_frames = int(round(controls["movement_duration_s"] * sample_rate))
    assert sample_rate == 44100
    assert audio.shape == (expected_frames, 3)
    assert np.max(np.abs(audio[:, 0])) > 0.01
    assert np.max(np.abs(audio[:, 1])) > 0.01
    assert np.max(np.abs(audio)) < 1.0

    onset = int(round(0.08 * sample_rate))
    assert np.max(np.abs(audio[:onset, 2])) == pytest.approx(0.0)
    assert np.max(np.abs(audio[onset:, 2])) > 0.1

    midpoint = len(audio) // 2
    first_rms = np.sqrt(np.mean(audio[:midpoint, :2] * audio[:midpoint, :2], axis=0))
    second_rms = np.sqrt(np.mean(audio[midpoint:, :2] * audio[midpoint:, :2], axis=0))
    assert first_rms[0] > first_rms[1] * 1.2
    assert second_rms[1] > second_rms[0] * 1.2

    config = json.loads(result.config_path.read_text(encoding="utf-8"))
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert config["design"] == state["design"]
    assert config["trajectory"]["samples"][0]["x_m"] == pytest.approx(-0.5)
    assert config["trajectory"]["samples"][-1]["x_m"] == pytest.approx(0.5)
    assert manifest["render_engine"] == "native-3dti"
    assert manifest["tactile_events"]["count"] == 1
    assert result.tactile_events_path is not None
    assert manifest["tactile_events"]["sha256"] == sha256_file(result.tactile_events_path)
    assert manifest["wav_outputs"][0]["sha256"] == sha256_file(result.wav_paths[0])


def test_dashboard_open_folder_is_local_backend_action(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    wav_path = tmp_path / "rendered" / "looming_pink_frontal.wav"
    calls = []

    class FakeProcess:
        pid = 123

    monkeypatch.setattr(dashboard_app.subprocess, "Popen", lambda args, **_kwargs: calls.append(args) or FakeProcess())
    opened = client.post("/api/local/open-folder", json={"path": str(wav_path)}).json()

    assert opened["local_only"] is True
    assert opened["folder"] == str(wav_path.parent.resolve())
    assert calls

    preload_path = dashboard_app.REPO_ROOT / "assets" / "preloads" / "study5_box_breathing_pps" / "looming_Pink_frontal.wav"
    opened_preload = client.post("/api/local/open-folder", json={"path": str(preload_path)}).json()
    assert opened_preload["local_only"] is True
    assert opened_preload["folder"] == str(preload_path.parent.resolve())


def test_custom_audio_render_mode_reaches_render_config(tmp_path: Path):
    source = tmp_path / "dry_tone.wav"
    sf.write(source, np.zeros((441, 1), dtype=np.float32), 44100)
    design = _compact_design()
    design.noises = []
    design.custom_looming_files = [
        AudioFileSpec(
            label="Dry local tone",
            path=str(source),
            target_duration_s=4.0,
            render_mode="spatialize",
            gain=0.75,
            sequence_order=2,
            motion_mode="stationary",
        )
    ]

    config = build_render_config(design, seed=20250604, output_dir=tmp_path)

    assert config["source"]["type"] == "imported_audio"
    imported = config["source"]["noises"][0]
    assert imported["source_kind"] == "imported_audio"
    assert imported["source_render_mode"] == "spatialize"
    assert imported["path"] == str(source)
    assert imported["gain"] == 0.75
    component = config["source"]["stimulus_assembly"]["components"][0]
    assert component["component_kind"] == "custom_audio"
    assert component["sequence_order"] == 2
    assert component["motion_mode"] == "stationary"


def test_dashboard_render_job_uses_existing_render_backend(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    controls = {
        "start_distance_cm": 140.0,
        "end_distance_cm": 35.0,
        "start_rotation_deg": 315.0,
        "end_rotation_deg": 30.0,
        "movement_duration_s": 2.25,
        "start_hold_s": 0.15,
        "end_hold_s": 0.25,
    }
    expected_start = point_from_distance_rotation_height(140.0, 315.0, 0.0)
    expected_end = point_from_distance_rotation_height(35.0, 30.0, 0.0)
    design = _compact_design()
    design.name = "Render endpoint current GUI controls"
    design.protocol.random_seed = 5151

    def fake_render(design_path, output_dir, *, seed, **_kwargs):
        design_data = json.loads(Path(design_path).read_text(encoding="utf-8"))
        manifest = Path(output_dir) / "render_manifest.json"
        qc = Path(output_dir) / "render_qc.csv"
        tactile = Path(output_dir) / "render_tactile_events.csv"
        manifest.write_text(json.dumps({"status": "rendered_reference"}), encoding="utf-8")
        qc.write_text("", encoding="utf-8")
        tactile.write_text("", encoding="utf-8")
        assert seed == 5151
        assert design_data["name"] == "Render endpoint current GUI controls"
        assert design_data["trajectory"]["start_x_m"] == pytest.approx(expected_start["x_m"])
        assert design_data["trajectory"]["start_y_m"] == pytest.approx(expected_start["y_m"])
        assert design_data["trajectory"]["end_x_m"] == pytest.approx(expected_end["x_m"])
        assert design_data["trajectory"]["end_y_m"] == pytest.approx(expected_end["y_m"])
        assert design_data["trajectory"]["padding_pre_s"] == pytest.approx(controls["start_hold_s"])
        assert design_data["trajectory"]["padding_post_s"] == pytest.approx(controls["end_hold_s"])
        return RenderResult("rendered_reference", 0, Path(output_dir), Path(design_path), manifest, qc, wav_paths=(), tactile_events_path=tactile)

    monkeypatch.setattr(dashboard_app.render_backend, "render_design_with_3dti", fake_render)
    job = client.post(
        "/api/render",
        json={
            "participant_id": "P515",
            "design": design_to_dict(design),
            "trajectory_controls": controls,
        },
    ).json()
    done = _wait_job(client, job["job_id"])

    assert done["status"] == "succeeded"
    assert done["result"]["status"] == "rendered_reference"
    assert done["result"]["exit_code"] == 0


def test_dashboard_prepare_session_and_focus_job(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)

    prepared = client.post("/api/session/prepare", json={"participant_id": "P001"}).json()
    assert prepared["session"]["session_id"].startswith("P001_")
    assert prepared["session"]["blocks"]

    class FakeProcess:
        pid = 12345

    monkeypatch.setattr(dashboard_app.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())
    job = client.post("/api/focus/start").json()
    done = _wait_job(client, job["job_id"])
    assert done["status"] == "succeeded"
    assert done["result"]["pid"] == 12345
