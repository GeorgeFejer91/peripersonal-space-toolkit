from __future__ import annotations

import wave
from pathlib import Path

import pytest

from peripersonal_space_toolkit.dashboard_app import DashboardController
from peripersonal_space_toolkit.design import block_trial_rows, default_design, save_design, validate_design
from peripersonal_space_toolkit.preload_inventory import load_preload_inventory, profile_asset_status
from peripersonal_space_toolkit.templates import DEFAULT_STUDY_TEMPLATE_ID, load_templates


def _study5_template():
    root = Path(__file__).resolve().parents[1]
    templates = load_templates(root / "study_templates")
    return next(template for template in templates if template.template_id == DEFAULT_STUDY_TEMPLATE_ID)


def test_study5_is_first_default_preload():
    root = Path(__file__).resolve().parents[1]
    templates = load_templates(root / "study_templates")

    assert templates[0].template_id == DEFAULT_STUDY_TEMPLATE_ID


def test_dashboard_starts_from_study5_when_no_deliberate_profile_is_saved(tmp_path: Path):
    missing_design_path = tmp_path / "missing.json"
    fresh = DashboardController(
        design_path=missing_design_path,
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
    ).snapshot()

    assert fresh["selected_template"] == DEFAULT_STUDY_TEMPLATE_ID
    assert fresh["design"]["prestimulus_files"][0]["label"] == "Inhale instruction"
    assert fresh["design"]["custom_looming_files"][0]["label"] == "Pink frontal"
    assert fresh["design"]["protocol"]["trial_strips"][0]["label"] == "Inhale row"
    assert fresh["preload_inventory"]["status"] == "ready"
    assert fresh["preflight"]["render_ready"] is True

    scratch_design = default_design()
    scratch_design.name = "Manual scratch design"
    scratch_design.study_profile_reference_parameters = {"dashboard_mode": "custom"}
    scratch_path = tmp_path / "custom_scratch.json"
    save_design(scratch_design, scratch_path)
    from_scratch = DashboardController(
        design_path=scratch_path,
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
    ).snapshot()

    assert from_scratch["selected_template"] == DEFAULT_STUDY_TEMPLATE_ID


def test_dashboard_preserves_deliberate_saved_profile(tmp_path: Path):
    saved_design = _study5_template().design
    saved_design.name = "Edited Study 5 working copy"
    saved_path = tmp_path / "saved_profile.json"
    save_design(saved_design, saved_path)

    state = DashboardController(
        design_path=saved_path,
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
    ).snapshot()

    assert state["selected_template"] == DEFAULT_STUDY_TEMPLATE_ID
    assert state["design"]["name"] == "Edited Study 5 working copy"


def test_unpublished_study5_template_preloads_breathing_assets_and_filmstrip():
    root = Path(__file__).resolve().parents[1]
    study5 = _study5_template()
    design = study5.design

    assert study5.doi == ""
    assert study5.verification_status == "verified"
    assert design.study_profile_title == "Study 5 PPS box-breathing profile"
    assert design.name == "Study 5 PPS box-breathing design"
    assert [clip.label for clip in design.prestimulus_files] == ["Inhale instruction", "Exhale instruction"]
    assert [clip.phase for clip in design.prestimulus_files] == ["Inhale", "Exhale"]
    assert all(clip.motion_mode == "stationary" for clip in design.prestimulus_files)
    assert all(clip.target_duration_s == pytest.approx(4.0) for clip in design.prestimulus_files)
    assert design.noises == []
    assert [asset.label for asset in design.custom_looming_files] == [
        "Pink frontal",
        "Blue frontal",
        "White frontal",
        "Brown frontal",
    ]

    for clip in design.prestimulus_files:
        path = root / clip.path
        assert path.exists()
        with wave.open(str(path), "rb") as wav:
            assert wav.getframerate() == 44100
            assert wav.getnframes() == 176400
            assert wav.getnframes() / wav.getframerate() == pytest.approx(4.0)

    for asset in design.custom_looming_files:
        path = root / asset.path
        assert path.exists()
        assert asset.render_mode == "preserve"
        assert asset.motion_mode == "looming"
        with wave.open(str(path), "rb") as wav:
            assert wav.getframerate() == 44100
            assert wav.getnchannels() == 2
            assert wav.getnframes() == 176400
            assert wav.getnframes() / wav.getframerate() == pytest.approx(4.0)

    inventory = load_preload_inventory(root)
    asset_status = profile_asset_status(DEFAULT_STUDY_TEMPLATE_ID, inventory=inventory, repo_root=root)
    assert asset_status["status"] == "ready"
    assert asset_status["asset_count"] == 4
    assert all(asset["sha256_ok"] is True for asset in asset_status["assets"])

    strips = design.protocol.trial_strips
    assert [strip.label for strip in strips] == ["Inhale row", "Exhale row"]
    assert [strip.elements[0].source_label for strip in strips] == ["Inhale instruction", "Exhale instruction"]
    for strip in strips:
        assert strip.elements[0].kind == "fixed_audio"
        assert strip.elements[0].randomized is False
        assert strip.elements[1].kind == "looming_stimulus"
        assert strip.elements[1].randomized is True
        assert strip.elements[1].source_labels == [asset.label for asset in design.custom_looming_files]

    assert validate_design(design) == []
    rows = block_trial_rows(design)
    noncatch = [row for row in rows if row["trial_type"] == "Audio-Tactile"]
    assert len(noncatch) == design.protocol.blocks * 2 * len(design.custom_looming_files) * len(design.protocol.soa_values_ms)
    assert {row["trial_strip_label"] for row in rows} == {"Inhale row", "Exhale row"}
    assert all("instruction | " in row["sequence_labels"] for row in rows)
