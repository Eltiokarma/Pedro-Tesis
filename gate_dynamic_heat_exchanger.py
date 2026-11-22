"""Acceptance evidence for time integration, spatial convergence, and conservation."""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys

import numpy as np
import scipy
from scipy.integrate import trapezoid
from scipy.special import gammaincc

from dynamic_heat_exchanger import simulate_heat_exchanger
from dynamic_heat_exchanger_examples import example_cases, matrix_reference, steady_reference, transport_outlet_reference


def _profiles(result):
    return np.asarray([row["hot_temperature_K"]+row["cold_temperature_K"]+row["wall_temperature_K"] for row in result["series"]])


def _evidence(result):
    return {"configuration_sha256": result["metadata"]["config_sha256"],
            "summary": result["summary"], "audit": result["audit"],
            "solver_settings": result["configuration"]["simulation"], "cells": result["configuration"]["cells"]}


def run_checks():
    cases, checks = example_cases(), []
    # Refinement thresholds are physical errors, not counts of solver steps.
    for arrangement in ("co_current", "counter_current"):
        case = copy.deepcopy(cases["msl_geometry_adaptation.json"])
        case.update(cells=6, flow_arrangement=arrangement)
        case["simulation"].update(rtol=1e-6, atol=1e-8, max_step_s=8.)
        variants = {"BDF": case}
        variants["Radau"] = copy.deepcopy(case)
        variants["Radau"]["simulation"]["method"] = "Radau"
        variants["refined"] = copy.deepcopy(case)
        variants["refined"]["simulation"].update(rtol=1e-10, atol=1e-12, max_step_s=.25)
        runs, errors = {}, {}
        for name, config in variants.items():
            result = simulate_heat_exchanger(config)
            reference = matrix_reference(config, [row["time_s"] for row in result["series"]])
            errors[name] = float(np.max(np.abs(_profiles(result)-reference)))
            runs[name] = result
        difference = float(np.max(np.abs(_profiles(runs["BDF"])-_profiles(runs["Radau"])) ))
        conservation = max(r["audit"]["max_energy_residual_relative"] for r in runs.values())
        signals = all(row["hot_flow_kg_s"] == row["cold_flow_kg_s"] == (0. if 60 <= row["time_s"] < 90 else .2)
                      for row in runs["BDF"]["series"])
        passed = (all(r["summary"]["success"] for r in runs.values()) and signals
                  and max(errors.values()) < .005 and errors["refined"] < 5e-6
                  and errors["refined"] < max(1e-8, errors["BDF"]/5)
                  and difference < .005 and conservation < 1e-9)
        checks.append({"name": "time_refinement_"+arrangement, "passed": bool(passed),
                       "reference": "independent affine matrix exponential; fixed mesh",
                       "provenance": case["provenance"], "max_profile_error_K": errors,
                       "BDF_Radau_difference_K": difference, "stop_restart_signals_consistent": signals,
                       "tolerances": {"profile_K": .005, "refined_profile_K": 5e-6, "energy_relative": 1e-9,
                                      "minimum_error_reduction": 5.},
                       "runs": {name: _evidence(r) for name, r in runs.items()}})

    for arrangement in ("co_current", "counter_current"):
        errors, records = [], []
        case = copy.deepcopy(cases[arrangement+".json"])
        case["simulation"].update(duration_s=1500., output_interval_s=100., max_step_s=10., rtol=1e-9, atol=1e-10)
        reference = steady_reference(case)
        for n in (8, 16, 32, 64, 128):
            case["cells"] = n
            result = simulate_heat_exchanger(case)
            error = max(abs(result["series"][-1][key]-reference[key])
                        for key in ("hot_outlet_temperature_K", "cold_outlet_temperature_K"))
            drift = max(abs(result["series"][-1][key]-result["series"][-2][key])
                        for key in ("hot_outlet_temperature_K", "cold_outlet_temperature_K"))
            errors.append(error)
            records.append({**_evidence(result), "outlet_error_K": error, "final_100s_drift_K": drift})
        orders = [math.log(a/b, 2) if min(a, b) > 0 else 0. for a, b in zip(errors, errors[1:])]
        passed = (all(r["summary"]["success"] and r["final_100s_drift_K"] < 1e-5
                      and r["audit"]["max_energy_residual_relative"] < 1e-9 for r in records)
                  and all(a > b for a, b in zip(errors, errors[1:]))
                  and errors[-1] < .2 and .8 < orders[-1] < 1.2)
        checks.append({"name": "space_refinement_"+arrangement, "passed": bool(passed),
                       "reference": "continuum effectiveness-NTU including full wall resistance",
                       "continuum_solution": reference, "observed_orders": orders, "runs": records,
                       "tolerances": {"finest_outlet_K": .2, "final_100s_drift_K": 1e-5,
                                      "last_order_min": .8, "last_order_max": 1.2, "energy_relative": 1e-9}})

    errors, records = [], []
    for n in (4, 16, 64):
        case = copy.deepcopy(cases["transport.json"])
        case["cells"] = n
        result = simulate_heat_exchanger(case)
        times = np.asarray([r["time_s"] for r in result["series"]])
        actual = np.asarray([r["hot_outlet_temperature_K"] for r in result["series"]])
        erlang = transport_outlet_reference(case, times)
        residence = 50.  # 10 kg / 0.2 kg/s, fixed total geometry on every mesh.
        amplitude = 60.
        normalized = (actual-300.)/amplitude
        # At the discontinuity average the two one-sided *errors*, not the
        # ideal step value before taking abs; those operations do not commute.
        delay_error = np.where(times < residence, np.abs(normalized), np.abs(1-normalized))
        delay_error[times == residence] = (np.abs(normalized[times == residence])+np.abs(1-normalized[times == residence]))/2
        error = float(trapezoid(delay_error, x=times)/residence)
        horizon = times[-1]/residence
        exact_l1 = 2*math.exp(n*math.log(n)-n-math.lgamma(n+1))
        exact_l1 -= float(gammaincc(n+1, n*horizon)-horizon*gammaincc(n, n*horizon))
        discrete_error = float(np.max(np.abs(actual-erlang)))
        errors.append(error)
        records.append({**_evidence(result), "normalized_L1_delay_error": error,
                        "analytical_finite_horizon_L1": exact_l1, "L1_quadrature_error": abs(error-exact_l1),
                        "erlang_outlet_error_K": discrete_error})
    checks.append({"name": "transient_residence_space_refinement",
                   "passed": bool(all(r["summary"]["success"] and r["erlang_outlet_error_K"] < 2e-4
                                      and r["L1_quadrature_error"] < 1e-3
                                      and r["audit"]["max_energy_residual_relative"] < 1e-9 for r in records)
                                  and all(a > b for a, b in zip(errors, errors[1:])) and errors[-1] < .11),
                   "reference": "Erlang finite-cell response and continuum plug-flow delay",
                   "interpretation": "Upwind numerical spreading shrinks with mesh; a step front has L1 order about 1/2.",
                   "tolerances": {"erlang_outlet_K": 2e-4, "finest_normalized_L1": .11,
                                  "L1_quadrature": 1e-3, "energy_relative": 1e-9}, "runs": records})
    return {"schema_version": "dynamic-heat-exchanger-verification/v1", "success": all(c["passed"] for c in checks),
            "data_kind": "synthetic_theoretical_verification", "comparison_with_external_simulator_executed": False,
            "complete_published_exchanger_case_reproduced": False,
            "numpy_version": np.__version__, "scipy_version": scipy.__version__, "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        from dynamic_calibration_cli import _write_json, guard_outputs
        if args.out: guard_outputs([args.out], [], overwrite=args.overwrite)
        report = run_checks()
        if args.out: _write_json(args.out, report, overwrite=args.overwrite)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if report["success"] else 1
    except (ValueError, OSError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
