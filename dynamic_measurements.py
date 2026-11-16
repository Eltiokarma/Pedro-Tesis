"""Compare a dynamic tank trajectory with explicitly labelled SI observations.

This module neither fits model parameters nor certifies plant validity. CSV
observations are user supplied and their authenticity is not inferred from a
filename or label. ``time_s`` is elapsed experiment time, not a wall-clock date.
Alignment is explicit: simulation_time_s = time_s + time_offset_s.

CSV columns must be ``time_s`` and one or more keys from ``VARIABLE_UNITS``.
Blank observation cells mean unavailable readings, never zero. Optional
``<variable>_uncertainty`` columns contain a strictly positive, one-standard-
deviation uncertainty in that variable's unit. No unit conversion is inferred.
Continuous states are interpolated linearly only inside the returned simulation
interval. Valve position and utility flow retain their previous sample between
recorded actions and take the new value exactly at the action time. The motor
must therefore include every action time in its series. A stopped run is compared
only over its available, explicitly partial trajectory.
"""

from __future__ import annotations

import bisect
import csv
import hashlib
import io
import math
from collections.abc import Mapping
from pathlib import Path


VARIABLE_UNITS = {
    "tank_temperature_K": "K",
    "jacket_temperature_K": "K",
    "wall_temperature_K": "K",
    "mass_kg": "kg",
    "volume_m3": "m3",
    "tracer_mass_fraction": "kg/kg",
    "valve_opening": "fraction",
    "utility_flow_kg_s": "kg/s",
}

HELD_VARIABLES = frozenset({"valve_opening", "utility_flow_kg_s"})

MAX_CSV_BYTES = 20 * 1024 * 1024
MAX_OBSERVATIONS = 100_000


def _finite_number(value, description: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{description}: expected a finite number, not bool")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{description}: expected a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{description}: expected a finite number")
    return number


def write_measurement_template(path) -> None:
    """Write only SI column names; do not fabricate measurement rows."""
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerow(["time_s", *VARIABLE_UNITS])


def _read_csv(path):
    # Read once so the provenance hash describes the exact bytes parsed.
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise ValueError(f"CSV exceeds the {MAX_CSV_BYTES}-byte limit")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must use UTF-8 encoding") from exc
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader, None)
        if not header:
            raise ValueError("CSV must contain a header")
        if len(header) != len(set(header)):
            raise ValueError("CSV contains duplicate column names")
        allowed = {"time_s", *VARIABLE_UNITS}
        allowed.update(f"{name}_uncertainty" for name in VARIABLE_UNITS)
        unknown = set(header) - allowed
        if unknown:
            raise ValueError("Unknown CSV columns; use explicit SI names: "
                             + ", ".join(sorted(unknown)))
        if "time_s" not in header:
            raise ValueError("CSV requires time_s in elapsed seconds")
        variables = [name for name in VARIABLE_UNITS if name in header]
        if not variables:
            raise ValueError("CSV requires at least one observation variable")
        uncertainty_variables = [name for name in VARIABLE_UNITS
                                 if f"{name}_uncertainty" in header]
        if any(name not in variables for name in uncertainty_variables):
            raise ValueError("Uncertainty column requires its observation column")
        observations = []
        previous = None
        for record in reader:
            if not record or all(not cell.strip() for cell in record):
                continue
            if len(record) != len(header):
                raise ValueError(f"CSV line {reader.line_num}: wrong column count")
            if len(observations) >= MAX_OBSERVATIONS:
                raise ValueError(f"CSV exceeds {MAX_OBSERVATIONS} observations")
            row = dict(zip(header, record))
            time = _finite_number(row["time_s"], f"line {reader.line_num} time_s")
            if time < 0:
                raise ValueError("CSV time_s must be nonnegative elapsed seconds")
            if previous is not None and time <= previous:
                raise ValueError("CSV time_s must be strictly increasing and unique")
            previous = time
            values, uncertainties = {}, {}
            for name in variables:
                cell = row[name].strip()
                values[name] = (_finite_number(cell, f"line {reader.line_num} {name}")
                                if cell else None)
                uncertainty = row.get(f"{name}_uncertainty", "").strip()
                if uncertainty:
                    number = _finite_number(uncertainty,
                                            f"line {reader.line_num} {name}_uncertainty")
                    if number <= 0:
                        raise ValueError("Measurement uncertainties must be positive")
                    if values[name] is None:
                        raise ValueError("Uncertainty cannot accompany a blank observation")
                    uncertainties[name] = number
            observations.append({"time_s": time, "values": values,
                                 "uncertainties": uncertainties})
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV: {exc}") from exc
    if not observations:
        raise ValueError("CSV contains no observation rows")
    if not any(value is not None for row in observations for value in row["values"].values()):
        raise ValueError("CSV contains no numeric observations")
    return observations, variables, raw


