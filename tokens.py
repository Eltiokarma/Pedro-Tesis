"""
tokens.py — sistema de diseño único del frontend (artboard 1a del rediseño).

Fuente canónica de:
  · TOK        — paleta viva (tema claro/oscuro + acento), mutada in-place
  · estados    — mapeo semántico status-del-solver → token de color
  · tipografía — los 4 tamaños oficiales
  · strokes    — los 2 pesos oficiales de trazo de glifo
  · formato    — el formateador único de dinero / porcentaje / años

Históricamente TOK vivía en block_inspector.py; se promovió acá para que
canvas, topbar, inspector, economía y las figuras matplotlib consuman el
mismo módulo.  block_inspector re-exporta estos nombres por compatibilidad.

Headless-safe: no importa Qt a nivel de módulo (el bus de preferencias
hace lazy-import de PySide6 recién cuando alguien se suscribe).
"""

import os
import json

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
    # fases (dots LIQ/VAP/GAS/2-φ — artboard 2a familia 6: set cohesivo
    # líquido=azul frío, vapor=ámbar cálido, gas=gris pálido, 2φ=violeta)
    "phase_liq":    "#2f6690",
    "phase_vap":    "#c47a1e",
    "phase_gas":    "#8a8172",
    "phase_2ph":    "#6d5a9c",
    # ── capa canvas (artboard 2a) ──
    # papel y grilla — el papel es plano de dibujo, no panel
    "canvas_bg":         "#fbfaf6",
    "canvas_grid":       "#eae5d9",
    "canvas_grid_major": "#ddd6c6",
    # puertos — paleta técnica propia (8 clases, ordenadas frío→cálido;
    # NO derivan del acento ni del semáforo)
    "port_process_in":  "#4f7a3a",
    "port_process_out": "#2f6690",
    "port_utility_in":  "#c86a12",
    "port_utility_out": "#b0442a",
    "port_fuel":        "#6d4a2f",
    "port_vent":        "#8a8172",
    "port_drain":       "#4a5a63",
    "port_aux":         "#6d5a9c",
    # servicio por temperatura (el matiz ES el significado)
    "service_hot":       "#d5501f",
    "service_hot_pale":  "#f4c8a8",
    "service_hot_deep":  "#a8320f",
    "service_cold":      "#2b8fc4",
    "service_cold_pale": "#bfe0f0",
    "service_cold_deep": "#125f88",
    # roles de stream (selección = +peso de trazo + halo accent_soft,
    # nunca un hex distinto del rol)
    "stream_internal": "#2a2620",
    "stream_product":  "#b8323f",
    "stream_utility":  "#2f4d9e",
    "stream_waste":    "#6d4c41",
    # labels on-canvas y duty badges (atados al eje de servicio)
    "label_bg":       "#e0ffffff",   # #AARRGGBB — pill al 88 %
    "label_ink":      "#26221c",
    "label_ink_soft": "#6b6256",
    "duty_hot":       "#b8323f",
    "duty_cold":      "#2f6690",
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
#  ESTADOS DEL SOLVER — un solo semáforo (artboard 1a/1b)
# ════════════════════════════════════════════════════════
# Reemplaza la paleta Material que vivía en flowsheet_qt (STATUS_COLORS:
# #2e7d32/#f9a825/#c62828/#1976d2/#7b1fa2).  Cada status resuelve a un
# token de TOK, así el semáforo respira el tema activo.

STATUS_TOKEN = {
    "ok":      "green",
    "warning": "amber",
    "error":   "danger",
    "stale":   "ink_soft",   # desaturado — "esto ya no vale"
    "unrun":   "ink_mute",   # punteado en el glifo
    "empty":   "ink_mute",
}

# Tinte de relleno por estado (fill del glifo). None = fill neutro bg_elev.
# ok SÍ tinta: el lienzo está lleno de dots de puertos de colores y un
# "éxito silencioso" resultaba invisible — el equipo debe cambiar de
# color al resolver (feedback de uso post-rediseño).
STATUS_FILL_TOKEN = {
    "ok":      "green_bg",
    "warning": "amber_bg",
    "error":   "danger_bg",
    "stale":   None,
    "unrun":   None,
    "empty":   None,
}


