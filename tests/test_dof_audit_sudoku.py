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
from dof_audit import analyze_flowsheet, format_report
from flowsheet_model import Block, Flowsheet, Stream


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
    # Test contradictory boundary conditions independently of plant fixtures,
    # whose product flows are now calculated from component recoveries.
    fs = Flowsheet()
    fs.blocks[1] = Block(1, "Heater", "Heat exchanger", 1, duty_locked=True)
    fs.streams[2] = Stream(2, "feed", 0, 1, mass_flow=100,
                           mass_flow_locked=True, main_component="water")
    fs.streams[3] = Stream(3, "product", 1, 0, mass_flow=100,
                           mass_flow_locked=True, main_component="water")
    assert analyze_flowsheet(fs).n_over == 0
    fs.streams[3].mass_flow = 200
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


def test_component_recoveries_determine_outlets_but_not_feed():
    fs = Flowsheet()
    block = Block(1, "Separator", "Tower", 1,
                  component_recoveries={"gas": {"methane": .99}},
                  component_recovery_default_port="liquid")
    fs.blocks[1] = block
    fs.streams = {
        2: Stream(2, "feed", 0, 1, mass_flow=100, mass_flow_locked=True,
                  composition={"methane": .5, "water": .5}),
        3: Stream(3, "gas", 1, 0, src_port="gas"),
        4: Stream(4, "liquid", 1, 0, src_port="liquid"),
    }
    assert analyze_flowsheet(fs).n_indeterminable_mass == 2
    block.component_recovery_active = True
    assert analyze_flowsheet(fs).n_indeterminable_mass == 0
    fs.streams[2].mass_flow_locked = False
    assert analyze_flowsheet(fs).n_indeterminable_mass == 3


def test_mass_conflict_and_missing_energy_spec_do_not_cancel():
    fs = Flowsheet()
    fs.blocks[1] = Block(1, "Heater", "Heat exchanger", 1)
    fs.streams = {
        2: Stream(2, "feed", 0, 1, mass_flow=100,
                  mass_flow_locked=True, main_component="water"),
        3: Stream(3, "product", 1, 0, mass_flow=200,
                  mass_flow_locked=True, main_component="water"),
    }
    report = analyze_flowsheet(fs)
    block = report.blocks[0]
    assert (block.mass_dof, block.energy_dof, block.comp_dof) == (-1, 1, 0)
    assert block.overall == "mixed"
    assert report.n_under == report.n_over == report.n_mixed == 1
    assert report.n_ok == 0
    assert report.n_ok + report.n_under + report.n_over - report.n_mixed == report.n_blocks
    assert "MIXTO" in report.summary
    assert "BIEN ESPECIFICADO" not in report.summary
    assert "masa=-1, energia=+1" in format_report(report)


@pytest.mark.parametrize("fixed_circulation", [False, True])
def test_cooling_tower_requires_circulation_or_blowdown_spec(fixed_circulation):
    fs = Flowsheet()
    block = Block(1, "Tower", "Cooling tower", 1,
                  cooling_tower_active=True)
    fs.blocks[1] = block
    fs.streams = {
        2: Stream(2, "hot water", 0, 1, mass_flow=1000,
                  mass_flow_locked=True, main_component="water"),
        3: Stream(3, "air", 0, 1, mass_flow=5000,
                  mass_flow_locked=True, main_component="nitrogen"),
        4: Stream(4, "cold water", 1, 0, src_port="agua_fria", mass_flow=900),
        5: Stream(5, "blowdown", 1, 0, src_port="blowdown"),
        6: Stream(6, "exhaust", 1, 0, src_port="vapor_loss"),
    }
    assert analyze_flowsheet(fs).n_indeterminable_mass == 3
    if fixed_circulation:
        fs.streams[4].mass_flow_locked = True
    else:
        block.cooling_tower_blowdown_fraction = .01
    assert analyze_flowsheet(fs).n_indeterminable_mass == 0
