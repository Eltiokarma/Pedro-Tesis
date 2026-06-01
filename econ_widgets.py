"""econ_widgets.py — Átomos NUEVOS del Panel Económico (Fase 2).

Solo los componentes que el handoff marca como nuevos de economía; los del
Inspector (MetricCard/MetricGrid/StatusBadge/GaugePill/DeltaBar) se IMPORTAN de
inspector_widgets, no se duplican.

  · NpvHero      — NPV grande con signo, ribbon 4px verde/danger, valor mono ~40px.
  · EconTabs     — segmented Resultados|Monte Carlo|Contabilidad (QPushButton
                   checkable en QButtonGroup), emite changed(index).
  · ConfigPanel  — QGroupBox colapsable: resumen .rchip (colapsado) / formulario
                   (.inp/.seg, segmented depreciación) abierto.
  · FinancialTable — QTableView mono right-aligned, filas sub/total/grp, pos/neg
                   verde/rojo, pie con indicadores del motor.

Patrón del repo: color desde TOK leído EN CALIENTE, suscripción a _PrefsBus.
Headless-safe (Qt puro). Default del panel: light·oliva·cozy.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import (QColor, QFont, QBrush, QPainter, QPen, QPainterPath,
                           QStandardItemModel, QStandardItem)
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QButtonGroup, QGroupBox, QSizePolicy, QTableView, QHeaderView, QComboBox,
    QLineEdit, QFormLayout, QAbstractItemView,
)

import pfd_fonts
import block_inspector as _bi
from block_inspector import _PrefsBus
from inspector_widgets import _tok   # lector de TOK en caliente (compartido)


def _fmt_musd(x):
    """USD → 'M USD' compacto; '—' si None."""
    if x is None:
        return "—"
    try:
        return f"{float(x) / 1e6:+,.2f}"
    except (TypeError, ValueError):
        return str(x)


# ─────────────────────────────────────────────────────────────────────
#  NpvHero
# ─────────────────────────────────────────────────────────────────────
class NpvHero(QFrame):
    """El número grande de NPV con signo y color. Ribbon de 4px (green si
    NPV>=0, danger si <0), valor mono ~40px, kicker arriba, sub abajo."""

    def __init__(self, value=0.0, unit="M USD", kicker="VALOR PRESENTE NETO",
                 sub=None, parent=None):
        super().__init__(parent)
        self._value = value          # USD (se muestra en M)
        self._unit = unit
        self._kicker = kicker
        self._sub = sub
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        _PrefsBus.signal().connect(self.update)

    def set_value(self, v):
        self._value = v
        self.update()

    def _neg(self):
        try:
            return float(self._value) < 0
        except (TypeError, ValueError):
            return False

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(260, 100)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        if w < 8 or h < 8:
            return
        ink_tok = "danger" if self._neg() else "green"
        r = 10.0
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)
        p.fillPath(path, QBrush(QColor(_tok("bg_elev"))))
        p.setPen(QPen(QColor(_tok("line")), 1))
        p.drawPath(path)
        # ribbon 4px
        p.save(); p.setClipPath(path)
        p.fillRect(QRectF(0, 0, 4, h), QBrush(QColor(_tok(ink_tok))))
        p.restore()
        pad_l = 16
        text_w = max(0, w - pad_l - 10)
        # kicker
        p.setPen(QColor(_tok("ink_soft")))
        fk = QFont(pfd_fonts.SANS, 8, QFont.Bold)
        fk.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        p.setFont(fk)
        p.drawText(QRectF(pad_l, 10, text_w, 14),
                   Qt.AlignLeft | Qt.AlignVCenter, self._kicker.upper())
        # valor grande (M USD) + unidad
        val_txt = _fmt_musd(self._value)
        p.setPen(QColor(_tok(ink_tok)))
        fv = QFont(pfd_fonts.MONO, 30, QFont.DemiBold)
        p.setFont(fv)
        fm = p.fontMetrics()
        vw = fm.horizontalAdvance(val_txt)
        p.drawText(QRectF(pad_l, 26, text_w, 46),
                   Qt.AlignLeft | Qt.AlignVCenter, val_txt)
        p.setPen(QColor(_tok("ink_soft")))
        p.setFont(QFont(pfd_fonts.MONO, 12))
        p.drawText(QRectF(pad_l + vw + 8, 26, max(0, text_w - vw - 8), 46),
                   Qt.AlignLeft | Qt.AlignVCenter, self._unit)
        # sub
        if self._sub:
            p.setPen(QColor(_tok("ink_mute")))
            p.setFont(QFont(pfd_fonts.SANS, 8))
            p.drawText(QRectF(pad_l, h - 20, text_w, 16),
                       Qt.AlignLeft | Qt.AlignVCenter, str(self._sub))


# ─────────────────────────────────────────────────────────────────────
#  EconTabs — segmented (Resultados | Monte Carlo | Contabilidad)
# ─────────────────────────────────────────────────────────────────────
class EconTabs(QWidget):
    """Segmented control: un botón activo a la vez. Emite changed(index)."""
    changed = Signal(int)

    def __init__(self, labels=("Resultados", "Monte Carlo", "Contabilidad"),
                 parent=None):
        super().__init__(parent)
        self._labels = list(labels)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: List[QPushButton] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        for i, lab in enumerate(self._labels):
            b = QPushButton(lab)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFont(QFont(pfd_fonts.SANS, 9, QFont.DemiBold))
            self._group.addButton(b, i)
            self._buttons.append(b)
            lay.addWidget(b)
        lay.addStretch(1)
        if self._buttons:
            self._buttons[0].setChecked(True)
        self._group.idClicked.connect(self._on_click)
        _PrefsBus.signal().connect(self._restyle)
        self._restyle()

    def _on_click(self, idx):
        self._restyle()
        self.changed.emit(idx)

    def current_index(self):
        return self._group.checkedId()

    def _restyle(self):
        on_bg = _tok("bg_elev"); on_ink = _tok("ink")
        off_ink = _tok("ink_soft"); line = _tok("line")
        for b in self._buttons:
            checked = b.isChecked()
            b.setStyleSheet(
                f"QPushButton {{ border:1px solid "
                f"{line if checked else 'transparent'}; "
                f"border-radius:7px; padding:5px 12px; "
                f"background:{on_bg if checked else 'transparent'}; "
                f"color:{on_ink if checked else off_ink}; }}"
                f"QPushButton:hover {{ color:{on_ink}; }}")


# ─────────────────────────────────────────────────────────────────────
#  ConfigPanel — colapsable (resumen rchip / formulario)
# ─────────────────────────────────────────────────────────────────────
class ConfigPanel(QGroupBox):
    """QGroupBox colapsable. Colapsado: chips resumen read-only. Abierto:
    formulario (QLineEdit mono + segmented depreciación). Emite paramsChanged
    cuando el usuario toca un campo (la re-corrida la maneja el caller)."""
    paramsChanged = Signal()

    def __init__(self, params: dict, parent=None):
        super().__init__("", parent)
        self.setFlat(True)
        self._params = dict(params or {})
        self._open = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # header (chevron + título + "Editar")
        head = QPushButton()
        head.setCursor(Qt.PointingHandCursor)
        head.setFont(QFont(pfd_fonts.SANS, 9, QFont.DemiBold))
        head.clicked.connect(self.toggle)
        self._head = head
        root.addWidget(head)

        # resumen (colapsado)
        self._summary = QWidget()
        sl = QHBoxLayout(self._summary)
        sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(6)
        self._rchips: List[QLabel] = []
        for label, val in self._summary_items():
            chip = QLabel(f"{label}: {val}")
            chip.setFont(QFont(pfd_fonts.MONO, 8))
            self._rchips.append(chip)
            sl.addWidget(chip)
        sl.addStretch(1)
        root.addWidget(self._summary)

        # formulario (abierto)
        self._form = QWidget()
        fl = QFormLayout(self._form)
        fl.setContentsMargins(0, 4, 0, 0)
        self.in_life = QLineEdit(str(self._params.get("project_life", "")))
        self.in_tax = QLineEdit(str(self._params.get("tax_rate", "")))
        self.in_disc = QLineEdit(str(self._params.get("discount_rate", "")))
        for w in (self.in_life, self.in_tax, self.in_disc):
            w.setFont(QFont(pfd_fonts.MONO, 9))
            w.editingFinished.connect(self.paramsChanged.emit)
        fl.addRow("Vida (años):", self.in_life)
        fl.addRow("Tax rate:", self.in_tax)
        fl.addRow("Discount:", self.in_disc)
        # segmented depreciación
        self._dep = EconTabs(("Lineal", "MACRS 5", "MACRS 7", "MACRS 15"))
        self._dep.changed.connect(lambda _i: self.paramsChanged.emit())
        fl.addRow("Depreciación:", self._dep)
        self._form.setVisible(False)
        root.addWidget(self._form)

        _PrefsBus.signal().connect(self._restyle)
        self._restyle()

    def _summary_items(self):
        p = self._params
        return [
            ("Vida", f"{p.get('project_life', '—')}a"),
            ("Tax", f"{p.get('tax_rate', '—')}"),
            ("Disc", f"{p.get('discount_rate', '—')}"),
            ("Dep", f"{p.get('dep_method', '—')}"),
        ]

    def toggle(self):
        self._open = not self._open
        self._form.setVisible(self._open)
        self._summary.setVisible(not self._open)
        self._restyle()

    def is_open(self):
        return self._open

    def _restyle(self):
        chev = "▾" if self._open else "▸"
        self._head.setText(f"{chev}  Parámetros  ·  "
                           f"{'Editar' if not self._open else 'Cerrar'}")
        self._head.setStyleSheet(
            f"QPushButton {{ text-align:left; border:none; "
            f"background:transparent; color:{_tok('ink')}; padding:4px 0; }}")
        for chip in self._rchips:
            chip.setStyleSheet(
                f"background:{_tok('bg_sunk')}; color:{_tok('ink_mute')}; "
                f"padding:2px 8px; border-radius:5px;")


# ─────────────────────────────────────────────────────────────────────
#  FinancialTable — QTableView mono right-aligned
# ─────────────────────────────────────────────────────────────────────
class FinancialTable(QTableView):
    """Tabla financiera. rows = [{cells:[...], kind:'normal'|'sub'|'total'|
    'grp', pos_neg:bool}]. Números mono right-aligned; total en negrita con
    borde; pos verde / neg rojo si pos_neg. headers opcional, foot opcional."""

    def __init__(self, headers=None, rows=None, foot=None, parent=None):
        super().__init__(parent)
        self._headers = list(headers or [])
        self._rows = list(rows or [])
        self._foot = foot
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self._build()
        _PrefsBus.signal().connect(self._restyle)

    def _build(self):
        ncol = len(self._headers) or (len(self._rows[0]["cells"])
                                      if self._rows else 1)
        model = QStandardItemModel(len(self._rows), ncol, self)
        if self._headers:
            model.setHorizontalHeaderLabels(self._headers)
        mono = QFont(pfd_fonts.MONO, 9)
        mono_b = QFont(pfd_fonts.MONO, 9, QFont.DemiBold)
        for r, row in enumerate(self._rows):
            kind = row.get("kind", "normal")
            for c, cell in enumerate(row["cells"]):
                it = QStandardItem(str(cell))
                # col 0 = label (left/sans), resto numérico (right/mono)
                if c == 0:
                    it.setFont(QFont(pfd_fonts.SANS, 9,
                                     QFont.DemiBold if kind in ("total", "grp")
                                     else QFont.Normal))
                    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                else:
                    it.setFont(mono_b if kind == "total" else mono)
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    # color pos/neg si la fila lo pide
                    if row.get("pos_neg"):
                        txt = str(cell).replace(",", "").replace(" ", "")
                        try:
                            neg = float(txt) < 0
                            it.setForeground(QColor(
                                _tok("danger" if neg else "green")))
                        except ValueError:
                            pass
                model.setItem(r, c, it)
        self.setModel(model)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, ncol):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._restyle()

    def _restyle(self):
        self.setStyleSheet(
            f"QTableView {{ background:{_tok('bg_elev')}; "
            f"color:{_tok('ink')}; border:1px solid {_tok('line')}; "
            f"border-radius:8px; gridline-color:{_tok('line_soft')}; }}"
            f"QHeaderView::section {{ background:{_tok('bg_mute')}; "
            f"color:{_tok('ink_soft')}; border:none; "
            f"border-bottom:1px solid {_tok('line')}; padding:4px 8px; }}")


__all__ = ["NpvHero", "EconTabs", "ConfigPanel", "FinancialTable"]
