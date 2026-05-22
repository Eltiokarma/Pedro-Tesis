"""
BLOCK INSPECTOR — rediseño hi-fi del BlockEditDialog (PySide6).

Reemplaza el QFormLayout plano del antiguo BlockEditDialog por un panel
slide-out con header, streams strip, sidebar contextual, content
scrolleable y footer con live preview de CAPEX/OPEX.

Átomos:
  · SpecField    — input con tres estados (spec / auto / empty)
                   bg azul cobalto, gris cálido o punteado.  Reemplaza
                   el patrón `QLineEdit + QCheckBox(🔒)` del dialog antiguo.
  · StreamPill   — pildora read-only de un stream conectado.
  · StreamsStrip — fila IN → [block] → OUT.
  · ReactionRow  — fila clickable con id, ecuación, ΔH chip, badge confianza.
  · DofIndicator — semáforo de DOF en el bottom del sidebar.

Composición:
  · BlockInspectorPanel — el widget con todo el layout.
  · BlockInspectorDock  — QDockWidget contenedor (slide-out a la derecha
                          del flowsheet, no modal).

El dock se construye una sola vez y se reusa via show_for(block, fs, ...).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QSize, QEvent
from PySide6.QtGui import (
    QColor, QFont, QPalette, QPainter, QPen, QBrush, QFontMetrics,
    QPixmap, QIcon,
)
from PySide6.QtWidgets import (
    QWidget, QDockWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QToolButton, QFrame, QScrollArea,
    QSizePolicy, QSpacerItem, QComboBox, QTextEdit, QMessageBox,
    QButtonGroup, QApplication, QStyle,
)

import pfd_fonts
import equipment_costs as eq

# ════════════════════════════════════════════════════════
#  TOKENS — paleta y dimensiones (claro)
# ════════════════════════════════════════════════════════
# Los nombres replican los del CSS del bundle de diseño para que la
# correspondencia con los mockups sea 1:1.

TOK = {
    # superficies
    "bg":           "#f6f3ec",
    "bg_elev":      "#ffffff",
    "bg_mute":      "#f1ede4",
    "bg_sunk":      "#ece6d8",
    # líneas
    "line":         "#e6e0d0",
    "line_strong":  "#d4ccb8",
    "line_soft":    "#efeadd",
    # tinta
    "ink":          "#1a1714",
    "ink_mute":     "#6b6256",
    "ink_soft":     "#948a7c",
    "ink_ghost":    "#bab2a3",
    # acento
    "accent":       "#0d6e78",
    "accent_deep":  "#064951",
    "accent_soft":  "#d4ebed",
    "accent_tint":  "#eaf4f5",
    # spec field
    "spec":         "#3548b4",
    "spec_ink":     "#2a3a9a",
    "spec_bg":      "#eef1ff",
    "spec_ribbon":  "#4a5dcc",
    # auto field
    "auto_bg":      "#f3efe5",
    "auto_ink":     "#918878",
    "auto_ribbon":  "#c9c0ad",
    # semánticos
    "green":        "#4d8742",
    "green_bg":     "#e6f0df",
    "amber":        "#b8841a",
    "amber_bg":     "#f4ecd1",
    "orange":       "#c26329",
    "orange_bg":    "#f5e1d0",
    "danger":       "#b8453a",
    "danger_bg":    "#f3dcd8",
    # chip de tipo
    "tag_bg":       "#ede7d6",
    "tag_ink":      "#6b6253",
}

ROW_PAD   = 12   # cozy
SECT_GAP  = 22   # cozy
PANEL_W   = 520


# ════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════

def _is_reactor(eq_type: str) -> bool:
    return "Reactor" in (eq_type or "")

def _is_hx(eq_type: str) -> bool:
    try:
        if eq.EQUIPMENT_DATA.get(eq_type, {}).get("categoria") == "Heat exchangers":
            return True
    except Exception:
        pass
    t = (eq_type or "").lower()
    return ("heat exchang" in t or "exchanger" in t or "intercambiador" in t
            or "cooler" in t or "heater" in t or "reboiler" in t
            or "condenser" in t)

def _is_tower(eq_type: str) -> bool:
    return "Tower" in (eq_type or "")

def _is_vessel_flash(eq_type: str) -> bool:
    t = (eq_type or "").lower()
    return "vessel" in t or "tanque" in t or "flash" in t

def _is_pump_compressor(eq_type: str) -> bool:
    t = (eq_type or "").lower()
    return "pump" in t or "compress" in t or "bomba" in t or "compresor" in t

def _is_mixer(eq_type: str) -> bool:
    t = (eq_type or "").lower()
    return "mixer" in t or "mezclador" in t

def _type_short(eq_type: str) -> str:
    """Etiqueta corta tipo 'REACTOR', 'HX', 'PUMP' para el chip del header."""
    if _is_reactor(eq_type):      return "REACTOR"
    if _is_tower(eq_type):        return "COLUMN"
    if _is_hx(eq_type):           return "HX"
    if _is_pump_compressor(eq_type): return "PUMP"
    if _is_vessel_flash(eq_type): return "FLASH"
    if _is_mixer(eq_type):        return "MIXER"
    return "BLOCK"


def _sections_for(eq_type: str) -> List[str]:
    """Devuelve qué secciones aplican a este tipo de bloque."""
    secs = ["identidad", "termo"]
    if _is_reactor(eq_type):
        secs.append("reactividad")
    if _is_tower(eq_type):
        secs.append("columna")
    secs.append("sizing")
    secs.append("utility")
    secs.append("economia")
    return secs


# ════════════════════════════════════════════════════════
#  ÁTOMOS — SpecField, StreamPill, ReactionRow, etc.
# ════════════════════════════════════════════════════════

class SpecField(QFrame):
    """Campo numérico con tres estados: spec / auto / empty.

    Reemplaza el patrón `QLineEdit + QCheckBox(🔒)` del dialog antiguo.

    Layout horizontal:
      [ribbon 4px] [input (transparent)] [unit label] [toggle "spec/auto"]

    Estados:
      · spec   — bg azul, ribbon azul, texto mono normal.  Editable.
      · auto   — bg crema, ribbon cálido, texto mono italic.  Read-only.
      · empty  — bg transparente con borde punteado, placeholder "—".

    Señales:
      · valueChanged(str) — texto cambió (solo cuando el field está activo).
      · stateChanged(str) — usuario alternó spec/auto vía el toggle.
    """

    valueChanged = Signal(str)
    stateChanged = Signal(str)   # "spec" o "auto"

    def __init__(self, value: str = "", unit: str = "",
                 state: str = "spec", parent=None,
                 placeholder: str = "—", allow_toggle: bool = True):
        super().__init__(parent)
        self._state = state
        self._unit  = unit
        self._allow_toggle = allow_toggle
        self.setObjectName("specField")
        self.setFixedHeight(34)
        self.setFrameShape(QFrame.NoFrame)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ribbon
        self._ribbon = QFrame(self)
        self._ribbon.setFixedWidth(4)
        self._ribbon.setObjectName("specRibbon")
        lay.addWidget(self._ribbon)

        # input
        self._input = QLineEdit(self)
        self._input.setObjectName("specInput")
        self._input.setFrame(False)
        f = QFont(pfd_fonts.MONO, 10)
        self._input.setFont(f)
        self._input.setPlaceholderText(placeholder)
        self._input.textEdited.connect(self._on_edited)
        self._input.setText(str(value) if value is not None else "")
        lay.addWidget(self._input, 1)

        # unit
        self._unit_lbl = QLabel(unit, self)
        self._unit_lbl.setObjectName("specUnit")
        self._unit_lbl.setContentsMargins(2, 0, 6, 0)
        uf = QFont(pfd_fonts.MONO, 9)
        self._unit_lbl.setFont(uf)
        lay.addWidget(self._unit_lbl)

        # toggle
        self._toggle = QToolButton(self)
        self._toggle.setObjectName("specToggle")
        self._toggle.setText("spec")
        self._toggle.setCursor(Qt.PointingHandCursor)
        tf = QFont(pfd_fonts.SANS, 8)
        tf.setBold(True)
        self._toggle.setFont(tf)
        self._toggle.setFixedHeight(20)
        self._toggle.clicked.connect(self._on_toggle_clicked)
        lay.addWidget(self._toggle)
        lay.addSpacing(4)

        self._apply_state_style()

    # ---- API pública ----
    def value(self) -> str:
        return self._input.text().strip()

    def setValue(self, v):
        self._input.setText("" if v is None else str(v))

    def state(self) -> str:
        return self._state

    def setState(self, st: str):
        self._state = st
        self._apply_state_style()

    def setAllowToggle(self, flag: bool):
        self._allow_toggle = flag
        self._toggle.setEnabled(flag)
        self._apply_state_style()

    # ---- internals ----
    def _on_toggle_clicked(self):
        if not self._allow_toggle:
            return
        new = "auto" if self._state == "spec" else "spec"
        self.setState(new)
        self.stateChanged.emit(new)

    def _on_edited(self, txt: str):
        # Promueve auto/empty → spec en cuanto el usuario escribe.
        if self._state in ("auto", "empty") and txt.strip():
            self.setState("spec")
            self.stateChanged.emit("spec")
        self.valueChanged.emit(txt)

    def _apply_state_style(self):
        s = self._state
        if s == "spec":
            bg, rib, ink = TOK["spec_bg"], TOK["spec_ribbon"], TOK["spec_ink"]
            italic, ro = False, False
            toggle_text = "spec"
            border = TOK["line_strong"]
        elif s == "auto":
            bg, rib, ink = TOK["auto_bg"], TOK["auto_ribbon"], TOK["auto_ink"]
            italic, ro = True, True
            toggle_text = "auto"
            border = TOK["line_strong"]
        else:  # empty
            bg, rib, ink = "transparent", "transparent", TOK["ink_ghost"]
            italic, ro = True, False
            toggle_text = "auto"
            border = TOK["line"]

        self.setStyleSheet(f"""
            #specField {{
                background: {bg};
                border: 1px {"dashed" if s == "empty" else "solid"} {border};
                border-radius: 7px;
            }}
            #specRibbon {{
                background: {rib};
                border-top-left-radius: 6px;
                border-bottom-left-radius: 6px;
            }}
            #specInput {{
                background: transparent;
                color: {ink};
                font-style: {"italic" if italic else "normal"};
                padding: 0 6px;
                selection-background-color: {TOK["accent_soft"]};
            }}
            #specUnit {{
                color: {TOK["ink_soft"]};
            }}
            #specToggle {{
                background: rgba(255,255,255,0.5);
                color: {TOK["ink_mute"]};
                border: 1px solid {TOK["line"]};
                border-radius: 4px;
                padding: 1px 6px;
                margin: 4px;
            }}
            #specToggle:hover {{
                background: {TOK["bg_elev"]};
                color: {TOK["accent_deep"]};
            }}
        """)
        self._input.setReadOnly(ro)
        self._toggle.setText(toggle_text)


class StreamPill(QFrame):
    """Pildora read-only de un stream conectado (dot, nombre, fase, meta)."""

    doubleClicked = Signal()

    def __init__(self, name: str, phase: str, T: float, P: float, mdot: float,
                 direction: str = "in", parent=None):
        super().__init__(parent)
        self._direction = direction
        self.setObjectName("streamPill")
        self.setCursor(Qt.PointingHandCursor)

        lay = QGridLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setHorizontalSpacing(6)
        lay.setVerticalSpacing(1)

        # dot (color por dirección)
        dot = QLabel(self)
        dot.setFixedSize(8, 8)
        dot_color = TOK["accent"] if direction == "in" else TOK["orange"]
        dot.setStyleSheet(f"background:{dot_color}; border-radius:4px;")
        lay.addWidget(dot, 0, 0)

        # nombre stream (mono)
        nm = QLabel(name, self)
        nf = QFont(pfd_fonts.MONO, 9)
        nf.setBold(True)
        nm.setFont(nf)
        nm.setStyleSheet(f"color:{TOK['ink']};")
        lay.addWidget(nm, 0, 1)

        # phase chip
        ph = QLabel(phase.upper() if phase else "?", self)
        pf = QFont(pfd_fonts.SANS, 7)
        pf.setBold(True)
        ph.setFont(pf)
        ph.setAlignment(Qt.AlignCenter)
        ph.setStyleSheet(
            f"background:{TOK['bg_sunk']}; color:{TOK['ink_mute']}; "
            f"border-radius:3px; padding:0 5px;"
        )
        lay.addWidget(ph, 0, 2, alignment=Qt.AlignLeft)
        lay.setColumnStretch(3, 1)

        # meta row
        meta = QLabel(self)
        meta.setTextFormat(Qt.RichText)
        soft = TOK["ink_soft"]; ink = TOK["ink_mute"]
        T_s = f"{T:.1f}" if T else "—"
        P_s = f"{P:.1f}" if P else "—"
        m_s = f"{mdot:.2f}" if mdot else "—"
        meta.setText(
            f'<span style="color:{soft};font-size:9px;">T</span> '
            f'<b style="color:{ink};font-size:10px;font-family:\'{pfd_fonts.MONO}\';">{T_s}</b>'
            f'<span style="color:{soft};font-size:9px;"> K · </span>'
            f'<span style="color:{soft};font-size:9px;">P</span> '
            f'<b style="color:{ink};font-size:10px;font-family:\'{pfd_fonts.MONO}\';">{P_s}</b>'
            f'<span style="color:{soft};font-size:9px;"> bar · </span>'
            f'<span style="color:{soft};font-size:9px;">ṁ</span> '
            f'<b style="color:{ink};font-size:10px;font-family:\'{pfd_fonts.MONO}\';">{m_s}</b>'
            f'<span style="color:{soft};font-size:9px;"> kg/s</span>'
        )
        lay.addWidget(meta, 1, 0, 1, 4)

        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(f"""
            #streamPill {{
                background: {TOK["bg_elev"]};
                border: 1px solid {TOK["line"]};
                border-radius: 7px;
            }}
            #streamPill:hover {{
                border: 1.5px solid {TOK["accent_soft"]};
                background: {TOK["accent_tint"]};
            }}
        """)

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(e)


class ConfidenceBadge(QLabel):
    """Badge ALTA/MEDIA/BAJA/N/A con dot + texto (sin emoji)."""

    PALETTE = {
        "alta":  (TOK["green"],  TOK["green_bg"],  "ALTA"),
        "media": (TOK["amber"],  TOK["amber_bg"],  "MEDIA"),
        "baja":  (TOK["orange"], TOK["orange_bg"], "BAJA"),
        "na":    (TOK["ink_soft"], TOK["bg_mute"], "N/A"),
    }

    def __init__(self, level: str, parent=None):
        super().__init__(parent)
        ink, bg, label = self.PALETTE.get(level, self.PALETTE["na"])
        f = QFont(pfd_fonts.SANS, 7)
        f.setBold(True)
        self.setFont(f)
        self.setText(f"●  {label}")
        self.setStyleSheet(
            f"background:{bg}; color:{ink}; "
            f"border-radius:4px; padding:2px 6px;"
        )


class ReactionRow(QFrame):
    """Fila clickable con check + ecuación + ΔH chip + confianza."""

    toggled = Signal(bool)

    def __init__(self, rxn_id: str, equation: str, name: str,
                 confidence: str, dh: Optional[float],
                 active: bool = False, applicable: bool = True,
                 parent=None):
        super().__init__(parent)
        self._on = bool(active)
        self._applicable = applicable
        self.setObjectName("rxnRow")
        self.setCursor(Qt.PointingHandCursor if applicable else Qt.ArrowCursor)
        self.setMinimumHeight(52)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)

        # check
        self._check = QLabel(self)
        self._check.setFixedSize(18, 18)
        self._check.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._check)

        # main col (id + eq)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        idn = QLabel(f"{rxn_id} · {name}", self)
        idn.setFont(QFont(pfd_fonts.MONO, 8))
        idn.setStyleSheet(f"color:{TOK['ink_soft']};")
        idn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        col.addWidget(idn)
        eq_lbl = QLabel(equation, self)
        eq_lbl.setFont(QFont(pfd_fonts.MONO, 9))
        eq_lbl.setStyleSheet(f"color:{TOK['ink']};")
        eq_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        col.addWidget(eq_lbl)
        lay.addLayout(col, 1)

        # right col (ΔH chip + badge) — ancho mínimo fijo para que no se clipee
        rwrap = QFrame(self)
        rwrap.setMinimumWidth(96)
        rcol = QVBoxLayout(rwrap)
        rcol.setContentsMargins(0, 0, 0, 0)
        rcol.setSpacing(4)
        rcol.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if dh is not None:
            kind_color = TOK["orange"] if dh < 0 else TOK["spec"]
            sign = "+" if dh > 0 else ""
            dh_lbl = QLabel(f"ΔH {sign}{dh:.0f}", self)
            dh_lbl.setFont(QFont(pfd_fonts.MONO, 8))
            dh_lbl.setStyleSheet(f"color:{kind_color};")
            dh_lbl.setAlignment(Qt.AlignRight)
            rcol.addWidget(dh_lbl)
        rcol.addWidget(ConfidenceBadge(confidence, self),
                       alignment=Qt.AlignRight)
        lay.addWidget(rwrap)

        self._refresh()

    def isOn(self) -> bool:
        return self._on

    def mousePressEvent(self, e):
        if self._applicable and e.button() == Qt.LeftButton:
            self._on = not self._on
            self._refresh()
            self.toggled.emit(self._on)
        super().mousePressEvent(e)

    def _refresh(self):
        if not self._applicable:
            self.setStyleSheet(
                f"#rxnRow {{ background: transparent; border: 1px solid {TOK['line']}; "
                f"border-radius: 7px; }} #rxnRow * {{ color: {TOK['ink_ghost']}; }}"
            )
            self._check.setText("")
            self._check.setStyleSheet("")
            return
        if self._on:
            self.setStyleSheet(
                f"#rxnRow {{ background: {TOK['bg_elev']}; "
                f"border: 1px solid {TOK['accent_soft']}; border-left: 3px solid {TOK['accent']}; "
                f"border-radius: 7px; }}"
            )
            self._check.setText("✓")
            self._check.setFont(QFont(pfd_fonts.SANS, 11, QFont.Bold))
            self._check.setStyleSheet(
                f"background:{TOK['accent']}; color:white; border-radius:9px;"
            )
        else:
            self.setStyleSheet(
                f"#rxnRow {{ background: transparent; "
                f"border: 1px solid {TOK['line']}; border-radius: 7px; }}"
                f"#rxnRow:hover {{ background: {TOK['bg_mute']}; }}"
            )
            self._check.setText("")
            self._check.setStyleSheet(
                f"background:transparent; border:1.5px solid {TOK['ink_ghost']}; "
                f"border-radius:9px;"
            )


# ════════════════════════════════════════════════════════
#  PIEZAS COMPUESTAS — Header, StreamsStrip, Sidebar
# ════════════════════════════════════════════════════════

class _InspectorHeader(QFrame):
    """Header: icon + tag editable + chip de tipo + descripción + kebab + close."""

    closeRequested = Signal()
    tagChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("insHeader")
        self.setFixedHeight(64)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 12, 12)
        lay.setSpacing(10)

        self._icon = QLabel(self)
        self._icon.setFixedSize(36, 36)
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet(
            f"background:{TOK['accent_tint']}; color:{TOK['accent']}; "
            f"border-radius:9px; border:1px solid {TOK['accent_soft']};"
        )
        f = QFont(pfd_fonts.SANS, 13, QFont.Bold)
        self._icon.setFont(f)
        lay.addWidget(self._icon)

        # titles col
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        self._tag = QLineEdit(self)
        self._tag.setFrame(False)
        tf = QFont(pfd_fonts.MONO, 14)
        tf.setWeight(QFont.Medium)
        self._tag.setFont(tf)
        self._tag.setStyleSheet(
            f"QLineEdit {{ background: transparent; color: {TOK['ink']}; "
            f"padding: 1px 4px; border-radius: 4px; }} "
            f"QLineEdit:hover {{ background: {TOK['bg_mute']}; }} "
            f"QLineEdit:focus {{ background: {TOK['bg_mute']}; "
            f"border: 1px solid {TOK['accent']}; }}"
        )
        self._tag.editingFinished.connect(
            lambda: self.tagChanged.emit(self._tag.text().strip())
        )
        col.addWidget(self._tag)

        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(4, 0, 0, 0)
        sub_row.setSpacing(6)
        self._chip = QLabel(self)
        cf = QFont(pfd_fonts.SANS, 8)
        cf.setBold(True)
        self._chip.setFont(cf)
        self._chip.setStyleSheet(
            f"background:{TOK['tag_bg']}; color:{TOK['tag_ink']}; "
            f"padding:1px 7px; border-radius:4px; letter-spacing:1px;"
        )
        sub_row.addWidget(self._chip)
        dot = QLabel("·", self); dot.setStyleSheet(f"color:{TOK['ink_soft']};")
        sub_row.addWidget(dot)
        self._desc = QLabel(self)
        df = QFont(pfd_fonts.SANS, 9)
        self._desc.setFont(df)
        self._desc.setStyleSheet(f"color:{TOK['ink_mute']};")
        sub_row.addWidget(self._desc, 1)
        col.addLayout(sub_row)
        lay.addLayout(col, 1)

        # actions
        self._close_btn = QToolButton(self)
        self._close_btn.setText("✕")
        self._close_btn.setFixedSize(28, 28)
        self._close_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; color: {TOK['ink_mute']}; "
            f"border: 0; border-radius: 6px; font-size: 14px; }} "
            f"QToolButton:hover {{ background: {TOK['danger_bg']}; "
            f"color: {TOK['danger']}; }}"
        )
        self._close_btn.clicked.connect(self.closeRequested.emit)
        lay.addWidget(self._close_btn)

        self.setStyleSheet(
            f"#insHeader {{ background: {TOK['bg_elev']}; "
            f"border-bottom: 1px solid {TOK['line']}; }}"
        )

    def setBlock(self, tag: str, type_short: str, description: str, icon_letter: str):
        self._tag.setText(tag)
        self._chip.setText(type_short)
        self._desc.setText(description)
        self._icon.setText(icon_letter)

    def tag(self) -> str:
        return self._tag.text().strip()


class _StreamsStrip(QFrame):
    """Fila IN → [block square] → OUT."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("insStreams")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(14, 10, 14, 10)
        self._lay.setSpacing(8)
        self.setStyleSheet(
            f"#insStreams {{ background: {TOK['bg_mute']}; "
            f"border-bottom: 1px solid {TOK['line']}; }}"
        )

    def populate(self, streams_in, streams_out, block_tag: str):
        # limpiar — recursivo para layouts anidados
        def _clear_layout(lay):
            while lay.count():
                it = lay.takeAt(0)
                w = it.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
                else:
                    inner = it.layout()
                    if inner is not None:
                        _clear_layout(inner)
        _clear_layout(self._lay)

        # col entradas
        col_in = QVBoxLayout(); col_in.setSpacing(4)
        lbl_in = QLabel(f"ENTRADAS · {len(streams_in)}")
        lbl_in.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
        lbl_in.setStyleSheet(
            f"color:{TOK['ink_soft']}; letter-spacing:1.5px;"
        )
        col_in.addWidget(lbl_in)
        if not streams_in:
            empty = QLabel("(sin entradas)"); empty.setStyleSheet(
                f"color:{TOK['ink_ghost']}; font-style:italic; font-size:9pt;")
            col_in.addWidget(empty)
        for s in streams_in:
            pill = StreamPill(
                s.get("name", "?"), s.get("phase", ""),
                s.get("T", 0.0), s.get("P", 0.0), s.get("mdot", 0.0),
                direction="in",
            )
            col_in.addWidget(pill)
        col_in.addStretch(1)
        self._lay.addLayout(col_in, 1)

        # centro: block square con flechas
        mid = QVBoxLayout(); mid.setSpacing(2); mid.setAlignment(Qt.AlignCenter)
        arrow_up = QLabel("→"); arrow_up.setAlignment(Qt.AlignCenter)
        arrow_up.setStyleSheet(f"color:{TOK['ink_soft']}; font-size:14px;")
        sq = QLabel(block_tag)
        sq.setFixedSize(56, 56); sq.setAlignment(Qt.AlignCenter)
        sq.setFont(QFont(pfd_fonts.MONO, 10, QFont.Bold))
        sq.setStyleSheet(
            f"background:{TOK['accent']}; color:white; "
            f"border-radius:10px;"
        )
        mid.addStretch(1)
        mid.addWidget(sq, alignment=Qt.AlignCenter)
        mid.addStretch(1)
        self._lay.addLayout(mid)

        # col salidas
        col_out = QVBoxLayout(); col_out.setSpacing(4)
        lbl_out = QLabel(f"SALIDAS · {len(streams_out)}")
        lbl_out.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
        lbl_out.setStyleSheet(
            f"color:{TOK['ink_soft']}; letter-spacing:1.5px;"
        )
        col_out.addWidget(lbl_out)
        if not streams_out:
            empty = QLabel("(sin salidas)"); empty.setStyleSheet(
                f"color:{TOK['ink_ghost']}; font-style:italic; font-size:9pt;")
            col_out.addWidget(empty)
        for s in streams_out:
            pill = StreamPill(
                s.get("name", "?"), s.get("phase", ""),
                s.get("T", 0.0), s.get("P", 0.0), s.get("mdot", 0.0),
                direction="out",
            )
            col_out.addWidget(pill)
        col_out.addStretch(1)
        self._lay.addLayout(col_out, 1)


