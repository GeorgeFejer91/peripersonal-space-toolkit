from __future__ import annotations

import wave
from pathlib import Path

import pytest

from peripersonal_space_toolkit.design import block_trial_rows, validate_design
from peripersonal_space_toolkit.templates import load_templates


def test_unpublished_study5_template_preloads_breathing_assets_and_filmstrip():
    root = Path(__file__).resolve().parents[1]
    templates = load_templates(root / "study_templates")
    study5 = next(template for template in templates if template.template_id == "study5_box_breathing_pps")
    design = study5.design

    assert study5.doi == ""
    assert study5.verification_status == "verified"
    assert design.study_profile_title == "Study 5 PPS box-breathing profile"
    assert design.name == "Study 5 PPS box-breathing design"
    assert [clip.label for clip in design.prestimulus_files] == ["Inhale instruction", "Exhale instruction"]
    assert [clip.phase for clip in design.prestimulus_files] == ["Inhale", "Exhale"]
    assert all(clip.motion_mode == "stationary" for clip in design.prestimulus_files)
    assert all(clip.target_duration_s == pytest.approx(4.0) for clip in design.prestimulus_files)

    for clip in design.prestimulus_files:
        path = root / clip.path
        assert path.exists()
        with wave.open(str(path), "rb") as wav:
            assert wav.getframerate() == 44100
            assert wav.getnframes() == 176400
            assert wav.getnframes() / wav.getframerate() == pytest.approx(4.0)

    strips = design.protocol.trial_strips
    assert [strip.label for strip in strips] == ["Inhale row", "Exhale row"]
    assert [strip.elements[0].source_label for strip in strips] == ["Inhale instruction", "Exhale instruction"]
    for strip in strips:
        assert strip.elements[0].kind == "fixed_audio"
        assert strip.elements[0].randomized is False
        assert strip.elements[1].kind == "looming_stimulus"
        assert strip.elements[1].randomized is True
        assert strip.elements[1].source_labels == [noise.label for noise in design.noises]

    assert validate_design(design) == []
    rows = block_trial_rows(design)
    noncatch = [row for row in rows if row["trial_type"] == "Audio-Tactile"]
    assert len(noncatch) == design.protocol.blocks * 2 * len(design.noises) * len(design.protocol.soa_values_ms)
    assert {row["trial_strip_label"] for row in rows} == {"Inhale row", "Exhale row"}
    assert all("instruction | " in row["sequence_labels"] for row in rows)
