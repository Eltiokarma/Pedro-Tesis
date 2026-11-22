"""Distributed sensible heat exchanger: JSON cases and long-format cell profiles.

Exit codes: 0 success, 1 incomplete simulation, 2 input/IO error, 130 interrupt.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from dynamic_calibration_cli import _write_json, guard_outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", nargs="?")
    parser.add_argument("--example", choices=("counter_current", "co_current", "transport", "msl_geometry_adaptation"))
    parser.add_argument("--write-example", metavar="JSON")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out", help="Resultado JSON con perfiles, balances y procedencia.")
    parser.add_argument("--csv", help="Una fila por celda y tiempo, unidades SI.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.case and (args.example or args.write_example):
            raise ValueError("Elegir un ejemplo y cargar un caso son operaciones distintas.")
        if args.write_example and (args.out or args.csv or args.check):
            raise ValueError("Crear un ejemplo no se combina con ejecutar o comprobar.")
        if args.check and args.csv:
            raise ValueError("--check no genera trayectorias CSV.")
        inputs = [args.case] if args.case else []
        outputs = [p for p in (args.out, args.csv, args.write_example) if p]
        guard_outputs(outputs, inputs, overwrite=args.overwrite)
        from dynamic_heat_exchanger import simulate_heat_exchanger, validate_heat_exchanger
        from dynamic_heat_exchanger_examples import example_cases
        case = (json.loads(Path(args.case).read_text(encoding="utf-8-sig")) if args.case else
                example_cases()[(args.example or "counter_current")+".json"])
        case = validate_heat_exchanger(case)
        if args.write_example:
            _write_json(args.write_example, case, overwrite=args.overwrite)
            return 0
        result = ({"schema_version": "dynamic-heat-exchanger-preflight/v1", "case_id": case["case_id"],
                   "status": "initial_conditions_and_all_events_checked", "configuration": case}
                  if args.check else simulate_heat_exchanger(case))
        guard_outputs(outputs, inputs, overwrite=args.overwrite)
        if args.csv:
            from dynamic_cli import export_trajectory
            rows = []
            for point in result["series"]:
                for cell, position in enumerate(result["geometry"]["cell_centres_m"]):
                    rows.append({"case_id": case["case_id"], "data_kind": "synthetic",
                                 "classification": case["provenance"]["classification"],
                                 "source": case["provenance"]["source"], "provenance_notes": case["provenance"]["notes"],
                                 "config_sha256": result["metadata"]["config_sha256"],
                                 "flow_arrangement": case["flow_arrangement"], "time_s": point["time_s"],
                                 "cell_index": cell, "position_m": position,
                                 **{side+"_temperature_K": point[side+"_temperature_K"][cell] for side in ("hot", "cold", "wall")},
                                 **{key: point[key] for key in case["inputs"]}})
            export_trajectory({"series": rows}, args.csv)
        if args.out: _write_json(args.out, result, overwrite=args.overwrite)
        else: print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if args.check or result["summary"]["success"] else 1
    except KeyboardInterrupt:
        print("Simulacion interrumpida.", file=sys.stderr)
        return 130
    except (ValueError, TypeError, OSError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
