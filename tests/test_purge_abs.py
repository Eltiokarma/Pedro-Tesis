"""Absolute-purge diagnostics: retain detection on invalid loops while
the industrial catalogue uses determined split fractions or true separations.
"""
import os
import re
from functools import lru_cache

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import examples_registry as reg
import flowsheet_solver as fsv
from flowsheet_model import Flowsheet, Block, Stream

_TAG = "[W-PURGE-ABS]"


@lru_cache(maxsize=None)
def _purge_blocks(clave):
    fs = reg.load_example(clave)
    res = fsv.solve(fs)
    blocks = set()
    for w in res.awareness_warnings:
        if w.startswith(_TAG):
            m = re.match(r"\[W-PURGE-ABS\] ([^:]+):", w)
            if m:
                blocks.add(m.group(1))
    return fs, res, blocks


# ── DISPARA en las purgas genuinas (split físico, comp idéntica) ────────
def test_hda_purga_de_gas_definida_por_fraccion():
    fs, result, blocks = _purge_blocks("hda_full")
    purge = next(s for s in fs.streams.values() if s.name == "S-purga")
    splitter = fs.blocks[purge.src]
    assert splitter.splitter_active
    assert not purge.mass_flow_locked
    assert purge.mass_flow > 0
    assert splitter.name not in blocks
    assert result.success


def test_no_dispara_en_separadores():
    casos = [("hda", "V-101"),         # H2/CH4 vs benzene/toluene
             ("hda_full", "T-101"),    # corte: benzene .1 vs .86
             ("hda_full", "T-103"),    # T29c: tolueno puro (S-14) vs tol+benc (S-13)
             ("gas_sweet", "T-101"),   # gas tratado vs amina rica
             ("gas_sweet", "V-101")]   # flash CO2 vs amina
    for clave, blk in casos:
        _, _, blocks = _purge_blocks(clave)
        assert blk not in blocks, \
            f"{clave}/{blk}: separador (comp distinta), no debería disparar"


def test_catalogo_sin_purgas_absolutas_indeterminadas():
    got = {(e["clave"], b) for e in reg.list_examples()
           for b in _purge_blocks(e["clave"])[2]}
    assert got == set(), f"Purgas absolutas no resueltas: {got}"


def test_caldera_integrada_tiene_purga_y_vapor_conservativos():
    fs, result, blocks = _purge_blocks("industrial")
    boiler = next(b for b in fs.blocks.values() if b.name == "F-301")
    outs = [s for s in fs.streams.values() if s.src == boiler.id]
    ins = [s for s in fs.streams.values() if s.dst == boiler.id]
    assert boiler.name not in blocks
    assert {s.phase for s in outs} == {"liquid", "vapor"}
    assert all(s.mass_flow > 0 for s in outs)
    assert abs(sum(s.mass_flow for s in ins) - sum(s.mass_flow for s in outs)) < 1e-6
    assert result.success


def test_no_dispara_loops_determinados():
    for clave, blk in [("haber_rec", "V-102"), ("haber_rec", "V-101"),
                       ("industrial", "V-203"), ("industrial", "V-201")]:
        _, _, blocks = _purge_blocks(clave)
        assert blk not in blocks


# ── helper de composición ───────────────────────────────────────────────
def test_comp_approx_equal():
    eq = fsv._comp_approx_equal
    assert eq({"a": 0.5, "b": 0.5}, {"a": 0.5, "b": 0.5})
    assert eq({"a": 0.50, "b": 0.50}, {"a": 0.515, "b": 0.485})   # dentro de tol
    assert not eq({"a": 0.9, "b": 0.1}, {"a": 0.1, "b": 0.9})     # distinta
    assert not eq({"a": 1.0}, {"a": 0.5, "b": 0.5})               # set distinto
    assert not eq({}, {"a": 1.0})                                 # vacía → False
    assert not eq(None, {"a": 1.0})


# ── POSITIVO / NEGATIVO sintéticos ──────────────────────────────────────
def _mk_loop_fs(distinct):
    """Loop MIX→SEP→MIX con purga absoluta lockeada + hermana recirculante.
    distinct=False → ambas salidas misma comp (SPLIT FÍSICO = purga → dispara).
    distinct=True  → comp distinta por salida (SEPARADOR → NO dispara)."""
    fs = Flowsheet()
    mix = fs.new_id()
    fs.blocks[mix] = Block(id=mix, name="MIX", eq_type="Mixer — static", S=1, x=0, y=0)
    sep = fs.new_id()
    fs.blocks[sep] = Block(id=sep, name="SEP", eq_type="Vessel — vertical", S=1, x=200, y=0)
    sink = fs.new_id()
    fs.blocks[sink] = Block(id=sink, name="SINK",
                            eq_type="Storage tank — cone roof", S=1, x=400, y=0)

    def S(**kw):
        i = fs.new_id()
        s = Stream(id=i, **kw)
        fs.streams[i] = s
        return s

    f = S(name="S-feed", src=0, dst=mix, mass_flow=1000.0, role="feed",
          composition={"nitrogen": 0.5, "oxygen": 0.5}, main_component="nitrogen")
    f.mass_flow_locked = True
    f.composition_locked = True
    f.start_xy = [-100.0, 0.0]
    S(name="S-a", src=mix, dst=sep, mass_flow=0.0)
    if distinct:
        cp_p, cp_r = {"nitrogen": 0.9, "oxygen": 0.1}, {"nitrogen": 0.1, "oxygen": 0.9}
    else:
        cp_p, cp_r = {"nitrogen": 0.5, "oxygen": 0.5}, {"nitrogen": 0.5, "oxygen": 0.5}
    p = S(name="S-purge", src=sep, dst=sink, mass_flow=200.0,
          composition=cp_p, main_component="nitrogen")
    p.mass_flow_locked = True
    p.composition_locked = True
    r = S(name="S-rec", src=sep, dst=mix, mass_flow=0.0,
          composition=cp_r, main_component="nitrogen")
    r.composition_locked = True
    return fs


def test_positivo_sintetico_purga_comp_identica_dispara():
    fs = _mk_loop_fs(distinct=False)
    res = fsv.solve(fs)
    assert any(w.startswith(_TAG) and "SEP" in w for w in res.awareness_warnings), \
        "purga de comp idéntica a la hermana recirculante debe disparar"


def test_negativo_sintetico_separador_comp_distinta_no_dispara():
    fs = _mk_loop_fs(distinct=True)
    res = fsv.solve(fs)
    assert not any(w.startswith(_TAG) for w in res.awareness_warnings), \
        "separador (comp distinta) con misma topología NO debe disparar"


# ── advisory: no altera overall_status ──────────────────────────────────
def test_advisory_no_altera_overall_status(monkeypatch):
    with_warnings = fsv.solve(_mk_loop_fs(distinct=False))
    assert any(w.startswith(_TAG) for w in with_warnings.awareness_warnings)
    monkeypatch.setattr(fsv, "_compute_awareness_warnings", lambda fs: [])
    without_warnings = fsv.solve(_mk_loop_fs(distinct=False))
    assert without_warnings.awareness_warnings == []
    assert with_warnings.overall_status == without_warnings.overall_status
    assert with_warnings.success == without_warnings.success
    # The advisory must not conceal the actual underdetermined-loop error.
    assert not with_warnings.success
