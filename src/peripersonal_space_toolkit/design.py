"""Stimulus-design data model and SOFA/trajectory helpers."""

from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


SUPPORTED_NOISE_TYPES = ("pink", "blue", "violet", "white", "brown")
CUSTOM_AUDIO_NOISE_TYPE = "custom_audio"
SUPPORTED_IMPORTED_AUDIO_RENDER_MODES = ("spatialize", "preserve")
SUPPORTED_DIRECTIONS = ("approach", "recede", "left_to_right", "right_to_left", "custom")
SUPPORTED_COORDINATE_MODES = ("polar", "cartesian")
SUPPORTED_TRIAL_TYPES = ("Audio-Tactile", "Baseline", "Catch")
SUPPORTED_TRIAL_RANDOMIZATION = ("balanced_shuffle", "no_immediate_repeats", "ordered")
SUPPORTED_BLOCK_ORDER_RANDOMIZATION = ("counterbalanced_rotation", "seeded_random_permutation", "fixed")
DEFAULT_SOFA_FILE = "assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa"
DEFAULT_TRAJECTORY_PLANE_HEIGHT_M = 0.0
DEFAULT_TRAJECTORY_PLANE_LABEL = "listener head/ear center plane"
DISTANCE_CM_MIN = 1.0
DISTANCE_CM_MAX = 1000.0
ROTATION_DEG_MIN = -180.0
ROTATION_DEG_MAX = 180.0
DISPLAY_ROTATION_DEG_MIN = 0.0
DISPLAY_ROTATION_DEG_MAX = 360.0


@dataclass
class AudioFileSpec:
    label: str
    path: str
    target_duration_s: float = 4.0
    render_mode: str = "preserve"
    gain: float = 1.0


@dataclass
class NoiseDefinition:
    label: str
    noise_type: str
    azimuth_deg: float = 0.0
    elevation_deg: float = 0.0
    gain: float = 1.0


@dataclass
class BlockSpec:
    label: str
    stimulus_types: list[str] = field(default_factory=lambda: ["Audio-Tactile", "Baseline", "Catch"])


@dataclass
class TrajectorySpec:
    start_radius_m: float = 1.1
    end_radius_m: float = 0.1
    path_direction: str = "approach"
    coordinate_mode: str = "polar"
    start_x_m: float | None = None
    start_y_m: float | None = None
    start_z_m: float | None = None
    end_x_m: float | None = None
    end_y_m: float | None = None
    end_z_m: float | None = None
    path_length_m: float = 1.0
    propagation_speed_mps: float = 1.0 / 3.0
    azimuth_start_deg: float = 0.0
    azimuth_end_deg: float = 0.0
    elevation_deg: float = 0.0
    padding_pre_s: float = 0.5
    padding_post_s: float = 0.5
    sample_rate: int = 44100
    use_inverse_square: bool = True

    @property
    def movement_duration_s(self) -> float:
        if self.propagation_speed_mps <= 0:
            return 0.0
        return self.path_length_m / self.propagation_speed_mps

    @property
    def total_duration_s(self) -> float:
        return self.padding_pre_s + self.movement_duration_s + self.padding_post_s


@dataclass
class ProtocolSpec:
    repetitions_per_condition: int = 1
    soa_values_ms: list[int] = field(default_factory=lambda: [300, 800, 1500, 2200, 2700])
    spatial_values_cm: list[float] = field(default_factory=lambda: [100.0, 83.3, 60.0, 36.7, 20.0])
    pair_spatial_values_with_soas: bool = True
    auditory_motion_directions: list[str] = field(default_factory=lambda: ["looming"])
    tactile_sites: list[str] = field(default_factory=lambda: ["hand"])
    catch_trial_percentage: float = 10.0
    catch_trials_exact: int | None = None
    include_baseline_trials: bool = True
    baseline_soa_values_ms: list[int] = field(default_factory=list)
    respiratory_phases: list[str] = field(default_factory=lambda: ["Inhale", "Exhale"])
    blocks: int = 6
    block_specs: list[BlockSpec] = field(default_factory=list)
    trial_randomization_strategy: str = "no_immediate_repeats"
    block_order_randomization: str = "counterbalanced_rotation"
    max_consecutive_same_trial_type: int = 2
    participants: int = 50
    random_seed: int = 20250604


@dataclass
class StimulusDesign:
    name: str = "Study 5 PPS design"
    study_profile_id: str = ""
    study_profile_title: str = ""
    study_profile_notes: str = ""
    study_profile_reference_parameters: dict[str, Any] = field(default_factory=dict)
    sofa_file: str = DEFAULT_SOFA_FILE
    noises: list[NoiseDefinition] = field(default_factory=list)
    custom_looming_files: list[AudioFileSpec] = field(default_factory=list)
    prestimulus_files: list[AudioFileSpec] = field(default_factory=list)
    trajectory: TrajectorySpec = field(default_factory=TrajectorySpec)
    protocol: ProtocolSpec = field(default_factory=ProtocolSpec)


