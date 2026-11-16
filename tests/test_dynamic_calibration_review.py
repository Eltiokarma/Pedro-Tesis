"""Independent physical checks for the bounded thermal identification workflow.
Observations here come from an affine matrix exponential, never from the tank
integrator or calibration code. They are synthetic verification fixtures, not
experimental evidence. A stationary liquid inventory makes the thermal model a
linear three-body system; the augmented fourth state supplies ambient forcing.
"""
from __future__ import annotations

import copy
import csv
import json

import numpy as np
import pytest
from scipy.linalg import expm

from dynamic_calibration import calibrate_study
from dynamic_tank import default_case


VARIABLES = (
    "tank_temperature_K", "wall_temperature_K", "jacket_temperature_K",
)
TIMES = (0.0, 3.7, 8.2, 21.1, 47.3, 80.4, 117.9, 180.0)
TRUTH = {
    "wall.ua_tank_W_K": 620.0,
    "wall.ua_jacket_W_K": 940.0,
    "wall.heat_capacity_J_K": 45000.0,
}
SPECS = {
    "wall.ua_tank_W_K": {"initial": 400.0, "lower": 100.0, "upper": 1600.0},
    "wall.ua_jacket_W_K": {"initial": 650.0, "lower": 100.0, "upper": 1800.0},
    "wall.heat_capacity_J_K": {"initial": 30000.0, "lower": 10000.0, "upper": 90000.0},
}


def _put(case, path, value):
    section, key = path.split(".")
    case[section][key] = value


def _case(case_id, temperatures=(298.15, 342.15, 326.15)):
    case = default_case()
    case["case_id"] = case_id
    case["controller"]["enabled"] = False
    case["tank"]["initial_mass_kg"] = 100.0
    case["jacket"]["mass_kg"] = 20.0
    for section, temperature in zip(("tank", "wall", "jacket"), temperatures):
        case[section]["initial_temperature_K"] = temperature
    case["inputs"].update(
        feed_flow_kg_s=0.0, outlet_flow_kg_s=0.0, valve_opening=0.0,
        agitator_power_W=0.0, ambient_temperature_K=295.15,
    )
    case["simulation"].update(
        duration_s=180.0, output_interval_s=61.0, max_step_s=10.0,
        rtol=1e-9, atol=1e-10,
    )
    for path, value in TRUTH.items():
        _put(case, path, value)
    return case


def _independent_temperatures(case, times=TIMES):
    tank, wall, jacket = (case[name] for name in ("tank", "wall", "jacket"))
    ct = tank["initial_mass_kg"] * tank["cp_J_kg_K"]
    cw = wall["heat_capacity_J_K"]
    cj = jacket["mass_kg"] * jacket["cp_J_kg_K"]
    ut = wall["ua_tank_W_K"]
    uj = wall["ua_jacket_W_K"]
    ua = wall["ua_ambient_W_K"]
    ambient = case["inputs"]["ambient_temperature_K"]
    generator = np.array([
        [-ut / ct, ut / ct, 0.0, 0.0],
        [ut / cw, -(ut + uj + ua) / cw, uj / cw, ua * ambient / cw],
        [0.0, uj / cj, -uj / cj, 0.0],
        [0.0, 0.0, 0.0, 0.0],
    ])
    initial = np.array([
        tank["initial_temperature_K"], wall["initial_temperature_K"],
        jacket["initial_temperature_K"], 1.0,
    ])
    return [(expm(generator * time) @ initial)[:3] for time in times]


def _write_observations(path, case, *, sigma=None, offsets=None):
    columns = ["time_s", *VARIABLES]
    if sigma is not None:
        columns.extend(f"{variable}_uncertainty" for variable in VARIABLES)
    offsets = offsets or {}
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for time, temperatures in zip(TIMES, _independent_temperatures(case)):
            row = {"time_s": time}
            for variable, value in zip(VARIABLES, temperatures):
                row[variable] = float(value) + offsets.get(variable, 0.0)
                if sigma is not None:
                    row[f"{variable}_uncertainty"] = sigma
            writer.writerow(row)


def _write_study(tmp_path, paths, *, calibration_cases=None, validation_case=None,
                 sigmas=None, observables=VARIABLES):
    calibration_cases = calibration_cases or [_case("calibration-1")]
    validation_case = validation_case or _case(
        "validation-1", temperatures=(312.15, 290.15, 346.15)
    )
    experiments = []
    cases = [*(('calibration', case) for case in calibration_cases),
             ('validation', validation_case)]
    for index, (role, truth) in enumerate(cases):
        case = copy.deepcopy(truth)
        for path in paths:
            _put(case, path, SPECS[path]["initial"])
        case_name = f"case-{index}.json"
        measurements_name = f"measurements-{index}.csv"
        (tmp_path / case_name).write_text(json.dumps(case), encoding="utf-8")
        _write_observations(tmp_path / measurements_name, truth,
                            sigma=None if sigmas is None else sigmas[index])
        experiments.append({
            "experiment_id": f"experiment-{index}", "role": role,
            "case_file": case_name, "measurements_file": measurements_name,
            "data_kind": "synthetic", "source": "Independent affine matrix exponential",
            "time_offset_s": 0.0,
        })
    manifest = {
        "schema_version": "dynamic-calibration-study/v1",
        "study_id": "independent-expm-verification",
        "equipment_id": "synthetic-three-body-test-rig",
        "parameters": [{"path": path, **SPECS[path]} for path in paths],
        "observables": {variable: {
            "scale_K": 0.05, "max_validation_rmse_K": 0.01,
            "max_validation_abs_error_K": 0.025,
        } for variable in observables},
        "experiments": experiments,
        "options": {"max_evaluations": 180},
    }
    study_path = tmp_path / "study.json"
    study_path.write_text(json.dumps(manifest), encoding="utf-8")
    return study_path, manifest


