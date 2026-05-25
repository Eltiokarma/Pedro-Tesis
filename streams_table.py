"""
STREAMS TABLE — dock inferior con tabla hi-fi de todas las corrientes.

Reemplaza el QTableWidget plano por filas custom con:
  · NumberPill (n + dot de fase)
  · Tag (mono) + chip de rol + status dot
  · Path src.port → dst.port
  · Chip de fase con dot de color
  · Mass flow + barra de proporción + (auto si no-locked)
  · CompositionStrip (stacked bar top-3 + leyenda chica)
  · T / P stacked
  · Double-click → abre StreamInspector

Toolbar:
  · Drag handle
  · Título + contador
  · Unit selector segmentado (tm/año · kg/h · kg/s · t/d · lb/h)
  · Totales Σ FEED / Σ PRODUCT
  · Buscar (filtro por tag / componente / bloque)
  · Export

Reusa de stream_inspector + block_inspector:
  · TOK, _PrefsBus
  · PHASE_DOT, PHASE_LABEL, role_style
"""

from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QFont, QBrush, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QDockWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QToolButton, QFrame, QScrollArea,
    QSizePolicy, QComboBox, QFileDialog, QMessageBox, QApplication,
)

import pfd_fonts
import flowsheet_units as funits
from block_inspector import TOK, _PrefsBus
from stream_inspector import PHASE_DOT, PHASE_LABEL, role_style


# ════════════════════════════════════════════════════════
#  ÁTOMOS REUSABLES
# ════════════════════════════════════════════════════════

class _NumberPill(QFrame):
    """Círculo 32px con número del stream + dot de fase abajo-derecha."""

    def __init__(self, n: int, phase: str, selected: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self._n = n
        self._phase = phase or ""
        self._selected = selected

    def paintEvent(self, ev):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing, True)
        bg = QColor(TOK["accent"]) if self._selected else QColor(TOK["bg_elev"])
        fg = QColor("white") if self._selected else QColor(TOK["ink"])
        border = QColor(TOK["accent"]) if self._selected else QColor(TOK["line_strong"])
        # círculo principal
        p.setBrush(QBrush(bg)); p.setPen(QPen(border, 1))
        p.drawEllipse(0, 0, 31, 31)
        # número
        p.setPen(QPen(fg))
        p.setFont(QFont(pfd_fonts.MONO, 11, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter, str(self._n) if self._n > 0 else "?")
        # dot de fase abajo-derecha
        if self._phase:
            phase_color = QColor(PHASE_DOT.get(self._phase, TOK["ink_ghost"]))
            border_color = bg
            p.setBrush(QBrush(phase_color))
            p.setPen(QPen(border_color, 2))
            p.drawEllipse(20, 20, 12, 12)


class _PhaseChip(QLabel):
    def __init__(self, phase: str, parent=None):
        super().__init__(parent)
        label = PHASE_LABEL.get(phase, "—")
        color = PHASE_DOT.get(phase, TOK["ink_ghost"])
        self.setText(f"●  {label}")
        self.setFont(QFont(pfd_fonts.SANS, 8, QFont.Bold))
        self.setStyleSheet(
            f"background:{TOK['bg_sunk']}; color:{TOK['ink_mute']}; "
            f"padding:2px 8px; border-radius:4px; letter-spacing:0.5px;"
        )
        # No podemos mezclar dot+text con colores distintos en un QLabel,
        # entonces hacemos rich text:
        self.setText(
            f'<span style="color:{color};">●</span>'
            f'<span style="color:{TOK["ink_mute"]};">  {label}</span>'
        )
        self.setTextFormat(Qt.RichText)


class _RoleChip(QLabel):
    def __init__(self, role: str, parent=None):
        super().__init__(parent)
        bg, fg, label = role_style(role)
        self.setText(label)
        self.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; "
            f"padding:1px 8px; border-radius:9px; letter-spacing:0.6px;"
        )


