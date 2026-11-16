"""Independent sensor-response identification and explicit observation semantics.

The oracle is a seven-state affine matrix exponential (three physical thermal
states, three probe states and a constant), not the dynamic integrator. These
are numerical verification fixtures, never experimental observations.
"""
from __future__ import annotations

import copy
import csv
import json

import numpy as np
import pytest
from scipy.linalg import expm

from dynamic_calibration import calibrate_study
from dynamic_measurements import compare_measurements, write_measurement_template
from dynamic_study import load_study
from dynamic_tank import default_case


SECTIONS = ("tank", "wall", "jacket")
INDICATED = tuple(f"{section}_indicated_temperature_K" for section in SECTIONS)
PHYSICAL = tuple(f"{section}_temperature_K" for section in SECTIONS)
TIMES = (0.0, 3.7, 8.2, 21.1, 47.3, 80.4, 117.9, 180.0)
TRUE_UA = 620.0


def _case(index):
    case = default_case()
    case["schema_version"] = "dynamic-tank/v2"
    case["case_id"] = f"instrumented-{index}"
    case["controller"]["enabled"] = False
    case["tank"]["initial_mass_kg"] = 100.0
    case["jacket"]["mass_kg"] = 20.0
    case["wall"].update(ua_tank_W_K=TRUE_UA, ua_jacket_W_K=940.0)
    initial = ((298.15, 342.15, 326.15), (312.15, 290.15, 346.15))[index]
    probes = ((295.15, 330.15, 320.15), (315.15, 294.15, 340.15))[index]
    for section, temperature in zip(SECTIONS, initial):
        case[section]["initial_temperature_K"] = temperature
    case["inputs"].update(valve_opening=0.0, agitator_power_W=0.0,
                          ambient_temperature_K=295.15)
    case["simulation"].update(duration_s=180.0, output_interval_s=61.0,
                               max_step_s=10.0, rtol=1e-9, atol=1e-10)
    case["instrumentation"] = {
        "temperature_sensors": {
            section: {"time_constant_s": tau, "bias_K": bias,
                      "initial_temperature_K": initial_probe}
            for section, tau, bias, initial_probe in zip(
                SECTIONS, (20.0, 10.0, 10.0), (1.2, -0.7, 0.5), probes)
        },
        "valve_actuator": {"enabled": False, "time_constant_s": 2.0,
                           "opening_rate_per_s": 0.05, "closing_rate_per_s": 0.1,
                           "initial_opening": 0.0},
        "tracking_time_s": 30.0,
    }
    return case


def _reference(case):
    ct = case["tank"]["initial_mass_kg"] * case["tank"]["cp_J_kg_K"]
    cw = case["wall"]["heat_capacity_J_K"]
    cj = case["jacket"]["mass_kg"] * case["jacket"]["cp_J_kg_K"]
    ut, uj, ua = (case["wall"][key] for key in
                  ("ua_tank_W_K", "ua_jacket_W_K", "ua_ambient_W_K"))
    matrix = np.zeros((7, 7))
    matrix[:3, :3] = [[-ut / ct, ut / ct, 0.0],
                       [ut / cw, -(ut + uj + ua) / cw, uj / cw],
                       [0.0, uj / cj, -uj / cj]]
    matrix[1, 6] = ua * case["inputs"]["ambient_temperature_K"] / cw
    sensors = case["instrumentation"]["temperature_sensors"]
    for index, section in enumerate(SECTIONS):
        tau = sensors[section]["time_constant_s"]
        matrix[index + 3, index] = 1.0 / tau
        matrix[index + 3, index + 3] = -1.0 / tau
    initial = np.array([case[section]["initial_temperature_K"] for section in SECTIONS]
                       + [sensors[section]["initial_temperature_K"] for section in SECTIONS] + [1.0])
    states = np.array([expm(matrix * time) @ initial for time in TIMES])
    bias = np.array([sensors[section]["bias_K"] for section in SECTIONS])
    return states[:, :3], states[:, 3:6] + bias


