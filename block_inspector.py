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
    QSizePolicy, QSpacerItem, QComboBox, QTextEdit, QMessageBox, QCheckBox,
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
    # catálogo Sinnott (extensión HX riguroso)
    "sinnott":        "#6e3aa6",
    "sinnott_ink":    "#4a2873",
    "sinnott_bg":     "#efebf7",
    "sinnott_ribbon": "#8a5cc0",
    "turton_ink":     "#3548b4",
    "status_fallback":"#5f7bd6",
}

ROW_PAD   = 12   # cozy
SECT_GAP  = 22   # cozy
PANEL_W   = 520


# ════════════════════════════════════════════════════════
#  PREFERENCIAS — temas, densidades, acentos
# ════════════════════════════════════════════════════════
# Estos diccionarios definen alternativas que el usuario puede elegir
# desde Vista > Preferencias…  Al cambiar, mutamos TOK / ROW_PAD /
# SECT_GAP in-place y emitimos un signal global para que widgets
# vivos se re-construyan.

THEME_LIGHT = {
    "bg": "#f6f3ec", "bg_elev": "#ffffff", "bg_mute": "#f1ede4",
    "bg_sunk": "#ece6d8",
    "line": "#e6e0d0", "line_strong": "#d4ccb8", "line_soft": "#efeadd",
    "ink": "#1a1714", "ink_mute": "#6b6256",
    "ink_soft": "#948a7c", "ink_ghost": "#bab2a3",
    "spec_bg": "#eef1ff", "spec": "#3548b4",
    "spec_ink": "#2a3a9a", "spec_ribbon": "#4a5dcc",
    "auto_bg": "#f3efe5", "auto_ink": "#918878", "auto_ribbon": "#c9c0ad",
    "green": "#4d8742", "green_bg": "#e6f0df",
    "amber": "#b8841a", "amber_bg": "#f4ecd1",
    "orange": "#c26329", "orange_bg": "#f5e1d0",
    "danger": "#b8453a", "danger_bg": "#f3dcd8",
    "tag_bg": "#ede7d6", "tag_ink": "#6b6253",
    "sinnott": "#6e3aa6", "sinnott_ink": "#4a2873", "sinnott_bg": "#efebf7",
    "sinnott_ribbon": "#8a5cc0", "turton_ink": "#3548b4",
    "status_fallback": "#5f7bd6",
}

THEME_DARK = {
    "bg": "#16130f", "bg_elev": "#1f1b16", "bg_mute": "#26211b",
    "bg_sunk": "#110e0a",
    "line": "#2f2920", "line_strong": "#3f3830", "line_soft": "#251f18",
    "ink": "#efe7d6", "ink_mute": "#a59a89",
    "ink_soft": "#6f6759", "ink_ghost": "#4a4438",
    "spec_bg": "#20254a", "spec": "#92a0ef",
    "spec_ink": "#b4befa", "spec_ribbon": "#8294f5",
    "auto_bg": "#221d16", "auto_ink": "#8a8170", "auto_ribbon": "#463f33",
    "green": "#85b274", "green_bg": "#1f2a1d",
    "amber": "#d8aa3a", "amber_bg": "#2e2618",
    "orange": "#d18a55", "orange_bg": "#2e2118",
    "danger": "#d97262", "danger_bg": "#2e1a17",
    "tag_bg": "#2a241d", "tag_ink": "#a59a89",
    "sinnott": "#b598e0", "sinnott_ink": "#d3befa", "sinnott_bg": "#2a2535",
    "sinnott_ribbon": "#9978c9", "turton_ink": "#b4befa",
    "status_fallback": "#9aaef0",
}

# Acentos: 4 presets que sobrescriben los 4 tokens de accent.
ACCENTS = {
    "teal": {     # default — teal profundo
        "accent": "#0d6e78", "accent_deep": "#064951",
        "accent_soft": "#d4ebed", "accent_tint": "#eaf4f5",
    },
    "terracota": {
        "accent": "#a44a2b", "accent_deep": "#7a341c",
        "accent_soft": "#f0d3c5", "accent_tint": "#f7e7df",
    },
    "cobalto": {
        "accent": "#3548b4", "accent_deep": "#1f2e8c",
        "accent_soft": "#cfd5f0", "accent_tint": "#e5e8f7",
    },
    "oliva": {
        "accent": "#5f7a30", "accent_deep": "#3f5520",
        "accent_soft": "#d9e3c2", "accent_tint": "#ecf0dc",
    },
}

# Dark-mode tiene su propio juego de accents (matiza más suave)
ACCENTS_DARK = {
    "teal":      {"accent": "#5dc1cc", "accent_deep": "#92dde4",
                  "accent_soft": "#1f3a3d", "accent_tint": "#1a2b2d"},
    "terracota": {"accent": "#d18a6a", "accent_deep": "#ecae8c",
                  "accent_soft": "#3a221a", "accent_tint": "#2a1812"},
    "cobalto":   {"accent": "#8a98ed", "accent_deep": "#aab5f4",
                  "accent_soft": "#23295a", "accent_tint": "#1a1f40"},
    "oliva":     {"accent": "#9cb56a", "accent_deep": "#bccf8d",
                  "accent_soft": "#2c3520", "accent_tint": "#1f2618"},
}

# Densidades: (row_pad, sect_gap)
DENSITIES = {
    "compact": (8,  14),
    "cozy":    (12, 22),
    "comfy":   (16, 30),
}

# Estado global de preferencias
_PREFS = {
    "theme":   "light",
    "density": "cozy",
    "accent":  "teal",
}


def current_prefs() -> dict:
    return dict(_PREFS)


