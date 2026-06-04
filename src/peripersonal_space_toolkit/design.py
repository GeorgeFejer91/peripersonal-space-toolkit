"""Stimulus-design data model and SOFA/trajectory helpers."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


SUPPORTED_NOISE_TYPES = ("pink", "blue", "white", "brown")
SUPPORTED_DIRECTIONS = ("approach", "recede", "left_to_right", "right_to_left", "custom")


@dataclass
class NoiseDefinition:
    label: str
    noise_type: str
    azimuth_deg: float = 0.0
    elevation_deg: float = 0.0
    gain: float = 1.0


@dataclass
class TrajectorySpec:
    start_radius_m: float = 1.1
    end_radius_m: float = 0.1
    path_direction: str = "approach"
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
    participants: int = 50
    random_seed: int = 20250604


@dataclass
class StimulusDesign:
    name: str = "Study 5 PPS design"
    sofa_file: str = ""
    noises: list[NoiseDefinition] = field(default_factory=list)
    trajectory: TrajectorySpec = field(default_factory=TrajectorySpec)
    protocol: ProtocolSpec = field(default_factory=ProtocolSpec)


def default_design() -> StimulusDesign:
    return StimulusDesign(
        noises=[
            NoiseDefinition("Pink frontal", "pink", 0.0),
            NoiseDefinition("Blue frontal", "blue", 0.0),
            NoiseDefinition("White frontal", "white", 0.0),
            NoiseDefinition("Brown frontal", "brown", 0.0),
        ]
    )


def design_to_dict(design: StimulusDesign) -> dict[str, Any]:
    return asdict(design)


def design_from_dict(data: dict[str, Any]) -> StimulusDesign:
    noises = [NoiseDefinition(**item) for item in data.get("noises", [])]
    trajectory = TrajectorySpec(**data.get("trajectory", {}))
    protocol = ProtocolSpec(**data.get("protocol", {}))
    return StimulusDesign(
        name=data.get("name", "Study 5 PPS design"),
        sofa_file=data.get("sofa_file", ""),
        noises=noises,
        trajectory=trajectory,
        protocol=protocol,
    )


def load_design(path: Path) -> StimulusDesign:
    return design_from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_design(design: StimulusDesign, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(design_to_dict(design), indent=2), encoding="utf-8")


def validate_design(design: StimulusDesign) -> list[str]:
    warnings: list[str] = []
    if not design.noises:
        warnings.append("At least one noise definition is required.")
    for noise in design.noises:
        if noise.noise_type.lower() not in SUPPORTED_NOISE_TYPES:
            warnings.append(f"Unsupported noise type for {noise.label}: {noise.noise_type}")
        if not -180.0 <= noise.azimuth_deg <= 180.0:
            warnings.append(f"Azimuth for {noise.label} should be between -180 and 180 degrees.")
        if not -90.0 <= noise.elevation_deg <= 90.0:
            warnings.append(f"Elevation for {noise.label} should be between -90 and 90 degrees.")
        if noise.gain <= 0:
            warnings.append(f"Gain for {noise.label} must be positive.")

    t = design.trajectory
    if t.path_direction not in SUPPORTED_DIRECTIONS:
        warnings.append(f"Unsupported path direction: {t.path_direction}")
    if t.start_radius_m <= 0 or t.end_radius_m <= 0:
        warnings.append("Start and end radius must be positive.")
    if t.path_length_m <= 0:
        warnings.append("Path length must be positive.")
    if t.propagation_speed_mps <= 0:
        warnings.append("Propagation speed must be positive.")
    radial_delta = abs(t.start_radius_m - t.end_radius_m)
    if t.path_direction in {"approach", "recede"} and abs(t.path_length_m - radial_delta) > 0.05:
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
    if p.participants < 1:
        warnings.append("Participant count must be at least 1.")
    return warnings


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

    for repetition in repetitions:
        for tactile_site in protocol.tactile_sites:
            for motion_direction in protocol.auditory_motion_directions:
                for phase in protocol.respiratory_phases:
                    for soa_ms, spatial_cm in factor_pairs:
                        for noise in design.noises:
                            rows.append(
                                {
                                    "trial_type": "Audio-Tactile",
                                    "repetition": repetition,
                                    "tactile_site": tactile_site,
                                    "motion_direction": motion_direction,
                                    "phase": phase,
                                    "soa_ms": soa_ms,
                                    "spatial_value_cm": spatial_cm,
                                    "noise_label": noise.label,
                                    "noise_type": noise.noise_type,
                                    "azimuth_deg": noise.azimuth_deg,
                                    "elevation_deg": noise.elevation_deg,
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

    noises = design.noises or [NoiseDefinition("Catch", "white")]
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
                "noise_label": noise.label,
                "noise_type": noise.noise_type,
                "azimuth_deg": noise.azimuth_deg,
                "elevation_deg": noise.elevation_deg,
            }
        )
    return rows


def protocol_summary(design: StimulusDesign) -> dict[str, int]:
    rows = protocol_trial_rows(design)
    audio_tactile = sum(1 for row in rows if row["trial_type"] == "Audio-Tactile")
    baseline = sum(1 for row in rows if row["trial_type"] == "Baseline")
    catch = sum(1 for row in rows if row["trial_type"] == "Catch")
    total = len(rows)
    blocks = max(1, design.protocol.blocks)
    return {
        "audio_tactile_trials": audio_tactile,
        "baseline_trials": baseline,
        "catch_trials": catch,
        "total_trials": total,
        "trials_per_block": int(math.ceil(total / blocks)),
        "participants": design.protocol.participants,
        "total_participant_trials": total * design.protocol.participants,
    }


def export_protocol_csv(design: StimulusDesign, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = protocol_trial_rows(design)
    fieldnames = [
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


def trajectory_points(spec: TrajectorySpec, samples: int = 121) -> list[dict[str, float]]:
    samples = max(2, samples)
    duration = max(spec.movement_duration_s, 0.0)
    az0, az1 = _default_azimuths_for_direction(spec)
    rows: list[dict[str, float]] = []
    for i in range(samples):
        u = i / (samples - 1)
        time_s = duration * u
        radius_m = spec.start_radius_m + (spec.end_radius_m - spec.start_radius_m) * u
        azimuth_deg = az0 + (az1 - az0) * u
        elevation_deg = spec.elevation_deg
        az = math.radians(azimuth_deg)
        el = math.radians(elevation_deg)
        horizontal_radius = radius_m * math.cos(el)
        rows.append(
            {
                "time_s": time_s,
                "radius_m": radius_m,
                "azimuth_deg": azimuth_deg,
                "elevation_deg": elevation_deg,
                "x_m": horizontal_radius * math.sin(az),
                "y_m": horizontal_radius * math.cos(az),
                "z_m": radius_m * math.sin(el),
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
