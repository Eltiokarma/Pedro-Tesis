"""econ_richview.py — LA UI del Panel Económico (rediseño 1e/1f).

    ┌─ EconRichView (columna) ───────────────────────────────┐
    │  PanelHeader  [$ ícono] ECONOMÍA · proyecto · CEPCI   ✕ │
    │  HeroStrip    NPV grande | TIR | Payback | ROI (1 vez)  │
    │  ┌ Sidebar ─┬ Stack (7 panes REALES) ─────────────────┐ │
    │  │ Resumen  │ 0 Resumen   4 Monte Carlo (embebido)     │ │
    │  │ CAPEX …  │ 1 CAPEX     5 Contabilidad               │ │
    │  │ ●Viable  │ 2 OPEX      6 Parámetros (formulario)    │ │
    │  └──────────┴ 3 Cash flow ────────────────────────────┘ │
    │  Footer  nota · [Exportar Excel] [Re-correr análisis]   │
    └─────────────────────────────────────────────────────────┘

El sidebar es LA navegación: 7 ítems → 7 panes (la segmented-tab bar
duplicada del diseño anterior murió, junto con su lógica de
sincronización). Los KPIs viven UNA vez en el hero; el footer es solo de
acciones. Acepta m=None (estado vacío pre-cálculo: placeholders y
sidebar arrancando en Parámetros).

Presentación pura: recibe el dict de econ_metrics(econ), no recalcula.
Reusa MetricCard/MetricGrid/StatusBadge (Inspector) + FinancialTable
(econ_widgets) + cashflow_figure (econ_figures, headless-safe). Color
desde tokens.TOK en caliente, suscrito a _PrefsBus; dinero/porcentaje/
años con el formateador único de tokens.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QStackedWidget, QScrollArea, QPushButton, QSizePolicy,
)

import pfd_fonts
from tokens import (_PrefsBus, fmt_pct, fmt_years, qfont, FONT_DISPLAY,
                    FONT_TITLE, FONT_UI, FONT_VALUE, FONT_HINT, FONT_LABEL)
from inspector_widgets import _tok, MetricCard, MetricGrid, StatusBadge
from econ_widgets import FinancialTable


def _musd(x, dec=2):
    """Número en M USD sin unidad (la unidad la pone la celda/label)."""
    if x is None:
        return "—"
    try:
        return f"{float(x)/1e6:,.{dec}f}"
    except (TypeError, ValueError):
        return str(x)


def _empty_metrics():
    """Métricas placeholder para el estado pre-cálculo (m=None)."""
    return {
        "heroes": {"npv": {"value": None},
                   "irr": {"value": None, "hurdle": None},
                   "payback": None, "roi": None},
        "capex": {}, "opex": {}, "params": {},
        "cashflow": [], "payback_year": None,
        "verdict": {"text": "sin calcular", "kind": "neutral"},
    }


def _placeholder(text="Presioná «Calcular» en Parámetros para ver esta vista."):
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setFont(qfont(FONT_UI))
    lbl.setStyleSheet(f"color:{_tok('ink_soft')}; font-style:italic; "
                      f"padding:28px;")
    host = QWidget(); v = QVBoxLayout(host)
    v.addStretch(1); v.addWidget(lbl); v.addStretch(2)
    return host


# ─────────────────────────────────────────────────────────────────────
#  PanelHeader (.ph) — ícono + tag + descripción + close
# ─────────────────────────────────────────────────────────────────────
class _PanelHeader(QFrame):
    closeClicked = Signal()

    def __init__(self, tag="ECONOMÍA", title="Rentabilidad del flowsheet",
                 desc="run_economics=True", parent=None):
        super().__init__(parent)
        self._tag, self._title, self._desc = tag, title, desc
        self.setFixedHeight(64)   # +6px: FONT_TITLE/FONT_HINT crecen vs. 12/8pt
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 12, 10); lay.setSpacing(10)
        # ícono $
        self._ico = QLabel("$")
        self._ico.setFixedSize(36, 36)
        self._ico.setAlignment(Qt.AlignCenter)
        # glifo-ícono: tamaño geométrico, no tipografía (excepción 2g)
        # glifo-ícono ($ en caja 36px): tamaño geométrico, no tipografía
        # (excepción 2g)
        self._ico.setFont(QFont(pfd_fonts.SANS, 13, QFont.Bold))
        lay.addWidget(self._ico)
        # bloque texto
        txt = QVBoxLayout(); txt.setSpacing(1); txt.setContentsMargins(0, 0, 0, 0)
        self._lab_tag = QLabel(tag)
        self._lab_tag.setFont(qfont(FONT_LABEL))
        self._lab_title = QLabel(title)
        self._lab_title.setFont(qfont(FONT_TITLE))
        self._lab_desc = QLabel(desc)
        self._lab_desc.setFont(qfont(FONT_HINT))
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
            # glifo-ícono: tamaño geométrico, no tipografía (excepción 2g)
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
        self._k = QLabel(kicker.upper()); self._k.setFont(qfont(FONT_LABEL))
        self._v = QLabel(value); self._v.setFont(qfont(FONT_VALUE))
        self._s = QLabel(sub); self._s.setFont(qfont(FONT_HINT))
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
        self._npv_k.setFont(qfont(FONT_LABEL))
        row = QHBoxLayout(); row.setSpacing(5); row.setContentsMargins(0, 0, 0, 0)
        neg = (npv or 0) < 0
        self._npv_value = npv
        self._npv_v = QLabel(f"{_musd(npv, 1)}")
        self._npv_v.setFont(qfont(FONT_DISPLAY))
        self._npv_neg = neg
        self._npv_u = QLabel("M USD"); self._npv_u.setFont(qfont(FONT_VALUE))
        row.addWidget(self._npv_v, alignment=Qt.AlignBottom)
        row.addWidget(self._npv_u, alignment=Qt.AlignBottom)
        row.addStretch(1)
        npv_box.addWidget(self._npv_k); npv_box.addLayout(row)
        nw = QWidget(); nw.setLayout(npv_box)
        lay.addWidget(nw, stretch=3)
        # KPIs
        self._kpis = [
            _Kpi("TIR", fmt_pct(irr) if irr is not None else "—",
                 f"hurdle {hurdle:.0f} %" if hurdle else "",
                 ("pos" if (irr or 0) > (hurdle or 0) else "neg")
                 if irr is not None else ""),
            _Kpi("Payback", fmt_years(pb) if pb is not None else "—",
                 "desde arranque"),
            _Kpi("ROI", fmt_pct(roi) if roi is not None else "—",
                 "anual medio"),
        ]
        for k in self._kpis:
            lay.addWidget(k, stretch=2)
        _PrefsBus.signal().connect(self._restyle); self._restyle()

    def _restyle(self):
        self.setStyleSheet(
            f"background:{_tok('bg_mute')}; "
            f"border-bottom:1px solid {_tok('line')};")
        self._npv_k.setStyleSheet(f"color:{_tok('ink_soft')}; letter-spacing:1px;")
        col = ("ink_soft" if self._npv_value is None
               else "danger" if self._npv_neg else "green")
        self._npv_v.setStyleSheet(
            f"color:{_tok(col)}; letter-spacing:-0.5px;")
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
        self.setFixedWidth(168)   # FONT_UI (12pt) necesita +18px vs los 150 de 9pt
        self._verdict = verdict
        self._active = 0
        v = QVBoxLayout(self); v.setContentsMargins(8, 10, 8, 10); v.setSpacing(2)
        self._labels = []
        for i, (name, ico) in enumerate(self.ITEMS):
            item = QPushButton(f"  {ico}   {name}")
            item.setCursor(Qt.PointingHandCursor)
            item.setFont(qfont(FONT_UI))
            item.clicked.connect(lambda _=False, k=i: self._on_item(k))
            self._labels.append(item)
            v.addWidget(item)
        v.addStretch(1)
        # chip veredicto
        self._dof = QLabel(f"●  {verdict.get('text', '—')}")
        self._dof.setFont(qfont(FONT_LABEL))
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
    """Footer SOLO de acciones (1e): los KPIs viven una única vez en el
    hero — acá va la nota de frescura + Exportar Excel + Re-correr."""
    rerun = Signal()
    exportExcel = Signal()

    def __init__(self, empty=False, show_export=False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)   # +4px: botones pasan de 9pt a FONT_UI (12pt)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8); lay.setSpacing(10)
        self._note = QLabel("configurá Parámetros y presioná Calcular"
                            if empty else
                            "actualizado tras el último cálculo")
        self._note.setFont(qfont(FONT_HINT))
        lay.addWidget(self._note)
        lay.addStretch(1)
        self._btn_xls = QPushButton("Exportar Excel")
        self._btn_xls.setCursor(Qt.PointingHandCursor)
        self._btn_xls.setFont(qfont(FONT_UI))
        self._btn_xls.clicked.connect(self.exportExcel.emit)
        self._btn_xls.setVisible(bool(show_export))
        lay.addWidget(self._btn_xls)
        self._btn = QPushButton("Re-correr análisis")
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setFont(qfont(FONT_UI))
        self._btn.clicked.connect(self.rerun.emit)
        lay.addWidget(self._btn)
        _PrefsBus.signal().connect(self._restyle); self._restyle()

    def _restyle(self):
        self.setStyleSheet(
            f"background:{_tok('bg_mute')}; "
            f"border-top:1px solid {_tok('line')};")
        self._note.setStyleSheet(f"color:{_tok('ink_soft')}; "
                                 f"font-style:italic;")
        self._btn_xls.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{_tok('ink_mute')}; "
            f"border:1px solid {_tok('line_strong')}; border-radius:6px; "
            f"padding:6px 12px; }}"
            f"QPushButton:hover {{ background:{_tok('bg_elev')}; "
            f"color:{_tok('ink')}; }}")
        self._btn.setStyleSheet(
            f"QPushButton {{ background:{_tok('accent')}; "
            f"color:{_tok('bg_elev')}; "
            f"border:0; border-radius:6px; padding:7px 14px; }}"
            f"QPushButton:hover {{ background:{_tok('accent_deep')}; }}")


# ─────────────────────────────────────────────────────────────────────
#  Tarjeta de evidencia (.evidence) — header con badges + cuerpo
# ─────────────────────────────────────────────────────────────────────
def _evidence_card(title, badges, body_widget):
    card = QFrame(); card.setObjectName("evCard")
    v = QVBoxLayout(card); v.setContentsMargins(12, 10, 12, 12); v.setSpacing(8)
    head = QHBoxLayout(); head.setSpacing(6); head.setContentsMargins(0, 0, 0, 0)
    t = QLabel(title); t.setFont(qfont(FONT_LABEL))
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
    """La UI del panel económico (1e). Recibe el dict de econ_metrics(econ)
    — o None para el estado vacío pre-cálculo — más los widgets huésped:
    el formulario de parámetros (pane 6) y el pane Monte Carlo embebido
    (pane 4). Señales closeClicked/rerun/exportExcel para el caller."""
    closeClicked = Signal()
    rerun = Signal()
    exportExcel = Signal()

    def __init__(self, m, project="", params_widget=None, mc_widget=None,
                 show_export=False, parent=None):
        super().__init__(parent)
        self._empty = m is None
        m = m if m is not None else _empty_metrics()
        self._m = m
        self._params_widget = params_widget
        self._mc_widget = mc_widget
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # header — proyecto · CEPCI (nada de run_economics=True)
        hdr = _PanelHeader(desc=project or "análisis económico")
        hdr.closeClicked.connect(self.closeClicked.emit)
        root.addWidget(hdr)
        # hero strip — los KPIs, UNA vez
        root.addWidget(_HeroStrip(m))
        # cuerpo: sidebar (LA navegación) + stack de 7 panes reales
        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        self._side = _Sidebar(m["verdict"])
        self._side.itemClicked.connect(self._on_side)
        body.addWidget(self._side)
        self._main = self._build_main(m)
        body.addWidget(self._main, stretch=1)
        bw = QWidget(); bw.setLayout(body)
        root.addWidget(bw, stretch=1)
        # footer — solo acciones
        ft = _Footer(empty=self._empty, show_export=show_export)
        ft.rerun.connect(self.rerun.emit)
        ft.exportExcel.connect(self.exportExcel.emit)
        root.addWidget(ft)
        _PrefsBus.signal().connect(self._restyle); self._restyle()
        # estado inicial: sin métricas todavía → arrancar en Parámetros
        self.set_pane(6 if self._empty else 0)

    # ── navegación: sidebar → pane, 1:1, sin controles duplicados ─────
    def _on_side(self, k):
        self._tabs.setCurrentIndex(k)

    def set_pane(self, k):
        """Activa el pane k (0 Resumen … 6 Parámetros) desde afuera."""
        if 0 <= k < self._tabs.count():
            self._side.set_active(k)
            self._tabs.setCurrentIndex(k)

    def detach_hosted(self):
        """Desengancha los widgets huésped (parámetros y Monte Carlo)
        para poder reconstruir la vista sin destruirlos."""
        for sa in (getattr(self, "_params_scroll", None),
                   getattr(self, "_mc_scroll", None)):
            if sa is not None and sa.widget() is not None:
                w = sa.takeWidget()
                w.setParent(None)

    def _build_main(self, m):
        main = QWidget()
        v = QVBoxLayout(main); v.setContentsMargins(16, 14, 16, 14); v.setSpacing(12)
        self._tabs = QStackedWidget()
        self._tabs.setMinimumHeight(300)
        v.addWidget(self._tabs, stretch=1)
        if self._empty:
            for _ in range(4):                      # 0-3
                self._tabs.addWidget(self._scroll(_placeholder()))
        else:
            self._tabs.addWidget(self._scroll(self._pane_resumen(m)))       # 0
            self._tabs.addWidget(self._scroll(self._pane_capex(m)))         # 1
            self._tabs.addWidget(self._scroll(self._pane_opex(m)))          # 2
            self._tabs.addWidget(self._scroll(self._pane_cashflow(m)))      # 3
        # 4 — Monte Carlo embebido (widget huésped)
        if self._mc_widget is not None:
            self._mc_scroll = self._scroll(self._mc_widget)
            self._tabs.addWidget(self._mc_scroll)
        else:
            self._tabs.addWidget(self._scroll(_placeholder(
                "Monte Carlo no disponible en este contexto.")))
        # 5 — Contabilidad
        self._tabs.addWidget(self._scroll(
            _placeholder() if self._empty else self._pane_contabilidad(m)))
        # 6 — Parámetros (widget huésped)
        if self._params_widget is not None:
            self._params_scroll = self._scroll(self._params_widget)
            self._tabs.addWidget(self._params_scroll)
        else:
            self._tabs.addWidget(self._scroll(_placeholder(
                "Sin formulario de parámetros en este contexto.")))
        return main

    @staticmethod
    def _scroll(widget):
        sa = QScrollArea(); sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.NoFrame)
        sa.setWidget(widget)
        return sa

    # ── pane 0 · Resumen: CAPEX cards + waterfall + OPEX cards ────────
    def _pane_resumen(self, m):
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

    # ── pane 1 · CAPEX: desglose grass-roots + ISBL por categoría ─────
    def _pane_capex(self, m):
        host = QWidget(); v = QVBoxLayout(host); v.setSpacing(12)
        v.setContentsMargins(0, 0, 0, 0)
        cb = m.get("capex_breakdown")
        if cb:
            rows = []
            for lab, key in (("ISBL · ΣCBM", "isbl"),
                             ("(+) Contingencia", "contingency"),
                             ("(+) Servicios aux. (OSBL)", "aux_facilities"),
                             ("FCI · Grass-Roots", "fci_grass_roots"),
                             ("(+) Working capital", "working_capital"),
                             ("CAPEX total (año 0)", "capex_total")):
                val = cb.get(key)
                if val is not None:
                    kind = ("total" if key in ("fci_grass_roots", "capex_total")
                            else "normal")
                    rows.append({"cells": [lab, _musd(val)], "kind": kind})
            if rows:
                v.addWidget(_evidence_card(
                    "CAPEX · Grass-Roots Capital (Turton 7.10)",
                    [("CBM Turton", "info")],
                    FinancialTable(headers=["Concepto", "M USD"], rows=rows)))
        ic = m.get("isbl_by_category")
        if ic and ic.get("rows"):
            rows = []
            for r in ic["rows"]:
                rows.append({"cells": [
                    r["category"], str(r.get("n") or "—"),
                    r.get("material") or "—", _musd(r["cbm"]),
                    f"{r['pct']:.1f}%" if r.get("pct") is not None else "—"]})
            rows.append({"cells": ["ISBL · ΣCBM", str(sum(
                (rr.get("n") or 0) for rr in ic["rows"])), "—",
                _musd(ic["isbl_total"]), "100%"], "kind": "total"})
            v.addWidget(_evidence_card(
                "ISBL · bare module por categoría",
                [("FP·FM auto", "info")],
                FinancialTable(
                    headers=["Categoría", "n", "Material", "CBM", "% ISBL"],
                    rows=rows)))
        if not cb and not (ic and ic.get("rows")):
            v.addWidget(_placeholder("Sin desglose de CAPEX en este cálculo."))
        v.addStretch(1)
        return host

    # ── pane 2 · OPEX: desglose COM_d ─────────────────────────────────
    def _pane_opex(self, m):
        host = QWidget(); v = QVBoxLayout(host); v.setSpacing(12)
        v.setContentsMargins(0, 0, 0, 0)
        ob = m.get("opex_breakdown")
        if ob:
            rows = [{"cells": ["Costos directos de manufactura", ""],
                     "kind": "grp"}]
            for lab, val in ob["directos"]:
                if val is not None:
                    rows.append({"cells": [lab, _musd(val)]})
            rows.append({"cells": ["Costos fijos (FCI-pegged)", ""], "kind": "grp"})
            for lab, val in ob["fijos"]:
                if val is not None:
                    rows.append({"cells": [lab, _musd(val)]})
            rows.append({"cells": ["COM_d (total, Turton 8.2)",
                                   _musd(ob["com_d"])], "kind": "total"})
            card = _evidence_card(
                "OPEX · costo de manufactura (COM_d)",
                [("Turton 8.2", "info")],
                FinancialTable(headers=["Concepto", "M USD"], rows=rows))
            v.addWidget(card)
            n = QLabel(ob["note"]); n.setWordWrap(True)
            n.setFont(qfont(FONT_HINT))
            n.setStyleSheet(f"color:{_tok('ink_mute')}; font-style:italic;")
            v.addWidget(n)
        else:
            v.addWidget(_placeholder("Sin desglose de OPEX en este cálculo."))
        v.addStretch(1)
        return host

    # ── pane 3 · Cash flow: waterfall + tabla año-por-año ─────────────
    def _pane_cashflow(self, m):
        host = QWidget(); v = QVBoxLayout(host); v.setSpacing(12)
        v.setContentsMargins(0, 0, 0, 0)
        fig_w = self._waterfall(m)
        if fig_w is not None:
            v.addWidget(_evidence_card("Cash flow neto por año", [], fig_w))
        cf = m.get("cashflow") or []
        if cf:
            cf_rows = [{"cells": [f"Año {r['year']} ({r['phase']})",
                                  _musd(r["cf"])], "pos_neg": True} for r in cf]
            tbl2 = FinancialTable(headers=["Año", "M USD"], rows=cf_rows)
            v.addWidget(_evidence_card("Cash flow año-por-año (nominal)", [],
                                       tbl2))
        if fig_w is None and not cf:
            v.addWidget(_placeholder("Sin cash flow en este cálculo."))
        v.addStretch(1)
        return host

    # ── pane 5 · Contabilidad: estado de resultados ───────────────────
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
            tbl = FinancialTable(headers=["Concepto", "M USD"], rows=rows)
            v.addWidget(_evidence_card("Estado de Resultados",
                                       [("anual · op. plena", "neutral")], tbl))
        else:
            v.addWidget(_placeholder("Sin estado de resultados en este "
                                     "cálculo."))
        v.addStretch(1)
        return host

    def _restyle(self):
        self.setStyleSheet(f"background:{_tok('bg')};")


__all__ = ["EconRichView"]