def status_hex(status: str) -> str:
    """Color (hex) del semáforo para un status del solver, leído en
    caliente de TOK — respeta tema/acento activos."""
    return TOK[STATUS_TOKEN.get(status, "ink_mute")]


def status_fill_hex(status: str):
    """Tinte de relleno (hex) para el cuerpo del glifo, o None si el
    estado usa el fill neutro (bg_elev)."""
    key = STATUS_FILL_TOKEN.get(status)
    return TOK[key] if key else None


# ════════════════════════════════════════════════════════
#  SEVERIDAD — una sola escala (artboard 2a familia 5)
# ════════════════════════════════════════════════════════
# Estaba triplicada (badges del canvas, dock de reactividad, chips) con
# hex propios (#c41e3a/#e57c00/#f4b400/#9ca3af).  Se alinea con los
# tokens semánticos existentes → hereda el par dark gratis.

SEVERITY_TOKEN = {
    "critical": "danger",
    "high":     "orange",
    "medium":   "amber",
    "low":      "ink_soft",
}


def severity_hex(severity: str) -> str:
    """Color (hex) para una severidad de warning, leído en caliente."""
    return TOK[SEVERITY_TOKEN.get(severity, "ink_soft")]


# ════════════════════════════════════════════════════════
#  TIPOGRAFÍA — 4 tamaños (artboard 1a)
# ════════════════════════════════════════════════════════
# (familia, pt, peso QFont).  Las familias se resuelven vía pfd_fonts si
# los Plex están embebidos; estos nombres son los canónicos.

FONT_DISPLAY = ("IBM Plex Sans", 26, 700) # KPI hero (solo panel económico)
FONT_TITLE = ("IBM Plex Sans", 15, 600)   # títulos de panel/diálogo
FONT_UI    = ("IBM Plex Sans", 12, 400)   # texto de interfaz · botones · celdas
FONT_VALUE = ("IBM Plex Mono", 11.5, 500) # valores numéricos · tabular
FONT_HINT  = ("IBM Plex Sans", 11, 400)   # hint/caption · subtexto de KPI
FONT_LABEL = ("IBM Plex Sans", 10, 600)   # labels/kickers · caps (mínimo del sistema)


def qfont(spec):
    """QFont desde un token de tipografía (familia, pt, peso 100-900).

    Único constructor de fuentes del frontend: resuelve la familia vía
    pfd_fonts (fallback si los Plex no están embebidos) y usa la escala
    de pesos CSS que Qt6 adopta nativamente.  Import lazy de Qt para
    mantener el módulo headless-safe.
    """
    from PySide6.QtGui import QFont
    fam, pt, weight = spec
    try:
        import pfd_fonts
        if "Mono" in fam:
            fam = pfd_fonts.MONO
        elif "Sans" in fam:
            fam = pfd_fonts.SANS
    except Exception:
        pass
    f = QFont(fam)
    f.setPointSizeF(float(pt))
    f.setWeight(QFont.Weight(int(weight)))
    return f


# ════════════════════════════════════════════════════════
#  ESCALA DE TARJETA COMPACTA ON-CANVAS — 4ª escala (ciclo 4, 4e)
# ════════════════════════════════════════════════════════
# Design ratificó la excepción de stream_bubbles / hx_bubbles como
# escala OFICIAL del sistema (bundle ciclo 4, artboard 4e) — NO migra
# a FONT_LABEL/VALUE porque rompería la densidad de 50+ burbujas.
#
# Regla que la separa del sistema tipográfico:
#   · físico FIJO (panel, tabla, diálogo — no zooma) → FONT_*
#   · escala CON LA ESCENA (burbujas, labels de plano) → escala
#     compacta on-canvas
#
# Valores documentados (px de referencia del bundle):
#   valor    Mono 9/600 · etiqueta Sans 8/600 upper ·
#   unidad   Sans 8/400 ink_soft · mínimo absoluto on-canvas 7
# (Los widgets de burbuja los consumen como px/pt directos — son
# tamaños de tarjeta compacta, deliberadamente bajo FONT_LABEL.)
COMPACT_VALUE_PX = 9
COMPACT_LABEL_PX = 8
COMPACT_MIN_PX   = 7

