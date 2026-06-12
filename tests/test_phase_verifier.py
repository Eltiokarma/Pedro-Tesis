"""FASE 4.10 — verificador de fase extendido (Tc / solid / melt)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flowsheet_model import Block, Stream, Flowsheet
from flowsheet_consistency_audit import audit_flowsheet


def _one_stream(phase, comp, T_C, P=1.013, main=""):
    fs = Flowsheet()
    fs.blocks = {1: Block(id=1, name="SRC", eq_type="Storage tank — cone roof", S=1.0),
                 2: Block(id=2, name="SNK", eq_type="Storage tank — cone roof", S=1.0)}
    s = Stream(id=10, name="S", src=1, dst=2, mass_flow=100.0,
               composition=comp, main_component=main, temperature=T_C,
               pressure_bar=P, phase=phase, phase_locked=True)
    fs.streams = {10: s}
    return fs


def _phase(fs):
    return audit_flowsheet(fs).by_category('phase')


def test_4a_supercritico_gas_confirmado():
    """H2 declarado gas a 200°C (T >> Tc=-240) → NO emite 'no confiable'."""
    fs = _one_stream("gas", {"hydrogen": 1.0}, 200.0, P=80.0, main="hydrogen")
    assert not any(f.data.get('reason') == 'antoine_range' for f in _phase(fs)), \
        "T>Tc con gas declarado no debería emitir antoine_range"


def test_4a_dominante_sin_main_component():
    """Sin main_component, usa el dominante de la composición (cloro Tc=144)."""
    fs = _one_stream("gas", {"chlorine": 0.95, "water": 0.05}, 318.0, P=7.0)
    assert not any(f.data.get('reason') == 'antoine_range' for f in _phase(fs))


def test_4a_liquido_sobre_Tc_no_se_suprime():
    """Liquid por encima de Tc NO se confirma (4.10a sólo confirma gas/vapor)."""
    fs = _one_stream("liquid", {"hydrogen": 1.0}, 200.0, P=80.0, main="hydrogen")
    # debe seguir habiendo algún hallazgo (no se suprime un liquid imposible)
    assert _phase(fs)


def test_4b_solid_omite_antoine():
    """phase='solid' → no se verifica contra VLE (sin hallazgo de fase)."""
    fs = _one_stream("solid", {"sucrose": 1.0}, 25.0, main="sucrose")
    assert _phase(fs) == []


def test_4c_melt_aviso_especifico():
    """Líquido a 1450°C (proxy mineral sin Tb) → aviso 'fundido', no genérico."""
    fs = _one_stream("liquid", {"clinker": 1.0}, 1450.0, main="clinker")
    ph = _phase(fs)
    assert any(f.data.get('reason') == 'melt' for f in ph), \
        f"un fundido a 1450°C debe dar reason='melt': {[f.message for f in ph]}"
    assert all('inconsistencia' not in f.message.lower() for f in ph)