def default_design() -> StimulusDesign:
    return StimulusDesign(
        sofa_file=DEFAULT_SOFA_FILE,
        noises=[
            NoiseDefinition("Pink frontal", "pink", 0.0),
            NoiseDefinition("Blue frontal", "blue", 0.0),
            NoiseDefinition("White frontal", "white", 0.0),
            NoiseDefinition("Brown frontal", "brown", 0.0),
        ]
    )


def design_to_dict(design: StimulusDesign) -> dict[str, Any]:
    return asdict(design)


def _audio_file_specs_from_dicts(items: list[Any]) -> list[AudioFileSpec]:
    specs: list[AudioFileSpec] = []
    for item in items:
        if isinstance(item, str):
            specs.append(AudioFileSpec(label=Path(item).stem, path=item))
        else:
            specs.append(AudioFileSpec(**item))
    return specs


def design_from_dict(data: dict[str, Any]) -> StimulusDesign:
    noises = [NoiseDefinition(**item) for item in data.get("noises", [])]
    custom_looming_files = _audio_file_specs_from_dicts(data.get("custom_looming_files", []))
    prestimulus_files = _audio_file_specs_from_dicts(data.get("prestimulus_files", []))
    trajectory_data = dict(data.get("trajectory", {}))
    if "coordinate_mode" not in trajectory_data and any(
        key in trajectory_data
        for key in ("start_x_m", "start_y_m", "start_z_m", "end_x_m", "end_y_m", "end_z_m")
    ):
        trajectory_data["coordinate_mode"] = "cartesian"
    trajectory = TrajectorySpec(**trajectory_data)
    protocol_data = dict(data.get("protocol", {}))
    protocol_data["block_specs"] = [
        BlockSpec(**item) if isinstance(item, dict) else BlockSpec(str(item))
        for item in protocol_data.get("block_specs", [])
    ]
    protocol = ProtocolSpec(**protocol_data)
    return StimulusDesign(
        name=data.get("name", "Study 5 PPS design"),
        study_profile_id=data.get("study_profile_id", ""),
        study_profile_title=data.get("study_profile_title", ""),
        study_profile_notes=data.get("study_profile_notes", ""),
        study_profile_reference_parameters=dict(data.get("study_profile_reference_parameters", {})),
        sofa_file=data.get("sofa_file") or DEFAULT_SOFA_FILE,
        noises=noises,
        custom_looming_files=custom_looming_files,
        prestimulus_files=prestimulus_files,
        trajectory=trajectory,
        protocol=protocol,
    )


def load_design(path: Path) -> StimulusDesign:
    return design_from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_design(design: StimulusDesign, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(design_to_dict(design), indent=2), encoding="utf-8")


def audio_file_summary(path: Path) -> dict[str, Any]:
    try:
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("Install soundfile to inspect audio durations.") from exc

    info = sf.info(str(path))
    return {
        "frames": int(info.frames),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "duration_s": float(info.frames / info.samplerate) if info.samplerate else 0.0,
        "format": info.format,
    }


def _uses_cartesian_coordinates(spec: TrajectorySpec) -> bool:
    fields = (spec.start_x_m, spec.start_y_m, spec.start_z_m, spec.end_x_m, spec.end_y_m, spec.end_z_m)
    return spec.coordinate_mode == "cartesian" or any(value is not None for value in fields)


def cartesian_to_spherical(x_m: float, y_m: float, z_m: float) -> dict[str, float]:
    radius_m = math.sqrt(x_m**2 + y_m**2 + z_m**2)
    horizontal_radius = math.sqrt(x_m**2 + y_m**2)
    azimuth_deg = math.degrees(math.atan2(x_m, y_m)) if horizontal_radius else 0.0
    elevation_deg = math.degrees(math.atan2(z_m, horizontal_radius)) if radius_m else 0.0
    return {
        "radius_m": radius_m,
        "azimuth_deg": azimuth_deg,
        "elevation_deg": elevation_deg,
    }


def spherical_to_cartesian(radius_m: float, azimuth_deg: float, elevation_deg: float) -> dict[str, float]:
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    horizontal_radius = radius_m * math.cos(el)
    return {
        "x_m": horizontal_radius * math.sin(az),
        "y_m": horizontal_radius * math.cos(az),
        "z_m": radius_m * math.sin(el),
    }


def normalize_azimuth_deg(rotation_deg: float) -> float:
    return ((rotation_deg + 180.0) % 360.0) - 180.0


def azimuth_to_display_rotation_deg(azimuth_deg: float) -> float:
    return azimuth_deg % 360.0


