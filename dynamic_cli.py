"""Run the jacketed-tank pilot without Qt and compare user-supplied time series.

Examples::

    python dynamic_cli.py --write-example case.json --measurement-template measured.csv
    python dynamic_cli.py case.json --out run.json --csv trajectory.csv
    python dynamic_cli.py case.json --measurements measured.csv --out compared.json
    python dynamic_cli.py --thermal-loop --write-example loop.json

The built-in example is synthetic. A completed simulation or a comparison does
not confer empirical validation. Exit codes: 0 completed, 1 stopped/failed,
2 invalid input or IO, 130 interrupted.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import sys
import tempfile


def _write_json(path: str, value: dict) -> None:
    from dynamic_calibration_cli import _write_json as write_atomic_json
    write_atomic_json(path, value, overwrite=True)


def export_trajectory(result: dict, path: str) -> None:
    """Export only recorded simulation points, in their native explicit SI units."""
    series = result.get("series", [])
    if not series:
        raise ValueError("No hay puntos de trayectoria para exportar.")
    target, temporary = Path(path), None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, prefix=".trajectory-",
                                         newline="", encoding="utf-8", delete=False) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=list(series[0]))
            writer.writeheader()
            writer.writerows(series)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Simula el piloto de tanque con camisa y control de temperatura."
    )
    parser.add_argument("case", nargs="?", help="Caso JSON; omitir ejecuta el ejemplo sintético.")
    parser.add_argument("--out", help="Resultado JSON, incluida comparación si se solicita.")
    parser.add_argument("--csv", help="Exportación de la trayectoria calculada (SI).")
    parser.add_argument("--measurements", help="CSV de observaciones con time_s y columnas SI.")
    parser.add_argument("--time-offset-s", type=float, default=0.0,
                        help="Tiempo simulado = tiempo CSV + este desplazamiento.")
    parser.add_argument("--source-label", default="user_supplied",
                        help="Identificador de las observaciones; no acredita su procedencia.")
    parser.add_argument("--write-example", metavar="CASE_JSON",
                        help="Guarda un caso de ejemplo y termina sin simular.")
    parser.add_argument("--measurement-template", metavar="CSV",
                        help="Guarda una plantilla de medición vacía y termina sin simular.")
    parser.add_argument("--thermal-loop", action="store_true",
                        help="Usa el ejemplo de circuito térmico cerrado v3; no combinar con un caso JSON.")
    args = parser.parse_args(argv)

    try:
        if args.thermal_loop and args.case:
            raise ValueError("--thermal-loop selecciona un ejemplo; no se combina con un caso JSON.")
        input_paths = {Path(p).resolve() for p in (args.case, args.measurements) if p}
        output_paths = [Path(p).resolve() for p in
                        (args.out, args.csv, args.write_example, args.measurement_template) if p]
        from dynamic_calibration_cli import guard_outputs
        guard_outputs(output_paths, input_paths, overwrite=True)
        from dynamic_tank import default_case, default_thermal_loop_case, simulate_dynamic_tank
        from dynamic_measurements import compare_measurements, write_measurement_template
        example_factory = default_thermal_loop_case if args.thermal_loop else default_case

        preparation = bool(args.write_example or args.measurement_template)
        if preparation:
            if args.case or args.out or args.csv or args.measurements:
                raise ValueError("Crear plantillas y ejecutar una simulación son operaciones separadas.")
            if args.write_example:
                _write_json(args.write_example, example_factory())
            if args.measurement_template:
                write_measurement_template(args.measurement_template, thermal_loop=args.thermal_loop)
            return 0

        case = json.loads(Path(args.case).read_text(encoding="utf-8-sig")) if args.case else example_factory()
        result = simulate_dynamic_tank(case)
        if args.measurements:
            result["measurement_comparison"] = compare_measurements(
                result, args.measurements, source_label=args.source_label,
                time_offset_s=args.time_offset_s,
            )
        guard_outputs([p for p in (args.csv, args.out) if p],
                      [*input_paths, *(p for p in (args.case, args.measurements) if p)], overwrite=True)
        if args.csv:
            export_trajectory(result, args.csv)
        if args.out:
            _write_json(args.out, result)
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0 if result.get("summary", {}).get("success") else 1
    except KeyboardInterrupt:
        print("Simulación interrumpida.", file=sys.stderr)
        return 130
    except (OSError, ValueError, TypeError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
