"""Reproducible numerical acceptance gate for the three synthetic pilot cases.

This gate checks completion, integrated conservation and solver agreement. It
does not compare against plant observations or certify an industrial model.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import platform
import time

from dynamic_tank import simulate_dynamic_tank


def run_gate() -> dict:
    examples = Path(__file__).resolve().parent / "data" / "dynamic_examples"
    rows = []
    for path in sorted(examples.glob("*.json")):
        config = json.loads(path.read_text(encoding="utf-8"))
        start = time.perf_counter()
        result = simulate_dynamic_tank(config)
        audit = result["audit"]
        final = result["series"][-1]
        passed = result["summary"]["success"] and all(
            audit[key] < 1e-9 for key in
            ("max_mass_residual_relative", "max_tracer_residual_relative", "max_energy_residual_relative")
        )
        solver_difference = None
        if path.name == "heating_500kg.json":
            reference = copy.deepcopy(config)
            reference["simulation"].update(method="Radau", rtol=1e-9, atol=1e-10, max_step_s=2.5)
            reference_result = simulate_dynamic_tank(reference)
            reference_by_time = {row["time_s"]: row for row in reference_result["series"]}
            solver_difference = max(
                abs(row[key] - reference_by_time[row["time_s"]][key])
                for row in result["series"]
                for key in ("tank_temperature_K", "wall_temperature_K", "jacket_temperature_K")
            )
            passed = passed and reference_result["summary"]["success"] and solver_difference < .02
        rows.append({
            "case": path.name, "passed": bool(passed), "summary": result["summary"],
            "config_sha256": result["metadata"]["config_sha256"],
            "elapsed_s": time.perf_counter() - start, "audit": audit,
            "final_tank_temperature_K": final["tank_temperature_K"],
            "final_mass_kg": final["mass_kg"],
            "final_tracer_mass_fraction": final["tracer_mass_fraction"],
            "max_BDF_Radau_temperature_difference_K": solver_difference,
        })
    passed = len(rows) == 3 and all(row["passed"] for row in rows)
    return {"success": passed, "scope": "numerical_only_synthetic_cases_no_plant_validation",
            "python": platform.python_version(),
            "acceptance": {"relative_balance_residual_max": 1e-9,
                           "BDF_Radau_temperature_difference_K_max": .02},
            "cases": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="Write numerical acceptance JSON.")
    args = parser.parse_args(argv)
    result = run_gate()
    payload = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