def horizontal_point_from_distance_rotation(distance_cm: float, rotation_deg: float) -> dict[str, float]:
    return point_from_distance_rotation_height(distance_cm, rotation_deg, 0.0)


def point_from_distance_rotation_height(
    distance_cm: float,
    rotation_deg: float,
    height_cm: float = 0.0,
) -> dict[str, float]:
    if not DISTANCE_CM_MIN <= distance_cm <= DISTANCE_CM_MAX:
        raise ValueError(f"Distance must be between {DISTANCE_CM_MIN:g} and {DISTANCE_CM_MAX:g} cm.")
    if not DISPLAY_ROTATION_DEG_MIN <= rotation_deg <= DISPLAY_ROTATION_DEG_MAX:
        raise ValueError(
            f"Rotation must be between {DISPLAY_ROTATION_DEG_MIN:g} and {DISPLAY_ROTATION_DEG_MAX:g} degrees."
        )
    if abs(height_cm) > distance_cm:
        raise ValueError("Height from the head plane cannot be larger than the distance from the listener.")
    radius_m = distance_cm / 100.0
    z_m = height_cm / 100.0
    horizontal_radius_m = math.sqrt(max(radius_m**2 - z_m**2, 0.0))
    az = math.radians(normalize_azimuth_deg(rotation_deg))
    return {
        "x_m": horizontal_radius_m * math.sin(az),
        "y_m": horizontal_radius_m * math.cos(az),
        "z_m": z_m,
    }


def trajectory_endpoints_xyz(spec: TrajectorySpec) -> tuple[dict[str, float], dict[str, float]]:
    if _uses_cartesian_coordinates(spec) and all(
        value is not None
        for value in (spec.start_x_m, spec.start_y_m, spec.start_z_m, spec.end_x_m, spec.end_y_m, spec.end_z_m)
    ):
        return (
            {"x_m": float(spec.start_x_m), "y_m": float(spec.start_y_m), "z_m": float(spec.start_z_m)},
            {"x_m": float(spec.end_x_m), "y_m": float(spec.end_y_m), "z_m": float(spec.end_z_m)},
        )

    az0, az1 = _default_azimuths_for_direction(spec)
    return (
        spherical_to_cartesian(spec.start_radius_m, az0, spec.elevation_deg),
        spherical_to_cartesian(spec.end_radius_m, az1, spec.elevation_deg),
    )


