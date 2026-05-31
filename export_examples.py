"""
export_examples.py — Regenerador de data/examples/_golden.json.

Los builders imperativos fueron retirados: los 41 JSON de data/examples/ son
la ÚNICA fuente de verdad (versionados a mano).  Este script ya NO genera los
<clave>.json; solo REGENERA el golden a partir de ellos, cargando cada uno
vía el registry (from_dict), resolviéndolo y volcando:

  · data/examples/_golden.json → golden values de cada ejemplo:
      overall_status, n_blocks, n_streams, mass_errors, energy_errors,
      sum_duty (Σ duties post-solve, canario de idempotencia del recycle),
      e ISBL si el ejemplo lo computa.

Solo correr (con escritura) cuando se cambia DELIBERADAMENTE un ejemplo y se
quiere actualizar su golden.  Para validar sin tocar nada, usar gate_examples.py.

USO:
    python export_examples.py            # regenera _golden.json desde los JSON
    python export_examples.py --check    # no escribe, solo imprime resumen
"""
import os
import sys
import json
import argparse


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "examples")
GOLDEN_PATH = os.path.join(DATA_DIR, "_golden.json")


def _headless_mocks():
    """Mockea PySide6/tkinter para correr sin GUI (igual que validate_ui)."""
    from unittest.mock import MagicMock
    for m in ['PySide6', 'PySide6.QtCore', 'PySide6.QtGui',
              'PySide6.QtWidgets', 'PySide6.QtSvg',
              'tkinter', 'tkinter.ttk', 'tkinter.messagebox',
              'tkinter.filedialog', 'tkinter.simpledialog', 'tkinter.font']:
        sys.modules.setdefault(m, MagicMock())


def _compute_isbl(fs):
    """ISBL (Inside Battery Limits) del flowsheet vía capex.compute_fci.

    El módulo capex usa la metodología Grass Roots (Turton 7.10): el ISBL
    "pelado" es Σ CBM (bare module cost de los equipos reales, excluyendo
    auto_aux).  Lo reportamos como golden para cazar regresiones de costing
    derivadas de cambios en el flowsheet armado.

    Defensivo: si la API difiere o falla, devuelve None — el gate compara
    golden-vs-golden, así que None en ambos lados sigue siendo consistente.
    Redondeado para evitar ruido float en la comparación."""
    try:
        import capex
        res = capex.compute_fci(fs)
    except Exception:
        return None
    if isinstance(res, dict) and "sum_cbm" in res:
        v = res["sum_cbm"]
        return round(float(v), 2) if v is not None else None
    return None


def golden(fs, res):
    """Golden values de un flowsheet ya resuelto.  Determinista.

    sum_duty es el canario de idempotencia (destapó el bug del recycle de
    industrial_complete en Fase 0) — permanente en el set."""
    g = {
        "overall_status": res.overall_status,
        "n_blocks": len(fs.blocks),
        "n_streams": len(fs.streams),
        "mass_errors": len(res.mass_balance_errors),
        "energy_errors": len(res.energy_balance_errors),
        "sum_duty": round(sum(float(getattr(b, "duty", 0.0) or 0.0)
                              for b in fs.blocks.values()), 6),
    }
    isbl = _compute_isbl(fs)
    if isbl is not None:
        g["ISBL"] = isbl
    return g


def run_one(clave):
    """Golden POST-solve de un ejemplo cargado desde su JSON canónico.

    Carga data/examples/<clave>.json vía el registry (from_dict), resuelve y
    computa el golden.  Los JSON son la fuente de verdad (los builders fueron
    retirados); este script solo REGENERA _golden.json a partir de ellos."""
    import examples_registry as reg
    import flowsheet_solver as fsv
    fs = reg.load_example(clave)
    res = fsv.solve(fs)
    return golden(fs, res)


def export_all(write=True):
    """Regenera data/examples/_golden.json desde los JSON canónicos.

    NO toca los <clave>.json (son la fuente de verdad, versionada a mano);
    solo recomputa el golden post-solve.  Devuelve (n, golden_dict)."""
    _headless_mocks()
    import examples_registry as reg

    golden_all = {}
    n = 0
    for e in reg.list_examples():
        clave = e["clave"]
        g = run_one(clave)
        golden_all[clave] = g
        n += 1
        print(f"  {clave:18s} {g['overall_status']:>8} "
              f"b{g['n_blocks']} s{g['n_streams']} duty={g['sum_duty']:.1f}")

    if write:
        with open(GOLDEN_PATH, "w", encoding="utf-8") as f:
            json.dump(golden_all, f, ensure_ascii=False, indent=1,
                      sort_keys=True)
        print(f"\nRegenerado _golden.json ({n} ejemplos) en {DATA_DIR}")
    else:
        print(f"\n[--check] {n} ejemplos procesados (sin escribir)")
    return n, golden_all


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="No escribir; solo procesar y resumir.")
    args = parser.parse_args()
    export_all(write=not args.check)
