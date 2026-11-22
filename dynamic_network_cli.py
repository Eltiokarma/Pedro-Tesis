"""Headless finite-inventory network runner; JSON and long-format SI CSV.

Exit codes: 0 completed/checked, 1 numerical or physical stop, 2 input/IO error,
130 interruption. Existing files require --overwrite; input aliases are protected.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from dynamic_calibration_cli import _write_json, guard_outputs


def trajectory_rows(result):
    """Long-format tanks and exchanger cells, preserving synthetic provenance."""
    case = result["configuration"]
    rows = []
    common = {"case_id": case["case_id"], "data_kind": "synthetic",
              "classification": case["provenance"]["classification"], "source": case["provenance"]["source"],
              "config_sha256": result["metadata"]["config_sha256"]}
    for point in result["series"]:
        for identifier, values in point["nodes"].items():
            rows.append({**common, "time_s": point["time_s"], "node_id": identifier, "unit_kind": "tank", **values})
        for identifier, values in point.get("heat_exchangers", {}).items():
            unit = result["metadata"]["heat_exchangers"][identifier]
            for i, position in enumerate(unit["cell_centres_m"]):
                rows.append({**common, "time_s": point["time_s"], "node_id": identifier, "unit_kind": "heat_exchanger_cell",
                             "cell_index": i, "position_m": position,
                             **{side+"_temperature_K": values[side+"_temperature_K"][i] for side in ("hot", "cold", "wall")},
                             **{side+"_tracer_mass_fraction": values[side+"_tracer_mass_fraction"][i] for side in ("hot", "cold")},
                             "component_classification": unit["provenance"]["classification"],
                             "component_source": unit["provenance"]["source"], "component_notes": unit["provenance"]["notes"]})
    columns = list(dict.fromkeys(key for row in rows for key in row))
    return [{key: row.get(key, "") for key in columns} for row in rows]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Red transitoria monofásica con caudales impuestos.")
    parser.add_argument("case", nargs="?", help="Caso JSON; sin caso se ejecuta el ejemplo en serie.")
    parser.add_argument("--example", choices=("cascade", "split_merge", "recirculation", "energyplus_mixed_tank",
                                             "coupled_recirculation", "coupled_feed"))
    parser.add_argument("--write-example", metavar="JSON", help="Crea el ejemplo elegido sin simular.")
    parser.add_argument("--check", action="store_true", help="Comprueba topología, estados iniciales y eventos.")
    parser.add_argument("--out", help="Resultado JSON con configuración, puertos, balances y procedencia.")
    parser.add_argument("--csv", help="Trayectorias SI: una fila por inventario y tiempo.")
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
        from dynamic_network import simulate_dynamic_network, validate_network
        from dynamic_network_examples import example_cases
        from dynamic_network_component_examples import example_cases as component_cases
        case = (json.loads(Path(args.case).read_text(encoding="utf-8-sig")) if args.case
                else {**example_cases(), **component_cases()}[(args.example or "cascade") + ".json"])
        case = validate_network(case)
        if args.write_example:
            _write_json(args.write_example, case, overwrite=args.overwrite)
            return 0
        result = ({"schema_version": "dynamic-network-preflight/v1", "case_id": case["case_id"],
                   "status": "initial_conditions_and_all_events_checked", "configuration": case}
                  if args.check else simulate_dynamic_network(case))
        guard_outputs(outputs, inputs, overwrite=args.overwrite)
        if args.csv:
            from dynamic_cli import export_trajectory
            export_trajectory({"series": trajectory_rows(result)}, args.csv)
        if args.out:
            _write_json(args.out, result, overwrite=args.overwrite)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if args.check or result["summary"]["success"] else 1
    except KeyboardInterrupt:
        print("Simulación interrumpida.", file=sys.stderr)
        return 130
    except (ValueError, TypeError, OSError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