def validate_design(design: StimulusDesign) -> list[str]:
    warnings: list[str] = []
    if not design.noises and not design.custom_looming_files:
        warnings.append("At least one procedural noise definition or custom looming audio source is required.")
    for noise in design.noises:
        if noise.noise_type.lower() not in SUPPORTED_NOISE_TYPES:
            warnings.append(f"Unsupported noise type for {noise.label}: {noise.noise_type}")
        if not -180.0 <= noise.azimuth_deg <= 180.0:
            warnings.append(f"Azimuth for {noise.label} should be between -180 and 180 degrees.")
        if not -90.0 <= noise.elevation_deg <= 90.0:
            warnings.append(f"Elevation for {noise.label} should be between -90 and 90 degrees.")
        if noise.gain <= 0:
            warnings.append(f"Gain for {noise.label} must be positive.")

    for label, files in [
        ("custom looming", design.custom_looming_files),
        ("prestimulus", design.prestimulus_files),
    ]:
        for asset in files:
            if not asset.label.strip():
                warnings.append(f"A {label} file is missing a label.")
            if not asset.path.strip():
                warnings.append(f"{asset.label or label.title()} is missing a file path.")
            elif not Path(asset.path).expanduser().exists():
                warnings.append(f"{asset.label} file was not found: {asset.path}")
            if asset.target_duration_s <= 0:
                warnings.append(f"{asset.label} target duration must be positive.")
            if asset.render_mode not in SUPPORTED_IMPORTED_AUDIO_RENDER_MODES:
                warnings.append(f"{asset.label} imported audio render mode is unsupported: {asset.render_mode}")
            if asset.gain <= 0:
                warnings.append(f"{asset.label} gain must be positive.")

    t = design.trajectory
    if t.path_direction not in SUPPORTED_DIRECTIONS:
        warnings.append(f"Unsupported path direction: {t.path_direction}")
    if t.coordinate_mode not in SUPPORTED_COORDINATE_MODES:
        warnings.append(f"Unsupported coordinate mode: {t.coordinate_mode}")
    if _uses_cartesian_coordinates(t):
        start = (t.start_x_m, t.start_y_m, t.start_z_m)
        end = (t.end_x_m, t.end_y_m, t.end_z_m)
        if any(value is None for value in (*start, *end)):
            warnings.append("Cartesian trajectories require start and end X/Y/Z coordinates.")
        elif math.dist(start, end) <= 0:
            warnings.append("Start and end coordinates must not be identical.")
    if not _uses_cartesian_coordinates(t) and (t.start_radius_m <= 0 or t.end_radius_m <= 0):
        warnings.append("Start and end radius must be positive.")
    if t.path_length_m <= 0:
        warnings.append("Path length must be positive.")
    if t.propagation_speed_mps <= 0:
        warnings.append("Propagation speed must be positive.")
    radial_delta = abs(t.start_radius_m - t.end_radius_m)
    if not _uses_cartesian_coordinates(t) and t.path_direction in {"approach", "recede"} and abs(t.path_length_m - radial_delta) > 0.05:
        warnings.append("Radial path length differs from the start/end radius difference.")

    p = design.protocol
    if p.repetitions_per_condition < 1:
        warnings.append("Repetitions per condition must be at least 1.")
    if not p.soa_values_ms:
        warnings.append("At least one SOA value is required.")
    if any(soa < 0 for soa in p.soa_values_ms):
        warnings.append("SOA values must be non-negative.")
    if not p.spatial_values_cm:
        warnings.append("At least one spatial value is required.")
    if any(value <= 0 for value in p.spatial_values_cm):
        warnings.append("Spatial values must be positive.")
    if p.pair_spatial_values_with_soas and len(p.soa_values_ms) != len(p.spatial_values_cm):
        warnings.append("Paired SOA/spatial mode expects the same number of SOAs and spatial values.")
    if not p.auditory_motion_directions:
        warnings.append("At least one auditory motion direction is required.")
    if not p.tactile_sites:
        warnings.append("At least one tactile body site is required.")
    if not 0 <= p.catch_trial_percentage < 100:
        warnings.append("Catch-trial percentage must be between 0 and 99.9.")
    if p.catch_trials_exact is not None and p.catch_trials_exact < 0:
        warnings.append("Exact catch-trial count cannot be negative.")
    if any(soa < -10000 for soa in p.baseline_soa_values_ms):
        warnings.append("Baseline SOA values look implausibly early.")
    if not p.respiratory_phases:
        warnings.append("At least one respiratory phase is required.")
    if p.blocks < 1:
        warnings.append("Block count must be at least 1.")
    if p.trial_randomization_strategy not in SUPPORTED_TRIAL_RANDOMIZATION:
        warnings.append(f"Unsupported trial randomization strategy: {p.trial_randomization_strategy}")
    if p.block_order_randomization not in SUPPORTED_BLOCK_ORDER_RANDOMIZATION:
        warnings.append(f"Unsupported block order randomization strategy: {p.block_order_randomization}")
    if p.max_consecutive_same_trial_type < 1:
        warnings.append("Maximum consecutive same trial type must be at least 1.")
    block_specs = effective_block_specs(p)
    if not block_specs:
        warnings.append("At least one block must be defined.")
    for block in block_specs:
        if not block.label.strip():
            warnings.append("A block is missing a label.")
        if not block.stimulus_types:
            warnings.append(f"{block.label or 'Block'} must include at least one stimulus type.")
        for stimulus_type in block.stimulus_types:
            if stimulus_type not in SUPPORTED_TRIAL_TYPES:
                warnings.append(f"Unsupported stimulus type in {block.label}: {stimulus_type}")
    required_types = {"Audio-Tactile"}
    if p.include_baseline_trials:
        required_types.add("Baseline")
    if p.catch_trials_exact is not None and p.catch_trials_exact > 0:
        required_types.add("Catch")
    elif p.catch_trial_percentage > 0:
        required_types.add("Catch")
    available_types = {stimulus_type for block in block_specs for stimulus_type in block.stimulus_types}
    missing_types = sorted(required_types - available_types)
    if missing_types:
        warnings.append(f"No block accepts required stimulus type(s): {', '.join(missing_types)}")
    if p.participants < 1:
        warnings.append("Participant count must be at least 1.")
    return warnings


def effective_block_specs(protocol: ProtocolSpec) -> list[BlockSpec]:
    if protocol.block_specs:
        return [
            BlockSpec(
                label=block.label,
                stimulus_types=[trial_type for trial_type in block.stimulus_types if trial_type],
            )
            for block in protocol.block_specs
        ]
    return [
        BlockSpec(label=f"Block {idx + 1}", stimulus_types=["Audio-Tactile", "Baseline", "Catch"])
        for idx in range(max(1, protocol.blocks))
    ]


def protocol_factor_pairs(protocol: ProtocolSpec) -> list[tuple[int, float]]:
    if protocol.pair_spatial_values_with_soas:
        return list(zip(protocol.soa_values_ms, protocol.spatial_values_cm))
    return [
        (soa, spatial)
        for soa in protocol.soa_values_ms
        for spatial in protocol.spatial_values_cm
    ]


