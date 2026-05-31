"""GATE 2 — átomos visuales (inspector_widgets), render headless-safe.

Cada átomo instancia y pinta offscreen (QPixmap.render) SIN crashear, en un
barrido representativo de los 2 temas × 4 acentos × 3 densidades, y re-pinta
al emitir _PrefsBus (re-tema en caliente).  Qt puro (no depende de matplotlib).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap

import block_inspector as bi
import inspector_widgets as iw

_app = QApplication.instance() or QApplication([])


def _render(widget, w=160, h=72):
    """Fuerza un paintEvent real vía QPixmap.render (offscreen)."""
    widget.resize(w, h)
    px = QPixmap(widget.size())
    widget.render(px)
    return px


def _make_all():
    """Una instancia de cada átomo, con valores plausibles."""
    card = iw.MetricCard(key="dTlm", label="ΔT LMTD", value="91.8",
                         unit="°C", state="auto", sub="ok", flag="≈")
    badge = iw.StatusBadge("Balance cierra", "ok")
    gauge = iw.GaugePill(label="Conversión", value=0.82, suffix="%",
                         marker=0.5)
    bar = iw.DeltaBar(label="IN agua", frac=0.7, value="1234.5", kind="in")
    return [card, badge, gauge, bar]


# ── instanciación + render ─────────────────────────────────────────────
def test_atoms_instantiate_and_render():
    for w in _make_all():
        px = _render(w)
        assert not px.isNull()


def test_metricgrid_reflow():
    grid = iw.MetricGrid()
    for i in range(6):
        grid.add(iw.MetricCard(label=f"m{i}", value=str(i), state="info"))
    # anchos que fuerzan 1, 2 y 3 columnas (w//150)
    for width, exp in [(149, 1), (300, 2), (480, 3)]:
        grid.resize(width, 200)
        grid._relayout(force=True)
        assert grid._cols == exp, f"w={width}: cols={grid._cols} != {exp}"


def test_all_states_and_kinds_render():
    for st in ("spec", "auto", "ok", "warn", "alert", "danger", "accent",
               "info", "neutral", "sinnott"):
        _render(iw.MetricCard(label="x", value="1", state=st))
    for kd in ("ok", "warn", "alert", "danger", "info", "accent", "neutral",
               "sinnott"):
        _render(iw.StatusBadge("k", kd))
    for kd in ("in", "out", "ok", "warn", "danger", "accent"):
        _render(iw.DeltaBar(label="b", frac=0.5, value="9", kind=kd))


# ── barrido temas × acentos × densidades ───────────────────────────────
def test_theme_accent_density_sweep():
    saved = bi.current_prefs()
    try:
        for theme in ("light", "dark"):
            for accent in ("teal", "terracota", "cobalto", "oliva"):
                for density in ("compact", "cozy", "comfy"):
                    bi.apply_preferences(theme=theme, accent=accent,
                                         density=density)
                    for w in _make_all():
                        px = _render(w)
                        assert not px.isNull(), (
                            f"render nulo en {theme}/{accent}/{density} "
                            f"para {type(w).__name__}")
    finally:
        bi.apply_preferences(**saved)


# ── re-pintado en caliente al emitir _PrefsBus ─────────────────────────
def test_repaint_on_prefs_signal():
    saved = bi.current_prefs()
    try:
        widgets = _make_all()
        grid = iw.MetricGrid()
        grid.add(iw.MetricCard(label="g", value="1", state="ok"))
        for w in widgets:
            _render(w)
        # cambiar tema dispara _PrefsBus.emit() dentro de apply_preferences
        bi.apply_preferences(theme="dark")
        # los widgets siguen vivos y re-renderizan sin crashear
        for w in widgets:
            px = _render(w)
            assert not px.isNull()
        _app.processEvents()
    finally:
        bi.apply_preferences(**saved)


def test_gauge_clamps_and_no_marker():
    # value fuera de [0,1] se clampa; marker None no crashea
    for v in (-0.5, 0.0, 0.5, 1.0, 1.7):
        _render(iw.GaugePill(label="g", value=v))
    _render(iw.GaugePill(label="g", value=0.3, marker=None))
    _render(iw.GaugePill(label="g", value=0.3, marker=0.9, color="danger"))
