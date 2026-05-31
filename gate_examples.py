"""
gate_examples.py — GATE de equivalencia builder ↔ JSON (Fase 1).

Para cada ejemplo migrado:
  1. Carga data/examples/<clave>.json con Flowsheet.from_dict().
  2. Corre solve().
  3. Recomputa los golden values (misma función golden() del exporter).
  4. Exige IGUALDAD EXACTA contra data/examples/_golden.json (el golden del
     builder original).  sum_duty con tolerancia float < 1e-6.

Si algún ejemplo difiere, lo reporta campo por campo y sale con código != 0.
Dado que el solver quedó idempotente en Fase 0, se espera 41/41 verde; un
fallo acá es una REGRESIÓN — investigar, no parchear el golden.

USO (comando único, CI-able):
    python gate_examples.py
    echo $?      # 0 = 41/41 verde, 1 = hay diferencias

RESTRICCIÓN: consume from_dict() tal cual.  Cero cambios a la serialización.
"""
import os
import sys
import json

from export_examples import (DATA_DIR, GOLDEN_PATH, golden,
                             _headless_mocks)

# Tolerancia para sum_duty / ISBL (ruido float documentado).
_FLOAT_TOL = 1e-6


def _load_golden_baseline():
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return json.load(f)


def _diff_golden(expected, got):
    """Devuelve lista de (campo, esperado, obtenido) que difieren.
    Campos float (sum_duty, ISBL) con tolerancia _FLOAT_TOL; el resto
    igualdad exacta."""
    diffs = []
    keys = set(expected) | set(got)
    for k in sorted(keys):
        e = expected.get(k, "<ausente>")
        g = got.get(k, "<ausente>")
        if k in ("sum_duty", "ISBL"):
            try:
                if abs(float(e) - float(g)) <= _FLOAT_TOL:
                    continue
            except (TypeError, ValueError):
                pass
        if e != g:
            diffs.append((k, e, g))
    return diffs


def run_gate():
    _headless_mocks()
    import flowsheet_model as fm
    import flowsheet_solver as fsv

    if not os.path.isdir(DATA_DIR):
        print(f"✗ No existe {DATA_DIR}. Corré export_examples.py primero.")
        return 1
    if not os.path.isfile(GOLDEN_PATH):
        print(f"✗ No existe {GOLDEN_PATH}. Corré export_examples.py primero.")
        return 1

    baseline = _load_golden_baseline()

    print("=" * 78)
    print("GATE builder ↔ JSON — re-solve de cada JSON vs golden del builder")
    print("=" * 78)

    n_ok = 0
    fails = []
    for key in sorted(baseline):
        path = os.path.join(DATA_DIR, f"{key}.json")
        if not os.path.isfile(path):
            fails.append((key, [("archivo", path, "<no existe>")]))
            print(f"  ✗ {key:18s} JSON faltante")
            continue
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        fs = fm.Flowsheet.from_dict(d)
        res = fsv.solve(fs)
        got = golden(fs, res)
        diffs = _diff_golden(baseline[key], got)
        if diffs:
            fails.append((key, diffs))
            print(f"  ✗ {key:18s} {len(diffs)} campo(s) difieren")
            for campo, e, g in diffs:
                print(f"        {campo}: golden={e!r}  roundtrip={g!r}")
        else:
            n_ok += 1
            print(f"  ✓ {key:18s} {got['overall_status']:>8} "
                  f"b{got['n_blocks']} s{got['n_streams']} "
                  f"duty={got['sum_duty']:.1f}")

    print("=" * 78)
    total = len(baseline)
    if fails:
        print(f"✗ GATE ROJO: {len(fails)}/{total} ejemplos NO equivalen.")
        print("  (Solver es idempotente desde Fase 0 → un fallo acá es "
              "REGRESIÓN; investigar, NO parchear el golden.)")
        return 1
    print(f"✓ GATE VERDE: {n_ok}/{total} ejemplos round-trippean idéntico.")
    return 0


if __name__ == "__main__":
    sys.exit(run_gate())