def baseline_factor_pairs(protocol: ProtocolSpec) -> list[tuple[int, float]]:
    if not protocol.baseline_soa_values_ms:
        return protocol_factor_pairs(protocol)
    spatial = protocol.spatial_values_cm[0] if protocol.spatial_values_cm else 0.0
    return [(soa, spatial) for soa in protocol.baseline_soa_values_ms]


def protocol_trial_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    protocol = design.protocol
    factor_pairs = protocol_factor_pairs(protocol)
    repetitions = range(1, protocol.repetitions_per_condition + 1)
    sound_sources = protocol_sound_sources(design)

    for repetition in repetitions:
        for tactile_site in protocol.tactile_sites:
            for motion_direction in protocol.auditory_motion_directions:
                for phase in protocol.respiratory_phases:
                    for soa_ms, spatial_cm in factor_pairs:
                        for source in sound_sources:
                            rows.append(
                                {
                                    "trial_type": "Audio-Tactile",
                                    "repetition": repetition,
                                    "tactile_site": tactile_site,
                                    "motion_direction": motion_direction,
                                    "phase": phase,
                                    "soa_ms": soa_ms,
                                    "spatial_value_cm": spatial_cm,
                                    "noise_label": source["label"],
                                    "noise_type": source["noise_type"],
                                    "azimuth_deg": source["azimuth_deg"],
                                    "elevation_deg": source["elevation_deg"],
                                }
                            )

    if protocol.include_baseline_trials:
        baseline_pairs = baseline_factor_pairs(protocol)
        for repetition in repetitions:
            for tactile_site in protocol.tactile_sites:
                for phase in protocol.respiratory_phases:
                    for soa_ms, spatial_cm in baseline_pairs:
                        rows.append(
                            {
                                "trial_type": "Baseline",
                                "repetition": repetition,
                                "tactile_site": tactile_site,
                                "motion_direction": "",
                                "phase": phase,
                                "soa_ms": soa_ms,
                                "spatial_value_cm": spatial_cm,
                                "noise_label": "",
                                "noise_type": "",
                                "azimuth_deg": "",
                                "elevation_deg": "",
                            }
                        )

    noncatch_count = len(rows)
    if protocol.catch_trials_exact is not None:
        catch_count = protocol.catch_trials_exact
    elif protocol.catch_trial_percentage > 0:
        catch_count = int(math.ceil(noncatch_count * protocol.catch_trial_percentage / (100.0 - protocol.catch_trial_percentage)))
    else:
        catch_count = 0

    noises = sound_sources or [_sound_source_from_noise(NoiseDefinition("Catch", "white"))]
    phases = protocol.respiratory_phases or ["Any"]
    pairs = factor_pairs or [(0, 0.0)]
    tactile_sites = protocol.tactile_sites or ["body"]
    motion_directions = protocol.auditory_motion_directions or ["looming"]
    for i in range(catch_count):
        soa_ms, spatial_cm = pairs[i % len(pairs)]
        noise = noises[i % len(noises)]
        rows.append(
            {
                "trial_type": "Catch",
                "repetition": "",
                "tactile_site": tactile_sites[i % len(tactile_sites)],
                "motion_direction": motion_directions[i % len(motion_directions)],
                "phase": phases[i % len(phases)],
                "soa_ms": soa_ms,
                "spatial_value_cm": spatial_cm,
                "noise_label": noise["label"],
                "noise_type": noise["noise_type"],
                "azimuth_deg": noise["azimuth_deg"],
                "elevation_deg": noise["elevation_deg"],
            }
        )
    return rows


def protocol_sound_sources(design: StimulusDesign) -> list[dict[str, Any]]:
    sources = [_sound_source_from_noise(noise) for noise in design.noises]
    sources.extend(
        {
            "label": asset.label,
            "noise_type": CUSTOM_AUDIO_NOISE_TYPE,
            "azimuth_deg": "",
            "elevation_deg": "",
            "gain": asset.gain,
            "source_path": asset.path,
            "target_duration_s": asset.target_duration_s,
            "source_render_mode": asset.render_mode,
        }
        for asset in design.custom_looming_files
        if asset.label.strip() or asset.path.strip()
    )
    return sources


def _sound_source_from_noise(noise: NoiseDefinition) -> dict[str, Any]:
    return {
        "label": noise.label,
        "noise_type": noise.noise_type,
        "azimuth_deg": noise.azimuth_deg,
        "elevation_deg": noise.elevation_deg,
        "gain": noise.gain,
    }


def _condition_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("trial_type"),
        row.get("tactile_site"),
        row.get("motion_direction"),
        row.get("phase"),
        row.get("soa_ms"),
        row.get("spatial_value_cm"),
        row.get("noise_label"),
    )


