"""Numerical acceptance of synthetic instrumentation; never plant validation."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import platform

from dynamic_calibration import calibrate_study
from dynamic_calibration_cli import _write_json, guard_outputs
from dynamic_tank import default_instrumented_case, simulate_dynamic_tank
from instrumentation_example import INDICATED, SECTIONS, reference_indicated_temperatures


def _conserved(result):
    return result["summary"]["success"] and all(result["audit"][name] < 1e-9 for name in (
        "max_mass_residual_relative", "max_tracer_residual_relative", "max_energy_residual_relative"))


def _reference_position(initial, command, elapsed, actuator):
    # Independent closed-form oracle, no import of the production actuator.
    delta = command - initial
    sign = 1.0 if delta >= 0 else -1.0
    rate = actuator["opening_rate_per_s"] if delta >= 0 else actuator["closing_rate_per_s"]
    tau = actuator["time_constant_s"]
    switch = max(0.0, abs(delta) / rate - tau)
    if elapsed <= switch:
        return initial + sign * rate * elapsed
    residual = min(abs(delta), rate * tau)
    return command - sign * residual * math.exp(-(elapsed - switch) / tau)


def run_gate():
    folder = Path(__file__).resolve().parent / "data/instrumentation_examples"
    checks = []
    manual = json.loads((folder / "valve_steps.json").read_text(encoding="utf-8"))
    result = simulate_dynamic_tank(manual)
    actuator = manual["instrumentation"]["valve_actuator"]
    actual, command, last = actuator["initial_opening"], manual["inputs"]["valve_opening"], 0.0
    events = iter(manual["events"])
    event = next(events, None)
    error = 0.0
    for row in result["series"]:
        time = row["time_s"]
        while event is not None and event["time_s"] <= time:
            actual = _reference_position(actual, command, event["time_s"] - last, actuator)
            last, command = event["time_s"], event["changes"]["valve_opening"]
            event = next(events, None)
        error = max(error, abs(row["valve_opening"] - _reference_position(actual, command, time - last, actuator)))
    checks.append({"check": "valve_piecewise_analytic_response", "passed": _conserved(result) and error < 1e-10,
                   "max_position_difference": error, "tolerance": 1e-10, "audit": result["audit"],
                   "config_sha256": result["metadata"]["config_sha256"]})

    closing_case = default_instrumented_case()
    closing_case["controller"]["enabled"] = False
    closing_case["inputs"]["valve_opening"] = 0.0
    closing_case["simulation"].update(duration_s=2000.0, output_interval_s=10.0)
    closing = simulate_dynamic_tank(closing_case)
    flows = [row["utility_flow_kg_s"] for row in closing["series"]]
    checks.append({"check": "prolonged_closure_without_resistance_overflow",
                   "passed": _conserved(closing) and len(flows) > 1 and flows[0] > 0
                             and all(0 <= after <= before for before, after in zip(flows, flows[1:])),
                   "final_time_s": closing["summary"]["final_time_s"],
                   "final_flow_kg_s": flows[-1], "audit": closing["audit"],
                   "config_sha256": closing["metadata"]["config_sha256"]})

    heating = json.loads((folder / "instrumented_heating.json").read_text(encoding="utf-8"))
    bdf = simulate_dynamic_tank(heating)
    radau_case = copy.deepcopy(heating)
    radau_case["simulation"].update(method="Radau", rtol=1e-9, atol=1e-10, max_step_s=1.0)
    radau = simulate_dynamic_tank(radau_case)
    reference = {row["time_s"]: row for row in radau["series"]}
    temperature_difference = max(abs(row[name] - reference[row["time_s"]][name])
        for row in bdf["series"] for name in (*INDICATED, *(section + "_temperature_K" for section in SECTIONS)))
    position_difference = max(abs(row["valve_opening"] - reference[row["time_s"]]["valve_opening"])
                              for row in bdf["series"])
    checks.append({"check": "closed_loop_BDF_Radau", "passed": bool(_conserved(bdf) and _conserved(radau)
                   and temperature_difference < 0.02 and position_difference < 0.002),
                   "max_temperature_difference_K": temperature_difference, "temperature_tolerance_K": 0.02,
                   "max_position_difference": position_difference, "position_tolerance": 0.002,
                   "audit": bdf["audit"], "config_sha256": bdf["metadata"]["config_sha256"],
                   "reference_config_sha256": radau["metadata"]["config_sha256"]})

    case = json.loads((folder / "calibration/cal_hot.json").read_text(encoding="utf-8"))
    times = [0.0, 3.0, 7.0, 19.0, 65.0, 150.0, 200.0, 260.0, 450.0, 600.0]
    expected = reference_indicated_temperatures(case, times)
    response = simulate_dynamic_tank(case, sample_times_s=times)
    rows = {row["time_s"]: row for row in response["series"]}
    sensor_error = max(abs(rows[t][name] - expected[index, column])
        for index, t in enumerate(times) for column, name in enumerate(INDICATED))
    checks.append({"check": "six_temperature_matrix_exponential", "passed": bool(_conserved(response) and sensor_error < 0.002),
                   "max_indicated_temperature_difference_K": float(sensor_error), "tolerance_K": 0.002})

    ideal = default_instrumented_case()
    ideal["controller"]["enabled"] = False
    ideal["simulation"].update(duration_s=300.0, rtol=1e-9, atol=1e-10)
    for sensor in ideal["instrumentation"]["temperature_sensors"].values():
        sensor.update(time_constant_s=0.0, bias_K=0.0)
    ideal["instrumentation"]["valve_actuator"]["enabled"] = False
    legacy = copy.deepcopy(ideal)
    legacy.pop("instrumentation")
    legacy["schema_version"] = "dynamic-tank/v1"
    legacy_result, ideal_result = simulate_dynamic_tank(legacy), simulate_dynamic_tank(ideal)
    old_rows = {row["time_s"]: row for row in legacy_result["series"]}
    ideal_rows = {row["time_s"]: row for row in ideal_result["series"]}
    same_times = set(old_rows) == set(ideal_rows)
    physical_error = (max(abs(old_rows[t][name] - ideal_rows[t][name]) for t in old_rows
                         for name in ("tank_temperature_K", "wall_temperature_K", "jacket_temperature_K"))
                      if same_times else None)
    checks.append({"check": "ideal_instrumentation_matches_legacy_physics",
                   "passed": _conserved(legacy_result) and _conserved(ideal_result) and same_times and physical_error < 0.0001,
                   "max_temperature_difference_K": physical_error, "tolerance_K": 0.0001})

    calibrated = calibrate_study(folder / "calibration/study.json")
    truth = json.loads((folder / "calibration/reference.json").read_text(encoding="utf-8"))["true_parameters"]
    recovered = [{"path": item["path"], "value": item["value"], "reference": truth[item["path"]],
                  "relative_error": abs(item["value"] - truth[item["path"]]) / truth[item["path"]]}
                 for item in calibrated["parameters"]]
    summary = calibrated["summary"]
    checks.append({"check": "calibration_of_indicated_channels_with_fixed_instruments",
        "passed": summary["status"] == "ok" and calibrated["validation_state"] == "synthetic_calibration_only"
                  and summary["optimization_converged"] and summary["usable_parameter_estimate"]
                  and summary["validation_status"] == "criteria_met" and len(recovered) == 2
                  and all(item["relative_error"] < 0.03 for item in recovered)
                  and len(calibrated["experiments"]) == 3
                  and all(all(item["balance_audit"][key] < 1e-9 for key in (
                      "max_mass_residual_relative", "max_tracer_residual_relative", "max_energy_residual_relative"))
                      for item in calibrated["experiments"]),
        "parameter_relative_error_max": 0.03, "parameter_recovery": recovered,
        "summary": summary, "diagnostics": calibrated["diagnostics"], "provenance": calibrated["provenance"],
        "heldout_metrics": {item["experiment_id"]: item["fitted_metrics"] for item in calibrated["experiments"]
                            if item["role"] == "validation"}})
    return {"success": all(check["passed"] for check in checks), "python": platform.python_version(),
            "scope": "synthetic_numerical_verification_no_instrument_characterization_or_plant_validation",
            "model_version": bdf["metadata"]["model_version"], "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    folder = Path(__file__).resolve().parent / "data/instrumentation_examples"
    if args.out:
        guard_outputs([args.out], list(folder.rglob("*.json")) + list(folder.rglob("*.csv")), overwrite=args.overwrite)
    result = run_gate()
    if args.out:
        _write_json(args.out, result, overwrite=args.overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