class _StatusDot(QFrame):
    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(11, 11)
        self._status = status

    def paintEvent(self, ev):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing, True)
        color_map = {
            "ok": TOK["green"], "warning": TOK["amber"], "warn": TOK["amber"],
            "error": TOK["danger"], "stale": TOK["spec"],
        }
        color = QColor(color_map.get(self._status, TOK["ink_soft"]))
        # halo
        halo = QColor(color); halo.setAlphaF(0.15)
        p.setBrush(QBrush(halo)); p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, 10, 10)
        # dot
        p.setBrush(QBrush(color))
        p.drawEllipse(2, 2, 6, 6)


class _MassBar(QFrame):
    """Barra horizontal con fill proporcional. Color según locked."""

    def __init__(self, frac: float, locked: bool, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self._frac = max(0.0, min(1.0, float(frac)))
        self._color = QColor(TOK["spec_ribbon"]) if locked \
                      else QColor(TOK["auto_ribbon"])

    def paintEvent(self, ev):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing, True)
        # bg
        p.setBrush(QBrush(QColor(TOK["bg_sunk"]))); p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 3, 3)
        # fill
        if self._frac > 0:
            w = int(self.width() * self._frac)
            p.setBrush(QBrush(self._color))
            p.drawRoundedRect(0, 0, w, self.height(), 3, 3)


class _CompositionStrip(QFrame):
    """Stacked horizontal bar + leyenda compacta (top-3 componentes)."""

    def __init__(self, comp_items, parent=None):
        """comp_items = [(name, frac), …] ordenado de mayor a menor."""
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(3)
        # paleta de colores
        colors = [TOK["accent"], TOK["orange"], TOK["spec"], TOK["amber"],
                   TOK["danger"], TOK["green"], TOK["ink_soft"]]
        items_colored = []
        for i, (name, frac) in enumerate(comp_items):
            items_colored.append((name, frac, colors[i % len(colors)]))

        # Stacked bar
        bar = _StackedBar(items_colored, self)
        bar.setFixedHeight(8)
        lay.addWidget(bar)

        # Leyenda — top 3, mono
        legend = QHBoxLayout(); legend.setSpacing(8); legend.setContentsMargins(0,0,0,0)
        for name, frac, color in items_colored[:3]:
            chip = QLabel()
            chip.setTextFormat(Qt.RichText)
            chip.setText(
                f'<span style="color:{color};">●</span>'
                f' <span style="color:{TOK["ink_mute"]};font-family:\'{pfd_fonts.MONO}\';font-size:8pt;">{name}</span>'
                f' <span style="color:{TOK["ink_soft"]};font-family:\'{pfd_fonts.MONO}\';font-size:8pt;">{frac*100:.1f}%</span>'
            )
            legend.addWidget(chip)
        legend.addStretch(1)
        lwrap = QFrame(); lwrap.setLayout(legend)
        lay.addWidget(lwrap)


class _StackedBar(QFrame):
    def __init__(self, items_colored, parent=None):
        """items_colored = [(name, frac, color_hex), …]"""
        super().__init__(parent)
        self._items = list(items_colored)
        self.setToolTip(
            "\n".join(f"{name}: {frac*100:.2f}%" for name, frac, _ in items_colored[:8])
        )

    def paintEvent(self, ev):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing, True)
        # bg
        p.setBrush(QBrush(QColor(TOK["bg_sunk"])))
        p.setPen(QPen(QColor(TOK["line"]), 1))
        p.drawRoundedRect(0, 0, self.width()-1, self.height()-1, 3, 3)
        # segments
        x = 1.0
        for name, frac, color in self._items:
            w = (self.width() - 2) * max(0.0, min(1.0, frac))
            if w <= 0: continue
            p.setBrush(QBrush(QColor(color))); p.setPen(Qt.NoPen)
            p.drawRect(int(x), 1, int(w), self.height()-2)
            x += w


# ════════════════════════════════════════════════════════
#  FILA DE STREAM (custom layout)
# ════════════════════════════════════════════════════════

