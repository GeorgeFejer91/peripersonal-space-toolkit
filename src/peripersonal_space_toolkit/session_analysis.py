"""Immediate session analysis for PPS runner event logs."""

from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.optimize import curve_fit


@dataclass
class SessionAnalysisResult:
    response_rows: list[dict[str, Any]] = field(default_factory=list)
    summary_rows: list[dict[str, Any]] = field(default_factory=list)
    curve_rows: list[dict[str, Any]] = field(default_factory=list)
    fit_rows: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def analyze_session_events(events: Iterable[Any], *, min_rt_s: float = 0.1, max_rt_s: float = 3.0) -> SessionAnalysisResult:
    rows = sorted((_as_row(event) for event in events), key=lambda row: (_as_float(row.get("unix_time"), 0.0), row.get("event_id", 0)))
    result = SessionAnalysisResult()
    result.response_rows = _pair_tactile_responses(rows, min_rt_s=min_rt_s, max_rt_s=max_rt_s)
    result.summary_rows = _summarize_responses(result.response_rows)
    result.curve_rows, result.fit_rows, curve_warnings = _build_pps_curves(result.response_rows)
    result.warnings.extend(curve_warnings)
    if not result.response_rows:
        result.warnings.append("No tactile response rows could be reconstructed from the event stream.")
    return result


def write_analysis_csvs(result: SessionAnalysisResult, output_dir: str | Path, stem: str) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "responses": output_dir / f"{stem}_responses.csv",
        "summary": output_dir / f"{stem}_summary.csv",
        "curves": output_dir / f"{stem}_pps_curve_points.csv",
        "fits": output_dir / f"{stem}_sigmoid_fits.csv",
    }
    _write_rows(outputs["responses"], result.response_rows)
    _write_rows(outputs["summary"], result.summary_rows)
    _write_rows(outputs["curves"], result.curve_rows)
    _write_rows(outputs["fits"], result.fit_rows)
    return outputs


def format_analysis_summary(result: SessionAnalysisResult) -> str:
    total = len(result.response_rows)
    hits = sum(1 for row in result.response_rows if row.get("hit"))
    clicks = [float(row["rt_ms"]) for row in result.response_rows if row.get("rt_ms") not in (None, "")]
    lines = [
        f"Tactile trials reconstructed: {total}",
        f"Detected responses: {hits} ({(hits / total * 100.0):.1f}% hit rate)" if total else "Detected responses: 0",
    ]
    if clicks:
        lines.append(f"Mean RT: {statistics.mean(clicks):.1f} ms")
    if result.fit_rows:
        lines.append("")
        lines.append("Sigmoid PPS fits")
        for fit in result.fit_rows[:8]:
            boundary = _fmt(fit.get("pps_boundary_soa_ms"), 1)
            slope = _fmt(fit.get("slope"), 5)
            r2 = _fmt(fit.get("r2"), 3)
            lines.append(f"- {fit.get('scope', '')}: boundary {boundary} ms, slope {slope}, R2 {r2}")
    else:
        lines.append("No sigmoid fit yet; at least four usable SOA points are needed per condition.")
    if result.warnings:
        lines.append("")
        lines.append("Warnings")
        lines.extend(f"- {warning}" for warning in result.warnings[:8])
    return "\n".join(lines)


def _pair_tactile_responses(events: list[dict[str, Any]], *, min_rt_s: float, max_rt_s: float) -> list[dict[str, Any]]:
    tactile_events = [row for row in events if row.get("event_type") == "tactile_onset"]
    trial_starts = sorted(_as_float(row.get("unix_time"), 0.0) for row in events if row.get("event_type") == "trial_start")
    clicks = [row for row in events if row.get("event_type") == "mouse_click" and _truthy(row.get("in_target", True))]
    clicks = [row for row in clicks if _truthy(row.get("during_playback", True))]
    clicks = sorted(clicks, key=lambda row: (_as_float(row.get("unix_time"), 0.0), row.get("event_id", 0)))

    used_click_ids: set[Any] = set()
    response_rows = []
    for tactile in tactile_events:
        onset = _as_float(tactile.get("unix_time"), 0.0)
        limit = onset + max_rt_s
        for trial_start in trial_starts:
            if trial_start > onset + 0.01:
                limit = min(limit, trial_start)
                break
        click = None
        for candidate in clicks:
            click_time = _as_float(candidate.get("unix_time"), 0.0)
            if candidate.get("event_id") in used_click_ids:
                continue
            if onset + min_rt_s <= click_time <= limit:
                click = candidate
                used_click_ids.add(candidate.get("event_id"))
                break
        row = _response_base(tactile)
        row["tactile_unix_time"] = onset
        row["hit"] = click is not None
        if click is not None:
            click_time = _as_float(click.get("unix_time"), 0.0)
            row["click_unix_time"] = click_time
            row["rt_ms"] = (click_time - onset) * 1000.0
            row["click_x"] = click.get("x", "")
            row["click_y"] = click.get("y", "")
            row["click_event_id"] = click.get("event_id", "")
        else:
            row["click_unix_time"] = ""
            row["rt_ms"] = ""
            row["click_x"] = ""
            row["click_y"] = ""
            row["click_event_id"] = ""
        response_rows.append(row)
    return response_rows