@pytest.mark.parametrize("paths", [
    ("wall.ua_tank_W_K",),
    ("wall.ua_tank_W_K", "wall.ua_jacket_W_K"),
    ("wall.ua_tank_W_K", "wall.heat_capacity_J_K"),
    ("wall.ua_tank_W_K", "wall.ua_jacket_W_K", "wall.heat_capacity_J_K"),
])
def test_recovers_independent_three_body_parameters_at_irregular_times(tmp_path, paths):
    study_path, _ = _write_study(tmp_path, paths)
    result = calibrate_study(study_path)
    assert result["summary"]["optimization_converged"], result["summary"]
    assert result["summary"]["usable_parameter_estimate"]
    assert result["diagnostics"]["rank"] == len(paths)
    assert result["summary"]["validation_status"] == "criteria_met"
    estimates = {parameter["path"]: parameter["value"]
                 for parameter in result["parameters"]}
    for path in paths:
        assert estimates[path] == pytest.approx(TRUTH[path], rel=2e-3)
    assert result["summary"]["objective_after"] < result["summary"]["objective_before"] * 1e-5
    assert result["validation_state"] == "synthetic_calibration_only"
    json.dumps(result, allow_nan=False)


def test_bad_holdout_changes_assessment_but_never_fitted_parameters(tmp_path):
    path = "wall.ua_tank_W_K"
    study_path, manifest = _write_study(tmp_path, (path,))
    good = calibrate_study(study_path)
    heldout = manifest["experiments"][-1]
    case_path = tmp_path / heldout["case_file"]
    independent_truth = json.loads(case_path.read_text(encoding="utf-8"))
    _put(independent_truth, path, TRUTH[path])
    _write_observations(tmp_path / heldout["measurements_file"], independent_truth,
                        offsets={"tank_temperature_K": 3.0})
    bad = calibrate_study(study_path)
    assert good["summary"]["validation_status"] == "criteria_met"
    assert bad["summary"]["validation_status"] == "criteria_exceeded"
    assert bad["parameters"][0]["value"] == pytest.approx(good["parameters"][0]["value"], abs=1e-9)
    assert bad["summary"]["objective_before"] == good["summary"]["objective_before"]
    assert bad["summary"]["objective_after"] == good["summary"]["objective_after"]
    assert bad["validation_state"] == "synthetic_calibration_only"


def test_unexcited_equilibrium_does_not_establish_identification(tmp_path):
    calibration = _case("constant-calibration", temperatures=(300.0, 300.0, 300.0))
    validation = _case("constant-validation", temperatures=(301.0, 301.0, 301.0))
    calibration["inputs"]["ambient_temperature_K"] = 300.0
    validation["inputs"]["ambient_temperature_K"] = 301.0
    study_path, _ = _write_study(
        tmp_path, ("wall.ua_tank_W_K",), calibration_cases=[calibration],
        validation_case=validation,
    )
    result = calibrate_study(study_path)
    assert result["diagnostics"]["rank"] == 0
    assert not result["summary"]["usable_parameter_estimate"]
    assert result["summary"]["status"] == "warning"
    assert result["warnings"]
    # A zero prediction error is compatible with an unobservable parameter.
    assert result["summary"]["validation_status"] == "criteria_met"
    json.dumps(result, allow_nan=False)


def test_observation_uncertainty_controls_weighting_without_using_holdout(tmp_path):
    path = "wall.ua_tank_W_K"
    first = _case("precise-reference")
    conflicting = _case("conflicting-reference")
    _put(conflicting, path, 1100.0)
    study_path, manifest = _write_study(
        tmp_path, (path,), calibration_cases=[first, conflicting],
        sigmas=(0.01, 10.0, 0.1), observables=("tank_temperature_K",),
    )
    result = calibrate_study(study_path)
    assert result["summary"]["optimization_converged"]
    assert result["parameters"][0]["value"] == pytest.approx(620.0, abs=0.5)
    for index, (case, sigma) in enumerate(((first, 10.0), (conflicting, 0.01))):
        _write_observations(tmp_path / manifest["experiments"][index]["measurements_file"],
                            case, sigma=sigma)
    reversed_weights = calibrate_study(study_path)
    assert reversed_weights["summary"]["optimization_converged"]
    assert reversed_weights["parameters"][0]["value"] == pytest.approx(1100.0, abs=0.5)
