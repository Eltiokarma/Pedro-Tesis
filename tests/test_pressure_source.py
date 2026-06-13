"""FASE 2 — principio de presión por dispositivo + duty auto-hidráulico.

Cubre el detector pressure_source (a/b/c), el origen del lock de presión y
el marcado duty_origin='auto-hidraulico'.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowsheet_model as fm
from flowsheet_model import Block, Stream, Flowsheet
from flowsheet_consistency_audit import audit_flowsheet


def _two_block(eq_type, p_in, p_out, dp=0.0, p_op=0.0):
    """Bloque B en el medio que sube la P de p_in a p_out, entre fuente y
    sumidero tontos.  Devuelve (fs, B)."""
    fs = Flowsheet()
    b = Block(id=1, name="B", eq_type=eq_type, S=1.0, delta_p_bar=dp, P_op_bar=p_op)
    src = Block(id=2, name="SRC", eq_type="Storage tank — cone roof", S=1.0)
    snk = Block(id=3, name="SNK", eq_type="Storage tank — cone roof", S=1.0)
    fs.blocks = {1: b, 2: src, 3: snk}
    si = Stream(id=10, name="in", src=2, dst=1, mass_flow=100.0,
                composition={"water": 1.0}, pressure_bar=p_in)
    so = Stream(id=11, name="out", src=1, dst=3, mass_flow=100.0,
                composition={"water": 1.0}, pressure_bar=p_out)
    fs.streams = {10: si, 11: so}
    return fs, b


def _ps(fs):
    return audit_flowsheet(fs).by_category('pressure_source')


# ── (a) no-rotativo crea presión ───────────────────────────────────────
def test_presion_creada_sin_dispositivo():
    fs, _ = _two_block("Fired heater — non-reformer", 1.0, 25.0)
    msgs = [f.message for f in _ps(fs) if 'sin dispositivo' in f.message]
    assert msgs, "horno que sube P 1→25 debe flagear 'sin dispositivo'"


def test_mixer_crea_presion():
    fs, _ = _two_block("Mixer — static", 1.0, 1.5)
    assert any('sin dispositivo' in f.message for f in _ps(fs))


def test_columna_no_flagea():
    """Una columna tiene gradiente de P propio → no es 'creada sin
    dispositivo'."""
    fs, _ = _two_block("Tower (column shell)", 1.0, 1.3)
    assert not any('sin dispositivo' in f.message for f in _ps(fs))


# ── (b) rotativo sin spec ──────────────────────────────────────────────
def test_rotativo_sin_spec():
    fs, _ = _two_block("Compressor — centrifugal", 1.0, 5.0, dp=0.0, p_op=0.0)
    assert any('sin spec' in f.message for f in _ps(fs))


def test_rotativo_con_delta_p_ok():
    fs, _ = _two_block("Compressor — centrifugal", 1.0, 5.0, dp=4.0)
    assert not any('sin spec' in f.message for f in _ps(fs))


def test_rotativo_con_p_op_ok():
    fs, _ = _two_block("Compressor — centrifugal", 1.0, 5.0, dp=0.0, p_op=5.0)
    assert not any('sin spec' in f.message for f in _ps(fs))


# ── (c) origen del lock de presión ─────────────────────────────────────
def test_lock_heuristico_flagea_user_no():
    fs, _ = _two_block("Compressor — centrifugal", 1.0, 5.0, dp=4.0)
    so = fs.streams[11]
    so.pressure_locked = True
    so.pressure_lock_origin = "heuristic"
    assert any(f.target_kind == 'stream' and 'HEURÍSTICO' in f.message
               for f in _ps(fs))
    # marcado como 'user' → ya no se flagea
    so.pressure_lock_origin = "user"
    assert not any(f.target_kind == 'stream' for f in _ps(fs))


# ── from_dict: origen heurístico por default en JSONs viejos ───────────
def test_from_dict_origen_heuristico_default():
    d = {"streams": {"1": {"id": 1, "name": "S", "src": 1, "dst": 2,
                            "mass_flow": 10.0, "pressure_bar": 50.0,
                            "pressure_locked": True}},
         "blocks": {}, "_next_id": 3}
    fs = Flowsheet.from_dict(d)
    assert fs.streams[1].pressure_lock_origin == "heuristic"
    # round-trip estable
    d2 = fs.to_dict(); d3 = Flowsheet.from_dict(d2).to_dict()
    assert d2 == d3


# ── duty_origin: auto-hidráulico al auto-dimensionar ───────────────────
def test_duty_origin_auto_hidraulico():
    """Un compresor sin ΔP pero con un producto a P locked downstream:
    el solver hidráulico auto-dimensiona ΔP y marca duty_origin."""
    import flowsheet_solver as fsv
    fs = Flowsheet()
    k = Block(id=1, name="K-1", eq_type="Compressor — centrifugal", S=1.0,
              efficiency=0.75)
    src = Block(id=2, name="SRC", eq_type="Storage tank — cone roof", S=1.0)
    snk = Block(id=3, name="SNK", eq_type="Storage tank — cone roof", S=1.0)
    fs.blocks = {1: k, 2: src, 3: snk}
    si = Stream(id=10, name="feed", src=2, dst=1, mass_flow=10000.0,
                composition={"nitrogen": 0.5, "hydrogen": 0.5},
                pressure_bar=1.013, pressure_locked=True,
                pressure_lock_origin="user", temperature=25.0)
    so = Stream(id=11, name="disch", src=1, dst=3, mass_flow=10000.0,
                composition={"nitrogen": 0.5, "hydrogen": 0.5},
                pressure_bar=20.0, pressure_locked=True,
                pressure_lock_origin="user", temperature=25.0)
    fs.streams = {10: si, 11: so}
    fsv.solve_pressure_hydraulic(fs)
    assert abs(k.delta_p_bar) > 1.0, "ΔP no auto-dimensionado"
    assert k.duty_origin == "auto-hidraulico", \
        f"duty_origin={k.duty_origin!r} (esperado auto-hidraulico)"
    assert k.duty > 0


def test_duty_origin_real_example():
    """En un ejemplo real con compresor auto-dimensionado y duty NO lockeado,
    el solver marca duty_origin='auto-hidraulico'."""
    import flowsheet_solver as fsv, json
    fs = fm.Flowsheet.from_dict(json.load(
        open(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "data", "examples", "acetic.json"))))
    fsv.solve(fs)
    k = next(b for b in fs.blocks.values() if b.name == "K-101")
    assert k.duty_origin == "auto-hidraulico"
