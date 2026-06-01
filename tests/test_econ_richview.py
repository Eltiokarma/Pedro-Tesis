"""GATE — EconRichView (ensamblado fiel al mockup), render headless-safe.

El layout completo (header + hero strip + sidebar + tabs + footer) instancia y
pinta offscreen sin crashear, en el barrido temas×acentos×densidades (default
light·oliva·cozy), reusa econ_metrics como fuente, y las señales close/rerun/
sidebar funcionan.
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


def test_sidebar_switches_tab():
    rv = EconRichView(_metrics())
    # Monte Carlo (índice 4 del sidebar) → tab 1
    rv._side._on_item(4)
    assert rv._tabs.currentIndex() == 1
    # Contabilidad (índice 5) → tab 2
    rv._side._on_item(5)
    assert rv._tabs.currentIndex() == 2
    # CAPEX (índice 1) → tab 0 (Resultados)
    rv._side._on_item(1)
    assert rv._tabs.currentIndex() == 0


def test_signals_fire():
    rv = EconRichView(_metrics())
    closed = []; reran = []; mc = []
    rv.closeClicked.connect(lambda: closed.append(1))
    rv.rerun.connect(lambda: reran.append(1))
    rv2 = EconRichView(_metrics(), on_montecarlo=lambda: mc.append(1))
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