def _trajectory(result, variables):
    if not isinstance(result, Mapping):
        raise ValueError("Simulation result must be a mapping")
    rows = result.get("series")
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("Simulation result requires a nonempty series")
    times, values = [], {name: [] for name in variables}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"Simulation series row {index} must be a mapping")
        time = _finite_number(row.get("time_s"), f"series[{index}].time_s")
        if time < 0 or (times and time <= times[-1]):
            raise ValueError("Simulation times must be nonnegative and strictly increasing")
        times.append(time)
        for name in variables:
            values[name].append(_finite_number(row.get(name), f"series[{index}].{name}"))
    return times, values


def _interpolate(time, times, values, *, hold_previous=False):
    # Caller checks support before interpolation. Endpoints are exact, including
    # the valid one-point trajectory of a run stopped at its initial condition.
    right = bisect.bisect_left(times, time)
    if right < len(times) and times[right] == time:
        return values[right]
    left = right - 1
    if hold_previous:
        return values[left]
    weight = (time - times[left]) / (times[right] - times[left])
    value = (1.0 - weight) * values[left] + weight * values[right]
    return _finite_number(value, "Interpolated simulation value")


def _metrics(errors):
    if not errors:
        return {"n": 0, "rmse": None, "mae": None, "bias": None,
                "max_abs_error": None}
    n = len(errors)
    # Scale before summation to avoid overflowing intermediate sums/squares.
    try:
        rmse = math.hypot(*(error / math.sqrt(n) for error in errors))
        mae = math.fsum(abs(error) / n for error in errors)
        bias = math.fsum(error / n for error in errors)
    except (OverflowError, ValueError) as exc:
        raise ValueError("Comparison metrics exceed numerical range") from exc
    return {"n": n, "rmse": _finite_number(rmse, "RMSE"), "mae": mae,
            "bias": bias, "max_abs_error": max(abs(error) for error in errors)}


