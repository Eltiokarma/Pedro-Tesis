"""GATE 2 — átomos del Panel Económico (econ_widgets), render headless-safe.

Cada átomo nuevo (NpvHero, EconTabs, ConfigPanel, FinancialTable) instancia y
pinta offscreen sin crashear, en un barrido 2 temas × 4 acentos × 3 densidades,
re-pinta al emitir _PrefsBus, y reusa _tok (TOK en caliente). Default del panel:
light·oliva·cozy. Qt puro — no depende de matplotlib.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap

import block_inspector as bi
import econ_widgets as ew

_app = QApplication.instance() or QApplication([])


def _render(w, sz=(300, 120)):
    w.resize(*sz)
    px = QPixmap(w.size())
    w.render(px)
    return px


def _make_all():
    return [
        ew.NpvHero(value=11.8e6, sub="rentable"),
        ew.NpvHero(value=-1.8e6),
        ew.EconTabs(),
        ew.ConfigPanel({"project_life": 10, "tax_rate": 0.30,
                        "discount_rate": 0.10, "dep_method": "straight_line"}),
        ew.FinancialTable(
            headers=["Concepto", "M USD", "%"],
            rows=[{"cells": ["Revenue", "40.5", "100%"]},
                  {"cells": ["COM_d", "-34.2", "84%"], "pos_neg": True},
                  {"cells": ["EBT", "6.3", "16%"], "kind": "total",
                   "pos_neg": True}]),
    ]


def test_atoms_instantiate_and_render():
    for w in _make_all():
        assert not _render(w).isNull()


def test_npvhero_sign_color_renders():
    # ambos signos deben pintar sin crashear (verde / danger por ribbon)
    for v in (-5e6, 0.0, 12e6):
        assert not _render(ew.NpvHero(value=v)).isNull()


def test_econtabs_switch_emits_and_restyles():
    t = ew.EconTabs()
    got = []
    t.changed.connect(got.append)
    t._buttons[2].click()      # Contabilidad
    assert t.current_index() == 2
    assert got == [2]
    assert not _render(t, (320, 36)).isNull()


def test_configpanel_collapse_expand():
    cfg = ew.ConfigPanel({"project_life": 10, "tax_rate": 0.30,
                          "discount_rate": 0.10, "dep_method": "macrs"})
    assert cfg.is_open() is False
    cfg.toggle()
    assert cfg.is_open() is True
    # isVisibleTo (no isVisible) porque el panel no se hace show() en headless;
    # refleja el estado de visibilidad relativo al padre tras el toggle.
    assert cfg._form.isVisibleTo(cfg) is True
    assert cfg._summary.isVisibleTo(cfg) is False
    cfg.toggle()
    assert cfg.is_open() is False
    assert cfg._form.isVisibleTo(cfg) is False
    assert not _render(cfg, (320, 160)).isNull()


def test_theme_accent_density_sweep():
    saved = bi.current_prefs()
    try:
        for theme in ("light", "dark"):
            for accent in ("teal", "terracota", "cobalto", "oliva"):
                for density in ("compact", "cozy", "comfy"):
                    bi.apply_preferences(theme=theme, accent=accent,
                                         density=density)
                    for w in _make_all():
                        assert not _render(w).isNull(), (
                            f"render nulo {theme}/{accent}/{density} "
                            f"{type(w).__name__}")
    finally:
        bi.apply_preferences(**saved)


def test_default_light_oliva_cozy():
    saved = bi.current_prefs()
    try:
        bi.apply_preferences(theme="light", accent="oliva", density="cozy")
        for w in _make_all():
            assert not _render(w).isNull()
    finally:
        bi.apply_preferences(**saved)


def test_repaint_on_prefs_signal():
    saved = bi.current_prefs()
    try:
        widgets = _make_all()
        for w in widgets:
            _render(w)
        bi.apply_preferences(theme="dark")   # dispara _PrefsBus.emit()
        for w in widgets:
            assert not _render(w).isNull()
        _app.processEvents()
    finally:
        bi.apply_preferences(**saved)


def test_degenerate_sizes_no_crash():
    from PySide6.QtGui import QPixmap as _PX
    for sz in [(0, 0), (1, 1), (8, 8), (12, 100)]:
        for w in _make_all():
            w.resize(*sz)
            px = _PX(max(sz[0], 1), max(sz[1], 1))
            w.render(px)   # no debe lanzar
