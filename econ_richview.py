"""econ_richview.py — Ensamblado visual del Panel Económico, fiel al mockup
(design_handoff_panel_economico). Hermano del BlockInspector.

Reproduce el layout del board `econFullRes`:
    ┌─ EconRichView (columna) ───────────────────────────────┐
    │  PanelHeader  [$ ícono] ECONOMÍA · RENTABILIDAD · proj ✕│
    │  HeroStrip    NPV +11.8 grande | TIR | Payback | ROI    │
    │  ┌ Sidebar ┬ Main (tabs Resultados/MC/Contabilidad) ──┐ │
    │  │ Resumen │ evidence cards + figura + tablas          │ │
    │  │ CAPEX   │                                            │ │
    │  │ ●Viable │                                            │ │
    │  └─────────┴────────────────────────────────────────────┘│
    │  Footer  NPV | TIR | Payback | CAPEX     [Re-correr]     │
    └─────────────────────────────────────────────────────────┘

Presentación pura: recibe el dict de econ_metrics(econ) (Fase 1), no recalcula.
Reusa MetricCard/MetricGrid/StatusBadge/GaugePill (Inspector) + NpvHero/
FinancialTable (econ_widgets) + cashflow_figure (econ_figures, headless-safe).
Color desde TOK en caliente, suscrito a _PrefsBus. Medidas del components.css.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QStackedWidget, QScrollArea, QPushButton, QSizePolicy,
)

import pfd_fonts
from block_inspector import _PrefsBus
from inspector_widgets import _tok, MetricCard, MetricGrid, StatusBadge, GaugePill
from econ_widgets import NpvHero, FinancialTable


def _musd(x, dec=2):
    if x is None:
        return "—"
    try:
        return f"{float(x)/1e6:,.{dec}f}"
    except (TypeError, ValueError):
        return str(x)


# ─────────────────────────────────────────────────────────────────────
#  PanelHeader (.ph) — ícono + tag + descripción + close
# ─────────────────────────────────────────────────────────────────────
class _PanelHeader(QFrame):
    closeClicked = Signal()

    def __init__(self, tag="ECONOMÍA", title="Rentabilidad del flowsheet",
                 desc="run_economics=True", parent=None):
        super().__init__(parent)
        self._tag, self._title, self._desc = tag, title, desc
        self.setFixedHeight(58)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 12, 10); lay.setSpacing(10)
        # ícono $
        self._ico = QLabel("$")
        self._ico.setFixedSize(36, 36)
        self._ico.setAlignment(Qt.AlignCenter)
        self._ico.setFont(QFont(pfd_fonts.SANS, 13, QFont.Bold))
        lay.addWidget(self._ico)
        # bloque texto
        txt = QVBoxLayout(); txt.setSpacing(1); txt.setContentsMargins(0, 0, 0, 0)
        self._lab_tag = QLabel(tag)
        self._lab_tag.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
        self._lab_title = QLabel(title)
        self._lab_title.setFont(QFont(pfd_fonts.MONO, 12))
        self._lab_desc = QLabel(desc)
        self._lab_desc.setFont(QFont(pfd_fonts.SANS, 8))
        txt.addWidget(self._lab_tag)
        txt.addWidget(self._lab_title)
        txt.addWidget(self._lab_desc)
        lay.addLayout(txt)
        lay.addStretch(1)
        # close
        self._x = QPushButton("✕")
        self._x.setFixedSize(26, 26)
        self._x.setCursor(Qt.PointingHandCursor)
        self._x.clicked.connect(self.closeClicked.emit)
        lay.addWidget(self._x, alignment=Qt.AlignTop)
        _PrefsBus.signal().connect(self._restyle)
        self._restyle()

    def _restyle(self):
        self.setStyleSheet(
            f"background:{_tok('bg_elev')}; "
            f"border-bottom:1px solid {_tok('line')};")
        self._ico.setStyleSheet(
            f"background:{_tok('accent_tint')}; color:{_tok('accent')}; "
            f"border:1px solid {_tok('accent_soft')}; border-radius:9px;")
        self._lab_tag.setStyleSheet(
            f"color:{_tok('ink_soft')}; letter-spacing:1px;")
        self._lab_title.setStyleSheet(f"color:{_tok('ink')};")
        self._lab_desc.setStyleSheet(f"color:{_tok('ink_mute')};")
        self._x.setStyleSheet(
            f"QPushButton {{ color:{_tok('ink_mute')}; border:none; "
            f"background:transparent; border-radius:6px; font-size:13px; }}"
            f"QPushButton:hover {{ background:{_tok('bg_mute')}; "
            f"color:{_tok('ink')}; }}")


# ─────────────────────────────────────────────────────────────────────
#  HeroStrip (.strip) — NPV grande + KPIs en grid horizontal
# ─────────────────────────────────────────────────────────────────────
class _Kpi(QFrame):
    def __init__(self, kicker, value, sub="", tone="", parent=None):
        super().__init__(parent)
        self._tone = tone
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(1)
        self._k = QLabel(kicker.upper()); self._k.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
        self._v = QLabel(value); self._v.setFont(QFont(pfd_fonts.MONO, 16, QFont.DemiBold))
        self._s = QLabel(sub); self._s.setFont(QFont(pfd_fonts.SANS, 8))
        v.addWidget(self._k); v.addWidget(self._v); v.addWidget(self._s)
        _PrefsBus.signal().connect(self._restyle); self._restyle()

    def _restyle(self):
        self._k.setStyleSheet(f"color:{_tok('ink_soft')}; letter-spacing:1px;")
        col = (_tok("green") if self._tone == "pos"
               else _tok("danger") if self._tone == "neg" else _tok("ink"))
        self._v.setStyleSheet(f"color:{col};")
        self._s.setStyleSheet(f"color:{_tok('ink_mute')};")


class _HeroStrip(QFrame):
    def __init__(self, m, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 9, 14, 9); lay.setSpacing(16)
        npv = m["heroes"]["npv"]["value"]
        irr = m["heroes"]["irr"]["value"]
        hurdle = m["heroes"]["irr"]["hurdle"]
        pb = m["heroes"]["payback"]; roi = m["heroes"]["roi"]
        # NPV grande (1.5fr)
        npv_box = QVBoxLayout(); npv_box.setSpacing(2); npv_box.setContentsMargins(0, 0, 0, 0)
        self._npv_k = QLabel(f"NPV · @ {hurdle:.0f} %" if hurdle else "NPV")
        self._npv_k.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
        row = QHBoxLayout(); row.setSpacing(5); row.setContentsMargins(0, 0, 0, 0)
        neg = (npv or 0) < 0
        self._npv_v = QLabel(f"{_musd(npv, 1)}")
        self._npv_v.setFont(QFont(pfd_fonts.MONO, 26, QFont.DemiBold))
        self._npv_neg = neg
        self._npv_u = QLabel("M USD"); self._npv_u.setFont(QFont(pfd_fonts.MONO, 11))
        row.addWidget(self._npv_v, alignment=Qt.AlignBottom)
        row.addWidget(self._npv_u, alignment=Qt.AlignBottom)
        row.addStretch(1)
        npv_box.addWidget(self._npv_k); npv_box.addLayout(row)
        nw = QWidget(); nw.setLayout(npv_box)
        lay.addWidget(nw, stretch=3)
        # KPIs
        self._kpis = [
            _Kpi("TIR", f"{irr:.1f} %" if irr is not None else "—",
                 f"hurdle {hurdle:.0f} %" if hurdle else "",
                 "pos" if (irr or 0) > (hurdle or 0) else "neg"),
            _Kpi("Payback", f"{pb:.1f} a" if pb is not None else "—",
                 "desde arranque"),
            _Kpi("ROI", f"{roi:.0f} %" if roi is not None else "—", "anual medio"),
        ]
        for k in self._kpis:
            lay.addWidget(k, stretch=2)
        _PrefsBus.signal().connect(self._restyle); self._restyle()

    def _restyle(self):
        self.setStyleSheet(
            f"background:{_tok('bg_mute')}; "
            f"border-bottom:1px solid {_tok('line')};")
        self._npv_k.setStyleSheet(f"color:{_tok('ink_soft')}; letter-spacing:1px;")
        self._npv_v.setStyleSheet(
            f"color:{_tok('danger') if self._npv_neg else _tok('green')}; "
            f"letter-spacing:-0.5px;")
        self._npv_u.setStyleSheet(f"color:{_tok('ink_soft')};")


# ─────────────────────────────────────────────────────────────────────
#  Sidebar (.side) — navegación + chip de veredicto
# ─────────────────────────────────────────────────────────────────────
class _Sidebar(QFrame):
    itemClicked = Signal(int)

    ITEMS = [("Resumen", "Σ"), ("CAPEX", "$"), ("OPEX", "¤"),
             ("Cash flow", "⌃"), ("Monte Carlo", "∿"),
             ("Contabilidad", "≡"), ("Parámetros", "⚙")]

    def __init__(self, verdict, parent=None):
        super().__init__(parent)
        self.setFixedWidth(150)
        self._verdict = verdict
        self._active = 0
        v = QVBoxLayout(self); v.setContentsMargins(8, 10, 8, 10); v.setSpacing(2)
        self._labels = []
        for i, (name, ico) in enumerate(self.ITEMS):
            item = QPushButton(f"  {ico}   {name}")
            item.setCursor(Qt.PointingHandCursor)
            item.setFont(QFont(pfd_fonts.SANS, 10))
            item.clicked.connect(lambda _=False, k=i: self._on_item(k))
            self._labels.append(item)
            v.addWidget(item)
        v.addStretch(1)
        # chip veredicto
        self._dof = QLabel(f"●  {verdict.get('text', '—')}")
        self._dof.setFont(QFont(pfd_fonts.SANS, 9, QFont.DemiBold))
        v.addWidget(self._dof)
        _PrefsBus.signal().connect(self._restyle); self._restyle()

    def _on_item(self, k):
        self._active = k
        self._restyle()
        self.itemClicked.emit(k)

    def set_active(self, k):
        self._active = k
        self._restyle()

    def _restyle(self):
        self.setStyleSheet(
            f"background:{_tok('bg_mute')}; "
            f"border-right:1px solid {_tok('line')};")
        for i, btn in enumerate(self._labels):
            if i == self._active:
                btn.setStyleSheet(
                    f"QPushButton {{ text-align:left; border:none; "
                    f"border-left:2px solid {_tok('accent')}; "
                    f"background:{_tok('bg_elev')}; color:{_tok('ink')}; "
                    f"border-radius:6px; padding:6px 8px; }}")
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ text-align:left; border:none; "
                    f"background:transparent; color:{_tok('ink')}; "
                    f"border-radius:6px; padding:6px 8px; }}"
                    f"QPushButton:hover {{ background:{_tok('bg_elev')}; }}")
        k = self._verdict.get("kind", "neutral")
        col = {"ok": "green", "warn": "amber", "danger": "danger"}.get(k, "ink_soft")
        self._dof.setStyleSheet(
            f"background:{_tok(col + '_bg' if col != 'ink_soft' else 'bg_mute')}; "
            f"color:{_tok(col)}; padding:8px; border-radius:7px;")


# ─────────────────────────────────────────────────────────────────────
#  Footer (.foot) — stats + botón re-correr
# ─────────────────────────────────────────────────────────────────────
class _Footer(QFrame):
    rerun = Signal()

    def __init__(self, m, parent=None):
        super().__init__(parent)
        self.setFixedHeight(46)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8); lay.setSpacing(16)
        h = m["heroes"]; cap = m["capex"]
        stats = [
            ("NPV", _musd(h["npv"]["value"], 1) + " M",
             "pos" if (h["npv"]["value"] or 0) >= 0 else "neg"),
            ("TIR", f"{h['irr']['value']:.1f} %" if h["irr"]["value"] is not None else "—", ""),
            ("Payback", f"{h['payback']:.1f} a" if h["payback"] is not None else "—", ""),
            ("CAPEX", _musd(cap.get("capex_total"), 1) + " M", ""),
        ]
        self._stat_widgets = []
        for k, val, tone in stats:
            box = QVBoxLayout(); box.setSpacing(0); box.setContentsMargins(0, 0, 0, 0)
            lk = QLabel(k.upper()); lk.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
            lv = QLabel(val); lv.setFont(QFont(pfd_fonts.MONO, 11, QFont.DemiBold))
            box.addWidget(lk); box.addWidget(lv)
            w = QWidget(); w.setLayout(box)
            lay.addWidget(w)
            self._stat_widgets.append((lk, lv, tone))
        lay.addStretch(1)
        self._btn = QPushButton("Re-correr análisis")
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setFont(QFont(pfd_fonts.SANS, 9, QFont.Bold))
        self._btn.clicked.connect(self.rerun.emit)
        lay.addWidget(self._btn)
        _PrefsBus.signal().connect(self._restyle); self._restyle()

    def _restyle(self):
        self.setStyleSheet(
            f"background:{_tok('bg_mute')}; "
            f"border-top:1px solid {_tok('line')};")
        for lk, lv, tone in self._stat_widgets:
            lk.setStyleSheet(f"color:{_tok('ink_soft')}; letter-spacing:1px;")
            col = (_tok("green") if tone == "pos"
                   else _tok("danger") if tone == "neg" else _tok("ink"))
            lv.setStyleSheet(f"color:{col};")
        self._btn.setStyleSheet(
            f"QPushButton {{ background:{_tok('accent')}; color:#ffffff; "
            f"border:0; border-radius:6px; padding:7px 14px; }}"
            f"QPushButton:hover {{ background:{_tok('accent_deep')}; }}")


# ─────────────────────────────────────────────────────────────────────
#  Tarjeta de evidencia (.evidence) — header con badges + cuerpo
# ─────────────────────────────────────────────────────────────────────
def _evidence_card(title, badges, body_widget):
    card = QFrame(); card.setObjectName("evCard")
    v = QVBoxLayout(card); v.setContentsMargins(12, 10, 12, 12); v.setSpacing(8)
    head = QHBoxLayout(); head.setSpacing(6); head.setContentsMargins(0, 0, 0, 0)
    t = QLabel(title); t.setFont(QFont(pfd_fonts.SANS, 10, QFont.DemiBold))
    t.setStyleSheet(f"color:{_tok('ink')};")
    head.addWidget(t); head.addStretch(1)
    for b in (badges or []):
        head.addWidget(StatusBadge(b[0], b[1]))
    v.addLayout(head)
    v.addWidget(body_widget)
    card.setStyleSheet(
        f"#evCard {{ background:{_tok('bg_elev')}; "
        f"border:1px solid {_tok('line')}; border-radius:8px; }}")
    return card


# ─────────────────────────────────────────────────────────────────────
#  EconRichView — el ensamblado completo
# ─────────────────────────────────────────────────────────────────────
class EconRichView(QWidget):
    """Vista rica del panel económico, fiel al mockup. Recibe el dict de
    econ_metrics(econ). Señales closeClicked/rerun para que el caller
    (EconomicsPanel) reaccione."""
    closeClicked = Signal()
    rerun = Signal()
    editParams = Signal()

    def __init__(self, m, project="", on_montecarlo=None, parent=None):
        super().__init__(parent)
        self._m = m
        self._on_montecarlo = on_montecarlo
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # header
        hdr = _PanelHeader(desc=project or "run_economics=True")
        hdr.closeClicked.connect(self.closeClicked.emit)
        root.addWidget(hdr)
        # hero strip
        root.addWidget(_HeroStrip(m))
        # cuerpo: sidebar + main(tabs)
        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        self._side = _Sidebar(m["verdict"])
        self._side.itemClicked.connect(self._on_side)
        body.addWidget(self._side)
        self._main = self._build_main(m)
        body.addWidget(self._main, stretch=1)
        bw = QWidget(); bw.setLayout(body)
        root.addWidget(bw, stretch=1)
        # footer
        ft = _Footer(m)
        ft.rerun.connect(self.rerun.emit)
        root.addWidget(ft)
        _PrefsBus.signal().connect(self._restyle); self._restyle()

    # mapeo sidebar → tab (Resumen/CAPEX/OPEX/Cashflow→Resultados; MC; Contab.)
    def _on_side(self, k):
        if k == 6:                     # Parámetros → editar inputs
            self.editParams.emit()
            return
        idx = {4: 1, 5: 2}.get(k, 0)   # Monte Carlo→1, Contabilidad→2, resto→0
        self._tabs.setCurrentIndex(idx)

    def _build_main(self, m):
        main = QWidget()
        v = QVBoxLayout(main); v.setContentsMargins(16, 14, 16, 14); v.setSpacing(12)
        # tabs (segmented) → stack
        from econ_widgets import EconTabs
        self._econtabs = EconTabs(("Resultados", "Monte Carlo", "Contabilidad"))
        self._tabs = QStackedWidget()
        self._econtabs.changed.connect(self._tabs.setCurrentIndex)
        self._tabs.setMinimumHeight(300)
        v.addWidget(self._econtabs)
        v.addWidget(self._tabs, stretch=1)
        # panes
        self._tabs.addWidget(self._scroll(self._pane_resultados(m)))
        self._tabs.addWidget(self._scroll(self._pane_montecarlo(m)))
        self._tabs.addWidget(self._scroll(self._pane_contabilidad(m)))
        return main

    @staticmethod
    def _scroll(widget):
        sa = QScrollArea(); sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.NoFrame)
        sa.setWidget(widget)
        return sa

    # ── pane Resultados: CAPEX cards + waterfall + OPEX ───────────────
    def _pane_resultados(self, m):
        host = QWidget(); v = QVBoxLayout(host); v.setSpacing(12)
        v.setContentsMargins(0, 0, 0, 0)
        cap = m["capex"]
        grid = MetricGrid()
        for lab, val, st, flag in (
                ("ISBL", cap.get("isbl"), "spec", "base"),
                ("FCI", cap.get("fci_grass_roots"), "accent", "FCI"),
                ("Work. cap.", cap.get("working_capital"), "auto", None),
                ("CAPEX", cap.get("capex_total"), "alert", "año 0")):
            if val is not None:
                grid.add(MetricCard(label=lab, value=_musd(val, 2), unit="M",
                                    state=st, flag=flag))
        v.addWidget(_evidence_card("CAPEX · Grass-Roots (Turton 7.10)",
                                   [(f"CEPCI {m['params'].get('year_target','')}",
                                     "neutral")], grid))
        # waterfall
        fig_w = self._waterfall(m)
        if fig_w is not None:
            v.addWidget(_evidence_card("Cash flow neto por año", [], fig_w))
        # OPEX
        opex = m["opex"]
        og = MetricGrid()
        rev = opex.get("revenue"); comd = opex.get("com_d")
        margin = (rev - comd) if (rev is not None and comd is not None) else None
        for lab, val, st in (("Revenue", rev, "ok"), ("COM_d", comd, "alert"),
                             ("Margen", margin, "accent")):
            if val is not None:
                og.add(MetricCard(label=lab, value=_musd(val, 2), unit="M/a",
                                  state=st))
        v.addWidget(_evidence_card("OPEX · costo de manufactura (Turton 8.2)",
                                   [], og))
        v.addStretch(1)
        return host

    def _waterfall(self, m):
        try:
            from econ_figures import cashflow_figure
            fig, _meta = cashflow_figure(m["cashflow"], m["payback_year"])
            if fig is None:
                return None
            from matplotlib.backends.backend_qtagg import FigureCanvas
            c = FigureCanvas(fig); c.setMinimumHeight(220)
            return c
        except Exception:
            return None

    # ── pane Monte Carlo: botón al panel vivo ─────────────────────────
    def _pane_montecarlo(self, m):
        host = QWidget(); v = QVBoxLayout(host); v.setSpacing(10)
        lbl = QLabel("Distribución de NPV (P10/P50/P90 + cola P(NPV<0)) y "
                     "tornado de sensibilidad. Corré el análisis de incertidumbre:")
        lbl.setWordWrap(True); lbl.setFont(QFont(pfd_fonts.SANS, 9))
        lbl.setStyleSheet(f"color:{_tok('ink_mute')};")
        v.addWidget(lbl)
        btn = QPushButton("Abrir Monte Carlo…")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFont(QFont(pfd_fonts.SANS, 9, QFont.DemiBold))
        btn.setStyleSheet(
            f"QPushButton {{ background:{_tok('accent')}; color:#fff; "
            f"border:0; border-radius:6px; padding:8px 16px; }}"
            f"QPushButton:hover {{ background:{_tok('accent_deep')}; }}")
        if self._on_montecarlo:
            btn.clicked.connect(self._on_montecarlo)
        v.addWidget(btn, alignment=Qt.AlignLeft)
        v.addStretch(1)
        return host

    # ── pane Contabilidad: P&L + cash flow año-por-año ────────────────
    def _pane_contabilidad(self, m):
        host = QWidget(); v = QVBoxLayout(host); v.setSpacing(12)
        v.setContentsMargins(0, 0, 0, 0)
        inc = m.get("income_statement")
        if inc:
            rows = [
                {"cells": ["Ingresos por ventas", "+" + _musd(inc["revenue"])],
                 "pos_neg": True},
                {"cells": ["Costo de manufactura (COM_d)",
                           "-" + _musd(inc["com_d"])], "pos_neg": True},
                {"cells": ["Utilidad bruta (EBT)", _musd(inc["ebt"])],
                 "kind": "sub", "pos_neg": True},
                {"cells": [f"Impuesto ({(inc['tax_rate'] or 0)*100:.0f}%)",
                           "-" + _musd(inc["tax"])], "pos_neg": True},
                {"cells": ["Utilidad neta", _musd(inc["net"])],
                 "kind": "sub", "pos_neg": True},
                {"cells": ["(+) Depreciación (no-caja)",
                           _musd(inc["depreciation"])]},
                {"cells": ["Flujo de caja operativo",
                           _musd(inc["operating_cash_flow"])],
                 "kind": "total", "pos_neg": True},
            ]
            tbl = FinancialTable(headers=["Estado de Resultados (M USD)", "M USD"],
                                 rows=rows)
            v.addWidget(_evidence_card("Estado de Resultados",
                                       [("anual · op. plena", "neutral")], tbl))
        cf = m.get("cashflow") or []
        if cf:
            cf_rows = [{"cells": [f"Año {r['year']} ({r['phase']})",
                                  _musd(r["cf"])], "pos_neg": True} for r in cf]
            tbl2 = FinancialTable(headers=["Año", "M USD"], rows=cf_rows)
            v.addWidget(_evidence_card("Cash flow año-por-año (nominal)", [], tbl2))
        v.addStretch(1)
        return host

    def _restyle(self):
        self.setStyleSheet(f"background:{_tok('bg')};")


__all__ = ["EconRichView"]