def compare_measurements(result: dict, csv_path, *, source_label: str = "user_supplied",
                         time_offset_s: float = 0.0) -> dict:
    """Return interpolation errors and provenance; never extrapolate or fit.

    ``error = predicted - observed``. Invalid files/configuration raise
    ``ValueError`` (filesystem errors propagate). If all observed times lie
    outside the simulated interval, return ``status='no_overlap'`` and null
    error metrics. A partial/error simulation remains clearly labelled partial
    even when a comparison over its available interval is possible.
    """
    offset = _finite_number(time_offset_s, "time_offset_s")
    if not isinstance(source_label, str) or not source_label.strip():
        raise ValueError("source_label must be a nonempty string")
    observations, variables, raw = _read_csv(csv_path)
    times, simulation = _trajectory(result, variables)
    summary = result.get("summary", {})
    if not isinstance(summary, Mapping):
        raise ValueError("Simulation summary must be a mapping")
    partial = summary.get("success") is not True
    errors = {name: [] for name in variables}
    normalized = {name: [] for name in variables}
    missing = {name: 0 for name in variables}
    excluded = {name: 0 for name in variables}
    comparisons, excluded_rows = [], []
    rows_in_range = 0
    for row in observations:
        aligned = _finite_number(row["time_s"] + offset, "Aligned simulation time")
        inside = times[0] <= aligned <= times[-1]
        if inside:
            rows_in_range += 1
        else:
            excluded_rows.append({"time_s": row["time_s"], "simulation_time_s": aligned,
                                  "reason": "before_simulation" if aligned < times[0]
                                  else "after_simulation"})
        compared = {}
        for name in variables:
            measured = row["values"][name]
            if measured is None:
                missing[name] += 1
                continue
            if not inside:
                excluded[name] += 1
                continue
            predicted = _interpolate(aligned, times, simulation[name],
                                     hold_previous=name in HELD_VARIABLES)
            error = _finite_number(predicted - measured, "Prediction error")
            errors[name].append(error)
            value = {"observed": measured, "predicted": predicted, "error": error}
            if name in row["uncertainties"]:
                uncertainty = row["uncertainties"][name]
                normalized_error = _finite_number(error / uncertainty, "Normalized error")
                normalized[name].append(normalized_error)
                value.update(uncertainty=uncertainty, normalized_error=normalized_error)
            compared[name] = value
        if inside:
            comparisons.append({"time_s": row["time_s"], "simulation_time_s": aligned,
                                "variables": compared})
    metrics = {}
    for name in variables:
        metric = _metrics(errors[name])
        metric.update(unit=VARIABLE_UNITS[name], missing_count=missing[name],
                      excluded_out_of_range_count=excluded[name],
                      normalized_n=len(normalized[name]),
                      normalized_rmse=_metrics(normalized[name])["rmse"])
        metrics[name] = metric
    count = sum(len(values) for values in errors.values())
    warnings = []
    if partial:
        warnings.append("Simulation is partial or unsuccessful; comparison covers only "
                        "the returned trajectory and cannot establish validity of the run.")
    if excluded_rows:
        warnings.append(f"{len(excluded_rows)} observation rows outside the simulated "
                        "interval were excluded; no extrapolation was performed.")
    if any(missing.values()):
        warnings.append("Blank observation cells were omitted per variable, not replaced by zero.")
    if not count:
        warnings.append("No numeric observations overlap the returned trajectory.")
    return {
        "schema_version": 1,
        "validation_state": "comparison_only_unverified",
        "summary": {"status": "no_overlap" if not count else ("warning" if warnings else "ok"),
                    "comparison_available": bool(count), "rows_total": len(observations),
                    "rows_in_range": rows_in_range, "rows_out_of_range": len(excluded_rows),
                    "comparison_count": count, "simulation_partial": partial},
        "metrics": metrics,
        "comparisons": comparisons,
        "excluded_rows": excluded_rows,
        "provenance": {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "source_label": source_label.strip(),
            "source_kind": "user_supplied_unverified",
            "filename": Path(csv_path).name,
            "time_offset_s": offset,
            "alignment": "simulation_time_s = time_s + time_offset_s",
            "time_basis": "elapsed_seconds_no_wall_clock_timezone",
            "simulation_interval_s": [times[0], times[-1]],
            "interpolation": {
                name: ("previous_value_right_continuous" if name in HELD_VARIABLES
                       else "linear") for name in variables
            },
            "interpolation_domain": "returned_simulation_interval_only_no_extrapolation",
            "error_definition": "predicted_minus_observed",
            "uncertainty_definition": "one_standard_deviation_in_variable_unit",
            "units": {name: VARIABLE_UNITS[name] for name in variables},
            "simulation_config_sha256": result.get("metadata", {}).get("config_sha256")
            if isinstance(result.get("metadata"), Mapping) else None,
        },
        "warnings": warnings,
        "conclusion": "Descriptive comparison only. Measurement authenticity, sensor "
                      "calibration, independence of validation data and model applicability "
                      "must be assessed separately. No parameters were fitted.",
    }
