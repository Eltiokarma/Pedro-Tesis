"""
gate_simulate.py — GATES de la API headless simulate_engine.

Tres gates CI-ables (todos sobre los 41 ejemplos del catálogo):

  1. EQUIVALENCIA MOTOR: simulate(load_example(clave))["summary"] == golden
     congelado (overall_status, n_blocks, n_streams, mass/energy errors,
     sum_duty abs<1e-6, ISBL rel<1e-6).  simulate es otro camino al mismo
     motor: no puede cambiar resultados.

  2. EQUIVALENCIA ECONÓMICA: simulate(run_economics=True) NPV/IRR ==
     la ruta GUI/Save (compute_turton_costing sobre el df_variable armado del
     fs).  Mismo motor, distinto envoltorio.

  3. HEADLESS REAL: simulate_engine se importa sin arrastrar PySide6/tkinter.

USO:
    python gate_simulate.py
    echo $?      # 0 = los 3 gates verdes, 1 = alguno rojo
"""
import os
import sys
import json

_SUMDUTY_TOL_ABS = 1e-6
_ISBL_TOL_REL    = 1e-6
_ECON_TOL        = 1e-6

DATA_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "data", "examples")
GOLDEN_PATH = os.path.join(DATA_DIR, "_golden.json")


def gate_headless():
    """Gate 3: importar simulate_engine NO debe traer Qt/tkinter."""
    # subproceso limpio: sin Qt pre-cargado
    import subprocess
    code = ("import sys; import simulate_engine; "
            "qt=[m for m in sys.modules if m.startswith('PySide6') or m=='tkinter']; "
            "sys.exit(1 if qt else 0)")
    r = subprocess.run([sys.executable, "-c", code],
                       cwd=os.path.dirname(os.path.abspath(__file__)),
                       capture_output=True, text=True)
    ok = (r.returncode == 0)
    print(f"  {'✓' if ok else '✗'} Gate 3 (headless): "
          f"simulate_engine importa sin PySide6/tkinter")
    return ok


def gate_engine_equivalence():
    """Gate 1: summary == golden congelado para los 41."""
    import examples_registry as reg
    import simulate_engine as se
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        golden = json.load(f)

    fails = []
    for clave in sorted(golden):
        out = se.simulate(reg.load_example(clave).to_dict())
        try:
            json.dumps(out)               # debe ser JSON-serializable
        except (TypeError, ValueError) as e:
            fails.append((clave, f"no serializable: {e}"))
            continue
        s = out["summary"]
        g = golden[clave]
        for fld in ("overall_status", "n_blocks", "n_streams",
                    "mass_errors", "energy_errors"):
            if g.get(fld) != s.get(fld):
                fails.append((clave, f"{fld}: golden={g.get(fld)} sim={s.get(fld)}"))
        if abs(float(g["sum_duty"]) - float(s["sum_duty"])) > _SUMDUTY_TOL_ABS:
            fails.append((clave, f"sum_duty: {g['sum_duty']} vs {s['sum_duty']}"))
        if "ISBL" in g:
            ref = max(abs(float(g["ISBL"])), 1.0)
            if abs(float(g["ISBL"]) - float(s.get("ISBL", 0))) / ref > _ISBL_TOL_REL:
                fails.append((clave, f"ISBL: {g['ISBL']} vs {s.get('ISBL')}"))

    ok = not fails
    print(f"  {'✓' if ok else '✗'} Gate 1 (motor): "
          f"{len(golden) - len({c for c, _ in fails})}/{len(golden)} "
          f"summary == golden congelado")
    for c, m in fails[:10]:
        print(f"        ✗ {c}: {m}")
    return ok


def gate_economics_equivalence():
    """Gate 2: NPV/IRR de simulate == ruta GUI/Save (compute_turton_costing)."""
    import pandas as pd
    import examples_registry as reg
    import flowsheet_solver as fsv
    import flowsheet_export as fexp
    import simulate_engine as se

    with open(GOLDEN_PATH, encoding="utf-8") as f:
        claves = sorted(json.load(f))

    fails = []
    for clave in claves:
        out = se.simulate(reg.load_example(clave).to_dict(), run_economics=True)
        econ = out["economics"]
        npv_sim, irr_sim = econ["NPV_usd"], econ["IRR_pct"]

        # referencia: ruta GUI/Save
        fs = reg.load_example(clave)
        fsv.solve(fs)
        feeds    = [s for s in fs.streams.values() if s.role == "feed"]
        products = [s for s in fs.streams.values() if s.role == "product"]
        rows = fexp._collect_pfd_opex_rows(fs, feeds, products)
        dfv = (pd.DataFrame(rows) if rows
               else pd.DataFrame(columns=["stream", "flowrate", "price usd/units"]))
        dff = pd.DataFrame([{"Concept": "Labor",
                             "Value": fexp._resolve_labor_usd(fs)}])
        ct = fexp.compute_turton_costing(fs, dfv, dff, fci_musd=None)
        npv_ref, irr_ref = ct["profit"]["NPV"], ct["profit"]["IRR %"]

        if abs((npv_sim or 0) - (npv_ref or 0)) > _ECON_TOL:
            fails.append((clave, f"NPV sim={npv_sim} ref={npv_ref}"))
        if isinstance(irr_sim, (int, float)) and isinstance(irr_ref, (int, float)):
            if abs(irr_sim - irr_ref) > _ECON_TOL:
                fails.append((clave, f"IRR sim={irr_sim} ref={irr_ref}"))
        elif irr_sim != irr_ref:
            fails.append((clave, f"IRR sim={irr_sim} ref={irr_ref}"))

    ok = not fails
    print(f"  {'✓' if ok else '✗'} Gate 2 (económico): "
          f"{len(claves) - len({c for c, _ in fails})}/{len(claves)} "
          f"NPV/IRR == ruta GUI/Save")
    for c, m in fails[:10]:
        print(f"        ✗ {c}: {m}")
    return ok


def main():
    print("=" * 70)
    print("GATES — API headless simulate_engine")
    print("=" * 70)
    g3 = gate_headless()
    g1 = gate_engine_equivalence()
    g2 = gate_economics_equivalence()
    print("=" * 70)
    if g1 and g2 and g3:
        print("✓ LOS 3 GATES VERDES.")
        return 0
    print("✗ HAY GATES ROJOS.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