def _save_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_study(folder, *, bias=None, selected=INDICATED):
    folder.mkdir(parents=True, exist_ok=True)
    experiments = []
    for index, role in enumerate(("calibration", "validation")):
        truth = _case(index)
        if bias is not None:
            for sensor in truth["instrumentation"]["temperature_sensors"].values():
                sensor["bias_K"] = bias
        physical, indicated = _reference(truth)
        case = copy.deepcopy(truth)
        case["wall"]["ua_tank_W_K"] = 400.0
        _save_json(folder / f"case-{index}.json", case)
        with (folder / f"data-{index}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["time_s", *PHYSICAL, *INDICATED])
            for time, temperatures, readings in zip(TIMES, physical, indicated):
                writer.writerow([time, *temperatures, *readings])
        experiments.append({
            "experiment_id": f"experiment-{index}", "role": role,
            "case_file": f"case-{index}.json", "measurements_file": f"data-{index}.csv",
            "data_kind": "synthetic", "source": "Independent seven-state matrix exponential",
            "time_offset_s": 0.0,
        })
    manifest = {
        "schema_version": "dynamic-calibration-study/v1", "study_id": "instrumented-thermal-fit",
        "equipment_id": "synthetic-test-rig",
        "parameters": [{"path": "wall.ua_tank_W_K", "initial": 400.0,
                        "lower": 100.0, "upper": 1600.0}],
        "observables": {name: {"scale_K": 0.05, "max_validation_rmse_K": 0.01,
                               "max_validation_abs_error_K": 0.025} for name in selected},
        "experiments": experiments, "options": {"max_evaluations": 100},
    }
    path = folder / "study.json"
    _save_json(path, manifest)
    return path


def test_thermal_parameter_recovered_from_indicated_channels_with_known_sensor_lag(tmp_path):
    path = _write_study(tmp_path)
    before = {file.name: file.read_bytes() for file in tmp_path.iterdir()}
    physical, indicated = _reference(_case(0))
    assert np.max(np.abs(physical - indicated)) > 10.0
    report = calibrate_study(path)
    assert report["summary"]["status"] == "ok"
    assert report["summary"]["optimization_converged"]
    assert report["summary"]["usable_parameter_estimate"]
    assert report["summary"]["validation_status"] == "criteria_met"
    assert report["parameters"][0]["value"] == pytest.approx(TRUE_UA, rel=2e-5)
    assert report["provenance"]["instrumentation_parameters"] == "declared_fixed_inputs_not_estimated_or_validated"
    assert "no los estima" in report["scope_notes"][0]
    assert set(report["provenance"]["observation_channels"].values()) == {"sensor_indication_including_declared_bias"}
    for experiment in report["experiments"]:
        assert max(metric["rmse"] for metric in experiment["fitted_metrics"].values()) < 1e-4
        assert experiment["fitted_case"]["instrumentation"] == experiment["instrumentation"]
        assert "no estimados ni validados" in experiment["fitted_case"]["provenance"]["notes"]
    assert before == {file.name: file.read_bytes() for file in tmp_path.iterdir()}


def test_reserved_sensor_readings_cannot_change_fitted_thermal_parameters(tmp_path):
    path = _write_study(tmp_path)
    baseline = calibrate_study(path)
    data = tmp_path / "data-1.csv"
    with data.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for name in INDICATED:
            row[name] = str(float(row[name]) + 1.0)
    with data.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    changed = calibrate_study(path)
    assert changed["parameters"] == baseline["parameters"]
    assert changed["summary"]["validation_status"] == "criteria_exceeded"
    assert changed["summary"]["usable_parameter_estimate"] is False


def test_bias_shifts_observation_domain_without_shifting_physical_property_domain(tmp_path):
    path = _write_study(tmp_path, bias=100.0)
    study = load_study(path)
    assert study["experiments"][0]["observations"][0]["values"][INDICATED[0]] > 363.15
    assert study["experiments"][0]["case"]["simulation"]["max_temperature_K"] == 363.15
    data = tmp_path / "data-0.csv"
    contents = data.read_text(encoding="utf-8").splitlines()
    record = contents[1].split(",")
    record[4] = "470.0"
    contents[1] = ",".join(record)
    data.write_text("\n".join(contents) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="including declared sensor bias"):
        load_study(path)


def test_indicated_observation_is_not_implicitly_mapped_to_a_v1_physical_state(tmp_path):
    path = _write_study(tmp_path)
    case_path = tmp_path / "case-0.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["schema_version"] = "dynamic-tank/v1"
    case.pop("instrumentation")
    _save_json(case_path, case)
    with pytest.raises(ValueError, match="require dynamic-tank/v2"):
        load_study(path)


def test_study_cannot_mix_model_versions_even_when_only_physical_channels_are_used(tmp_path):
    path = _write_study(tmp_path, selected=PHYSICAL)
    case_path = tmp_path / "case-1.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["schema_version"] = "dynamic-tank/v1"
    case.pop("instrumentation")
    _save_json(case_path, case)
    with pytest.raises(ValueError, match="same equipment"):
        load_study(path)


@pytest.mark.parametrize("parameter", ["time_constant_s", "bias_K", "opening_rate_per_s"])
def test_study_rejects_changed_fixed_instrumentation(tmp_path, parameter):
    path = _write_study(tmp_path)
    case_path = tmp_path / "case-1.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    if parameter == "opening_rate_per_s":
        case["instrumentation"]["valve_actuator"][parameter] *= 2
    else:
        case["instrumentation"]["temperature_sensors"]["tank"][parameter] *= 2
    _save_json(case_path, case)
    with pytest.raises(ValueError, match="same equipment"):
        load_study(path)


def test_sensor_and_actuator_initial_states_can_change_between_trials(tmp_path):
    path = _write_study(tmp_path)
    case_path = tmp_path / "case-1.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["instrumentation"]["valve_actuator"]["initial_opening"] = 0.25
    _save_json(case_path, case)
    study = load_study(path)
    assert study["experiments"][0]["case"]["instrumentation"] != study["experiments"][1]["case"]["instrumentation"]


def test_sensor_parameters_are_not_silently_added_to_the_fitted_parameter_set(tmp_path):
    path = _write_study(tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["parameters"][0]["path"] = "instrumentation.temperature_sensors.tank.time_constant_s"
    _save_json(path, manifest)
    with pytest.raises(ValueError, match="unsupported thermal parameter"):
        load_study(path)


def test_comparison_preserves_command_steps_but_interpolates_continuous_position_and_flow(tmp_path):
    result = {
        "schema_version": "dynamic-tank/v2", "summary": {"success": True},
        "configuration": {"instrumentation": {"valve_actuator": {"enabled": True}}},
        "series": [{"time_s": 0.0, "valve_command": 0.8, "valve_opening": 0.2,
                    "utility_flow_kg_s": 0.1, "tank_indicated_temperature_K": 300.0},
                   {"time_s": 10.0, "valve_command": 0.1, "valve_opening": 0.6,
                    "utility_flow_kg_s": 0.5, "tank_indicated_temperature_K": 310.0}],
    }
    csv_path = tmp_path / "comparison.csv"
    csv_path.write_text("time_s,valve_command,valve_opening,utility_flow_kg_s,tank_indicated_temperature_K\n"
                        "5,0.8,0.4,0.3,305\n10,0.1,0.6,0.5,310\n", encoding="utf-8")
    report = compare_measurements(result, csv_path)
    assert max(metric["rmse"] for metric in report["metrics"].values()) < 1e-15
    assert report["provenance"]["interpolation"]["valve_command"] == "previous_value_right_continuous"
    assert report["provenance"]["interpolation"]["valve_opening"] == "linear"
    assert report["provenance"]["interpolation"]["utility_flow_kg_s"] == "linear"
    assert report["provenance"]["observation_channels"][INDICATED[0]] == "sensor_indication_including_declared_bias"
    result["schema_version"] = "dynamic-tank/v1"
    with pytest.raises(ValueError, match="require a dynamic-tank/v2"):
        compare_measurements(result, csv_path)


def test_measurement_template_uses_an_explicit_instrumented_opt_in(tmp_path):
    legacy, instrumented = tmp_path / "legacy.csv", tmp_path / "instrumented.csv"
    write_measurement_template(legacy)
    write_measurement_template(instrumented, instrumented=True)
    assert "indicated" not in legacy.read_text(encoding="utf-8")
    assert "valve_command" not in legacy.read_text(encoding="utf-8")
    assert "tank_indicated_temperature_K" in instrumented.read_text(encoding="utf-8")
    assert "valve_command" in instrumented.read_text(encoding="utf-8")