class _InspectorSidebar(QFrame):
    """Sidebar contextual con secciones + DOF indicator al fondo."""

    sectionChanged = Signal(str)

    SECTION_LABEL = {
        "identidad":   "Identidad",
        "termo":       "Termodinámica",
        "reactividad": "Reactividad",
        "columna":     "Etapas y reflujo",
        "sizing":      "Sizing",
        "utility":     "Utility",
        "economia":    "Economía",
    }
    SECTION_ICON = {
        "identidad":   "T",
        "termo":       "θ",
        "reactividad": "R",
        "columna":     "≡",
        "sizing":      "□",
        "utility":     "♨",
        "economia":    "$",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("insSidebar")
        self.setFixedWidth(168)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 12, 8, 12)
        self._lay.setSpacing(2)

        self._items: Dict[str, QPushButton] = {}
        self._badges: Dict[str, QLabel] = {}
        self._active: Optional[str] = None

        self._lay.addStretch(1)
        self._dof = QFrame(self)
        self._dof.setObjectName("dofRow")
        df_lay = QHBoxLayout(self._dof)
        df_lay.setContentsMargins(8, 8, 8, 8); df_lay.setSpacing(6)
        self._dof_dot = QLabel(self._dof); self._dof_dot.setFixedSize(8, 8)
        self._dof_text = QLabel("Sistema determinado", self._dof)
        self._dof_text.setFont(QFont(pfd_fonts.SANS, 8))
        df_lay.addWidget(self._dof_dot)
        df_lay.addWidget(self._dof_text, 1)
        self._lay.addWidget(self._dof)
        self.set_dof("ok", 0)

        self.setStyleSheet(
            f"#insSidebar {{ background: {TOK['bg_mute']}; "
            f"border-right: 1px solid {TOK['line']}; }}"
        )

    def set_sections(self, sections: List[str], active: Optional[str] = None):
        # clear existing buttons (preserve stretch + dof)
        for key, btn in list(self._items.items()):
            self._lay.removeWidget(btn)
            btn.setParent(None)
            btn.deleteLater()
        self._items.clear()
        self._badges.clear()

        for i, key in enumerate(sections):
            row = QFrame(self)
            row.setObjectName(f"navItem_{key}")
            rlay = QHBoxLayout(row); rlay.setContentsMargins(8, 6, 8, 6)
            rlay.setSpacing(8)

            ico = QLabel(self.SECTION_ICON.get(key, "•"), row)
            ico.setFixedWidth(14); ico.setAlignment(Qt.AlignCenter)
            ico.setFont(QFont(pfd_fonts.MONO, 10, QFont.Bold))
            ico.setStyleSheet(f"color:{TOK['ink_mute']};")
            rlay.addWidget(ico)
            lbl = QLabel(self.SECTION_LABEL.get(key, key), row)
            lbl.setFont(QFont(pfd_fonts.SANS, 9))
            lbl.setStyleSheet(f"color:{TOK['ink']};")
            rlay.addWidget(lbl, 1)
            badge = QLabel("", row)
            badge.setFont(QFont(pfd_fonts.MONO, 7, QFont.Bold))
            badge.setStyleSheet(
                f"color:{TOK['ink_soft']}; background:{TOK['bg_sunk']}; "
                f"border-radius:8px; padding:1px 6px;"
            )
            badge.setVisible(False)
            rlay.addWidget(badge)
            self._badges[key] = badge

            row.setCursor(Qt.PointingHandCursor)
            row.mousePressEvent = (lambda ev, k=key: self._on_click(k))
            # store button-like reference
            self._items[key] = row
            # insert above the stretch (index = i)
            self._lay.insertWidget(i, row)

        self._refresh_styles()
        if active and active in sections:
            self._active = active
        elif sections:
            self._active = sections[0]
        self._refresh_styles()

    def _on_click(self, key: str):
        if self._active == key:
            return
        self._active = key
        self._refresh_styles()
        self.sectionChanged.emit(key)

    def active(self) -> Optional[str]:
        return self._active

    def set_badge(self, key: str, text: str):
        b = self._badges.get(key)
        if not b: return
        if text:
            b.setText(text); b.setVisible(True)
        else:
            b.setVisible(False)

    def set_dof(self, state: str, n: int):
        if state == "ok":
            color = TOK["green"]; bg = TOK["green_bg"]
            text = "Sistema <b>determinado</b>"
        elif state == "warn":
            color = TOK["amber"]; bg = TOK["amber_bg"]
            text = f"<b>{n}</b> grado{'s' if abs(n)!=1 else ''} libre{'s' if abs(n)!=1 else ''}"
        else:
            color = TOK["danger"]; bg = TOK["danger_bg"]
            text = f"<b>{abs(n)}</b> sobre-especificado"
        self._dof.setStyleSheet(
            f"#dofRow {{ background: {bg}; border-radius: 7px; }}"
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
                    f"QFrame#navItem_{key} {{ background: {TOK['bg_elev']}; "
                    f"border-left: 2.5px solid {TOK['accent']}; "
                    f"border-radius: 6px; }}"
                )
            else:
                row.setStyleSheet(
                    f"QFrame#navItem_{key} {{ background: transparent; "
                    f"border-radius: 6px; }} "
                    f"QFrame#navItem_{key}:hover {{ background: {TOK['bg_sunk']}; }}"
                )