class _StreamRow(QFrame):
    """Una fila de la tabla — custom layout, no QTableWidget."""

    clicked       = Signal(int)   # stream_id
    doubleClicked = Signal(int)   # stream_id

    # Anchos relativos (replicado del jsx grid):
    COL_WEIGHTS = (44, 220, 200, 96, 220, 240, 96)
    # number, tag+role, path, phase, flow, comp, T/P

    def __init__(self, stream, fs, unit: str, max_mass: float,
                 status: str = "ok", selected: bool = False, parent=None):
        super().__init__(parent)
        self._sid = stream.id
        self._selected = selected
        self.setObjectName(f"streamRow_{stream.id}")
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10); lay.setSpacing(14)

        # ── columna 1: number pill ──
        pill = _NumberPill(
            int(getattr(stream, "display_number", 0) or stream.id),
            getattr(stream, "phase", "") or "",
            selected=selected,
        )
        lay.addWidget(pill)

        # ── columna 2: tag + role chip + status dot ──
        col_tag = QVBoxLayout(); col_tag.setSpacing(4); col_tag.setContentsMargins(0,0,0,0)
        tag = QLabel(stream.name or "?")
        tag.setFont(QFont(pfd_fonts.MONO, 10, QFont.DemiBold))
        tag.setStyleSheet(f"color:{TOK['ink']};")
        col_tag.addWidget(tag)
        chip_row = QHBoxLayout(); chip_row.setSpacing(5); chip_row.setContentsMargins(0,0,0,0)
        chip_row.addWidget(_RoleChip(stream.role or "internal"))
        chip_row.addWidget(_StatusDot(status))
        chip_row.addStretch(1)
        cw = QFrame(); cw.setLayout(chip_row); col_tag.addWidget(cw)
        tag_wrap = QFrame(); tag_wrap.setLayout(col_tag)
        tag_wrap.setMinimumWidth(140)
        lay.addWidget(tag_wrap, 2)

        # ── columna 3: path src.port → dst.port ──
        b_src = fs.blocks.get(stream.src) if fs else None
        b_dst = fs.blocks.get(stream.dst) if fs else None
        src_label = (f"{b_src.name}.{stream.src_port or '?'}"
                     if b_src else "(boundary)")
        dst_label = (f"{b_dst.name}.{stream.dst_port or '?'}"
                     if b_dst else "(boundary)")
        path_wrap = QFrame()
        path_lay = QHBoxLayout(path_wrap); path_lay.setContentsMargins(0,0,0,0); path_lay.setSpacing(6)
        from_lbl = QLabel(src_label)
        from_lbl.setFont(QFont(pfd_fonts.MONO, 9))
        from_lbl.setStyleSheet(f"color:{TOK['ink_mute']};")
        from_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        arrow = QLabel("→")
        arrow.setStyleSheet(f"color:{TOK['ink_soft']}; font-size:10pt;")
        to_lbl = QLabel(dst_label)
        to_lbl.setFont(QFont(pfd_fonts.MONO, 9))
        to_lbl.setStyleSheet(f"color:{TOK['ink_mute']};")
        path_lay.addWidget(from_lbl, 1)
        path_lay.addWidget(arrow)
        path_lay.addWidget(to_lbl, 1)
        path_wrap.setMinimumWidth(150)
        lay.addWidget(path_wrap, 2)

        # ── columna 4: phase chip ──
        ph_wrap = QFrame()
        phl = QHBoxLayout(ph_wrap); phl.setContentsMargins(0,0,0,0)
        phl.addWidget(_PhaseChip(getattr(stream, "phase", "") or ""))
        phl.addStretch(1)
        ph_wrap.setMinimumWidth(80)
        lay.addWidget(ph_wrap)

        # ── columna 5: flow + bar ──
        mass = float(stream.mass_flow or 0)
        locked = bool(getattr(stream, "mass_flow_locked", False))
        flow_wrap = QFrame()
        fl = QVBoxLayout(flow_wrap); fl.setContentsMargins(0,0,0,0); fl.setSpacing(4)
        flow_text_row = QHBoxLayout(); flow_text_row.setSpacing(5)
        # convert via flowsheet_units si la unidad cambió
        try:
            mass_disp = funits.format_flow(mass, unit)
            # format_flow returns string like "18 420 tm/año"
            parts = mass_disp.rsplit(" ", 1)
            num_txt, unit_txt = (parts if len(parts) == 2 else (mass_disp, unit))
        except Exception:
            num_txt = f"{mass:,.0f}".replace(",", " ")
            unit_txt = unit
        val = QLabel(num_txt)
        val.setFont(QFont(pfd_fonts.MONO, 11, QFont.Bold))
        val.setStyleSheet(
            f"color:{TOK['ink'] if locked else TOK['ink_soft']};"
        )
        flow_text_row.addWidget(val)
        unit_lbl = QLabel(unit_txt)
        unit_lbl.setFont(QFont(pfd_fonts.SANS, 8))
        unit_lbl.setStyleSheet(f"color:{TOK['ink_soft']};")
        flow_text_row.addWidget(unit_lbl)
        if not locked:
            auto_chip = QLabel("auto")
            auto_chip.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
            auto_chip.setStyleSheet(
                f"color:{TOK['auto_ink']}; font-style:italic;"
            )
            flow_text_row.addWidget(auto_chip)
        flow_text_row.addStretch(1)
        ftw = QFrame(); ftw.setLayout(flow_text_row); fl.addWidget(ftw)
        bar_frac = mass / max(max_mass, 1) if max_mass > 0 else 0
        fl.addWidget(_MassBar(bar_frac, locked))
        flow_wrap.setMinimumWidth(160)
        lay.addWidget(flow_wrap, 2)

        # ── columna 6: composition strip ──
        comp = getattr(stream, "composition", None) or {}
        if not comp:
            mc = getattr(stream, "main_component", "")
            if mc:
                comp = {mc: 1.0}
        comp_items = sorted(comp.items(), key=lambda kv: -kv[1])[:4]
        if comp_items:
            cs = _CompositionStrip(comp_items)
            cs.setMinimumWidth(180)
            lay.addWidget(cs, 2)
        else:
            empty = QLabel("(sin composición)")
            empty.setFont(QFont(pfd_fonts.SANS, 9))
            empty.setStyleSheet(f"color:{TOK['ink_ghost']}; font-style:italic;")
            lay.addWidget(empty, 2)

        # ── columna 7: T / P stacked ──
        tp = QVBoxLayout(); tp.setSpacing(2); tp.setContentsMargins(0,0,0,0)
        tp.setAlignment(Qt.AlignRight)
        T = float(getattr(stream, "temperature", 25.0) or 25.0)
        T_locked = bool(getattr(stream, "temperature_locked", False))
        t_html = (
            f'<span style="color:{TOK["ink"] if T_locked else TOK["ink_soft"]};'
            f' font-family:\'{pfd_fonts.MONO}\'; font-size:10pt; font-weight:600;">'
            f'{T:.1f}</span>'
            f'<span style="color:{TOK["ink_soft"]}; font-size:8pt;"> °C</span>'
        )
        t_lbl = QLabel(); t_lbl.setTextFormat(Qt.RichText); t_lbl.setText(t_html)
        t_lbl.setAlignment(Qt.AlignRight)
        tp.addWidget(t_lbl)
        P = float(getattr(stream, "pressure_bar", 1.013) or 1.013)
        P_locked = bool(getattr(stream, "pressure_locked", False))
        p_html = (
            f'<span style="color:{TOK["ink"] if P_locked else TOK["ink_soft"]};'
            f' font-family:\'{pfd_fonts.MONO}\'; font-size:10pt; font-weight:500;">'
            f'{P:.2f}</span>'
            f'<span style="color:{TOK["ink_soft"]}; font-size:8pt;"> bar</span>'
        )
        p_lbl = QLabel(); p_lbl.setTextFormat(Qt.RichText); p_lbl.setText(p_html)
        p_lbl.setAlignment(Qt.AlignRight)
        tp.addWidget(p_lbl)
        tpw = QFrame(); tpw.setLayout(tp); tpw.setMinimumWidth(80)
        lay.addWidget(tpw)

    def _apply_style(self):
        if self._selected:
            self.setStyleSheet(
                f"#streamRow_{self._sid} {{ background:{TOK['bg_elev']}; "
                f"border-left:3px solid {TOK['accent']}; "
                f"border-bottom:1px solid {TOK['line_soft']}; }}"
            )
        else:
            self.setStyleSheet(
                f"#streamRow_{self._sid} {{ background:transparent; "
                f"border-left:3px solid transparent; "
                f"border-bottom:1px solid {TOK['line_soft']}; }}"
                f"#streamRow_{self._sid}:hover {{ background:{TOK['bg_mute']}; }}"
            )

    def stream_id(self) -> int:
        return self._sid

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self._sid)
        super().mousePressEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.doubleClicked.emit(self._sid)
        super().mouseDoubleClickEvent(ev)


