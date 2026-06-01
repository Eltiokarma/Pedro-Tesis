"""GATE 4 — integración de la vista rica en EconomicsPanel (Fase 4).

El panel económico (mismo punto de entrada del usuario: action_launch_analysis
→ EconomicsPanel) monta la vista rica sin crashear: tabs Resultados/Monte Carlo/
Contabilidad, NpvHero + GaugePill TIR + MetricGrid CAPEX + waterfall + tablas.
Aditivo: el MonteCarloPanel vivo sigue funcionando; si la vista rica fallara,
el texto plano queda como fallback.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap

import examples_registry as reg
import block_inspector as bi
from economics_panel import EconomicsPanel, MonteCarloPanel
from econ_widgets import NpvHero, FinancialTable
from inspector_widgets import MetricCard, StatusBadge

_app = QApplication.instance() or QApplication([])


def _panel(clave="hda_full"):
    p = EconomicsPanel(reg.load_example(clave))
    p._run()
    return p


def test_rich_view_populates():
    p = _panel()
    assert p._has_rich is True
    assert p.last_result is not None
    # pane Resultados poblado
    assert len(p._pane_res_host.findChildren(NpvHero)) == 1
    assert len(p._pane_res_host.findChildren(MetricCard)) >= 4
    assert len(p._pane_res_host.findChildren(StatusBadge)) >= 1
    # pane Contabilidad: P&L + cash flow
    assert len(p._pane_acc_host.findChildren(FinancialTable)) >= 1


def test_tabs_switch_panes():
    p = _panel()
    p._tabs._buttons[2].click()
    assert p._stack.currentIndex() == 2     # Contabilidad
    p._tabs._buttons[1].click()
    assert p._stack.currentIndex() == 1     # Monte Carlo
    p._tabs._buttons[0].click()
    assert p._stack.currentIndex() == 0     # Resultados


def test_panel_renders_without_crash():
    p = _panel()
    p.resize(560, 720)
    px = QPixmap(p.size())
    p.render(px)
    assert not px.isNull()


def test_montecarlo_panel_still_alive():
    p = _panel()
    fs_dict = reg.load_example("hda_full").to_dict()
    mcp = MonteCarloPanel(fs_dict, {}, p)
    assert mcp is not None


def test_entry_point_uses_economics_panel():
    """El botón del usuario (action_launch_analysis) abre EconomicsPanel —
    no un panel huérfano."""
    src = open("flowsheet_qt.py", encoding="utf-8").read()
    i = src.find("def action_launch_analysis")
    assert i != -1
    body = src[i:i + 800]
    assert "EconomicsPanel" in body


def test_default_oliva_renders():
    saved = bi.current_prefs()
    try:
        bi.apply_preferences(theme="light", accent="oliva", density="cozy")
        p = _panel("methanol")
        p.resize(560, 720)
        px = QPixmap(p.size())
        p.render(px)
        assert not px.isNull()
        assert len(p._pane_res_host.findChildren(NpvHero)) == 1
    finally:
        bi.apply_preferences(**saved)


def test_waterfall_canvas_when_mpl_present():
    try:
        from matplotlib.backends.backend_qtagg import FigureCanvas
    except Exception:
        pytest.skip("matplotlib/Qt backend no disponible")
    p = _panel()
    canvases = p._pane_res_host.findChildren(FigureCanvas)
    assert len(canvases) == 1   # waterfall embebido en pane Resultados
