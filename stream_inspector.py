"""
STREAM INSPECTOR — rediseño del StreamEditDialog viejo.

Slide-out panel con el mismo lenguaje visual que BlockInspectorPanel:
header + path strip (origen → número + flecha → destino) + sidebar
con 5 secciones contextual + footer con stats live.

Las 5 secciones:
  · Identidad     — tag, rol, N° corriente, src/dst, precio
  · Termodinámica — T, T objetivo, P, fase, Cp, ΔHvap
  · Composición   — tabla multi-componente con barras de proporción + Σ
  · Hidráulica    — toggle is_pipe + L, D, ε, K local (Darcy-Weisbach)
  · Geometría     — auto / horizontal / vertical (alinear endpoints)

Mapeo Sudoku-locks → SpecField state:
  stream.mass_flow_locked   → mass_flow spec/auto
  stream.temperature_locked → T spec/auto
  stream.pressure_locked    → P spec/auto
  stream.composition_locked → composición spec/auto

Reusa TOK + SpecField + _PrefsBus de block_inspector para que el tema
(claro/oscuro), densidad y acento se respeten globalmente.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget, QDockWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QToolButton, QFrame, QScrollArea,
    QSizePolicy, QComboBox, QCheckBox, QButtonGroup, QMessageBox,
    QApplication,
)

import pfd_fonts
from block_inspector import (
    TOK, ROW_PAD, SECT_GAP, PANEL_W,
    SpecField, _PrefsBus,
)


# ════════════════════════════════════════════════════════
#  CONSTANTES VISUALES — phases + roles (replica del jsx)
# ════════════════════════════════════════════════════════

PHASE_DOT = {
    "liquid":    "#3548b4",   # azul cobalto
    "vapor":     "#c26329",   # naranja
    "gas":       "#b8841a",   # ámbar
    "two_phase": "#0d6e78",   # teal
    "":          "#bab2a3",   # ghost
}
PHASE_LABEL = {
    "liquid": "LIQ", "vapor": "VAP", "gas": "GAS",
    "two_phase": "2-φ", "": "—",
}

ROLES = ["internal", "feed", "product", "utility", "waste"]

def role_style(role: str) -> Tuple[str, str, str]:
    """Devuelve (bg, fg, label) para un rol dado."""
    if role == "feed":    return (TOK["green_bg"],  TOK["green"],  "FEED")
    if role == "product": return (TOK["orange_bg"], TOK["orange"], "PRODUCT")
    if role == "utility": return (TOK["amber_bg"],  TOK["amber"],  "UTILITY")
    if role == "waste":   return (TOK["danger_bg"], TOK["danger"], "WASTE")
    return (TOK["bg_sunk"], TOK["ink_mute"], "INTERNAL")


# ════════════════════════════════════════════════════════
#  HEADER — ícono S{n} + tag + chip + path
# ════════════════════════════════════════════════════════

class _StreamHeader(QFrame):
    closeRequested = Signal()
    tagChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("strHeader")
        self.setFixedHeight(64)
        self.setStyleSheet(
            f"#strHeader {{ background:{TOK['bg_elev']}; "
            f"border-bottom:1px solid {TOK['line']}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 12, 12); lay.setSpacing(10)

        # ícono S{n}
        self._icon = QLabel(self)
        self._icon.setFixedSize(36, 36)
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet(
            f"background:{TOK['accent_tint']}; color:{TOK['accent']}; "
            f"border-radius:9px; border:1px solid {TOK['accent_soft']};"
        )
        self._icon.setFont(QFont(pfd_fonts.MONO, 11, QFont.Bold))
        lay.addWidget(self._icon)

        # title col
        col = QVBoxLayout(); col.setContentsMargins(0,0,0,0); col.setSpacing(2)
        self._tag = QLineEdit(self)
        self._tag.setFrame(False)
        tf = QFont(pfd_fonts.MONO, 14)
        tf.setWeight(QFont.Medium)
        self._tag.setFont(tf)
        self._tag.setStyleSheet(
            f"QLineEdit {{ background:transparent; color:{TOK['ink']}; "
            f"padding:1px 4px; border-radius:4px; }} "
            f"QLineEdit:hover {{ background:{TOK['bg_mute']}; }} "
            f"QLineEdit:focus {{ background:{TOK['bg_mute']}; "
            f"border:1px solid {TOK['accent']}; }}"
        )
        self._tag.editingFinished.connect(
            lambda: self.tagChanged.emit(self._tag.text().strip())
        )
        col.addWidget(self._tag)

        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(4, 0, 0, 0); sub_row.setSpacing(6)
        self._chip = QLabel("STREAM")
        cf = QFont(pfd_fonts.SANS, 8); cf.setBold(True)
        self._chip.setFont(cf)
        self._chip.setStyleSheet(
            f"background:{TOK['tag_bg']}; color:{TOK['tag_ink']}; "
            f"padding:1px 7px; border-radius:4px; letter-spacing:1px;"
        )
        sub_row.addWidget(self._chip)
        dot = QLabel("·"); dot.setStyleSheet(f"color:{TOK['ink_soft']};")
        sub_row.addWidget(dot)
        self._desc = QLabel(self)
        self._desc.setFont(QFont(pfd_fonts.SANS, 9))
        self._desc.setStyleSheet(f"color:{TOK['ink_mute']};")
        sub_row.addWidget(self._desc, 1)
        col.addLayout(sub_row)
        lay.addLayout(col, 1)

        self._close = QToolButton(self)
        self._close.setText("✕")
        self._close.setFixedSize(28, 28)
        self._close.setStyleSheet(
            f"QToolButton {{ background:transparent; color:{TOK['ink_mute']}; "
            f"border:0; border-radius:6px; font-size:14px; }} "
            f"QToolButton:hover {{ background:{TOK['danger_bg']}; "
            f"color:{TOK['danger']}; }}"
        )
        self._close.clicked.connect(self.closeRequested.emit)
        lay.addWidget(self._close)

    def set_stream(self, n: int, name: str, src_desc: str, dst_desc: str):
        self._icon.setText(f"S{n}" if n > 0 else "S")
        self._tag.setText(name or "")
        if src_desc and dst_desc:
            self._desc.setText(f"{src_desc} → {dst_desc}")
        elif src_desc:
            self._desc.setText(f"{src_desc} → ?")
        elif dst_desc:
            self._desc.setText(f"? → {dst_desc}")
        else:
            self._desc.setText("(sin conectar)")

    def tag(self) -> str:
        return self._tag.text().strip()


# ════════════════════════════════════════════════════════
#  PATH STRIP — origen + número con fase + flecha + destino
# ════════════════════════════════════════════════════════

class _PathStrip(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("strPath")
        self.setStyleSheet(
            f"#strPath {{ background:{TOK['bg_mute']}; "
            f"border-bottom:1px solid {TOK['line']}; }}"
        )
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(18, 12, 18, 12); self._lay.setSpacing(14)

    def populate(self, src_tag: str, src_eq: str,
                 dst_tag: str, dst_eq: str,
                 number: int, mass_flow: float, phase: str):
        # limpiar
        while self._lay.count():
            it = self._lay.takeAt(0)
            w = it.widget()
            if w: w.setParent(None); w.deleteLater()
            else:
                lay = it.layout()
                if lay:
                    while lay.count():
                        ww = lay.takeAt(0).widget()
                        if ww: ww.deleteLater()

        # ── columna izquierda (origen) ──
        col_src = self._make_col("ORIGEN · src", src_tag or "(sin)",
                                  src_eq or "boundary", "src")
        self._lay.addLayout(col_src, 1)

        # ── centro: número + flujo + flecha ──
        mid = QVBoxLayout(); mid.setSpacing(4); mid.setAlignment(Qt.AlignCenter)
        bubble = QLabel(str(number) if number > 0 else "?")
        bubble.setFixedSize(52, 52); bubble.setAlignment(Qt.AlignCenter)
        bubble.setFont(QFont(pfd_fonts.MONO, 16, QFont.Bold))
        bubble.setStyleSheet(
            f"background:{TOK['accent']}; color:white; "
            f"border-radius:26px;"
        )
        mid.addWidget(bubble, alignment=Qt.AlignCenter)
        # mass flow text
        mf_txt = f"{mass_flow:,.0f}".replace(",", " ")
        mf = QLabel(f"{mf_txt}  tm/yr")
        mf.setFont(QFont(pfd_fonts.MONO, 9))
        mf.setStyleSheet(f"color:{TOK['ink_mute']};")
        mf.setAlignment(Qt.AlignCenter)
        mid.addWidget(mf)
        # dashed arrow
        arr = _DashArrow(self, color=QColor(TOK["accent"]))
        arr.setFixedSize(92, 14)
        mid.addWidget(arr, alignment=Qt.AlignCenter)
        # phase chip below number
        phase_short = PHASE_LABEL.get(phase, "—")
        phase_color = PHASE_DOT.get(phase, TOK["ink_ghost"])
        ph = QLabel(phase_short)
        ph.setFont(QFont(pfd_fonts.SANS, 8, QFont.Bold))
        ph.setAlignment(Qt.AlignCenter)
        ph.setStyleSheet(
            f"background:{phase_color}; color:white; "
            f"padding:1px 6px; border-radius:8px; letter-spacing:1px;"
        )
        mid.addWidget(ph, alignment=Qt.AlignCenter)
        self._lay.addLayout(mid)

        # ── columna derecha (destino) ──
        col_dst = self._make_col("DESTINO · dst", dst_tag or "(sin)",
                                  dst_eq or "boundary", "dst", align_right=True)
        self._lay.addLayout(col_dst, 1)

    def _make_col(self, header_text, tag, eq, direction, align_right=False):
        col = QVBoxLayout(); col.setSpacing(5)
        hd = QLabel(header_text)
        hd.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
        hd.setStyleSheet(
            f"color:{TOK['ink_soft']}; letter-spacing:1.5px;"
        )
        hd.setAlignment(Qt.AlignRight if align_right else Qt.AlignLeft)
        col.addWidget(hd)
        # block pill
        pill = QFrame()
        pill.setStyleSheet(
            f"QFrame {{ background:{TOK['bg_elev']}; "
            f"border:1px solid {TOK['line']}; border-radius:8px; }}"
        )
        pl = QHBoxLayout(pill); pl.setContentsMargins(10, 6, 10, 6); pl.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dcolor = TOK["accent"] if direction == "src" else TOK["orange"]
        dot.setStyleSheet(f"background:{dcolor}; border-radius:4px;")
        pl.addWidget(dot)
        ic = QVBoxLayout(); ic.setSpacing(2); ic.setContentsMargins(0,0,0,0)
        tg = QLabel(tag)
        tg.setFont(QFont(pfd_fonts.MONO, 10, QFont.Bold))
        tg.setStyleSheet(f"color:{TOK['ink']};")
        ic.addWidget(tg)
        eql = QLabel(eq.upper())
        eql.setFont(QFont(pfd_fonts.SANS, 7))
        eql.setStyleSheet(
            f"color:{TOK['ink_soft']}; letter-spacing:1px;"
        )
        ic.addWidget(eql)
        pl.addLayout(ic, 1)
        col.addWidget(pill)
        return col


class _DashArrow(QFrame):
    """Una flecha punteada con cabeza, en color teal."""

    def __init__(self, parent=None, color: QColor = None):
        super().__init__(parent)
        self._color = color or QColor(TOK["accent"])

    def paintEvent(self, ev):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(self._color, 2)
        pen.setStyle(Qt.CustomDashLine); pen.setDashPattern([6, 4])
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        y = self.height() / 2
        x_end = self.width() - 8
        p.drawLine(0, int(y), int(x_end), int(y))
        # cabeza triangular
        p.setBrush(QBrush(self._color)); p.setPen(Qt.NoPen)
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF
        tri = QPolygonF([
            QPointF(x_end + 6, y),
            QPointF(x_end - 2, y - 4),
            QPointF(x_end - 2, y + 4),
        ])
        p.drawPolygon(tri)


# ════════════════════════════════════════════════════════
#  SIDEBAR
# ════════════════════════════════════════════════════════

class _StreamSidebar(QFrame):
    sectionChanged = Signal(str)

    SECTIONS = [
        ("identidad",   "T", "Identidad"),
        ("termo",       "θ", "Termodinámica"),
        ("composicion", "Σ", "Composición"),
        ("hidraulica",  "Δ", "Hidráulica"),
        ("propiedades", "≈", "Propiedades"),
        ("geometria",   "↗", "Geometría"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("strSidebar")
        self.setFixedWidth(168)
        self.setStyleSheet(
            f"#strSidebar {{ background:{TOK['bg_mute']}; "
            f"border-right:1px solid {TOK['line']}; }}"
        )
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 12, 8, 12); self._lay.setSpacing(2)

        self._items: Dict[str, QFrame] = {}
        self._active = "identidad"

        for key, icon, label in self.SECTIONS:
            row = QFrame(self); row.setObjectName(f"strNav_{key}")
            row.setCursor(Qt.PointingHandCursor)
            rl = QHBoxLayout(row); rl.setContentsMargins(8, 6, 8, 6); rl.setSpacing(8)
            ico = QLabel(icon); ico.setFixedWidth(14)
            ico.setAlignment(Qt.AlignCenter)
            ico.setFont(QFont(pfd_fonts.MONO, 10, QFont.Bold))
            ico.setStyleSheet(f"color:{TOK['ink_mute']};")
            rl.addWidget(ico)
            lbl = QLabel(label)
            lbl.setFont(QFont(pfd_fonts.SANS, 9))
            lbl.setStyleSheet(f"color:{TOK['ink']};")
            rl.addWidget(lbl, 1)
            row.mousePressEvent = (lambda ev, k=key: self._on_click(k))
            self._items[key] = row
            self._lay.addWidget(row)

        self._lay.addStretch(1)
        # DOF box al fondo
        self._dof = QFrame(self); self._dof.setObjectName("strDof")
        dl = QHBoxLayout(self._dof); dl.setContentsMargins(8, 8, 8, 8); dl.setSpacing(6)
        self._dof_dot = QLabel(); self._dof_dot.setFixedSize(8, 8)
        self._dof_text = QLabel("Consistente")
        self._dof_text.setFont(QFont(pfd_fonts.SANS, 8))
        self._dof_text.setTextFormat(Qt.RichText)
        self._dof_text.setWordWrap(True)
        dl.addWidget(self._dof_dot)
        dl.addWidget(self._dof_text, 1)
        self._lay.addWidget(self._dof)
        self.set_dof("ok", "0 sobre-spec")
        self._refresh_styles()

    def _on_click(self, key):
        if key == self._active:
            return
        self._active = key
        self._refresh_styles()
        self.sectionChanged.emit(key)

    def active(self) -> str:
        return self._active

    def set_active(self, key):
        if key in self._items:
            self._active = key
            self._refresh_styles()

    def set_dof(self, state: str, text: str):
        if state == "ok":
            color = TOK["green"]; bg = TOK["green_bg"]
        elif state == "warn":
            color = TOK["amber"]; bg = TOK["amber_bg"]
        else:
            color = TOK["danger"]; bg = TOK["danger_bg"]
        self._dof.setStyleSheet(
            f"#strDof {{ background:{bg}; border-radius:7px; }}"
        )
        self._dof_dot.setStyleSheet(
            f"background:{color}; border-radius:4px;"
        )
        self._dof_text.setText(text)
        self._dof_text.setStyleSheet(f"color:{color};")

    def _refresh_styles(self):
        for key, row in self._items.items():
            if key == self._active:
                row.setStyleSheet(
                    f"QFrame#strNav_{key} {{ background:{TOK['bg_elev']}; "
                    f"border-left:2.5px solid {TOK['accent']}; "
                    f"border-radius:6px; }}"
                )
            else:
                row.setStyleSheet(
                    f"QFrame#strNav_{key} {{ background:transparent; "
                    f"border-radius:6px; }} "
                    f"QFrame#strNav_{key}:hover {{ background:{TOK['bg_sunk']}; }}"
                )


# ════════════════════════════════════════════════════════
#  HELPERS COMUNES PARA SECCIONES
# ════════════════════════════════════════════════════════

def _section_header(title: str, sub: str = "", help_text: str = "") -> QVBoxLayout:
    wrap = QVBoxLayout(); wrap.setContentsMargins(0,0,0,0); wrap.setSpacing(4)
    hd = QHBoxLayout(); hd.setContentsMargins(0,0,0,0); hd.setSpacing(8)
    tl = QLabel(title); tl.setFont(QFont(pfd_fonts.SANS, 11, QFont.Bold))
    tl.setStyleSheet(f"color:{TOK['ink']};")
    hd.addWidget(tl)
    if sub:
        sl = QLabel(sub); sl.setFont(QFont(pfd_fonts.SANS, 8))
        sl.setStyleSheet(f"color:{TOK['ink_soft']};")
        hd.addWidget(sl)
    hd.addStretch(1)
    wrap.addLayout(hd)
    if help_text:
        ht = QLabel(help_text); ht.setWordWrap(True)
        ht.setFont(QFont(pfd_fonts.SANS, 8))
        ht.setStyleSheet(f"color:{TOK['ink_mute']}; line-height:1.4em;")
        wrap.addWidget(ht)
    return wrap


def _form_row(label: str, control, info: str = "") -> QFrame:
    r = QFrame()
    lay = QHBoxLayout(r); lay.setContentsMargins(0, ROW_PAD//2, 0, ROW_PAD//2)
    lay.setSpacing(12)
    l = QLabel(label)
    l.setFont(QFont(pfd_fonts.SANS, 9))
    l.setStyleSheet(f"color:{TOK['ink_mute']};")
    l.setMinimumWidth(140)
    if info:
        l.setToolTip(info)
    lay.addWidget(l)
    lay.addWidget(control, 1)
    r.setStyleSheet(f"QFrame {{ border-bottom:1px solid {TOK['line_soft']}; }}")
    return r


def _line_input(value: str = "") -> QLineEdit:
    e = QLineEdit(value)
    e.setStyleSheet(
        f"QLineEdit {{ background:{TOK['bg_elev']}; color:{TOK['ink']}; "
        f"border:1px solid {TOK['line_strong']}; border-radius:7px; "
        f"padding:6px 8px; font-family:'{pfd_fonts.SANS}'; font-size:9pt; }} "
        f"QLineEdit:focus {{ border:1.5px solid {TOK['accent']}; }}"
    )
    return e


def _combo() -> QComboBox:
    cb = QComboBox()
    cb.setStyleSheet(
        f"QComboBox {{ background:{TOK['bg_elev']}; color:{TOK['ink']}; "
        f"border:1px solid {TOK['line_strong']}; border-radius:6px; "
        f"padding:5px 8px; font-family:'{pfd_fonts.SANS}'; font-size:9pt; }} "
        f"QComboBox:hover {{ border:1px solid {TOK['accent_soft']}; }} "
        f"QComboBox::drop-down {{ border:0; }} "
        f"QComboBox QAbstractItemView {{ background:{TOK['bg_elev']}; "
        f"border:1px solid {TOK['line_strong']}; "
        f"selection-background-color:{TOK['accent_tint']}; "
        f"selection-color:{TOK['ink']}; }}"
    )
    return cb


# ════════════════════════════════════════════════════════
#  PANEL PRINCIPAL — StreamInspectorPanel
# ════════════════════════════════════════════════════════

class StreamInspectorPanel(QWidget):
    closeRequested = Signal()
    saved          = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stream = None
        self.fs = None
        self._on_save: Optional[Callable] = None
        self._on_cancel: Optional[Callable] = None
        self._fields: Dict[str, SpecField] = {}
        self._extras: Dict[str, object] = {}
        self._comp_rows: List[Tuple[str, QLineEdit]] = []

        # suscribirse a cambios de tema.  Solo RuntimeError es esperado
        # (QApplication aún no creada en algunos paths de import); el resto
        # de excepciones se loggean para no perderlas silenciosamente.
        try:
            _PrefsBus.signal().connect(self._on_prefs_changed)
        except RuntimeError:
            pass   # QApplication aún no instanciada
        except Exception as _e:
            print(f"[stream_inspector] PrefsBus connect failed: {_e}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        self._header = _StreamHeader(self)
        self._header.closeRequested.connect(self._on_close_requested)
        outer.addWidget(self._header)

        self._path = _PathStrip(self)
        outer.addWidget(self._path)

        body = QFrame(self); body.setObjectName("strBody")
        body.setStyleSheet(f"#strBody {{ background:{TOK['bg_elev']}; }}")
        bl = QHBoxLayout(body); bl.setContentsMargins(0,0,0,0); bl.setSpacing(0)
        self._sidebar = _StreamSidebar(self)
        self._sidebar.sectionChanged.connect(self._switch_section)
        bl.addWidget(self._sidebar)
        self._content_scroll = QScrollArea(self)
        self._content_scroll.setWidgetResizable(True)
        self._content_scroll.setFrameShape(QFrame.NoFrame)
        self._content_scroll.setStyleSheet(f"background:{TOK['bg_elev']};")
        self._content = QWidget()
        self._content.setStyleSheet(f"background:{TOK['bg_elev']};")
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(20, 18, 20, 18)
        self._content_lay.setSpacing(SECT_GAP)
        self._content_lay.addStretch(1)
        self._content_scroll.setWidget(self._content)
        bl.addWidget(self._content_scroll, 1)
        outer.addWidget(body, 1)

        self._footer = self._build_footer()
        outer.addWidget(self._footer)

    def _build_footer(self) -> QFrame:
        ft = QFrame(self); ft.setObjectName("strFooter")
        ft.setFixedHeight(60)
        ft.setStyleSheet(
            f"#strFooter {{ background:{TOK['bg_mute']}; "
            f"border-top:1px solid {TOK['line']}; }}"
        )
        lay = QHBoxLayout(ft); lay.setContentsMargins(20, 8, 14, 8); lay.setSpacing(18)

        # 3 stats: FLUJO, VALOR ANUAL, DOF
        self._stat_flow_lbl = QLabel("FLUJO")
        self._stat_flow_val = QLabel("—")
        self._stat_flow_unit = QLabel("tm/año")
        self._stat_val_lbl  = QLabel("VALOR ANUAL")
        self._stat_val_val  = QLabel("—")
        self._stat_val_unit = QLabel("USD")
        self._stat_dof_lbl  = QLabel("DOF")
        self._stat_dof_val  = QLabel("0")
        self._stat_dof_unit = QLabel("ok")

        for cap, val, unit in [
            (self._stat_flow_lbl, self._stat_flow_val, self._stat_flow_unit),
            (self._stat_val_lbl,  self._stat_val_val,  self._stat_val_unit),
            (self._stat_dof_lbl,  self._stat_dof_val,  self._stat_dof_unit),
        ]:
            col = QVBoxLayout(); col.setContentsMargins(0,0,0,0); col.setSpacing(1)
            cap.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
            cap.setStyleSheet(f"color:{TOK['ink_soft']}; letter-spacing:1px;")
            col.addWidget(cap)
            inner = QHBoxLayout(); inner.setSpacing(3); inner.setAlignment(Qt.AlignBaseline)
            val.setFont(QFont(pfd_fonts.MONO, 11, QFont.Bold))
            val.setStyleSheet(f"color:{TOK['ink']};")
            unit.setFont(QFont(pfd_fonts.SANS, 8))
            unit.setStyleSheet(f"color:{TOK['ink_soft']};")
            inner.addWidget(val); inner.addWidget(unit)
            col.addLayout(inner)
            lay.addLayout(col)
        lay.addStretch(1)

        self._cancel_btn = QPushButton("Cancelar")
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TOK['ink_mute']}; "
            f"border:1px solid {TOK['line']}; border-radius:6px; "
            f"padding:6px 14px; }} "
            f"QPushButton:hover {{ background:{TOK['bg_mute']}; }}"
        )
        self._cancel_btn.clicked.connect(self._on_close_requested)
        lay.addWidget(self._cancel_btn)

        self._save_btn = QPushButton("Guardar cambios")
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setFont(QFont(pfd_fonts.SANS, 9, QFont.Bold))
        self._save_btn.setStyleSheet(
            f"QPushButton {{ background:{TOK['accent']}; color:white; "
            f"border:0; border-radius:6px; padding:7px 16px; }} "
            f"QPushButton:hover {{ background:{TOK['accent_deep']}; }}"
        )
        self._save_btn.clicked.connect(self._do_save)
        lay.addWidget(self._save_btn)
        return ft

    # ── API pública ─────────────────────────────────────
    def load_stream(self, stream, flowsheet,
                    on_save: Optional[Callable] = None,
                    on_cancel: Optional[Callable] = None):
        """Carga un stream para edición.

        on_save:   se invoca tras pulsar Guardar — el callback hace
                   validación, push undo cmd, refresh canvas.
        on_cancel: se invoca cuando el user cierra sin guardar (X o
                   Cancelar) — el callback debería revertir cualquier
                   mutación que el panel hizo durante la sesión.
        """
        self.stream = stream
        self.fs = flowsheet
        self._on_save = on_save
        self._on_cancel = on_cancel
        self._fields.clear(); self._extras.clear(); self._comp_rows.clear()

        # Header
        b_src = flowsheet.blocks.get(stream.src) if flowsheet else None
        b_dst = flowsheet.blocks.get(stream.dst) if flowsheet else None
        src_tag = b_src.name if b_src else "(sin)"
        dst_tag = b_dst.name if b_dst else "(sin)"
        src_eq = b_src.eq_type if b_src else "boundary"
        dst_eq = b_dst.eq_type if b_dst else "boundary"
        src_port = stream.src_port or "out"
        dst_port = stream.dst_port or "in"
        self._header.set_stream(
            int(getattr(stream, "display_number", 0) or 0),
            stream.name,
            f"{src_tag}.{src_port}",
            f"{dst_tag}.{dst_port}",
        )

        # Path strip
        # mass_flow del modelo en tm/año
        self._path.populate(
            src_tag, src_eq, dst_tag, dst_eq,
            int(getattr(stream, "display_number", 0) or 0),
            float(stream.mass_flow or 0),
            getattr(stream, "phase", "") or "",
        )

        # construir Identidad por default
        self._sidebar.set_active("identidad")
        self._build_section_content("identidad")
        self._update_footer()
        self._update_dof()

    # ── Switch section ────────────────────────────────
    def _switch_section(self, key):
        # Antes de cambiar de sección, persistir lo que se editó en la
        # actual (in-memory) — los SpecField se destruyen al rebuild.
        self._stash_current_section()
        self._fields.clear()
        self._extras.clear()
        self._comp_rows.clear()
        # Sincronizar sidebar (caller puede ser programático)
        if self._sidebar.active() != key:
            self._sidebar.set_active(key)
        self._build_section_content(key)

    def _stash_current_section(self):
        """Aplica los valores del set actual al stream in-memory.
        Sin esto, los edits se pierden al cambiar de sección.

        Cualquier excepción se logguea pero NO se silencia — perder
        edits sin warning es peor que un traceback en consola."""
        if self.stream is None:
            return
        try:
            self._apply_to_stream(commit=False)
        except Exception as _e:
            import traceback
            print(f"[stream_inspector] _stash_current_section failed: "
                  f"{type(_e).__name__}: {_e}")
            traceback.print_exc()

    def _clear_content(self):
        while self._content_lay.count() > 1:
            it = self._content_lay.takeAt(0)
            w = it.widget()
            if w: w.setParent(None); w.deleteLater()

    def _build_section_content(self, key):
        self._clear_content()
        builders = {
            "identidad":   self._sec_identidad,
            "termo":       self._sec_termo,
            "composicion": self._sec_composicion,
            "hidraulica":  self._sec_hidraulica,
            "propiedades": self._sec_propiedades_calc,
            "geometria":   self._sec_geometria,
        }
        fn = builders.get(key)
        if fn:
            sect = fn()
            self._content_lay.insertWidget(self._content_lay.count()-1, sect)

        # scroll to top
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0,
            lambda: self._content_scroll.verticalScrollBar().setValue(0))

    # ── Sección Identidad ────────────────────────────
    def _sec_identidad(self) -> QFrame:
        s = self.stream
        sect = QFrame(); l = QVBoxLayout(sect)
        l.setContentsMargins(0,0,0,0); l.setSpacing(8)
        l.addLayout(_section_header(
            "Identidad",
            help_text="Tag visible en el canvas, rol en el balance global "
                      "y N° de corriente para el reporte."))

        # Tag (inline) — duplicado del header pero también acá por accesibilidad
        # No mostramos otra vez el tag; el del header es la fuente de verdad.

        # Rol — pill buttons
        role_row = QHBoxLayout(); role_row.setSpacing(6)
        self._role_group = QButtonGroup(sect)
        current_role = s.role or "internal"
        for r in ROLES:
            bg, fg, label = role_style(r)
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(r == current_role)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFont(QFont(pfd_fonts.SANS, 8, QFont.Bold))
            on_style = (
                f"QPushButton {{ background:{bg}; color:{fg}; "
                f"border:1px solid {fg}; border-radius:12px; "
                f"padding:3px 10px; letter-spacing:1px; }}"
            )
            off_style = (
                f"QPushButton {{ background:transparent; color:{TOK['ink_mute']}; "
                f"border:1px solid {TOK['line']}; border-radius:12px; "
                f"padding:3px 10px; letter-spacing:1px; }}"
                f"QPushButton:hover {{ background:{TOK['bg_mute']}; }}"
            )
            btn.setStyleSheet(on_style if r == current_role else off_style)
            btn.setProperty("role", r)
            btn.setProperty("on_style", on_style)
            btn.setProperty("off_style", off_style)
            btn.clicked.connect(lambda _=False, b=btn: self._on_role_pick(b))
            self._role_group.addButton(btn)
            role_row.addWidget(btn)
        role_row.addStretch(1)
        wrap = QFrame(); wrap.setLayout(role_row)
        self._extras["role_buttons"] = self._role_group
        l.addWidget(_form_row("Rol", wrap))

        # N° corriente
        n = int(getattr(s, "display_number", 0) or 0)
        sf_n = SpecField(value=str(n) if n > 0 else "", unit="·",
                         state="spec" if n > 0 else "empty",
                         allow_toggle=False)
        self._fields["display_number"] = sf_n
        l.addWidget(_form_row("N° corriente", sf_n,
                              info="0 = auto (numeración topológica desde feeds)"))

        # Puertos src/dst (si los blocks tienen ports definidos)
        try:
            import equipment_ports as ep
            b_src = self.fs.blocks.get(s.src) if self.fs else None
            b_dst = self.fs.blocks.get(s.dst) if self.fs else None
            src_ports = list(ep.get_ports(b_src.eq_type).keys()) if b_src else []
            dst_ports = list(ep.get_ports(b_dst.eq_type).keys()) if b_dst else []
        except Exception:
            src_ports = []; dst_ports = []

        if src_ports:
            cb = _combo()
            for p in src_ports: cb.addItem(p)
            cur = s.src_port or ""
            if cur in src_ports: cb.setCurrentIndex(src_ports.index(cur))
            self._extras["src_port"] = cb
            l.addWidget(_form_row("Puerto origen", cb))
        if dst_ports:
            cb = _combo()
            for p in dst_ports: cb.addItem(p)
            cur = s.dst_port or ""
            if cur in dst_ports: cb.setCurrentIndex(dst_ports.index(cur))
            self._extras["dst_port"] = cb
            l.addWidget(_form_row("Puerto destino", cb))

        # Precio si feed/product
        if (s.role or "internal") in ("feed", "product"):
            pr = float(getattr(s, "price_usd_per_tm", 0.0) or 0.0)
            sf_pr = SpecField(value=f"{pr:.2f}", unit="USD/tm",
                              state="spec", allow_toggle=False)
            self._fields["price_usd_per_tm"] = sf_pr
            l.addWidget(_form_row("Precio", sf_pr))

        return sect

    def _on_role_pick(self, btn):
        # Guard RuntimeError: si el user cambia de sección rápido entre
        # clicks, el group puede ser destruido por deleteLater() mientras
        # esta lambda se procesa.
        try:
            for b in self._role_group.buttons():
                on = (b is btn)
                b.setChecked(on)
                b.setStyleSheet(b.property("on_style") if on else b.property("off_style"))
        except RuntimeError:
            pass

    # ── Sección Termodinámica ────────────────────────
    def _sec_termo(self) -> QFrame:
        s = self.stream
        sect = QFrame(); l = QVBoxLayout(sect)
        l.setContentsMargins(0,0,0,0); l.setSpacing(8)
        l.addLayout(_section_header(
            "Termodinámica", sub="balance de energía",
            help_text="Fijá lo que conocés; el solver calcula el resto. "
                      "Tocá el toggle para alternar spec/auto."))

        # Temperatura
        T = float(getattr(s, "temperature", 25.0) or 25.0)
        sf_T = SpecField(value=f"{T:.1f}", unit="°C",
                         state="spec" if getattr(s, "temperature_locked", False) else "auto")
        self._fields["temperature"] = sf_T
        l.addWidget(_form_row("Temperatura", sf_T,
                              info="auto = balance de energía la calcula desde upstream"))

        # T objetivo (setpoint)
        tt = float(getattr(s, "target_temperature", -999.0) or -999.0)
        has_sp = tt > -273.0
        sf_tt = SpecField(value=f"{tt:.1f}" if has_sp else "",
                          unit="°C",
                          state="spec" if has_sp else "empty",
                          placeholder="— sin setpoint")
        self._fields["target_temperature"] = sf_tt
        l.addWidget(_form_row("T objetivo", sf_tt,
                              info="Setpoint de diseño: el solver ajusta el duty del bloque upstream"))

        # Presión
        P = float(getattr(s, "pressure_bar", 1.013) or 1.013)
        sf_P = SpecField(value=f"{P:.3f}", unit="bar",
                         state="spec" if getattr(s, "pressure_locked", False) else "auto")
        self._fields["pressure_bar"] = sf_P
        l.addWidget(_form_row("Presión", sf_P))

        # Fase — pill buttons
        phase_row = QHBoxLayout(); phase_row.setSpacing(6)
        phases = ["liquid", "vapor", "gas", "two_phase"]
        current_phase = getattr(s, "phase", "") or "liquid"
        if current_phase not in phases:
            current_phase = "liquid"
        self._phase_group = QButtonGroup(sect)
        for p in phases:
            label = PHASE_LABEL[p]
            color = PHASE_DOT[p]
            btn = QPushButton(f"●  {label}")
            btn.setCheckable(True); btn.setChecked(p == current_phase)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFont(QFont(pfd_fonts.SANS, 9, QFont.DemiBold))
            on_style = (
                f"QPushButton {{ background:{TOK['bg_elev']}; color:{TOK['ink']}; "
                f"border:1px solid {TOK['accent']}; "
                f"border-left:3px solid {TOK['accent']}; "
                f"border-radius:6px; padding:4px 9px 4px 7px; }}"
            )
            off_style = (
                f"QPushButton {{ background:transparent; color:{TOK['ink_mute']}; "
                f"border:1px solid {TOK['line']}; border-radius:6px; "
                f"padding:4px 9px 4px 7px; }} "
                f"QPushButton:hover {{ background:{TOK['bg_mute']}; }}"
            )
            btn.setStyleSheet(on_style if p == current_phase else off_style)
            btn.setProperty("phase", p)
            btn.setProperty("on_style", on_style)
            btn.setProperty("off_style", off_style)
            btn.clicked.connect(lambda _=False, b=btn: self._on_phase_pick(b))
            self._phase_group.addButton(btn)
            phase_row.addWidget(btn)
        phase_row.addStretch(1)
        pw = QFrame(); pw.setLayout(phase_row)
        self._extras["phase_buttons"] = self._phase_group
        l.addWidget(_form_row("Fase", pw))

        # Cp (auto por default)
        cp = float(getattr(s, "cp", 0.0) or 0.0)
        sf_cp = SpecField(
            value=f"{cp:.3f}" if cp > 0 else "",
            unit="kJ/kg·K",
            state="spec" if cp > 0 else "auto",
        )
        self._fields["cp"] = sf_cp
        l.addWidget(_form_row("Cp", sf_cp,
                              info="Auto = solver calcula desde composición + fase"))

        # ΔHvap override
        dhv = float(getattr(s, "delta_h_vap_override", 0.0) or 0.0)
        sf_dh = SpecField(
            value=f"{dhv:.1f}" if dhv > 0 else "",
            unit="kJ/kg",
            state="spec" if dhv > 0 else "empty",
            placeholder="— auto desde composición",
        )
        self._fields["delta_h_vap_override"] = sf_dh
        l.addWidget(_form_row("ΔH vaporización", sf_dh,
                              info="Override solo si querés sobreescribir el cálculo desde composición"))

        return sect

    def _on_phase_pick(self, btn):
        # ver _on_role_pick — guard contra rebuild rápido del section
        try:
            for b in self._phase_group.buttons():
                on = (b is btn)
                b.setChecked(on)
                b.setStyleSheet(b.property("on_style") if on else b.property("off_style"))
        except RuntimeError:
            pass

    # ── Sección Composición ─────────────────────────
    def _sec_composicion(self) -> QFrame:
        s = self.stream
        sect = QFrame(); l = QVBoxLayout(sect)
        l.setContentsMargins(0,0,0,0); l.setSpacing(8)
        comp = getattr(s, "composition", None) or {}
        if isinstance(comp, dict):
            comp_items = list(comp.items())
        else:
            comp_items = list(comp)
        l.addLayout(_section_header(
            "Composición", sub=f"{len(comp_items)} componentes",
            help_text="Fracción másica por componente. Σ debe sumar 1.00 — "
                      "el botón \"Normalizar\" escala."))

        # Tabla custom (vivirá en un QFrame para poder rebuild filas)
        self._comp_table = QFrame(); self._comp_table.setObjectName("compTbl")
        self._comp_table.setStyleSheet(
            f"#compTbl {{ background:{TOK['bg_elev']}; "
            f"border:1px solid {TOK['line']}; border-radius:8px; }}"
        )
        self._comp_lay = QVBoxLayout(self._comp_table)
        self._comp_lay.setContentsMargins(0, 0, 0, 0); self._comp_lay.setSpacing(0)

        # header row
        hdr = QFrame()
        hl = QHBoxLayout(hdr); hl.setContentsMargins(12, 8, 12, 8); hl.setSpacing(10)
        for txt, w, align in [
            ("", 12, Qt.AlignLeft),
            ("COMPONENTE", 120, Qt.AlignLeft),
            ("FRACCIÓN", 80, Qt.AlignLeft),
            ("tm/AÑO", 70, Qt.AlignRight),
            ("", 22, Qt.AlignCenter),
        ]:
            lbl = QLabel(txt)
            lbl.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
            lbl.setStyleSheet(
                f"color:{TOK['ink_soft']}; letter-spacing:1.2px;"
            )
            lbl.setMinimumWidth(w); lbl.setAlignment(align)
            hl.addWidget(lbl, 1 if not w else 0)
        hdr.setStyleSheet(
            f"QFrame {{ background:{TOK['bg_mute']}; "
            f"border-bottom:1px solid {TOK['line']}; }}"
        )
        self._comp_lay.addWidget(hdr)

        # filas de componentes
        self._comp_rows_wrap = QVBoxLayout()
        self._comp_rows_wrap.setContentsMargins(0,0,0,0); self._comp_rows_wrap.setSpacing(0)
        rows_wrap = QFrame(); rows_wrap.setLayout(self._comp_rows_wrap)
        self._comp_lay.addWidget(rows_wrap)
        self._refresh_comp_rows(comp_items)

        # footer del tabla — + agregar, normalizar, Σ
        ftr = QFrame()
        ftr.setStyleSheet(
            f"QFrame {{ background:{TOK['bg_mute']}; "
            f"border-top:1px solid {TOK['line']}; }}"
        )
        fl = QHBoxLayout(ftr); fl.setContentsMargins(12, 8, 12, 8); fl.setSpacing(8)
        add_btn = QPushButton("+ Agregar")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFont(QFont(pfd_fonts.SANS, 9, QFont.Bold))
        add_btn.setStyleSheet(
            f"QPushButton {{ background:{TOK['accent']}; color:white; "
            f"border:0; border-radius:5px; padding:4px 12px; }} "
            f"QPushButton:hover {{ background:{TOK['accent_deep']}; }}"
        )
        add_btn.clicked.connect(self._on_add_comp)
        fl.addWidget(add_btn)
        norm_btn = QPushButton("Normalizar Σ → 1.00")
        norm_btn.setCursor(Qt.PointingHandCursor)
        norm_btn.setFont(QFont(pfd_fonts.SANS, 9))
        norm_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TOK['ink_mute']}; "
            f"border:1px solid {TOK['line']}; border-radius:5px; "
            f"padding:4px 12px; }} "
            f"QPushButton:hover {{ background:{TOK['bg_elev']}; }}"
        )
        norm_btn.clicked.connect(self._on_normalize_comp)
        fl.addWidget(norm_btn)
        fl.addStretch(1)
        self._sigma_lbl = QLabel("Σ = 0.00")
        self._sigma_lbl.setFont(QFont(pfd_fonts.MONO, 10, QFont.Bold))
        fl.addWidget(self._sigma_lbl)
        self._comp_lay.addWidget(ftr)
        l.addWidget(self._comp_table)

        # Lock toggle (composition_locked)
        lock_wrap = QFrame()
        ll = QHBoxLayout(lock_wrap); ll.setContentsMargins(12, 8, 12, 8); ll.setSpacing(10)
        self._comp_lock_cb = QCheckBox("Composición fija — el solver no la recomputa")
        self._comp_lock_cb.setChecked(bool(getattr(s, "composition_locked", False)))
        self._comp_lock_cb.setStyleSheet(
            f"QCheckBox {{ color:{TOK['spec_ink']}; "
            f"font-family:'{pfd_fonts.SANS}'; font-size:9pt; spacing:8px; }} "
            f"QCheckBox::indicator {{ width:16px; height:16px; "
            f"border:1.5px solid {TOK['line_strong']}; "
            f"border-radius:4px; background:{TOK['bg_elev']}; }} "
            f"QCheckBox::indicator:checked {{ background:{TOK['accent']}; "
            f"border-color:{TOK['accent']}; }}"
        )
        ll.addWidget(self._comp_lock_cb)
        ll.addStretch(1)
        lock_wrap.setStyleSheet(
            f"QFrame {{ background:{TOK['spec_bg']}; "
            f"border:1px solid {TOK['spec_ribbon']}; border-radius:7px; }}"
        )
        self._extras["composition_lock_cb"] = self._comp_lock_cb
        l.addWidget(lock_wrap)
        self._update_sigma()
        return sect

    def _refresh_comp_rows(self, items):
        # limpiar
        while self._comp_rows_wrap.count():
            it = self._comp_rows_wrap.takeAt(0)
            w = it.widget()
            if w: w.setParent(None); w.deleteLater()
        self._comp_rows.clear()
        colors = [TOK["accent"], TOK["orange"], TOK["spec"], TOK["amber"],
                   TOK["danger"], TOK["green"]]
        for i, (name, frac) in enumerate(items):
            row = self._build_comp_row(i, name, float(frac), colors[i % len(colors)])
            self._comp_rows_wrap.addWidget(row)

    def _build_comp_row(self, idx, name, frac, color):
        row = QFrame()
        rl = QHBoxLayout(row); rl.setContentsMargins(12, 8, 12, 8); rl.setSpacing(10)
        row.setStyleSheet(
            f"QFrame {{ border-bottom:1px solid {TOK['line_soft']}; }}"
        )
        # color dot
        dot = QLabel(); dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background:{color}; border-radius:5px;")
        rl.addWidget(dot)
        # name input
        nm = _line_input(name); nm.setMinimumWidth(110)
        nm.setFont(QFont(pfd_fonts.SANS, 9))
        rl.addWidget(nm)
        # fraction input
        fr = _line_input(f"{frac:.4f}"); fr.setMaximumWidth(80)
        fr.setFont(QFont(pfd_fonts.MONO, 9))
        fr.textChanged.connect(self._update_sigma)
        rl.addWidget(fr)
        # mass flow estimado
        s = self.stream
        mass = float(s.mass_flow or 0)
        flow = frac * mass
        flow_lbl = QLabel(f"{flow:,.0f}".replace(",", " "))
        flow_lbl.setFont(QFont(pfd_fonts.MONO, 9))
        flow_lbl.setStyleSheet(f"color:{TOK['ink_mute']};")
        flow_lbl.setMinimumWidth(60); flow_lbl.setAlignment(Qt.AlignRight)
        rl.addWidget(flow_lbl)
        # delete btn
        rm = QToolButton(); rm.setText("✕"); rm.setFixedSize(22, 22)
        rm.setCursor(Qt.PointingHandCursor)
        rm.setStyleSheet(
            f"QToolButton {{ background:transparent; color:{TOK['ink_ghost']}; "
            f"border:1px solid {TOK['line']}; border-radius:4px; }} "
            f"QToolButton:hover {{ background:{TOK['danger_bg']}; "
            f"color:{TOK['danger']}; }}"
        )
        rm.clicked.connect(lambda: self._on_remove_comp_row(idx))
        rl.addWidget(rm)
        self._comp_rows.append((nm, fr))
        return row

    def _on_add_comp(self):
        items = self._current_comp_items()
        items.append(("nuevo", 0.0))
        self._refresh_comp_rows(items)
        self._update_sigma()

    def _on_remove_comp_row(self, idx):
        items = self._current_comp_items()
        if 0 <= idx < len(items):
            del items[idx]
            self._refresh_comp_rows(items)
            self._update_sigma()

    def _on_normalize_comp(self):
        items = self._current_comp_items()
        total = sum(f for _, f in items if f > 0)
        if total <= 0:
            # No hay fracciones positivas — el botón es un no-op pero
            # damos feedback explícito en lugar de silencio.
            QMessageBox.information(
                self, "Σ es cero",
                "No hay fracciones positivas para normalizar.\n\n"
                "Ingresá al menos una fracción > 0 y volvé a intentar."
            )
            self._update_sigma()
            return
        items = [(n, f / total) for n, f in items]
        self._refresh_comp_rows(items)
        self._update_sigma()

    def _current_comp_items(self):
        items = []
        for nm_w, fr_w in self._comp_rows:
            name = (nm_w.text() or "").strip()
            if not name: continue
            try:
                frac = float((fr_w.text() or "0").replace(",", "."))
            except ValueError:
                frac = 0.0
            items.append((name, frac))
        return items

    def _update_sigma(self):
        if not hasattr(self, "_sigma_lbl"):
            return
        total = sum(f for _, f in self._current_comp_items())
        ok = abs(total - 1.0) < 0.01
        color = TOK["green"] if ok else TOK["amber"]
        flag = "✓" if ok else "⚠"
        self._sigma_lbl.setText(f"Σ = {total:.4f}  {flag}")
        self._sigma_lbl.setStyleSheet(f"color:{color};")

    # ── Sección Hidráulica ─────────────────────────
    def _sec_hidraulica(self) -> QFrame:
        s = self.stream
        sect = QFrame(); l = QVBoxLayout(sect)
        l.setContentsMargins(0,0,0,0); l.setSpacing(8)
        l.addLayout(_section_header(
            "Hidráulica", sub="Darcy-Weisbach",
            help_text="Si está activo, el solver calcula ΔP_fric + ΔP_local "
                      "y lo descuenta de la presión downstream. Si no, la "
                      "corriente es conceptual: P se propaga sin pérdida."))

        # Toggle is_pipe (card)
        is_pipe = bool(getattr(s, "is_pipe", False))
        toggle_card = QFrame()
        tc = QHBoxLayout(toggle_card); tc.setContentsMargins(12, 10, 12, 10); tc.setSpacing(10)
        toggle_card.setStyleSheet(
            f"QFrame {{ background:{TOK['bg_elev']}; "
            f"border:1px solid {TOK['line_strong']}; border-radius:8px; }}"
        )
        self._pipe_cb = QCheckBox("Tratar como tubería física")
        self._pipe_cb.setChecked(is_pipe)
        self._pipe_cb.setFont(QFont(pfd_fonts.SANS, 9, QFont.DemiBold))
        self._pipe_cb.setStyleSheet(
            f"QCheckBox {{ color:{TOK['ink']}; spacing:10px; }} "
            f"QCheckBox::indicator {{ width:32px; height:18px; "
            f"border-radius:9px; background:{TOK['bg_sunk']}; }} "
            f"QCheckBox::indicator:checked {{ background:{TOK['accent']}; }}"
        )
        tc.addWidget(self._pipe_cb)
        tc.addStretch(1)
        self._extras["is_pipe_cb"] = self._pipe_cb
        l.addWidget(toggle_card)

        # Longitud
        L = float(getattr(s, "pipe_length_m", 0.0) or 0.0)
        sf_L = SpecField(value=f"{L:.1f}" if L > 0 else "", unit="m",
                         state="spec" if L > 0 else "empty",
                         allow_toggle=False, placeholder="default 10")
        self._fields["pipe_length_m"] = sf_L
        l.addWidget(_form_row("Longitud", sf_L))

        # Diámetro
        D_m = float(getattr(s, "pipe_diameter_m", 0.0) or 0.0)
        D_mm = D_m * 1000.0
        sf_D = SpecField(value=f"{D_mm:.0f}" if D_mm > 0 else "", unit="mm",
                         state="spec" if D_mm > 0 else "empty",
                         allow_toggle=False, placeholder="default 50")
        self._fields["pipe_diameter_mm"] = sf_D
        l.addWidget(_form_row("Diámetro interno", sf_D))

        # Rugosidad
        eps_m = float(getattr(s, "pipe_roughness_m", 4.5e-5) or 4.5e-5)
        eps_mm = eps_m * 1000.0
        sf_eps = SpecField(value=f"{eps_mm:.3f}", unit="mm",
                           state="spec", allow_toggle=False)
        self._fields["pipe_roughness_mm"] = sf_eps
        l.addWidget(_form_row("Rugosidad ε", sf_eps,
                              info="Acero comercial ≈ 0.045 mm"))

        # K local
        K = float(getattr(s, "pipe_K_local", 0.0) or 0.0)
        sf_K = SpecField(value=f"{K:.2f}", unit="(adim.)",
                         state="spec" if K > 0 else "empty",
                         allow_toggle=False)
        self._fields["pipe_K_local"] = sf_K
        l.addWidget(_form_row("K local", sf_K,
                              info="Σ de coeficientes de accesorios — codos, válvulas, etc."))
        return sect

    # ── Sección Geometría ────────────────────────────
    def _sec_propiedades_calc(self) -> QFrame:
        """FASE 3 — sección de SÓLO LECTURA con las propiedades calculadas de
        la mezcla (densidad, viscosidad, flujo molar, Cp, entalpía…).  Nada se
        inventa: si falta dato de Capa 2 para un componente, se muestra
        'n/d [sin datos en Capa 2]'."""
        s = self.stream
        sect = QFrame(); l = QVBoxLayout(sect)
        l.setContentsMargins(0, 0, 0, 0); l.setSpacing(8)
        l.addLayout(_section_header(
            "Propiedades de la mezcla [calculado]",
            sub="solo lectura · derivado de la composición + T/P",
            help_text="Valores que el solver/termo derivan de la composición "
                      "másica, T y P. No editables."))

        from flowsheet_model import SEC_PER_YEAR, TM_TO_KG
        comp = dict(s.composition or {})
        if not comp and getattr(s, "main_component", ""):
            comp = {s.main_component: 1.0}
        T_C = float(getattr(s, "temperature", 25.0) or 25.0)
        T_K = T_C + 273.15
        P_bar = float(getattr(s, "pressure_bar", 1.013) or 1.013)
        phase = (getattr(s, "phase", "") or "liquid").lower()
        vfrac = float(getattr(s, "vapor_fraction", 0.0) or 0.0)
        mdot_kg_s = float(s.mass_flow or 0.0) * TM_TO_KG / SEC_PER_YEAR

        ND = ("n/d", "[sin datos en Capa 2]")

        def _row(label, value, unit="", nd_note=""):
            r = QFrame(); rl = QHBoxLayout(r)
            rl.setContentsMargins(0, ROW_PAD // 2, 0, ROW_PAD // 2)
            rl.setSpacing(12)
            k = QLabel(label); k.setFont(QFont(pfd_fonts.SANS, 9))
            k.setStyleSheet(f"color:{TOK['ink_mute']};"); k.setMinimumWidth(150)
            rl.addWidget(k)
            if value is None:
                v = QLabel("n/d")
                v.setStyleSheet(f"color:{TOK['ink_soft']}; font-style:italic;")
                v.setToolTip(nd_note or ND[1])
            else:
                v = QLabel(f"{value}{(' ' + unit) if unit else ''}")
                v.setFont(QFont(pfd_fonts.MONO, 9))
                v.setStyleSheet(f"color:{TOK['ink']};")
            rl.addWidget(v, 1)
            r.setStyleSheet(f"QFrame {{ border-bottom:1px solid {TOK['line_soft']}; }}")
            l.addWidget(r)

        # ── MW de la mezcla (base composición MÁSICA): M = 1/Σ(wᵢ/MWᵢ) ──
        mw_mix = None
        missing = []
        try:
            import thermo_db as _td
            inv = 0.0; wtot = 0.0
            for c, w in comp.items():
                co = _td.get(c)
                if co is None or not getattr(co, "mw", 0) or co.mw <= 0:
                    missing.append(c); continue
                inv += w / co.mw; wtot += w
            if inv > 0 and wtot > 0:
                mw_mix = wtot / inv          # g/mol
        except Exception:
            mw_mix = None

        # Flujo másico
        _row("Flujo másico", f"{s.mass_flow:,.0f}", "t/a")
        _row("", f"{mdot_kg_s:.4f}", "kg/s")
        # Flujo molar + M de mezcla
        if mw_mix and mdot_kg_s > 0:
            nmol_kmol_h = mdot_kg_s * 3600.0 / mw_mix   # kmol/h
            _row("Flujo molar", f"{nmol_kmol_h:,.2f}", "kmol/h")
            _row("M de la mezcla", f"{mw_mix:.2f}", "g/mol")
        else:
            _row("Flujo molar", None, nd_note=f"sin MW para: {', '.join(missing) or '—'}")
            _row("M de la mezcla", None, nd_note=f"sin MW para: {', '.join(missing) or '—'}")

        # Densidad, viscosidad, caudal volumétrico.
        # GAS: ρ = P·M/(R·T) con la M REAL de la mezcla (mw_mix), coherente con
        #   el flujo molar de arriba.  (No usamos _density_kg_m3 para gas: usa
        #   una M ponderada por masa que sobreestima ρ en mezclas ricas en H2;
        #   no lo tocamos — es función del solver hidráulico.)
        # LÍQUIDO: _density_kg_m3 (método volume-additive, correcto).
        rho = visc = None
        try:
            import pressure_drop as _pd
            if phase in ("gas", "vapor") and mw_mix:
                rho = P_bar * 1e5 * (mw_mix * 1e-3) / (8.314 * T_K)
            else:
                rho = _pd._density_kg_m3(comp, T_K, phase, P_bar * 1e5)
            visc = _pd._viscosity_Pa_s(comp, T_K, phase)
        except Exception:
            rho = visc = None
        _row("Densidad ρ", f"{rho:.3f}" if rho else None, "kg/m³")
        _row("Viscosidad μ", f"{visc:.3e}" if visc else None, "Pa·s")
        if rho and rho > 0 and mdot_kg_s > 0:
            q_m3_h = mdot_kg_s / rho * 3600.0
            _row("Caudal volumétrico", f"{q_m3_h:,.2f}", "m³/h")
        else:
            _row("Caudal volumétrico", None)

        # Cp y entalpía específica
        cp = None
        try:
            import thermo_db as _td
            cp = _td.cp_mix_kJ_kg_K(comp, T_C, phase)
        except Exception:
            cp = None
        _row("Cp de la mezcla", f"{cp:.3f}" if cp else None, "kJ/kg·K")
        try:
            import stream_enthalpy as _se
            h = _se.specific_enthalpy_kJ_kg(comp, T_C, phase, vfrac)
            _row("h específica", f"{h:.1f}" if h is not None else None, "kJ/kg")
        except Exception:
            _row("h específica", None)

        l.addStretch(1)
        return sect

    def _sec_geometria(self) -> QFrame:
        sect = QFrame(); l = QVBoxLayout(sect)
        l.setContentsMargins(0,0,0,0); l.setSpacing(8)
        l.addLayout(_section_header(
            "Geometría", sub="path en el canvas",
            help_text="Forzá el trazado del stream sin salir del inspector. "
                      "Aplica al render — no toca el balance ni los puertos."))

        # 3 botones grandes
        grid = QGridLayout(); grid.setSpacing(8)
        for i, (key, label, descr) in enumerate([
            ("auto", "Auto-route", "Z-step (codo en L)"),
            ("horz", "Horizontal", "Alinear endpoints (Y)"),
            ("vert", "Vertical",   "Alinear endpoints (X)"),
        ]):
            btn = QPushButton(f"{label}\n{descr}")
            btn.setMinimumHeight(64)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFont(QFont(pfd_fonts.SANS, 9, QFont.DemiBold))
            btn.setStyleSheet(
                f"QPushButton {{ background:{TOK['bg_elev']}; "
                f"color:{TOK['ink_mute']}; "
                f"border:1px solid {TOK['line']}; border-radius:8px; "
                f"padding:10px; text-align:center; }} "
                f"QPushButton:hover {{ border:1px solid {TOK['accent']}; "
                f"color:{TOK['accent']}; }}"
            )
            btn.clicked.connect(lambda _=False, k=key: self._on_geo_pick(k))
            grid.addWidget(btn, 0, i)
        wrap = QFrame(); wrap.setLayout(grid)
        l.addWidget(wrap)

        note = QLabel(
            "Click + arrastrar sobre el path en el canvas crea waypoints "
            "manuales si querés más control."
        )
        note.setWordWrap(True)
        note.setFont(QFont(pfd_fonts.SANS, 8))
        note.setStyleSheet(f"color:{TOK['ink_soft']}; padding-top:6px;")
        l.addWidget(note)
        return sect

    def _on_geo_pick(self, key):
        """Auto/horizontal/vertical alignment.  Aplicado al stream actual."""
        s = self.stream
        if s is None or self.fs is None:
            return
        b_src = self.fs.blocks.get(s.src)
        b_dst = self.fs.blocks.get(s.dst)
        if not b_src or not b_dst:
            QMessageBox.information(self, "Sin geometría",
                "El stream debe estar conectado a 2 bloques para alinear.")
            return
        # Para auto: limpiar waypoints (el router calcula Z-step).
        # Para horz: forzar dst.y = src.y (alineación horizontal).
        # Para vert: forzar dst.x = src.x (alineación vertical).
        from flowsheet_model import GRID_STEP
        if key == "auto":
            s.waypoints = []
        elif key == "horz":
            b_dst.y = b_src.y
            s.waypoints = []
        elif key == "vert":
            b_dst.x = b_src.x
            s.waypoints = []

    # ── Footer + DOF ─────────────────────────────────
    def _update_footer(self):
        s = self.stream
        if not s: return
        mf = float(s.mass_flow or 0)
        self._stat_flow_val.setText(f"{mf:,.0f}".replace(",", " "))
        price = float(getattr(s, "price_usd_per_tm", 0.0) or 0.0)
        val = mf * price
        if val > 0:
            self._stat_val_val.setText(f"${val/1e6:.2f}M")
            self._stat_val_lbl.setVisible(True)
            self._stat_val_val.setVisible(True)
            self._stat_val_unit.setVisible(True)
        else:
            self._stat_val_val.setText("—")

    def _update_dof(self):
        s = self.stream
        if not s:
            return
        # Sudoku-locks: contar cuántos campos están en spec
        specs = 0
        for attr in ("mass_flow_locked", "temperature_locked",
                     "pressure_locked", "composition_locked"):
            if getattr(s, attr, False):
                specs += 1
        # Una corriente tiene ~4 grados de libertad clave
        if specs == 4:
            self._sidebar.set_dof("ok",
                f"<b>{specs}</b> specs · 0 libres<br/>T, P, ṁ, comp.")
            self._stat_dof_val.setText("0")
            self._stat_dof_unit.setText("ok")
        elif specs >= 2:
            self._sidebar.set_dof("warn",
                f"<b>{specs}</b> specs · {4-specs} libre(s)")
            self._stat_dof_val.setText(str(4 - specs))
            self._stat_dof_unit.setText("libre")
        else:
            self._sidebar.set_dof("warn",
                f"<b>{specs}</b> specs · {4-specs} libre(s)")
            self._stat_dof_val.setText(str(4 - specs))
            self._stat_dof_unit.setText("libre")

    # ── Persistencia ─────────────────────────────────
    def _do_save(self):
        if self.stream is None:
            return
        try:
            self._apply_to_stream(commit=True)
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar",
                f"No se pudo aplicar los cambios:\n{e}")
            return
        # Saved: NO disparar on_cancel ya — limpiar para que un close
        # subsiguiente (X) no revierta el save recién hecho.
        self._on_cancel = None
        if self._on_save:
            self._on_save()
        self._update_footer()
        self._update_dof()
        self.saved.emit()
        # cerrar el dock después de un save exitoso
        self.closeRequested.emit()

    def _on_close_requested(self):
        """Handler unificado para X / Cancelar.  Si hay un on_cancel
        callback (ej. revertir desde un snapshot pre-edit), lo invoca
        antes de emitir closeRequested para que el dock se oculte."""
        cb = self._on_cancel
        self._on_cancel = None    # one-shot — evita doble revert
        if cb is not None:
            try:
                cb()
            except Exception as _e:
                print(f"[stream_inspector] on_cancel raised: {_e}")
        self.closeRequested.emit()

    def _apply_to_stream(self, commit: bool = True):
        """Aplica los valores actuales del set renderizado al stream.
        Para los sets NO renderizados, los valores del stream quedan
        intactos."""
        s = self.stream
        if s is None:
            return
        # Tag (siempre presente)
        new_name = self._header.tag()
        if new_name:
            s.name = new_name

        f = self._fields; x = self._extras

        # ── Identidad ──
        if "display_number" in f:
            v = self._parse_num(f["display_number"].value())
            try:
                s.display_number = int(float(v)) if v else 0
            except Exception:
                pass
        if "role_buttons" in x:
            for b in x["role_buttons"].buttons():
                if b.isChecked():
                    s.role = b.property("role") or "internal"
                    break
        if "src_port" in x:
            s.src_port = x["src_port"].currentText()
        if "dst_port" in x:
            s.dst_port = x["dst_port"].currentText()
        if "price_usd_per_tm" in f:
            v = self._parse_num(f["price_usd_per_tm"].value())
            try:
                s.price_usd_per_tm = float(v) if v else 0.0
            except Exception:
                pass

        # ── Termo ──
        if "temperature" in f:
            v = self._parse_num(f["temperature"].value())
            try:
                s.temperature = float(v) if v else 25.0
                s.temperature_locked = (f["temperature"].state() == "spec")
            except Exception:
                pass
        if "target_temperature" in f:
            sf = f["target_temperature"]
            v = self._parse_num(sf.value())
            try:
                if sf.state() == "spec" and v:
                    s.target_temperature = float(v)
                else:
                    s.target_temperature = -999.0
            except Exception:
                pass
        if "pressure_bar" in f:
            v = self._parse_num(f["pressure_bar"].value())
            try:
                s.pressure_bar = float(v) if v else 1.013
                s.pressure_locked = (f["pressure_bar"].state() == "spec")
            except Exception:
                pass
        if "phase_buttons" in x:
            for b in x["phase_buttons"].buttons():
                if b.isChecked():
                    s.phase = b.property("phase") or ""
                    break
        if "cp" in f:
            v = self._parse_num(f["cp"].value())
            try:
                s.cp = float(v) if v else 0.0
            except Exception:
                pass
        if "delta_h_vap_override" in f:
            v = self._parse_num(f["delta_h_vap_override"].value())
            try:
                s.delta_h_vap_override = float(v) if v else 0.0
            except Exception:
                pass

        # ── Composición ──
        if self._comp_rows:
            comp = {}
            for nm_w, fr_w in self._comp_rows:
                name = (nm_w.text() or "").strip()
                if not name:
                    continue
                try:
                    frac = float((fr_w.text() or "0").replace(",", "."))
                except ValueError:
                    frac = 0.0
                if frac > 0:
                    comp[name] = frac
            s.composition = comp
            if comp:
                s.main_component = max(comp.items(), key=lambda kv: kv[1])[0]
            else:
                s.main_component = ""
        if "composition_lock_cb" in x:
            s.composition_locked = bool(x["composition_lock_cb"].isChecked())

        # ── Hidráulica ──
        if "is_pipe_cb" in x:
            s.is_pipe = bool(x["is_pipe_cb"].isChecked())
        if "pipe_length_m" in f:
            v = self._parse_num(f["pipe_length_m"].value())
            try:
                s.pipe_length_m = float(v) if v else 0.0
            except Exception:
                pass
        if "pipe_diameter_mm" in f:
            v = self._parse_num(f["pipe_diameter_mm"].value())
            try:
                s.pipe_diameter_m = (float(v) / 1000.0) if v else 0.0
            except Exception:
                pass
        if "pipe_roughness_mm" in f:
            v = self._parse_num(f["pipe_roughness_mm"].value())
            try:
                s.pipe_roughness_m = (float(v) / 1000.0) if v else 4.5e-5
            except Exception:
                pass
        if "pipe_K_local" in f:
            v = self._parse_num(f["pipe_K_local"].value())
            try:
                s.pipe_K_local = float(v) if v else 0.0
            except Exception:
                pass

    @staticmethod
    def _parse_num(s_):
        if not s_:
            return ""
        return s_.replace(" ", "").replace(" ", "").replace(",", "")

    def _on_prefs_changed(self):
        """Reload tras un cambio de tema/densidad/acento — preferencia
        global aplicada por block_inspector._PrefsBus.

        Importante: stash de edits in-memory ANTES del reload para no
        perder lo que el usuario tipeó pero no guardó.  El stream es la
        fuente de verdad — load_stream lo re-lee."""
        if self.stream is None or self.fs is None:
            return
        # 1) commit del set actual al stream (preserva edits sin guardar)
        self._stash_current_section()
        # 2) recordar sección activa
        active = self._sidebar.active() or "identidad"
        # 3) reload con las prefs nuevas + on_save y on_cancel preservados
        self.load_stream(self.stream, self.fs,
                         on_save=self._on_save, on_cancel=self._on_cancel)
        try:
            self._sidebar.set_active(active)
            self._switch_section(active)
        except RuntimeError:
            pass   # widgets recién destruidos en reload — esperado
        except Exception as _e:
            print(f"[stream_inspector] reload section restore failed: {_e}")


# ════════════════════════════════════════════════════════
#  DOCK CONTENEDOR
# ════════════════════════════════════════════════════════

class StreamInspectorDock(QDockWidget):
    """QDockWidget slide-out con el StreamInspectorPanel.  Se construye
    una sola vez en FlowsheetMainWindow y se reusa via show_for()."""

    def __init__(self, parent=None):
        super().__init__("Stream Inspector", parent)
        self.setObjectName("StreamInspectorDock")
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetFloatable |
            QDockWidget.DockWidgetClosable
        )
        self.setMinimumWidth(PANEL_W)
        empty_tb = QWidget(self); empty_tb.setFixedHeight(0)
        self.setTitleBarWidget(empty_tb)

        self.panel = StreamInspectorPanel(self)
        self.panel.closeRequested.connect(self.hide)
        self.setWidget(self.panel)
        self.hide()

    def show_for(self, stream, flowsheet,
                 on_save: Optional[Callable] = None,
                 on_cancel: Optional[Callable] = None):
        self.panel.load_stream(stream, flowsheet,
                               on_save=on_save, on_cancel=on_cancel)
        self.show()
        self.raise_()

    def refresh_calc(self):
        """FASE 3.5 — refresca la sección 'Propiedades [calculado]' tras un
        recalc del solver (el stream ya está mutado in-place).  Sólo si esa
        sección está activa: es read-only, así que rebuild no clobbea edits del
        user en las secciones editables."""
        try:
            p = self.panel
            if (self.isVisible() and getattr(p, "stream", None) is not None
                    and p._sidebar.active() == "propiedades"):
                p._build_section_content("propiedades")
        except Exception:
            pass
