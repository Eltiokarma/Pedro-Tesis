"""Headless v3 workflows and causal comparison across service interruptions."""
import csv
import json

import pytest

import dynamic_cli
from dynamic_hydraulics import solve_circuit
from dynamic_measurements import compare_measurements, write_measurement_template
from dynamic_study import load_study
from dynamic_tank import default_thermal_loop_case, simulate_dynamic_tank


def short_case():
    case = default_thermal_loop_case()
    case["controller"]["enabled"] = False
    case["simulation"].update(duration_s=20.0, output_interval_s=10.0)
    case["instrumentation"]["valve_actuator"]["enabled"] = False
    case["events"] = [{"time_s": 10.0, "changes": {
        "pump_speed_fraction": 0.0, "heater_power_request_W": 0.0,
    }}]
    return case


def save_csv(tmp_path, names, rows):
    path = tmp_path / "reference.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time_s", *names])
        writer.writerows(rows)
    return path


def test_cli_creates_explicit_v3_and_runs_headless_exports(tmp_path):
    case_path, template = tmp_path / "loop.json", tmp_path / "template.csv"
    assert dynamic_cli.main(["--thermal-loop", "--write-example", str(case_path),
                             "--measurement-template", str(template)]) == 0
    assert json.loads(case_path.read_text(encoding="utf-8"))["schema_version"] == "dynamic-tank/v3"
    header = template.read_text(encoding="utf-8")
    assert "utility_reservoir_temperature_K" in header
    assert "tank_indicated_temperature_K" in header
    assert len(header.splitlines()) == 1
    case_path.write_text(json.dumps(short_case()), encoding="utf-8")
    result_path, trajectory_path = tmp_path / "run.json", tmp_path / "run.csv"
    assert dynamic_cli.main([str(case_path), "--out", str(result_path),
                             "--csv", str(trajectory_path)]) == 0
    run = json.loads(result_path.read_text(encoding="utf-8"))
    assert run["summary"]["success"]
    assert run["series"][-1]["heater_applied_power_W"] == 0
    assert run["series"][-1]["utility_flow_kg_s"] == 0
    assert "utility_reservoir_temperature_K" in trajectory_path.read_text(encoding="utf-8").splitlines()[0]


def test_cli_does_not_silently_replace_a_user_case_with_v3(tmp_path, capsys):
    path, output = tmp_path / "case.json", tmp_path / "output.json"
    path.write_text(json.dumps(short_case()), encoding="utf-8")
    original = path.read_bytes()
    assert dynamic_cli.main([str(path), "--thermal-loop", "--out", str(output)]) == 2
    assert "--thermal-loop" in capsys.readouterr().err
    assert not output.exists()
    assert path.read_bytes() == original


def test_template_opt_in_preserves_v1_and_v2_headers(tmp_path):
    v1, v2, v3 = [tmp_path / name for name in ("v1.csv", "v2.csv", "v3.csv")]
    write_measurement_template(v1)
    write_measurement_template(v2, instrumented=True)
    write_measurement_template(v3, thermal_loop=True)
    legacy = v1.read_text(encoding="utf-8").strip().split(",")
    assert legacy == ["time_s", "tank_temperature_K", "jacket_temperature_K", "wall_temperature_K",
                      "mass_kg", "volume_m3", "tracer_mass_fraction", "valve_opening", "utility_flow_kg_s"]
    assert v2.read_text(encoding="utf-8").strip().split(",") == [
        *legacy, "tank_indicated_temperature_K", "wall_indicated_temperature_K",
        "jacket_indicated_temperature_K", "valve_command",
    ]
    assert "heater_heat_W" in v3.read_text(encoding="utf-8")
    assert "heater_saturated" not in v3.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="thermal_loop must be a boolean"):
        write_measurement_template(v3, thermal_loop=1)


def test_pump_stop_and_power_cut_do_not_ramp_backwards_in_csv_comparison(tmp_path):
    case = short_case()
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    initial = result["series"][0]
    names = ["utility_flow_kg_s", "pump_speed_fraction", "heater_power_request_W",
             "heater_applied_power_W", "heater_heat_W"]
    path = save_csv(tmp_path, names, [
        [5.0, *[initial[name] for name in names]],
        [10.0, 0, 0, 0, 0, 0],
        [15.0, 0, 0, 0, 0, 0],
    ])
    report = compare_measurements(result, path)
    assert max(v["rmse"] for v in report["metrics"].values()) < 1e-13
    methods = report["provenance"]["interpolation"]
    assert methods["heater_heat_W"] == "previous_value_right_continuous"
    assert methods["utility_flow_kg_s"] == "hydraulic_closure_from_valve_position_and_held_pump_speed"


