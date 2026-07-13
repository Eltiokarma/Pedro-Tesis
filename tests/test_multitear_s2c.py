"""CAPA 5 — S2-C: separador v/l pasivo degenerado en loop vivo → flash activo.

Un separador vapor/líquido PASIVO que, al resolver su loop vivo, da un split
DEGENERADO (una salida ≈0) se re-resuelve como FLASH ACTIVO (método por
`_flash_method`, P/T de operación propagadas).  Esto rompe la degeneración y el
reciclo converge de verdad.

REGLA por FÍSICA (a-fix: separador v/l con comp declarada distinta · b: pasivo ·
c-fix: degenera), NUNCA por nombre.  Validada con un ANCLA SINTÉTICA acoplada
(H₂/benceno) cuyo balance cierra a mano; hda_full real se enciende en Capa 6
(necesita racionalizar el lock de purga a masa fija → underdetermined).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import examples_registry as reg
import flowsheet_solver as F
from flowsheet_model import Flowsheet, Block, Stream


def build_s2c_degenerate_fs():
    """Loop acoplado (2 reciclos) con un separador v/l PASIVO que degenera.

        Feed(H₂+benceno) → M → SEP(pasivo) → vapor → Xv → [purge, Rvap→M]
                                            → liq   → Xl → [prod,  Rliq→M]

    Pasivamente las 2 salidas de SEP quedan sin productor (ambas →0) → degenera.
    S2-C activa el flash → H₂→vapor, benceno→líquido → el loop converge.
    Cierre de masa exacto: Feed entra = purge + prod salen.
    """
    fs = Flowsheet()

    def blk(name, et, **kw):
        i = fs.new_id()
        b = Block(id=i, name=name, eq_type=et, S=1.0, x=0, y=0)
        for k, v in kw.items():
            setattr(b, k, v)
        fs.blocks[i] = b
        return i

    M = blk("M", "Mixer — static")
    SEP = blk("SEP", "Vessel — vertical")               # separador PASIVO
    Xv = blk("Xv", "Splitter — flow divider",
             splitter_active=True, splitter_fractions=[0.5, 0.5])   # purge, Rvap
    Xl = blk("Xl", "Splitter — flow divider",
             splitter_active=True, splitter_fractions=[0.7, 0.3])   # prod, Rliq

    def S(nm, src, dst, m=0.0, comp=None, lock=False, role="internal",
          phase="liquid", P=10.0, T=25):
        i = fs.new_id()
        s = Stream(id=i, name=nm, src=src, dst=dst, mass_flow=m,
                   composition=comp or {},
                   main_component=(max(comp, key=comp.get) if comp else ""),
                   phase=phase, role=role)
        s.mass_flow_locked = lock
        s.pressure_bar = P
        s.temperature = T
        fs.streams[i] = s
        return s

    S("Feed", -1, M, 100.0, {"hydrogen": 0.2, "benzene": 0.8},
      lock=True, role="feed")
    S("S-m", M, SEP)
    S("S-vap", SEP, Xv, comp={"hydrogen": 1.0}, phase="gas")    # comp DISTINTA
    S("S-liq", SEP, Xl, comp={"benzene": 1.0}, phase="liquid")
    S("Purge", Xv, -1, role="product", phase="gas")
    S("Rvap", Xv, M, role="recycle", phase="gas")
    S("Prod", Xl, -1, role="product")
    S("Rliq", Xl, M, role="recycle")
    return fs


def test_s2c_activa_y_converge_con_balance_cerrado():
    fs = build_s2c_degenerate_fs()
    res = F.solve(fs)
    rs = res.recycle_solutions[0]
    # S2-C activó el separador degenerado
    assert "SEP" in rs.s2c_activated, f"S2-C no activó SEP: {rs.s2c_activated}"
    # convergencia REAL
    assert rs.converged
    assert res.overall_status == "ok"
    assert len(res.mass_balance_errors) == 0
    g = {s.name: s.mass_flow for s in fs.streams.values()}
    # interior >0 (no colapso)
    for k in ("S-m", "S-vap", "S-liq", "Rvap", "Rliq"):
        assert g[k] > 0.0, f"{k} colapsó a {g[k]}"
    # balance global cierra: Feed = Purge + Prod
    assert abs((g["Purge"] + g["Prod"]) - g["Feed"]) < 0.5, \
        f"balance no cierra: Feed={g['Feed']} Purge+Prod={g['Purge']+g['Prod']}"
    # el flash produjo un split FÍSICO (vapor H₂-rico, líquido benceno-rico)
    vap = next(s for s in fs.streams.values() if s.name == "S-vap")
    liq = next(s for s in fs.streams.values() if s.name == "S-liq")
    assert vap.composition.get("hydrogen", 0) > liq.composition.get("hydrogen", 0)


def test_is_vl_separator_acotado():
    """(a-fix): identifica separadores v/l reales; excluye same-comp y splitters."""
    # hda_full/V-101: comp declarada distinta → True
    fs = Flowsheet.from_dict(json.load(open("data/examples/hda_full.json")))
    F._reset_propagated_values(fs)
    v = next(b for b in fs.blocks.values() if b.name == "V-101")
    assert F._is_vl_separator(fs, v)
    # industrial/V-201: salidas misma comp (declarada) → False
    fs2 = Flowsheet.from_dict(json.load(open("data/examples/industrial.json")))
    F._reset_propagated_values(fs2)
    v201 = next(b for b in fs2.blocks.values() if b.name == "V-201")
    assert not F._is_vl_separator(fs2, v201)


def test_haber_rec_no_activa_s2c_byte_identico():
    """haber_rec/V-101 está pinneado y su SCC es mono (Wegstein, no Broyden) →
    S2-C NO se activa → byte-idéntico (ancla de acotamiento)."""
    fs = reg.load_example("haber_rec")
    res = F.solve(fs)
    sols = [(rs.tear_stream, rs.converged, rs.iterations, rs.s2c_activated)
            for rs in res.recycle_solutions]
    assert sols == [("S-recycle", True, 3, [])], sols
    assert res.overall_status == "ok"


def test_gate_examples_no_activan_s2c():
    """Ningún ejemplo de los 41 enciende S2-C (todos frozen/pinned/mono) →
    el golden no se mueve en esta capa.  Prueba dura de acotamiento."""
    for ex in ("hda_full", "gas_sweet", "industrial", "haber_rec", "hda"):
        fs = reg.load_example(ex)
        res = F.solve(fs)
        for rs in res.recycle_solutions:
            assert not rs.s2c_activated, \
                f"{ex}: S2-C activó {rs.s2c_activated} (no debería en los 41)"
