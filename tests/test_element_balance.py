"""TRABAJOS_FUTUROS §13 — chequeo ELEMENTAL de balance (C/H/O/N/S/…).

Los átomos se conservan AUNQUE haya química, así que este chequeo audita
también los bloques que el chequeo por especie saltea (reactores con química
real) y los placeholders con outputs escritos a mano.  Cobertura:

  (A) Unidad: parser de fórmulas y reparto de masa elemental.
  (B) Detector: un reactor con output que crea átomos dispara.
  (C) RATCHET del catálogo: tras la sesión 2026-07, 40/41 ejemplos auditan
      elemental-limpio.  El hallazgo ESTRUCTURAL conocido queda confinado
      a su bloque (deuda documentada en TRABAJOS_FUTUROS §17):
        · hno3/T-401: el HNO3 producido excede el N de los NOx alimentados
          (el spec 6 200 t/a @60% no es alcanzable con ese feed) — requiere
          re-derivar el tren de absorción completo.
      (talara/R-SMR se cerró en esta misma sesión: feed de vapor C21-steam
      + resize CH4/CO2 por estequiometría exacta, H2 de los HDT intacto.)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audit_examples_components as aec
from flowsheet_model import Block, Stream, Flowsheet

aec._headless()

# Ejemplos con hallazgos elementales ESTRUCTURALES conocidos → bloque dueño.
_KNOWN_DIRTY = {"hno3": "T-401"}


# ── (A) unidad ──────────────────────────────────────────────────────────
def test_parse_formula():
    assert aec._parse_formula("C7H8") == {"C": 7, "H": 8}
    assert aec._parse_formula("H2O") == {"H": 2, "O": 1}
    assert aec._parse_formula("CaCO3") == {"Ca": 1, "C": 1, "O": 3}
    assert aec._parse_formula("Mix") is None          # pseudo → no parseable
    assert aec._parse_formula("") is None


def test_element_masses_reproduce_la_masa_del_componente():
    """El reparto elemental usa fracciones de FÓRMULA: la suma de los
    elementos reproduce exacto la masa del componente."""
    el = aec._element_masses({"water": 100.0}, block_flow=100.0)
    assert abs(sum(el.values()) - 100.0) < 1e-9
    assert abs(el["H"] - 100.0 * 2 * 1.008 / 18.015) < 1e-3


# ── (B) detector vivo ───────────────────────────────────────────────────
def test_detector_reactor_que_crea_atomos_dispara():
    """Un 'reactor' cuyo output declara H2 desde N2 puro debe disparar
    hallazgos elementales (N desaparece, H aparece)."""
    fs = Flowsheet()
    fs.blocks[1] = Block(id=1, name="R-X", eq_type="Reactor — autoclave",
                         S=1.0, reactions=["R004"], reactor_mode="stoich")
    fs.blocks[2] = Block(id=2, name="TK-A", eq_type="Storage tank — cone roof", S=1.0)
    fs.blocks[3] = Block(id=3, name="TK-B", eq_type="Storage tank — cone roof", S=1.0)
    fs.streams[1] = Stream(id=1, name="S-in", src=2, dst=1, mass_flow=100.0,
                           composition={"nitrogen": 1.0}, composition_locked=True,
                           mass_flow_locked=True)
    fs.streams[2] = Stream(id=2, name="S-out", src=1, dst=3, mass_flow=100.0,
                           composition={"hydrogen": 1.0}, composition_locked=True,
                           mass_flow_locked=True)
    findings = aec.audit_block_elements(fs, fs.blocks[1])
    els = {f["component"] for f in findings}
    assert "N" in els and "H" in els, f"debe disparar N y H: {findings}"


def test_pseudo_sin_formula_saltea_sin_ruido():
    """Un bloque con pseudo-componente no-traza sin fórmula ('Mix') no es
    evaluable → 0 hallazgos (skip silencioso, no falso positivo)."""
    fs = Flowsheet()
    fs.blocks[1] = Block(id=1, name="V-X", eq_type="Vessel — vertical", S=1.0)
    fs.blocks[2] = Block(id=2, name="TK-A", eq_type="Storage tank — cone roof", S=1.0)
    fs.blocks[3] = Block(id=3, name="TK-B", eq_type="Storage tank — cone roof", S=1.0)
    fs.streams[1] = Stream(id=1, name="S-in", src=2, dst=1, mass_flow=100.0,
                           composition={"crude_oil": 1.0}, composition_locked=True,
                           mass_flow_locked=True)
    fs.streams[2] = Stream(id=2, name="S-out", src=1, dst=3, mass_flow=100.0,
                           composition={"naphtha": 0.5, "diesel": 0.5},
                           composition_locked=True, mass_flow_locked=True)
    assert aec.audit_block_elements(fs, fs.blocks[1]) == []


# ── (C) ratchet del catálogo ───────────────────────────────────────────
def test_catalogo_elemental_ratchet():
    """39/41 ejemplos elemental-limpios; los 2 conocidos confinados a su
    bloque estructural documentado.  Cualquier hallazgo nuevo = regresión."""
    for key in aec._example_keys():
        rep = aec.audit_example(key)
        ef = rep["element_findings"]
        if key in _KNOWN_DIRTY:
            blk = _KNOWN_DIRTY[key]
            extra = [f for f in ef if f["block"] != blk]
            assert extra == [], \
                f"{key}: hallazgos elementales fuera de {blk}: {extra}"
            assert ef, f"{key}/{blk}: la deuda documentada desapareció — " \
                       f"actualizar _KNOWN_DIRTY (¡buena noticia!)"
        else:
            assert ef == [], f"{key}: hallazgos elementales nuevos: {ef}"
