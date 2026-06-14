"""GATE solver — S1 tear-fix: `_choose_tear` excluye streams lockeados.

Un stream `mass_flow_locked=True` es una FRONTERA DE DISEÑO (lock del user),
no una variable libre del reciclo → no puede ser elegido como tear.  S1
asegura que `_choose_tear` lo excluya tanto en el camino back-edge como en el
fallback, manteniendo el ranking por role para el resto.

Patrón medido (hda_full gas loop): con un back-edge lockeado (S-gas-recic) y
uno tearable (S-gas-pre), el viejo heurístico podía elegir el lockeado; S1
fuerza la elección del tearable.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import flowsheet_solver as fsolv
from flowsheet_model import Flowsheet, Block, Stream


def _mk_loop_with_locked_backedge():
    """Mixer → Reactor → Splitter → (back-edges al Mixer).

    El SCC {MIX, RX, SPL} tiene un feed externo al MIX.  Dos back-edges
    re-entran al MIX: S-rec-lock (lockeado, frontera de diseño) y
    S-rec-free (tearable).  S1 debe elegir S-rec-free.
    """
    fs = Flowsheet()
    b_mix = fs.new_id()
    fs.blocks[b_mix] = Block(id=b_mix, name="MIX",
                             eq_type="Mixer — static", S=1.0, x=0, y=0)
    b_rx = fs.new_id()
    fs.blocks[b_rx] = Block(id=b_rx, name="RX",
                            eq_type="Reactor — jacketed non-agit.",
                            S=1.0, x=200, y=0)
    b_spl = fs.new_id()
    fs.blocks[b_spl] = Block(id=b_spl, name="SPL",
                             eq_type="Splitter — flow divider",
                             S=1.0, x=400, y=0)

    feed = Stream(id=fs.new_id(), name="S-feed", src=-1, dst=b_mix,
                  mass_flow=1000.0)
    feed.mass_flow_locked = True
    fs.streams[feed.id] = feed

    s_a = Stream(id=fs.new_id(), name="S-a", src=b_mix, dst=b_rx,
                 mass_flow=0.0, role="internal")
    fs.streams[s_a.id] = s_a
    s_b = Stream(id=fs.new_id(), name="S-b", src=b_rx, dst=b_spl,
                 mass_flow=0.0, role="internal")
    fs.streams[s_b.id] = s_b

    # Dos back-edges SPL → MIX: uno lockeado, uno libre.
    s_lock = Stream(id=fs.new_id(), name="S-rec-lock", src=b_spl, dst=b_mix,
                    mass_flow=500.0, role="recycle")
    s_lock.mass_flow_locked = True
    fs.streams[s_lock.id] = s_lock
    s_free = Stream(id=fs.new_id(), name="S-rec-free", src=b_spl, dst=b_mix,
                    mass_flow=0.0, role="recycle")
    fs.streams[s_free.id] = s_free
    return fs, {b_mix, b_rx, b_spl}


def test_s1_excludes_locked_backedge():
    fs, scc_bids = _mk_loop_with_locked_backedge()
    scc_streams = fsolv._streams_in_scc(scc_bids, fs)
    tear = fsolv._choose_tear(scc_streams, fs, scc_bids)
    assert tear is not None, "debería elegir un tear tearable"
    assert tear.name == "S-rec-free", (
        f"S1: el tear debe ser el back-edge NO lockeado, no {tear.name}")
    assert not getattr(tear, "mass_flow_locked", False)


def test_s1_no_tearable_candidate_returns_none():
    """Si TODOS los back-edges (y unknowns) están lockeados, no hay tear
    elegible → None (no se puede tearear una frontera de diseño)."""
    fs, scc_bids = _mk_loop_with_locked_backedge()
    # lockear también el back-edge libre y limpiar el unknown interno
    for s in fs.streams.values():
        if s.name == "S-rec-free":
            s.mass_flow = 500.0
            s.mass_flow_locked = True
    # fijar internos para que no haya unknowns tearables
    for s in fs.streams.values():
        if s.name in ("S-a", "S-b"):
            s.mass_flow = 1500.0
            s.mass_flow_locked = True
    scc_streams = fsolv._streams_in_scc(scc_bids, fs)
    tear = fsolv._choose_tear(scc_streams, fs, scc_bids)
    assert tear is None, f"sin candidato tearable debe devolver None, dio {tear}"


def test_s1_keeps_role_ranking_among_tearable():
    """Entre varios back-edges tearables, mantiene el ranking por role
    (recycle > internal)."""
    fs, scc_bids = _mk_loop_with_locked_backedge()
    # deslockear el lock y bajarle el role a internal; el recycle libre gana
    for s in fs.streams.values():
        if s.name == "S-rec-lock":
            s.mass_flow = 0.0
            s.mass_flow_locked = False
            s.role = "internal"
    scc_streams = fsolv._streams_in_scc(scc_bids, fs)
    tear = fsolv._choose_tear(scc_streams, fs, scc_bids)
    assert tear.name == "S-rec-free", (
        f"con dos tearables, gana el role 'recycle', no {tear.name}")
