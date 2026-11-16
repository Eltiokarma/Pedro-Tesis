"""Headless calibration/held-out evaluation of the bounded dynamic tank.

Exit 0 means preflight passed, or numerical fitting and configured held-out
criteria passed with a usable local estimate. It never certifies plant accuracy.
Exit 1 means a failed/inconclusive fit or unmet criteria, 2 invalid input/IO,
and 130 cancellation/interruption. Existing outputs require --overwrite;
study files and referenced input data must never be overwritten.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


def _same_path(first, second):
    first, second = Path(first).resolve(), Path(second).resolve()
    if os.path.normcase(str(first)) == os.path.normcase(str(second)):
        return True
    if first.exists() and second.exists():
        return os.path.samefile(first, second)
    return False


def guard_outputs(outputs, inputs, *, overwrite=False):
    """Protect inputs, aliases and existing files before starting expensive work."""
    for index, output in enumerate(outputs):
        if any(_same_path(output, previous) for previous in outputs[:index]):
            raise ValueError("Cada salida debe tener una ruta distinta.")
        if any(_same_path(output, source) for source in inputs):
            raise ValueError("Una salida no puede sobrescribir el estudio ni sus datos de entrada.")
        if Path(output).exists() and not overwrite:
            raise FileExistsError(f"La salida ya existe: {output}. Use --overwrite para reemplazarla.")
        if not Path(output).parent.is_dir():
            raise ValueError(f"La carpeta de salida no existe: {Path(output).parent}")


def _write_json(path, value, *, overwrite=False):
    # Encode before opening any destination: invalid Unicode must not truncate
    # an existing report. Replacement also avoids modifying a hardlink target.
    encoded = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    target = Path(path)
    if not overwrite:
        with target.open("xb") as handle:
            handle.write(encoded)
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".calibration-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def guard_snapshot(study, report):
    """Ensure the fitted snapshot is the same study that passed preflight."""
    if study["provenance"]["study_sha256"] != report["provenance"].get("study_sha256"):
        raise ValueError("El estudio cambió después de la comprobación; vuelva a cargarlo.")
    expected = {exp["experiment_id"]: (exp["case_sha256"], exp["measurement_sha256"])
                for exp in study["experiments"]}
    actual = {exp["experiment_id"]: (exp["provenance"].get("case_sha256"),
                                      exp["provenance"].get("measurement_sha256"))
              for exp in report["experiments"]}
    if actual != expected:
        raise ValueError("Los casos o mediciones cambiaron después de la comprobación; vuelva a cargar el estudio.")


def _input_paths(study_path, study):
    base = Path(study_path).resolve().parent
    return [Path(study_path), *(base / exp[key] for exp in study["experiments"]
                               for key in ("case_file", "measurements_file"))]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ajusta parámetros térmicos y evalúa ensayos reservados.")
    parser.add_argument("study", nargs="?", help="Estudio JSON con casos y CSV referenciados.")
    parser.add_argument("--check", action="store_true", help="Comprueba datos y separación de ensayos sin ajustar.")
    parser.add_argument("--out", help="Informe JSON con resultados, procedencia y diagnósticos.")
    parser.add_argument("--fitted-case", help="Guarda explícitamente el caso candidato del ensayo seleccionado.")
    parser.add_argument("--experiment-id", help="Ensayo cuyo caso ajustado se exporta.")
    parser.add_argument("--write-example", metavar="DIRECTORY", help="Crea un estudio completo con datos sintéticos.")
    parser.add_argument("--overwrite", action="store_true", help="Permite reemplazar salidas; nunca entradas.")
    args = parser.parse_args(argv)
    try:
        if args.write_example:
            if args.study or args.check or args.out or args.fitted_case or args.experiment_id:
                raise ValueError("Crear el ejemplo y ajustar un estudio son operaciones separadas.")
            from calibration_example import write_calibration_example
            print(write_calibration_example(args.write_example, overwrite=args.overwrite))
            print("Datos sintéticos por exponencial matricial; no son registros de planta.")
            return 0
        if not args.study:
            raise ValueError("Indique un estudio JSON o --write-example DIRECTORIO.")
        if bool(args.fitted_case) != bool(args.experiment_id):
            raise ValueError("--fitted-case y --experiment-id deben usarse juntos.")
        if args.check and args.fitted_case:
            raise ValueError("--check no genera un caso ajustado.")
        from dynamic_study import load_study
        study = load_study(args.study)
        if args.experiment_id and args.experiment_id not in {
                exp["experiment_id"] for exp in study["experiments"]}:
            raise ValueError("El experiment-id solicitado no existe en el estudio.")
        outputs = [Path(value) for value in (args.out, args.fitted_case) if value]
        guard_outputs(outputs, _input_paths(args.study, study), overwrite=args.overwrite)
        if args.check:
            result = {
                "schema_version": "dynamic-calibration-preflight/v1",
                "study_id": study["study_id"], "equipment_id": study["equipment_id"],
                "status": "inputs_checked_not_fitted",
                "parameters": study["parameters"],
                "experiments": [{key: exp[key] for key in
                                 ("experiment_id", "role", "data_kind", "measurement_sha256")}
                                for exp in study["experiments"]],
                "provenance": study["provenance"],
                "conclusion": "Duplicados comprobados; autenticidad e independencia experimental no acreditadas.",
            }
            if args.out:
                _write_json(args.out, result, overwrite=args.overwrite)
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
            return 0

        from dynamic_calibration import calibrate_study
        result = calibrate_study(args.study)
        guard_snapshot(study, result)
        # A run may take time. Recheck current references and output aliases
        # before writing, while the result continues to describe its snapshot.
        current_study = load_study(args.study)
        guard_snapshot(current_study, result)
        guard_outputs(outputs, _input_paths(args.study, study) + _input_paths(args.study, current_study),
                      overwrite=args.overwrite)
        summary = result["summary"]
        if args.out:
            _write_json(args.out, result, overwrite=args.overwrite)
        if args.fitted_case:
            selected = next((exp for exp in result.get("experiments", [])
                             if exp["experiment_id"] == args.experiment_id), None)
            if summary.get("optimization_converged") and selected and selected.get("fitted_case"):
                _write_json(args.fitted_case, selected["fitted_case"], overwrite=args.overwrite)
            else:
                print("No se exportó un caso: el ajuste no produjo un candidato convergido.", file=sys.stderr)
        print(json.dumps({"summary": summary, "parameters": result.get("parameters", []),
                          "warnings": result.get("warnings", []),
                          "validation_state": result.get("validation_state")},
                         ensure_ascii=False, indent=2, allow_nan=False))
        if summary.get("status") == "cancelled":
            return 130
        return 0 if (summary.get("optimization_converged")
                     and summary.get("validation_status") == "criteria_met"
                     and summary.get("usable_parameter_estimate") is True) else 1
    except KeyboardInterrupt:
        print("Calibración interrumpida.", file=sys.stderr)
        return 130
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