def _violates_trial_type_run(candidate: dict[str, Any], ordered: list[dict[str, Any]], max_run: int) -> bool:
    if max_run <= 0 or len(ordered) < max_run:
        return False
    trial_type = candidate.get("trial_type")
    return all(row.get("trial_type") == trial_type for row in ordered[-max_run:])


def _randomize_rows(rows: list[dict[str, Any]], protocol: ProtocolSpec, seed: int) -> list[dict[str, Any]]:
    if protocol.trial_randomization_strategy == "ordered":
        return list(rows)

    rng = random.Random(seed)
    remaining = list(rows)
    rng.shuffle(remaining)
    if protocol.trial_randomization_strategy == "balanced_shuffle":
        return remaining

    ordered: list[dict[str, Any]] = []
    while remaining:
        previous_key = _condition_key(ordered[-1]) if ordered else None
        choice_index = None
        for idx, row in enumerate(remaining):
            if _violates_trial_type_run(row, ordered, protocol.max_consecutive_same_trial_type):
                continue
            if previous_key is not None and _condition_key(row) == previous_key:
                continue
            choice_index = idx
            break
        if choice_index is None:
            for idx, row in enumerate(remaining):
                if not _violates_trial_type_run(row, ordered, protocol.max_consecutive_same_trial_type):
                    choice_index = idx
                    break
        if choice_index is None:
            choice_index = 0
        ordered.append(remaining.pop(choice_index))
    return ordered


def block_trial_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    protocol = design.protocol
    blocks = effective_block_specs(protocol)
    block_rows: dict[str, list[dict[str, Any]]] = {block.label: [] for block in blocks}
    rows_by_type: dict[str, list[dict[str, Any]]] = {trial_type: [] for trial_type in SUPPORTED_TRIAL_TYPES}
    for row in protocol_trial_rows(design):
        rows_by_type.setdefault(str(row["trial_type"]), []).append(row)

    for trial_type, rows in rows_by_type.items():
        if not rows:
            continue
        eligible_blocks = [block for block in blocks if trial_type in block.stimulus_types]
        if not eligible_blocks:
            continue
        shuffled = list(rows)
        random.Random(protocol.random_seed + sum(ord(ch) for ch in trial_type)).shuffle(shuffled)
        for idx, row in enumerate(shuffled):
            min_count = min(len(block_rows[block.label]) for block in eligible_blocks)
            candidates = [
                block
                for block in eligible_blocks
                if len(block_rows[block.label]) == min_count
            ]
            block = candidates[idx % len(candidates)]
            block_rows[block.label].append(dict(row))

    scheduled: list[dict[str, Any]] = []
    for block_index, block in enumerate(blocks, start=1):
        randomized = _randomize_rows(
            block_rows[block.label],
            protocol,
            seed=protocol.random_seed + block_index * 1009,
        )
        for trial_index, row in enumerate(randomized, start=1):
            scheduled.append(
                {
                    "block_index": block_index,
                    "block_label": block.label,
                    "block_trial_index": trial_index,
                    **row,
                }
            )
    return scheduled