def test_v3_uses_interpolated_position_and_held_speed_for_nonlinear_flow(tmp_path):
    case = short_case()
    case["instrumentation"]["valve_actuator"]["enabled"] = True
    pump = dict(case["pump"], speed_fraction=1.0)
    expected_flow = solve_circuit(pump, case["circuit"], .4,
                                  case["jacket"]["density_kg_m3"])["mass_flow_kg_s"]
    result = {
        "schema_version": "dynamic-tank/v3", "configuration": case,
        "summary": {"success": True},
        "series": [
            {"time_s": 0.0, "valve_opening": .2, "pump_speed_fraction": 1.0,
             "utility_flow_kg_s": .1, "tank_indicated_temperature_K": 300.0},
            {"time_s": 10.0, "valve_opening": .6, "pump_speed_fraction": 0.0,
             "utility_flow_kg_s": 0.0, "tank_indicated_temperature_K": 310.0},
        ],
    }
    path = save_csv(tmp_path, ["utility_flow_kg_s", "tank_indicated_temperature_K"],
                    [[5.0, expected_flow, 305.0], [10.0, 0.0, 310.0]])
    report = compare_measurements(result, path)
    assert report["metrics"]["utility_flow_kg_s"]["rmse"] < 1e-13
    assert report["metrics"]["tank_indicated_temperature_K"]["rmse"] == 0


def test_incomplete_v3_event_trajectory_cannot_hide_a_pump_stop(tmp_path):
    result = simulate_dynamic_tank(short_case())
    result["series"] = [result["series"][0], result["series"][-1]]
    path = save_csv(tmp_path, ["utility_flow_kg_s"], [[15, 0]])
    with pytest.raises(ValueError, match="record every input event"):
        compare_measurements(result, path)


def test_loop_temperature_channels_are_continuous_and_v3_only(tmp_path):
    case = short_case()
    names = ["utility_reservoir_temperature_K", "utility_supply_temperature_K",
             "utility_return_temperature_K"]
    result = {"schema_version": "dynamic-tank/v3", "configuration": case,
              "summary": {"success": True},
              "series": [{"time_s": t, **dict.fromkeys(names, temp)}
                         for t, temp in ((0, 300), (10, 310))]}
    path = save_csv(tmp_path, names, [[5, 305, 305, 305]])
    report = compare_measurements(result, path)
    assert all(v["rmse"] == 0 for v in report["metrics"].values())
    result["schema_version"] = "dynamic-tank/v2"
    with pytest.raises(ValueError, match="require a dynamic-tank/v3"):
        compare_measurements(result, path)


def test_v3_calibration_is_rejected_before_equipment_matching(tmp_path):
    case_path = tmp_path / "loop.json"
    case_path.write_text(json.dumps(short_case()), encoding="utf-8")
    for name in ("fit", "holdout"):
        (tmp_path / f"{name}.csv").write_text("time_s,tank_temperature_K\n0,298.15\n10,299\n",
                                             encoding="utf-8")
    manifest = {
        "schema_version": "dynamic-calibration-study/v1", "study_id": "unsupported-loop-fit",
        "equipment_id": "loop", "parameters": [{"path": "wall.ua_tank_W_K", "initial": 800,
                                                   "lower": 100, "upper": 1600}],
        "observables": {"tank_temperature_K": {"scale_K": .1,
                         "max_validation_rmse_K": .5, "max_validation_abs_error_K": 1}},
        "experiments": [{"experiment_id": name, "role": role, "case_file": "loop.json",
                         "measurements_file": f"{name}.csv", "data_kind": "synthetic",
                         "source": "Theoretical fixture", "time_offset_s": 0}
                        for name, role in (("fit", "calibration"), ("holdout", "validation"))],
        "options": {"max_evaluations": 20},
    }
    manifest_path = tmp_path / "study.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="calibration of dynamic-tank/v3.*not supported"):
        load_study(manifest_path)
