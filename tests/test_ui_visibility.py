"""Visibilidad de presión y propiedades en la UI Qt (tooltip / inspector /
burbuja).  Smoke + lógica pura.  Headless (QT_QPA_PLATFORM=offscreen)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QLabel

_app = QApplication.instance() or QApplication([])

import flowsheet_qt as fq
import stream_inspector as si
from flowsheet_model import Block, Stream, Flowsheet


# ── badges / origen de P (lógica pura) ─────────────────────────────────
def test_auto_badge_html():
    assert "AUTO" in fq._auto_badge()
    assert "spec" in fq._spec_tag().lower()


def test_pressure_origin_is_auto():
    s = Stream(id=1, name="s", src=1, dst=2)
    s.pressure_locked = True; s.pressure_lock_origin = "user"
    assert fq._pressure_origin_is_auto(s) is False          # user → spec
    s.pressure_lock_origin = "solver"
    assert fq._pressure_origin_is_auto(s) is True            # solver → auto
    s.pressure_lock_origin = "heuristic"
    assert fq._pressure_origin_is_auto(s) is True
    # campo ausente: locked→spec, no→auto
    s2 = Stream(id=2, name="s2", src=1, dst=2)
    object.__delattr__(s2, "pressure_lock_origin") if hasattr(s2, "pressure_lock_origin") else None
    # forzamos ausencia simulando getattr default
    class _NoOrigin:
        pressure_locked = True
    assert fq._pressure_origin_is_auto(_NoOrigin()) is False
    class _NoOrigin2:
        pressure_locked = False
    assert fq._pressure_origin_is_auto(_NoOrigin2()) is True


# ── tooltip de StreamItem: P con sufijo + marca de fase ────────────────
def _stream_tooltip(s, fs):
    import types
    item = fq.StreamItem.__new__(fq.StreamItem)
    item.model = s; item.fs = fs; item.editor = None
    item.setToolTip = types.MethodType(
        lambda self, t: setattr(self, "_tt", t), item)
    fq.StreamItem._update_tooltip(item)
    return item._tt


def test_tooltip_P_auto_y_spec():
    fs = Flowsheet()
    fs.blocks = {1: Block(id=1, name="A", eq_type="Vessel — vertical", S=1.0),
                 2: Block(id=2, name="B", eq_type="Vessel — vertical", S=1.0)}
    s = Stream(id=10, name="S", src=1, dst=2, mass_flow=100.0,
               composition={"water": 1.0}, temperature=80.0,
               pressure_bar=50.0, pressure_locked=True,
               pressure_lock_origin="user")
    fs.streams = {10: s}
    tt = _stream_tooltip(s, fs)
    assert "P = 50.00 bar" in tt and "spec" in tt
    s.pressure_lock_origin = "solver"
    assert "AUTO" in _stream_tooltip(s, fs)


def test_tooltip_phase_mark():
    fs = Flowsheet()
    fs.blocks = {1: Block(id=1, name="A", eq_type="Vessel — vertical", S=1.0),
                 2: Block(id=2, name="B", eq_type="Vessel — vertical", S=1.0)}
    # liquid declarado pero T/P en zona vapor
    s = Stream(id=10, name="S", src=1, dst=2, mass_flow=100.0,
               composition={"ethanol": 1.0}, temperature=120.0,
               pressure_bar=1.0, phase="liquid", phase_locked=True,
               temperature_locked=True, pressure_locked=True,
               pressure_lock_origin="user")
    fs.streams = {10: s}
    tt = _stream_tooltip(s, fs)
    assert "⚠" in tt and "flash da" in tt


# ── inspector: sección de propiedades calculadas ───────────────────────
def test_inspector_calc_section_syngas():
    fs = Flowsheet()
    fs.blocks = {1: Block(id=1, name="A", eq_type="Vessel — vertical", S=1.0),
                 2: Block(id=2, name="B", eq_type="Vessel — vertical", S=1.0)}
    s = Stream(id=10, name="S-syngas", src=1, dst=2, mass_flow=50000.0,
               composition={"hydrogen": 0.52, "co": 0.38, "methane": 0.05,
                            "water": 0.05}, temperature=40.0,
               pressure_bar=80.0, phase="gas")
    fs.streams = {10: s}
    panel = si.StreamInspectorPanel()
    panel.load_stream(s, fs)
    sect = panel._sec_propiedades_calc()
    texts = [c.text() for c in sect.findChildren(QLabel)]
    joined = " | ".join(texts)
    assert "Propiedades de la mezcla [calculado]" in joined
    assert "Densidad ρ" in joined and "M de la mezcla" in joined
    # M de mezcla del syngas H2-rich ≈ 3.6 g/mol; ρ gas ≈ 11 kg/m³ (sanity)
    assert any("3.6" in t for t in texts), f"M esperado ~3.6: {texts}"
    # ρ debe estar en el rango físico (7-12), no los ~41 del MW mass-weighted
    rho_vals = [t for t in texts if "kg/m³" in t]
    assert rho_vals, "falta densidad"
    rho = float(rho_vals[0].split()[0])
    assert 7.0 <= rho <= 12.0, f"ρ fuera de sanity 7-12: {rho}"


def test_inspector_calc_n_d_sin_datos():
    """Componente sin MW → 'n/d', nunca se inventa."""
    fs = Flowsheet()
    fs.blocks = {1: Block(id=1, name="A", eq_type="Vessel — vertical", S=1.0),
                 2: Block(id=2, name="B", eq_type="Vessel — vertical", S=1.0)}
    s = Stream(id=10, name="S", src=1, dst=2, mass_flow=1000.0,
               composition={"__inventado__": 1.0}, temperature=25.0,
               pressure_bar=1.0, phase="liquid")
    fs.streams = {10: s}
    panel = si.StreamInspectorPanel()
    panel.load_stream(s, fs)
    sect = panel._sec_propiedades_calc()
    texts = [c.text() for c in sect.findChildren(QLabel)]
    assert any(t == "n/d" for t in texts), f"esperaba n/d: {texts}"