# ════════════════════════════════════════════════════════
#  TOTAL CHIP
# ════════════════════════════════════════════════════════

class _TotalChip(QFrame):
    def __init__(self, label: str, value: float, unit: str, color: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        l = QLabel(label)
        l.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
        l.setStyleSheet(f"color:{TOK['ink_soft']}; letter-spacing:1.1px;")
        lay.addWidget(l)
        # value row
        row = QHBoxLayout(); row.setSpacing(4); row.setContentsMargins(0,0,0,0)
        row.setAlignment(Qt.AlignBaseline)
        dot = QLabel(); dot.setFixedSize(6, 6)
        dot.setStyleSheet(f"background:{color}; border-radius:3px;")
        row.addWidget(dot)
        try:
            txt = funits.format_flow(value, unit) if value > 0 else "—"
        except Exception:
            txt = f"{value:,.0f}".replace(",", " ") + f" {unit}"
        v = QLabel(txt)
        v.setFont(QFont(pfd_fonts.MONO, 10, QFont.Bold))
        v.setStyleSheet(f"color:{TOK['ink']};")
        row.addWidget(v)
        row_wrap = QFrame(); row_wrap.setLayout(row); lay.addWidget(row_wrap)


# ════════════════════════════════════════════════════════
#  HEADER CELL (column titles)
# ════════════════════════════════════════════════════════

def _hdr_cell(text: str, align=Qt.AlignLeft, min_w: int = 0) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
    lbl.setStyleSheet(f"color:{TOK['ink_soft']}; letter-spacing:1.4px;")
    lbl.setAlignment(align)
    if min_w: lbl.setMinimumWidth(min_w)
    return lbl


# ════════════════════════════════════════════════════════
#  STREAMS TABLE DOCK (nuevo)
# ════════════════════════════════════════════════════════

class StreamsTableDock(QDockWidget):
    """Dock inferior con tabla hi-fi de todas las corrientes.

    Toolbar superior + headers + rows en QScrollArea.
    Double-click en una fila abre el StreamInspector.
    """

    def __init__(self, parent, editor):
        super().__init__(" Corrientes ", parent)
        self.editor = editor
        self._search_text = ""
        self._selected_sid: Optional[int] = None

        self.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetMovable
                          | QDockWidget.DockWidgetFloatable
                          | QDockWidget.DockWidgetClosable)

        # subscribir a prefs changes
        try:
            _PrefsBus.signal().connect(self.refresh)
        except Exception:
            pass

        host = QWidget()
        host.setStyleSheet(f"QWidget {{ background:{TOK['bg_elev']}; }}")
        outer = QVBoxLayout(host)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # ── Toolbar ──
        self._toolbar = self._build_toolbar()
        outer.addWidget(self._toolbar)

        # ── Header row (column titles) ──
        self._headers = self._build_headers()
        outer.addWidget(self._headers)

        # ── Rows scrollable ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(f"background:{TOK['bg_elev']};")
        self._rows_host = QWidget()
        self._rows_host.setStyleSheet(f"background:{TOK['bg_elev']};")
        self._rows_lay = QVBoxLayout(self._rows_host)
        self._rows_lay.setContentsMargins(0, 0, 0, 0); self._rows_lay.setSpacing(0)
        self._rows_lay.addStretch(1)
        self._scroll.setWidget(self._rows_host)
        outer.addWidget(self._scroll, 1)

        self.setWidget(host)

    # ── Toolbar ──────────────────────────────────────
    def _build_toolbar(self) -> QFrame:
        tb = QFrame()
        tb.setObjectName("strTblToolbar")
        tb.setStyleSheet(
            f"#strTblToolbar {{ background:{TOK['bg_mute']}; "
            f"border-bottom:1px solid {TOK['line']}; }}"
        )
        lay = QHBoxLayout(tb); lay.setContentsMargins(18, 10, 18, 10); lay.setSpacing(14)

        # ── Title ──
        title = QLabel("Corrientes")
        title.setFont(QFont(pfd_fonts.SANS, 11, QFont.Bold))
        title.setStyleSheet(f"color:{TOK['ink']};")
        lay.addWidget(title)
        self._count_lbl = QLabel("0")
        self._count_lbl.setFont(QFont(pfd_fonts.MONO, 9))
        self._count_lbl.setStyleSheet(f"color:{TOK['ink_soft']};")
        lay.addWidget(self._count_lbl)

        # divider
        d = QFrame(); d.setFixedWidth(1); d.setFixedHeight(20)
        d.setStyleSheet(f"background:{TOK['line']};")
        lay.addWidget(d)

        # ── Unit selector segmentado ──
        self._unit_seg = QFrame()
        self._unit_seg.setStyleSheet(
            f"QFrame {{ background:{TOK['bg_elev']}; "
            f"border:1px solid {TOK['line_strong']}; border-radius:6px; }}"
        )
        seg_lay = QHBoxLayout(self._unit_seg); seg_lay.setContentsMargins(2, 2, 2, 2); seg_lay.setSpacing(1)
        self._unit_buttons = {}
        for u in funits.FLOW_UNITS_ORDER:
            btn = QPushButton(u)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFont(QFont(pfd_fonts.MONO, 8, QFont.DemiBold))
            btn.setStyleSheet(self._unit_btn_style(False))
            btn.clicked.connect(lambda _=False, u=u: self._on_unit_pick(u))
            self._unit_buttons[u] = btn
            seg_lay.addWidget(btn)
        # default
        default_u = "tm/año" if "tm/año" in self._unit_buttons else \
                    list(self._unit_buttons.keys())[0]
        self._current_unit = default_u
        self._unit_buttons[default_u].setChecked(True)
        self._unit_buttons[default_u].setStyleSheet(self._unit_btn_style(True))
        lay.addWidget(self._unit_seg)

        # ── Totales ──
        self._feed_total = _TotalChip("Σ FEED", 0.0, default_u, TOK["green"])
        lay.addWidget(self._feed_total)
        self._prod_total = _TotalChip("Σ PRODUCT", 0.0, default_u, TOK["orange"])
        lay.addWidget(self._prod_total)

        lay.addStretch(1)

        # ── Search ──
        search_wrap = QFrame()
        search_wrap.setStyleSheet(
            f"QFrame {{ background:{TOK['bg_elev']}; "
            f"border:1px solid {TOK['line_strong']}; border-radius:6px; }}"
        )
        sl = QHBoxLayout(search_wrap); sl.setContentsMargins(8, 3, 8, 3); sl.setSpacing(6)
        ic = QLabel("🔍")
        ic.setStyleSheet(f"color:{TOK['ink_soft']};")
        sl.addWidget(ic)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Buscar corriente, componente, bloque…")
        self._search.setStyleSheet(
            "QLineEdit { background:transparent; border:0; outline:0; }"
        )
        self._search.setFont(QFont(pfd_fonts.SANS, 9))
        self._search.textChanged.connect(self._on_search_change)
        self._search.setMinimumWidth(220)
        sl.addWidget(self._search)
        lay.addWidget(search_wrap)

        # ── Export ──
        exp_btn = QPushButton("⇣  Export")
        exp_btn.setCursor(Qt.PointingHandCursor)
        exp_btn.setFont(QFont(pfd_fonts.SANS, 9, QFont.DemiBold))
        exp_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TOK['ink_mute']}; "
            f"border:1px solid {TOK['line']}; border-radius:6px; "
            f"padding:5px 12px; }} "
            f"QPushButton:hover {{ background:{TOK['bg_elev']}; "
            f"color:{TOK['ink']}; }}"
        )
        exp_btn.clicked.connect(self._on_export)
        lay.addWidget(exp_btn)
        return tb

    def _unit_btn_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background:{TOK['accent']}; color:white; "
                f"border:0; border-radius:4px; padding:3px 10px; }}"
            )
        return (
            f"QPushButton {{ background:transparent; color:{TOK['ink_mute']}; "
            f"border:0; border-radius:4px; padding:3px 10px; }} "
            f"QPushButton:hover {{ background:{TOK['bg_mute']}; color:{TOK['ink']}; }}"
        )

    def _on_unit_pick(self, unit: str):
        if unit == self._current_unit:
            self._unit_buttons[unit].setChecked(True)
            return
        # toggle off prev
        if self._current_unit in self._unit_buttons:
            self._unit_buttons[self._current_unit].setChecked(False)
            self._unit_buttons[self._current_unit].setStyleSheet(self._unit_btn_style(False))
        self._current_unit = unit
        self._unit_buttons[unit].setChecked(True)
        self._unit_buttons[unit].setStyleSheet(self._unit_btn_style(True))
        funits.set_quantity("flow", unit)   # sincronizar con el sistema global
        # refresh tabla + labels del canvas
        self.refresh()
        if hasattr(self.editor, "scene") and hasattr(self.editor.scene, "stream_items"):
            for sid, item in self.editor.scene.stream_items.items():
                if hasattr(item, "update_path"):
                    item.update_path()

    def select_flow_unit(self, unit: str):
        """Setea la unidad de flujo del segmented control SIN re-disparar el
        refresh del canvas (lo usa el cambio de sistema global de unidades)."""
        if unit not in self._unit_buttons or unit == self._current_unit:
            if unit in self._unit_buttons:
                # asegurar highlight consistente
                for u, btn in self._unit_buttons.items():
                    on = (u == unit)
                    btn.setChecked(on)
                    btn.setStyleSheet(self._unit_btn_style(on))
            return
        for u, btn in self._unit_buttons.items():
            on = (u == unit)
            btn.setChecked(on)
            btn.setStyleSheet(self._unit_btn_style(on))
        self._current_unit = unit
        self.refresh()

    def _on_search_change(self, txt: str):
        self._search_text = (txt or "").lower().strip()
        self.refresh()

    def _on_export(self):
        # CSV export del estado actual
        fs = getattr(self.editor, "fs", None)
        if not fs or not fs.streams:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar corrientes a CSV", "streams.csv",
            "CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("name,role,src,src_port,dst,dst_port,mass_flow_tm_yr,"
                         "mass_flow_locked,T_C,T_locked,P_bar,P_locked,phase,"
                         "composition,cp,price\n")
                for s in fs.streams.values():
                    b_src = fs.blocks.get(s.src)
                    b_dst = fs.blocks.get(s.dst)
                    comp = ";".join(f"{k}:{v:.4f}"
                                     for k, v in (s.composition or {}).items())
                    f.write(",".join(str(x) for x in [
                        s.name, s.role,
                        b_src.name if b_src else "?", s.src_port,
                        b_dst.name if b_dst else "?", s.dst_port,
                        s.mass_flow,
                        int(getattr(s, "mass_flow_locked", False)),
                        s.temperature,
                        int(getattr(s, "temperature_locked", False)),
                        getattr(s, "pressure_bar", 0),
                        int(getattr(s, "pressure_locked", False)),
                        s.phase or "",
                        f'"{comp}"',
                        s.cp,
                        getattr(s, "price_usd_per_tm", 0),
                    ]) + "\n")
        except Exception as e:
            QMessageBox.critical(self, "Error exportando",
                f"{type(e).__name__}: {e}")
            return
        QMessageBox.information(self, "Exportado",
            f"{len(fs.streams)} corrientes guardadas en:\n{path}")

    # ── Header row ──────────────────────────────────
    def _build_headers(self) -> QFrame:
        hd = QFrame()
        hd.setStyleSheet(
            f"QFrame {{ background:{TOK['bg']}; "
            f"border-bottom:1px solid {TOK['line']}; }}"
        )
        lay = QHBoxLayout(hd); lay.setContentsMargins(16, 8, 16, 7); lay.setSpacing(14)
        # 7 columnas — pesos similares a las rows
        lay.addWidget(_hdr_cell("#", min_w=44))
        lay.addWidget(_hdr_cell("TAG · ROL", min_w=140), 2)
        lay.addWidget(_hdr_cell("DESDE → HACIA", min_w=150), 2)
        lay.addWidget(_hdr_cell("FASE", min_w=80))
        lay.addWidget(_hdr_cell("FLUJO", min_w=160), 2)
        lay.addWidget(_hdr_cell("COMPOSICIÓN (mass frac)", min_w=180), 2)
        lay.addWidget(_hdr_cell("T · P", align=Qt.AlignRight, min_w=80))
        return hd

    # ── API pública (compat con código existente) ─────
    def current_unit(self) -> str:
        return self._current_unit

    def refresh(self):
        """Reconstruye la lista de filas desde el flowsheet actual."""
        fs = getattr(self.editor, "fs", None)
        if fs is None:
            return
        # clear existing rows
        while self._rows_lay.count() > 1:
            it = self._rows_lay.takeAt(0)
            w = it.widget()
            if w: w.setParent(None); w.deleteLater()

        streams = sorted(fs.streams.values(),
                          key=lambda s: (int(getattr(s, "display_number", 0) or 0),
                                          s.name))
        # search filter
        if self._search_text:
            q = self._search_text
            def matches(s):
                if q in (s.name or "").lower(): return True
                if q in (s.role or "").lower(): return True
                # blocks
                b_src = fs.blocks.get(s.src)
                b_dst = fs.blocks.get(s.dst)
                if b_src and q in b_src.name.lower(): return True
                if b_dst and q in b_dst.name.lower(): return True
                # composition
                for k in (s.composition or {}):
                    if q in k.lower(): return True
                return False
            streams = [s for s in streams if matches(s)]

        self._count_lbl.setText(str(len(streams)))

        # totals — actualizar los chips (rebuild para mantenerlos simples)
        feed_total = sum(s.mass_flow for s in streams if s.role == "feed")
        prod_total = sum(s.mass_flow for s in streams if s.role == "product")
        tb_lay = self._toolbar.layout()
        # Snapshot de items antes de modificar (no iterar durante mutación)
        to_remove = []
        spacer_idx = -1
        for i in range(tb_lay.count()):
            it = tb_lay.itemAt(i)
            if it is None: continue
            w = it.widget()
            if w is self._feed_total or w is self._prod_total:
                to_remove.append(w)
            elif it.spacerItem() is not None and spacer_idx < 0:
                spacer_idx = i
        # Remove old chips
        for w in to_remove:
            tb_lay.removeWidget(w); w.setParent(None); w.deleteLater()
        # Build new chips
        self._feed_total = _TotalChip("Σ FEED", feed_total,
                                       self._current_unit, TOK["green"])
        self._prod_total = _TotalChip("Σ PRODUCT", prod_total,
                                       self._current_unit, TOK["orange"])
        # Re-locate spacer post-removal y insertar chips antes
        spacer_idx = -1
        for i in range(tb_lay.count()):
            it = tb_lay.itemAt(i)
            if it is not None and it.spacerItem() is not None:
                spacer_idx = i
                break
        if spacer_idx >= 0:
            tb_lay.insertWidget(spacer_idx, self._prod_total)
            tb_lay.insertWidget(spacer_idx, self._feed_total)

        # max mass para barra
        max_mass = max((s.mass_flow for s in streams), default=0.0)
        # añadir rows
        for s in streams:
            # status puede venir de algún campo o quedar "ok" por default
            status = getattr(s, "_status", None) or "ok"
            row = _StreamRow(
                s, fs, self._current_unit, max_mass,
                status=status, selected=(s.id == self._selected_sid),
            )
            row.clicked.connect(self._on_row_click)
            row.doubleClicked.connect(self._on_row_double_click)
            self._rows_lay.insertWidget(self._rows_lay.count()-1, row)

    def _on_row_click(self, sid: int):
        self._selected_sid = sid
        # Highlight visual: solo refrescar las filas
        self.refresh()
        # también seleccionar el stream en la scene
        item = getattr(self.editor.scene, "stream_items", {}).get(sid)
        if item is not None:
            try:
                self.editor.scene.clearSelection()
                item.setSelected(True)
            except Exception:
                pass

    def _on_row_double_click(self, sid: int):
        stream = self.editor.fs.streams.get(sid)
        if stream is not None and hasattr(self.editor, "edit_stream"):
            self.editor.edit_stream(stream)
