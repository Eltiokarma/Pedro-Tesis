"""Numerical verification of a finite thermal loop, not experimental validation."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import platform

import numpy as np
from scipy.integrate import solve_ivp, trapezoid

from dynamic_calibration_cli import _write_json, guard_outputs
from dynamic_tank import simulate_dynamic_tank
from dynamic_thermal_loop import thermal_reservoir_rates
from thermal_loop_examples import (
    ENERGYPLUS_PARAMETERS, ENERGYPLUS_TEST_URL, TEMPERATURES, reference_temperatures,
    reference_steady_temperatures,
)


FOLDER = Path(__file__).resolve().parent / "data/thermal_loop_examples"


def _conserved(result):
    return result["summary"]["success"] and all(result["audit"][key] < 1e-8 for key in (
        "max_mass_residual_relative", "max_tracer_residual_relative", "max_energy_residual_relative"))


def published_component_benchmark():
    """Exercise the production reservoir balance, with a prescribed cold return.

    This tests a component boundary condition, NOT the closed-loop engine.
    Integrate temperature and its integral together to avoid quadrature error.
    """
    p = ENERGYPLUS_PARAMETERS
    capacity = p["mass_kg"] * p["cp_J_kg_K"]

    def rhs(_time, state):
        rate = thermal_reservoir_rates(mass_flow_kg_s=p["mass_flow_kg_s"],
            cp_J_kg_K=p["cp_J_kg_K"], reservoir_temperature_K=state[0],
            return_temperature_K=p["return_temperature_K"], ua_ambient_W_K=p["ua_ambient_W_K"],
            ambient_temperature_K=p["ambient_temperature_K"], heater_heat_W=0.0, pump_heat_W=0.0)
        return [rate["reservoir_energy_rate_W"] / capacity, state[0] - 273.15]

    duration = p["duration_s"]
    solution = solve_ivp(rhs, [0.0, duration], [p["initial_temperature_K"], 0.0],
                         method="Radau", rtol=1e-10, atol=1e-10)
    # Closed-form solution assembled independently of the production balance.
    conductance = p["ua_ambient_W_K"] + p["mass_flow_kg_s"] * p["cp_J_kg_K"]
    equilibrium = (p["ua_ambient_W_K"] * p["ambient_temperature_K"]
                   + p["mass_flow_kg_s"] * p["cp_J_kg_K"] * p["return_temperature_K"]) / conductance
    tau = capacity / conductance
    expected = equilibrium + (p["initial_temperature_K"]-equilibrium) * math.exp(-duration/tau)
    expected_integral = (equilibrium-273.15) * duration + (
        p["initial_temperature_K"]-equilibrium) * tau * -math.expm1(-duration/tau)
    actual_integral = float(solution.y[1, -1])
    error = abs(float(solution.y[0, -1])-expected)
    return {"check": "EnergyPlus_published_cold_mixing_component", "passed": bool(solution.success
            and error < 1e-6 and abs(actual_integral-expected_integral) < 1e-4
            and abs(actual_integral-p["published_integral_C_s"]) <= p["published_tolerance_C_s"]),
        "scope": "production_reservoir_balance_with_prescribed_return_not_full_closed_loop",
        "source": ENERGYPLUS_TEST_URL, "final_temperature_C": float(solution.y[0, -1]-273.15),
        "analytic_final_temperature_C": expected-273.15, "max_final_temperature_error_K": error,
        "temperature_tolerance_K": 1e-6, "integral_C_s": actual_integral,
        "analytic_integral_C_s": expected_integral, "published_integral_C_s": p["published_integral_C_s"],
        "published_tolerance_C_s": p["published_tolerance_C_s"], "analytic_integral_tolerance_C_s": 1e-4}


def run_gate():
    checks = [published_component_benchmark()]
    heating = json.loads((FOLDER / "energyplus_adiabatic.json").read_text(encoding="utf-8"))
    response = simulate_dynamic_tank(heating)
    rows = response["series"]
    duration = heating["simulation"]["duration_s"]
    capacity = heating["utility_loop"]["mass_kg"] * heating["jacket"]["cp_J_kg_K"]
    start = heating["utility_loop"]["initial_temperature_K"]
    slope = 1000.0 / capacity
    error = max(abs(row["utility_reservoir_temperature_K"]-(start+slope*row["time_s"])) for row in rows)
    integral = float(trapezoid([row["utility_reservoir_temperature_K"]-273.15 for row in rows],
                                  [row["time_s"] for row in rows]))
    exact_integral = (start-273.15)*duration + 0.5*slope*duration**2
    checks.append({"check": "EnergyPlus_published_1000W_full_engine", "passed": bool(_conserved(response)
        and error < 1e-6 and abs(integral-exact_integral) < 1e-4
        and abs(integral-ENERGYPLUS_PARAMETERS["published_adiabatic_1000W_integral_C_s"]) <= 0.1),
        "scope": "full_engine_v3_decoupled_reservoir", "source": ENERGYPLUS_TEST_URL,
        "max_temperature_error_K": error, "temperature_tolerance_K": 1e-6,
        "integral_C_s": integral, "analytic_integral_C_s": exact_integral,
        "published_integral_C_s": ENERGYPLUS_PARAMETERS["published_adiabatic_1000W_integral_C_s"],
        "published_tolerance_C_s": 0.1, "analytic_integral_tolerance_C_s": 1e-4,
        "audit": response["audit"], "config_sha256": response["metadata"]["config_sha256"]})

    coupled = json.loads((FOLDER / "coupled_disturbances.json").read_text(encoding="utf-8"))
    baseline = simulate_dynamic_tank(coupled)
    times = [row["time_s"] for row in baseline["series"]]
    oracle = reference_temperatures(coupled, times)
    errors = np.abs(np.array([[row[name] for name in TEMPERATURES] for row in baseline["series"]])-oracle)
    checks.append({"check": "four_inventory_independent_matrix_exponential", "passed": bool(
        _conserved(baseline) and errors.max() < 2e-4),
        "scope": "own_coupled_theoretical_case_not_Modelica_output_reproduction",
        "max_temperature_error_K": float(errors.max()), "temperature_tolerance_K": 2e-4,
        "per_inventory_max_error_K": dict(zip(TEMPERATURES, map(float, errors.max(axis=0)))),
        "audit": baseline["audit"], "config_sha256": baseline["metadata"]["config_sha256"]})

    outage_rows = [row for row in baseline["series"] if 600 < row["time_s"] < 1300]
    stopped_rows = [row for row in baseline["series"] if 1000 < row["time_s"] < 1300]
    resumed_rows = [row for row in baseline["series"] if row["time_s"] > 1300]
    no_heat = all(row["heater_heat_W"] == 0 and row["heater_applied_power_W"] == 0 for row in outage_rows)
    no_flow = all(row["utility_flow_kg_s"] == 0 and row["pump_heat_to_loop_W"] == 0 for row in stopped_rows)
    restored = all(row["utility_flow_kg_s"] > 0 and row["heater_heat_W"] > 0 for row in resumed_rows)
    checks.append({"check": "power_outage_pump_stop_and_restart", "passed": bool(_conserved(baseline)
        and outage_rows and stopped_rows and resumed_rows and no_heat and no_flow and restored),
        "power_outage_interval_s": [600, 1300], "pump_stopped_interval_s": [1000, 1300],
        "zero_heater_heat_during_outage": no_heat, "zero_flow_and_pump_heat_when_stopped": no_flow,
        "flow_and_heater_restored": restored})

    radau_case = copy.deepcopy(coupled)
    radau_case["simulation"].update(method="Radau", max_step_s=2.0, rtol=1e-10, atol=1e-11)
    radau = simulate_dynamic_tank(radau_case)
    refined_case = copy.deepcopy(coupled)
    refined_case["simulation"].update(max_step_s=2.0, rtol=1e-10, atol=1e-11)
    refined = simulate_dynamic_tank(refined_case)
    reference_rows = {row["time_s"]: row for row in radau["series"]}
    refined_rows = {row["time_s"]: row for row in refined["series"]}
    methods_error = max(abs(row[name]-reference_rows[row["time_s"]][name])
                        for row in baseline["series"] for name in TEMPERATURES)
    refined_error = max(abs(refined_rows[t][name]-oracle[i, j])
                        for i, t in enumerate(times) for j, name in enumerate(TEMPERATURES))
    checks.append({"check": "BDF_Radau_and_refinement", "passed": bool(_conserved(radau) and _conserved(refined)
        and methods_error < 2e-4 and refined_error < 2e-5 and refined_error <= max(float(errors.max()), 1e-8)),
        "BDF_Radau_max_difference_K": methods_error, "method_tolerance_K": 2e-4,
        "baseline_oracle_max_error_K": float(errors.max()), "refined_oracle_max_error_K": refined_error,
        "refined_tolerance_K": 2e-5, "radau_audit": radau["audit"], "refined_audit": refined["audit"]})

    limited = json.loads((FOLDER / "insufficient_power.json").read_text(encoding="utf-8"))
    limited_result = simulate_dynamic_tank(limited)
    inventory = limited["utility_loop"]
    equilibrium = limited["inputs"]["ambient_temperature_K"] + inventory["heater_max_power_W"] / inventory["ua_ambient_W_K"]
    tau = inventory["mass_kg"] * limited["jacket"]["cp_J_kg_K"] / inventory["ua_ambient_W_K"]
    limited_rows = limited_result["series"]
    limited_error = max(abs(row["utility_reservoir_temperature_K"] - (equilibrium +
        (inventory["initial_temperature_K"]-equilibrium) * math.exp(-row["time_s"]/tau))) for row in limited_rows)
    bounded = all(row["heater_applied_power_W"] == inventory["heater_max_power_W"]
                  and row["heater_saturated"] and row["utility_reservoir_temperature_K"] <= equilibrium+1e-6
                  for row in limited_rows)
    checks.append({"check": "insufficient_power_analytic_equilibrium", "passed": bool(_conserved(limited_result)
        and limited_error < 2e-4 and bounded and equilibrium < limited["inputs"]["temperature_setpoint_K"]),
        "scope": "own_theoretical_case", "max_temperature_error_K": limited_error, "tolerance_K": 2e-4,
        "equilibrium_temperature_K": equilibrium, "illustrative_reservoir_target_K": 323.15,
        "controller_active": False,
        "requested_electric_power_W": limited["inputs"]["heater_power_request_W"],
        "maximum_electric_power_W": inventory["heater_max_power_W"], "audit": limited_result["audit"]})

    controlled_case = json.loads((FOLDER / "coupled_capacity_limit.json").read_text(encoding="utf-8"))
    controlled = simulate_dynamic_tank(controlled_case)
    manual_reference = copy.deepcopy(controlled_case)
    manual_reference["controller"]["enabled"] = False
    manual_reference["inputs"]["valve_opening"] = 1.0
    controlled_rows = controlled["series"]
    controlled_times = [row["time_s"] for row in controlled_rows]
    expected_controlled = reference_temperatures(manual_reference, controlled_times)
    steady = reference_steady_temperatures(manual_reference)
    controlled_error = float(np.abs(np.array([[row[name] for name in TEMPERATURES]
                                for row in controlled_rows])-expected_controlled).max())
    steady_error = max(abs(controlled_rows[-1][name]-steady[j]) for j, name in enumerate(TEMPERATURES))
    physical_limit = all(row["valve_command"] == 1.0 and row["valve_opening"] == 1.0
        and row["heater_saturated"] and row["heater_applied_power_W"] == 1000.0 for row in controlled_rows)
    setpoint = controlled_case["inputs"]["temperature_setpoint_K"]
    checks.append({"check": "coupled_PI_saturation_and_unreachable_process_setpoint",
        "passed": bool(_conserved(controlled) and physical_limit and controlled_error < 2e-4
                       and steady_error < 0.01 and steady[0] < setpoint-1.0),
        "scope": "own_coupled_theoretical_case_with_active_process_PI",
        "max_trajectory_error_K": controlled_error, "trajectory_tolerance_K": 2e-4,
        "final_steady_state_error_K": float(steady_error), "steady_state_tolerance_K": 0.01,
        "steady_temperatures_K": dict(zip(TEMPERATURES, map(float, steady))),
        "process_setpoint_K": setpoint, "process_final_temperature_K": controlled_rows[-1]["tank_temperature_K"],
        "fully_open_valve_and_heater_limit": physical_limit, "audit": controlled["audit"],
        "config_sha256": controlled["metadata"]["config_sha256"]})
    return {"success": all(check["passed"] for check in checks), "python": platform.python_version(),
        "scope": "published_component_tests_and_own_coupled_theoretical_verification_no_experimental_validation",
        "model_version": baseline["metadata"]["model_version"], "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.out:
        guard_outputs([args.out], list(FOLDER.glob("*.json")), overwrite=args.overwrite)
    result = run_gate()
    if args.out:
        _write_json(args.out, result, overwrite=args.overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
