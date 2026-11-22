"""Independent acceptance checks for directed dynamic networks, with evidence."""
from __future__ import annotations

import argparse
import copy
import json
import sys

import numpy as np
from scipy.integrate import simpson

from dynamic_network import simulate_dynamic_network
from dynamic_network_examples import ENERGYPLUS_URL, energyplus_integral_C_s, example_cases, reference_trajectories


def _errors(result):
    times = [row["time_s"] for row in result["series"]]
    reference = reference_trajectories(result["configuration"]["case_id"], times)
    errors = {"temperature_K": 0.0, "tracer_mass_fraction": 0.0}
    for identifier, values in reference.items():
        for quantity, expected in values.items():
            actual = np.array([row["nodes"][identifier][quantity] for row in result["series"]])
            errors[quantity] = max(errors[quantity], float(np.max(np.abs(actual - expected))))
    return errors


def run_checks():
    checks = []
    for filename, case in example_cases().items():
        bdf = simulate_dynamic_network(case)
        radau_case = copy.deepcopy(case)
        radau_case["simulation"]["method"] = "Radau"
        radau = simulate_dynamic_network(radau_case)
        refined_case = copy.deepcopy(case)
        refined_case["simulation"].update(rtol=1e-10, atol=1e-12, max_step_s=1.0)
        refined = simulate_dynamic_network(refined_case)
        errors = {name: _errors(result) for name, result in (("BDF", bdf), ("Radau", radau), ("refined", refined))}
        succeeded = all(result["summary"]["success"] for result in (bdf, radau, refined))
        conservation = max(max(result["audit"]["max_relative_residual"].values()) for result in (bdf, radau, refined))
        method_difference = max(abs(a["nodes"][identifier]["temperature_K"] - b["nodes"][identifier]["temperature_K"])
                                for a, b in zip(bdf["series"], radau["series"])
                                for identifier in a["nodes"])
        time_grids_match = [r["time_s"] for r in bdf["series"]] == [r["time_s"] for r in radau["series"]]
        passed = (succeeded and time_grids_match and conservation < 1e-9 and method_difference < 2e-4
                  and all(e["temperature_K"] < 2e-4 and e["tracer_mass_fraction"] < 5e-6 for e in errors.values())
                  and errors["refined"]["temperature_K"] < max(1e-9, errors["BDF"]["temperature_K"]))
        detail = {"name": filename, "passed": bool(passed), "errors": errors,
                  "max_conservation_relative": conservation, "BDF_Radau_max_temperature_difference_K": method_difference,
                  "time_grids_match": time_grids_match, "configuration_sha256": bdf["metadata"]["config_sha256"],
                  "provenance": case["provenance"], "summary": bdf["summary"], "audit": bdf["audit"],
                  "tolerances": {"temperature_K": 2e-4, "tracer_fraction": 5e-6, "conservation_relative": 1e-9}}
        if case["case_id"] == "energyplus-mixed-tank":
            temperatures_C = [row["nodes"]["tank"]["temperature_K"] - 273.15 for row in refined["series"]]
            numerical = float(simpson(temperatures_C, x=[row["time_s"] for row in refined["series"]]))
            analytic = energyplus_integral_C_s()
            detail["published_reference"] = {"source": ENERGYPLUS_URL, "published_integral_C_s": 14716.6,
                                             "published_tolerance_C_s": .1, "numerical_integral_C_s": numerical,
                                             "analytical_integral_C_s": analytic, "independent_integral_tolerance_C_s": 1e-4}
            detail["passed"] = bool(passed and abs(numerical - 14716.6) < .1 and abs(numerical - analytic) < 1e-4)
        if case["case_id"] == "analytical-recirculation":
            signals = all(all(port["mass_flow_kg_s"] == (0.0 if 100 <= row["time_s"] < 200 else 1.0)
                              for port in row["ports"]) for row in bdf["series"])
            detail["stop_restart_signals_consistent"] = signals
            detail["passed"] = bool(passed and signals)
        checks.append(detail)
    return {"schema_version": "dynamic-network-verification/v1", "success": all(item["passed"] for item in checks),
            "data_kind": "synthetic_theoretical_verification", "comparison_with_external_simulator_executed": False,
            "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        from dynamic_calibration_cli import _write_json, guard_outputs
        if args.out:
            guard_outputs([args.out], [], overwrite=args.overwrite)
        report = run_checks()
        if args.out:
            _write_json(args.out, report, overwrite=args.overwrite)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if report["success"] else 1
    except (OSError, ValueError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
