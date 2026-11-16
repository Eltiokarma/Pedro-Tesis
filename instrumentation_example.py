"""Explicitly synthetic instrumented tank fixtures and an independent reference.

The six-temperature affine reference uses a matrix exponential, not the tank
integrator. It is restricted to constant inventory/valve position and zero pump
heat. Neither the reference nor its added seeded noise is experimental evidence.
"""
from __future__ import annotations

import copy
import csv
import math
from pathlib import Path

import numpy as np
from scipy.linalg import expm

from calibration_example import SAMPLE_TIMES, TRUE_PARAMETERS, _thermal_matrix
from dynamic_calibration_cli import _write_json
from dynamic_tank import default_instrumented_case, validate_case

SEED = 20261117
SECTIONS = ("tank", "wall", "jacket")
INDICATED = tuple(f"{section}_indicated_temperature_K" for section in SECTIONS)


def reference_indicated_temperatures(config, times=SAMPLE_TIMES):
    """Independent seven-state affine solution (six temperatures + constant)."""
    case = validate_case(config)
    if case["schema_version"] != "dynamic-tank/v2" or case["controller"]["enabled"]:
        raise ValueError("Reference requires v2 with prescribed inputs and PI disabled.")
    inputs = copy.deepcopy(case["inputs"])
    actuator = case["instrumentation"]["valve_actuator"]
    if (inputs["feed_flow_kg_s"] or inputs["outlet_flow_kg_s"]
            or case["jacket"]["pump_heat_fraction"]):
        raise ValueError("Reference requires fixed inventory and zero pump heat.")
    if actuator["enabled"] and actuator["initial_opening"] != inputs["valve_opening"]:
        raise ValueError("Reference requires constant valve position, equal to its command.")
    for event in case["events"]:
        changes = event["changes"]
        if (any(changes.get(key, 0) != 0 for key in ("feed_flow_kg_s", "outlet_flow_kg_s"))
                or changes.get("valve_opening", inputs["valve_opening"]) != inputs["valve_opening"]):
            raise ValueError("Reference cannot represent inventory or valve movement events.")
    sensors = case["instrumentation"]["temperature_sensors"]
    if any(sensors[section]["time_constant_s"] <= 0 for section in SECTIONS):
        raise ValueError("Reference requires three positive sensor time constants.")
    if any(not math.isfinite(t) or not 0 <= t <= case["simulation"]["duration_s"] for t in times):
        raise ValueError("Reference sample time is outside the finite simulation domain.")
    state = np.array([case[section]["initial_temperature_K"] for section in SECTIONS]
                     + [sensors[section]["initial_temperature_K"] for section in SECTIONS] + [1.0])
    bias = np.array([sensors[section]["bias_K"] for section in SECTIONS])
    changes = {event["time_s"]: event["changes"] for event in case["events"]}
    samples, values, previous = set(times), {}, 0.0
    for time in sorted({0.0, *samples, *changes}):
        thermal = _thermal_matrix(case, inputs)
        matrix = np.zeros((7, 7))
        matrix[:3, :3] = thermal[:3, :3]
        matrix[:3, 6] = thermal[:3, 3]
        for index, section in enumerate(SECTIONS):
            inverse_tau = 1.0 / sensors[section]["time_constant_s"]
            matrix[index + 3, index] = inverse_tau
            matrix[index + 3, index + 3] = -inverse_tau
        state = expm(matrix * (time - previous)) @ state
        if time in samples:
            values[time] = state[3:6] + bias
        if time in changes:
            inputs.update(changes[time])
        previous = time
    return np.array([values[time] for time in times])


