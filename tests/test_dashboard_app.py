from __future__ import annotations

import base64
import json
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
from peripersonal_space_toolkit.design import AudioFileSpec, ProtocolSpec, default_design, save_design
from peripersonal_space_toolkit.render_backend import RenderResult, build_render_config


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
    )
    return TestClient(create_app(controller))


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(50):
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["status"] in {"succeeded", "failed"}:
            return data
        time.sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")


def test_dashboard_static_assets_are_packaged():
    dashboard_files = files("peripersonal_space_toolkit.dashboard")
    viewer_files = files("peripersonal_space_toolkit.viewer")
    assert dashboard_files.joinpath("index.html").is_file()
    assert dashboard_files.joinpath("styles.css").is_file()
    assert dashboard_files.joinpath("app.js").is_file()
    assert viewer_files.joinpath("trajectory-viewer.js").is_file()

    html = dashboard_files.joinpath("index.html").read_text(encoding="utf-8")
    app_js = dashboard_files.joinpath("app.js").read_text(encoding="utf-8")
    viewer_js = viewer_files.joinpath("trajectory-viewer.js").read_text(encoding="utf-8")
    assert 'href="styles.css"' in html
    assert 'src="app.js"' in html
    assert 'src="../viewer/index.html"' in html
    assert 'id="audio-file-input"' in html
    assert 'id="import-audio-spatialize"' in html
    assert 'id="import-audio-preserve"' in html
    assert 'id="generated-noise-select"' in html
    assert 'id="noise-list"' in html
    assert 'id="source-counts"' in html
    assert "Stimulus Selection" in html
    assert "Dry Custom Tone" in html
    assert "Already Looming / Control" in html
    assert "IMPORTED_AUDIO_HANDLING" in app_js
    assert "PROCEDURAL_NOISE_TYPES" in app_js
    assert "noise-source-card" in app_js
    assert "START_MARKER_COLOR" in viewer_js
    assert "END_MARKER_COLOR" in viewer_js
    assert "end_marker_color" in viewer_js
    assert "/api/" not in html


def test_dashboard_pages_companion_contract(tmp_path: Path):
    client = _client(tmp_path)

    root = client.get("/", follow_redirects=False)
    assert root.status_code in {302, 307}
    assert root.headers["location"] == "/dashboard/index.html"

    health = client.get("/api/health", headers={"Origin": "https://georgefejer91.github.io"})
    assert health.status_code == 200
    assert health.json()["service"] == "pps-dashboard-companion"
    assert health.headers["access-control-allow-origin"] == "https://georgefejer91.github.io"


def test_dashboard_state_templates_and_design_update(tmp_path: Path):
    client = _client(tmp_path)

    state = client.get("/api/state").json()
    assert state["design"]["name"]
    assert state["templates"]
    assert state["render"]["wav_count"] == 1

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
        )
    ]

    config = build_render_config(design, seed=20250604, output_dir=tmp_path)

    assert config["source"]["type"] == "imported_audio"
    imported = config["source"]["noises"][0]
    assert imported["source_kind"] == "imported_audio"
    assert imported["source_render_mode"] == "spatialize"
    assert imported["path"] == str(source)
    assert imported["gain"] == 0.75


def test_dashboard_render_job_uses_existing_render_backend(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)

    def fake_render(design_path, output_dir, *, seed, **_kwargs):
        manifest = Path(output_dir) / "render_manifest.json"
        qc = Path(output_dir) / "render_qc.csv"
        tactile = Path(output_dir) / "render_tactile_events.csv"
        manifest.write_text(json.dumps({"status": "rendered_reference"}), encoding="utf-8")
        qc.write_text("", encoding="utf-8")
        tactile.write_text("", encoding="utf-8")
        return RenderResult("rendered_reference", 0, Path(output_dir), Path(design_path), manifest, qc, wav_paths=(), tactile_events_path=tactile)

    monkeypatch.setattr(dashboard_app.render_backend, "render_design_with_3dti", fake_render)
    job = client.post("/api/render", json={}).json()
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
