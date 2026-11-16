"""Reproduce explicitly synthetic calibration data with a matrix exponential.

This independent, linear, three-temperature reference does not call the dynamic
integrator or the fitter. A seeded noise realization is part of the fixture,
not an assertion about real sensor uncertainty or industrial accuracy.
"""
from __future__ import annotations

import copy
import csv
import math
from pathlib import Path

import numpy as np
from scipy.linalg import expm

from dynamic_tank import default_case


SEED = 20261116
TRUE_PARAMETERS = {"wall.ua_tank_W_K": 800.0, "wall.ua_jacket_W_K": 1200.0}
TEMPERATURES = ("tank_temperature_K", "wall_temperature_K", "jacket_temperature_K")
SAMPLE_TIMES = (0.0, 7.0, 15.0, 28.0, 45.0, 70.0, 105.0, 150.0,
                200.0, 260.0, 340.0, 450.0, 600.0)


def _thermal_matrix(case, inputs):
    """Constant coefficients for fixed mass, no process flow, and zero pump heat."""
    t, w, j = case["tank"], case["wall"], case["jacket"]
    pump, circuit = case["pump"], case["circuit"]
    opening = inputs["valve_opening"]
    head = pump["shutoff_head_m"] * pump["speed_fraction"] ** 2 - circuit["static_head_m"]
    if opening == 0 or head <= 0:
        flow = 0.0
    else:
        valve_k = 1e5 / (1000.0 * 9.80665) * (3600.0 / (circuit["valve_kv_m3_h"] * opening)) ** 2
        flow = math.sqrt(head / (pump["curve_coefficient_s2_m5"]
                                 + circuit["resistance_s2_m5"] + valve_k))
    ct = t["initial_mass_kg"] * t["cp_J_kg_K"]
    cw = w["heat_capacity_J_K"]
    cj = j["mass_kg"] * j["cp_J_kg_K"]
    ht, hj, ha = (w[key] for key in ("ua_tank_W_K", "ua_jacket_W_K", "ua_ambient_W_K"))
    utility = flow * j["density_kg_m3"] * j["cp_J_kg_K"]
    return np.array([
        [-ht / ct, ht / ct, 0.0, inputs["agitator_power_W"] / ct],
        [ht / cw, -(ht + hj + ha) / cw, hj / cw, ha * inputs["ambient_temperature_K"] / cw],
        [0.0, hj / cj, -(hj + utility) / cj, utility * inputs["utility_supply_temperature_K"] / cj],
        [0.0, 0.0, 0.0, 0.0],
    ])


def reference_temperatures(case, times=SAMPLE_TIMES):
    """Piecewise exact affine-system solution; the last state is the constant 1."""
    inputs = copy.deepcopy(case["inputs"])
    if case["controller"]["enabled"]:
        raise ValueError("The reference requires prescribed inputs, with the PI disabled.")
    if inputs["feed_flow_kg_s"] or inputs["outlet_flow_kg_s"] or case["jacket"]["pump_heat_fraction"]:
        raise ValueError("The reference requires fixed mass and zero pump heat.")
    if any(event["changes"].get(key, 0.0) != 0.0 for event in case["events"]
           for key in ("feed_flow_kg_s", "outlet_flow_kg_s")):
        raise ValueError("The reference requires fixed mass throughout all events.")
    if any(not math.isfinite(value) or value < 0 for value in times):
        raise ValueError("Reference sample times must be finite and nonnegative.")
    state = np.array([case[key]["initial_temperature_K"] for key in ("tank", "wall", "jacket")] + [1.0])
    changes = {event["time_s"]: event["changes"] for event in case["events"]}
    sample_set = set(times)
    previous = 0.0
    values = {}
    for time in sorted({0.0, *sample_set, *changes}):
        state = expm(_thermal_matrix(case, inputs) * (time - previous)) @ state
        if time in sample_set:
            values[time] = state[:3].copy()
        if time in changes:
            inputs.update(changes[time])
        previous = time
    return np.array([values[time] for time in times])


