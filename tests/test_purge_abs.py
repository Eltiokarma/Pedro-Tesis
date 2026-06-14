"""PR-A2 / PR-A2.2 — [W-PURGE-ABS]: purga absoluta dentro de un loop.

PR-A2 detectó el patrón topológico (salida terminal lockeada + hermana
recirculante en un loop de reciclo no determinado).  PR-A2.2 añadió el
discriminador FÍSICO por COMPOSICIÓN: una PURGA es un split físico (la
salida que purga y la que recircula llevan la MISMA composición — mismo gas
dividido); un SEPARADOR reparte composiciones distintas a cada salida (cada
una es una fase/producto/corte).  Solo el split físico subdetermina el
caudal del reciclo.  (El rol NO discrimina: la purga canónica de haber_rec
es role=waste — por eso A2.1, que filtraba por rol, estaba mal.)

Disparos finales sobre los 41: hda_full K-101 (purga de gas absoluta genuina
→ input para PR-G2 / Fase 2 de T29c).  NO disparan los separadores (comp
distinta) ni los loops ya determinados por splitter.

T29c (loop de gas vivo + makeup de H2): tras re-sintonizar la separación de
hda_full a un estado estacionario coherente, T-103 dejó de ser una purga
absoluta (S-14/S-pesados ahora es tolueno puro, mientras S-13 recircula
tolueno+benceno) y pasó a clasificar como SEPARADOR real (comp distinta) →
ya no dispara.  Queda K-101 como única purga absoluta (el reparto del gas de
reciclo sigue lockeado; su conversión a fracción es la Fase 2 diferida).
"""
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import examples_registry as reg
import flowsheet_solver as fsv
from flowsheet_model import Flowsheet, Block, Stream

_TAG = "[W-PURGE-ABS]"


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
def test_dispara_en_purgas_genuinas():
    # hda_full K-101 (gas de reciclo): S-purga ≡ S-gas-pre (mismo gas dividido).
    # NOTA: industrial V-301 (S-blowdown) ERA un disparo, pero PR-G2a lo
    # convirtió a splitter (purga = fracción) → ya no dispara.
    # NOTA: hda_full T-103 ERA un disparo, pero T29c re-sintonizó la
    # separación → ahora separa de verdad (comp distinta) → no dispara
    # (ver test_no_dispara_en_separadores).
    casos = [("hda_full", "K-101")]    # S-purga ≡ S-gas-pre (benzene/H2/CH4)
    for clave, blk in casos:
        _, _, blocks = _purge_blocks(clave)
        assert blk in blocks, f"{clave}/{blk}: purga genuina debería disparar, got {blocks}"


# ── NO dispara en SEPARADORES (comp distinta a cada salida) ─────────────
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


def test_disparos_exactos_en_los_41():
    # PR-G2a convirtió industrial V-301 a splitter; T29c re-sintonizó la
    # separación de hda_full (T-103 ahora separa de verdad) → queda 1 disparo:
    # K-101, la única purga de gas todavía lockeada en absoluto (Fase 2).
    got = set()
    for e in reg.list_examples():
        _, _, blocks = _purge_blocks(e["clave"])
        for b in blocks:
            got.add((e["clave"], b))
    assert got == {("hda_full", "K-101")}, \
        f"set de disparos inesperado: {got}"


def test_industrial_v301_convertido_no_dispara():
    """PR-G2a: V-301 pasó a splitter (purga de vapor = fracción) → el
    [W-PURGE-ABS] que disparaba en A2.2 ya no aparece."""
    fs, _, blocks = _purge_blocks("industrial")
    assert "V-301" not in blocks
    v301 = next(b for b in fs.blocks.values() if b.name == "V-301")
    assert v301.splitter_active


# ── loops determinados por splitter NO disparan ─────────────────────────
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

    f = S(name="S-feed", src=-1, dst=mix, mass_flow=1000.0, role="feed",
          composition={"a": 0.5, "b": 0.5}, main_component="a")
    f.mass_flow_locked = True
    f.composition_locked = True
    f.start_xy = [-100.0, 0.0]
    S(name="S-a", src=mix, dst=sep, mass_flow=0.0)
    if distinct:
        cp_p, cp_r = {"a": 0.9, "b": 0.1}, {"a": 0.1, "b": 0.9}
    else:
        cp_p, cp_r = {"a": 0.5, "b": 0.5}, {"a": 0.5, "b": 0.5}
    p = S(name="S-purge", src=sep, dst=sink, mass_flow=200.0,
          composition=cp_p, main_component="a")
    p.mass_flow_locked = True
    p.composition_locked = True
    r = S(name="S-rec", src=sep, dst=mix, mass_flow=0.0,
          composition=cp_r, main_component="a")
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
def test_advisory_no_altera_overall_status():
    import json
    golden_path = os.path.join(os.path.dirname(__file__), "..", "data",
                               "examples", "_golden.json")
    with open(golden_path, encoding="utf-8") as f:
        golden = json.load(f)
    for clave, g in golden.items():
        fs = reg.load_example(clave)
        res = fsv.solve(fs)
        assert res.overall_status == g["overall_status"], \
            f"{clave}: overall_status cambió"
