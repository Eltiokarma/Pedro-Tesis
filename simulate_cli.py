"""
simulate_cli.py — CLI fino sobre simulate_engine.simulate.

Lee un flowsheet JSON (el to_dict() de un Flowsheet, mismo formato que
data/examples/*.json), lo resuelve headless y vuelca el dict de resultados
a stdout o a --out.

USO:
    python simulate_cli.py entrada.json
    python simulate_cli.py entrada.json --economics
    python simulate_cli.py entrada.json --economics --econ-inputs econ.json
    python simulate_cli.py entrada.json --out resultados.json
    python simulate_cli.py entrada.json --economics --write-xlsx proyecto.xlsx

EXIT CODE:
    0  si overall_status in {ok, warning}
    1  si overall_status == error (o empty)
    2  error de uso / archivo (argparse / IO)

Sin dependencia de PySide6/tkinter: corre headless.
"""
import sys
import json
import argparse

import simulate_engine as se


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Resuelve un flowsheet JSON headless y emite resultados JSON.")
    parser.add_argument("flowsheet", help="ruta al flowsheet JSON (to_dict)")
    parser.add_argument("--economics", action="store_true",
                        help="incluir el bloque económico (NPV/IRR/Payback/ROI).")
    parser.add_argument("--econ-inputs", metavar="econ.json", default=None,
                        help="JSON con overrides económicos (tax_rate, "
                             "discount_rate, project_life, useful_life, "
                             "year_target, isbl_override_usd).")
    parser.add_argument("--out", metavar="resultados.json", default=None,
                        help="escribir el dict de resultados acá (default: stdout).")
    parser.add_argument("--write-xlsx", metavar="proyecto.xlsx", default=None,
                        help="además, escribir el xlsx del proyecto (opt-in).")
    args = parser.parse_args(argv)

    # cargar flowsheet
    try:
        with open(args.flowsheet, encoding="utf-8") as f:
            flowsheet_dict = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error leyendo flowsheet: {e}", file=sys.stderr)
        return 2

    # cargar econ_inputs si se pasó
    econ_inputs = None
    if args.econ_inputs:
        try:
            with open(args.econ_inputs, encoding="utf-8") as f:
                econ_inputs = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"error leyendo econ-inputs: {e}", file=sys.stderr)
            return 2

    # correr
    result = se.simulate(
        flowsheet_dict,
        run_economics=args.economics,
        econ_inputs=econ_inputs,
        write_xlsx=args.write_xlsx,
    )

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(payload)
        except OSError as e:
            print(f"error escribiendo --out: {e}", file=sys.stderr)
            return 2
    else:
        print(payload)

    status = result.get("summary", {}).get("overall_status", "error")
    return 0 if status in ("ok", "warning") else 1


if __name__ == "__main__":
    sys.exit(main())