def write_calibration_example(directory, *, overwrite=False):
    """Write a complete, labelled synthetic study; refuse existing files by default."""
    root = Path(directory)
    names = ["study.json", "reference.json"]
    ids = ("cal_hot", "cal_warm", "validation_cooling")
    names += [name + suffix for name in ids for suffix in (".json", ".csv")]
    if not overwrite and any((root / name).exists() for name in names):
        raise FileExistsError("The example would overwrite an existing file.")
    root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    experiments = []
    initial_conditions = (
        (500.0, 298.15, 353.15, 0.6, 200.0, {"valve_opening": 0.3}),
        (600.0, 308.15, 343.15, 0.4, 260.0, {"utility_supply_temperature_K": 353.15}),
        (550.0, 328.15, 288.15, 0.5, 200.0, {"valve_opening": 0.75}),
    )
    for index, (experiment_id, conditions) in enumerate(zip(ids, initial_conditions)):
        mass, initial_temperature, supply, opening, event_time, changes = conditions
        case = default_case()
        case["case_id"] = experiment_id
        case["title"] = "Ensayo sintético: " + experiment_id
        case["controller"]["enabled"] = False
        case["tank"]["initial_mass_kg"] = mass
        for section in ("tank", "wall", "jacket"):
            case[section]["initial_temperature_K"] = initial_temperature
        case["inputs"].update(utility_supply_temperature_K=supply, valve_opening=opening)
        case["events"] = [{"time_s": event_time, "changes": changes}]
        case["simulation"].update(duration_s=600.0, output_interval_s=10.0,
                                   max_step_s=5.0, rtol=1e-8, atol=1e-9)
        for path, value in TRUE_PARAMETERS.items():
            section, key = path.split(".")
            case[section][key] = value
        truth = reference_temperatures(case)
        observed = truth + rng.normal(0.0, 0.05, size=truth.shape)
        # The input case contains the initial estimates, not the reference truth.
        case["wall"].update(ua_tank_W_K=450.0, ua_jacket_W_K=650.0)
        case["provenance"].update(
            data_kind="synthetic",
            source="Referencia sintética por exponencial matricial; calibration_example.py.",
            notes="Parámetros iniciales deliberadamente distintos de la referencia. Ningún dato de planta.",
        )
        from dynamic_calibration_cli import _write_json
        _write_json(root / (experiment_id + ".json"), case, overwrite=overwrite)
        with (root / (experiment_id + ".csv")).open("w" if overwrite else "x", newline="", encoding="utf-8") as handle:
            columns = ["time_s", *TEMPERATURES, *(name + "_uncertainty" for name in TEMPERATURES)]
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(columns)
            for time, temperatures in zip(SAMPLE_TIMES, observed):
                writer.writerow([time, *(f"{value:.9f}" for value in temperatures), 0.05, 0.05, 0.05])
        experiments.append({
            "experiment_id": experiment_id,
            "role": "validation" if index == 2 else "calibration",
            "case_file": experiment_id + ".json",
            "measurements_file": experiment_id + ".csv",
            "data_kind": "synthetic",
            "source": "Exponencial matricial independiente con ruido gaussiano sembrado; no son mediciones.",
            "time_offset_s": 0.0,
        })
    study = {
        "schema_version": "dynamic-calibration-study/v1",
        "study_id": "synthetic-three-thermal-tests",
        "equipment_id": "synthetic-jacketed-tank-01",
        "parameters": [
            {"path": "wall.ua_tank_W_K", "initial": 450.0, "lower": 100.0, "upper": 2500.0},
            {"path": "wall.ua_jacket_W_K", "initial": 650.0, "lower": 100.0, "upper": 2500.0},
        ],
        "observables": {
            name: {"scale_K": 0.05, "max_validation_rmse_K": 0.15,
                   "max_validation_abs_error_K": 0.3} for name in TEMPERATURES
        },
        "experiments": experiments,
        "options": {"max_evaluations": 100},
    }
    reference = {
        "data_kind": "synthetic",
        "method": "piecewise affine three-body system via scipy.linalg.expm; not dynamic_tank integration",
        "true_parameters": TRUE_PARAMETERS,
        "noise_standard_deviation_K": 0.05,
        "random_seed": SEED,
        "notes": "The criteria demonstrate the software only. They are not industrial acceptance tolerances.",
    }
    for name, payload in (("study.json", study), ("reference.json", reference)):
        _write_json(root / name, payload, overwrite=overwrite)
    return root / "study.json"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Genera un estudio sintético reproducible, sin datos de planta.")
    parser.add_argument("directory")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(write_calibration_example(args.directory, overwrite=args.overwrite))