# Degradación (4e): a zoom < 0.5 la burbuja colapsa a solo número +
# dot de fase — con 50+ burbujas en pantalla la densidad manda.
BUBBLE_COLLAPSE_ZOOM = 0.5


# ════════════════════════════════════════════════════════
#  STROKES — 2 pesos (artboard 1a)
# ════════════════════════════════════════════════════════
# Reemplazan los 0.9–2.5 dispersos en los _draw_* de glifos.

STROKE_OUTLINE = 1.6   # contorno de glifo
STROKE_DETAIL  = 1.0   # detalle interno


# ════════════════════════════════════════════════════════
#  FORMATO ÚNICO — dinero / porcentaje / años (artboard 1a)
# ════════════════════════════════════════════════════════
# El único formateador del frontend.  Antes había cinco convenciones
# ("$ X,000", "$ X.XX MM", "X.XX M USD", "+X.XX", "X MUSD").

def fmt_musd(x, dec: int = 1, unit: str = "M USD") -> str:
    """Dinero en millones de USD: 12.5 M USD (unit='M' para tarjetas
    compactas, 'M/a' para flujos anuales).  x en USD."""
    if x is None:
        return "—"
    return f"{x / 1e6:,.{dec}f} {unit}"


def fmt_pct(x, dec: int = 1) -> str:
    """Porcentaje: 39.7 % (x ya en unidades de %)."""
    if x is None:
        return "—"
    return f"{x:,.{dec}f} %"


def fmt_years(x, dec: int = 1) -> str:
    """Años: 2.4 años."""
    if x is None:
        return "—"
    return f"{x:,.{dec}f} años"


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
    "phase_liq": "#2f6690", "phase_vap": "#c47a1e",
    "phase_gas": "#8a8172", "phase_2ph": "#6d5a9c",
    "canvas_bg": "#fbfaf6", "canvas_grid": "#eae5d9",
    "canvas_grid_major": "#ddd6c6",
    "port_process_in": "#4f7a3a", "port_process_out": "#2f6690",
    "port_utility_in": "#c86a12", "port_utility_out": "#b0442a",
    "port_fuel": "#6d4a2f", "port_vent": "#8a8172",
    "port_drain": "#4a5a63", "port_aux": "#6d5a9c",
    "service_hot": "#d5501f", "service_hot_pale": "#f4c8a8",
    "service_hot_deep": "#a8320f",
    "service_cold": "#2b8fc4", "service_cold_pale": "#bfe0f0",
    "service_cold_deep": "#125f88",
    "stream_internal": "#2a2620", "stream_product": "#b8323f",
    "stream_utility": "#2f4d9e", "stream_waste": "#6d4c41",
    "label_bg": "#e0ffffff", "label_ink": "#26221c",
    "label_ink_soft": "#6b6256",
    "duty_hot": "#b8323f", "duty_cold": "#2f6690",
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
    "phase_liq": "#6fa8d6", "phase_vap": "#e0a94e",
    "phase_gas": "#b3a892", "phase_2ph": "#a795d6",
    "canvas_bg": "#221d15", "canvas_grid": "#2c2519",
    "canvas_grid_major": "#38301f",
    "port_process_in": "#8fb46a", "port_process_out": "#6fa8d6",
    "port_utility_in": "#e0a94e", "port_utility_out": "#d98a68",
    "port_fuel": "#b08a63", "port_vent": "#b3a892",
    "port_drain": "#8ba0aa", "port_aux": "#a795d6",
    "service_hot": "#e88a5a", "service_hot_pale": "#5a3320",
    "service_hot_deep": "#f0a877",
    "service_cold": "#63b8e0", "service_cold_pale": "#1e3a4a",
    "service_cold_deep": "#8fcdec",
    "stream_internal": "#d8cfbf", "stream_product": "#e07a82",
    "stream_utility": "#8595d8", "stream_waste": "#b39a8a",
    "label_bg": "#e626211a", "label_ink": "#efe7d6",
    "label_ink_soft": "#a59a89",
    "duty_hot": "#e07a82", "duty_cold": "#6fa8d6",
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
