"""
gate_examples.py — GATE de REGRESIÓN de los 41 ejemplos.

Los 41 JSON de data/examples/ son la ÚNICA fuente de verdad (los builders
imperativos fueron retirados; ver examples_library.py).  Este gate ya NO
compara "builder ↔ JSON": valida que cargar cada JSON y resolverlo reproduce
EXACTAMENTE el golden congelado.

Para cada ejemplo:
  1. Carga data/examples/<clave>.json (from_dict directo, o vía el registry
     con --registry: el mismo camino que usa la UI).
  2. Corre solve().
  3. Recomputa los golden values (misma función golden() del exporter).
  4. Exige IGUALDAD contra data/examples/_golden.json (patrón CONGELADO de
     Fase 1).  sum_duty con tolerancia absoluta < 1e-6; ISBL relativa < 1e-6.

Si algún ejemplo difiere, lo reporta campo por campo y sale con código != 0.
El solver es idempotente (Fase 0) y el export es pre-solve (estado declarativo
limpio), así que se espera 41/41 verde; un fallo acá es una REGRESIÓN —
investigar, NO parchear el golden.

USO (comando único, CI-able):
    python gate_examples.py              # carga from_dict directo
    python gate_examples.py --registry   # carga vía examples_registry (UI path)
    echo $?      # 0 = 41/41 verde, 1 = hay diferencias

RESTRICCIÓN: consume from_dict() tal cual.  Cero cambios a la serialización.
"""
import os
import sys
import json
import argparse

from export_examples import (DATA_DIR, GOLDEN_PATH, golden,
                             _headless_mocks)

# Tolerancia de sum_duty (canario de idempotencia): ABSOLUTA y estricta.
# Las duties son O(1e4) kW y, con el solver idempotente (Fase 0), salen
# bit-idénticas entre builder y round-trip; 1e-6 absoluto las clava sin
# margen para una regresión real.
_SUMDUTY_TOL_ABS = 1e-6

# Tolerancia de ISBL: RELATIVA.  ISBL (Σ CBM, capex.compute_fci) es una
# cifra en millones de USD; su factor de presión depende de la propagación
# hidráulica iterativa, que tiene ruido float de bajo orden cuando re-
# resuelve desde presiones ya convergidas (path JSON) vs desde presiones
# iniciales (path builder).  Comprobado en rxn_flash_col: 0.26 USD sobre
# 3.64 M = 7e-8 relativo, con sum_duty bit-idéntico (NO es regresión de
# idempotencia, es ruido float legítimo del costing).  1e-6 relativo lo
# absorbe sin enmascarar un cambio real de costo (que sería >> 1e-6).
_ISBL_TOL_REL = 1e-6


def _load_golden_baseline():
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return json.load(f)


def _diff_golden(expected, got):
    """Devuelve lista de (campo, esperado, obtenido) que difieren.
    sum_duty: tolerancia absoluta estricta (idempotencia).  ISBL:
    tolerancia relativa (ruido float del costing hidráulico).  El resto:
    igualdad exacta."""
    diffs = []
    keys = set(expected) | set(got)
    for k in sorted(keys):
        e = expected.get(k, "<ausente>")
        g = got.get(k, "<ausente>")
        if k == "sum_duty":
            try:
                if abs(float(e) - float(g)) <= _SUMDUTY_TOL_ABS:
                    continue
            except (TypeError, ValueError):
                pass
        elif k == "ISBL":
            try:
                ref = max(abs(float(e)), abs(float(g)), 1.0)
                if abs(float(e) - float(g)) / ref <= _ISBL_TOL_REL:
                    continue
            except (TypeError, ValueError):
                pass
        if e != g:
            diffs.append((k, e, g))
    return diffs


def _load_direct(key):
    """Cargador directo: lee el JSON y hace from_dict (gate de Fase 1)."""
    import flowsheet_model as fm
    path = os.path.join(DATA_DIR, f"{key}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return fm.Flowsheet.from_dict(d)


def _load_via_registry(key):
    """Cargador vía examples_registry.load_example (gate de Fase 2).
    Verifica que el camino de carga real de la UI da los mismos golden."""
    import examples_registry as reg
    return reg.load_example(key)


def run_gate(via_registry=False):
    _headless_mocks()
    import flowsheet_solver as fsv

    if not os.path.isdir(DATA_DIR):
        print(f"✗ No existe {DATA_DIR}. Corré export_examples.py primero.")
        return 1
    if not os.path.isfile(GOLDEN_PATH):
        print(f"✗ No existe {GOLDEN_PATH}. Corré export_examples.py primero.")
        return 1

    baseline = _load_golden_baseline()
    load = _load_via_registry if via_registry else _load_direct
    modo = "vía registry" if via_registry else "from_dict directo"

    print("=" * 78)
    print(f"GATE de regresión ({modo}) — JSON → solve vs golden congelado (Fase 1)")
    print("=" * 78)

    n_ok = 0
    fails = []
    for key in sorted(baseline):
        try:
            fs = load(key)
        except Exception as e:
            fails.append((key, [("carga", "<ok>", f"{type(e).__name__}: {e}")]))
            print(f"  ✗ {key:18s} error de carga: {e}")
            continue
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", action="store_true",
                        help="Cargar vía examples_registry (gate Fase 2) "
                             "en vez de from_dict directo.")
    args = parser.parse_args()
    sys.exit(run_gate(via_registry=args.registry))
