"""Frente 1 (auditoría frontend) — invariantes de la matriz por eq_type.

La matriz completa vive en `audit_frontend_matrix.py` (regenera
docs/AUDITORIA_FRONTEND_EQUIPOS_MATRIZ.md). Acá se congelan los
invariantes que la auditoría 2026-07-22 dejó verdes, más los dos fixes
de evidencia que salieron de ella:

  1. Todo eq_type del catálogo tiene glyph PFD propio y puertos
     catalogados (0 huecos).
  2. Los únicos tipos sin sizer son los 4 internos de columna
     (trays/packing) — la excepción deliberada documentada.
  3. Un expansor/turbina (compresor con P_out < P_in) muestra evidencia
     (antes: None — el inspector quedaba mudo aunque el solver computa
     la expansión y el W generado).
  4. Un reactor en modo 'equilibrium' sin lista de reacciones muestra
     modo/T_op/P_op (patrón sancionado), pero el default del dataclass
     ('equilibrium' en TODOS los bloques) NO hace que bombas o válvulas
     reporten evidencia de reactor.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from examples_registry import load_example
import flowsheet_solver as fsv
import inspector_evidence as ie


INTERNOS_DE_COLUMNA = {"Tray — sieve", "Tray — valve",
                       "Packing — random", "Packing — structured"}


# ══════════════════════════════════════════════════════════════════════
# 1-2. Invariantes de catálogo (sin resolver ejemplos — rápidos)
# ══════════════════════════════════════════════════════════════════════
def test_todo_eq_type_tiene_glyph_y_puertos():
    import equipment_costs as ec
    import equipment_ports as ep
    import pfd_symbols as pfd
    sin_glyph = [t for t in ec.EQUIPMENT_DATA
                 if not pfd.get_for_eq_type(t)]
    sin_ports = [t for t in ec.EQUIPMENT_DATA if not ep.get_ports(t)]
    assert not sin_glyph, f"eq_types sin glyph PFD: {sin_glyph}"
    assert not sin_ports, f"eq_types sin puertos: {sin_ports}"


def test_solo_internos_de_columna_sin_sizer():
    import equipment_costs as ec
    from equipment_sizing import SIZER_BY_EQTYPE, SIZER_BY_CAT
    sin_sizer = set()
    for t in ec.EQUIPMENT_DATA:
        cat = ec.EQUIPMENT_DATA[t].get("categoria", "")
        if t not in SIZER_BY_EQTYPE and cat not in SIZER_BY_CAT:
            sin_sizer.add(t)
    assert sin_sizer == INTERNOS_DE_COLUMNA, (
        f"huecos de sizer fuera de la excepción deliberada: "
        f"{sin_sizer ^ INTERNOS_DE_COLUMNA}")


# ══════════════════════════════════════════════════════════════════════
# 3. Evidencia de expansor/turbina
# ══════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def hno3_resuelto():
    fs = load_example("hno3")
    fsv.solve(fs)
    return fs


def test_expansor_muestra_evidencia(hno3_resuelto):
    fs = hno3_resuelto
    exp = next(b for b in fs.blocks.values()
               if "axial" in b.eq_type.lower())
    txt = ie.compressor_text(exp, fs)
    assert txt is not None, "expansor sin evidencia de texto"
    assert "expansor" in txt.lower()
    assert "W generada" in txt
    m = ie.compressor_metrics(exp, fs)
    assert m is not None, "expansor sin métricas"
    keys = {x["key"] for x in m["metrics"]}
    assert {"ratio_exp", "Tout"} <= keys
    wgen = next(x for x in m["metrics"] if x["key"] == "Wgen")
    assert float(wgen["value"].replace(",", "")) > 0


# ══════════════════════════════════════════════════════════════════════
# 4. Reactor equilibrium sin reacciones listadas
# ══════════════════════════════════════════════════════════════════════
def test_reactor_equilibrium_sin_reacciones_muestra_modo():
    fs = load_example("pfr")
    fsv.solve(fs)
    r = next(b for b in fs.blocks.values() if "Reactor" in b.eq_type)
    txt = ie.reactor_text(r)
    assert txt is not None
    assert "equilibrium" in txt


def test_default_equilibrium_no_leakea_a_no_reactores():
    fs = load_example("letdown")   # bomba + válvula, ambos con el
    for b in fs.blocks.values():   # default reactor_mode='equilibrium'
        assert ie.reactor_text(b) is None, (
            f"{b.eq_type} reporta evidencia de reactor")
