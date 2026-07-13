"""CAPA 4 — S2-B: el tear no se deduce por balance (cierre de RC2).

RC2 era la "deducción circular": `_solve_mass_iteration` deducía el tear por
balance, pisando el valor del paso de convergencia → cualquier guess se
auto-satisfacía → converged FALSO a 0.  S2-B marca los tears activos
(`_ACTIVE_TEAR_IDS`) y los excluye de la deducción por balance.

Verifica:
  - aislado: un stream marcado como tear activo NO se deduce por balance;
  - RC2 cerrado: hda_full vivo ya NO declara convergencia falsa (antes:
    conv=True iters=1 con interior colapsado; ahora: conv=False honesto);
  - el ancla sintética SIGUE convergiendo (S2-B no rompe la convergencia real);
  - haber_rec byte-idéntico.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import json

import examples_registry as reg
import flowsheet_solver as F
from flowsheet_model import Flowsheet, Block, Stream
from tests.test_multitear_anchor import build_dual_recycle_fs


def test_active_tear_not_deduced_by_balance():
    """Contrato S2-B refinado (TF §3): un tear activo SÍ puede PRODUCIRSE en
    su bloque FUENTE (deducción forward Σin−Σotros_out — necesaria cuando la
    fuente es un pass-through, p.ej. el compresor de reciclo K-202 de
    industrial), pero NUNCA deducirse en su bloque DESTINO (unknown_ins del
    mixer) — esa es la deducción circular RC2 que devolvía el propio guess."""
    # (a) FUENTE: 1-in(lock 100)/1-out(tear, 0) → se PRODUCE forward.
    fs = Flowsheet()
    b = fs.new_id()
    fs.blocks[b] = Block(id=b, name="B", eq_type="Mixer — static",
                         S=1.0, x=0, y=0)
    si = Stream(id=fs.new_id(), name="in", src=-1, dst=b, mass_flow=100.0)
    si.mass_flow_locked = True
    fs.streams[si.id] = si
    so = Stream(id=fs.new_id(), name="out", src=b, dst=-1, mass_flow=0.0)
    fs.streams[so.id] = so

    F._ACTIVE_TEAR_IDS = {so.id}
    try:
        F._solve_mass_iteration(fs)
        assert so.mass_flow == 100.0, \
            "el tear debe PRODUCIRSE en su bloque fuente (forward)"
    finally:
        F._ACTIVE_TEAR_IDS = set()

    # (b) DESTINO: mixer con out resuelto (stale del guess) y el tear como
    # única entrada desconocida → NO se deduce backward (el eco RC2).
    fs2 = Flowsheet()
    m = fs2.new_id()
    fs2.blocks[m] = Block(id=m, name="MIX", eq_type="Mixer — static",
                          S=1.0, x=0, y=0)
    f2 = Stream(id=fs2.new_id(), name="feed", src=-1, dst=m, mass_flow=50.0)
    f2.mass_flow_locked = True
    fs2.streams[f2.id] = f2
    tear2 = Stream(id=fs2.new_id(), name="rec", src=-1, dst=m, mass_flow=0.0)
    fs2.streams[tear2.id] = tear2
    out2 = Stream(id=fs2.new_id(), name="mix-out", src=m, dst=-1,
                  mass_flow=60.0)          # stale: propagado desde un guess
    fs2.streams[out2.id] = out2

    F._ACTIVE_TEAR_IDS = {tear2.id}
    try:
        F._solve_mass_iteration(fs2)
        assert tear2.mass_flow == 0.0, \
            "el tear NO debe deducirse backward en su bloque destino (RC2)"
    finally:
        F._ACTIVE_TEAR_IDS = set()


def test_rc2_cerrado_hda_full_no_converge_falso():
    """hda_full vivo: antes de S2-B el motor declaraba conv=True en 1 iter con
    el interior colapsado (S-5=0).  Con S2-B debe ser conv=False HONESTO (no
    hay productor del split sin S2-C → el residuo no cierra)."""
    d = json.load(open("data/examples/hda_full.json"))
    for s in d["streams"].values():
        if s["name"] in ("S-2", "S-4", "S-gas-recic", "S-11", "S-tol-recic"):
            s["mass_flow_locked"] = False
    fs = Flowsheet.from_dict(d)
    res = F.solve(fs)
    multi = [rs for rs in res.recycle_solutions if "+" in rs.tear_stream]
    assert multi, "hda_full vivo debe ir al solver multi-tear"
    rs = multi[0]
    # NO debe declarar convergencia (sería falsa: interior colapsa sin S2-C)
    assert not rs.converged, (
        "RC2: no debe declarar conv=True con el interior colapsado")
    # y el vector EVOLUCIONA (no congelado en el guess de un solo paso)
    assert len(rs.history) > 1


def test_ancla_sigue_convergiendo_con_s2b():
    fs = build_dual_recycle_fs()
    res = F.solve(fs)
    got = {s.name: s.mass_flow for s in fs.streams.values()}
    assert res.overall_status != "error"
    assert abs(got["S-a"] - 400.0) < 0.5
    assert abs(got["Prod"] - 100.0) < 0.5
    assert all(got[k] > 0 for k in ("S-a", "S-fwd", "R1", "R2", "Prod"))


def test_haber_rec_byte_identico_con_s2b():
    fs = reg.load_example("haber_rec")
    res = F.solve(fs)
    sols = [(rs.tear_stream, rs.converged, rs.iterations)
            for rs in res.recycle_solutions]
    assert sols == [("S-recycle", True, 3)], sols
    assert res.overall_status == "ok"
