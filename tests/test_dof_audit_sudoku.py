"""Frente 3 (auditoría frontend) — sistema sudoku / grados de libertad.

Protege tres propiedades del dof_audit sobre el set de ejemplos:

1. Los 58 ejemplos quedan EXACTAMENTE determinados (0 DOF libres, 0
   masa indeterminable). Antes de la sesión 2026-07-22 los 7 ejemplos
   con reciclo (hda, haber_rec, industrial, feed_effluent,
   nested_recycle, hen, cw_loop) daban falsos under-specificados: el
   audit propagaba solo forward y no sabía que el solver determina los
   lazos por convergencia del tearing (ahora: status "torn").
2. Perturbación under: quitar un lock necesario → el audit lo detecta.
3. Perturbación over: un lock que viola el balance de un bloque con
   todos sus streams lockeados → conflicto detectado (antes la rama
   "over" era código muerto: ningún *_dof podía ser negativo).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from examples_registry import list_examples, load_example
from dof_audit import analyze_flowsheet


EJEMPLOS_CON_RECICLO = ["hda", "haber_rec", "industrial", "feed_effluent",
                        "nested_recycle", "hen", "cw_loop"]


def _keys():
    return [e["clave"] for e in list_examples()]


# ══════════════════════════════════════════════════════════════════════
# 1. El sudoku cierra en los 58
# ══════════════════════════════════════════════════════════════════════
def test_58_ejemplos_exactamente_determinados():
    fallas = []
    for k in _keys():
        r = analyze_flowsheet(load_example(k))
        if r.total_dof != 0 or r.n_indeterminable_mass != 0 or r.n_over:
            fallas.append((k, r.total_dof, r.n_indeterminable_mass,
                           r.n_over))
    assert not fallas, f"ejemplos mal especificados: {fallas}"


@pytest.mark.parametrize("clave", EJEMPLOS_CON_RECICLO)
def test_reciclos_marcados_torn_no_under(clave):
    """Los lazos se reportan como 'torn' (convergencia), no como
    under-specificados."""
    r = analyze_flowsheet(load_example(clave))
    assert r.total_dof == 0, f"{clave}: dof={r.total_dof}"
    torn = [s.name for s in r.streams if s.mass_status == "torn"]
    assert torn, f"{clave}: sin streams torn (¿SCC no detectado?)"


def test_hda_reciclo_es_torn():
    r = analyze_flowsheet(load_example("hda"))
    torn = {s.name for s in r.streams if s.mass_status == "torn"}
    assert "S-9-recic" in torn


# ══════════════════════════════════════════════════════════════════════
# 2. Perturbación: quitar un lock → under-specificado
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("clave", ["soap", "distillation", "methanol"])
def test_quitar_lock_detecta_under(clave):
    """Al menos un lock del ejemplo es NECESARIO: quitarlo debe dejar
    el flowsheet under-specificado (si ninguno lo fuera, todos los
    locks serían redundantes y el sudoku no sería un sudoku)."""
    fs = load_example(clave)
    locked = [s.id for s in fs.streams.values()
              if getattr(s, "mass_flow_locked", False)]
    assert locked, f"{clave} sin locks de masa"
    detecto = False
    for sid in locked:
        fs = load_example(clave)   # estado limpio por intento
        fs.streams[sid].mass_flow_locked = False
        r = analyze_flowsheet(fs)
        if r.total_dof > 0 or r.n_indeterminable_mass > 0:
            detecto = True
            break
    assert detecto, (f"{clave}: se quitó cada lock de masa por separado "
                     f"y el audit nunca reportó under-especificación")


def test_quitar_todos_los_locks_es_under_masivo():
    fs = load_example("soap")
    for s in fs.streams.values():
        s.mass_flow_locked = False
    r = analyze_flowsheet(fs)
    assert r.n_indeterminable_mass > 0
    assert "UNDER" in r.summary or r.total_dof > 0


# ══════════════════════════════════════════════════════════════════════
# 3. Perturbación: lock conflictivo → over-specificado
# ══════════════════════════════════════════════════════════════════════
def test_lock_conflictivo_detecta_over():
    """Un bloque con TODOS sus streams lockeados cuyo balance no cierra
    es un conflicto entre locks: el solver no puede corregir ninguno."""
    fs = load_example("sugar")   # R-102 tiene todos sus streams lockeados
    target = None
    for b in fs.blocks.values():
        ins = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if (ins and outs
                and all(getattr(s, "mass_flow_locked", False)
                        for s in ins + outs)):
            target = (b, outs[0])
            break
    assert target, "sugar sin bloque completamente lockeado"
    _, out_stream = target
    out_stream.mass_flow *= 2.0    # sigue lockeado, ahora en conflicto
    r = analyze_flowsheet(fs)
    assert r.n_over >= 1, "conflicto entre locks no detectado"
    assert r.total_dof < 0
    assert "OVER" in r.summary


def test_ejemplos_sanos_no_flagean_over():
    """El patrón sancionado (locks que cierran por diseño) NO debe
    flagear over — solo el conflicto real."""
    for k in _keys():
        r = analyze_flowsheet(load_example(k))
        assert r.n_over == 0, f"{k}: falso positivo over"
