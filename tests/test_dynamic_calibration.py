"""Budgets, cancellation and reporting around an analytic wall-cooling trial."""
import csv
import json
import math
from pathlib import Path

import pytest

import dynamic_calibration as calibration
from dynamic_tank import default_case


def make_study(folder, *, budget=80, true_ua=12., scale=.1, validation_shift=0.):
    folder.mkdir(parents=True, exist_ok=True)
    experiments = []
    for label, role, initial in (("warm", "calibration", 340.), ("cool", "validation", 320.)):
        config = default_case()
        config["case_id"] = label
        config["controller"]["enabled"] = False
        config["tank"]["initial_temperature_K"] = 300.
        config["jacket"]["initial_temperature_K"] = 300.
        config["wall"].update(initial_temperature_K=initial, ua_tank_W_K=0.,
                              ua_jacket_W_K=0., ua_ambient_W_K=12.)
        config["inputs"].update(valve_opening=0., agitator_power_W=0., ambient_temperature_K=298.15)
        config["simulation"].update(duration_s=2000., max_step_s=50., output_interval_s=1000.,
                                    rtol=1e-9, atol=1e-10)
        (folder / f"{label}.json").write_text(json.dumps(config), encoding="utf-8")
        with (folder / f"{label}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["time_s", "wall_temperature_K"])
            for time in (0., 17.3, 57.6, 190.4, 650.8, 1100.9, 2000.):
                value = 298.15 + (initial - 298.15) * math.exp(-true_ua / 45000. * time)
                writer.writerow([time, value + (validation_shift if role == "validation" else 0.)])
        experiments.append({"experiment_id": label, "role": role,
                            "case_file": f"{label}.json", "measurements_file": f"{label}.csv",
                            "data_kind": "synthetic", "source": "analytic exponential wall cooling",
                            "time_offset_s": 0.})
    manifest = {"schema_version": "dynamic-calibration-study/v1", "study_id": "cooling-study",
                "equipment_id": "synthetic-wall", "parameters": [{
                    "path": "wall.ua_ambient_W_K", "initial": 30., "lower": 1., "upper": 50.}],
                "observables": {"wall_temperature_K": {"scale_K": scale,
                    "max_validation_rmse_K": .02, "max_validation_abs_error_K": .04}},
                "experiments": experiments, "options": {"max_evaluations": budget}}
    path = folder / "study.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_analytic_wall_fit_and_reproducible_cases_do_not_mutate_inputs(tmp_path):
    study = make_study(tmp_path)
    original = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    progress = []
    result = calibration.calibrate_study(study, progress=progress.append)
    assert result["summary"]["status"] == "ok"
    assert result["summary"]["optimization_converged"]
    assert result["summary"]["validation_status"] == "criteria_met"
    assert result["parameters"][0]["value"] == pytest.approx(12., abs=.002)
    assert result["summary"]["objective_after"] < result["summary"]["objective_before"] * 1e-6
    assert result["validation_state"] == "synthetic_calibration_only"
    for experiment in result["experiments"]:
        assert experiment["fitted_metrics"]["wall_temperature_K"]["rmse"] < 1e-4
        assert "cooling-study" in experiment["fitted_case"]["provenance"]["notes"]
        assert experiment["provenance"]["fitted_case_sha256"] != experiment["provenance"]["case_sha256"]
        assert len(experiment["provenance"]["measurement_aligned_sha256"]) == 64
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == original
    assert progress[-1]["evaluations"] == result["summary"]["evaluations"]
    assert progress[-1]["simulations_count"] == result["summary"]["simulations_count"]
    assert progress[-1]["phase"] == "completed"
    json.dumps(result, allow_nan=False)


def test_real_candidate_budget_includes_numerical_jacobian(tmp_path, monkeypatch):
    study = make_study(tmp_path, budget=1)
    actual_simulations = []
    original_simulate = calibration.simulate_dynamic_tank

    def tracked(*args, **kwargs):
        actual_simulations.append(1)
        return original_simulate(*args, **kwargs)

    monkeypatch.setattr(calibration, "simulate_dynamic_tank", tracked)
    result = calibration.calibrate_study(study)
    assert result["summary"]["status"] == "failed"
    assert result["failure"]["reason"] == "evaluation_budget_exceeded"
    assert result["summary"]["evaluations"] == 1
    assert result["summary"]["simulations_count"] == len(actual_simulations)
    assert result["summary"]["simulations_count"] > result["summary"]["evaluations"]
    assert all(experiment["fitted_case"] is None for experiment in result["experiments"])
    json.dumps(result, allow_nan=False)


def test_cancel_before_work_returns_no_exportable_candidate(tmp_path):
    result = calibration.calibrate_study(make_study(tmp_path), cancel=lambda: True)
    assert result["summary"]["status"] == "cancelled"
    assert result["summary"]["simulations_count"] == 0
    assert result["summary"]["evaluations"] == 0
    assert all(experiment["fitted_case"] is None for experiment in result["experiments"])


def test_cancel_during_jacobian_propagates_to_integrator(tmp_path):
    stopped = False

    def progress(event):
        nonlocal stopped
        if event["phase"] == "jacobian":
            stopped = True

    result = calibration.calibrate_study(make_study(tmp_path), cancel=lambda: stopped, progress=progress)
    assert result["summary"]["status"] == "cancelled"
    assert result["failure"]["reason"] == "user_cancelled"
    assert result["summary"]["validation_status"] == "not_assessed"
    assert all(experiment["fitted_case"] is None for experiment in result["experiments"])


def test_physical_stop_is_not_an_optimizer_success(tmp_path):
    study = make_study(tmp_path)
    case_path = tmp_path / "warm.json"
    config = json.loads(case_path.read_text(encoding="utf-8"))
    config["inputs"]["outlet_flow_kg_s"] = 5.
    case_path.write_text(json.dumps(config), encoding="utf-8")
    result = calibration.calibrate_study(study)
    assert result["summary"]["status"] == "failed"
    assert not result["summary"]["optimization_converged"]
    assert result["failure"]["reason"] == "incomplete_candidate_simulation"
    assert result["failure"]["simulation_summary"]["stop_reason"] == "minimum_inventory"
    assert all(experiment["fitted_case"] is None for experiment in result["experiments"])


def test_large_noise_scale_marks_weak_absolute_sensitivity(tmp_path):
    result = calibration.calibrate_study(make_study(tmp_path, scale=1e7))
    assert result["summary"]["optimization_converged"]
    assert not result["summary"]["usable_parameter_estimate"]
    assert result["summary"]["status"] == "warning"
    assert result["diagnostics"]["weak_sensitivity"]
    assert result["diagnostics"]["scaled_jacobian_condition"] == pytest.approx(1.)
    assert result["diagnostics"]["minimum_scaled_singular_value"] < 1.
    assert any("sensibilidad" in warning.lower() for warning in result["warnings"])


def test_fit_at_bound_is_flagged_instead_of_claiming_unique_parameter(tmp_path):
    result = calibration.calibrate_study(make_study(tmp_path, true_ua=80.))
    assert result["summary"]["optimization_converged"]
    assert result["parameters"][0]["at_bound"]
    assert not result["summary"]["usable_parameter_estimate"]
    assert result["summary"]["validation_status"] == "criteria_exceeded"
    assert result["summary"]["status"] == "warning"
    assert "Advertencias" in result["experiments"][0]["fitted_case"]["provenance"]["notes"]


def test_unrepresentable_residual_scale_returns_serializable_failure(tmp_path):
    result = calibration.calibrate_study(make_study(tmp_path, scale=1e-320))
    assert result["summary"]["status"] == "failed"
    assert result["failure"]["reason"] == "nonfinite_comparison_metrics"
    assert not result["summary"]["usable_parameter_estimate"]
    assert all(experiment["fitted_case"] is None for experiment in result["experiments"])
    json.dumps(result, allow_nan=False)


def test_validation_failure_warning_travels_with_exported_case(tmp_path):
    result = calibration.calibrate_study(make_study(tmp_path, validation_shift=2.))
    assert result["summary"]["optimization_converged"]
    assert result["summary"]["validation_status"] == "criteria_exceeded"
    for experiment in result["experiments"]:
        assert "criterio de error" in experiment["fitted_case"]["provenance"]["notes"]
        assert experiment["provenance"]["fitted_case_sha256"] == calibration._json_hash(experiment["fitted_case"])
