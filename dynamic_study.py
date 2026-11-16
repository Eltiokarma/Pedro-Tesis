"""Read an explicit calibration/holdout study without altering its input files.

Every observation is in SI, with an explicit time offset.  A study declares
measurement provenance; this loader cannot authenticate measurements or prove
that separate experiment identifiers are independent experiments.  It rejects
reused measurements across fitting and holdout roles, including formatting and
clock-offset aliases.  Optimisation consumes the returned in-memory snapshots,
so hashes refer to the bytes actually read rather than a later file revision.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath

from dynamic_measurements import INDICATED_TEMPERATURES, _read_csv
from dynamic_tank import validate_case


SCHEMA_VERSION = "dynamic-calibration-study/v1"
PARAMETER_UNITS = {
    "wall.ua_tank_W_K": "W/K",
    "wall.ua_jacket_W_K": "W/K",
    "wall.ua_ambient_W_K": "W/K",
    "wall.heat_capacity_J_K": "J/K",
}
OBSERVABLES = (
    "tank_temperature_K", "wall_temperature_K", "jacket_temperature_K",
    "tank_indicated_temperature_K", "wall_indicated_temperature_K",
    "jacket_indicated_temperature_K",
)
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_EXPERIMENTS = 12
MAX_SELECTED_OBSERVATIONS = 20_000
MAX_EVALUATIONS = 500

_STUDY_KEYS = {
    "schema_version", "study_id", "equipment_id", "parameters",
    "observables", "experiments", "options",
}
_EXPERIMENT_KEYS = {
    "experiment_id", "role", "case_file", "measurements_file",
    "data_kind", "source", "time_offset_s",
}


def _object(value, keys, name):
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        raise ValueError(f"{name}: expected an object with string keys")
    missing, unknown = set(keys) - set(value), set(value) - set(keys)
    if missing or unknown:
        raise ValueError(f"{name}: missing {sorted(missing)}; unknown {sorted(unknown)}")


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: expected nonempty text")
    return value.strip()


def _finite(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: expected a finite real number, not bool or text")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name}: expected a finite real number") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise ValueError(f"{name}: expected a {'positive ' if positive else ''}finite number")
    return number


def _no_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"JSON contains duplicate key: {key}")
        obj[key] = value
    return obj


def _invalid_constant(value):
    raise ValueError(f"JSON contains a nonfinite constant: {value}")


def _read_json(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError(f"JSON exceeds the {MAX_JSON_BYTES}-byte limit")
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_no_duplicates,
                           parse_constant=_invalid_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Study and case JSON must be finite UTF-8 JSON objects") from exc
    return value, raw


def _reference(value, folder, name):
    # Relative paths may refer to sibling folders (../cases/a.json).  Resolve
    # only for reading: retain the manifest's original references in reports.
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name}: expected a nonempty relative path without outer whitespace")
    if "\x00" in value or Path(value).is_absolute() or PureWindowsPath(value).drive:
        raise ValueError(f"{name}: use a relative file path")
    if PureWindowsPath(value).root:
        raise ValueError(f"{name}: use a relative file path")
    # Forward slashes are portable; backslashes are Windows paths and should
    # not silently name a different file when the study is opened on Linux.
    if "\\" in value:
        raise ValueError(f"{name}: use forward slashes in portable relative paths")
    path = (folder / value).resolve()
    if not path.is_file():
        raise ValueError(f"{name}: referenced file does not exist: {value}")
    return path


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     allow_nan=False, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _zero_normalised(value):
    # JSON distinguishes -0.0 from 0.0, but these represent the same observation.
    return 0.0 if value == 0 else value


def _measurement_signature(rows, observables, offset=0.0):
    selected = []
    for row in rows:
        values = {name: _zero_normalised(row["values"][name])
                  for name in observables if row["values"].get(name) is not None}
        if values:
            # Deliberately omit uncertainty: changing weights or adding blank
            # rows/unselected columns does not create a new experiment.
            selected.append({"time_s": _zero_normalised(row["time_s"] + offset),
                             "values": values})
    return _digest(selected)


def _physical_identity(case, parameter_paths):
    identity = {section: copy.deepcopy(case[section])
                for section in ("tank", "wall", "jacket", "pump", "circuit")}
    identity["schema_version"] = case["schema_version"]
    if case["schema_version"] == "dynamic-tank/v2":
        instrumentation = copy.deepcopy(case["instrumentation"])
        for sensor in instrumentation["temperature_sensors"].values():
            sensor.pop("initial_temperature_K")
        instrumentation["valve_actuator"].pop("initial_opening")
        identity["instrumentation"] = instrumentation
    for section, keys in {
        "tank": ("initial_mass_kg", "initial_temperature_K",
                 "initial_tracer_mass_fraction", "min_mass_kg"),
        "wall": ("initial_temperature_K",),
        "jacket": ("initial_temperature_K",),
        "pump": ("speed_fraction",),
    }.items():
        for key in keys:
            identity[section].pop(key)
    for path in parameter_paths:
        section, key = path.split(".")
        identity[section].pop(key)
    return identity


def _observation_temperature_range(case, variable):
    """Property limits apply to physical temperature, not to a biased reading."""
    lower, upper = (case["simulation"][key] for key in ("min_temperature_K", "max_temperature_K"))
    if variable in INDICATED_TEMPERATURES:
        if case["schema_version"] != "dynamic-tank/v2":
            raise ValueError("Indicated temperature observations require dynamic-tank/v2 instrumentation")
        section = variable.split("_", 1)[0]
        bias = case["instrumentation"]["temperature_sensors"][section]["bias_K"]
        lower, upper = lower + bias, upper + bias
        if not math.isfinite(lower) or not math.isfinite(upper):
            raise ValueError("Indicated temperature domain must remain finite after applying the sensor bias")
    return lower, upper


def load_study(path) -> dict:
    """Return a validated study and exact case/CSV snapshots, without writes.

    Invalid manifests, unsupported physics, missing inputs, out-of-domain
    selected readings and duplicated fitting/holdout data raise ``ValueError``.
    Filesystem errors from readable-looking files propagate.  Observations keep
    their original CSV ``time_s``; model time is ``time_s + time_offset_s``.
    The numerical scale is used only when a per-observation uncertainty is not
    supplied; it is not an inferred sensor uncertainty or confidence interval.
    """
    manifest_path = Path(path).resolve()
    manifest, manifest_raw = _read_json(manifest_path)
    _object(manifest, _STUDY_KEYS, "study")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version: expected {SCHEMA_VERSION}")
    result = copy.deepcopy(dict(manifest))
    for key in ("study_id", "equipment_id"):
        result[key] = _text(result[key], key)

    parameters = result["parameters"]
    if not isinstance(parameters, list) or not 1 <= len(parameters) <= 3:
        raise ValueError("parameters: choose one to three thermal parameters")
    parameter_paths = set()
    for index, parameter in enumerate(parameters):
        label = f"parameters[{index}]"
        _object(parameter, {"path", "initial", "lower", "upper"}, label)
        path_name = parameter["path"]
        if not isinstance(path_name, str) or path_name not in PARAMETER_UNITS:
            raise ValueError(f"{label}.path: unsupported thermal parameter")
        if path_name in parameter_paths:
            raise ValueError(f"{label}.path: duplicate parameter")
        parameter_paths.add(path_name)
        for key in ("initial", "lower", "upper"):
            parameter[key] = _finite(parameter[key], f"{label}.{key}")
        lower, initial, upper = (parameter[key] for key in ("lower", "initial", "upper"))
        if lower < 0 or (path_name == "wall.heat_capacity_J_K" and lower <= 0):
            raise ValueError(f"{label}: physical parameter bounds must be nonnegative (heat capacity positive)")
        if not lower < initial < upper or not math.isfinite(upper - lower):
            raise ValueError(f"{label}: require finite lower < initial < upper")

    observables = result["observables"]
    if (not isinstance(observables, Mapping) or not observables
            or any(name not in OBSERVABLES for name in observables)):
        raise ValueError("observables: select explicit tank/wall/jacket temperature names in K")
    for name, settings in observables.items():
        _object(settings, {"scale_K", "max_validation_rmse_K", "max_validation_abs_error_K"},
                f"observables.{name}")
        for key in settings:
            settings[key] = _finite(settings[key], f"observables.{name}.{key}", positive=True)

    _object(result["options"], {"max_evaluations"}, "options")
    budget = result["options"]["max_evaluations"]
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= MAX_EVALUATIONS:
        raise ValueError(f"options.max_evaluations: integer from 1 to {MAX_EVALUATIONS} required")

    experiments = result["experiments"]
    if not isinstance(experiments, list) or not 2 <= len(experiments) <= MAX_EXPERIMENTS:
        raise ValueError(f"experiments: two to {MAX_EXPERIMENTS} experiments required")
    ids, roles, signatures = set(), set(), {}
    reference_identity = None
    selected_total = calibration_count = 0
    # Share immutable input snapshots when multiple experiments use one case or
    # CSV.  Each file is read once even if aliases resolve to the same location.
    case_cache, measurement_cache = {}, {}
    for index, experiment in enumerate(experiments):
        label = f"experiments[{index}]"
        _object(experiment, _EXPERIMENT_KEYS, label)
        experiment["experiment_id"] = _text(experiment["experiment_id"], f"{label}.experiment_id")
        identifier = experiment["experiment_id"]
        if identifier in ids:
            raise ValueError(f"{label}: duplicate experiment_id")
        ids.add(identifier)
        role = experiment["role"]
        if not isinstance(role, str) or role not in {"calibration", "validation"}:
            raise ValueError(f"{label}.role: calibration or validation required")
        roles.add(role)
        if experiment["data_kind"] not in ("synthetic", "user_supplied"):
            raise ValueError(f"{label}.data_kind: synthetic or user_supplied required")
        experiment["source"] = _text(experiment["source"], f"{label}.source")
        offset = _finite(experiment["time_offset_s"], f"{label}.time_offset_s")
        experiment["time_offset_s"] = offset
        case_path = _reference(experiment["case_file"], manifest_path.parent, f"{label}.case_file")
        csv_path = _reference(experiment["measurements_file"], manifest_path.parent,
                              f"{label}.measurements_file")
        if case_path not in case_cache:
            source_case, case_raw = _read_json(case_path)
            case_cache[case_path] = (validate_case(source_case), hashlib.sha256(case_raw).hexdigest())
        case, case_hash = copy.deepcopy(case_cache[case_path])
        if case["schema_version"] == "dynamic-tank/v3":
            raise ValueError(f"{label}: calibration of dynamic-tank/v3 thermal loops is not supported; "
                             "use theoretical benchmarks for this solver stage")
        if case["controller"]["enabled"]:
            raise ValueError(f"{label}: disable the PI and prescribe the recorded input history")
        observable_ranges = {name: _observation_temperature_range(case, name) for name in observables}
        identity = _physical_identity(case, parameter_paths)
        if reference_identity is None:
            reference_identity = identity
        elif identity != reference_identity:
            raise ValueError(f"{label}: fixed physical properties must describe the same equipment")
        # Check every common starting estimate and the full upper corner using
        # the engine's own domain validation before an optimiser is constructed.
        for field in ("initial", "lower", "upper"):
            candidate = copy.deepcopy(case)
            for parameter in parameters:
                section, key = parameter["path"].split(".")
                candidate[section][key] = parameter[field]
            validate_case(candidate)
        if csv_path not in measurement_cache:
            rows, csv_variables, raw = _read_csv(csv_path)
            measurement_cache[csv_path] = (rows, csv_variables, hashlib.sha256(raw).hexdigest())
        rows, csv_variables, raw_hash = copy.deepcopy(measurement_cache[csv_path])
        missing_variables = set(observables) - set(csv_variables)
        if missing_variables:
            raise ValueError(f"{label}: CSV missing selected temperature columns {sorted(missing_variables)}")
        counts = dict.fromkeys(observables, 0)
        duration = case["simulation"]["duration_s"]
        for row in rows:
            aligned = row["time_s"] + offset
            if not math.isfinite(aligned):
                raise ValueError(f"{label}: aligned observation time is nonfinite")
            for name in observables:
                temperature_min, temperature_max = observable_ranges[name]
                value = row["values"][name]
                if value is None:
                    continue
                if value <= 0:
                    raise ValueError(f"{label}: {name} must be an absolute temperature greater than zero K")
                if not temperature_min <= value <= temperature_max:
                    raise ValueError(f"{label}: selected {name} lies outside the declared property temperature "
                                     "domain (including declared sensor bias for indicated channels); "
                                     "review model applicability instead of clipping observations")
                if not 0 <= aligned <= duration:
                    raise ValueError(f"{label}: selected observation outside the simulated interval; no extrapolation")
                counts[name] += 1
                selected_total += 1
                if selected_total > MAX_SELECTED_OBSERVATIONS:
                    raise ValueError(f"Study exceeds {MAX_SELECTED_OBSERVATIONS} selected numeric observations")
                if role == "calibration":
                    calibration_count += 1
        if any(count == 0 for count in counts.values()):
            raise ValueError(f"{label}: each selected temperature requires a numeric observation")
        canonical_hash = _measurement_signature(rows, observables)
        aligned_hash = _measurement_signature(rows, observables, offset)
        for kind, value in (("raw", raw_hash), ("canonical", canonical_hash), ("aligned", aligned_hash)):
            signature = kind, value
            previous = signatures.get(signature)
            if previous is not None and previous["role"] != role:
                raise ValueError(f"Calibration/validation leakage: {identifier} duplicates measurements from "
                                 f"{previous['experiment_id']} ({kind} fingerprint)")
            signatures[signature] = {"role": role, "experiment_id": identifier}
        experiment.update(case=case, observations=rows,
                          measurement_sha256=raw_hash,
                          measurement_canonical_sha256=canonical_hash,
                          measurement_aligned_sha256=aligned_hash,
                          case_sha256=case_hash)
    if roles != {"calibration", "validation"}:
        raise ValueError("Study requires separate calibration and validation experiments")
    if calibration_count <= len(parameters):
        raise ValueError("Calibration requires more numeric observations than fitted parameters")
    result["provenance"] = {
        "study_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "authenticity": "user_declared_unverified",
        "independence": "duplicate_detection_only_not_proof",
        "measurement_snapshots": "read_once_before_optimisation",
        "selected_observations": selected_total,
        "calibration_observations": calibration_count,
        "units": "explicit_SI_temperature_K_time_s",
        "case_schema_version": experiments[0]["case"]["schema_version"],
        "observation_channels": {
            name: ("sensor_indication_including_declared_bias" if name in INDICATED_TEMPERATURES
                   else "physical_process_temperature") for name in observables
        },
    }
    return result
