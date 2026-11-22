"""Acceptance evidence for simultaneously coupled tanks and distributed exchangers."""
from __future__ import annotations

import argparse
import copy
import json
import sys

import numpy as np
from scipy.special import gammainc

from dynamic_network import simulate_dynamic_network
from dynamic_network_component_examples import example_cases, recirculation_reference


def run_checks():
    checks = []
    for orientation in ("co_current", "counter_current"):
        case = example_cases()["coupled_recirculation.json"]
        case["heat_exchangers"][0]["flow_arrangement"] = orientation
        runs = []
        for name in ("BDF", "Radau", "refined"):
            candidate = copy.deepcopy(case)
            if name == "Radau": candidate["simulation"]["method"] = "Radau"
            if name == "refined": candidate["simulation"].update(rtol=1e-10, atol=1e-12, max_step_s=1.)
            result = simulate_dynamic_network(candidate)
            times = [p["time_s"] for p in result["series"]]
            profiles = np.array([[p["nodes"]["HotTank"]["temperature_K"], p["nodes"]["ColdTank"]["temperature_K"]]
                +sum([p["heat_exchangers"]["HX1"][s+"_temperature_K"] for s in ("hot", "cold", "wall")], []) for p in result["series"]])
            error = float(np.max(np.abs(profiles-recirculation_reference(case, times))))
            runs.append({"method": name, "profile_error_K": error, "summary": result["summary"], "audit": result["audit"],
                         "configuration_sha256": result["metadata"]["config_sha256"], "solver_settings": candidate["simulation"]})
        passed = (all(r["summary"]["success"] and r["profile_error_K"] < 2e-4
                      and max(r["audit"]["max_relative_residual"].values()) < 1e-9 for r in runs)
                  and runs[-1]["profile_error_K"] < max(1e-8, runs[0]["profile_error_K"]/5))
        checks.append({"name": "closed_coupling_"+orientation, "passed": bool(passed),
                       "reference": "independent matrix exponential of both tanks, both fluids and solid wall",
                       "tolerances": {"profile_K": 2e-4, "conservation_relative": 1e-9, "refinement_reduction": 5.}, "runs": runs})
    case = example_cases()["coupled_feed.json"]
    case["nodes"][0]["initial_mass_kg"] = 2.5
    case["heat_exchangers"][0]["heat_transfer"].update(hot_h_W_m2_K=0., cold_h_W_m2_K=0.)
    result = simulate_dynamic_network(case)
    times = np.array([p["time_s"] for p in result["series"]])
    exact = gammainc(5, times/12.5)
    tracer_error = float(np.max(np.abs([p["nodes"]["HotTank"]["tracer_mass_fraction"] for p in result["series"]]-exact)))
    temperature_error = float(np.max(np.abs([p["nodes"]["HotTank"]["temperature_K"] for p in result["series"]]-(300.+60.*exact))))
    checks.append({"name": "residence_through_exchanger_and_tank", "passed": bool(result["summary"]["success"]
                    and tracer_error < 3e-6 and temperature_error < 2e-4 and max(result["audit"]["max_relative_residual"].values()) < 1e-9),
                   "reference": "Erlang step response, five equal liquid inventories in series",
                   "temperature_error_K": temperature_error, "tracer_error": tracer_error,
                   "audit": result["audit"], "configuration_sha256": result["metadata"]["config_sha256"],
                   "tolerances": {"temperature_K": 2e-4, "tracer_fraction": 3e-6, "conservation_relative": 1e-9}})
    return {"schema_version": "dynamic-network-components-verification/v1", "success": all(c["passed"] for c in checks),
            "data_kind": "synthetic_theoretical_verification", "comparison_with_external_simulator_executed": False,
            "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out"); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        from dynamic_calibration_cli import guard_outputs, _write_json
        if args.out: guard_outputs([args.out], [], overwrite=args.overwrite)
        report = run_checks()
        if args.out: _write_json(args.out, report, overwrite=args.overwrite)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if report["success"] else 1
    except (ValueError, OSError, ImportError) as exc:
        print(str(exc), file=sys.stderr); return 2


if __name__ == "__main__": sys.exit(main())