def _response_base(event: dict[str, Any]) -> dict[str, Any]:
    part_number = _as_int(_field(event, "part_number", "Part_Number"), None)
    condition = _field(event, "condition") or (f"Part {part_number}" if part_number else "")
    return {
        "participant_id": _field(event, "participant_id", "Participant_ID"),
        "condition": condition,
        "part_number": part_number if part_number is not None else "",
        "block_number": _as_int(_field(event, "block_number", "Block_Number"), ""),
        "trial_number": _as_int(_field(event, "trial_number", "Trial_Number"), ""),
        "trial_type": _field(event, "trial_type", "Trial_Type"),
        "soa_ms": _as_int(_field(event, "soa_ms", "SOA_ms"), ""),
        "noise_type": _field(event, "noise_type", "Noise_Type"),
        "respiratory_phase": _field(event, "respiratory_phase", "Respiratory_Phase"),
        "stimulus_modality": _field(event, "stimulus_modality"),
    }


def _summarize_responses(response_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in response_rows:
        key = (
            row.get("participant_id", ""),
            row.get("condition", ""),
            row.get("trial_type", ""),
            row.get("respiratory_phase", ""),
            row.get("noise_type", ""),
            row.get("soa_ms", ""),
        )
        groups.setdefault(key, []).append(row)

    summary = []
    for key, rows in sorted(groups.items(), key=lambda item: tuple(str(part) for part in item[0])):
        rts = [_as_float(row.get("rt_ms"), math.nan) for row in rows if row.get("rt_ms") not in (None, "")]
        rts = [rt for rt in rts if math.isfinite(rt)]
        hits = sum(1 for row in rows if row.get("hit"))
        summary.append(
            {
                "participant_id": key[0],
                "condition": key[1],
                "trial_type": key[2],
                "respiratory_phase": key[3],
                "noise_type": key[4],
                "soa_ms": key[5],
                "n": len(rows),
                "hits": hits,
                "hit_rate": hits / len(rows) if rows else "",
                "mean_rt_ms": statistics.mean(rts) if rts else "",
                "sd_rt_ms": statistics.stdev(rts) if len(rts) > 1 else "",
            }
        )
    return summary


def _build_pps_curves(response_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    baseline = _baseline_means(response_rows)
    audio_rows = [row for row in response_rows if row.get("trial_type") == "Audio-Tactile" and row.get("rt_ms") not in (None, "")]
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in audio_rows:
        key = (row.get("condition", ""), row.get("respiratory_phase", ""), row.get("noise_type", ""))
        groups.setdefault(key, []).append(row)

    curve_rows: list[dict[str, Any]] = []
    fit_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for key, rows in sorted(groups.items(), key=lambda item: tuple(str(part) for part in item[0])):
        condition, phase, noise = key
        by_soa: dict[int, list[float]] = {}
        for row in rows:
            soa = _as_int(row.get("soa_ms"), None)
            rt = _as_float(row.get("rt_ms"), math.nan)
            if soa is None or not math.isfinite(rt):
                continue
            by_soa.setdefault(soa, []).append(rt)
        xs = []
        ys = []
        metric = "facilitation_ms"
        for soa, values in sorted(by_soa.items()):
            mean_rt = statistics.mean(values)
            base_rt = _lookup_baseline(baseline, condition, phase, soa)
            facilitation = base_rt - mean_rt if base_rt is not None else None
            y = facilitation if facilitation is not None else mean_rt
            if facilitation is None:
                metric = "mean_rt_ms"
            curve_rows.append(
                {
                    "scope": _scope(condition, phase, noise),
                    "condition": condition,
                    "respiratory_phase": phase,
                    "noise_type": noise,
                    "soa_ms": soa,
                    "n": len(values),
                    "mean_rt_ms": mean_rt,
                    "baseline_mean_rt_ms": "" if base_rt is None else base_rt,
                    "facilitation_ms": "" if facilitation is None else facilitation,
                    "fit_metric": metric,
                }
            )
            xs.append(float(soa))
            ys.append(float(y))
        if len(xs) >= 4:
            fit = _fit_sigmoid(np.asarray(xs), np.asarray(ys))
            if fit:
                fit_rows.append({"scope": _scope(condition, phase, noise), "condition": condition, "respiratory_phase": phase, "noise_type": noise, "fit_metric": metric, **fit})
            else:
                warnings.append(f"Sigmoid fit did not converge for {_scope(condition, phase, noise)}.")
        elif xs:
            warnings.append(f"Only {len(xs)} SOA point(s) for {_scope(condition, phase, noise)}; sigmoid fit skipped.")
    return curve_rows, fit_rows, warnings


def _baseline_means(response_rows: list[dict[str, Any]]) -> dict[tuple[Any, ...], float]:
    groups: dict[tuple[Any, ...], list[float]] = {}
    for row in response_rows:
        if row.get("trial_type") != "Baseline" or row.get("rt_ms") in (None, ""):
            continue
        rt = _as_float(row.get("rt_ms"), math.nan)
        soa = _as_int(row.get("soa_ms"), None)
        if soa is None or not math.isfinite(rt):
            continue
        condition = row.get("condition", "")
        phase = row.get("respiratory_phase", "")
        groups.setdefault((condition, phase, soa), []).append(rt)
        groups.setdefault(("", phase, soa), []).append(rt)
        groups.setdefault(("", "", soa), []).append(rt)
    return {key: statistics.mean(values) for key, values in groups.items() if values}


def _lookup_baseline(baseline: dict[tuple[Any, ...], float], condition: Any, phase: Any, soa: int) -> float | None:
    for key in ((condition, phase, soa), ("", phase, soa), ("", "", soa)):
        if key in baseline:
            return baseline[key]
    return None


def _fit_sigmoid(x: np.ndarray, y: np.ndarray) -> dict[str, float] | None:
    if len(x) < 4 or len(set(x.tolist())) < 4:
        return None
    lower0 = float(np.min(y))
    upper0 = float(np.max(y))
    x00 = float(np.median(x))
    direction = 1.0 if y[-1] >= y[0] else -1.0
    p0 = [lower0, upper0, x00, direction * 0.004]
    bounds = ([-np.inf, -np.inf, float(np.min(x)), -1.0], [np.inf, np.inf, float(np.max(x)), 1.0])
    try:
        params, _ = curve_fit(_sigmoid, x, y, p0=p0, bounds=bounds, maxfev=20000)
    except Exception:
        return None
    predicted = _sigmoid(x, *params)
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot else 1.0
    return {
        "lower": float(params[0]),
        "upper": float(params[1]),
        "pps_boundary_soa_ms": float(params[2]),
        "slope": float(params[3]),
        "r2": r2,
    }


def _sigmoid(x: np.ndarray, lower: float, upper: float, x0: float, slope: float) -> np.ndarray:
    return lower + (upper - lower) / (1.0 + np.exp(-slope * (x - x0)))


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _scope(condition: Any, phase: Any, noise: Any) -> str:
    parts = [str(part) for part in (condition, phase, noise) if str(part).strip()]
    return " / ".join(parts) or "All audio-tactile"


def _as_row(event: Any) -> dict[str, Any]:
    if hasattr(event, "as_flat_dict"):
        return dict(event.as_flat_dict())
    if isinstance(event, dict):
        row = dict(event)
        payload = row.pop("payload", None)
        if isinstance(payload, dict):
            row.update(payload)
        return row
    raise TypeError(f"Unsupported event type: {type(event)!r}")


def _field(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none"}


def _as_float(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _as_int(value: Any, default: Any) -> Any:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _fmt(value: Any, digits: int) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"