def apply_preferences(theme: str = None, density: str = None,
                      accent: str = None) -> bool:
    """Muta TOK / ROW_PAD / SECT_GAP in-place según el tema / densidad /
    acento elegidos.  Devuelve True si algo cambió.

    Llamar al inicio de la app (cargando prefs.json) y desde el diálogo
    de preferencias.  Widgets ya construidos NO se actualizan
    automáticamente — el caller debe reconstruirlos (signal
    PreferencesChanged emitido).
    """
    global ROW_PAD, SECT_GAP
    changed = False
    if theme and theme in ("light", "dark") and theme != _PREFS["theme"]:
        _PREFS["theme"] = theme
        changed = True
    if density and density in DENSITIES and density != _PREFS["density"]:
        _PREFS["density"] = density
        changed = True
    if accent and accent in ACCENTS and accent != _PREFS["accent"]:
        _PREFS["accent"] = accent
        changed = True

    # Reconstruir TOK
    base = THEME_DARK if _PREFS["theme"] == "dark" else THEME_LIGHT
    acc_set = ACCENTS_DARK if _PREFS["theme"] == "dark" else ACCENTS
    acc = acc_set.get(_PREFS["accent"], acc_set["teal"])

    TOK.clear()
    TOK.update(base)
    TOK.update(acc)

    # Densidad
    ROW_PAD, SECT_GAP = DENSITIES.get(_PREFS["density"], (12, 22))
    return changed


# Inicializa TOK con los defaults para que importar el módulo no rompa
apply_preferences()


# Signal global de cambios — los widgets vivos se suscriben y rebuilen.
# Lo expone via un QObject helper porque las Signal de Qt necesitan
# un instancia.

class _PrefsBus:
    """Bus de eventos para cambios de preferencias.  Lazy-init para
    no requerir un QApplication al importar el módulo."""
    _instance = None
    _obj = None

    @classmethod
    def signal(cls):
        if cls._obj is None:
            from PySide6.QtCore import QObject, Signal as _Sig
            class _Bus(QObject):
                themeChanged = _Sig()
            cls._obj = _Bus()
        return cls._obj.themeChanged

    @classmethod
    def emit(cls):
        sig = cls.signal()
        sig.emit()


# Persistencia: ~/.flowsheet_prefs.json
import os, json
_PREFS_PATH = os.path.expanduser("~/.flowsheet_prefs.json")


def load_prefs_from_disk():
    try:
        with open(_PREFS_PATH) as f:
            d = json.load(f)
        apply_preferences(d.get("theme"), d.get("density"), d.get("accent"))
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[prefs] no se pudo cargar {_PREFS_PATH}: {e}")


def save_prefs_to_disk():
    try:
        with open(_PREFS_PATH, "w") as f:
            json.dump(_PREFS, f, indent=2)
    except Exception as e:
        print(f"[prefs] no se pudo guardar {_PREFS_PATH}: {e}")


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

def _is_flash_vessel(eq_type: str) -> bool:
    """Flash VLE aplica a Vessels (verticales/horizontales) y Flash drums."""
    t = (eq_type or "").lower()
    return ("vessel" in t or "tanque" in t or "flash" in t) and "tower" not in t

def _is_mech_separator(eq_type: str) -> bool:
    """Filtro o centrífuga — separación sólido/líquido mecánica."""
    t = (eq_type or "").lower()
    return "filter" in t or "centrifuge" in t

def _is_dryer(eq_type: str) -> bool:
    return "dryer" in (eq_type or "").lower()

def _is_crystallizer(eq_type: str) -> bool:
    return "crystallizer" in (eq_type or "").lower()

def _is_evaporator(eq_type: str) -> bool:
    return "evaporator" in (eq_type or "").lower()

def _is_cyclone(eq_type: str) -> bool:
    return "cyclone" in (eq_type or "").lower()

def _is_decanter(eq_type: str) -> bool:
    return "decanter" in (eq_type or "").lower()

def _is_mech_sep_any(eq_type: str) -> bool:
    """Cualquier separador mecánico unificado (modelo mech_sep_active):
    filtro, centrífuga, ciclón o decanter."""
    return (_is_mech_separator(eq_type) or _is_cyclone(eq_type)
            or _is_decanter(eq_type))

