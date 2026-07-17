"""GATE — EconRichView (única UI del panel económico, rediseño 1e).

El layout completo (header + hero + sidebar de 7 panes + footer de acciones)
instancia y pinta offscreen sin crashear, en el barrido temas×acentos×
densidades, reusa econ_metrics como fuente, el sidebar navega 1:1 a los panes
(sin segmented duplicado) y las señales close/rerun funcionan.  Acepta m=None
(estado vacío pre-cálculo).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap

import examples_registry as reg
import simulate_engine as se
import block_inspector as bi
from econ_evidence import econ_metrics
from econ_richview import (EconRichView, _PanelHeader, _HeroStrip, _Sidebar,
                           _Footer)

_app = QApplication.instance() or QApplication([])


def _metrics(clave="methanol"):
    econ = se.simulate(reg.load_example(clave).to_dict(),
                       run_economics=True)["economics"]
    return econ_metrics(econ)


def _render(w, sz=(600, 760)):
    w.resize(*sz)
    px = QPixmap(w.size())
    w.render(px)
    return px


def test_richview_renders():
    rv = EconRichView(_metrics(), project="methanol")
    assert not _render(rv).isNull()


def test_richview_has_all_zones():
    rv = EconRichView(_metrics())
    assert len(rv.findChildren(_PanelHeader)) == 1
    assert len(rv.findChildren(_HeroStrip)) == 1
    assert len(rv.findChildren(_Sidebar)) == 1
    assert len(rv.findChildren(_Footer)) == 1


def test_sidebar_switches_pane_one_to_one():
    """7 ítems → 7 panes reales, mapeo identidad (antes 4 de 7 ítems
    colapsaban al mismo tab)."""
    rv = EconRichView(_metrics())
    assert rv._tabs.count() == 7
    for k in range(7):
        rv._side._on_item(k)
        assert rv._tabs.currentIndex() == k


def test_empty_state():
    """m=None → estado vacío: placeholders, hero en '—', arranca en
    Parámetros."""
    rv = EconRichView(None)
    assert rv._tabs.count() == 7
    assert rv._tabs.currentIndex() == 6
    assert not _render(rv).isNull()


def test_signals_fire():
    rv = EconRichView(_metrics())
    closed = []; reran = []
    rv.closeClicked.connect(lambda: closed.append(1))
    rv.rerun.connect(lambda: reran.append(1))
    # header close
    rv.findChildren(_PanelHeader)[0].closeClicked.emit()
    assert closed == [1]
    # footer rerun
    rv.findChildren(_Footer)[0].rerun.emit()
    assert reran == [1]


def test_theme_sweep():
    saved = bi.current_prefs()
    try:
        m = _metrics()
        for theme in ("light", "dark"):
            for accent in ("teal", "oliva", "cobalto", "terracota"):
                for density in ("compact", "cozy", "comfy"):
                    bi.apply_preferences(theme=theme, accent=accent,
                                         density=density)
                    assert not _render(EconRichView(m)).isNull(), (
                        f"{theme}/{accent}/{density}")
    finally:
        bi.apply_preferences(**saved)


def test_negative_npv_renders():
    # ejemplo con NPV negativo (hda_full default) → hero/footer en danger
    rv = EconRichView(_metrics("hda_full"))
    assert not _render(rv).isNull()


def test_no_duplicate_navigation():
    """La segmented-tab bar duplicada murió: el sidebar es LA navegación
    (no queda ningún EconTabs dentro del rich view)."""
    from econ_widgets import EconTabs
    rv = EconRichView(_metrics())
    assert len(rv.findChildren(EconTabs)) == 0