def participant_block_orders(design: StimulusDesign) -> dict[str, list[str]]:
    protocol = design.protocol
    labels = [block.label for block in effective_block_specs(protocol)]
    if not labels:
        return {}

    base_order = list(labels)
    if protocol.block_order_randomization != "fixed":
        random.Random(protocol.random_seed).shuffle(base_order)

    orders: dict[str, list[str]] = {}
    block_count = len(base_order)
    for participant_index in range(1, protocol.participants + 1):
        if protocol.block_order_randomization == "fixed":
            order = list(labels)
        elif protocol.block_order_randomization == "seeded_random_permutation":
            order = list(labels)
            random.Random(protocol.random_seed + participant_index * 7919).shuffle(order)
        else:
            shift = (participant_index - 1) % block_count
            order = base_order[shift:] + base_order[:shift]
            if ((participant_index - 1) // block_count) % 2 == 1:
                order = list(reversed(order))
        orders[f"P{participant_index:03d}"] = order
    return orders


def experiment_schedule_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    block_rows = block_trial_rows(design)
    rows_by_block: dict[str, list[dict[str, Any]]] = {}
    for row in block_rows:
        rows_by_block.setdefault(str(row["block_label"]), []).append(row)

    scheduled: list[dict[str, Any]] = []
    for participant_id, order in participant_block_orders(design).items():
        participant_index = int(participant_id[1:])
        for block_position, block_label in enumerate(order, start=1):
            for row in rows_by_block.get(block_label, []):
                scheduled.append(
                    {
                        "participant_id": participant_id,
                        "participant_index": participant_index,
                        "participant_block_position": block_position,
                        **row,
                    }
                )
    return scheduled


def protocol_summary(design: StimulusDesign) -> dict[str, int]:
    rows = block_trial_rows(design)
    audio_tactile = sum(1 for row in rows if row["trial_type"] == "Audio-Tactile")
    baseline = sum(1 for row in rows if row["trial_type"] == "Baseline")
    catch = sum(1 for row in rows if row["trial_type"] == "Catch")
    total = len(rows)
    blocks = max(1, len(effective_block_specs(design.protocol)))
    block_counts: dict[str, int] = {}
    for row in rows:
        block_counts[str(row["block_label"])] = block_counts.get(str(row["block_label"]), 0) + 1
    return {
        "audio_tactile_trials": audio_tactile,
        "baseline_trials": baseline,
        "catch_trials": catch,
        "total_trials": total,
        "blocks": blocks,
        "trials_per_block": max(block_counts.values(), default=int(math.ceil(total / blocks))),
        "min_trials_per_block": min(block_counts.values(), default=0),
        "max_trials_per_block": max(block_counts.values(), default=0),
        "participants": design.protocol.participants,
        "total_participant_trials": total * design.protocol.participants,
    }


def export_protocol_csv(design: StimulusDesign, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = experiment_schedule_rows(design)
    fieldnames = [
        "participant_id",
        "participant_index",
        "participant_block_position",
        "block_index",
        "block_label",
        "block_trial_index",
        "trial_type",
        "repetition",
        "tactile_site",
        "motion_direction",
        "phase",
        "soa_ms",
        "spatial_value_cm",
        "noise_label",
        "noise_type",
        "azimuth_deg",
        "elevation_deg",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _default_azimuths_for_direction(spec: TrajectorySpec) -> tuple[float, float]:
    if spec.path_direction == "left_to_right" and spec.azimuth_start_deg == spec.azimuth_end_deg:
        return -45.0, 45.0
    if spec.path_direction == "right_to_left" and spec.azimuth_start_deg == spec.azimuth_end_deg:
        return 45.0, -45.0
    return spec.azimuth_start_deg, spec.azimuth_end_deg


def _trajectory_xyz_at_fraction(spec: TrajectorySpec, u: float) -> dict[str, float]:
    u = max(0.0, min(1.0, u))
    if _uses_cartesian_coordinates(spec):
        start, end = trajectory_endpoints_xyz(spec)
        return {
            "x_m": start["x_m"] + (end["x_m"] - start["x_m"]) * u,
            "y_m": start["y_m"] + (end["y_m"] - start["y_m"]) * u,
            "z_m": start["z_m"] + (end["z_m"] - start["z_m"]) * u,
        }

    az0, az1 = _default_azimuths_for_direction(spec)
    radius_m = spec.start_radius_m + (spec.end_radius_m - spec.start_radius_m) * u
    azimuth_deg = az0 + (az1 - az0) * u
    return spherical_to_cartesian(radius_m, azimuth_deg, spec.elevation_deg)


def trajectory_point_at_time(spec: TrajectorySpec, time_s: float) -> dict[str, float]:
    movement_duration = max(spec.movement_duration_s, 0.0)
    start_hold_s = max(spec.padding_pre_s, 0.0)
    end_hold_s = max(spec.padding_post_s, 0.0)
    total_duration = start_hold_s + movement_duration + end_hold_s
    clamped_time = max(0.0, min(time_s, total_duration))
    if clamped_time < start_hold_s or movement_duration <= 0:
        phase = "start_hold"
        u = 0.0
    elif clamped_time <= start_hold_s + movement_duration:
        phase = "movement"
        u = (clamped_time - start_hold_s) / movement_duration
    else:
        phase = "end_hold"
        u = 1.0

    xyz = _trajectory_xyz_at_fraction(spec, u)
    spherical = cartesian_to_spherical(xyz["x_m"], xyz["y_m"], xyz["z_m"])
    return {
        "time_s": clamped_time,
        "phase": phase,
        "u": u,
        "radius_m": spherical["radius_m"],
        "azimuth_deg": spherical["azimuth_deg"],
        "elevation_deg": spherical["elevation_deg"],
        "x_m": xyz["x_m"],
        "y_m": xyz["y_m"],
        "z_m": xyz["z_m"],
    }


def trajectory_points_with_holds(spec: TrajectorySpec, samples_per_second: float = 100.0) -> list[dict[str, float]]:
    if samples_per_second <= 0:
        raise ValueError("samples_per_second must be positive.")
    total_duration = max(spec.total_duration_s, 0.0)
    sample_count = max(2, int(round(total_duration * samples_per_second)) + 1)
    if sample_count == 2:
        return [trajectory_point_at_time(spec, 0.0), trajectory_point_at_time(spec, total_duration)]
    return [
        trajectory_point_at_time(spec, total_duration * i / (sample_count - 1))
        for i in range(sample_count)
    ]


def trajectory_points(spec: TrajectorySpec, samples: int = 121) -> list[dict[str, float]]:
    samples = max(2, samples)
    duration = max(spec.movement_duration_s, 0.0)
    if _uses_cartesian_coordinates(spec):
        rows: list[dict[str, float]] = []
        for i in range(samples):
            u = i / (samples - 1)
            time_s = duration * u
            xyz = _trajectory_xyz_at_fraction(spec, u)
            x_m = xyz["x_m"]
            y_m = xyz["y_m"]
            z_m = xyz["z_m"]
            spherical = cartesian_to_spherical(x_m, y_m, z_m)
            rows.append(
                {
                    "time_s": time_s,
                    "radius_m": spherical["radius_m"],
                    "azimuth_deg": spherical["azimuth_deg"],
                    "elevation_deg": spherical["elevation_deg"],
                    "x_m": x_m,
                    "y_m": y_m,
                    "z_m": z_m,
                }
            )
        return rows

    rows: list[dict[str, float]] = []
    for i in range(samples):
        u = i / (samples - 1)
        time_s = duration * u
        xyz = _trajectory_xyz_at_fraction(spec, u)
        spherical = cartesian_to_spherical(xyz["x_m"], xyz["y_m"], xyz["z_m"])
        rows.append(
            {
                "time_s": time_s,
                "radius_m": spherical["radius_m"],
                "azimuth_deg": spherical["azimuth_deg"],
                "elevation_deg": spherical["elevation_deg"],
                "x_m": xyz["x_m"],
                "y_m": xyz["y_m"],
                "z_m": xyz["z_m"],
            }
        )
    return rows


def export_trajectory_csv(design: StimulusDesign, path: Path, samples: int = 121) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = trajectory_points(design.trajectory, samples=samples)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sofa_summary(path: Path) -> dict[str, Any]:
    try:
        import sofar
    except ImportError as exc:
        raise RuntimeError("Install the sofar package to inspect SOFA files.") from exc

    hrtf = sofar.read_sofa(str(path))
    positions = np.asarray(hrtf.Source.Position.get_values(), dtype=float)
    if positions.ndim != 2 or positions.shape[1] < 2:
        raise RuntimeError("SOFA source positions must have at least azimuth and elevation columns.")

    sample_rate = None
    try:
        sample_rate = float(np.asarray(hrtf.Data.SamplingRate.get_values()).reshape(-1)[0])
    except Exception:
        sample_rate = None

    distances = positions[:, 2] if positions.shape[1] >= 3 else np.full(len(positions), np.nan)
    return {
        "conventions": getattr(hrtf, "GLOBAL_SOFAConventions", ""),
        "version": getattr(hrtf, "GLOBAL_SOFAConventionsVersion", ""),
        "positions": int(len(positions)),
        "azimuth_min": float(np.nanmin(positions[:, 0])),
        "azimuth_max": float(np.nanmax(positions[:, 0])),
        "elevation_min": float(np.nanmin(positions[:, 1])),
        "elevation_max": float(np.nanmax(positions[:, 1])),
        "distance_min": float(np.nanmin(distances)) if not np.all(np.isnan(distances)) else None,
        "distance_max": float(np.nanmax(distances)) if not np.all(np.isnan(distances)) else None,
        "sample_rate": sample_rate,
    }


def nearest_sofa_position(path: Path, azimuth_deg: float, elevation_deg: float = 0.0) -> dict[str, float]:
    try:
        import sofar
    except ImportError as exc:
        raise RuntimeError("Install the sofar package to inspect SOFA files.") from exc

    hrtf = sofar.read_sofa(str(path))
    positions = np.asarray(hrtf.Source.Position.get_values(), dtype=float)
    if positions.ndim != 2 or positions.shape[1] < 2:
        raise RuntimeError("SOFA source positions must have at least azimuth and elevation columns.")

    azimuth_delta = ((positions[:, 0] - azimuth_deg + 180.0) % 360.0) - 180.0
    elevation_delta = positions[:, 1] - elevation_deg
    score = np.sqrt(azimuth_delta**2 + elevation_delta**2)
    idx = int(np.argmin(score))
    row = positions[idx]
    return {
        "index": float(idx),
        "azimuth_deg": float(row[0]),
        "elevation_deg": float(row[1]),
        "distance_m": float(row[2]) if row.shape[0] >= 3 else float("nan"),
        "angular_error_deg": float(score[idx]),
    }


def snap_noises_to_sofa(design: StimulusDesign) -> StimulusDesign:
    if not design.sofa_file:
        raise RuntimeError("No SOFA file selected.")
    sofa_path = Path(design.sofa_file)
    snapped = design_from_dict(design_to_dict(design))
    for noise in snapped.noises:
        nearest = nearest_sofa_position(sofa_path, noise.azimuth_deg, noise.elevation_deg)
        noise.azimuth_deg = nearest["azimuth_deg"]
        noise.elevation_deg = nearest["elevation_deg"]
    return snapped
