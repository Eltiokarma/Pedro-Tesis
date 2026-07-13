"""CAPA 3 — convergencia multi-tear simultánea (Broyden).

Verifica el corazón del motor: `_solve_recycle_broyden` / `_solve_recycle_multitear`.
  - converge el loop ACOPLADO (ancla) al SS exacto, con el vector de tears
    EVOLUCIONANDO (no un 'converged' falso a 0);
  - dim-1 (mono) ≈ Wegstein (no regresiona el caso simple);
  - detecta la NO-convergencia (no reporta falso éxito si no llegó).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import flowsheet_solver as F
from flowsheet_model import Flowsheet, Block, Stream
from tests.test_multitear_anchor import build_dual_recycle_fs, EXPECTED_SS


def _recycle_scc(fs):
    return max((s for s in F._strongly_connected_components(fs)
                if F._is_recycle_scc(s, fs)), key=len)


def _mk_mono_recycle_fs(feed=100.0, rec_frac=0.5):
    """Mono-reciclo: Feed → M(mixer) → X(splitter: forward + recycle).

    SS exacto: T = Feed/(1−rec_frac); recycle = rec_frac·T.
    Con feed=100, rec_frac=0.5 → T=200, recycle=100, product=100.
    """
    fs = Flowsheet()
    M = fs.new_id()
    fs.blocks[M] = Block(id=M, name="M", eq_type="Mixer — static",
                         S=1.0, x=0, y=0)
    X = fs.new_id()
    fs.blocks[X] = Block(id=X, name="X",
                         eq_type="Splitter — flow divider", S=1.0, x=200, y=0)
    fs.blocks[X].splitter_active = True
    fs.blocks[X].splitter_fractions = [1.0 - rec_frac, rec_frac]  # [fwd, rec]
    W = {"water": 1.0}

    def S(nm, src, dst, m=0.0, lock=False, role="internal"):
        sid = fs.new_id()
        s = Stream(id=sid, name=nm, src=src, dst=dst, mass_flow=m,
                   composition=dict(W), main_component="water",
                   phase="liquid", role=role)
        s.mass_flow_locked = lock
        fs.streams[sid] = s
        return s

    S("Feed", -1, M, feed, lock=True, role="feed")
    S("S-t", M, X)
    S("Prod", X, -1, role="product")
    S("Rec", X, M, role="recycle")
    return fs


def test_broyden_converge_ancla_vector_evoluciona():
    fs = build_dual_recycle_fs()
    scc = _recycle_scc(fs)
    tears = F._choose_tears(scc, fs)
    rs = F._solve_recycle_broyden(fs, scc, tears)
    assert rs.converged, f"Broyden no convergió: {rs.history}"
    # el vector de tears EVOLUCIONA (no congelado en el guess)
    assert len(rs.history) >= 3
    assert abs(rs.history[0] - rs.history[-1]) > 1.0, \
        f"el tear no evolucionó: {rs.history}"
    # SS exacto: sum(tears) = R1+R2 = 300
    assert abs(rs.final_value - (EXPECTED_SS["R1"] + EXPECTED_SS["R2"])) < 0.5


def test_broyden_dim1_igual_a_wegstein():
    """En un mono-reciclo, Broyden (forzado dim-1) da el mismo SS que el
    Wegstein escalar → no regresiona el caso simple."""
    fs_w = _mk_mono_recycle_fs()
    scc_w = _recycle_scc(fs_w)
    rs_w = F._solve_recycle_wegstein(fs_w, scc_w)

    fs_b = _mk_mono_recycle_fs()
    scc_b = _recycle_scc(fs_b)
    tears = F._choose_tears(scc_b, fs_b)
    assert len(tears) == 1
    rs_b = F._solve_recycle_broyden(fs_b, scc_b, tears)

    assert rs_w.converged and rs_b.converged
    # ambos llegan al mismo caudal de reciclo (100) ± tol
    assert abs(rs_w.final_value - rs_b.final_value) < 0.5, \
        f"wegstein={rs_w.final_value} broyden={rs_b.final_value}"
    assert abs(rs_b.final_value - 100.0) < 0.5


def test_dispatcher_mono_delega_en_wegstein():
    """El dispatcher manda los mono-reciclo al Wegstein (byte-idéntico)."""
    fs = _mk_mono_recycle_fs()
    scc = _recycle_scc(fs)
    rs = F._solve_recycle_multitear(fs, scc)
    assert rs.converged
    assert abs(rs.final_value - 100.0) < 0.5


def test_broyden_detecta_no_convergencia():
    """Con max_iter=1 sobre el loop acoplado, Broyden NO alcanza el SS →
    debe reportar converged=False (no un falso éxito)."""
    fs = build_dual_recycle_fs()
    scc = _recycle_scc(fs)
    tears = F._choose_tears(scc, fs)
    rs = F._solve_recycle_broyden(fs, scc, tears, max_iter=1)
    assert not rs.converged, "no debe declarar convergencia en 1 iteración"
