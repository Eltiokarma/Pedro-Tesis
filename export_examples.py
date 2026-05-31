"""
export_examples.py — Exporter one-time de builders imperativos a JSON
declarativo (Fase 1 de la migración de ejemplos).

Corre cada builder _example_* de examples_library.ExampleBuilder en modo
headless (patrón _FakeEditor de validate_ui.py), y vuelca por cada ejemplo:

  · data/examples/<clave_menu>.json   → el to_dict() del flowsheet armado.
      El NOMBRE DEL ARCHIVO es la CLAVE DEL MENÚ (flowsheet_qt.py builder_map),
      NO nombre[9:].  Hay ~21 alias (crude_distillation→cdu, etc.); el mapeo
      se extrae vía AST con tools_extract_menu_map.extract_menu_map().

  · data/examples/_golden.json        → golden values de cada ejemplo:
      overall_status, n_blocks, n_streams, mass_errors, energy_errors,
      sum_duty (Σ duties post-solve, OBLIGATORIO — canario de idempotencia
      del recycle), e ISBL si el ejemplo lo computa.

USO:
    python export_examples.py            # genera JSON + golden
    python export_examples.py --check    # no escribe, solo imprime resumen

RESTRICCIÓN: consume to_dict() tal cual.  Cero cambios a la serialización.
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


def _make_fake_editor():
    """Replica el _FakeEditor de validate_ui.py: un objeto con .fs y los
    5 helpers de ExampleBuilder enganchados como métodos."""
    import flowsheet_model as fm
    import examples_library as el

    class _FakeEditor:
        def __init__(self):
            self.fs = fm.Flowsheet()
            self.labor_workers = 0
        _add_example_block = el.ExampleBuilder._add_example_block
        _add_example_stream = el.ExampleBuilder._add_example_stream
        _add_example_extra = el.ExampleBuilder._add_example_extra
        _set_example_labor = el.ExampleBuilder._set_example_labor
        _set_block_duty = el.ExampleBuilder._set_block_duty

    return _FakeEditor()


def build_flowsheet(builder_name):
    """Corre un builder y devuelve el Flowsheet armado (SIN solve)."""
    import examples_library as el
    fake = _make_fake_editor()
    getattr(el.ExampleBuilder, builder_name)(fake)
    return fake.fs


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


def run_one(builder_name):
    """Construye y devuelve (to_dict PRE-solve, golden POST-solve).

    El JSON se captura ANTES de solve() — estado DECLARATIVO puro: solo las
    specs que el builder declaró (composiciones, T/P/flujos lockeados,
    duties manuales, flags de reactor/columna/flash).  NO incluye valores
    DERIVADOS por el solver (presiones propagadas, duties auto-inferidos,
    composiciones de columna/flash).  Esto elimina de raíz la asimetría
    builder↔JSON: cargar el JSON y resolver reproduce el mismo flowsheet que
    construir con el builder y resolver, porque ambos parten del mismo
    estado declarativo y aplican el MISMO solver encima.

    El golden se computa POST-solve (necesita el flowsheet resuelto)."""
    import flowsheet_solver as fsv
    fs = build_flowsheet(builder_name)
    data = fs.to_dict()            # ← snapshot declarativo, antes de resolver
    res = fsv.solve(fs)            # solve in-place (muta fs, no el dict)
    return data, golden(fs, res)


def _builder_key_pairs():
    """[(builder_name, clave_menú), ...] para los 41 ejemplos.

    Prioridad:
      1) data/examples/manifest.json (fuente de verdad tras Fase 2, cuando
         flowsheet_qt.py ya no expone los literales builder_map/
         EXAMPLE_CATEGORIES para extracción AST).
      2) Bootstrap desde flowsheet_qt.py vía AST (sólo en la generación
         inicial, antes de que exista el manifest)."""
    manifest = os.path.join(DATA_DIR, "manifest.json")
    if os.path.isfile(manifest):
        with open(manifest, encoding="utf-8") as f:
            data = json.load(f)
        return [(e["builder"], e["clave"]) for e in data.get("examples", [])]
    # bootstrap
    from tools_extract_menu_map import extract_menu_map
    menu_map = extract_menu_map()      # builder -> (clave, nombre, area, pfd)
    return [(b, k) for b, (k, *_rest) in menu_map.items()]


def export_all(write=True):
    """Exporta los 41 ejemplos.  Devuelve (n_exportados, golden_dict)."""
    _headless_mocks()
    # Mapeo builder -> clave.  Fuente: el manifest si ya existe (post-Fase 2,
    # cuando flowsheet_qt.py ya es data-driven y los extractores AST de
    # EXAMPLE_CATEGORIES/builder_map ya no aplican); si no, bootstrap desde
    # flowsheet_qt.py vía AST (generación inicial).
    pairs = _builder_key_pairs()      # [(builder_name, key), ...]

    if write:
        os.makedirs(DATA_DIR, exist_ok=True)

    golden_all = {}
    n = 0
    for builder_name, key in sorted(pairs):
        data, g = run_one(builder_name)
        golden_all[key] = g
        if write:
            path = os.path.join(DATA_DIR, f"{key}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        n += 1
        print(f"  {key:18s} <- {builder_name:34s} "
              f"{g['overall_status']:>8} b{g['n_blocks']} s{g['n_streams']} "
              f"duty={g['sum_duty']:.1f}")

    if write:
        with open(GOLDEN_PATH, "w", encoding="utf-8") as f:
            json.dump(golden_all, f, ensure_ascii=False, indent=1,
                      sort_keys=True)
        print(f"\nEscritos {n} JSON + _golden.json en {DATA_DIR}")
    else:
        print(f"\n[--check] {n} ejemplos procesados (sin escribir)")
    return n, golden_all


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="No escribir; solo procesar y resumir.")
    args = parser.parse_args()
    export_all(write=not args.check)
