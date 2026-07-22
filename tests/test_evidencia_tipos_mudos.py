"""Evidencia para los 7 tipos que la matriz del Frente 1 marcó mudos.

Antes de esta sesión, Crystallizer / Dryer — drum / Evaporator —
vertical / Mixer — static / Valve — control globe / Boiler fire-tube y
water-tube tenían instancia en los 58 ejemplos pero NINGUNA evidencia
computada en el inspector (solo el editor de specs, en el mejor caso).

Cada tipo gana su par text+metrics en inspector_evidence (Gate 1: cada
métrica aparece textualmente en la *_text), cableado en block_inspector
(evidence_specs) y en la matriz (audit_frontend_matrix). Los modos
especiales (dryer/crystallizer/evaporator) hablan en AMBOS estados:
modo automático activo (specs del solver) y patrón sancionado con
corrientes lockeadas (evidencia derivada de corrientes, con la
procedencia dicha).
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from examples_registry import load_example
import flowsheet_solver as fsv
import inspector_evidence as ie


@pytest.fixture(scope="module")
def resueltos():
    out = {}
    for k in ("sugar", "boiler_ft", "rankine", "letdown", "smr_eq"):
        fs = load_example(k)
        fsv.solve(fs)
        out[k] = fs
    return out


def _block(fs, needle):
    return next(b for b in fs.blocks.values() if needle in b.eq_type
                or needle == b.name)


CASOS = [
    # (ejemplo, bloque, text_fn, metrics_fn, fragmento esperado en el texto)
    ("sugar", "Dryer", "dryer", "Humedad in"),
    ("sugar", "R-102", "crystallizer", "Corrientes lockeadas"),
    ("sugar", "EV-101", "evaporator", "efectivo"),
    ("boiler_ft", "Boiler", "boiler", "kJ/kg vapor"),
    ("rankine", "Boiler", "boiler", "Duty"),
    ("letdown", "Valve", "valve", "isoentálpica"),
    ("smr_eq", "Mixer", "mixer", "mezcla"),
]


@pytest.mark.parametrize("ejemplo,bloque,familia,frag", CASOS)
def test_tipo_mudo_ahora_habla(resueltos, ejemplo, bloque, familia, frag):
    fs = resueltos[ejemplo]
    b = _block(fs, bloque)
    text_fn = getattr(ie, f"{familia}_text")
    metrics_fn = getattr(ie, f"{familia}_metrics")
    txt = text_fn(b, fs)
    assert txt is not None, f"{b.name} ({b.eq_type}) sigue mudo"
    assert frag in txt, f"'{frag}' no aparece en:\n{txt}"
    m = metrics_fn(b, fs)
    assert m is not None and m.get("metrics"), f"{b.name} sin métricas"


def test_boiler_energia_especifica_fisica(resueltos):
    """La energía específica de la caldera debe estar en el rango de
    sensible+latente del agua (≈2000-3000 kJ/kg según P y precalent.)."""
    fs = resueltos["boiler_ft"]
    b = _block(fs, "Boiler")
    m = ie.boiler_metrics(b, fs)
    esp = next(x for x in m["metrics"] if x["key"] == "esp")
    val = float(esp["value"].replace(",", ""))
    assert 1800 < val < 3200, f"específica {val} kJ/kg fuera de física"


def test_mixer_balance_verde_y_t_intermedia(resueltos):
    fs = resueltos["smr_eq"]
    b = _block(fs, "Mixer")
    m = ie.mixer_metrics(b, fs)
    assert any(s.get("text", "").startswith("Σin = out")
               for s in m["status"])
    ins = [s for s in fs.streams.values()
           if s.dst == b.id and s.mass_flow > 0]
    out = next(s for s in fs.streams.values()
               if s.src == b.id and s.mass_flow > 0)
    ts = [s.temperature for s in ins]
    assert min(ts) - 0.1 <= out.temperature <= max(ts) + 0.1, (
        "T de mezcla fuera del rango de las entradas")


def test_guards_no_leakean_a_otros_tipos(resueltos):
    """Una bomba no es caldera ni válvula ni mixer — las funciones
    nuevas devuelven None fuera de su familia."""
    fs = resueltos["letdown"]
    pump = _block(fs, "Pump")
    for fn in (ie.boiler_text, ie.mixer_text, ie.dryer_text,
               ie.crystallizer_text, ie.evaporator_text):
        assert fn(pump, fs) is None, f"{fn.__name__} disparó para una bomba"
    valve = _block(fs, "Valve")
    assert ie.boiler_text(valve, fs) is None


def test_matriz_sin_huecos_didacticos():
    """El flag central del Frente 1: ya no queda NINGÚN eq_type con
    instancia en los ejemplos y cero evidencia específica."""
    from audit_frontend_matrix import build_matrix
    rows = build_matrix()
    mudos = [t for t, r in rows.items()
             if r["example"] and not [e for e in r["evidence"]
                                      if "ERROR" not in e]]
    assert mudos == [], f"tipos aún mudos: {mudos}"
    con_error = [(t, e) for t, r in rows.items()
                 for e in r["evidence"] if "ERROR" in e]
    assert not con_error, f"evidencia que revienta: {con_error}"
