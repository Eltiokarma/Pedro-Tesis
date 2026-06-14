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
    """Un bloque 1-in(lock 100)/1-out(0): normalmente mass_iteration deduce
    out=100.  Marcado como tear activo, NO se deduce (queda en 0)."""
    fs = Flowsheet()
    b = fs.new_id()
    fs.blocks[b] = Block(id=b, name="B", eq_type="Mixer — static",
                         S=1.0, x=0, y=0)
    si = Stream(id=fs.new_id(), name="in", src=-1, dst=b, mass_flow=100.0)
    si.mass_flow_locked = True
    fs.streams[si.id] = si
    so = Stream(id=fs.new_id(), name="out", src=b, dst=-1, mass_flow=0.0)
    fs.streams[so.id] = so

    # sin marcar → se deduce
    F._ACTIVE_TEAR_IDS = set()
    F._solve_mass_iteration(fs)
    assert so.mass_flow == 100.0

    # marcado como tear activo → NO se deduce
    so.mass_flow = 0.0
    F._ACTIVE_TEAR_IDS = {so.id}
    try:
        F._solve_mass_iteration(fs)
        assert so.mass_flow == 0.0, "el tear activo no debe deducirse por balance"
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
