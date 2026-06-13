"""PR-A2 / PR-A2.1 — [W-PURGE-ABS]: purga absoluta lockeada dentro de un loop.

PR-A2 detectó el patrón topológico (purga terminal lockeada + hermana
recirculante en un loop de reciclo no determinado).  PR-A2.1 añadió el
filtro por FUNCIÓN: las salidas role product/waste/utility son specs de
diseño que abandonan el loop por definición (su caudal NO es un grado de
libertad del reciclo), y las columnas reparten cortes, no gas de reciclo.
Tras el filtro, los 7 disparos de PR-A2 sobre los 41 ejemplos eran TODOS
falsos positivos → 0 disparos reales; el detector queda armado para el
patrón genuino (salida INTERNA en un separador de fase), verificado con un
flowsheet sintético.
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


# ── PR-A2.1: los 7 candidatos de PR-A2 eran falsos positivos ────────────
# (product/waste terminales, o cortes de columna) → ya NO disparan.
def test_ex_candidatos_pra2_ya_no_disparan():
    casos = [
        ("hda", "V-101"),          # S-purga-H2  role=product
        ("hda_full", "K-101"),     # S-purga     role=product
        ("hda_full", "T-101"),     # S-7-light   Tower (corte)
        ("hda_full", "T-103"),     # S-14        Tower (corte)
        ("gas_sweet", "T-101"),    # S-gas-dulce role=product
        ("gas_sweet", "V-101"),    # S-flash-vap role=product
        ("industrial", "V-301"),   # S-blowdown  role=waste
    ]
    for clave, blk in casos:
        _, _, blocks = _purge_blocks(clave)
        assert blk not in blocks, \
            f"{clave}/{blk}: spec terminal/corte, no debería disparar [W-PURGE-ABS]"


def test_ningun_ejemplo_de_los_41_dispara():
    total = 0
    for e in reg.list_examples():
        _, _, blocks = _purge_blocks(e["clave"])
        total += len(blocks)
    assert total == 0, f"esperaba 0 disparos reales tras el filtro de rol, hay {total}"


# ── controles previos (siguen válidos) ──────────────────────────────────
def test_no_dispara_haber_rec_ni_industrial_determinados():
    for clave, blk in [("haber_rec", "V-102"), ("haber_rec", "V-101"),
                       ("industrial", "V-203"), ("industrial", "V-201")]:
        _, _, blocks = _purge_blocks(clave)
        assert blk not in blocks


# ── POSITIVO SINTÉTICO: el detector SIGUE VIVO ──────────────────────────
def _mk_genuine_purge_fs():
    """Loop MIX→SEP→MIX donde SEP (separador de fase, Vessel) reparte el
    gas de reciclo con una purga INTERNA de flujo absoluto lockeado y una
    hermana que recircula: el patrón genuino de subdeterminación (haber_rec
    V-102 pre-G1) que [W-PURGE-ABS] DEBE marcar."""
    fs = Flowsheet()
    mix = fs.new_id()
    fs.blocks[mix] = Block(id=mix, name="MIX", eq_type="Mixer — static",
                           S=1, x=0, y=0)
    sep = fs.new_id()
    fs.blocks[sep] = Block(id=sep, name="SEP", eq_type="Vessel — vertical",
                           S=1, x=200, y=0)
    sink = fs.new_id()
    fs.blocks[sink] = Block(id=sink, name="SINK",
                            eq_type="Storage tank — cone roof", S=1, x=400, y=0)

    def S(**kw):
        i = fs.new_id()
        s = Stream(id=i, **kw)
        fs.streams[i] = s
        return s

    feed = S(name="S-feed", src=-1, dst=mix, mass_flow=1000.0, role="feed")
    feed.mass_flow_locked = True
    feed.start_xy = [-100.0, 0.0]
    S(name="S-a", src=mix, dst=sep, mass_flow=0.0, role="internal")
    purge = S(name="S-purge", src=sep, dst=sink, mass_flow=200.0,
              role="internal")            # purga INTERNA absoluta lockeada
    purge.mass_flow_locked = True
    S(name="S-rec", src=sep, dst=mix, mass_flow=0.0, role="internal")  # recircula
    return fs


def test_dispara_en_purga_interna_genuina_sintetica():
    fs = _mk_genuine_purge_fs()
    res = fsv.solve(fs)
    fired = [w for w in res.awareness_warnings
             if w.startswith(_TAG) and "SEP" in w]
    assert fired, "el detector debe seguir disparando en la purga interna genuina"


def test_no_dispara_si_la_purga_es_product():
    """Mismo loop, pero la purga es role=product → spec terminal legítima,
    NO debe disparar (es la diferencia que introduce PR-A2.1)."""
    fs = _mk_genuine_purge_fs()
    for s in fs.streams.values():
        if s.name == "S-purge":
            s.role = "product"
    res = fsv.solve(fs)
    fired = [w for w in res.awareness_warnings if w.startswith(_TAG)]
    assert not fired, f"role=product no debería disparar, got {fired}"


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