def _has_special_mode(eq_type: str) -> bool:
    """True si el eq_type tiene un modelo automático nicho (separador
    mecánico, secador, cristalizador, evaporador)."""
    return (_is_mech_sep_any(eq_type) or _is_dryer(eq_type)
            or _is_crystallizer(eq_type) or _is_evaporator(eq_type))

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
    if _is_flash_vessel(eq_type):
        secs.append("flash")
    if _has_special_mode(eq_type):
        secs.append("especial")
    secs.append("sizing")
    secs.append("utility")
    secs.append("economia")
    secs.append("diagnostico")
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
        "flash":       "Flash VLE",
        "especial":    "Modo especial",
        "sizing":      "Sizing",
        "utility":     "Utility",
        "economia":    "Economía",
        "diagnostico": "Diagnóstico",
    }
    SECTION_ICON = {
        "identidad":   "T",
        "termo":       "θ",
        "reactividad": "R",
        "columna":     "≡",
        "flash":       "V",
        "especial":    "★",
        "sizing":      "□",
        "utility":     "♨",
        "economia":    "$",
        "diagnostico": "i",
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
        # Suscribirse al bus de prefs para re-construir el panel al
        # cambiar tema/densidad/acento (Vista > Preferencias…).
        try:
            _PrefsBus.signal().connect(self._on_prefs_changed)
        except Exception:
            pass

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
        lay.setContentsMargins(14, 8, 10, 8); lay.setSpacing(9)

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

        # stats derivados HX (Área/Steam + ΔT_lm·F) — color atenuado
        self._stat_hxA_lbl   = QLabel("Área")
        self._stat_hxA_val   = QLabel("—")
        self._stat_hxdt_lbl  = QLabel("ΔT_lm·F")
        self._stat_hxdt_val  = QLabel("—")
        for caps, val in [
            (self._stat_hxA_lbl,  self._stat_hxA_val),
            (self._stat_hxdt_lbl, self._stat_hxdt_val),
        ]:
            col = QVBoxLayout(); col.setContentsMargins(0,0,0,0); col.setSpacing(1)
            caps.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
            caps.setStyleSheet(f"color:{TOK['ink_soft']}; letter-spacing:1px;")
            val.setFont(QFont(pfd_fonts.MONO, 11, QFont.Bold))
            val.setStyleSheet(f"color:{TOK['ink_mute']};")
            col.addWidget(caps); col.addWidget(val)
            lay.addLayout(col)
            caps.setVisible(False); val.setVisible(False)
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

    def _on_prefs_changed(self):
        """Callback de Vista > Preferencias…  Reconstruye el panel
        entero para que el nuevo tema / densidad / acento se aplique
        a todos los widgets hijos.  Sin block cargado → no-op."""
        if self.block is None or self.fs is None:
            return
        active = self._sidebar.active() or "identidad"
        self.load_block(self.block, self.fs,
                        on_save=self._on_save,
                        open_advanced=self._open_advanced_cb)
        # restaurar sección activa
        try:
            self._switch_section(active)
        except Exception:
            pass

    # ─── API pública ─────────────────────────────────────
    def load_block(self, block, flowsheet, on_save: Optional[Callable] = None,
                   open_advanced: Optional[Callable] = None):
        """Carga un Block en el panel. on_save() se invoca tras un Guardar OK."""
        self.block = block
        self.fs = flowsheet
        self._on_save = on_save
        self._open_advanced_cb = open_advanced
        self._hx_vm_cache = None
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
        # custom reactions: drop el snapshot local — se re-crea desde el
        # block.custom_reactions cuando se vuelve a entrar a Reactividad
        if hasattr(self, "_custom_rxns_data"):
            del self._custom_rxns_data
        b = self.block
        if b is None:
            return
        eq_type = b.eq_type

        builders = {
            "identidad":   self._section_identidad,
            "termo":       self._section_termo,
            "reactividad": self._section_reactividad,
            "columna":     self._section_columna,
            "flash":       self._section_flash,
            "especial":    self._section_especial,
            "sizing":      self._section_sizing,
            "utility":     self._section_utility,
            "economia":    self._section_economia,
            "diagnostico": self._section_diagnostico,
        }
        fn = builders.get(key)
        if fn:
            sect = fn(b, eq_type)
            self._content_lay.insertWidget(self._content_lay.count() - 1, sect)

        # Nota: el link 'Opciones avanzadas…' fue retirado en V2 — todas
        # las opciones de nicho (custom rxns, FUG columna, flash VLE,
        # separadores mecánicos, dryer, crystallizer, evaporator, cyclone)
        # están migradas a secciones nativas del inspector.

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

    # ─── HX riguroso (extensión Sinnott/WHB) ─────────────
    def _hx_viewmodel(self):
        """View-model térmico del HX (cacheado por load_block)."""
        if getattr(self, "_hx_vm_cache", None) is not None:
            return self._hx_vm_cache
        try:
            import hx_inspector as hxui
            self._hx_vm_cache = hxui.build_hx_viewmodel(self.block, self.fs)
        except Exception:
            self._hx_vm_cache = None
        return self._hx_vm_cache

    def _open_hx_topic(self, topic: str, ctx: dict = None):
        try:
            import hx_edu
            hx_edu.open_topic(topic, parent=self, ctx=ctx)
        except Exception:
            pass

    def _append_hx_termo(self, l, b):
        """Agrega las subsecciones HX-rigurosas a la sección Termodinámica:
        diseño térmico (4 cards o empty-state), riguroso colapsable y avisos."""
        try:
            import hx_inspector as hxui
        except Exception:
            return
        vm = self._hx_viewmodel()
        if not vm:
            return
        on_open = self._open_hx_topic
        empty = hxui.hx_empty_state(vm, b)

        l.addSpacing(6)
        l.addWidget(hxui._subsect_header(
            "Diseño térmico", "click una card para su explicación"))
        if empty:
            l.addWidget(hxui.make_empty_state(empty))
        else:
            l.addWidget(hxui.make_diagnostic_grid(vm, on_open))
            l.addSpacing(4)
            l.addWidget(hxui.RigorousBlock(vm))

        if vm.get("warnings"):
            n = len(vm["warnings"])
            l.addSpacing(6)
            l.addWidget(hxui._subsect_header(
                "Avisos termodinámicos", f"{n} aviso{'s' if n != 1 else ''}"))
            l.addWidget(hxui.WarningPanel(vm["warnings"], on_open))

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

        # HX riguroso: diseño térmico (cards) + riguroso + avisos
        if _is_hx(eq_type):
            self._append_hx_termo(l, b)

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

        # ── Reacciones custom ────────────────────────────────
        # Reacciones in-memory que no están en el catálogo .md.  Cada
        # una es un dict {id, name, eq?, dh_rxn_298_kJ_mol?, …}.
        custom_hd = QLabel("Reacciones custom")
        custom_hd.setFont(QFont(pfd_fonts.SANS, 8, QFont.Bold))
        custom_hd.setStyleSheet(
            f"color:{TOK['ink_soft']}; padding-top:12px; letter-spacing:1px;"
        )
        l.addWidget(custom_hd)

        self._custom_rxn_list_widget = QVBoxLayout()
        self._custom_rxn_list_widget.setContentsMargins(0, 0, 0, 0)
        self._custom_rxn_list_widget.setSpacing(4)
        # Snapshot mutable de las custom rxns del bloque
        self._custom_rxns_data = list(getattr(b, "custom_reactions", []) or [])
        self._refresh_custom_rxn_rows()
        cl_wrap = QFrame(); cl_wrap.setLayout(self._custom_rxn_list_widget)
        l.addWidget(cl_wrap)

        # Botón "+ Añadir reacción custom"
        add_btn = QPushButton("+  Añadir reacción custom")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFont(QFont(pfd_fonts.SANS, 9))
        add_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TOK['accent']}; "
            f"border: 1px dashed {TOK['accent_soft']}; border-radius: 7px; "
            f"padding: 8px; text-align: center; }} "
            f"QPushButton:hover {{ background: {TOK['accent_tint']}; "
            f"color: {TOK['accent_deep']}; border-color: {TOK['accent']}; }}"
        )
        add_btn.clicked.connect(self._on_add_custom_rxn)
        l.addWidget(add_btn)

        return sect

    def _refresh_custom_rxn_rows(self):
        """Repuebla la lista visual de custom reactions."""
        lay = self._custom_rxn_list_widget
        # limpiar
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w: w.setParent(None); w.deleteLater()
        if not self._custom_rxns_data:
            empty = QLabel("(ninguna)  ")
            empty.setStyleSheet(f"color:{TOK['ink_ghost']}; font-style:italic; padding:4px;")
            lay.addWidget(empty)
            return
        for idx, d in enumerate(self._custom_rxns_data):
            row = QFrame(); row.setObjectName(f"customRxn_{idx}")
            row.setStyleSheet(
                f"#customRxn_{idx} {{ background: {TOK['bg_mute']}; "
                f"border: 1px solid {TOK['line']}; border-left: 3px solid "
                f"{TOK['spec_ribbon']}; border-radius: 6px; }}"
            )
            rlay = QHBoxLayout(row); rlay.setContentsMargins(10, 6, 6, 6)
            rlay.setSpacing(8)
            # diamante indicador
            dot = QLabel("◆")
            dot.setStyleSheet(f"color:{TOK['spec']}; font-size:11px;")
            rlay.addWidget(dot)
            # nombre + id
            name = d.get("name") or d.get("id", "?")
            rid  = d.get("id", "?")
            nm = QLabel(name)
            nm.setFont(QFont(pfd_fonts.MONO, 9))
            nm.setStyleSheet(f"color:{TOK['ink']};")
            rlay.addWidget(nm, 1)
            rid_lbl = QLabel(rid)
            rid_lbl.setFont(QFont(pfd_fonts.MONO, 8))
            rid_lbl.setStyleSheet(f"color:{TOK['ink_soft']};")
            rlay.addWidget(rid_lbl)
            # botón eliminar
            rm = QToolButton(); rm.setText("✕")
            rm.setCursor(Qt.PointingHandCursor)
            rm.setFixedSize(22, 22)
            rm.setStyleSheet(
                f"QToolButton {{ background: transparent; color: {TOK['ink_mute']}; "
                f"border: 0; border-radius: 4px; }} "
                f"QToolButton:hover {{ background: {TOK['danger_bg']}; "
                f"color: {TOK['danger']}; }}"
            )
            rm.clicked.connect(lambda _=False, i=idx: self._on_remove_custom_rxn(i))
            rlay.addWidget(rm)
            lay.addWidget(row)

    def _on_add_custom_rxn(self):
        """Abre CustomReactionDialog (del flowsheet_qt legacy) y, si el user
        acepta, lo añade a la lista in-memory."""
        try:
            from flowsheet_qt import CustomReactionDialog
        except Exception:
            QMessageBox.warning(self, "No disponible",
                "CustomReactionDialog no está disponible en este entorno.")
            return
        dlg = CustomReactionDialog(self)
        from PySide6.QtWidgets import QDialog as _QDialog
        if dlg.exec() == _QDialog.Accepted and dlg.result_dict is not None:
            self._custom_rxns_data.append(dlg.result_dict)
            self._refresh_custom_rxn_rows()
            self._update_dof_badges()

    def _on_remove_custom_rxn(self, idx: int):
        if 0 <= idx < len(self._custom_rxns_data):
            del self._custom_rxns_data[idx]
            self._refresh_custom_rxn_rows()
            self._update_dof_badges()

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
            help_text="FUG (Fenske-Underwood-Gilliland) o Wang-Henke MESH. "
                      "Activar el diseño automático hace que el solver calcule "
                      "composiciones de destilado/fondo + Q_reb desde el feed."
        ))

        # Toggle FUG/MESH automático
        act = QCheckBox("Activar diseño automático")
        act.setChecked(bool(getattr(b, "column_active", False)))
        act.setFont(QFont(pfd_fonts.SANS, 9))
        act.setStyleSheet(self._checkbox_style())
        self._extras["column_active"] = act
        l.addWidget(act)

        # LK / HK por nombre de componente
        lk = QLineEdit(getattr(b, "column_LK", "") or "")
        lk.setPlaceholderText("ethanol, methanol, propane, ...")
        lk.setStyleSheet(self._line_input_style())
        self._extras["column_LK"] = lk
        l.addWidget(self._row("Light key (LK)", lk,
                              info="Componente más volátil. Por nombre canónico."))
        hk = QLineEdit(getattr(b, "column_HK", "") or "")
        hk.setPlaceholderText("water, butane, ...")
        hk.setStyleSheet(self._line_input_style())
        self._extras["column_HK"] = hk
        l.addWidget(self._row("Heavy key (HK)", hk,
                              info="Componente menos volátil."))

        # N etapas
        N = int(getattr(b, "column_N_stages", 0) or 0)
        sf_N = self._spec_field("column_N_stages",
                                value=str(N) if N > 0 else "",
                                unit="·",
                                state="spec" if N > 0 else "empty")
        l.addWidget(self._row("N etapas", sf_N,
                              info="0/empty → solver lo calcula con Gilliland (FUG)"))

        # Pureza destilado / frac fondo
        xD = float(getattr(b, "column_x_D_LK", 0.95) or 0.95)
        sf_xD = self._spec_field("column_x_D_LK", value=f"{xD:.4f}",
                                 unit="·", state="spec")
        l.addWidget(self._row("Pureza LK en destilado", sf_xD))

        xB = float(getattr(b, "column_x_B_LK", 0.05) or 0.05)
        sf_xB = self._spec_field("column_x_B_LK", value=f"{xB:.4f}",
                                 unit="·", state="spec")
        l.addWidget(self._row("Frac LK en fondo", sf_xB))

        # R / Rmin
        Rf = float(getattr(b, "column_R_factor", 1.3) or 1.3)
        sf_Rf = self._spec_field("column_R_factor", value=f"{Rf:.2f}",
                                 unit="·", state="spec")
        l.addWidget(self._row("Relación R / Rmin", sf_Rf,
                              info="Típico 1.2-1.5. R=Rmin requeriría ∞ etapas."))

        # Método combo
        m_cb = QComboBox()
        m_cb.addItem("FUG — shortcut (rápido)", "fug")
        m_cb.addItem("Wang-Henke MESH (riguroso)", "wanghenke")
        idx = m_cb.findData(getattr(b, "column_method", "fug") or "fug")
        if idx >= 0: m_cb.setCurrentIndex(idx)
        m_cb.setStyleSheet(self._combo_style())
        self._extras["column_method"] = m_cb
        l.addWidget(self._combo_row("Método", m_cb))

        return sect

    def _section_flash(self, b, eq_type) -> QFrame:
        """Flash isotérmico VLE — Vessels y flash drums."""
        sect = QFrame()
        l = QVBoxLayout(sect); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(8)
        l.addLayout(self._section_header(
            "Flash VLE",
            help_text="Si activo, el solver separa vapor/líquido con flash "
                      "isotérmico NRTL (γ·P_sat) a T_flash, P_flash. Asigna "
                      "vapor al puerto 'vapor' y líquido al 'liquido'."
        ))

        act = QCheckBox("Activar flash automático")
        act.setChecked(bool(getattr(b, "flash_active", False)))
        act.setFont(QFont(pfd_fonts.SANS, 9))
        act.setStyleSheet(self._checkbox_style())
        self._extras["flash_active"] = act
        l.addWidget(act)

        T_K = float(getattr(b, "flash_T_K", 298.15) or 298.15)
        sf_T = self._spec_field("flash_T_K", value=f"{T_K:.2f}",
                                unit="K", state="spec")
        l.addWidget(self._row("T_flash", sf_T))

        P_bar = float(getattr(b, "flash_P_bar", 1.013) or 1.013)
        sf_P = self._spec_field("flash_P_bar", value=f"{P_bar:.3f}",
                                unit="bar", state="spec")
        l.addWidget(self._row("P_flash", sf_P))

        return sect

    def _section_especial(self, b, eq_type) -> QFrame:
        """Modos especiales según eq_type: filtro/centrífuga, secador,
        cristalizador, evaporador, ciclón. Sólo aparece la sub-pieza
        relevante."""
        sect = QFrame()
        l = QVBoxLayout(sect); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(8)

        if _is_mech_sep_any(eq_type):
            is_cyc = _is_cyclone(eq_type)
            is_dec = _is_decanter(eq_type)
            sub = ("Cyclone gas/sólido" if is_cyc else
                   "Decanter líquido-líquido" if is_dec else
                   "Filter / Centrifuge")
            help_text = (
                "El solver reparte el feed entre la salida target (la fase "
                "objetivo × η) y la reject.  Para el decanter, target = fase "
                "pesada (split por densidad).")
            l.addLayout(self._section_header(
                "Separación mecánica (η declarada)", sub=sub,
                help_text=help_text))
            init_active = (getattr(b, "mech_sep_active", False)
                           or getattr(b, "separator_active", False)
                           or getattr(b, "cyclone_active", False))
            self._add_active_toggle(l, "mech_sep_active",
                                    "Activar separación automática",
                                    init_active)
            # Eficiencia η — inicial desde mech o, si no, del legacy.
            eff = float(getattr(b, "mech_sep_efficiency", 0.0) or 0.0)
            if eff <= 0:
                eff = float((getattr(b, "collection_efficiency", 0.90) if is_cyc
                             else getattr(b, "solids_recovery", 0.95)) or 0.95)
            l.addWidget(self._row(
                "Eficiencia η",
                self._spec_field("mech_sep_efficiency", value=f"{eff:.3f}",
                                 unit="·", state="spec"),
                info="Fracción de la fase objetivo recuperada en la salida target"))
            # Fase objetivo (combo)
            default_tp = (getattr(b, "mech_sep_target_phase", "") or
                          ("liquid" if is_dec else "solid"))
            tp = QComboBox()
            for ph in ("solid", "liquid", "vapor"):
                tp.addItem(ph, ph)
            try:
                tp.setCurrentIndex(["solid", "liquid", "vapor"].index(default_tp))
            except ValueError:
                tp.setCurrentIndex(0)
            tp.setEnabled(not is_dec)   # decanter siempre pesada-por-densidad
            self._extras["mech_sep_target_phase"] = tp
            l.addWidget(self._row(
                "Fase objetivo", tp,
                info=("Decanter: fase pesada por densidad" if is_dec
                      else "solid / liquid / vapor")))
            if not is_dec:
                sc = QLineEdit(",".join(getattr(b, "solid_components", []) or []))
                sc.setPlaceholderText("sucrose, silica, …  (vacío = heurístico por fase)")
                sc.setStyleSheet(self._line_input_style())
                self._extras["solid_components"] = sc
                l.addWidget(self._row(
                    "Componentes target", sc,
                    info="Override explícito de qué componentes son la fase objetivo"))

        elif _is_dryer(eq_type):
            l.addLayout(self._section_header(
                "Secador (Dryer — drum)",
                help_text="Solver computa producto seco a humedad final + "
                          "venteo del vapor del moisture_component."
            ))
            self._add_active_toggle(l, "dryer_active",
                                    "Activar secador automático",
                                    getattr(b, "dryer_active", False))
            fm = float(getattr(b, "final_moisture", 0.02) or 0.02)
            l.addWidget(self._row("Humedad final",
                                  self._spec_field("final_moisture",
                                                   value=f"{fm:.3f}",
                                                   unit="·", state="spec")))
            mc = QLineEdit(getattr(b, "moisture_component", "water") or "water")
            mc.setStyleSheet(self._line_input_style())
            self._extras["moisture_component"] = mc
            l.addWidget(self._row("Moisture comp.", mc,
                                  info="Componente que se evapora (default: water)"))

        elif _is_crystallizer(eq_type):
            l.addLayout(self._section_header(
                "Cristalizador",
                help_text="Solver extrae solute_component a cristales según "
                          "crystal_yield; el resto va a la madre."
            ))
            self._add_active_toggle(l, "crystallizer_active",
                                    "Activar cristalizador automático",
                                    getattr(b, "crystallizer_active", False))
            sl = QLineEdit(getattr(b, "solute_component", "") or "")
            sl.setPlaceholderText("sucrose, urea, …")
            sl.setStyleSheet(self._line_input_style())
            self._extras["solute_component"] = sl
            l.addWidget(self._row("Solute comp.", sl))
            cy = float(getattr(b, "crystal_yield", 0.80) or 0.80)
            l.addWidget(self._row("Crystal yield",
                                  self._spec_field("crystal_yield",
                                                   value=f"{cy:.3f}",
                                                   unit="·", state="spec")))

        elif _is_evaporator(eq_type):
            l.addLayout(self._section_header(
                "Evaporador",
                help_text="Solver concentra los sólidos según concentration "
                          "factor; el volátil sale como vapor."
            ))
            self._add_active_toggle(l, "evaporator_active",
                                    "Activar evaporador automático",
                                    getattr(b, "evaporator_active", False))
            cf = float(getattr(b, "concentration_factor", 2.0) or 2.0)
            l.addWidget(self._row("Concentration factor",
                                  self._spec_field("concentration_factor",
                                                   value=f"{cf:.2f}",
                                                   unit="·", state="spec"),
                                  info="Ratio sólidos out/in (e.g. 2.0 → masa cae a la mitad)"))
            vc = QLineEdit(getattr(b, "volatile_component", "water") or "water")
            vc.setStyleSheet(self._line_input_style())
            self._extras["volatile_component"] = vc
            l.addWidget(self._row("Volatile comp.", vc))

        else:
            empty = QLabel("(No hay modos especiales para este tipo de bloque)")
            empty.setStyleSheet(f"color:{TOK['ink_soft']}; font-style:italic;")
            l.addWidget(empty)

        return sect

    # ---- helpers compartidos ----
    def _add_active_toggle(self, layout, key: str, label: str, checked: bool):
        cb = QCheckBox(label)
        cb.setChecked(bool(checked))
        cb.setFont(QFont(pfd_fonts.SANS, 9))
        cb.setStyleSheet(self._checkbox_style())
        self._extras[key] = cb
        layout.addWidget(cb)

    def _combo_row(self, label: str, combo) -> QFrame:
        """Row con label + combo (usado en lugar de _row + SpecField)."""
        r = QFrame()
        lay = QHBoxLayout(r); lay.setContentsMargins(0, ROW_PAD//2, 0, ROW_PAD//2)
        lay.setSpacing(12)
        l = QLabel(label)
        l.setFont(QFont(pfd_fonts.SANS, 9))
        l.setStyleSheet(f"color:{TOK['ink_mute']};")
        l.setMinimumWidth(140)
        lay.addWidget(l); lay.addWidget(combo, 1)
        r.setStyleSheet(
            f"#combo_row {{ border-bottom: 1px solid {TOK['line_soft']}; }}"
        )
        return r

    @staticmethod
    def _checkbox_style() -> str:
        return (
            f"QCheckBox {{ color: {TOK['ink']}; spacing: 8px; padding: 4px 0; }} "
            f"QCheckBox::indicator {{ width: 16px; height: 16px; "
            f"border: 1.5px solid {TOK['line_strong']}; "
            f"border-radius: 4px; background: {TOK['bg_elev']}; }} "
            f"QCheckBox::indicator:checked {{ background: {TOK['accent']}; "
            f"border-color: {TOK['accent']}; image: none; }} "
            f"QCheckBox::indicator:hover {{ border-color: {TOK['accent_soft']}; }}"
        )

    @staticmethod
    def _line_input_style() -> str:
        return (
            f"QLineEdit {{ background: {TOK['bg_elev']}; color: {TOK['ink']}; "
            f"border: 1px solid {TOK['line_strong']}; border-radius: 7px; "
            f"padding: 6px 8px; font-family: '{pfd_fonts.SANS}'; font-size: 9pt; }} "
            f"QLineEdit:focus {{ border: 1.5px solid {TOK['accent']}; }} "
            f"QLineEdit::placeholder {{ color: {TOK['ink_ghost']}; }}"
        )

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
            # WHB Sinnott: panel especial con barra de rango de escala
            vm = self._hx_viewmodel()
            if vm and vm.get("whb"):
                try:
                    import hx_inspector as hxui
                    l.addWidget(hxui.WHBSubcomponent(vm["whb"], self._open_hx_topic))
                except Exception:
                    pass
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

        # HX: badge de correlación (Turton/Sinnott) + chip de instalación
        if _is_hx(eq_type):
            try:
                import hx_inspector as hxui
                badges = hxui.make_correlation_badges(b, self._open_hx_topic)
                if badges:
                    l.addWidget(badges)
            except Exception:
                pass

        # CBM (read-only, derivado)
        cbm = self._compute_cbm(b)
        cbm_str = f"{cbm:,.0f}".replace(",", " ") if cbm else "—"
        sf_cbm = self._spec_field("CBM_readonly",
                                  value=cbm_str,
                                  unit="USD", state="auto", allow_toggle=False)
        l.addWidget(self._row("C_BM (bare module)", sf_cbm))
        return sect

    # ─── Diagnóstico ─────────────────────────────────────
    def _section_diagnostico(self, b, eq_type) -> QFrame:
        """Evidencia textual del solver + figuras matplotlib (cuando aplica).
        Single source of truth: inspector_evidence (modulo Qt-free)."""
        sect = QFrame()
        l = QVBoxLayout(sect); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(8)
        l.addLayout(self._section_header(
            "Diagnóstico",
            help_text="Evidencia textual y gráfica de los cálculos del solver "
                      "para este bloque (T, presión, conversión, ΔP itemizado, "
                      "McCabe-Thiele, perfil tray-by-tray, flash VLE)."
        ))

        try:
            import inspector_evidence as _ev
        except Exception as exc:
            err = QLabel(f"⚠ inspector_evidence no disponible: {exc}")
            err.setWordWrap(True)
            err.setFont(QFont(pfd_fonts.SANS, 9))
            err.setStyleSheet(f"color:{TOK['danger']};")
            l.addWidget(err)
            return sect

        fs = self.fs
        any_added = False

        # 1) Bloques de texto por tipo de equipo --------------------
        text_blocks: List[Tuple[str, Optional[str]]] = [
            ("Reactor",                _ev.reactor_text(b)),
            ("Intercambiador (HX)",    _ev.hx_text(b)),
            ("Flash",                  _ev.flash_text(b)),
            ("Separador mecánico",     _ev.mech_sep_text(b)),
            ("Splitter",               _ev.splitter_text(b)),
            ("Tanque",                 _ev.tank_text(b, fs)),
            ("Columna — McCabe",       _ev.mccabe_text(b, fs)),
            ("Columna — Perfil",       _ev.profile_text(b, fs)),
            ("Bomba",                  _ev.pump_text(b, fs)),
            ("Compresor",              _ev.compressor_text(b, fs)),
            ("Hidráulica (ΔP)",        _ev.hydraulic_breakdown_text(b, fs)),
        ]
        for title, txt in text_blocks:
            if not txt:
                continue
            l.addWidget(self._diag_text_card(title, txt))
            any_added = True

        # 2) Figuras matplotlib (si el backend Qt está disponible) ----
        canvas_widgets = self._diag_figures(b, fs)
        for w in canvas_widgets:
            l.addWidget(w)
            any_added = True

        if not any_added:
            ph = QLabel("Sin evidencia disponible para este bloque "
                        "(el solver aún no produjo diagnóstico o el tipo "
                        "no tiene métricas asociadas).")
            ph.setWordWrap(True)
            ph.setFont(QFont(pfd_fonts.SANS, 9))
            ph.setStyleSheet(f"color:{TOK['ink_soft']}; font-style:italic;")
            l.addWidget(ph)

        return sect

    def _diag_text_card(self, title: str, body: str) -> QFrame:
        """Tarjeta con título + cuerpo monospace para un bloque de evidencia."""
        card = QFrame(); card.setObjectName("diagCard")
        cl = QVBoxLayout(card); cl.setContentsMargins(10, 8, 10, 8); cl.setSpacing(4)
        t = QLabel(title)
        t.setFont(QFont(pfd_fonts.SANS, 9, QFont.Bold))
        t.setStyleSheet(f"color:{TOK['ink']};")
        cl.addWidget(t)
        body_lbl = QLabel(body)
        body_lbl.setFont(QFont(pfd_fonts.MONO, 9))
        body_lbl.setStyleSheet(f"color:{TOK['ink']};")
        body_lbl.setWordWrap(True)
        body_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        cl.addWidget(body_lbl)
        card.setStyleSheet(
            f"#diagCard {{ background: {TOK['bg_mute']}; "
            f"border: 1px solid {TOK['line']}; border-radius: 6px; }}"
        )
        return card

    def _diag_figures(self, b, fs) -> List[QWidget]:
        """Crea canvases QtAgg para las figuras disponibles.  Devuelve [] si
        matplotlib-Qt no está, o si ninguna figura aplica."""
        out: List[QWidget] = []
        try:
            import matplotlib
            matplotlib.use("QtAgg")
            from matplotlib.backends.backend_qtagg import (
                FigureCanvas as _MplCanvas
            )
        except Exception:
            return out
        try:
            import inspector_evidence as _ev
        except Exception:
            return out

        # McCabe + Profile para columnas
        if getattr(b, "column_active", False):
            try:
                fig, _d = _ev.mccabe_figure(b, fs)
                if fig is not None:
                    out.append(self._diag_canvas_card(
                        "McCabe-Thiele", _MplCanvas(fig)))
            except Exception:
                pass
            try:
                fig, _p = _ev.profile_figure(b, fs)
                if fig is not None:
                    out.append(self._diag_canvas_card(
                        "Perfil tray-by-tray", _MplCanvas(fig)))
            except Exception:
                pass

        # Flash binario para Vessels con flash_active
        if getattr(b, "flash_active", False):
            try:
                fig, _f = _ev.flash_figure(b, fs)
                if fig is not None:
                    out.append(self._diag_canvas_card(
                        "Flash VLE binario", _MplCanvas(fig)))
            except Exception:
                pass

        return out

    def _diag_canvas_card(self, title: str, canvas) -> QFrame:
        """Tarjeta con título + canvas matplotlib embebido."""
        card = QFrame(); card.setObjectName("diagCard")
        cl = QVBoxLayout(card); cl.setContentsMargins(10, 8, 10, 8); cl.setSpacing(6)
        t = QLabel(title)
        t.setFont(QFont(pfd_fonts.SANS, 9, QFont.Bold))
        t.setStyleSheet(f"color:{TOK['ink']};")
        cl.addWidget(t)
        canvas.setMinimumHeight(280)
        cl.addWidget(canvas)
        card.setStyleSheet(
            f"#diagCard {{ background: {TOK['bg_elev']}; "
            f"border: 1px solid {TOK['line']}; border-radius: 6px; }}"
        )
        return card

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
            if cbm >= 1e6:
                s = f"${cbm/1e6:.2f}M"
            self._stat_capex_val.setText(s + " USD")
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

        # Stats derivados HX: Área (o Steam si WHB) + ΔT_lm·F efectivo
        hx_stats = getattr(self, "_stat_hxA_lbl", None)
        if hx_stats is not None:
            show = _is_hx(b.eq_type)
            if show:
                vm = self._hx_viewmodel()
                if vm and vm.get("whb"):
                    self._stat_hxA_lbl.setText("Steam")
                    self._stat_hxA_val.setText(
                        f"{int(round(vm['whb']['steam_kg_per_h'])):,}".replace(",", " ")
                        + " kg/h")
                else:
                    self._stat_hxA_lbl.setText("Área")
                    S = float(getattr(b, "S", 0) or 0)
                    self._stat_hxA_val.setText(f"{S:,.0f} m²".replace(",", " ") if S else "—")
                dtlm = (vm or {}).get("dTlm")
                F = (vm or {}).get("F", 1.0)
                if dtlm is not None:
                    eff = dtlm * F
                    bad = (vm and (vm.get("approach") is not None
                           and vm["approach"] < 0 or F < 0.75))
                    self._stat_hxdt_val.setText(f"{eff:.1f} K")
                    self._stat_hxdt_val.setStyleSheet(
                        f"color:{TOK['danger'] if bad else TOK['ink_mute']};")
                else:
                    self._stat_hxdt_val.setText("—")
            # Área/Steam siempre que sea HX; ΔT_lm·F sólo si está disponible
            self._stat_hxA_lbl.setVisible(show)
            self._stat_hxA_val.setVisible(show)
            dt_ok = show and (vm or {}).get("dTlm") is not None
            self._stat_hxdt_lbl.setVisible(dt_ok)
            self._stat_hxdt_val.setVisible(dt_ok)

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
        # invalida el view-model HX: S/duty pudieron cambiar tras el solver
        self._hx_vm_cache = None
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
        # custom reactions (lista in-memory de dicts)
        if hasattr(self, "_custom_rxns_data"):
            b.custom_reactions = list(self._custom_rxns_data)
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
        if "column_active" in self._extras:
            b.column_active = bool(self._extras["column_active"].isChecked())
        if "column_LK" in self._extras:
            b.column_LK = self._extras["column_LK"].text().strip()
        if "column_HK" in self._extras:
            b.column_HK = self._extras["column_HK"].text().strip()
        # ─── Flash VLE ───
        if "flash_active" in self._extras:
            b.flash_active = bool(self._extras["flash_active"].isChecked())
        for key in ("flash_T_K", "flash_P_bar"):
            if key in f:
                v = self._parse_num(f[key].value())
                try:
                    setattr(b, key, float(v) if v else 0.0)
                except Exception:
                    pass
        # ─── Modos especiales ───
        for key in ("separator_active", "dryer_active", "crystallizer_active",
                    "evaporator_active", "cyclone_active"):
            if key in self._extras:
                setattr(b, key, bool(self._extras[key].isChecked()))
        # Separador mecánico unificado (mech_sep_active): al guardarlo se
        # limpia el legacy separator/cyclone_active → mech es la única fuente.
        if "mech_sep_active" in self._extras:
            b.mech_sep_active = bool(self._extras["mech_sep_active"].isChecked())
            if b.mech_sep_active:
                b.separator_active = False
                b.cyclone_active = False
        if "mech_sep_target_phase" in self._extras:
            cb = self._extras["mech_sep_target_phase"]
            b.mech_sep_target_phase = cb.currentData() or "solid"
        for key in ("solids_recovery", "cake_moisture", "final_moisture",
                    "crystal_yield", "concentration_factor",
                    "collection_efficiency", "mech_sep_efficiency"):
            if key in f:
                v = self._parse_num(f[key].value())
                try:
                    setattr(b, key, float(v) if v else 0.0)
                except Exception:
                    pass
        for key in ("solute_component", "moisture_component", "volatile_component"):
            if key in self._extras:
                setattr(b, key, self._extras[key].text().strip())
        if "solid_components" in self._extras:
            txt = self._extras["solid_components"].text().strip()
            b.solid_components = [t.strip() for t in txt.split(",")
                                  if t.strip()] if txt else []
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


# ════════════════════════════════════════════════════════
#  PREFERENCIAS — diálogo
# ════════════════════════════════════════════════════════

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QRadioButton


class PreferencesDialog(QDialog):
    """Pequeño diálogo accesible desde Vista > Preferencias…

    Tres grupos exclusivos: Tema (light/dark), Densidad
    (compact/cozy/comfy), Acento (teal/terracota/cobalto/oliva).

    Al pulsar Aplicar: muta TOK + persiste a disco + emite
    PrefsBus.signal() para que widgets vivos se reconstruyan.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferencias")
        self.setMinimumWidth(420)
        cur = current_prefs()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20); lay.setSpacing(18)

        # ── Tema ──
        lay.addWidget(self._group_title("Tema"))
        self._theme_group = QButtonGroup(self)
        themes_row = QHBoxLayout(); themes_row.setSpacing(10)
        for key, label in [("light", "Claro"), ("dark", "Oscuro")]:
            rb = QRadioButton(label)
            rb.setChecked(cur["theme"] == key)
            rb.setProperty("value", key)
            self._theme_group.addButton(rb)
            themes_row.addWidget(rb)
        themes_row.addStretch(1)
        wrap = QFrame(); wrap.setLayout(themes_row); lay.addWidget(wrap)

        # ── Densidad ──
        lay.addWidget(self._group_title("Densidad"))
        self._density_group = QButtonGroup(self)
        dens_row = QHBoxLayout(); dens_row.setSpacing(10)
        for key, label in [("compact", "Compacta"), ("cozy", "Cómoda"),
                           ("comfy", "Amplia")]:
            rb = QRadioButton(label)
            rb.setChecked(cur["density"] == key)
            rb.setProperty("value", key)
            self._density_group.addButton(rb)
            dens_row.addWidget(rb)
        dens_row.addStretch(1)
        wrap = QFrame(); wrap.setLayout(dens_row); lay.addWidget(wrap)

        # ── Acento ──
        lay.addWidget(self._group_title("Color de acento"))
        self._accent_group = QButtonGroup(self)
        acc_row = QHBoxLayout(); acc_row.setSpacing(10)
        for key, label in [("teal", "Teal"), ("terracota", "Terracota"),
                           ("cobalto", "Cobalto"), ("oliva", "Oliva")]:
            rb = QRadioButton(label)
            rb.setChecked(cur["accent"] == key)
            rb.setProperty("value", key)
            self._accent_group.addButton(rb)
            # swatch
            swatch_color = ACCENTS[key]["accent"]
            rb.setStyleSheet(
                f"QRadioButton::indicator {{ width: 14px; height: 14px; }} "
                f"QRadioButton {{ padding: 4px 8px; "
                f"border-left: 4px solid {swatch_color}; "
                f"padding-left: 10px; }}"
            )
            acc_row.addWidget(rb)
        acc_row.addStretch(1)
        wrap = QFrame(); wrap.setLayout(acc_row); lay.addWidget(wrap)

        # nota
        note = QLabel(
            "Tema y acento se aplican al Inspector inmediatamente. "
            "El editor (topbar, paleta, zoom) toma el nuevo estilo al "
            "reiniciar la app."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{TOK['ink_soft']}; font-size:9pt; "
            f"background:{TOK['bg_mute']}; padding:8px; border-radius:6px;"
        )
        lay.addWidget(note)

        # botones
        bb = QDialogButtonBox(
            QDialogButtonBox.Apply | QDialogButtonBox.Close, parent=self
        )
        bb.button(QDialogButtonBox.Apply).setText("Aplicar")
        bb.button(QDialogButtonBox.Close).setText("Cerrar")
        bb.button(QDialogButtonBox.Apply).clicked.connect(self._do_apply)
        bb.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        lay.addWidget(bb)

    def _group_title(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setFont(QFont(pfd_fonts.SANS, 10, QFont.Bold))
        l.setStyleSheet(f"color:{TOK['ink']}; letter-spacing:0.5px;")
        return l

    def _picked(self, group: QButtonGroup) -> Optional[str]:
        btn = group.checkedButton()
        if btn is None: return None
        return btn.property("value")

    def _do_apply(self):
        theme   = self._picked(self._theme_group)
        density = self._picked(self._density_group)
        accent  = self._picked(self._accent_group)
        changed = apply_preferences(theme=theme, density=density, accent=accent)
        if changed:
            save_prefs_to_disk()
            _PrefsBus.emit()