# ════════════════════════════════════════════════════════
#  PANEL PRINCIPAL — BlockInspectorPanel
# ════════════════════════════════════════════════════════

class BlockInspectorPanel(QWidget):
    """Panel completo: header + streams + sidebar + content + footer.

    No es modal. Se popula con un Block via load_block(block, fs, on_save_cb).
    Al pulsar "Guardar cambios" persiste todos los specs al Block y llama
    a on_save_cb() para que el FlowsheetMainWindow refresque y solverize.
    """

    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.block = None
        self.fs = None
        self._on_save = None
        self._fields: Dict[str, SpecField] = {}
        self._extras: Dict[str, object] = {}   # widgets no-SpecField
        self._reaction_rows: List[Tuple[str, ReactionRow]] = []
        self._open_advanced_cb: Optional[Callable] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        self._header = _InspectorHeader(self)
        self._header.closeRequested.connect(self.closeRequested.emit)
        outer.addWidget(self._header)

        self._streams = _StreamsStrip(self)
        outer.addWidget(self._streams)

        body = QFrame(self); body.setObjectName("insBody")
        body.setStyleSheet(f"#insBody {{ background:{TOK['bg_elev']}; }}")
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0); body_lay.setSpacing(0)
        self._sidebar = _InspectorSidebar(self)
        self._sidebar.sectionChanged.connect(self._switch_section)
        body_lay.addWidget(self._sidebar)
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
        body_lay.addWidget(self._content_scroll, 1)
        outer.addWidget(body, 1)

        self._footer = self._build_footer()
        outer.addWidget(self._footer)

        self.setStyleSheet(
            self.styleSheet() +
            f"QWidget {{ font-family: '{pfd_fonts.SANS}'; color: {TOK['ink']}; }}"
        )

    # ---- footer ----
    def _build_footer(self) -> QFrame:
        ft = QFrame(self); ft.setObjectName("insFooter")
        ft.setFixedHeight(58)
        lay = QHBoxLayout(ft)
        lay.setContentsMargins(20, 8, 14, 8); lay.setSpacing(20)

        # stats
        self._stat_capex_lbl = QLabel("CAPEX (CBM)")
        self._stat_capex_val = QLabel("—")
        self._stat_opex_lbl  = QLabel("OPEX")
        self._stat_opex_val  = QLabel("—")
        self._stat_conv_lbl  = QLabel("Conv.")
        self._stat_conv_val  = QLabel("—")

        for caps, val in [
            (self._stat_capex_lbl, self._stat_capex_val),
            (self._stat_opex_lbl,  self._stat_opex_val),
            (self._stat_conv_lbl,  self._stat_conv_val),
        ]:
            col = QVBoxLayout(); col.setContentsMargins(0,0,0,0); col.setSpacing(1)
            caps.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
            caps.setStyleSheet(
                f"color:{TOK['ink_soft']}; letter-spacing:1px;"
            )
            val.setFont(QFont(pfd_fonts.MONO, 11, QFont.Bold))
            val.setStyleSheet(f"color:{TOK['ink']};")
            col.addWidget(caps); col.addWidget(val)
            lay.addLayout(col)
        lay.addStretch(1)

        # cancel
        self._cancel_btn = QPushButton("Cancelar")
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TOK['ink_mute']}; "
            f"border: 1px solid {TOK['line']}; border-radius: 6px; "
            f"padding: 6px 14px; }} "
            f"QPushButton:hover {{ background: {TOK['bg_mute']}; }}"
        )
        self._cancel_btn.clicked.connect(self.closeRequested.emit)
        lay.addWidget(self._cancel_btn)

        # save
        self._save_btn = QPushButton("Guardar cambios")
        self._save_btn.setCursor(Qt.PointingHandCursor)
        sf = QFont(pfd_fonts.SANS, 9, QFont.Bold)
        self._save_btn.setFont(sf)
        self._save_btn.setStyleSheet(
            f"QPushButton {{ background: {TOK['accent']}; color: white; "
            f"border: 0; border-radius: 6px; padding: 7px 16px; }} "
            f"QPushButton:hover {{ background: {TOK['accent_deep']}; }}"
        )
        self._save_btn.clicked.connect(self._do_save)
        lay.addWidget(self._save_btn)

        ft.setStyleSheet(
            f"#insFooter {{ background: {TOK['bg_mute']}; "
            f"border-top: 1px solid {TOK['line']}; }}"
        )
        return ft

    # ─── API pública ─────────────────────────────────────
    def load_block(self, block, flowsheet, on_save: Optional[Callable] = None,
                   open_advanced: Optional[Callable] = None):
        """Carga un Block en el panel. on_save() se invoca tras un Guardar OK."""
        self.block = block
        self.fs = flowsheet
        self._on_save = on_save
        self._open_advanced_cb = open_advanced
        self._fields.clear()
        self._extras.clear()
        self._reaction_rows.clear()

        eq_type = block.eq_type
        type_short = _type_short(eq_type)
        # icon letter: la primera del type_short
        icon_letter = type_short[:1]
        self._header.setBlock(
            tag=block.name,
            type_short=type_short,
            description=eq_type,
            icon_letter=icon_letter,
        )

        # streams strip — proyección read-only desde el flowsheet
        self._streams.populate(
            self._projected_streams_in(),
            self._projected_streams_out(),
            block_tag=block.name,
        )

        sections = _sections_for(eq_type)
        self._sidebar.set_sections(sections, active="identidad")
        self._build_section_content("identidad")
        self._update_footer()
        self._update_dof_badges()

    def _iter_streams(self):
        """Itera sobre los Stream del flowsheet (acepta dict o list)."""
        st = getattr(self.fs, "streams", None) if self.fs else None
        if st is None:
            return []
        if isinstance(st, dict):
            return st.values()
        return st

    def _projected_streams_in(self) -> List[dict]:
        if not self.fs or not self.block:
            return []
        out = []
        for s in self._iter_streams():
            if getattr(s, "dst", None) == self.block.id:
                out.append(self._stream_dict(s))
        return out

    def _projected_streams_out(self) -> List[dict]:
        if not self.fs or not self.block:
            return []
        out = []
        for s in self._iter_streams():
            if getattr(s, "src", None) == self.block.id:
                out.append(self._stream_dict(s))
        return out

    @staticmethod
    def _stream_dict(s) -> dict:
        # Convertimos a la proyección que espera StreamPill (T en K,
        # P en bar, mdot en kg/s). El modelo guarda T en °C y mass_flow
        # en tm/año; convertimos aquí para mostrar en unidades de proceso.
        T_C = float(getattr(s, "temperature", 0.0) or 0.0)
        T_K = T_C + 273.15
        P_bar = float(getattr(s, "pressure_bar", 0.0) or 0.0)
        # mass_flow en tm/año → kg/s
        tm_yr = float(getattr(s, "mass_flow", 0.0) or 0.0)
        mdot_kg_s = (tm_yr * 1000.0) / (8760.0 * 3600.0) if tm_yr > 0 else 0.0
        phase = getattr(s, "phase", "") or ""
        phase_short = {"liquid": "liq", "vapor": "vap", "gas": "gas",
                       "two_phase": "2ph"}.get(phase, phase[:3] if phase else "")
        return {
            "name":  getattr(s, "name", "?") or "?",
            "phase": phase_short,
            "T":     T_K,
            "P":     P_bar,
            "mdot":  mdot_kg_s,
        }

    # ─── Construcción de secciones ───────────────────────
    def _switch_section(self, key: str):
        # mantener sidebar y content en sync (caller puede ser programático)
        if self._sidebar.active() != key:
            self._sidebar._active = key
            self._sidebar._refresh_styles()
        self._build_section_content(key)

    def _clear_content(self):
        # quita todo menos el stretch final
        while self._content_lay.count() > 1:
            item = self._content_lay.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _section_header(self, title: str, sub: str = "", help_text: str = ""):
        wrap = QVBoxLayout(); wrap.setContentsMargins(0, 0, 0, 0); wrap.setSpacing(4)
        hd = QHBoxLayout(); hd.setContentsMargins(0, 0, 0, 0); hd.setSpacing(8)
        tl = QLabel(title); tl.setFont(QFont(pfd_fonts.SANS, 11, QFont.Bold))
        tl.setStyleSheet(f"color:{TOK['ink']};")
        hd.addWidget(tl)
        if sub:
            sb = QLabel(sub); sb.setFont(QFont(pfd_fonts.SANS, 8))
            sb.setStyleSheet(f"color:{TOK['ink_soft']};")
            hd.addWidget(sb)
        hd.addStretch(1)
        wrap.addLayout(hd)
        if help_text:
            ht = QLabel(help_text); ht.setWordWrap(True)
            ht.setFont(QFont(pfd_fonts.SANS, 8))
            ht.setStyleSheet(f"color:{TOK['ink_mute']}; line-height: 1.4em;")
            wrap.addWidget(ht)
        return wrap

    def _row(self, label: str, control, info: str = "") -> QFrame:
        r = QFrame(); r.setObjectName("insRow")
        lay = QHBoxLayout(r); lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        l = QLabel(label); l.setFont(QFont(pfd_fonts.SANS, 9))
        l.setStyleSheet(f"color:{TOK['ink_mute']};")
        l.setMinimumWidth(140)
        if info:
            l.setToolTip(info)
        lay.addWidget(l)
        lay.addWidget(control, 1)
        r.setStyleSheet(
            f"#insRow {{ padding: 2px 0; "
            f"border-bottom: 1px solid {TOK['line_soft']}; }}"
        )
        # add padding via fixed margin in layout instead of stylesheet padding
        lay.setContentsMargins(0, ROW_PAD//2, 0, ROW_PAD//2)
        return r

    def _spec_field(self, key: str, value, unit: str = "",
                    state: str = "spec", allow_toggle: bool = True) -> SpecField:
        sf = SpecField(value=value, unit=unit, state=state,
                       allow_toggle=allow_toggle)
        self._fields[key] = sf
        return sf

    def _build_section_content(self, key: str):
        self._clear_content()
        # los SpecField/extras del set anterior se eliminaron; limpiar refs
        self._fields.clear()
        self._extras.clear()
        self._reaction_rows.clear()
        b = self.block
        if b is None:
            return
        eq_type = b.eq_type

        builders = {
            "identidad":   self._section_identidad,
            "termo":       self._section_termo,
            "reactividad": self._section_reactividad,
            "columna":     self._section_columna,
            "sizing":      self._section_sizing,
            "utility":     self._section_utility,
            "economia":    self._section_economia,
        }
        fn = builders.get(key)
        if fn:
            sect = fn(b, eq_type)
            self._content_lay.insertWidget(self._content_lay.count() - 1, sect)

        # Avanzado (siempre disponible — abre el dialog legacy para
        # opciones de nicho aún no migradas: custom rxns, FUG columna,
        # separadores mecánicos, batch).
        if self._open_advanced_cb:
            adv = self._build_advanced_link()
            self._content_lay.insertWidget(self._content_lay.count() - 1, adv)

        # asegurar que el scroll empieza arriba al cambiar de sección
        # (defer un tick para que el layout calcule range primero)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._content_scroll.verticalScrollBar().setValue(0))

    def _build_advanced_link(self) -> QFrame:
        f = QFrame(); f.setObjectName("advLink")
        lay = QHBoxLayout(f); lay.setContentsMargins(0, 8, 0, 4)
        btn = QPushButton("Opciones avanzadas…")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TOK['accent']}; "
            f"border: 0; padding: 4px 0; text-align: left; }} "
            f"QPushButton:hover {{ color: {TOK['accent_deep']}; text-decoration: underline; }}"
        )
        btn.clicked.connect(self._do_open_advanced)
        lay.addWidget(btn); lay.addStretch(1)
        return f

    def _do_open_advanced(self):
        if self._open_advanced_cb:
            self._open_advanced_cb(self.block)

    # ─── SECCIONES ───────────────────────────────────────
    def _section_identidad(self, b, eq_type) -> QFrame:
        sect = QFrame()
        l = QVBoxLayout(sect); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(8)
        l.addLayout(self._section_header(
            "Identidad",
            help_text="Tag ISA, tamaño característico y unidades en paralelo. "
                      "El tag y el tipo son lo único que el flowsheet usa para "
                      "identificar este bloque."
        ))

        # Empty state especial para mixer
        if _is_mixer(eq_type):
            empty = self._mixer_empty_state()
            l.addWidget(empty)

        # Tag inline en el header — no se duplica aquí.
        # S
        spec = eq.EQUIPMENT_DATA.get(eq_type, {})
        s_unit = spec.get("S_unit", "·")
        sf = self._spec_field("S", value=f"{float(b.S):.3f}", unit=s_unit, state="spec")
        l.addWidget(self._row("Tamaño S", sf,
                              info="Tamaño característico para escalado de costos"))

        s_min, s_max = spec.get("S_min"), spec.get("S_max")
        if s_min is not None and s_max is not None:
            hint = QLabel(f"Rango válido Turton: [{s_min:g} – {s_max:g}] {s_unit}")
            hint.setFont(QFont(pfd_fonts.SANS, 7))
            hint.setStyleSheet(f"color:{TOK['ink_soft']}; padding-left:152px;")
            l.addWidget(hint)

        # n
        sf_n = self._spec_field("n", value=str(int(b.n)), unit="·", state="spec")
        l.addWidget(self._row("Unidades en paralelo", sf_n,
                              info="El solver divide el duty entre n."))
        return sect

    def _mixer_empty_state(self) -> QFrame:
        f = QFrame(); f.setObjectName("mixerEmpty")
        lay = QVBoxLayout(f); lay.setContentsMargins(16, 16, 16, 16); lay.setSpacing(8)
        ico = QLabel("✨"); ico.setFixedSize(56, 56); ico.setAlignment(Qt.AlignCenter)
        ico.setStyleSheet(
            f"background:{TOK['accent_tint']}; color:{TOK['accent']}; "
            f"border-radius:14px; font-size:24px;"
        )
        lay.addWidget(ico, alignment=Qt.AlignCenter)
        ttl = QLabel("No hay nada que configurar acá")
        ttl.setFont(QFont(pfd_fonts.SANS, 11, QFont.Bold))
        ttl.setStyleSheet(f"color:{TOK['ink']};")
        ttl.setAlignment(Qt.AlignCenter)
        lay.addWidget(ttl)
        body = QLabel(
            "Un mezclador no define transformación propia: el solver calcula "
            "la salida sumando las entradas y aplicando el balance de energía.\n\n"
            "Si quieres añadir una caída de presión, una geometría o un material, "
            "abre Sizing."
        )
        body.setWordWrap(True); body.setAlignment(Qt.AlignCenter)
        body.setFont(QFont(pfd_fonts.SANS, 9))
        body.setStyleSheet(f"color:{TOK['ink_mute']};")
        lay.addWidget(body)

        f.setStyleSheet(
            f"#mixerEmpty {{ background:{TOK['bg_mute']}; "
            f"border:1px solid {TOK['line']}; border-radius:9px; }}"
        )
        return f

    def _section_termo(self, b, eq_type) -> QFrame:
        is_reactor = _is_reactor(eq_type)
        is_mixer = _is_mixer(eq_type)

        sect = QFrame()
        l = QVBoxLayout(sect); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(8)
        l.addLayout(self._section_header(
            "Termodinámica",
            help_text=("Para un mezclador la T de salida es resultado del balance "
                       "de mezcla — la lee el solver." if is_mixer else
                       "Fija los parámetros que conoces; el solver calcula el resto. "
                       "Toca cualquier campo y alterna entre spec / auto.")
        ))

        # T de operación
        T_val = float(getattr(b, "T_op_K", 0.0) or 0.0)
        T_state = "auto" if is_mixer or T_val <= 0 else "spec"
        sf_T = self._spec_field("T_op_K",
                                value=f"{T_val:.1f}" if T_val > 0 else "",
                                unit="K", state=T_state)
        l.addWidget(self._row("T de operación", sf_T,
                              info="0/auto → solver usa T promedio del input."))

        # P de operación
        P_val = float(getattr(b, "P_op_bar", 1.0) or 1.0)
        sf_P = self._spec_field("P_op_bar", value=f"{P_val:.2f}",
                                unit="bar", state="spec")
        l.addWidget(self._row("P de operación", sf_P))

        # ΔP
        dp = float(getattr(b, "delta_p_bar", 0.0) or 0.0)
        sf_dp = self._spec_field("delta_p_bar",
                                 value=f"{dp:.3f}" if dp != 0 else "",
                                 unit="bar",
                                 state="spec" if dp != 0 else "empty")
        l.addWidget(self._row("ΔP a través del bloque", sf_dp,
                              info=">0 suma presión (bomba), <0 la pierde (HX, columna)"))

        # duty (spec = locked, auto = solver lo computa)
        if not is_mixer:
            duty_val = float(getattr(b, "duty", 0.0) or 0.0)
            duty_state = "spec" if getattr(b, "duty_locked", False) else "auto"
            sf_duty = self._spec_field("duty",
                                       value=f"{duty_val:.1f}" if duty_val != 0 else "",
                                       unit="kW", state=duty_state)
            l.addWidget(self._row("Duty", sf_duty,
                                  info=">0 aporta calor · <0 lo extrae · auto = solver lo calcula"))

        # heat_of_reaction (solo reactores)
        if is_reactor:
            hor = float(getattr(b, "heat_of_reaction", 0.0) or 0.0)
            sf_hor = self._spec_field("heat_of_reaction",
                                      value=f"{hor:.1f}" if hor != 0 else "",
                                      unit="kJ/kg",
                                      state="spec" if hor != 0 else "auto")
            l.addWidget(self._row("Calor de reacción", sf_hor,
                                  info="Por kg de input. >0 endo · <0 exo · auto = del catálogo"))

        return sect

    def _section_reactividad(self, b, eq_type) -> QFrame:
        sect = QFrame()
        l = QVBoxLayout(sect); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(8)

        try:
            import reactions_db as rdb
            ids = rdb.list_ids()
        except Exception:
            ids = []
            rdb = None

        active_ids = set(getattr(b, "reactions", []) or [])
        n_active = sum(1 for rid in ids if rid in active_ids)

        l.addLayout(self._section_header(
            "Reactividad",
            sub=f"{n_active} activas · {len(ids)} en catálogo",
            help_text="Marca las reacciones que este reactor cataliza. "
                      "El solver calcula conversión y ΔH a partir de la cinética "
                      "y termodinámica de cada una."
        ))

        # modo del reactor
        mode_row = QHBoxLayout(); mode_row.setSpacing(6)
        mode_lbl = QLabel("Modo")
        mode_lbl.setFont(QFont(pfd_fonts.SANS, 9))
        mode_lbl.setStyleSheet(f"color:{TOK['ink_mute']};")
        mode_lbl.setMinimumWidth(140)
        mode_cb = QComboBox()
        mode_cb.addItem("equilibrium — Newton Gibbs", "equilibrium")
        mode_cb.addItem("pfr — RK4 cinética", "pfr")
        mode_cb.addItem("cstr — Newton cinética", "cstr")
        mode_cb.addItem("batch — RK4 dN/dt, V cte", "batch")
        cur = getattr(b, "reactor_mode", "equilibrium") or "equilibrium"
        i = mode_cb.findData(cur)
        if i >= 0: mode_cb.setCurrentIndex(i)
        mode_cb.setStyleSheet(self._combo_style())
        self._extras["reactor_mode"] = mode_cb
        mode_row.addWidget(mode_lbl); mode_row.addWidget(mode_cb, 1)
        row = QFrame(); row.setLayout(mode_row)
        l.addWidget(row)

        # volumen (para pfr/cstr/batch)
        vol = float(getattr(b, "reactor_volume_L", 0.0) or 0.0)
        sf_vol = self._spec_field("reactor_volume_L",
                                  value=f"{vol:.2f}" if vol > 0 else "",
                                  unit="L",
                                  state="spec" if vol > 0 else "empty")
        l.addWidget(self._row("Volumen reactor", sf_vol,
                              info="Solo en modo PFR/CSTR/batch"))

        # batch_time
        bt = float(getattr(b, "batch_time_s", 3600.0) or 3600.0)
        sf_bt = self._spec_field("batch_time_s",
                                 value=f"{bt:.0f}",
                                 unit="s",
                                 state="spec")
        l.addWidget(self._row("Tiempo de tanda", sf_bt,
                              info="Solo modo batch — V cte, P emergente"))

        # tabla de reacciones
        if rdb and ids:
            list_label = QLabel("Catálogo de reacciones")
            list_label.setFont(QFont(pfd_fonts.SANS, 8, QFont.Bold))
            list_label.setStyleSheet(f"color:{TOK['ink_soft']}; padding-top:8px; letter-spacing:1px;")
            l.addWidget(list_label)
            for rid in ids:
                r = rdb.get(rid)
                if not r: continue
                conf = self._confidence_for(r)
                dh = getattr(r, "dh_rxn_298_kJ_mol", None)
                eq_str = self._equation_string(r)
                row = ReactionRow(rid, eq_str, r.name, conf, dh,
                                  active=(rid in active_ids),
                                  applicable=True)
                self._reaction_rows.append((rid, row))
                l.addWidget(row)
        else:
            warn = QLabel("(Catálogo de reacciones no disponible en este entorno)")
            warn.setStyleSheet(f"color:{TOK['ink_ghost']}; font-style:italic;")
            l.addWidget(warn)

        return sect

    @staticmethod
    def _confidence_for(r) -> str:
        # Heurística simple: si tiene cinética o ΔH y rango T, "alta";
        # si tiene ΔH pero sin cinética, "media"; resto, "baja".
        has_kin = bool(getattr(r, "kinetics", None))
        has_dh  = getattr(r, "dh_rxn_298_kJ_mol", None) is not None
        if has_kin and has_dh: return "alta"
        if has_dh:             return "media"
        return "baja"

    @staticmethod
    def _equation_string(r) -> str:
        try:
            reactants = [(e.nu, e.formula) for e in r.stoich if e.nu < 0]
            products  = [(e.nu, e.formula) for e in r.stoich if e.nu > 0]
            def fmt(parts):
                out = []
                for nu, f in parts:
                    n = abs(nu)
                    if n == 1: out.append(f)
                    else:      out.append(f"{n} {f}")
                return " + ".join(out)
            return f"{fmt(reactants)} → {fmt(products)}"
        except Exception:
            return r.name

    def _section_columna(self, b, eq_type) -> QFrame:
        sect = QFrame()
        l = QVBoxLayout(sect); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(8)
        l.addLayout(self._section_header(
            "Etapas y reflujo",
            help_text="Método FUG (Fenske-Underwood-Gilliland) o Wang-Henke MESH."
        ))

        N = int(getattr(b, "column_N_stages", 0) or 0)
        sf_N = self._spec_field("column_N_stages",
                                value=str(N) if N > 0 else "",
                                unit="·",
                                state="spec" if N > 0 else "empty")
        l.addWidget(self._row("N etapas", sf_N))

        xD = float(getattr(b, "column_x_D_LK", 0.95) or 0.95)
        sf_xD = self._spec_field("column_x_D_LK", value=f"{xD:.3f}", unit="·", state="spec")
        l.addWidget(self._row("Pureza LK en destilado", sf_xD))

        xB = float(getattr(b, "column_x_B_LK", 0.05) or 0.05)
        sf_xB = self._spec_field("column_x_B_LK", value=f"{xB:.3f}", unit="·", state="spec")
        l.addWidget(self._row("Frac LK en fondo", sf_xB))

        Rf = float(getattr(b, "column_R_factor", 1.3) or 1.3)
        sf_Rf = self._spec_field("column_R_factor", value=f"{Rf:.2f}", unit="·", state="spec")
        l.addWidget(self._row("Relación R / Rmin", sf_Rf))

        # método (combo)
        m_lay = QHBoxLayout()
        m_lbl = QLabel("Método")
        m_lbl.setFont(QFont(pfd_fonts.SANS, 9)); m_lbl.setStyleSheet(f"color:{TOK['ink_mute']};")
        m_lbl.setMinimumWidth(140)
        m_cb = QComboBox()
        m_cb.addItem("FUG — shortcut", "fug")
        m_cb.addItem("Wang-Henke MESH", "wanghenke")
        idx = m_cb.findData(getattr(b, "column_method", "fug") or "fug")
        if idx >= 0: m_cb.setCurrentIndex(idx)
        m_cb.setStyleSheet(self._combo_style())
        self._extras["column_method"] = m_cb
        m_lay.addWidget(m_lbl); m_lay.addWidget(m_cb, 1)
        wrap = QFrame(); wrap.setLayout(m_lay); l.addWidget(wrap)

        return sect

    def _section_sizing(self, b, eq_type) -> QFrame:
        sect = QFrame()
        l = QVBoxLayout(sect); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(8)
        l.addLayout(self._section_header(
            "Sizing",
            help_text="Geometría y overrides físicos del bloque. "
                      "Vacío = el solver usa el default canónico."
        ))

        # HX overrides
        if _is_hx(eq_type):
            U = float(getattr(b, "U_override", None) or 0.0)
            sf_U = self._spec_field("U_override",
                                    value=f"{U:.1f}" if U > 0 else "",
                                    unit="W/m²K",
                                    state="spec" if U > 0 else "empty")
            l.addWidget(self._row("U_override", sf_U,
                                  info="Coeficiente global. Vacío → usar valor típico de tabla"))
            DT = float(getattr(b, "dtlm_override", None) or 0.0)
            sf_DT = self._spec_field("dtlm_override",
                                     value=f"{DT:.2f}" if DT > 0 else "",
                                     unit="K",
                                     state="spec" if DT > 0 else "empty")
            l.addWidget(self._row("ΔTlm override", sf_DT,
                                  info="Vacío → usar valor típico de tabla"))

        # Tower internos
        if _is_tower(eq_type):
            ts = float(getattr(b, "tray_spacing_m", None) or 0.0)
            sf_ts = self._spec_field("tray_spacing_m",
                                     value=f"{ts:.3f}" if ts > 0 else "",
                                     unit="m",
                                     state="spec" if ts > 0 else "empty")
            l.addWidget(self._row("Tray spacing", sf_ts,
                                  info="Default canónico: 0.6 m (24\")"))
            K = float(getattr(b, "K_souders_brown", None) or 0.0)
            sf_K = self._spec_field("K_souders_brown",
                                    value=f"{K:.4f}" if K > 0 else "",
                                    unit="m/s",
                                    state="spec" if K > 0 else "empty")
            l.addWidget(self._row("K Souders-Brown", sf_K, info="Default canónico: 0.06"))
            head = float(getattr(b, "column_head_height_m", None) or 0.0)
            sf_h = self._spec_field("column_head_height_m",
                                    value=f"{head:.2f}" if head > 0 else "",
                                    unit="m",
                                    state="spec" if head > 0 else "empty")
            l.addWidget(self._row("Head height", sf_h, info="Default canónico: 3 m"))

        # Pump/Compressor — efficiency
        if _is_pump_compressor(eq_type):
            eta = float(getattr(b, "efficiency", 0.75) or 0.75)
            sf_eta = self._spec_field("efficiency",
                                      value=f"{eta:.3f}",
                                      unit="·", state="spec")
            l.addWidget(self._row("Eficiencia η", sf_eta,
                                  info="η_hidráulica · η_motor (típico bomba 0.75, compresor 0.70)"))

        # Si no hay nada específico, mostrar placeholder
        if not (_is_hx(eq_type) or _is_tower(eq_type) or _is_pump_compressor(eq_type)):
            ph = QLabel("Geometría base (Tamaño S) en la sección Identidad.")
            ph.setFont(QFont(pfd_fonts.SANS, 9))
            ph.setStyleSheet(f"color:{TOK['ink_soft']}; font-style:italic;")
            l.addWidget(ph)

        return sect

    def _section_utility(self, b, eq_type) -> QFrame:
        sect = QFrame()
        l = QVBoxLayout(sect); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(8)
        l.addLayout(self._section_header(
            "Utility",
            help_text="Servicio que aporta o retira el duty. El costo OPEX "
                      "se calcula con el catálogo del proyecto."
        ))

        # Utility combo
        try:
            import equipment_ports as ep
            keys = list(ep.UTILITIES.keys())
        except Exception:
            keys = []

        cb = QComboBox()
        cb.addItem("(auto — el solver elige)", "")
        for k in keys:
            cb.addItem(k, k)
        cur = getattr(b, "heat_source", "") or ""
        idx = cb.findData(cur) if cur else 0
        cb.setCurrentIndex(max(0, idx))
        cb.setStyleSheet(self._combo_style())
        self._extras["heat_source"] = cb
        u_lay = QHBoxLayout()
        u_lbl = QLabel("Tipo de utility")
        u_lbl.setFont(QFont(pfd_fonts.SANS, 9))
        u_lbl.setStyleSheet(f"color:{TOK['ink_mute']};")
        u_lbl.setMinimumWidth(140)
        u_lay.addWidget(u_lbl); u_lay.addWidget(cb, 1)
        wrap = QFrame(); wrap.setLayout(u_lay)
        l.addWidget(wrap)
        return sect

    def _section_economia(self, b, eq_type) -> QFrame:
        sect = QFrame()
        l = QVBoxLayout(sect); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(8)
        l.addLayout(self._section_header(
            "Economía",
            sub="CEPCI · Turton 5ª",
            help_text="Bare Module Cost por bloque, con factores de material y presión. "
                      "El solver lo recalcula al guardar."
        ))

        # CBM (read-only, derivado)
        cbm = self._compute_cbm(b)
        cbm_str = f"{cbm:,.0f}".replace(",", " ") if cbm else "—"
        sf_cbm = self._spec_field("CBM_readonly",
                                  value=cbm_str,
                                  unit="USD", state="auto", allow_toggle=False)
        l.addWidget(self._row("C_BM (bare module)", sf_cbm))
        return sect

    @staticmethod
    def _combo_style() -> str:
        return f"""
            QComboBox {{
                background: {TOK['bg_elev']};
                color: {TOK['ink']};
                border: 1px solid {TOK['line_strong']};
                border-radius: 6px;
                padding: 5px 8px;
                font-family: '{pfd_fonts.SANS}';
                font-size: 9pt;
            }}
            QComboBox:hover {{ border: 1px solid {TOK['accent_soft']}; }}
            QComboBox::drop-down {{ border: 0; }}
            QComboBox QAbstractItemView {{
                background: {TOK['bg_elev']};
                border: 1px solid {TOK['line_strong']};
                selection-background-color: {TOK['accent_tint']};
                selection-color: {TOK['ink']};
            }}
        """

    # ─── DOF + Footer ────────────────────────────────────
    def _update_footer(self):
        b = self.block
        if not b:
            return
        cbm = self._compute_cbm(b)
        if cbm:
            s = f"${cbm:,.0f}".replace(",", " ")
            self._stat_capex_val.setText(s + "  USD")
        else:
            self._stat_capex_val.setText("—")

        # OPEX/h — aproximación: si el bloque tiene duty != 0 y heat_source,
        # cost por hora puede estimarse. Por ahora, placeholder.
        self._stat_opex_val.setText("—")

        # Conversión (solo reactores con reacciones activas)
        if _is_reactor(b.eq_type):
            n_act = len(getattr(b, "reactions", []) or [])
            if n_act > 0:
                self._stat_conv_val.setText(f"{n_act} rxn")
            else:
                self._stat_conv_val.setText("—")
            self._stat_conv_lbl.setVisible(True)
            self._stat_conv_val.setVisible(True)
        else:
            self._stat_conv_lbl.setVisible(False)
            self._stat_conv_val.setVisible(False)

    def _update_dof_badges(self):
        b = self.block
        if not b:
            return
        # badge "reactividad" = n/total
        if _is_reactor(b.eq_type):
            try:
                import reactions_db as rdb
                total = len(rdb.list_ids())
            except Exception:
                total = 0
            n_act = len(getattr(b, "reactions", []) or [])
            self._sidebar.set_badge("reactividad", f"{n_act}/{total}" if total else f"{n_act}")
            # DOF heurístico: si hay reacciones, OK; si es reactor sin rxn, warn 1
            if n_act == 0:
                self._sidebar.set_dof("warn", 1)
            else:
                self._sidebar.set_dof("ok", 0)
        else:
            self._sidebar.set_dof("ok", 0)
        # badge economía
        self._sidebar.set_badge("economia", "$")

    @staticmethod
    def _compute_cbm(b) -> float:
        try:
            d = eq.bare_module_cost(b.eq_type, float(b.S),
                                    P_op_bar=float(getattr(b, "P_op_bar", 1.0) or 1.0))
            return float(d.get("CBM", 0.0) or 0.0)
        except Exception:
            return 0.0

    # ─── Persistencia ────────────────────────────────────
    def _do_save(self):
        if not self.block:
            return
        try:
            self._apply_to_block()
        except Exception as e:
            QMessageBox.critical(
                self, "Error al guardar",
                f"No se pudo aplicar los cambios:\n{e}"
            )
            return
        if self._on_save:
            self._on_save()
        # refresca footer post-save (CBM puede haber cambiado por S, P_op)
        self._update_footer()
        self._update_dof_badges()
        # también re-popula streams (T/P pueden haber cambiado tras solver)
        self._streams.populate(
            self._projected_streams_in(),
            self._projected_streams_out(),
            block_tag=self.block.name,
        )

    def _apply_to_block(self):
        """Persiste los valores actuales de los SpecField + extras al Block.

        Solo persistimos los campos que están EN el panel actualmente
        renderizado. Para los que no están renderizados, el valor del Block
        permanece intacto.
        """
        b = self.block
        # Tag (siempre presente en el header)
        nt = self._header.tag()
        if nt:
            b.name = nt

        f = self._fields
        # ─── Identidad ───
        if "S" in f:
            try: b.S = float(self._parse_num(f["S"].value()))
            except Exception: pass
        if "n" in f:
            try: b.n = int(float(self._parse_num(f["n"].value())))
            except Exception: pass
        # ─── Termo ───
        if "T_op_K" in f:
            try:
                v = self._parse_num(f["T_op_K"].value())
                b.T_op_K = float(v) if v else 0.0
            except Exception: pass
        if "P_op_bar" in f:
            try:
                v = self._parse_num(f["P_op_bar"].value())
                b.P_op_bar = float(v) if v else 1.0
            except Exception: pass
        if "delta_p_bar" in f:
            try:
                v = self._parse_num(f["delta_p_bar"].value())
                b.delta_p_bar = float(v) if v else 0.0
            except Exception: pass
        if "duty" in f:
            try:
                v = self._parse_num(f["duty"].value())
                b.duty = float(v) if v else 0.0
                b.duty_locked = (f["duty"].state() == "spec")
            except Exception: pass
        if "heat_of_reaction" in f:
            try:
                v = self._parse_num(f["heat_of_reaction"].value())
                b.heat_of_reaction = float(v) if v else 0.0
            except Exception: pass
        # ─── Reactividad ───
        if "reactor_volume_L" in f:
            try:
                v = self._parse_num(f["reactor_volume_L"].value())
                b.reactor_volume_L = float(v) if v else 0.0
            except Exception: pass
        if "batch_time_s" in f:
            try:
                v = self._parse_num(f["batch_time_s"].value())
                b.batch_time_s = float(v) if v else 3600.0
            except Exception: pass
        if "reactor_mode" in self._extras:
            cb = self._extras["reactor_mode"]
            b.reactor_mode = cb.currentData() or "equilibrium"
        if self._reaction_rows:
            b.reactions = [rid for rid, row in self._reaction_rows if row.isOn()]
        # ─── Columna ───
        for key, attr in (
            ("column_N_stages", "column_N_stages"),
            ("column_x_D_LK", "column_x_D_LK"),
            ("column_x_B_LK", "column_x_B_LK"),
            ("column_R_factor", "column_R_factor"),
        ):
            if key in f:
                try:
                    v = self._parse_num(f[key].value())
                    val = float(v) if v else 0.0
                    if attr == "column_N_stages":
                        setattr(b, attr, int(val))
                    else:
                        setattr(b, attr, val)
                except Exception:
                    pass
        if "column_method" in self._extras:
            cb = self._extras["column_method"]
            b.column_method = cb.currentData() or "fug"
        # ─── Sizing ───
        if "U_override" in f:
            v = self._parse_num(f["U_override"].value())
            try:
                b.U_override = float(v) if v else None
            except Exception:
                b.U_override = None
        if "dtlm_override" in f:
            v = self._parse_num(f["dtlm_override"].value())
            try:
                b.dtlm_override = float(v) if v else None
            except Exception:
                b.dtlm_override = None
        for key in ("tray_spacing_m", "K_souders_brown", "column_head_height_m",
                    "efficiency"):
            if key in f:
                v = self._parse_num(f[key].value())
                try:
                    setattr(b, key, float(v) if v else 0.0)
                except Exception:
                    pass
        # ─── Utility ───
        if "heat_source" in self._extras:
            cb = self._extras["heat_source"]
            data = cb.currentData()
            b.heat_source = data if data else ""

    @staticmethod
    def _parse_num(s: str) -> str:
        """Limpia separadores de miles tipo NNN NNN o NNN,NNN."""
        if not s:
            return ""
        s = s.replace(" ", "").replace(" ", "").replace(",", "")
        # rechaza si quedan cosas no numéricas que no sean . - +
        # (no es ultra estricto: float() decidirá)
        return s


# ════════════════════════════════════════════════════════
#  DOCK CONTENEDOR
# ════════════════════════════════════════════════════════

class BlockInspectorDock(QDockWidget):
    """QDockWidget slide-out con el BlockInspectorPanel adentro.

    Se construye una sola vez en FlowsheetMainWindow y se reusa via show_for().
    """

    def __init__(self, parent=None):
        super().__init__("Inspector", parent)
        self.setObjectName("BlockInspectorDock")
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetFloatable |
            QDockWidget.DockWidgetClosable
        )
        self.setMinimumWidth(PANEL_W)
        # title bar custom — el panel ya tiene su propio header con
        # tag/close, así que escondemos el de Qt para no duplicar.
        # Mantenemos un widget vacío como title para permitir drag.
        empty_tb = QWidget(self); empty_tb.setFixedHeight(0)
        self.setTitleBarWidget(empty_tb)

        self.panel = BlockInspectorPanel(self)
        self.panel.closeRequested.connect(self.hide)
        self.setWidget(self.panel)
        self.hide()

    def show_for(self, block, flowsheet, on_save=None, open_advanced=None):
        self.panel.load_block(block, flowsheet,
                              on_save=on_save,
                              open_advanced=open_advanced)
        self.show()
        self.raise_()
