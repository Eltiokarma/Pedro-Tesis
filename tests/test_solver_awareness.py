"""PR-A — Conciencia física del solver.

Verifica los warnings advisory tagged [W-...] que EXPONEN inconsistencias
físicas latentes (cierre de energía por bloque, T de descarga de compresor,
duty espurio, reactor placeholder, split-lock, duty>S, signo de duty) y el
INVARIANTE de regresión: estos warnings NO alteran overall_status.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowsheet_solver as fsv
import examples_registry as reg

_TAG = re.compile(r"\[(W-[A-Z-]+)\]")


def _solve(clave):
    fs = reg.load_example(clave)
    res = fsv.solve(fs)
    return fs, res


def _tags(res):
    out = set()
    for w in res.awareness_warnings:
        m = _TAG.match(w)
        if m:
            out.add(m.group(1))
    return out


def _lines(res, tag):
    return [w for w in res.awareness_warnings if w.startswith(f"[{tag}]")]


# ── 1.1 [W-ENERGY-BLOCK] ────────────────────────────────────────────────
def test_energy_block_methanol_compressor():
    """methanol K-101: duty politrópico calculado (~361 kW) vs ΔH≈18 kW de
    corrientes (descarga T lockeada = interenfriamiento implícito) → resid
    visible con causa de compresor.  (Antes el caso era ammonia con duty
    1200 hardcodeado; ese duty ya se calcula y su balance cierra.)"""
    _, res = _solve("methanol")
    lines = _lines(res, "W-ENERGY-BLOCK")
    k101 = [w for w in lines if "K-101" in w]
    assert k101, "K-101 debe disparar W-ENERGY-BLOCK"
    assert "≠ ΔH" in k101[0]


def test_energy_block_barrido_amplio():
    """El barrido de cierre de energía debe disparar en múltiples ejemplos
    (reactores reales descuadrados + compresores/bombas con duty espurio)."""
    n = 0
    for e in reg.list_examples():
        _, res = _solve(e["clave"])
        if _lines(res, "W-ENERGY-BLOCK"):
            n += 1
    assert n >= 12, f"esperado barrido amplio, sólo {n} ejemplos"


# ── 1.2 [W-COMP-T] ──────────────────────────────────────────────────────
def test_comp_t_ldpe_extremo():
    """ldpe K-101/S-HP: descarga isentrópica 1 etapa ~1322 °C >> 250 °C."""
    _, res = _solve("ldpe")
    lines = _lines(res, "W-COMP-T")
    assert any("S-HP" in w and "250" in w for w in lines)


def test_comp_t_solo_supera_umbral():
    """Ningún W-COMP-T debe dispararse por debajo de 250 °C."""
    for clave in ("ldpe", "acetic", "urea", "ammonia", "quimpac"):
        _, res = _solve(clave)
        for w in _lines(res, "W-COMP-T"):
            grados = float(re.search(r"=\s*(-?\d+)\s*°C", w).group(1))
            assert grados > 250


# ── 1.3 [W-T-OVERRIDE] ──────────────────────────────────────────────────
def test_t_override_se_dispara():
    """Al menos un ejemplo pierde la intención de T declarada (no locked)."""
    total = 0
    for e in reg.list_examples():
        _, res = _solve(e["clave"])
        total += len(_lines(res, "W-T-OVERRIDE"))
    assert total >= 3


# ── 1.4 [W-MIXER-DUTY] / [W-TANK-DUTY] ──────────────────────────────────
def test_mixer_duty_industrial():
    _, res = _solve("industrial")
    assert any("M-101" in w for w in _lines(res, "W-MIXER-DUTY"))


def test_tank_duty_industrial():
    _, res = _solve("industrial")
    assert any("TK-301" in w for w in _lines(res, "W-TANK-DUTY"))


# ── 1.5 [W-PLACEHOLDER] + bonus ─────────────────────────────────────────
def test_placeholder_quince_ejemplos():
    """Los reactores estructurales (química via outputs locked) deben ser
    visibles en ~15 ejemplos."""
    n = 0
    for e in reg.list_examples():
        _, res = _solve(e["clave"])
        if _lines(res, "W-PLACEHOLDER"):
            n += 1
    assert n >= 14, f"esperado ~15 ejemplos con placeholder, hay {n}"


def test_placeholder_bonus_ldpe_r027():
    """ldpe usa R027_PLACEHOLDER y R027 existe curada → bonus de sugerencia."""
    _, res = _solve("ldpe")
    lines = _lines(res, "W-PLACEHOLDER")
    assert any("R027 existe curada" in w for w in lines)


# ── 1.6 [W-SPLIT-LOCK] ──────────────────────────────────────────────────
def test_split_lock_talara_v101_corregido():
    """talara V-101 (desalador): el cruce fracción↔stream fue corregido.

    El cruce era: splitter_fractions=[0.952, 0.048] asignaba 0.952 a la
    salmuera (S-brine, 25000 t/a) y 0.048 al crudo desalado (C1-desalado,
    500000 t/a) — invertido.  Corregido a [0.048, 0.952] para alinear con
    el orden de outputs [S-brine, C1-desalado].  V-101 ya NO debe disparar
    [W-SPLIT-LOCK] y su split debe cerrar el balance."""
    fs, res = _solve("talara")
    lines = _lines(res, "W-SPLIT-LOCK")
    assert not any("V-101" in w for w in lines), \
        f"V-101 no debe disparar W-SPLIT-LOCK tras el fix: {lines}"

    b = next(b for b in fs.blocks.values() if b.name == "V-101")
    ins = [s for s in fs.streams.values() if s.dst == b.id]
    outs = [s for s in fs.streams.values() if s.src == b.id]
    feed = sum(s.mass_flow for s in ins)
    assert abs(sum(s.mass_flow for s in outs) - feed) < 1e-6  # Σout = feed
    # cada fracción cuadra con el flujo lockeado de su output (tol 2%)
    for k, s in enumerate(outs):
        expected = feed * b.splitter_fractions[k]
        assert abs(s.mass_flow - expected) / max(abs(expected), 1.0) < 0.02


def test_split_lock_detector_sigue_vivo():
    """El detector [W-SPLIT-LOCK] sigue funcionando: si se RE-introduce el
    cruce en V-101 (invertir las fracciones), el warning vuelve a dispararse.
    Garantiza que el fix de arriba es lo que limpió el warning, no que el
    detector quedó muerto."""
    fs = reg.load_example("talara")
    b = next(b for b in fs.blocks.values() if b.name == "V-101")
    b.splitter_fractions = list(reversed(b.splitter_fractions))  # re-cruzar
    res = fsv.solve(fs)
    lines = _lines(res, "W-SPLIT-LOCK")
    assert any("V-101" in w for w in lines), \
        "el detector W-SPLIT-LOCK debe disparar con el cruce re-introducido"


# ── 1.7 [W-DUTY-S] ──────────────────────────────────────────────────────
def test_duty_s_talara_fhtn():
    _, res = _solve("talara")
    assert any("F-HTN" in w for w in _lines(res, "W-DUTY-S"))


# ── 1.8 [W-SIGN] ────────────────────────────────────────────────────────
def test_sign_rxn_flash_col_aircooler():
    """rxn_flash_col E-101: air cooler con duty positivo (debería ser <0)."""
    _, res = _solve("rxn_flash_col")
    lines = _lines(res, "W-SIGN")
    assert any("E-101" in w and "air cooler" in w for w in lines)


# ── INVARIANTE: los warnings NO alteran overall_status ──────────────────
def test_awareness_no_altera_overall_status():
    """Un ejemplo 'ok' del golden con warnings de conciencia debe seguir
    siendo 'ok' (un warning advisory no cambia el estado)."""
    import json
    golden_path = os.path.join(os.path.dirname(__file__), "..", "data",
                               "examples", "_golden.json")
    with open(golden_path, encoding="utf-8") as f:
        golden = json.load(f)
    for clave, g in golden.items():
        _, res = _solve(clave)
        assert res.overall_status == g["overall_status"], (
            f"{clave}: overall_status cambió "
            f"{g['overall_status']} → {res.overall_status}")


def test_ok_example_con_warnings_sigue_ok():
    """talara es golden 'ok' pero dispara múltiples warnings de conciencia."""
    _, res = _solve("talara")
    assert res.overall_status == "ok"
    assert len(res.awareness_warnings) >= 5
