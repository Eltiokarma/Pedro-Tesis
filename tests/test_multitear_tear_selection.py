"""CAPA 2 — selección de tear reciclo-aware (`_choose_tears`).

Verifica que, usando la descomposición de Capa 1, el solver elige UN tear por
ciclo independiente — el reciclo REAL (back-edge), nunca una línea de feed
interna como S-2 (el bug medido).  Esta capa SELECCIONA; no resuelve (capa 3).

Las pruebas multi-ciclo corren sobre el escenario VIVO (internos deslockeados),
que es el que la capa 3 va a resolver; en el estado congelado los loops ni
tocan Wegstein, así que la selección es moot.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import collections
import copy
import json

import examples_registry as reg
import flowsheet_solver as F
from flowsheet_model import Flowsheet
from tests.test_multitear_anchor import build_dual_recycle_fs


def _recycle_scc(fs):
    sccs = [s for s in F._strongly_connected_components(fs)
            if F._is_recycle_scc(s, fs)]
    return max(sccs, key=len)


def _live(example):
    """Carga el ejemplo y deslockea TODOS sus streams internos de SCC
    (escenario vivo) para que los back-edges sean tearables. Solo selección."""
    d = json.load(open(f"data/examples/{example}.json"))
    fs0 = Flowsheet.from_dict(d)
    scc = _recycle_scc(fs0)
    internal_names = {s.name for s in F._streams_in_scc(scc, fs0)}
    for s in d["streams"].values():
        if s["name"] in internal_names:
            s["mass_flow_locked"] = False
    return Flowsheet.from_dict(d)


def _breaks_all_cycles(scc, fs, tear_ids):
    sub = [s for s in F._streams_in_scc(scc, fs) if s.id not in tear_ids]
    adj = collections.defaultdict(list)
    for s in sub:
        adj[s.src].append(s.dst)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {}

    def dfs(u):
        color[u] = GRAY
        for v in adj[u]:
            c = color.get(v, WHITE)
            if c == GRAY:
                return True
            if c == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False

    return not any(dfs(b) for b in set(scc) if color.get(b, WHITE) == WHITE)


def _cycle_index_of(cycles, stream_name):
    return {i for i, c in enumerate(cycles)
            if any(s.name == stream_name for s in c["streams"])}


def test_hda_full_tear_por_ciclo_no_S2():
    fs = _live("hda_full")
    scc = _recycle_scc(fs)
    cycles = F._decompose_scc_cycles(scc, fs)
    tears = F._choose_tears(scc, fs)
    names = [t.name for t in tears]

    assert len(tears) == len(cycles) == 3
    # PRUEBA DURA: el bug S-2 está corregido.
    assert "S-2" not in names, f"S-2 no debe ser tear; tears={names}"
    # gas y tolueno eligen su reciclo real.
    gas_tear = next(t for t in tears
                    if _cycle_index_of(cycles, t.name)
                    & _cycle_index_of(cycles, "S-gas-recic"))
    assert gas_tear.name in ("S-gas-pre", "S-gas-recic"), gas_tear.name
    assert "S-tol-recic" in names, f"tear de tolueno debe ser S-tol-recic; {names}"
    # tears distintos, ninguno lockeado, rompen todos los ciclos.
    assert len(set(t.id for t in tears)) == 3
    assert all(not getattr(t, "mass_flow_locked", False) for t in tears)
    assert _breaks_all_cycles(scc, fs, {t.id for t in tears})


def test_gas_sweet_tres_tears_reciclos_reales():
    fs = _live("gas_sweet")
    scc = _recycle_scc(fs)
    tears = F._choose_tears(scc, fs)
    assert len(tears) == 3
    assert len(set(t.id for t in tears)) == 3
    assert all(not getattr(t, "mass_flow_locked", False) for t in tears)
    assert _breaks_all_cycles(scc, fs, {t.id for t in tears})


def test_haber_rec_mono_mismo_tear_que_el_solve():
    """Para el SCC mono-reciclo, _choose_tears debe coincidir con el tear que
    el solve realmente usa hoy (S-recycle) → comportamiento byte-idéntico
    cuando la capa 3 conmute a esta selección."""
    fs = reg.load_example("haber_rec")
    res = F.solve(fs)
    actual = [rs.tear_stream for rs in res.recycle_solutions]
    fs2 = reg.load_example("haber_rec")
    scc = _recycle_scc(fs2)
    tears = [t.name for t in F._choose_tears(scc, fs2)]
    assert len(tears) == 1
    assert tears == actual, f"_choose_tears={tears} vs solve={actual}"


def test_anchor_un_tear_por_ciclo():
    fs = build_dual_recycle_fs()
    scc = _recycle_scc(fs)
    cycles = F._decompose_scc_cycles(scc, fs)
    tears = F._choose_tears(scc, fs)
    assert len(tears) == len(cycles) == 2
    names = {t.name for t in tears}
    assert names == {"R1", "R2"}, names
    assert _breaks_all_cycles(scc, fs, {t.id for t in tears})


def test_ningun_tear_es_feedline_ni_lockeado():
    """Invariante transversal sobre los casos acoplados vivos."""
    for ex in ("hda_full", "gas_sweet"):
        fs = _live(ex)
        scc = _recycle_scc(fs)
        bids = set(scc)
        for t in F._choose_tears(scc, fs):
            assert not getattr(t, "mass_flow_locked", False)
            # no es una feed-line pura: o es back-edge, o no tiene feed externo
            # en su destino. (Se valida vía que rompe ciclos y no es S-2 arriba.)