def write_instrumentation_examples(directory, *, overwrite=False):
    root = Path(directory)
    ids = ("cal_hot", "cal_warm", "validation_cooling")
    names = ["instrumented_heating.json", "valve_steps.json", "calibration/study.json",
             "calibration/reference.json", *("calibration/" + name + extension
                 for name in ids for extension in (".json", ".csv"))]
    if not overwrite and any((root / name).exists() for name in names):
        raise FileExistsError("Synthetic example destinations already exist.")
    (root / "calibration").mkdir(parents=True, exist_ok=True)
    case = default_instrumented_case()
    case["case_id"] = "synthetic-instrumented-heating"
    case["title"] = "Calentamiento instrumentado: demostración sintética"
    case["simulation"].update(duration_s=1800.0, output_interval_s=5.0, max_step_s=2.0)
    case["inputs"].update(temperature_setpoint_K=308.15, valve_opening=0.1)
    case["instrumentation"]["valve_actuator"].update(initial_opening=0.1,
        opening_rate_per_s=0.02, closing_rate_per_s=0.04)
    case["instrumentation"]["temperature_sensors"]["tank"]["bias_K"] = 0.4
    case["events"] = [{"time_s": 900.0, "changes": {"temperature_setpoint_K": 305.15}}]
    case["provenance"].update(source="Ejemplo sintético de instrumentación; ningún fabricante o instalación.",
        notes="Tiempos, sesgos y velocidades son didácticos; requieren caracterización experimental.")
    _write_json(root / "instrumented_heating.json", validate_case(case), overwrite=overwrite)
    manual = copy.deepcopy(case)
    manual["case_id"] = "synthetic-valve-step-response"
    manual["title"] = "Respuesta de válvula a escalones: demostración sintética"
    manual["controller"]["enabled"] = False
    manual["simulation"].update(duration_s=500.0, output_interval_s=1.0)
    manual["events"] = [{"time_s": time, "changes": {"valve_opening": opening}}
                        for time, opening in ((100.0, 0.9), (200.0, 0.1), (300.0, 0.8))]
    _write_json(root / "valve_steps.json", validate_case(manual), overwrite=overwrite)

    rng, experiments = np.random.default_rng(SEED), []
    conditions = ((500.0, 298.15, 353.15, 0.6, 200.0, 343.15),
                  (600.0, 308.15, 343.15, 0.4, 260.0, 353.15),
                  (550.0, 328.15, 288.15, 0.5, 200.0, 298.15))
    for index, (identifier, values) in enumerate(zip(ids, conditions)):
        mass, initial, supply, opening, change_time, new_supply = values
        current = default_instrumented_case()
        current["case_id"], current["title"] = identifier, "Ensayo instrumental sintético: " + identifier
        current["controller"]["enabled"] = False
        current["tank"]["initial_mass_kg"] = mass
        for section, bias in zip(SECTIONS, (0.4, -0.2, 0.1)):
            current[section]["initial_temperature_K"] = initial
            current["instrumentation"]["temperature_sensors"][section].update(
                initial_temperature_K=initial, bias_K=bias)
        current["inputs"].update(valve_opening=opening, utility_supply_temperature_K=supply)
        current["instrumentation"]["valve_actuator"]["initial_opening"] = opening
        current["simulation"].update(duration_s=600.0, output_interval_s=10.0,
                                    max_step_s=5.0, rtol=1e-8, atol=1e-9)
        current["events"] = [{"time_s": change_time,
                              "changes": {"utility_supply_temperature_K": new_supply}}]
        for path, value in TRUE_PARAMETERS.items():
            section, key = path.split(".")
            current[section][key] = value
        observed = reference_indicated_temperatures(current) + rng.normal(0.0, 0.05, (len(SAMPLE_TIMES), 3))
        current["wall"].update(ua_tank_W_K=450.0, ua_jacket_W_K=650.0)
        current["provenance"].update(source="Exponencial matricial independiente de seis temperaturas.",
            notes="Sensores con respuesta y sesgo conocidos sintéticos; sin registros de planta.")
        _write_json(root / "calibration" / (identifier + ".json"), current, overwrite=overwrite)
        with (root / "calibration" / (identifier + ".csv")).open(
                "w" if overwrite else "x", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["time_s", *INDICATED, *(key + "_uncertainty" for key in INDICATED)])
            for time, row in zip(SAMPLE_TIMES, observed):
                writer.writerow([time, *(f"{value:.9f}" for value in row), 0.05, 0.05, 0.05])
        experiments.append({"experiment_id": identifier,
            "role": "validation" if index == 2 else "calibration", "case_file": identifier + ".json",
            "measurements_file": identifier + ".csv", "data_kind": "synthetic", "time_offset_s": 0.0,
            "source": "Referencia expm de seis temperaturas con ruido sembrado; no son mediciones."})
    study = {"schema_version": "dynamic-calibration-study/v1", "study_id": "synthetic-instrumented-calibration",
        "equipment_id": "synthetic-instrumented-tank", "parameters": [
            {"path": "wall.ua_tank_W_K", "initial": 450.0, "lower": 100.0, "upper": 2500.0},
            {"path": "wall.ua_jacket_W_K", "initial": 650.0, "lower": 100.0, "upper": 2500.0}],
        "observables": {name: {"scale_K": 0.05, "max_validation_rmse_K": 0.15,
                               "max_validation_abs_error_K": 0.3} for name in INDICATED},
        "experiments": experiments, "options": {"max_evaluations": 100}}
    _write_json(root / "calibration/study.json", study, overwrite=overwrite)
    _write_json(root / "calibration/reference.json", {"data_kind": "synthetic",
        "method": "independent_piecewise_six_temperature_affine_matrix_exponential",
        "true_parameters": TRUE_PARAMETERS, "noise_standard_deviation_K": 0.05,
        "random_seed": SEED, "sensor_parameters": "fixed_and_known_in_input_cases_not_fitted",
        "scope": "software_demonstration_not_industrial_acceptance_or_plant_validation"}, overwrite=overwrite)
    return root / "calibration/study.json"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(write_instrumentation_examples(args.directory, overwrite=args.overwrite))
