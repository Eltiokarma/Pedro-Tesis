"""Parte 1 — harness permanente de balance por componente.

Cubre:
  (A) Serialización round-trip de los campos nuevos inline_reaction /
      pseudo_cut en flowsheet_model (aditivo, sin pérdida).
  (B) Comportamiento del auditor audit_examples_components: detección de
      desbalance por componente, modo estequiometría (inline_reaction),
      modo masa-total de grupo (pseudo_cut) y exclusión de reactores.
  (C) Gate ratchet con whitelist vacía → verde.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowsheet_model as fm
from flowsheet_model import Block, Stream, Flowsheet
import audit_examples_components as aec


# ======================================================================
# (A) ROUND-TRIP DE SERIALIZACIÓN
# ======================================================================
def test_roundtrip_sin_campos_nuevos_estable():
    """Un bloque SIN declarar los campos nuevos: JSON→modelo→JSON estable
    (fixpoint) y los campos nuevos aparecen con su default vacío."""
    fs = Flowsheet()
    fs.blocks[1] = Block(id=1, name="B-1", eq_type="Pump — centrifugal", S=1.0)
    d1 = fs.to_dict()
    d2 = Flowsheet.from_dict(d1).to_dict()
    assert d1 == d2, "round-trip no es idéntico (fixpoint roto)"
    assert d1["blocks"][1]["inline_reaction"] == []
    assert d1["blocks"][1]["pseudo_cut"] == {}


def test_roundtrip_con_campos_nuevos_preservados():
    """Con los campos poblados, se preservan exactamente tras el round-trip."""
    fs = Flowsheet()
    fs.blocks[1] = Block(
        id=1, name="ABS", eq_type="Tower (column shell)", S=1.0,
        inline_reaction=["R023", "R024"],
        pseudo_cut={"crude_oil": ["naphtha", "diesel", "atmospheric_residue"]})
    d1 = fs.to_dict()
    fs2 = Flowsheet.from_dict(d1)
    d2 = fs2.to_dict()
    assert d1 == d2
    assert fs2.blocks[1].inline_reaction == ["R023", "R024"]
    assert fs2.blocks[1].pseudo_cut == {
        "crude_oil": ["naphtha", "diesel", "atmospheric_residue"]}


def test_roundtrip_ejemplo_real_solo_agrega_claves_nuevas():
    """Cargar un ejemplo on-disk (sin los campos nuevos) y re-serializar
    sólo AGREGA campos aditivos nuevos; ningún valor original se pierde ni
    cambia."""
    BLOCK_NEW = {"inline_reaction", "pseudo_cut", "duty_origin"}
    STREAM_NEW = {"pressure_lock_origin"}
    path = os.path.join(aec.DATA_DIR, "gas_sweet.json")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    d2 = Flowsheet.from_dict(d).to_dict()
    for bid_str, b_in in d["blocks"].items():
        b_out = d2["blocks"][int(bid_str)]
        new_keys = set(b_out) - set(b_in)
        assert new_keys <= BLOCK_NEW, \
            f"claves de bloque inesperadas agregadas: {new_keys - BLOCK_NEW}"
        for k in b_in:                       # nada original se modifica
            assert b_in[k] == b_out[k], f"clave '{k}' cambió en round-trip"
    for sid_str, s_in in d["streams"].items():
        s_out = d2["streams"][int(sid_str)]
        new_keys = set(s_out) - set(s_in)
        assert new_keys <= STREAM_NEW, \
            f"claves de stream inesperadas agregadas: {new_keys - STREAM_NEW}"
        for k in s_in:
            assert s_in[k] == s_out[k], f"clave '{k}' cambió en round-trip"


# ======================================================================
# (B) AUDITOR — helpers de construcción
# ======================================================================
def _block_in_out(b, comp_in_streams, comp_out_streams):
    """Arma un Flowsheet con b en el medio y fuentes/sumideros tontos para
    que tenga entradas y salidas reales."""
    fs = Flowsheet()
    src = Block(id=90, name="SRC", eq_type="Storage tank — cone roof", S=1.0)
    snk = Block(id=91, name="SNK", eq_type="Storage tank — cone roof", S=1.0)
    fs.blocks = {b.id: b, 90: src, 91: snk}
    sid = 100
    for comp, mass in comp_in_streams:
        fs.streams[sid] = Stream(id=sid, name=f"in{sid}", src=90, dst=b.id,
                                 mass_flow=mass, composition=comp)
        sid += 1
    for comp, mass in comp_out_streams:
        fs.streams[sid] = Stream(id=sid, name=f"out{sid}", src=b.id, dst=91,
                                 mass_flow=mass, composition=comp)
        sid += 1
    return fs


def test_desbalance_por_componente_detectado():
    """Vessel no-reactor: agua entra, etanol sale (100% roto) → CRÍTICO."""
    b = Block(id=1, name="MX", eq_type="Vessel — vertical", S=1.0)
    fs = _block_in_out(b, [({"water": 1.0}, 100.0)],
                          [({"ethanol": 1.0}, 100.0)])
    findings = aec.audit_block(fs, b)
    comps = {f["component"] for f in findings}
    assert "water" in comps and "ethanol" in comps
    assert any(f["severity"] == "CRITICO" for f in findings)


def test_balance_correcto_sin_hallazgos():
    """Flash que reparte un componente entre dos salidas conserva la masa
    por componente → sin hallazgos."""
    b = Block(id=1, name="FL", eq_type="Vessel — vertical", S=1.0)
    # in: 50 EtOH / 50 H2O.  out vapor: 40 EtOH puro.  out liq: 10 EtOH + 50 H2O.
    # → EtOH 50=40+10, H2O 50=0+50.  Conserva cada componente.
    fs = _block_in_out(
        b,
        [({"ethanol": 0.5, "water": 0.5}, 100.0)],
        [({"ethanol": 1.0}, 40.0),
         ({"ethanol": 10.0 / 60.0, "water": 50.0 / 60.0}, 60.0)])
    findings = aec.audit_block(fs, b)
    assert findings == [], f"flash balanceado no debería flagear: {findings}"


def test_inline_reaction_modo_estequiometria():
    """Con inline_reaction declarada, un cambio de composición explicado por
    la estequiometría NO se flagea; el mismo bloque SIN la declaración sí."""
    # WGS R002: CO + H2O → CO2 + H2 (ξ = 1000 kmol/a base).
    comp_in = [({"co": 28.01 / 46.025, "water": 18.015 / 46.025}, 46025.0)]
    comp_out = [({"co2": 44.01 / 46.026, "hydrogen": 2.016 / 46.026}, 46026.0)]

    b_no = Block(id=1, name="RX", eq_type="Vessel — vertical", S=1.0)
    fs_no = _block_in_out(b_no, comp_in, comp_out)
    findings_no = aec.audit_block(fs_no, b_no)
    assert any(f["severity"] == "CRITICO" for f in findings_no), \
        "sin inline_reaction el cambio CO→CO2 debe flagear"

    b_yes = Block(id=1, name="RX", eq_type="Vessel — vertical", S=1.0,
                  inline_reaction=["R002"])
    fs_yes = _block_in_out(b_yes, comp_in, comp_out)
    findings_yes = aec.audit_block(fs_yes, b_yes)
    # la estequiometría explica el cambio → sin masa no explicada ni
    # desbalance total (las reacciones conservan masa).
    unexplained = [f for f in findings_yes
                   if f.get("mode") == "inline_reaction"
                   and f.get("component") != "__total__"
                   and f.get("delta_unexplained", 0) > 0]
    assert not unexplained, \
        f"la estequiometría WGS debería explicar el cambio: {unexplained}"


def test_pseudo_cut_modo_masa_total():
    """pseudo_cut: el grupo crude_oil→[naphtha,diesel] cierra en masa total
    aunque crude_oil 'desaparezca' por componente."""
    b_no = Block(id=1, name="T-101", eq_type="Tower (column shell)", S=1.0)
    fs_no = _block_in_out(b_no, [({"crude_oil": 1.0}, 100000.0)],
                                [({"naphtha": 1.0}, 40000.0),
                                 ({"diesel": 1.0}, 60000.0)])
    assert any(f["severity"] == "CRITICO" for f in aec.audit_block(fs_no, b_no)), \
        "sin pseudo_cut, crude_oil→cortes debe flagear"

    b_yes = Block(id=1, name="T-101", eq_type="Tower (column shell)", S=1.0,
                  pseudo_cut={"crude_oil": ["naphtha", "diesel"]})
    fs_yes = _block_in_out(b_yes, [({"crude_oil": 1.0}, 100000.0)],
                                  [({"naphtha": 1.0}, 40000.0),
                                   ({"diesel": 1.0}, 60000.0)])
    assert aec.audit_block(fs_yes, b_yes) == [], \
        "pseudo_cut con grupo balanceado no debería flagear"


def test_pseudo_cut_grupo_no_cierra_flagea():
    """Si el grupo pseudo_cut NO cierra en masa total, sí se flagea."""
    b = Block(id=1, name="T-101", eq_type="Tower (column shell)", S=1.0,
              pseudo_cut={"crude_oil": ["naphtha", "diesel"]})
    fs = _block_in_out(b, [({"crude_oil": 1.0}, 100000.0)],
                          [({"naphtha": 1.0}, 40000.0),
                           ({"diesel": 1.0}, 40000.0)])     # faltan 20000
    findings = aec.audit_block(fs, b)
    assert any(f.get("mode") == "pseudo_cut" for f in findings)


def test_reactor_declarado_excluido():
    """Un bloque con reactions=[...] (reactor real) se excluye del chequeo
    por componente."""
    b = Block(id=1, name="R-101", eq_type="Reactor — jacketed non-agit.",
              S=1.0, reactions=["R002"])
    fs = _block_in_out(b, [({"co": 1.0}, 100.0)], [({"co2": 1.0}, 100.0)])
    assert aec.audit_block(fs, b) == [], "reactor declarado no debe auditarse"


# ======================================================================
# (C) GATE RATCHET
# ======================================================================
def test_gate_whitelist_vacia_o_consistente():
    """gate_component_balance corre y devuelve 0 (verde) con la whitelist
    actual; cada ejemplo de la whitelist debe auditar limpio."""
    import gate_component_balance as gcb
    assert gcb.run_gate() == 0
