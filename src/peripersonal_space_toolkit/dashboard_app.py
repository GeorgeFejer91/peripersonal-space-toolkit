"""Local browser dashboard for researcher-facing PPS control."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import math
import random
import re
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, Callable

from . import render_backend
from .design import (
    AudioFileSpec,
    BlockSpec,
    NoiseDefinition,
    SUPPORTED_NOISE_TYPES,
    StimulusDesign,
    azimuth_to_display_rotation_deg,
    audio_file_summary,
    block_trial_rows,
    cartesian_to_spherical,
    default_design,
    design_from_dict,
    design_to_dict,
    has_trial_strips,
    load_design,
    participant_block_orders,
    point_from_distance_rotation_height,
    protocol_summary,
    save_design,
    trajectory_endpoints_xyz,
    validate_design,
)
from .session_runner import (
    DEFAULT_RENDER_DIR,
    DEFAULT_SESSION_ROOT,
    RunPackage,
    available_stimulus_wavs,
    prepare_run_package,
    preflight_run_package,
    rendered_wavs,
)
from .templates import (
    DEFAULT_STUDY_TEMPLATE_ID,
    StudyTemplate,
    load_templates,
    study_template_bibtex,
    study_template_citation_label,
    study_template_csl_json,
)
from .preload_inventory import ensure_preload_assets, load_preload_inventory, preload_inventory_payload, profile_asset_status


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESIGN_PATH = REPO_ROOT / "configs" / "stimulus_design.generated.json"
TEMPLATE_DIR = REPO_ROOT / "study_templates"
DEFAULT_IMPORT_DIR = REPO_ROOT / "local_data" / "dashboard_audio"
DEFAULT_PREVIEW_DIR = REPO_ROOT / "local_data" / "dashboard_previews"
TRIAL_PREVIEW_LIMIT = 240
CUSTOM_TEMPLATE_IDS = {"custom", "__custom__"}
DEFAULT_WEB_ORIGINS = ("https://georgefejer91.github.io",)


@dataclass
class DashboardJob:
    job_id: str
    kind: str
    status: str = "queued"
    message: str = ""
    result: dict[str, Any] | None = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, DashboardJob] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, func: Callable[[], dict[str, Any]]) -> DashboardJob:
        job = DashboardJob(job_id=uuid.uuid4().hex[:12], kind=kind)
        with self._lock:
            self._jobs[job.job_id] = job

        def _run() -> None:
            self._update(job.job_id, status="running", message=f"{kind} started")
            try:
                result = func()
            except Exception as exc:
                self._update(job.job_id, status="failed", error=str(exc), message=f"{kind} failed")
            else:
                self._update(job.job_id, status="succeeded", result=_json_ready(result), message=f"{kind} complete")

        threading.Thread(target=_run, daemon=True).start()
        return job

    def get(self, job_id: str) -> DashboardJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, limit: int = 12) -> list[DashboardJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)[:limit]

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = time.time()


class DashboardController:
    def __init__(
        self,
        *,
        design_path: Path = DEFAULT_DESIGN_PATH,
        render_dir: Path = DEFAULT_RENDER_DIR,
        session_root: Path = DEFAULT_SESSION_ROOT,
        template_dir: Path = TEMPLATE_DIR,
        import_dir: Path = DEFAULT_IMPORT_DIR,
        preview_dir: Path = DEFAULT_PREVIEW_DIR,
    ) -> None:
        self.design_path = Path(design_path)
        self.render_dir = Path(render_dir)
        self.session_root = Path(session_root)
        self.template_dir = Path(template_dir)
        self.import_dir = Path(import_dir)
        self.preview_dir = Path(preview_dir)
        self.templates = load_templates(self.template_dir)
        self.preload_inventory = load_preload_inventory(REPO_ROOT)
        self.design = self._load_initial_design()
        self.participant_id = "P001"
        self.current_run_package: RunPackage | None = None
        self.jobs = JobManager()
        self._lock = threading.Lock()

    def _load_initial_design(self) -> StimulusDesign:
        if self.design_path.exists():
            try:
                design = load_design(self.design_path)
                if not _should_replace_saved_design_with_default_profile(design):
                    return _normalize_study5_event_sequence_labels(design)
            except Exception:
                pass
        return self._default_profile_design()

    def _default_profile_design(self) -> StimulusDesign:
        template = next((item for item in self.templates if item.template_id == DEFAULT_STUDY_TEMPLATE_ID), None)
        if template is None:
            return default_design()
        return _normalize_study5_event_sequence_labels(_copy_design(template.design))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            design = _copy_design(self.design)
            participant_id = self.participant_id
            package = self.current_run_package
        preflight = _preflight_to_dict(
            preflight_run_package(design, participant_id, render_dir=self.render_dir, require_audio=False)
        )
        return {
            "design": design_to_dict(design),
            "design_path": str(self.design_path),
            "participant_id": participant_id,
            "templates": self.templates_payload(),
            "selected_template": design.study_profile_id,
            "custom_workflow": _custom_workflow_status(design, participant_id),
            "trajectory_controls": _trajectory_controls(design),
            "viewer_payload": trajectory_viewer_payload(design),
            "protocol_summary": protocol_summary(design),
            "trial_preview": _trial_preview_rows(design),
            "participant_orders": _participant_orders(design),
            "validation": validate_design(design),
            "render": _render_status(self.render_dir, design),
            "preload_inventory": profile_asset_status(
                design.study_profile_id,
                inventory=self.preload_inventory,
                repo_root=REPO_ROOT,
            ),
            "preflight": preflight,
            "session": _package_to_dict(package),
            "jobs": [_job_to_dict(job) for job in self.jobs.recent()],
        }

    def templates_payload(self) -> list[dict[str, Any]]:
        return [
            _template_to_dict(
                template,
                asset_status=profile_asset_status(
                    template.template_id,
                    inventory=self.preload_inventory,
                    repo_root=REPO_ROOT,
                ),
            )
            for template in self.templates
        ]

    def preload_inventory_payload(self) -> dict[str, Any]:
        return preload_inventory_payload(
            [template.template_id for template in self.templates],
            repo_root=REPO_ROOT,
        )

    def sync_preload_assets(self, template_id: str) -> dict[str, Any]:
        return ensure_preload_assets(
            template_id,
            inventory=self.preload_inventory,
            repo_root=REPO_ROOT,
        )

    def load_template(self, template_id: str) -> dict[str, Any]:
        if template_id in CUSTOM_TEMPLATE_IDS:
            return self.load_custom_design()
        template = next((item for item in self.templates if item.template_id == template_id), None)
        if template is None:
            raise KeyError(template_id)
        self.sync_preload_assets(template_id)
        with self._lock:
            self.design = _normalize_study5_event_sequence_labels(_copy_design(template.design))
            self.current_run_package = None
        return self.snapshot()

    def load_custom_design(self) -> dict[str, Any]:
        design = default_design()
        design.name = "Custom PPS design"
        design.study_profile_id = ""
        design.study_profile_title = ""
        design.study_profile_notes = ""
        design.study_profile_reference_parameters = {"dashboard_mode": "custom"}
        design.noises = []
        design.custom_looming_files = []
        design.prestimulus_files = []
        design.protocol.soa_values_ms = []
        design.protocol.spatial_values_cm = []
        design.protocol.catch_trial_percentage = 0.0
        design.protocol.include_baseline_trials = False
        design.protocol.blocks = 1
        design.protocol.participants = 1
        with self._lock:
            self.design = design
            self.participant_id = ""
            self.current_run_package = None
        return self.snapshot()

    def update_design(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if "participant_id" in payload:
                participant_id = str(payload.get("participant_id") or "").strip()
                self.participant_id = participant_id or ("" if _is_custom_design(self.design) else "P001")
            if "design" in payload:
                self.design = design_from_dict(dict(payload["design"]))
            elif any(key in payload for key in ("name", "trajectory", "protocol", "noises")):
                self.design = design_from_dict(payload)
            if "trajectory_controls" in payload:
                self.design = _apply_trajectory_controls(self.design, dict(payload["trajectory_controls"]))
            self.design = _normalize_study5_event_sequence_labels(self.design)
            self.current_run_package = None
            save_design(self.design, self.design_path)
        return self.snapshot()

    def start_render_job(self, payload: dict[str, Any]) -> DashboardJob:
        if payload:
            self.update_design(payload)
        with self._lock:
            design = _copy_design(self.design)
            participant_id = self.participant_id
            self.current_run_package = None
        _require_custom_workflow_ready(design, participant_id, require_participant=False)
        seed = int(design.protocol.random_seed or 20250604)
        render_dir = self.render_dir

        def _render() -> dict[str, Any]:
            render_dir.mkdir(parents=True, exist_ok=True)
            design_path = render_dir / "stimulus_design.for_dashboard_render.json"
            save_design(design, design_path)
            result = render_backend.render_design_with_3dti(design_path, render_dir, seed=seed)
            return {
                "status": result.status,
                "exit_code": result.exit_code,
                "output_dir": str(result.output_dir),
                "manifest_path": str(result.manifest_path),
                "qc_path": str(result.qc_path),
                "wav_paths": [str(path) for path in result.wav_paths],
                "tactile_events_path": str(result.tactile_events_path) if result.tactile_events_path else "",
            }

        return self.jobs.start("render", _render)

    def start_bake_stimulus_job(self, payload: dict[str, Any]) -> DashboardJob:
        recipe = dict(payload.get("bake_recipe") or {})
        if not recipe:
            raise ValueError("Choose a stimulus source before baking.")
        design_payload = {key: value for key, value in payload.items() if key != "bake_recipe"}
        if design_payload:
            self.update_design(design_payload)
        with self._lock:
            design = _copy_design(self.design)
        label = _unique_stimulus_label(_bake_recipe_label(recipe), design)
        bake_design, source_kind, source_payload = _design_for_bake_recipe(design, recipe, label)
        seed = int(design.protocol.random_seed or 20250604)
        render_dir = self.render_dir

        def _bake() -> dict[str, Any]:
            render_dir.mkdir(parents=True, exist_ok=True)
            design_path = render_dir / f"stimulus_design.bake_{_slug(label)}.json"
            save_design(bake_design, design_path)
            result = render_backend.render_design_with_3dti(
                design_path,
                render_dir,
                seed=seed,
                engine="python-sofa-reference",
                include_tactile=False,
            )
            wav_path = _baked_wav_path(result, label)
            if wav_path is None or not wav_path.exists():
                raise RuntimeError(f"Bake did not create a WAV for {label}.")

            with self._lock:
                if source_kind == "generated_noise":
                    source = NoiseDefinition(**source_payload)
                    self.design.noises.append(source)
                    saved_source = asdict(source)
                else:
                    source = AudioFileSpec(
                        label=label,
                        path=str(wav_path),
                        target_duration_s=float(source_payload.get("target_duration_s", design.trajectory.total_duration_s)),
                        render_mode="preserve",
                        gain=1.0,
                        motion_mode="looming",
                    )
                    self.design.custom_looming_files.append(source)
                    saved_source = asdict(source)
                self.current_run_package = None
                save_design(self.design, self.design_path)

            return {
                "status": result.status,
                "exit_code": result.exit_code,
                "source_kind": source_kind,
                "source": saved_source,
                "wav_path": str(wav_path),
                "manifest_path": str(result.manifest_path),
                "qc_path": str(result.qc_path),
                "include_tactile": False,
                "local_only": True,
                "message": "Stimulus was baked by the local companion backend; no online upload was performed.",
            }

        return self.jobs.start("stimulus_bake", _bake)

    def prepare_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload:
            self.update_design(payload)
        with self._lock:
            design = _copy_design(self.design)
            participant_id = self.participant_id
        _require_custom_workflow_ready(design, participant_id, require_participant=True)
        package = prepare_run_package(
            design,
            participant_id,
            render_dir=self.render_dir,
            session_root=self.session_root,
        )
        with self._lock:
            self.current_run_package = package
        return self.snapshot()

    def import_audio_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        filename = _safe_filename(str(payload.get("filename") or "audio.wav"))
        encoded = str(payload.get("content_base64") or "")
        if not encoded:
            raise ValueError("Audio import is missing file content.")
        if "," in encoded:
            encoded = encoded.split(",", 1)[1]
        try:
            content = base64.b64decode(encoded, validate=True)
        except binascii.Error as exc:
            raise ValueError("Audio import content is not valid base64.") from exc
        if not content:
            raise ValueError("Audio import file is empty.")

        self.import_dir.mkdir(parents=True, exist_ok=True)
        path = self.import_dir / f"{uuid.uuid4().hex[:10]}_{filename}"
        path.write_bytes(content)
        label = str(payload.get("label") or Path(filename).stem).strip() or Path(filename).stem
        duration_s = _float(payload.get("target_duration_s"), 0.0)
        if duration_s <= 0:
            try:
                duration_s = float(audio_file_summary(path)["duration_s"])
            except Exception:
                duration_s = 4.0
        render_mode = str(payload.get("render_mode") or "preserve").strip().lower()
        if render_mode not in {"spatialize", "preserve"}:
            render_mode = "preserve"
        placement = str(payload.get("placement") or "before").strip().lower()
        if placement not in {"before", "after"}:
            placement = "before"
        motion_mode = str(payload.get("motion_mode") or "looming").strip().lower()
        if motion_mode not in {"looming", "stationary"}:
            motion_mode = "looming"
        audio = AudioFileSpec(
            label=label,
            path=str(path),
            target_duration_s=duration_s,
            render_mode=render_mode,
            gain=_float(payload.get("gain"), 1.0),
            placement=placement,
            target_source_label=str(payload.get("target_source_label") or "").strip(),
            phase=str(payload.get("phase") or "").strip(),
            gap_s=max(0.0, _float(payload.get("gap_s"), 0.0)),
            sequence_order=max(0, int(_float(payload.get("sequence_order"), 0.0))),
            motion_mode=motion_mode,
        )
        return {
            "audio": asdict(audio),
            "local_only": True,
            "message": "Stored by the local companion backend; no online upload was performed.",
        }

    def preview_trial_strip_audio(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "design" in payload:
            design = design_from_dict(dict(payload["design"]))
        else:
            with self._lock:
                design = _copy_design(self.design)
        if "trajectory_controls" in payload:
            design = _apply_trajectory_controls(design, dict(payload["trajectory_controls"]))

        strips = [strip for strip in design.protocol.trial_strips if strip.elements]
        if not strips:
            raise ValueError("Create an event sequence before previewing audio.")
        strip_index = max(0, int(_float(payload.get("strip_index"), 0)))
        if strip_index >= len(strips):
            raise ValueError("The requested event sequence does not exist.")
        return _trial_strip_audio_preview(
            design,
            strips[strip_index],
            strip_index=strip_index,
            render_dir=self.render_dir,
            preview_dir=self.preview_dir,
        )

    def open_local_folder(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_path = str(payload.get("path") or "").strip()
        if not raw_path:
            raise ValueError("No local path was provided.")
        target = Path(raw_path).expanduser()
        if not target.is_absolute():
            target = REPO_ROOT / target
        target = target.resolve()
        allowed_roots = [
            self.render_dir.resolve(),
            self.import_dir.resolve(),
            self.session_root.resolve(),
            self.design_path.resolve().parent,
            (REPO_ROOT / "assets" / "preloads").resolve(),
        ]
        if not any(target == root or root in target.parents for root in allowed_roots):
            raise ValueError("Local folder opening is limited to dashboard-managed folders.")
        folder = target if target.is_dir() else target.parent
        if not folder.exists():
            raise FileNotFoundError(f"Local folder does not exist: {folder}")
        if sys.platform.startswith("win"):
            if target.exists() and target.is_file():
                subprocess.Popen(["explorer.exe", f"/select,{target}"])
            else:
                subprocess.Popen(["explorer.exe", str(folder)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        return {
            "local_only": True,
            "path": str(target),
            "folder": str(folder),
            "message": "Opened by the local companion backend.",
        }

    def start_audio_stress_job(self) -> DashboardJob:
        command = [
            sys.executable,
            "-m",
            "peripersonal_space_toolkit.audio_device_stress",
            "--device-query",
            "Komplete",
            "--mode",
            "callback",
            "--iterations",
            "1",
            "--duration-s",
            "2",
            "--latency",
            "0.010",
            "--blocksize",
            "256",
        ]

        def _stress() -> dict[str, Any]:
            completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=45, check=False)
            return {
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "command": command,
            }

        return self.jobs.start("audio_stress", _stress)

    def start_focus_job(self) -> DashboardJob:
        with self._lock:
            package = self.current_run_package
        if package is None:
            raise RuntimeError("Prepare a session before starting native Focus Mode.")
        command = [
            sys.executable,
            "-m",
            "peripersonal_space_toolkit.focus_app",
            "--session-manifest",
            str(package.manifest_path),
        ]

        def _focus() -> dict[str, Any]:
            process = subprocess.Popen(command, cwd=REPO_ROOT)
            return {
                "pid": process.pid,
                "command": command,
                "session_manifest": str(package.manifest_path),
            }

        return self.jobs.start("focus_start", _focus)


def create_app(
    controller: DashboardController | None = None,
    *,
    web_origins: list[str] | tuple[str, ...] | None = None,
) -> Any:
    try:
        from fastapi import Body, FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import RedirectResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError("Install the web extra to run the dashboard: pip install -e .[web]") from exc

    controller = controller or DashboardController()
    app = FastAPI(title="PPS Local Dashboard", docs_url=None, redoc_url=None)
    configured_origins = DEFAULT_WEB_ORIGINS if web_origins is None else web_origins
    origins = [origin.rstrip("/") for origin in configured_origins if origin]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
            allow_credentials=False,
        )
    dashboard_dir = files("peripersonal_space_toolkit.dashboard")
    viewer_dir = files("peripersonal_space_toolkit.viewer")

    @app.get("/")
    def index() -> Any:
        return RedirectResponse(url="/dashboard/index.html")

    app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir)), name="dashboard")
    app.mount("/viewer", StaticFiles(directory=str(viewer_dir)), name="viewer")
    controller.preview_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/api/trial-row-previews", StaticFiles(directory=str(controller.preview_dir)), name="trial_row_previews")

    @app.get("/api/state")
    def api_state() -> dict[str, Any]:
        return controller.snapshot()

    @app.get("/api/health")
    def api_health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "pps-dashboard-companion",
            "local_only": True,
            "render_dir": str(controller.render_dir),
            "session_root": str(controller.session_root),
        }

    @app.get("/api/templates")
    def api_templates() -> list[dict[str, Any]]:
        return controller.templates_payload()

    @app.get("/api/preloads")
    def api_preloads() -> dict[str, Any]:
        return controller.preload_inventory_payload()

    @app.post("/api/preloads/{template_id}/sync")
    def api_sync_preload(template_id: str) -> dict[str, Any]:
        return controller.sync_preload_assets(template_id)

    @app.post("/api/templates/{template_id}/load")
    def api_load_template(template_id: str) -> dict[str, Any]:
        try:
            return controller.load_template(template_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Template not found: {template_id}") from exc

    @app.post("/api/design")
    def api_design(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.update_design(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/render")
    def api_render(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            job = controller.start_render_job(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _job_to_dict(job)

    @app.post("/api/stimulus/bake")
    def api_bake_stimulus(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            job = controller.start_bake_stimulus_job(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _job_to_dict(job)

    @app.post("/api/session/prepare")
    def api_prepare(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.prepare_session(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/audio/stress")
    def api_audio_stress() -> dict[str, Any]:
        return _job_to_dict(controller.start_audio_stress_job())

    @app.post("/api/audio/import")
    def api_audio_import(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.import_audio_source(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/trials/preview-row")
    def api_preview_trial_row(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.preview_trial_strip_audio(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/local/open-folder")
    def api_open_local_folder(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.open_local_folder(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/focus/start")
    def api_focus_start() -> dict[str, Any]:
        try:
            job = controller.start_focus_job()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _job_to_dict(job)

    @app.get("/api/jobs/{job_id}")
    def api_job(job_id: str) -> dict[str, Any]:
        job = controller.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        return _job_to_dict(job)

    return app


def trajectory_viewer_payload(design: StimulusDesign, *, preview_mode: str = "2d") -> dict[str, Any]:
    start, end = trajectory_endpoints_xyz(design.trajectory)
    start_spherical = cartesian_to_spherical(start["x_m"], start["y_m"], start["z_m"])
    end_spherical = cartesian_to_spherical(end["x_m"], end["y_m"], end["z_m"])
    radius_m = max(float(start_spherical["radius_m"]), float(end_spherical["radius_m"]), 0.1)
    return {
        "preview_mode": preview_mode,
        "radius_m": radius_m,
        "path_length_m": float(design.trajectory.path_length_m),
        "movement_duration_s": float(design.trajectory.movement_duration_s),
        "start": start,
        "end": end,
    }


def _apply_trajectory_controls(design: StimulusDesign, controls: dict[str, Any]) -> StimulusDesign:
    updated = _copy_design(design)
    start_distance_cm = _float(controls.get("start_distance_cm"), updated.trajectory.start_radius_m * 100.0)
    end_distance_cm = _float(controls.get("end_distance_cm"), updated.trajectory.end_radius_m * 100.0)
    start_rotation_deg = _float(controls.get("start_rotation_deg"), azimuth_to_display_rotation_deg(updated.trajectory.azimuth_start_deg))
    end_rotation_deg = _float(controls.get("end_rotation_deg"), azimuth_to_display_rotation_deg(updated.trajectory.azimuth_end_deg))
    start_height_cm = _float(controls.get("start_height_cm"), 0.0)
    end_height_cm = _float(controls.get("end_height_cm"), 0.0)
    movement_duration_s = max(0.1, _float(controls.get("movement_duration_s"), updated.trajectory.movement_duration_s or 3.0))
    start_hold_s = max(0.0, _float(controls.get("start_hold_s"), updated.trajectory.padding_pre_s))
    end_hold_s = max(0.0, _float(controls.get("end_hold_s"), updated.trajectory.padding_post_s))
    start = point_from_distance_rotation_height(start_distance_cm, start_rotation_deg, start_height_cm)
    end = point_from_distance_rotation_height(end_distance_cm, end_rotation_deg, end_height_cm)
    path_length = math.dist((start["x_m"], start["y_m"], start["z_m"]), (end["x_m"], end["y_m"], end["z_m"]))
    updated.trajectory.coordinate_mode = "cartesian"
    updated.trajectory.path_direction = "custom"
    updated.trajectory.start_radius_m = start_distance_cm / 100.0
    updated.trajectory.end_radius_m = end_distance_cm / 100.0
    updated.trajectory.azimuth_start_deg = ((start_rotation_deg + 180.0) % 360.0) - 180.0
    updated.trajectory.azimuth_end_deg = ((end_rotation_deg + 180.0) % 360.0) - 180.0
    updated.trajectory.start_x_m = start["x_m"]
    updated.trajectory.start_y_m = start["y_m"]
    updated.trajectory.start_z_m = start["z_m"]
    updated.trajectory.end_x_m = end["x_m"]
    updated.trajectory.end_y_m = end["y_m"]
    updated.trajectory.end_z_m = end["z_m"]
    updated.trajectory.path_length_m = path_length
    updated.trajectory.propagation_speed_mps = path_length / movement_duration_s if movement_duration_s > 0 else 0.0
    updated.trajectory.padding_pre_s = start_hold_s
    updated.trajectory.padding_post_s = end_hold_s
    return updated


def _trajectory_controls(design: StimulusDesign) -> dict[str, float]:
    start, end = trajectory_endpoints_xyz(design.trajectory)
    start_spherical = cartesian_to_spherical(start["x_m"], start["y_m"], start["z_m"])
    end_spherical = cartesian_to_spherical(end["x_m"], end["y_m"], end["z_m"])
    return {
        "start_distance_cm": round(float(start_spherical["radius_m"]) * 100.0, 4),
        "end_distance_cm": round(float(end_spherical["radius_m"]) * 100.0, 4),
        "start_rotation_deg": round(azimuth_to_display_rotation_deg(float(start_spherical["azimuth_deg"])), 4),
        "end_rotation_deg": round(azimuth_to_display_rotation_deg(float(end_spherical["azimuth_deg"])), 4),
        "start_height_cm": round(float(start["z_m"]) * 100.0, 4),
        "end_height_cm": round(float(end["z_m"]) * 100.0, 4),
        "movement_duration_s": round(float(design.trajectory.movement_duration_s), 4),
        "start_hold_s": round(float(design.trajectory.padding_pre_s), 4),
        "end_hold_s": round(float(design.trajectory.padding_post_s), 4),
    }


def _trial_preview_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    rows = []
    for row in block_trial_rows(design)[:TRIAL_PREVIEW_LIMIT]:
        rows.append(
            {
                "block": row.get("block_label", ""),
                "trial": row.get("block_trial_index", ""),
                "type": row.get("trial_type", ""),
                "phase": row.get("trial_strip_label", row.get("phase", "")),
                "soa_ms": row.get("soa_ms", ""),
                "space_cm": row.get("spatial_value_cm", ""),
                "tactile_site": row.get("tactile_site", ""),
                "sequence": row.get("sequence_labels") or row.get("noise_label", row.get("noise_type", "")),
            }
        )
    return rows


def _participant_orders(design: StimulusDesign) -> list[dict[str, Any]]:
    orders = participant_block_orders(design)
    return [{"participant": participant, "block_order": " -> ".join(blocks)} for participant, blocks in list(orders.items())[:80]]


def _render_status(render_dir: Path, design: StimulusDesign | None = None) -> dict[str, Any]:
    manifest_path = Path(render_dir) / "render_manifest.json"
    manifest = _load_json(manifest_path)
    wavs = available_stimulus_wavs(design, render_dir) if design is not None else rendered_wavs(render_dir)
    return {
        "render_dir": str(render_dir),
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_path.exists(),
        "status": manifest.get("status", "missing") if isinstance(manifest, dict) else "missing",
        "render_engine": manifest.get("render_engine", "") if isinstance(manifest, dict) else "",
        "wav_count": len(wavs),
        "wavs": [_json_ready(asdict(wav)) for wav in wavs],
    }


def _trial_strip_audio_preview(
    design: StimulusDesign,
    strip: Any,
    *,
    strip_index: int,
    render_dir: Path,
    preview_dir: Path,
) -> dict[str, Any]:
    chunks = _trial_strip_preview_chunks(design, strip, render_dir)
    if not chunks:
        raise ValueError("This event sequence has no playable audio elements.")
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / f"row_{strip_index + 1}_{_slug(strip.label or 'filmstrip')}_{uuid.uuid4().hex[:8]}.wav"
    duration_s = _write_trial_strip_preview_wav(preview_path, chunks)
    return {
        "url": f"/api/trial-row-previews/{preview_path.name}",
        "path": str(preview_path),
        "row_label": strip.label or f"Row {strip_index + 1}",
        "sequence": [chunk["label"] for chunk in chunks],
        "selected_source_label": next((chunk["label"] for chunk in chunks if chunk["kind"] == "looming_stimulus"), ""),
        "duration_s": duration_s,
        "local_only": True,
        "auditory_preview_only": True,
        "message": "Temporary browser-playable event-sequence preview assembled by the local companion backend.",
    }


def _trial_strip_preview_chunks(design: StimulusDesign, strip: Any, render_dir: Path) -> list[dict[str, Any]]:
    fixed = {asset.label: asset for asset in design.prestimulus_files if asset.label.strip()}
    source_assets = {asset.label: asset for asset in design.custom_looming_files if asset.label.strip()}
    source_wavs = _stimulus_wav_lookup(design, render_dir)
    chunks: list[dict[str, Any]] = []
    for element in strip.elements:
        if element.kind == "fixed_audio":
            asset = fixed.get(element.source_label)
            if asset is None:
                raise ValueError(f"Event sequence references an unknown fixed clip: {element.source_label}")
            chunks.append(
                {
                    "kind": "fixed_audio",
                    "label": asset.label,
                    "path": _resolve_dashboard_local_path(asset.path),
                    "gain": asset.gain,
                }
            )
        elif element.kind == "looming_stimulus":
            labels = [label for label in element.source_labels if label] or list(source_wavs)
            playable = [(label, _source_key(label)) for label in labels if _source_key(label) in source_wavs]
            if not playable:
                raise ValueError("Bake or render at least one selected looming source before previewing this event sequence.")
            selected, selected_key = random.choice(playable)
            asset = source_assets.get(selected)
            chunks.append(
                {
                    "kind": "looming_stimulus",
                    "label": selected,
                    "path": source_wavs[selected_key],
                    "gain": asset.gain if asset is not None else 1.0,
                }
            )
    return chunks


def _stimulus_wav_lookup(design: StimulusDesign, render_dir: Path) -> dict[str, Path]:
    lookup: dict[str, Path] = {}
    for wav in available_stimulus_wavs(design, render_dir):
        keys = {
            wav.label,
            wav.path.stem,
            wav.path.name,
            wav.path.stem.replace("looming_", ""),
            _slug(wav.label).replace("_", " "),
        }
        for key in keys:
            normalized = _source_key(key)
            if normalized and normalized not in lookup:
                lookup[normalized] = wav.path
    return lookup


def _source_key(value: str) -> str:
    return str(value or "").replace("_", " ").replace("-", " ").strip().lower()


def _resolve_dashboard_local_path(value: str | Path) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _write_trial_strip_preview_wav(path: Path, chunks: list[dict[str, Any]]) -> float:
    try:
        import numpy as np
        import soundfile as sf
        from scipy import signal
    except ImportError as exc:
        raise RuntimeError("Install numpy, scipy, and soundfile to preview event sequences.") from exc

    sample_rate = 0
    audio_chunks = []
    for chunk in chunks:
        source_path = Path(chunk["path"])
        if not source_path.exists():
            raise FileNotFoundError(f"Preview audio file was not found: {source_path}")
        data, rate = sf.read(str(source_path), dtype="float32", always_2d=True)
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] > 2:
            data = data[:, :2]
        if not sample_rate:
            sample_rate = int(rate)
        elif int(rate) != sample_rate:
            divisor = math.gcd(sample_rate, int(rate))
            data = signal.resample_poly(data, sample_rate // divisor, int(rate) // divisor, axis=0)
        gain = max(0.0, float(chunk.get("gain", 1.0)))
        audio_chunks.append(data * gain)

    if not audio_chunks or not sample_rate:
        raise ValueError("No audio data was available for this event sequence.")
    preview = np.concatenate(audio_chunks, axis=0)
    peak = float(np.max(np.abs(preview))) if preview.size else 0.0
    if peak > 0.99:
        preview = preview / peak * 0.99
    sf.write(str(path), preview, sample_rate, subtype="PCM_16")
    return float(preview.shape[0] / sample_rate)


def _bake_recipe_label(recipe: dict[str, Any]) -> str:
    label = str(recipe.get("label") or "").strip()
    if label:
        return label
    if str(recipe.get("kind") or "") == "generated_noise":
        return f"{str(recipe.get('noise_type') or 'pink').strip().title()} noise"
    audio = recipe.get("audio") if isinstance(recipe.get("audio"), dict) else {}
    return str(audio.get("label") or recipe.get("filename") or "Baked stimulus").strip() or "Baked stimulus"


def _unique_stimulus_label(label: str, design: StimulusDesign) -> str:
    base = str(label or "Baked stimulus").strip() or "Baked stimulus"
    existing = {noise.label.strip().lower() for noise in design.noises}
    existing.update(asset.label.strip().lower() for asset in design.custom_looming_files)
    if base.lower() not in existing:
        return base
    index = 2
    while f"{base} {index}".lower() in existing:
        index += 1
    return f"{base} {index}"


def _design_for_bake_recipe(design: StimulusDesign, recipe: dict[str, Any], label: str) -> tuple[StimulusDesign, str, dict[str, Any]]:
    bake_design = _copy_design(design)
    bake_design.name = f"{design.name} - baked {label}"
    bake_design.noises = []
    bake_design.custom_looming_files = []
    bake_design.prestimulus_files = []
    kind = str(recipe.get("kind") or "generated_noise").strip().lower()
    if kind == "generated_noise":
        noise_type = str(recipe.get("noise_type") or "").strip().lower()
        if noise_type not in SUPPORTED_NOISE_TYPES:
            raise ValueError(f"Unsupported generated-noise type: {noise_type or 'missing'}")
        source = {
            "label": label,
            "noise_type": noise_type,
            "azimuth_deg": 0.0,
            "elevation_deg": 0.0,
            "gain": max(0.01, _float(recipe.get("gain"), 1.0)),
            "motion_mode": "looming",
        }
        bake_design.noises = [NoiseDefinition(**source)]
        return bake_design, "generated_noise", source

    if kind == "imported_audio":
        audio = recipe.get("audio") if isinstance(recipe.get("audio"), dict) else {}
        path = str(audio.get("path") or recipe.get("path") or "").strip()
        if not path or not Path(path).expanduser().exists():
            raise ValueError("Imported audio must be stored locally before baking.")
        render_mode = str(recipe.get("render_mode") or audio.get("render_mode") or "preserve").strip().lower()
        if render_mode not in {"spatialize", "preserve"}:
            render_mode = "preserve"
        duration_s = max(0.1, _float(audio.get("target_duration_s") or recipe.get("target_duration_s"), design.trajectory.total_duration_s))
        gain = max(0.01, _float(audio.get("gain") or recipe.get("gain"), 1.0))
        bake_design.custom_looming_files = [
            AudioFileSpec(
                label=label,
                path=path,
                target_duration_s=duration_s,
                render_mode=render_mode,
                gain=gain,
                motion_mode="looming",
            )
        ]
        return bake_design, "imported_audio", {"target_duration_s": duration_s, "render_mode": render_mode}

    raise ValueError(f"Unsupported bake recipe kind: {kind or 'missing'}")


def _baked_wav_path(result: render_backend.RenderResult, label: str) -> Path | None:
    if result.wav_paths:
        label_slug = _slug(label).lower()
        for path in result.wav_paths:
            if label_slug in _slug(path.stem).lower():
                return Path(path)
        return Path(result.wav_paths[0])
    candidate = result.output_dir / f"looming_{_slug(label)}.wav"
    return candidate if candidate.exists() else None


def _preflight_to_dict(preflight: Any) -> dict[str, Any]:
    return {
        "participant_id": preflight.participant_id,
        "valid_design": preflight.valid_design,
        "participant_ready": preflight.participant_ready,
        "render_ready": preflight.render_ready,
        "schedule_ready": preflight.schedule_ready,
        "audio_route": preflight.audio_route,
        "audio_ready": preflight.audio_ready,
        "ready": preflight.ready,
        "messages": list(preflight.messages),
    }


def _custom_workflow_status(design: StimulusDesign, participant_id: str) -> dict[str, Any]:
    step_checks = [
        ("study", "Study Profile", _custom_study_missing(design)),
        ("stimulus", "Stimulus Design", _custom_stimulus_missing(design)),
        ("trials", "Trial Assembly", _custom_trials_missing(design)),
        ("run", "Run Preparation", _custom_run_missing(participant_id)),
        ("review", "Review", []),
    ]
    is_custom = _is_custom_design(design)
    if not is_custom:
        return {
            "is_custom": False,
            "current_step": "review",
            "ready_to_render": True,
            "ready_to_prepare": True,
            "missing": [],
            "steps": [
                {"id": step_id, "label": label, "complete": True, "missing": []}
                for step_id, label, _missing in step_checks
            ],
        }

    steps = [
        {"id": step_id, "label": label, "complete": not missing, "missing": list(missing)}
        for step_id, label, missing in step_checks
    ]
    current_step = next((step["id"] for step in steps if not step["complete"]), "review")
    render_missing = _missing_for_steps(steps, {"study", "stimulus", "trials"})
    prepare_missing = _missing_for_steps(steps, {"study", "stimulus", "trials", "run"})
    return {
        "is_custom": True,
        "current_step": current_step,
        "ready_to_render": not render_missing,
        "ready_to_prepare": not prepare_missing,
        "missing": prepare_missing,
        "steps": steps,
    }


def _require_custom_workflow_ready(
    design: StimulusDesign,
    participant_id: str,
    *,
    require_participant: bool,
) -> None:
    workflow = _custom_workflow_status(design, participant_id)
    if not workflow["is_custom"]:
        return
    ready_key = "ready_to_prepare" if require_participant else "ready_to_render"
    if workflow[ready_key]:
        return
    step_ids = {"study", "stimulus", "trials", "run"} if require_participant else {"study", "stimulus", "trials"}
    missing = _missing_for_steps(workflow["steps"], step_ids)
    raise RuntimeError(f"Custom design is incomplete: {'; '.join(missing)}")


def _is_custom_design(design: StimulusDesign) -> bool:
    return str(design.study_profile_reference_parameters.get("dashboard_mode", "")).lower() == "custom"


def _missing_for_steps(steps: list[dict[str, Any]], step_ids: set[str]) -> list[str]:
    missing: list[str] = []
    for step in steps:
        if step["id"] not in step_ids:
            continue
        missing.extend(str(item) for item in step.get("missing", []))
    return missing


def _custom_study_missing(design: StimulusDesign) -> list[str]:
    name = design.name.strip()
    if not name or name.lower() in {"custom pps design", "untitled pps design"}:
        return ["Choose a custom design name."]
    return []


def _custom_stimulus_missing(design: StimulusDesign) -> list[str]:
    missing: list[str] = []
    t = design.trajectory
    if t.path_length_m <= 0 or t.movement_duration_s <= 0:
        missing.append("Choose a valid sound trajectory and movement duration.")
    has_noise = any(
        noise.label.strip()
        and noise.noise_type.lower() in SUPPORTED_NOISE_TYPES
        and noise.gain > 0
        for noise in design.noises
    )
    has_imported_source = any(
        asset.label.strip()
        and asset.path.strip()
        and Path(asset.path).expanduser().exists()
        and asset.target_duration_s > 0
        for asset in design.custom_looming_files
    )
    if not has_noise and not has_imported_source:
        missing.append("Add at least one procedural noise or custom looming audio source.")
    return missing


def _custom_trials_missing(design: StimulusDesign) -> list[str]:
    missing: list[str] = []
    p = design.protocol
    if p.repetitions_per_condition < 1:
        missing.append("Set repetitions to at least 1.")
    if p.blocks < 1:
        missing.append("Set block count to at least 1.")
    if p.participants < 1:
        missing.append("Set planned participants to at least 1.")
    if not p.soa_values_ms:
        missing.append("Enter at least one SOA value.")
    if not has_trial_strips(p):
        missing.append("Create at least one within-block event sequence.")
    if not p.tactile_sites:
        missing.append("Keep at least one tactile site.")
    if not p.respiratory_phases:
        missing.append("Keep at least one respiratory phase.")
    return missing


def _custom_run_missing(participant_id: str) -> list[str]:
    if not str(participant_id or "").strip():
        return ["Enter a participant ID."]
    return []


def _template_to_dict(template: StudyTemplate, *, asset_status: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "template_id": template.template_id,
        "title": template.title,
        "citation_label": study_template_citation_label(template),
        "citation": template.citation,
        "bibtex": study_template_bibtex(template),
        "csl_json": study_template_csl_json(template),
        "doi": template.doi,
        "source_url": template.source_url,
        "verification_status": template.verification_status,
        "notes": template.notes,
    }
    if asset_status is not None:
        payload["preload_asset_status"] = asset_status
    return payload


def _package_to_dict(package: RunPackage | None) -> dict[str, Any] | None:
    if package is None:
        return None
    return {
        "participant_id": package.participant_id,
        "session_id": package.session_id,
        "created_at": package.created_at,
        "session_dir": str(package.session_dir),
        "manifest_path": str(package.manifest_path),
        "design_path": str(package.design_path),
        "protocol_path": str(package.protocol_path),
        "blocks": [_json_ready(asdict(block)) for block in package.blocks],
    }


def _job_to_dict(job: DashboardJob) -> dict[str, Any]:
    return _json_ready(asdict(job))


def _copy_design(design: StimulusDesign) -> StimulusDesign:
    return design_from_dict(design_to_dict(design))


def _normalize_study5_event_sequence_labels(design: StimulusDesign) -> StimulusDesign:
    if design.study_profile_id != DEFAULT_STUDY_TEMPLATE_ID:
        return design
    updated = _copy_design(design)
    label_map = {
        "Inhale row": "Inhale event",
        "Exhale row": "Exhale event",
    }
    for strip in updated.protocol.trial_strips:
        strip.label = label_map.get(strip.label, strip.label)
    if "filmstrip trial rows" in updated.study_profile_notes:
        updated.study_profile_notes = updated.study_profile_notes.replace(
            "filmstrip trial rows",
            "within-block event sequences",
        )
    return updated


def _should_replace_saved_design_with_default_profile(design: StimulusDesign) -> bool:
    if design.study_profile_id:
        return False
    mode = str(design.study_profile_reference_parameters.get("dashboard_mode", "")).strip().lower()
    if mode == "custom":
        return True
    return design.name.strip() in {"", "Study 5 PPS design", "Custom PPS design"}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_filename(value: str) -> str:
    name = Path(value).name.strip() or "audio.wav"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return safe or "audio.wav"


def _slug(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip()).strip("._")
    return safe or "stimulus"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the local PPS browser dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind. Defaults to local-only 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8766, help="Port for the local dashboard.")
    parser.add_argument("--no-browser", action="store_true", help="Start the server without opening a browser.")
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN_PATH, help="Working design JSON path.")
    parser.add_argument("--render-dir", type=Path, default=DEFAULT_RENDER_DIR, help="Rendered stimulus handoff directory.")
    parser.add_argument("--session-root", type=Path, default=DEFAULT_SESSION_ROOT, help="Session output root directory.")
    parser.add_argument(
        "--web-origin",
        action="append",
        default=[],
        help="Allow one hosted dashboard origin to call this local backend, for example https://user.github.io.",
    )
    parser.add_argument(
        "--no-default-web-origin",
        action="store_true",
        help="Do not allow the default project GitHub Pages origin.",
    )
    return parser


def _running_dashboard_url(host: str, port: int) -> str | None:
    url = f"http://{host}:{port}/"
    try:
        with urllib.request.urlopen(f"{url}api/state", timeout=1.5) as response:
            if response.status == 200:
                return url
    except Exception:
        return None
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    url = f"http://{args.host}:{args.port}/"
    running_url = _running_dashboard_url(args.host, args.port)
    if running_url is not None:
        print(f"PPS dashboard is already running at {running_url}")
        if not args.no_browser:
            webbrowser.open(running_url)
        return 0

    app = create_app(
        DashboardController(
            design_path=args.design,
            render_dir=args.render_dir,
            session_root=args.session_root,
        ),
        web_origins=[] if args.no_default_web_origin else [*DEFAULT_WEB_ORIGINS, *args.web_origin],
    )
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install the web extra to run the dashboard: pip install -e .[web]") from exc
    print(f"PPS dashboard running at {url}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
