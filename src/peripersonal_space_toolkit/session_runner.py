"""Qt-facing session package and runner controller.

This module is intentionally independent from Qt.  The desktop designer uses it
to prepare one reproducible run folder and to drive the same event/audio
primitives used by the legacy runner.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from .design import StimulusDesign, experiment_schedule_rows, export_protocol_csv, save_design, validate_design
from .session_analysis import analyze_session_events, format_analysis_summary, write_analysis_csvs
from .session_events import SessionEventLogger
from .timing_events import TimingEventHub


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RENDER_DIR = REPO_ROOT / "artifacts" / "qt_runner_render"
DEFAULT_SESSION_ROOT = REPO_ROOT / "local_data" / "sessions"
PREFERRED_AUDIO_ROUTE = "Komplete Audio ASIO Driver"
REQUESTED_LATENCY_S = 0.010
REQUESTED_BLOCKSIZE = 256
RUN_PACKAGE_SCHEMA = "pps-run-session.v1"
RESPONSE_MARKER_GAIN = 0.05


@dataclass(frozen=True)
class RenderedWav:
    path: Path
    label: str
    duration_s: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    sha256: str = ""


@dataclass(frozen=True)
class RunBlock:
    index: int
    label: str
    manifest_path: Path
    wav_path: Path
    trial_count: int
    duration_s: float


@dataclass(frozen=True)
class RunPackage:
    participant_id: str
    session_id: str
    created_at: str
    session_dir: Path
    design_path: Path
    protocol_path: Path
    manifest_path: Path
    render_manifest_path: Path | None
    blocks: list[RunBlock] = field(default_factory=list)


@dataclass(frozen=True)
class RunPreflight:
    participant_id: str
    valid_design: bool
    participant_ready: bool
    render_ready: bool
    schedule_ready: bool
    audio_route: str
    audio_ready: bool
    render_dir: Path
    rendered_wavs: list[RenderedWav] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.valid_design and self.participant_ready and self.render_ready and self.schedule_ready and self.audio_ready


@dataclass(frozen=True)
class SessionRunResult:
    completed: bool
    interrupted: bool
    session_dir: Path
    events_csv: Path
    events_xdf: Path
    analysis_outputs: dict[str, Path]
    summary_text: str
    warnings: list[str] = field(default_factory=list)
    lsl_status: dict[str, Any] = field(default_factory=dict)
    recording_paths: list[Path] = field(default_factory=list)


ProgressCallback = Callable[[dict[str, Any]], None]
EventCallback = Callable[[str], None]


def sanitize_participant_id(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return safe[:64]


def render_manifest_path(render_dir: Path = DEFAULT_RENDER_DIR) -> Path:
    return Path(render_dir) / "render_manifest.json"


def rendered_wavs(render_dir: Path = DEFAULT_RENDER_DIR) -> list[RenderedWav]:
    render_dir = Path(render_dir)
    manifest = _load_json(render_manifest_path(render_dir))
    outputs = manifest.get("wav_outputs", []) if isinstance(manifest, dict) else []
    wavs: list[RenderedWav] = []
    for item in outputs:
        path = Path(str(item.get("path", "")))
        if not path.is_absolute():
            path = render_dir / path
        if path.exists():
            wavs.append(_wav_info(path, sha256=str(item.get("sha256", ""))))
    if wavs:
        return sorted(wavs, key=lambda item: item.label)
    return sorted((_wav_info(path) for path in render_dir.glob("*.wav")), key=lambda item: item.label)


def preflight_run_package(
    design: StimulusDesign,
    participant_id: str,
    *,
    render_dir: Path = DEFAULT_RENDER_DIR,
    require_audio: bool = False,
) -> RunPreflight:
    messages: list[str] = []
    clean_participant = sanitize_participant_id(participant_id)
    design_warnings = validate_design(design)
    if design_warnings:
        messages.extend(f"Design: {warning}" for warning in design_warnings[:4])
    participant_ready = bool(clean_participant)
    if not participant_ready:
        messages.append("Participant ID is required.")

    wavs = rendered_wavs(render_dir)
    render_ready = bool(wavs)
    if not render_ready:
        messages.append("Rendered looming WAVs are missing.")

    schedule_rows = experiment_schedule_rows(design)
    schedule_ready = bool(schedule_rows)
    if not schedule_ready:
        messages.append("No trial schedule rows are available.")

    audio_ready = True
    if require_audio:
        audio_ready = _preferred_audio_route_available()
        if not audio_ready:
            messages.append(f"Preferred audio route not detected: {PREFERRED_AUDIO_ROUTE}.")

    return RunPreflight(
        participant_id=clean_participant,
        valid_design=not design_warnings,
        participant_ready=participant_ready,
        render_ready=render_ready,
        schedule_ready=schedule_ready,
        audio_route=f"{PREFERRED_AUDIO_ROUTE}, 3 channels, latency {REQUESTED_LATENCY_S:.3f}, blocksize {REQUESTED_BLOCKSIZE}",
        audio_ready=audio_ready,
        render_dir=Path(render_dir),
        rendered_wavs=wavs,
        messages=messages,
    )


def prepare_run_package(
    design: StimulusDesign,
    participant_id: str,
    *,
    render_dir: Path = DEFAULT_RENDER_DIR,
    session_root: Path = DEFAULT_SESSION_ROOT,
    created_at: datetime | None = None,
) -> RunPackage:
    clean_participant = sanitize_participant_id(participant_id)
    if not clean_participant:
        raise ValueError("Participant ID is required.")
    wavs = rendered_wavs(render_dir)
    if not wavs:
        raise FileNotFoundError(f"No rendered WAV files found in {render_dir}.")

    created_at = created_at or datetime.now()
    timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    session_id = f"{clean_participant}_{timestamp}"
    session_dir = Path(session_root) / session_id
    block_dir = session_dir / "blocks"
    analysis_dir = session_dir / "analysis"
    block_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)

    design_path = session_dir / "design.json"
    protocol_path = session_dir / "protocol_schedule.csv"
    save_design(design, design_path)
    export_protocol_csv(design, protocol_path)

    rows = _participant_rows(design, clean_participant)
    if not rows:
        raise ValueError("The current design produced no participant schedule rows.")

    wav_by_label = _wav_lookup(wavs)
    blocks: list[RunBlock] = []
    for block_index, (block_label, block_rows) in enumerate(_group_rows_by_block(rows), start=1):
        manifest_path = block_dir / f"Block_{block_index:02d}_{_slug(block_label)}.csv"
        wav_path = block_dir / f"Block_{block_index:02d}_{_slug(block_label)}_concatenated.wav"
        _write_block_manifest(manifest_path, block_rows, clean_participant)
        duration_s = _materialize_block_wav(wav_path, block_rows, wav_by_label)
        if duration_s <= 0:
            duration_s = wav_by_label["__default__"].duration_s
        blocks.append(
            RunBlock(
                index=block_index,
                label=block_label,
                manifest_path=manifest_path,
                wav_path=wav_path,
                trial_count=len(block_rows),
                duration_s=float(duration_s),
            )
        )

    manifest_path = session_dir / "session_manifest.json"
    render_manifest = render_manifest_path(render_dir)
    package = RunPackage(
        participant_id=clean_participant,
        session_id=session_id,
        created_at=created_at.isoformat(timespec="seconds"),
        session_dir=session_dir,
        design_path=design_path,
        protocol_path=protocol_path,
        manifest_path=manifest_path,
        render_manifest_path=render_manifest if render_manifest.exists() else None,
        blocks=blocks,
    )
    _write_session_manifest(package, wavs)
    return package


def load_run_package(manifest_path: Path) -> RunPackage:
    """Rehydrate a prepared run package from its session manifest."""
    manifest_path = Path(manifest_path)
    data = _load_json(manifest_path)
    if data.get("schema") != RUN_PACKAGE_SCHEMA:
        raise ValueError(f"Unsupported run package manifest: {manifest_path}")
    session_dir = manifest_path.parent
    blocks = [
        RunBlock(
            index=int(item["index"]),
            label=str(item["label"]),
            manifest_path=Path(item["manifest_path"]),
            wav_path=Path(item["wav_path"]),
            trial_count=int(item["trial_count"]),
            duration_s=float(item["duration_s"]),
        )
        for item in data.get("blocks", [])
    ]
    return RunPackage(
        participant_id=str(data.get("participant_id", "")),
        session_id=str(data.get("session_id", session_dir.name)),
        created_at=str(data.get("created_at", "")),
        session_dir=session_dir,
        design_path=Path(str(data.get("design_path", session_dir / "design.json"))),
        protocol_path=Path(str(data.get("protocol_path", session_dir / "protocol_schedule.csv"))),
        manifest_path=manifest_path,
        render_manifest_path=Path(str(data["render_manifest_path"])) if data.get("render_manifest_path") else None,
        blocks=blocks,
    )


class SessionRunnerController:
    """Runs a prepared package and writes recoverable session outputs."""

    def __init__(self, package: RunPackage, *, audio_engine: Any | None = None):
        self.package = package
        self.audio_engine = audio_engine
        self.logger = SessionEventLogger(package.participant_id)
        self.events = TimingEventHub(
            self.logger,
            enable_lsl=True,
            session_id=package.session_id,
            participant_id=package.participant_id,
        )
        self._stop_requested = False
        self._analysis_outputs: dict[str, Path] = {}
        self._summary_text = ""
        self._recording_paths: list[Path] = []
        self._accepting_responses = False

    def run(
        self,
        *,
        progress_callback: ProgressCallback | None = None,
        event_callback: EventCallback | None = None,
    ) -> SessionRunResult:
        completed = False
        interrupted = False
        owns_engine = self.audio_engine is None
        engine = self.audio_engine
        self.events.log(
            "session_start",
            session_dir=str(self.package.session_dir),
            lsl_enabled=self.events.lsl_status.enabled,
            lsl_message=self.events.lsl_status.message,
        )
        try:
            if engine is None:
                engine = self._create_audio_engine()
                self.audio_engine = engine
            for block in self.package.blocks:
                if self._stop_requested:
                    interrupted = True
                    break
                self._emit(event_callback, f"Block {block.index}: {block.label}")
                block_start_unix = time.time()
                block_start_monotonic = time.perf_counter()
                self.events.log(
                    "block_start",
                    unix_time=block_start_unix,
                    monotonic_time=block_start_monotonic,
                    block_number=block.index,
                    block_label=block.label,
                    block_path=str(block.wav_path),
                    trial_count=block.trial_count,
                )
                planned_logged = False
                recording_path = self.package.session_dir / "recordings" / f"Block_{block.index:02d}_{_slug(block.label)}_loopback.wav"
                recording_started = self._start_backup_recording(engine, recording_path, block)

                def _progress(elapsed_s: float, current_block: RunBlock = block) -> None:
                    if progress_callback:
                        progress_callback(
                            {
                                "block_index": current_block.index,
                                "block_label": current_block.label,
                                "elapsed_s": float(elapsed_s),
                                "duration_s": current_block.duration_s,
                                "session_id": self.package.session_id,
                            }
                        )

                def _audio_event(payload: dict[str, Any], current_block: RunBlock = block) -> None:
                    nonlocal planned_logged
                    event_type = str(payload.pop("event_type", "audio_event"))
                    unix_time = payload.pop("unix_time", None)
                    monotonic_time = payload.pop("monotonic_time", None)
                    event = self.events.log(
                        event_type,
                        unix_time=unix_time,
                        monotonic_time=monotonic_time,
                        block_number=current_block.index,
                        block_label=current_block.label,
                        block_path=str(current_block.wav_path),
                        **payload,
                    )
                    if event_type == "audio_sample_zero" and not planned_logged:
                        self._accepting_responses = True
                        self.logger.extend_planned_block_events(
                            current_block.manifest_path,
                            block_start_unix=event.unix_time,
                            block_start_monotonic=event.monotonic_time,
                            participant_id=self.package.participant_id,
                            part_number=1,
                            block_number=current_block.index,
                            trial_duration_s=_trial_duration_s(current_block),
                            stimulus_segment_onset_s=0.0,
                        )
                        planned_logged = True

                ok = bool(engine.play_block(str(block.wav_path), progress_callback=_progress, audio_event_callback=_audio_event))
                if not planned_logged:
                    self.events.log(
                        "timing_anchor_fallback",
                        block_number=block.index,
                        block_label=block.label,
                        reason="audio_sample_zero was not emitted by the audio engine",
                    )
                    self.logger.extend_planned_block_events(
                        block.manifest_path,
                        block_start_unix=block_start_unix,
                        block_start_monotonic=block_start_monotonic,
                        participant_id=self.package.participant_id,
                        part_number=1,
                        block_number=block.index,
                        trial_duration_s=_trial_duration_s(block),
                        stimulus_segment_onset_s=0.0,
                    )
                self._stop_backup_recording(engine, recording_path, block, interrupted=(not ok or self._stop_requested), started=recording_started)
                self._accepting_responses = False
                self.events.log("block_end", block_number=block.index, block_label=block.label, completed=ok)
                if not ok or self._stop_requested:
                    interrupted = True
                    break
            completed = not interrupted
            self.events.log("session_end", completed=completed, interrupted=interrupted)
        except Exception as exc:
            interrupted = True
            self.events.log("session_error", message=str(exc))
            self._emit(event_callback, f"Run error: {exc}")
        finally:
            self._write_outputs()
            if owns_engine and self.audio_engine is not None and hasattr(self.audio_engine, "shutdown"):
                self.audio_engine.shutdown()

        return SessionRunResult(
            completed=completed,
            interrupted=interrupted,
            session_dir=self.package.session_dir,
            events_csv=self.package.session_dir / "events.csv",
            events_xdf=self.package.session_dir / "events.xdf",
            analysis_outputs=self._analysis_outputs,
            summary_text=self._summary_text,
            warnings=[] if completed else ["Session was interrupted before all blocks completed."],
            lsl_status=dict(self.events.lsl_status.__dict__),
            recording_paths=list(self._recording_paths),
        )

    def stop(self) -> None:
        self._stop_requested = True
        if self.audio_engine is not None and hasattr(self.audio_engine, "stop"):
            self.audio_engine.stop()
        self.events.log("operator_stop")

    def pause(self) -> None:
        if self.audio_engine is not None and hasattr(self.audio_engine, "pause"):
            self.audio_engine.pause()
        self.events.log("operator_pause")

    def resume(self) -> None:
        if self.audio_engine is not None and hasattr(self.audio_engine, "resume"):
            self.audio_engine.resume()
        self.events.log("operator_resume")

    def log_click(self, *, x: int | None = None, y: int | None = None, in_target: bool = True) -> None:
        during_playback = self._accepting_responses
        event = self.events.log("mouse_click", x=x if x is not None else "", y=y if y is not None else "", in_target=in_target, during_playback=during_playback)
        if during_playback and self.audio_engine is not None and hasattr(self.audio_engine, "trigger_click"):
            self.audio_engine.trigger_click(
                metadata={
                    "mouse_event_id": event.event_id,
                    "mouse_event_unix_time": event.unix_time,
                    "mouse_event_monotonic_time": event.monotonic_time,
                },
                marker_gain=RESPONSE_MARKER_GAIN,
            )

    def _create_audio_engine(self) -> Any:
        from .runner import CLICK_SOUND, AudioEngine, find_output_device

        device_idx, _device_name, _is_preferred = find_output_device()
        if device_idx is None:
            raise RuntimeError("No usable audio output device was found.")
        engine = AudioEngine(device_idx)
        if CLICK_SOUND:
            engine.load_click_sound(CLICK_SOUND)
        return engine

    def _write_outputs(self) -> None:
        events_csv = self.package.session_dir / "events.csv"
        events_xdf = self.package.session_dir / "events.xdf"
        self.logger.write_csv(events_csv)
        self.logger.write_xdf(
            events_xdf,
            metadata={
                "participant_id": self.package.participant_id,
                "session_id": self.package.session_id,
                "session_manifest": str(self.package.manifest_path),
                "lsl_status": dict(self.events.lsl_status.__dict__),
            },
        )
        analysis = analyze_session_events(self.logger.events)
        self._analysis_outputs = write_analysis_csvs(analysis, self.package.session_dir / "analysis", self.package.session_id)
        self._analysis_outputs["timing_qc"] = _write_timing_qc_csv(self.logger.events, self.package.session_dir / "analysis" / f"{self.package.session_id}_timing_qc.csv")
        self._summary_text = format_analysis_summary(analysis)
        (self.package.session_dir / "analysis_summary.txt").write_text(self._summary_text + "\n", encoding="utf-8")

    def _start_backup_recording(self, engine: Any, path: Path, block: RunBlock) -> bool:
        if not hasattr(engine, "start_recording"):
            self.events.log("recording_unavailable", block_number=block.index, block_label=block.label, reason="audio engine has no recording API")
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            started = bool(engine.start_recording(str(path)))
        except Exception as exc:
            self.events.log("recording_start_failed", block_number=block.index, block_label=block.label, path=str(path), message=str(exc))
            return False
        self.events.log(
            "recording_start",
            block_number=block.index,
            block_label=block.label,
            path=str(path),
            started=started,
            mode="hardware_loopback_preferred_wasapi_fallback",
        )
        if started:
            self._recording_paths.append(path)
        return started

    def _stop_backup_recording(self, engine: Any, path: Path, block: RunBlock, *, interrupted: bool, started: bool) -> None:
        if not started or not hasattr(engine, "stop_recording"):
            return
        try:
            engine.stop_recording(str(path), interrupted=interrupted)
            self.events.log("recording_end", block_number=block.index, block_label=block.label, path=str(path), interrupted=interrupted)
        except Exception as exc:
            self.events.log("recording_stop_failed", block_number=block.index, block_label=block.label, path=str(path), message=str(exc))

    @staticmethod
    def _emit(callback: EventCallback | None, message: str) -> None:
        if callback:
            callback(message)


def _preferred_audio_route_available() -> bool:
    try:
        import sounddevice as sd

        for device in sd.query_devices():
            name = str(device.get("name", "")).lower()
            hostapi = sd.query_hostapis(int(device.get("hostapi", 0))).get("name", "").lower()
            if "komplete" in name and "asio" in hostapi and int(device.get("max_output_channels", 0)) >= 3:
                return True
    except Exception:
        return False
    return False


def _participant_rows(design: StimulusDesign, participant_id: str) -> list[dict[str, Any]]:
    rows = experiment_schedule_rows(design)
    exact = [dict(row) for row in rows if str(row.get("participant_id", "")) == participant_id]
    if exact:
        return exact
    first_id = str(rows[0].get("participant_id", "")) if rows else ""
    fallback = [dict(row) for row in rows if str(row.get("participant_id", "")) == first_id]
    for row in fallback:
        row["participant_id"] = participant_id
        row["participant_index"] = ""
    return fallback


def _group_rows_by_block(rows: Iterable[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in rows:
        position = _as_int(row.get("participant_block_position"), default=_as_int(row.get("block_index"), default=1))
        label = str(row.get("block_label", f"Block {position}"))
        grouped.setdefault((position, label), []).append(row)
    return [(key[1], grouped[key]) for key in sorted(grouped)]


def _write_block_manifest(path: Path, rows: list[dict[str, Any]], participant_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "Participant_ID",
        "Part_Number",
        "Block_Number",
        "Block_Label",
        "Trial_Number",
        "Trial_Type",
        "SOA_ms",
        "Noise_Label",
        "Noise_Type",
        "Respiratory_Phase",
        "Tactile_Site",
        "Motion_Direction",
        "Spatial_Value_cm",
        "Azimuth_deg",
        "Elevation_deg",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            writer.writerow(
                {
                    "Participant_ID": participant_id,
                    "Part_Number": 1,
                    "Block_Number": row.get("participant_block_position", row.get("block_index", "")),
                    "Block_Label": row.get("block_label", ""),
                    "Trial_Number": index,
                    "Trial_Type": row.get("trial_type", ""),
                    "SOA_ms": row.get("soa_ms", ""),
                    "Noise_Label": row.get("noise_label", ""),
                    "Noise_Type": row.get("noise_type", ""),
                    "Respiratory_Phase": row.get("phase", ""),
                    "Tactile_Site": row.get("tactile_site", ""),
                    "Motion_Direction": row.get("motion_direction", ""),
                    "Spatial_Value_cm": row.get("spatial_value_cm", ""),
                    "Azimuth_deg": row.get("azimuth_deg", ""),
                    "Elevation_deg": row.get("elevation_deg", ""),
                }
            )


def _materialize_block_wav(path: Path, rows: list[dict[str, Any]], wav_by_label: dict[str, RenderedWav]) -> float:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("Install numpy and soundfile to prepare runnable session blocks.") from exc

    clips = []
    sample_rate = 0
    channels = 0
    default_wav = wav_by_label["__default__"]
    for row in rows:
        wav = _select_wav_for_row(row, wav_by_label, default_wav)
        data, sr = sf.read(str(wav.path), dtype="float32", always_2d=True)
        if sample_rate and sr != sample_rate:
            raise ValueError(f"Rendered WAV sample-rate mismatch: {wav.path}")
        sample_rate = int(sr)
        channels = max(channels, int(data.shape[1]))
        clips.append(data)
    if not clips:
        return 0.0
    padded = []
    for data in clips:
        if data.shape[1] < channels:
            pad = np.zeros((data.shape[0], channels - data.shape[1]), dtype=data.dtype)
            data = np.concatenate([data, pad], axis=1)
        padded.append(data)
    block = np.concatenate(padded, axis=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), block, sample_rate)
    return float(block.shape[0] / sample_rate) if sample_rate else 0.0


def _select_wav_for_row(row: dict[str, Any], wav_by_label: dict[str, RenderedWav], default_wav: RenderedWav) -> RenderedWav:
    candidates = [
        str(row.get("noise_label", "")),
        str(row.get("noise_type", "")),
        _slug(str(row.get("noise_label", ""))),
        _slug(str(row.get("noise_type", ""))),
    ]
    for candidate in candidates:
        key = candidate.strip().lower()
        if key and key in wav_by_label:
            return wav_by_label[key]
    return default_wav


def _wav_lookup(wavs: list[RenderedWav]) -> dict[str, RenderedWav]:
    lookup: dict[str, RenderedWav] = {"__default__": wavs[0]}
    for wav in wavs:
        for key in {wav.label, wav.path.stem, wav.path.name, wav.path.stem.replace("looming_", "")}:
            if key:
                lookup[key.strip().lower()] = wav
                lookup[_slug(key).lower()] = wav
    return lookup


def _wav_info(path: Path, *, sha256: str = "") -> RenderedWav:
    try:
        import soundfile as sf

        info = sf.info(str(path))
        duration_s = float(info.frames / info.samplerate) if info.samplerate else 0.0
        sample_rate = int(info.samplerate)
        channels = int(info.channels)
    except Exception:
        duration_s = 0.0
        sample_rate = 0
        channels = 0
    label = path.stem.replace("looming_", "").replace("_", " ")
    return RenderedWav(path=path, label=label, duration_s=duration_s, sample_rate=sample_rate, channels=channels, sha256=sha256)


def _write_session_manifest(package: RunPackage, wavs: list[RenderedWav]) -> None:
    manifest = {
        "schema": RUN_PACKAGE_SCHEMA,
        "participant_id": package.participant_id,
        "session_id": package.session_id,
        "created_at": package.created_at,
        "audio_route": {
            "preferred_device": PREFERRED_AUDIO_ROUTE,
            "channels": 3,
            "latency_s": REQUESTED_LATENCY_S,
            "blocksize": REQUESTED_BLOCKSIZE,
        },
        "timing": {
            "primary_response_source": "mouse_click event log plus optional LSL marker stream",
            "stimulus_anchor": "audio_sample_zero emitted by audio callback",
            "backup_trace": "hardware loopback preferred; WASAPI loopback is diagnostic fallback when available",
            "response_marker": {
                "channel": "tactile output",
                "gain": RESPONSE_MARKER_GAIN,
                "purpose": "sub-threshold physical QC marker, not primary RT source",
            },
            "lsl_stream": {
                "name": "PPSMarkers",
                "type": "Markers",
                "required": False,
            },
        },
        "design_path": str(package.design_path),
        "protocol_path": str(package.protocol_path),
        "render_manifest_path": str(package.render_manifest_path) if package.render_manifest_path else "",
        "source_wavs": [_json_ready(asdict(wav)) for wav in wavs],
        "blocks": [_json_ready(asdict(block)) for block in package.blocks],
        "outputs": {
            "events_csv": str(package.session_dir / "events.csv"),
            "events_xdf": str(package.session_dir / "events.xdf"),
            "analysis_dir": str(package.session_dir / "analysis"),
        },
    }
    package.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _write_timing_qc_csv(events: Iterable[Any], path: Path) -> Path:
    rows = []
    mouse_by_id: dict[int, Any] = {}
    markers = []
    for event in events:
        if getattr(event, "event_type", "") == "mouse_click":
            mouse_by_id[int(event.event_id)] = event
        elif getattr(event, "event_type", "") == "response_marker_start":
            markers.append(event)

    for marker in markers:
        payload = dict(getattr(marker, "payload", {}) or {})
        mouse_event_id = _as_int(payload.get("mouse_event_id"), default=0)
        mouse = mouse_by_id.get(mouse_event_id)
        delta_ms = ""
        if mouse is not None:
            delta_ms = (float(marker.unix_time) - float(mouse.unix_time)) * 1000.0
        rows.append(
            {
                "mouse_event_id": mouse_event_id or "",
                "response_marker_event_id": marker.event_id,
                "mouse_unix_time": "" if mouse is None else f"{mouse.unix_time:.9f}",
                "response_marker_unix_time": f"{marker.unix_time:.9f}",
                "marker_minus_mouse_ms": "" if delta_ms == "" else f"{delta_ms:.3f}",
                "marker_channel": payload.get("marker_channel", ""),
                "marker_gain": payload.get("marker_gain", ""),
                "block_number": payload.get("block_number", ""),
                "block_label": payload.get("block_label", ""),
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "mouse_event_id",
                "response_marker_event_id",
                "mouse_unix_time",
                "response_marker_unix_time",
                "marker_minus_mouse_ms",
                "marker_channel",
                "marker_gain",
                "block_number",
                "block_label",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _trial_duration_s(block: RunBlock) -> float:
    return max(0.001, block.duration_s / max(1, block.trial_count))


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return slug or "Block"


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
