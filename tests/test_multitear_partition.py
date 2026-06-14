"""CAPA 1 — descomposición de SCC en reciclos independientes.

Verifica `flowsheet_solver._decompose_scc_cycles`: identifica los ciclos
fundamentales (circuit rank = E_int − V + 1) dentro de un SCC, SIN resolver ni
elegir tears (eso es capa 2/3).  Es pura estructura.

Anclas:
  - gas_sweet / hda_full: SCC acoplado → 3 ciclos DISTINTOS (el bug raíz era
    verlos como un solo loop). En hda_full, gas y tolueno quedan separados.
  - haber_rec / mono-reciclo: 1 ciclo (no se sobre-particiona lo simple).
  - industrial: cada uno de sus 3 SCC → 1 ciclo.
  - ancla sintética (#88): 2 ciclos independientes.
Invariante transversal: nº de ciclos == circuit rank, y el set de back-edges
rompe TODOS los ciclos (subgrafo restante acíclico).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import collections

import examples_registry as reg
import flowsheet_solver as F
from tests.test_multitear_anchor import build_dual_recycle_fs


def _recycle_sccs(fs):
    return [s for s in F._strongly_connected_components(fs)
            if F._is_recycle_scc(s, fs)]


def _remaining_is_acyclic(scc, fs, back_edge_ids):
    sub = [s for s in F._streams_in_scc(scc, fs) if s.id not in back_edge_ids]
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


def _assert_basis_valid(scc, fs):
    """Invariante transversal: #ciclos == circuit rank, back-edges distintos,
    y el set de back-edges rompe todos los ciclos."""
    rank = F._scc_circuit_rank(scc, fs)
    cycles = F._decompose_scc_cycles(scc, fs)
    assert len(cycles) == rank, f"esperaba {rank} ciclos, dio {len(cycles)}"
    be_ids = [c["back_edge"].id for c in cycles]
    assert len(set(be_ids)) == len(be_ids), "back-edges deben ser distintos"
    assert _remaining_is_acyclic(scc, fs, set(be_ids)), \
        "el set de back-edges debe romper TODOS los ciclos"
    # cada ciclo es un loop cerrado: todo bloque del ciclo tiene grado par
    for c in cycles:
        deg = collections.Counter()
        for s in c["streams"]:
            deg[s.src] += 1
            deg[s.dst] += 1
        assert all(d % 2 == 0 for d in deg.values()), \
            f"ciclo no cerrado: grados {dict(deg)}"
    return cycles


def test_gas_sweet_3_ciclos_acoplados():
    fs = reg.load_example("gas_sweet")
    sccs = _recycle_sccs(fs)
    assert len(sccs) == 1
    cycles = _assert_basis_valid(sccs[0], fs)
    assert len(cycles) == 3


def test_hda_full_gas_y_tolueno_son_ciclos_distintos():
    fs = reg.load_example("hda_full")
    sccs = _recycle_sccs(fs)
    assert len(sccs) == 1
    cycles = _assert_basis_valid(sccs[0], fs)
    assert len(cycles) == 3
    # El bug raíz: gas y tolueno fusionados en un solo loop. Acá deben caer
    # en ciclos DISTINTOS.
    def cycle_of(stream_name):
        idxs = [i for i, c in enumerate(cycles)
                if any(s.name == stream_name for s in c["streams"])]
        return set(idxs)
    gas = cycle_of("S-gas-recic")
    tol = cycle_of("S-tol-recic")
    assert gas and tol, f"gas={gas} tol={tol} (ambos deben aparecer)"
    assert gas.isdisjoint(tol), (
        f"gas (ciclos {gas}) y tolueno (ciclos {tol}) NO deben compartir ciclo")


def test_haber_rec_mono_un_solo_ciclo():
    fs = reg.load_example("haber_rec")
    sccs = _recycle_sccs(fs)
    assert len(sccs) == 1
    cycles = _assert_basis_valid(sccs[0], fs)
    assert len(cycles) == 1, "mono-reciclo no debe sobre-particionarse"


def test_industrial_tres_sccs_un_ciclo_cada_uno():
    fs = reg.load_example("industrial")
    sccs = _recycle_sccs(fs)
    assert len(sccs) == 3, f"industrial son 3 SCC paralelos, dio {len(sccs)}"
    for scc in sccs:
        cycles = _assert_basis_valid(scc, fs)
        assert len(cycles) == 1, "cada SCC paralelo es mono-reciclo"


def test_anchor_sintetico_dos_ciclos():
    fs = build_dual_recycle_fs()
    sccs = _recycle_sccs(fs)
    assert len(sccs) == 1
    cycles = _assert_basis_valid(sccs[0], fs)
    assert len(cycles) == 2
    # R1 y R2 son reciclos distintos.
    def cycle_of(name):
        return {i for i, c in enumerate(cycles)
                if any(s.name == name for s in c["streams"])}
    assert cycle_of("R1").isdisjoint(cycle_of("R2"))
