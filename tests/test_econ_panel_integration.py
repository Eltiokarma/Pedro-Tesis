"""GATE 4 — EconomicsPanel monta la EconRichView como ÚNICA UI (rediseño 1e/1f).

El panel económico (mismo punto de entrada del usuario: action_launch_analysis
→ EconomicsPanel) monta la rich view desde el arranque: sidebar de 7 panes
reales (Resumen/CAPEX/OPEX/Cash flow/Monte Carlo/Contabilidad/Parámetros),
KPIs una sola vez en el hero, footer de acciones, Monte Carlo EMBEBIDO con
figuras (no ventana ASCII aparte) y parámetros como pane — sin dump de texto
plano ni tab bar exterior duplicada.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QTextEdit
from PySide6.QtGui import QPixmap

import examples_registry as reg
import block_inspector as bi
from economics_panel import EconomicsPanel, MonteCarloPane
from econ_widgets import FinancialTable
from econ_richview import EconRichView
from inspector_widgets import MetricCard

_app = QApplication.instance() or QApplication([])


def _panel(clave="hda_full"):
    p = EconomicsPanel(reg.load_example(clave))
    p._run()
    return p


def test_rich_view_is_the_only_ui():
    p = _panel()
    assert p.last_result is not None
    rvs = p.findChildren(EconRichView)
    assert len(rvs) == 1
    rv = rvs[0]
    # dentro del rich view: MetricCards (CAPEX/OPEX) + tablas
    assert len(rv.findChildren(MetricCard)) >= 4
    assert len(rv.findChildren(FinancialTable)) >= 1
    # el dump ASCII murió: no hay QTextEdit en el panel
    assert len(p.findChildren(QTextEdit)) == 0


def test_seven_real_panes():
    """Sidebar de 7 ítems → 7 panes REALES (antes 4 de 7 ruteaban al
    mismo tab)."""
    p = _panel()
    rv = p._rich
    assert rv._tabs.count() == 7
    for k in range(7):
        rv._side._on_item(k)
        assert rv._tabs.currentIndex() == k


def test_params_pane_hosts_form():
    """Los parámetros viven en el pane ⚙ (índice 6) — el formulario está
    embebido en la rich view, no apilado encima."""
    p = _panel()
    rv = p._rich
    rv.set_pane(6)
    # el formulario (spin de vida del proyecto) es descendiente del rich view
    assert p.spin_life in rv.findChildren(type(p.spin_life))


def test_empty_state_starts_at_params():
    """Antes de calcular: rich view montada con placeholders y el pane
    activo es Parámetros."""
    p = EconomicsPanel(reg.load_example("methanol"))
    assert p._rich is not None
    assert p._rich._tabs.currentIndex() == 6
    assert p.last_result is None


def test_montecarlo_embedded_pane():
    """Monte Carlo es un pane embebido (índice 4) con la configuración de
    variables — la ventana ASCII aparte murió."""
    p = _panel()
    rv = p._rich
    panes_mc = rv.findChildren(MonteCarloPane)
    assert len(panes_mc) == 1
    assert panes_mc[0] is p._mc_pane
    # variables detectadas del flowsheet (hda_full tiene productos/feeds)
    assert len(p._mc_pane._rows) >= 1


def test_panel_fits_small_screen():
    """El panel cabe en laptops chicas: mínimo bajo y los panes scrollean
    por dentro (un solo nivel de scroll por pane)."""
    p = EconomicsPanel(reg.load_example("hda_full"))
    assert p.minimumSize().height() <= 400
    p.resize(560, 480)
    px = QPixmap(p.size())
    p.render(px)
    assert not px.isNull()


def test_panel_renders_without_crash():
    p = _panel()
    p.resize(760, 720)
    px = QPixmap(p.size())
    p.render(px)
    assert not px.isNull()


def test_rerun_keeps_hosted_widgets():
    """Re-correr reconstruye la rich view sin destruir el formulario de
    parámetros ni el pane Monte Carlo (widgets huésped)."""
    p = _panel("methanol")
    params_before = p._params_widget
    mc_before = p._mc_pane
    p._run()
    assert p._params_widget is params_before
    assert p._mc_pane is mc_before
    assert len(p.findChildren(EconRichView)) == 1


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
        assert len(p.findChildren(EconRichView)) == 1
    finally:
        bi.apply_preferences(**saved)


def test_waterfall_canvas_when_mpl_present():
    try:
        from matplotlib.backends.backend_qtagg import FigureCanvas
    except Exception:
        pytest.skip("matplotlib/Qt backend no disponible")
    p = _panel()
    # waterfall en Resumen y en Cash flow (2 canvases tras calcular)
    canvases = p._rich.findChildren(FigureCanvas)
    assert len(canvases) >= 1


def test_no_debug_leaks_in_header():
    """El subtítulo del header es proyecto · CEPCI, no internals del motor
    (regresión: 'run_economics=True' visible en la UI)."""
    p = _panel("methanol")
    from econ_richview import _PanelHeader
    hdr = p._rich.findChildren(_PanelHeader)[0]
    assert "run_economics" not in hdr._lab_desc.text()
    assert "CEPCI" in hdr._lab_desc.text()
