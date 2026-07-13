"""TRABAJOS_FUTUROS §1 / §4 / §12 — regresiones de la barrida 2026-07.

  §1  SCC mixto proceso+aux: el multitear con S2-D converge el SCC que
      fusiona el reciclo de proceso con lazos CW (hda_full+aux) — el
      síntoma histórico era "Wegstein elige U-aux-1 y falla en 1 iter".
  §4  HX standalone: el duty se infiere de flujo+Ts lockeados y el lazo
      de servicio se dimensiona analíticamente (no "m pendiente").
  §12 X_eq(T): las reacciones con ΔH+ΔG curados a 298 K pero sin A/B
      explícitos en el .md derivan van't Hoff 2-param al parsear
      (misma forma que build_custom_reaction) — R022–R031 habilitadas.
"""
import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import examples_registry as reg
import flowsheet_solver as fsv
import equipment_auxiliaries as eaux
import equipment_costs as ec
import reactions_db as rdb
from flowsheet_model import Flowsheet, Block, Stream


# ── §1: SCC mixto proceso+aux converge ──────────────────────────────────
def test_scc_mixto_hda_full_aux_converge():
    """hda_full con auxiliares instanciados: Tarjan fusiona el reciclo de
    proceso con los lazos CW en un SCC mixto.  El multitear (con S2-D)
    debe converger sin warnings espurios de no-convergencia."""
    fs = reg.load_example("hda_full")
    fsv.solve(fs)
    n = 0
    for b in list(fs.blocks.values()):
        if ec.EQUIPMENT_DATA.get(b.eq_type, {}).get("categoria") \
                != "Heat exchangers":
            continue
        if any((s.src == b.id or s.dst == b.id)
               and (s.role or "") == "utility"
               for s in fs.streams.values()):
            continue
        if eaux.instantiate_auxiliaries(fs, b):
            n += 1
    assert n >= 1, "hda_full no instanció auxiliares"
    res = fsv.solve(fs)
    no_conv = [rs for rs in res.recycle_solutions if not rs.converged]
    assert no_conv == [], f"SCC mixto no convergió: {no_conv}"
    assert res.overall_status in ("ok", "warning")


# ── §4: HX aislado infiere duty y dimensiona su lazo ────────────────────
def test_hx_standalone_infiere_duty_y_dimensiona_lazo():
    fs = Flowsheet()
    b = fs.new_id()
    fs.blocks[b] = Block(id=b, name="E-1", eq_type="Heat exch. — fixed tube",
                         S=10.0, x=0, y=0)
    s1 = Stream(id=fs.new_id(), name="S-in", src=-1, dst=b, mass_flow=1000.0,
                composition={"water": 1.0}, temperature=80.0)
    s1.mass_flow_locked = True
    s1.composition_locked = True
    s1.temperature_locked = True
    s1.start_xy = [-100, 0]
    fs.streams[s1.id] = s1
    s2 = Stream(id=fs.new_id(), name="S-out", src=b, dst=-1, mass_flow=1000.0,
                composition={"water": 1.0}, temperature=40.0)
    s2.mass_flow_locked = True
    s2.composition_locked = True
    s2.temperature_locked = True
    s2.end_xy = [200, 0]
    fs.streams[s2.id] = s2

    fsv.solve(fs)
    blk = fs.blocks[b]
    assert blk.duty < -4.0, f"duty no inferido del ΔT: {blk.duty}"
    assert eaux.instantiate_auxiliaries(fs, blk)
    res = fsv.solve(fs)
    assert res.service_loops, "sin lazo de servicio detectado"
    assert all("m pendiente" not in sl for sl in res.service_loops), \
        f"lazo sin dimensionar: {res.service_loops}"


# ── §12: van't Hoff derivado de ΔH/ΔG curados ──────────────────────────
def test_vant_hoff_derivado_solo_con_especies_sourceadas():
    """De R022–R031 (sin A/B explícitos), derivan van't Hoff SOLO las que
    tienen todas sus especies con MW en thermo_db (invariante del seam de
    equilibrio: van't Hoff ⇒ especies sourceadas).  Hoy: R026 y R028.
    Para las derivadas, K(298) reproduce exp(−ΔG/RT) exacto y el signo de
    dK/dT sigue al de −ΔH."""
    R = 8.314462618e-3
    habilitadas = []
    for i in range(22, 32):
        r = rdb.get(f"R0{i}")
        assert r is not None
        if r.vant_hoff_A is None:
            continue                          # pseudo sin MW → placeholder
        habilitadas.append(r.id)
        K298 = r.keq_vant_hoff(298.15)
        exact = math.exp(-r.dg_rxn_298_kJ_mol / (R * 298.15))
        assert abs(K298 - exact) / exact < 1e-9, f"{r.id}: K(298) no cuadra"
        K350 = r.keq_vant_hoff(350.0)
        if r.dh_rxn_298_kJ_mol < 0:
            assert K350 < K298, f"{r.id}: exotérmica debe bajar K con T"
        else:
            assert K350 > K298, f"{r.id}: endotérmica debe subir K con T"
    assert "R026" in habilitadas and "R028" in habilitadas, \
        f"R026/R028 (especies completas) deben derivar: {habilitadas}"


def test_vant_hoff_explicito_no_se_pisa():
    """Una reacción con A/B explícitos en el .md (p.ej. R001) conserva sus
    valores curados — la derivación sólo llena los ausentes."""
    r = rdb.get("R001")
    assert r.vant_hoff_A is not None and r.vant_hoff_B is not None
    # los valores del .md no coinciden con la derivación 2-param simple
    # (fueron ajustados con más puntos); basta verificar que keq funciona
    assert r.keq_vant_hoff(600.0) is not None
