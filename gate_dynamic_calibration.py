"""Numerical gate with independent synthetic observations, not plant validation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform

from dynamic_calibration import calibrate_study
from dynamic_calibration_cli import _write_json, guard_outputs, _input_paths
from dynamic_study import load_study


def run_gate():
    folder = Path(__file__).resolve().parent / "data" / "calibration_examples"
    report = calibrate_study(folder / "study.json")
    reference_bytes = (folder / "reference.json").read_bytes()
    reference = json.loads(reference_bytes)
    summary = report["summary"]
    recovery = []
    for item in report["parameters"]:
        truth = reference["true_parameters"][item["path"]]
        relative_error = abs(item["value"] - truth) / abs(truth)
        recovery.append({"path": item["path"], "reference": truth,
                         "estimated": item["value"], "unit": item["unit"],
                         "relative_error": relative_error, "passed": relative_error <= 0.03})
    experiments = []
    for item in report["experiments"]:
        audit = item.get("balance_audit", {})
        balances_pass = bool(audit) and all(audit[key] < 1e-9 for key in (
            "max_mass_residual_relative", "max_tracer_residual_relative", "max_energy_residual_relative"))
        experiments.append({"experiment_id": item["experiment_id"], "role": item["role"],
                            "baseline_metrics": item["baseline_metrics"], "fitted_metrics": item["fitted_metrics"],
                            "balance_audit": audit, "balances_pass": balances_pass,
                            "provenance": item["provenance"]})
    improved = (summary["objective_before"] is not None and summary["objective_after"] is not None
                and summary["objective_after"] < summary["objective_before"] * 0.01)
    passed = (summary["status"] == "ok" and summary["optimization_converged"]
              and summary["usable_parameter_estimate"] and summary["validation_status"] == "criteria_met"
              and report["validation_state"] == "synthetic_calibration_only"
              and improved and len(recovery) == 2 and all(item["passed"] for item in recovery)
              and len(experiments) == 3 and all(item["balances_pass"] for item in experiments))
    return {"success": bool(passed), "scope": "synthetic_numerical_verification_no_plant_validation",
            "python": platform.python_version(), "summary": summary,
            "acceptance": {"parameter_relative_error_max": 0.03, "objective_ratio_max": 0.01,
                           "relative_balance_residual_max": 1e-9,
                           "heldout_error_criteria": "declared_in_study_not_industrial_tolerances"},
            "parameter_recovery": recovery, "diagnostics": report["diagnostics"],
            "experiments": experiments, "warnings": report["warnings"],
            "provenance": report["provenance"],
            "reference_sha256": hashlib.sha256(reference_bytes).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="Save numerical gate evidence as JSON.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    folder = Path(__file__).resolve().parent / "data" / "calibration_examples"
    if args.out:
        study = load_study(folder / "study.json")
        guard_outputs([args.out], _input_paths(folder / "study.json", study) + [folder / "reference.json"],
                      overwrite=args.overwrite)
    result = run_gate()
    if args.out:
        _write_json(args.out, result, overwrite=args.overwrite)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
