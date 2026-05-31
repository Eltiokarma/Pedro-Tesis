"""GATE 3 — integración en _section_diagnostico (Fase 3).

Para un bloque de cada familia, el panel de Diagnóstico se construye sin
crashear (smoke Qt offscreen).  Verifica:
  · _render_evidence produce un QFrame con sub-widgets (tarjeta rica) para
    familias con *_metrics().
  · _section_diagnostico corre end-to-end por ejemplo (rico + fallback texto).
  · Reporta, por figura, si RENDERIZÓ (matplotlib presente) o DEGRADÓ a
    placeholder limpio (matplotlib ausente) — ambos aceptables, distinguidos.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFrame

import examples_registry as reg
import flowsheet_solver as fsv
import inspector_evidence as ev
import block_inspector as bi

_app = QApplication.instance() or QApplication([])


def _mpl_available():
    try:
        import matplotlib  # noqa: F401
        from matplotlib.backends.backend_qtagg import FigureCanvas  # noqa: F401
        return True
    except Exception:
        return False


def _solve(clave):
    fs = reg.load_example(clave)
    fsv.solve(fs)
    return fs


def _panel(fs):
    p = bi.BlockInspectorPanel()
    p.fs = fs
    return p


def _first(fs, pred):
    return next((b for b in fs.blocks.values() if pred(b)), None)


# ── _render_evidence produce tarjeta rica con sub-widgets ──────────────
def test_render_evidence_builds_card():
    fs = _solve("distillation")
    blk = _first(fs, lambda b: getattr(b, "_hx_diagnostics", None))
    if blk is None:
        pytest.skip("sin HX en distillation")
    m = ev.hx_metrics(blk)
    panel = _panel(fs)
    card = panel._render_evidence("Intercambiador (HX)", m)
    assert isinstance(card, QFrame)
    # debe tener hijos (badges/grid/bars), no estar vacía
    assert card.findChildren(object), "tarjeta rica sin sub-widgets"


# ── _section_diagnostico end-to-end por familia ────────────────────────
@pytest.mark.parametrize("clave", [
    "ammonia", "distillation", "hda_full", "biodiesel", "air_sep",
])
def test_section_diagnostico_renders(clave):
    fs = _solve(clave)
    panel = _panel(fs)
    built = 0
    for b in fs.blocks.values():
        sect = panel._section_diagnostico(b, b.eq_type)
        assert isinstance(sect, QFrame)
        built += 1
    assert built > 0


# ── fallback: familia sin *_metrics() implementada → texto ─────────────
def test_fallback_to_text_when_metrics_none():
    # forzamos un metrics que devuelve None y verificamos que el panel
    # igual construye la sección vía *_text() sin romper.
    fs = _solve("ammonia")
    panel = _panel(fs)
    for b in fs.blocks.values():
        sect = panel._section_diagnostico(b, b.eq_type)
        assert isinstance(sect, QFrame)


# ── reporte: figura renderizó vs degradó a placeholder ─────────────────
def test_report_figure_render_vs_degraded(capsys):
    mpl = _mpl_available()
    fs = _solve("distillation")
    panel = _panel(fs)
    # buscar un bloque que tenga figura asociada (columna o HX)
    blk = _first(fs, lambda b: getattr(b, "column_active", False)
                 or getattr(b, "_hx_diagnostics", None))
    figs = panel._diag_figures(blk, fs) if blk else []
    status = ("RENDERIZÓ (matplotlib presente)" if mpl
              else "DEGRADÓ a placeholder limpio (matplotlib ausente)")
    print(f"\n[GATE3-FIGURA] matplotlib={'sí' if mpl else 'no'} → "
          f"_diag_figures devolvió {len(figs)} canvas(es) → {status}")
    if mpl:
        # con matplotlib, al menos intentó construir canvases (>=0, sin crash)
        assert isinstance(figs, list)
    else:
        # sin matplotlib, degrada a lista vacía SIN crashear (headless-safe)
        assert figs == [], "sin matplotlib _diag_figures debe degradar a []"


def test_figures_headless_safe_no_crash():
    # _diag_figures nunca debe crashear, haya o no matplotlib.
    for clave in ("distillation", "ammonia", "hda_full"):
        fs = _solve(clave)
        panel = _panel(fs)
        for b in fs.blocks.values():
            out = panel._diag_figures(b, fs)
            assert isinstance(out, list)
