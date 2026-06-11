"""GATE solver — lazos de servicio cerrados vs reciclos de proceso.

Protege la clasificación de SCCs del solver (_is_pure_service_scc):

  (a) un lazo de circulación de servicio puro (bomba→header→HX, todas
      las aristas auto_aux) NO se resuelve por tear+Wegstein — su
      caudal es analítico (m = Q/(cp·ΔT) desde el duty, via
      size_utility_streams) y el solver lo reporta como línea
      informativa, no como '⚠ Wegstein NO convergió';

  (b) un reciclo de PROCESO real sigue yendo a Wegstein y converge —
      la exención es solo para SCCs 100% aux (criterio conservador:
      cualquier corriente de proceso en el ciclo → Wegstein como
      siempre).

  (c) integración: el ejemplo metanol con auxiliares materializadas
      queda sin warnings espurios y con los caudales analíticos
      poblados.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import equipment_auxiliaries as eaux
import equipment_costs as ec
import flowsheet_solver as fsolv
from flowsheet_model import Flowsheet, Block, Stream


def _mk_service_loop_fs():
    """HX de proceso (agua 80→40 °C) + lazo cerrado de cooling water
    creado por equipment_auxiliaries (header + bomba + 3 aristas
    auto_aux).  El SCC resultante es 100% aux en sus corrientes."""
    fs = Flowsheet()
    hx_id = fs.new_id()
    fs.blocks[hx_id] = Block(id=hx_id, name="E-1",
                             eq_type="Heat exch. — fixed tube",
                             S=1.0, x=100.0, y=100.0)
    sid = fs.new_id()
    s_in = Stream(id=sid, name="S-hot", src=-1, dst=hx_id,
                  mass_flow=5000.0, temperature=80.0,
                  composition={"water": 1.0}, main_component="water",
                  phase="liquid")
    s_in.mass_flow_locked = True
    s_in.temperature_locked = True
    s_in.composition_locked = True
    s_in.start_xy = [0.0, 100.0]
    fs.streams[sid] = s_in
    sid2 = fs.new_id()
    s_out = Stream(id=sid2, name="S-cold", src=hx_id, dst=-1,
                   temperature=40.0, composition={"water": 1.0},
                   main_component="water", phase="liquid")
    s_out.temperature_locked = True
    s_out.end_xy = [300.0, 100.0]
    fs.streams[sid2] = s_out
    created = eaux.instantiate_auxiliaries(fs, fs.blocks[hx_id])
    assert created, "instantiate_auxiliaries no creó el lazo"
    return fs, hx_id


def _mk_process_recycle_fs():
    """Mixer → HX → Splitter con purga al estado estacionario
    (producto lockeado = feed) y reciclo desconocido: SCC de proceso
    puro que requiere tear + Wegstein."""
    fs = Flowsheet()
    b_mix = fs.new_id()
    fs.blocks[b_mix] = Block(id=b_mix, name="MIX",
                             eq_type="Mixer — static", S=1.0, x=0, y=0)
    b_hx = fs.new_id()
    fs.blocks[b_hx] = Block(id=b_hx, name="E-2",
                            eq_type="Heat exch. — fixed tube",
                            S=1.0, x=200, y=0)
    b_spl = fs.new_id()
    fs.blocks[b_spl] = Block(id=b_spl, name="SPL",
                             eq_type="Splitter — flow divider",
                             S=1.0, x=400, y=0)
    sid = fs.new_id()
    feed = Stream(id=sid, name="S-feed", src=-1, dst=b_mix,
                  mass_flow=1000.0)
    feed.mass_flow_locked = True
    feed.start_xy = [-100.0, 0.0]
    fs.streams[sid] = feed
    sid = fs.new_id()
    fs.streams[sid] = Stream(id=sid, name="S-a", src=b_mix, dst=b_hx,
                             mass_flow=0.0)
    sid = fs.new_id()
    fs.streams[sid] = Stream(id=sid, name="S-b", src=b_hx, dst=b_spl,
                             mass_flow=0.0)
    sid = fs.new_id()
    prod = Stream(id=sid, name="S-prod", src=b_spl, dst=-1,
                  mass_flow=1000.0)
    prod.mass_flow_locked = True
    prod.end_xy = [600.0, 0.0]
    fs.streams[sid] = prod
    sid = fs.new_id()
    fs.streams[sid] = Stream(id=sid, name="S-rec", src=b_spl, dst=b_mix,
                             mass_flow=0.0)
    return fs


# ── (a) lazo de servicio puro: sin Wegstein, reporte informativo ──────
def test_service_loop_exento_de_wegstein():
    fs, hx_id = _mk_service_loop_fs()
    # el SCC existe y es 100% aux en sus aristas
    sccs = [scc for scc in fsolv._strongly_connected_components(fs)
            if len(scc) > 1]
    assert len(sccs) == 1
    assert fsolv._is_pure_service_scc(sccs[0], fs)

    res = fsolv.solve(fs)
    # cero Wegstein sobre el lazo (ni convergido ni fallido)
    assert res.recycle_solutions == [], \
        f"el lazo de servicio fue a Wegstein: {res.recycle_solutions}"
    # reporte informativo presente, warning rojo ausente
    assert len(res.service_loops) == 1
    assert "Lazo de servicio detectado" in res.service_loops[0]
    assert "E-1" in res.service_loops[0]
    assert "NO convergió" not in res.summary()
    assert "Lazo de servicio detectado" in res.summary()


# ── (b) reciclo de proceso real: Wegstein corre y converge ────────────
def test_reciclo_de_proceso_sigue_en_wegstein():
    fs = _mk_process_recycle_fs()
    sccs = [scc for scc in fsolv._strongly_connected_components(fs)
            if len(scc) > 1]
    assert len(sccs) == 1
    assert not fsolv._is_pure_service_scc(sccs[0], fs)

    res = fsolv.solve(fs)
    assert len(res.recycle_solutions) == 1, \
        "el reciclo de proceso no fue a Wegstein"
    rs = res.recycle_solutions[0]
    assert rs.converged, f"Wegstein no convergió: {rs}"
    assert rs.tear_stream == "S-a"
    assert rs.final_value > 0
    assert res.service_loops == []


# ── criterio conservador: SCC mixto NO se exime ───────────────────────
def test_scc_mixto_no_se_exime():
    fs = _mk_process_recycle_fs()
    # marcar UNA arista del ciclo como auto_aux: el SCC pasa a mixto
    rec = next(s for s in fs.streams.values() if s.name == "S-rec")
    rec.auto_aux = True
    sccs = [scc for scc in fsolv._strongly_connected_components(fs)
            if len(scc) > 1]
    assert len(sccs) == 1
    assert not fsolv._is_pure_service_scc(sccs[0], fs), \
        "SCC mixto (proceso+aux) fue clasificado como lazo de servicio"


# ── (c) integración: metanol + aux sin warnings espurios ──────────────
def test_metanol_con_aux_sin_warnings_espurios():
    import examples_registry as reg
    fs = reg.load_example("methanol")
    fsolv.solve(fs)        # duties primero (como hace la UI)
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
    assert n >= 1, "metanol no instanció auxiliares"

    res = fsolv.solve(fs)
    no_conv = [rs for rs in res.recycle_solutions if not rs.converged]
    assert no_conv == [], f"warnings espurios: {no_conv}"
    assert len(res.service_loops) == 2
    # los caudales del lazo quedaron fijados analíticamente (> 0)
    aux_flows = [s.mass_flow for s in fs.streams.values()
                 if getattr(s, "auto_aux", False)
                 and (s.role or "") == "utility"]
    assert aux_flows and all(m > 0 for m in aux_flows), \
        f"caudales aux sin dimensionar: {aux_flows}"
    assert all("m = " in sl for sl in res.service_loops)
