"""
EQUIPMENT ICONS — íconos SVG para cada tipo de equipo de PFD.

Cada SVG está hardcoded como string Python en viewBox '0 0 130 60'
(coincide con BLOCK_W × BLOCK_H del flowsheet_model).

Diseño:
  · Estilo ISA-5.1 / industria química, simplificado para legibilidad
  · Paleta consistente (azules para acero, naranja para llama, gris
    para tubos internos)
  · Líneas delgadas (1.5 px stroke) para que el texto del bloque
    (nombre + S) quede legible encima

El editor Qt carga estos via QSvgRenderer + QGraphicsSvgItem.
Si el SVG no se puede renderizar (PySide6 sin QtSvg), el editor
hace fallback a los Qt paths simples de phase C.

API pública:

  get_icon_svg(eq_type) → string SVG o None si no hay ícono específico
"""


# ======================================================
# COLORES (paleta unificada con el resto del editor)
# ======================================================
# Definidos como constantes Python para no tener que repetir en cada SVG.
# Inyectados via .format() al construir cada SVG_ICON.

_C_OUTLINE   = "#5c6bc0"        # borde principal (índigo)
_C_OUTLINE_2 = "#283593"        # borde marcado (índigo oscuro)
_C_GRAY      = "#90a4ae"        # tubos / detalles internos
_C_BG_BLUE   = "#e3f2fd"        # vessels (proceso)
_C_BG_GREEN  = "#e8f5e9"        # storage / agua
_C_BG_YELLOW = "#fff8e1"        # hornos
_C_BG_RED    = "#fbe9e7"        # reactores
_C_BG_ORANGE = "#fff3e0"        # compresores
_C_BG_CYAN   = "#e1f5fe"        # fans
_C_BG_GRAY   = "#efebe9"        # solids
_C_BG_INDIGO = "#e8eaf6"        # bombas
_C_FLAME     = "#ff6f00"
_C_FLAME_DK  = "#bf360c"


def _svg(body):
    """Envuelve un body en un SVG bien formado."""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 130 60" width="130" height="60">'
        f'{body}'
        f'</svg>'
    )


# ======================================================
# HEAT EXCHANGERS
# ======================================================

# Shell-and-tube: rectángulo con extremos curvados, líneas internas
# que representan el banco de tubos, y baffles en líneas punteadas.
SVG_HX_SHELL_TUBE = _svg(f"""
  <rect x="18" y="16" width="94" height="28" rx="3"
        fill="#fff" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="22" y1="22" x2="108" y2="22" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="22" y1="30" x2="108" y2="30" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="22" y1="38" x2="108" y2="38" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="42" y1="18" x2="42" y2="42" stroke="{_C_GRAY}" stroke-width="0.6" stroke-dasharray="2,2"/>
  <line x1="65" y1="18" x2="65" y2="42" stroke="{_C_GRAY}" stroke-width="0.6" stroke-dasharray="2,2"/>
  <line x1="88" y1="18" x2="88" y2="42" stroke="{_C_GRAY}" stroke-width="0.6" stroke-dasharray="2,2"/>
""")

# Air cooler: bank de tubos finos sobre una base con aletas dibujadas
SVG_HX_AIR_COOLER = _svg(f"""
  <rect x="18" y="18" width="94" height="24" rx="2"
        fill="#fff" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="22" y1="24" x2="108" y2="24" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="22" y1="30" x2="108" y2="30" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="22" y1="36" x2="108" y2="36" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <!-- aletas de cooling fan abajo -->
  <circle cx="40" cy="50" r="6" fill="{_C_BG_CYAN}" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <line x1="40" y1="46" x2="40" y2="54" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="36" y1="50" x2="44" y2="50" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <circle cx="90" cy="50" r="6" fill="{_C_BG_CYAN}" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <line x1="90" y1="46" x2="90" y2="54" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="86" y1="50" x2="94" y2="50" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
""")

# Kettle reboiler: forma característica con un domo arriba
SVG_HX_KETTLE = _svg(f"""
  <path d="M 18 38 L 18 25 Q 18 14 35 12 L 95 12 Q 112 14 112 25 L 112 38 Z"
        fill="{_C_BG_BLUE}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="22" y1="30" x2="108" y2="30" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="22" y1="36" x2="108" y2="36" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="25" y1="42" x2="105" y2="42" stroke="{_C_OUTLINE}" stroke-width="1"/>
""")

# Double pipe / multiple pipe: dos tubos concéntricos
SVG_HX_DOUBLE_PIPE = _svg(f"""
  <rect x="15" y="20" width="100" height="20" rx="10"
        fill="#fff" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <rect x="22" y="25" width="86" height="10" rx="5"
        fill="{_C_BG_BLUE}" stroke="{_C_OUTLINE}" stroke-width="1"/>
""")


# ======================================================
# PUMPS
# ======================================================

# Centrifugal: círculo + impulsor con flecha curva
SVG_PUMP_CENTRIFUGAL = _svg(f"""
  <circle cx="65" cy="30" r="18" fill="{_C_BG_INDIGO}"
          stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- impulsor: curva con flecha al final -->
  <path d="M 53 30 Q 60 14 75 28"
        fill="none" stroke="{_C_OUTLINE_2}" stroke-width="2"
        stroke-linecap="round"/>
  <polygon points="75,28 71,24 74,32" fill="{_C_OUTLINE_2}"/>
  <!-- líneas radiales (palas internas) -->
  <line x1="65" y1="30" x2="65" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="65" y1="30" x2="78" y2="38" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="65" y1="30" x2="52" y2="38" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
""")

# Positive displacement / reciprocating: cilindro horizontal con pistón
SVG_PUMP_RECIP = _svg(f"""
  <rect x="25" y="18" width="80" height="24" rx="3"
        fill="{_C_BG_INDIGO}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="35" y1="18" x2="35" y2="42" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <line x1="45" y1="20" x2="45" y2="40" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <!-- cigüeñal -->
  <circle cx="55" cy="30" r="4" fill="{_C_OUTLINE_2}"/>
  <line x1="55" y1="30" x2="100" y2="30" stroke="{_C_OUTLINE_2}" stroke-width="2"/>
""")


# ======================================================
# COMPRESSORS
# ======================================================

# Turbocompresor (axial / centrifugal / rotary):
# forma trapezoidal (entrada estrecha → salida ancha) con álabes
SVG_COMPRESSOR = _svg(f"""
  <path d="M 25 22 L 105 12 L 105 48 L 25 38 Z"
        fill="{_C_BG_ORANGE}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- álabes -->
  <line x1="55" y1="18" x2="55" y2="42" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="70" y1="15" x2="70" y2="45" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="85" y1="13" x2="85" y2="47" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
""")

# Reciprocating: cilindro con pistón (similar a pump_recip pero con
# acumulador esférico arriba)
SVG_COMPRESSOR_RECIP = _svg(f"""
  <rect x="25" y="22" width="80" height="24" rx="3"
        fill="{_C_BG_ORANGE}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- acumulador esférico -->
  <circle cx="65" cy="14" r="8" fill="{_C_BG_ORANGE}"
          stroke="{_C_OUTLINE}" stroke-width="1.2"/>
  <line x1="65" y1="22" x2="65" y2="22" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <!-- pistón -->
  <line x1="40" y1="22" x2="40" y2="46" stroke="{_C_OUTLINE_2}" stroke-width="1.5"/>
  <line x1="50" y1="22" x2="50" y2="46" stroke="{_C_OUTLINE_2}" stroke-width="1.5"/>
""")


# ======================================================
# REACTORS
# ======================================================

# Autoclave: vessel cilíndrico con extremos curvos
SVG_REACTOR_AUTOCLAVE = _svg(f"""
  <path d="M 30 14 Q 30 6 40 6 L 90 6 Q 100 6 100 14
           L 100 46 Q 100 54 90 54 L 40 54 Q 30 54 30 46 Z"
        fill="{_C_BG_RED}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
""")

# Jacketed con agitador: doble pared + eje con paletas
SVG_REACTOR_JACKETED = _svg(f"""
  <!-- chaqueta exterior -->
  <rect x="28" y="10" width="74" height="40" rx="4"
        fill="{_C_BG_RED}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- vessel interno -->
  <rect x="33" y="14" width="64" height="32" rx="3"
        fill="#fff" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <!-- eje del agitador -->
  <line x1="65" y1="2" x2="65" y2="36" stroke="{_C_OUTLINE_2}" stroke-width="2"/>
  <!-- motor (rect pequeño arriba) -->
  <rect x="60" y="0" width="10" height="6" fill="{_C_OUTLINE_2}"/>
  <!-- paletas (cruz Rushton) -->
  <line x1="54" y1="36" x2="76" y2="36" stroke="{_C_OUTLINE_2}" stroke-width="1.5"/>
  <line x1="56" y1="32" x2="56" y2="40" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <line x1="74" y1="32" x2="74" y2="40" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
""")

# Jacketed sin agitador: igual pero sin eje
SVG_REACTOR_JACKETED_NA = _svg(f"""
  <rect x="28" y="10" width="74" height="40" rx="4"
        fill="{_C_BG_RED}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <rect x="33" y="14" width="64" height="32" rx="3"
        fill="#fff" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <!-- líneas internas (tubos del lecho catalítico) -->
  <line x1="40" y1="18" x2="40" y2="42" stroke="{_C_GRAY}" stroke-width="0.6" stroke-dasharray="1,2"/>
  <line x1="55" y1="18" x2="55" y2="42" stroke="{_C_GRAY}" stroke-width="0.6" stroke-dasharray="1,2"/>
  <line x1="70" y1="18" x2="70" y2="42" stroke="{_C_GRAY}" stroke-width="0.6" stroke-dasharray="1,2"/>
  <line x1="85" y1="18" x2="85" y2="42" stroke="{_C_GRAY}" stroke-width="0.6" stroke-dasharray="1,2"/>
""")


# ======================================================
# VESSELS / TOWERS
# ======================================================

# Columna de destilación: rect alto + bandejas internas
SVG_TOWER = _svg(f"""
  <rect x="55" y="3" width="20" height="54" rx="8"
        fill="{_C_BG_BLUE}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="58" y1="12" x2="72" y2="12" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="58" y1="18" x2="72" y2="18" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="58" y1="24" x2="72" y2="24" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="58" y1="30" x2="72" y2="30" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="58" y1="36" x2="72" y2="36" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="58" y1="42" x2="72" y2="42" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="58" y1="48" x2="72" y2="48" stroke="{_C_GRAY}" stroke-width="0.8"/>
""")

# Vessel vertical: cilindro con extremos curvos (cap)
SVG_VESSEL_VERTICAL = _svg(f"""
  <path d="M 52 12 Q 52 4 65 4 Q 78 4 78 12
           L 78 48 Q 78 56 65 56 Q 52 56 52 48 Z"
        fill="{_C_BG_BLUE}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- línea de nivel del líquido -->
  <line x1="55" y1="38" x2="75" y2="38"
        stroke="{_C_OUTLINE}" stroke-width="0.8" stroke-dasharray="3,2"/>
""")

# Vessel horizontal: cilindro acostado
SVG_VESSEL_HORIZONTAL = _svg(f"""
  <path d="M 22 22 Q 14 22 14 30 Q 14 38 22 38
           L 108 38 Q 116 38 116 30 Q 116 22 108 22 Z"
        fill="{_C_BG_BLUE}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="20" y1="32" x2="110" y2="32"
        stroke="{_C_OUTLINE}" stroke-width="0.8" stroke-dasharray="3,2"/>
""")


# ======================================================
# STORAGE TANKS
# ======================================================

# Cone roof: techo cónico + cuerpo cilíndrico
SVG_TANK_CONE = _svg(f"""
  <path d="M 30 22 L 65 6 L 100 22"
        fill="{_C_BG_GREEN}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <rect x="30" y="22" width="70" height="32"
        fill="{_C_BG_GREEN}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- nivel del líquido -->
  <line x1="33" y1="38" x2="97" y2="38"
        stroke="{_C_OUTLINE}" stroke-width="0.8" stroke-dasharray="3,2"/>
""")

# Floating roof: cuerpo rectangular con techo plano deslizable interno
SVG_TANK_FLOAT = _svg(f"""
  <rect x="28" y="12" width="74" height="42"
        fill="{_C_BG_GREEN}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- techo flotante (rect interno arriba) -->
  <rect x="32" y="18" width="66" height="4"
        fill="{_C_OUTLINE}" opacity="0.4"/>
  <!-- nivel del líquido -->
  <line x1="32" y1="38" x2="98" y2="38"
        stroke="{_C_OUTLINE}" stroke-width="0.8" stroke-dasharray="3,2"/>
""")


# ======================================================
# FIRED HEATERS
# ======================================================

# Horno: rect con tubo de proceso en S + llamas en la base
SVG_FURNACE = _svg(f"""
  <rect x="22" y="10" width="86" height="34" rx="3"
        fill="{_C_BG_YELLOW}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- tubo de proceso (serpentín en S) -->
  <path d="M 26 18 Q 50 18 50 26 Q 50 34 70 34 Q 90 34 90 26 Q 90 18 104 18"
        fill="none" stroke="{_C_OUTLINE_2}" stroke-width="1.5"/>
  <!-- llamas (3 triángulos naranjas) -->
  <path d="M 38 50 L 42 38 L 46 50 Z"
        fill="{_C_FLAME}" stroke="{_C_FLAME_DK}" stroke-width="0.8"/>
  <path d="M 60 50 L 65 34 L 70 50 Z"
        fill="{_C_FLAME}" stroke="{_C_FLAME_DK}" stroke-width="0.8"/>
  <path d="M 82 50 L 86 38 L 90 50 Z"
        fill="{_C_FLAME}" stroke="{_C_FLAME_DK}" stroke-width="0.8"/>
""")


# ======================================================
# FANS / BLOWERS
# ======================================================

# Fan: círculo con 3 aspas (visualmente reconocible como turbina)
SVG_FAN = _svg(f"""
  <circle cx="65" cy="30" r="20" fill="{_C_BG_CYAN}"
          stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- aspas: 3 paths curvos radiales -->
  <path d="M 65 30 L 65 11 Q 73 17 65 30"
        fill="{_C_OUTLINE}" opacity="0.6"
        stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <path d="M 65 30 L 81 39 Q 76 47 65 30"
        fill="{_C_OUTLINE}" opacity="0.6"
        stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <path d="M 65 30 L 49 39 Q 54 47 65 30"
        fill="{_C_OUTLINE}" opacity="0.6"
        stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <!-- hub central -->
  <circle cx="65" cy="30" r="3" fill="{_C_OUTLINE_2}"/>
""")


# ======================================================
# SOLIDS / SEP.
# ======================================================

# Cyclone / separador: cilindro arriba + cono abajo (tolva)
SVG_FILTER = _svg(f"""
  <rect x="30" y="8" width="70" height="22"
        fill="{_C_BG_GRAY}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 30 30 L 100 30 L 75 52 L 55 52 Z"
        fill="{_C_BG_GRAY}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- líneas internas (representan elemento filtrante) -->
  <line x1="35" y1="14" x2="95" y2="14" stroke="{_C_GRAY}" stroke-width="0.6" stroke-dasharray="2,2"/>
  <line x1="35" y1="22" x2="95" y2="22" stroke="{_C_GRAY}" stroke-width="0.6" stroke-dasharray="2,2"/>
""")

# Dryer: rect con líneas que indican calor + sólido
SVG_DRYER = _svg(f"""
  <rect x="22" y="14" width="86" height="32" rx="3"
        fill="{_C_BG_GRAY}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- líneas wavy (aire caliente) -->
  <path d="M 30 22 Q 35 18 40 22 Q 45 26 50 22 Q 55 18 60 22"
        fill="none" stroke="{_C_FLAME}" stroke-width="1"/>
  <path d="M 70 22 Q 75 18 80 22 Q 85 26 90 22 Q 95 18 100 22"
        fill="none" stroke="{_C_FLAME}" stroke-width="1"/>
  <!-- puntos representando sólido -->
  <circle cx="40" cy="36" r="1.5" fill="{_C_OUTLINE_2}"/>
  <circle cx="55" cy="40" r="1.5" fill="{_C_OUTLINE_2}"/>
  <circle cx="70" cy="36" r="1.5" fill="{_C_OUTLINE_2}"/>
  <circle cx="85" cy="40" r="1.5" fill="{_C_OUTLINE_2}"/>
""")

# Evaporator: similar a vessel pero con elementos de calefacción
SVG_EVAPORATOR = _svg(f"""
  <rect x="35" y="10" width="60" height="40" rx="3"
        fill="{_C_BG_BLUE}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- vapor saliendo (líneas wavy arriba) -->
  <path d="M 40 6 Q 45 2 50 6"
        fill="none" stroke="{_C_GRAY}" stroke-width="1"/>
  <path d="M 60 6 Q 65 2 70 6"
        fill="none" stroke="{_C_GRAY}" stroke-width="1"/>
  <path d="M 80 6 Q 85 2 90 6"
        fill="none" stroke="{_C_GRAY}" stroke-width="1"/>
  <!-- tubos calentadores internos -->
  <line x1="42" y1="20" x2="42" y2="44" stroke="{_C_GRAY}" stroke-width="1"/>
  <line x1="50" y1="20" x2="50" y2="44" stroke="{_C_GRAY}" stroke-width="1"/>
  <line x1="58" y1="20" x2="58" y2="44" stroke="{_C_GRAY}" stroke-width="1"/>
  <line x1="66" y1="20" x2="66" y2="44" stroke="{_C_GRAY}" stroke-width="1"/>
  <line x1="74" y1="20" x2="74" y2="44" stroke="{_C_GRAY}" stroke-width="1"/>
  <line x1="82" y1="20" x2="82" y2="44" stroke="{_C_GRAY}" stroke-width="1"/>
  <line x1="90" y1="20" x2="90" y2="44" stroke="{_C_GRAY}" stroke-width="1"/>
""")

# Crystallizer: vessel con cristales en el fondo
SVG_CRYSTALLIZER = _svg(f"""
  <path d="M 30 10 Q 30 6 35 6 L 95 6 Q 100 6 100 10
           L 100 40 L 80 52 L 50 52 L 30 40 Z"
        fill="{_C_BG_GRAY}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <!-- cristales en el fondo (rombos) -->
  <path d="M 50 44 L 53 41 L 56 44 L 53 47 Z" fill="{_C_OUTLINE_2}"/>
  <path d="M 62 46 L 65 43 L 68 46 L 65 49 Z" fill="{_C_OUTLINE_2}"/>
  <path d="M 74 44 L 77 41 L 80 44 L 77 47 Z" fill="{_C_OUTLINE_2}"/>
""")


# ======================================================
# MAPPING eq_type → SVG
# ======================================================

SVG_ICONS = {
    # Heat exchangers
    "Heat exch. — U-tube":          SVG_HX_SHELL_TUBE,
    "Heat exch. — floating head":   SVG_HX_SHELL_TUBE,
    "Heat exch. — fixed tube":      SVG_HX_SHELL_TUBE,
    "Heat exch. — flat plate":      SVG_HX_SHELL_TUBE,
    "Heat exch. — multiple pipe":   SVG_HX_DOUBLE_PIPE,
    "Heat exch. — double pipe":     SVG_HX_DOUBLE_PIPE,
    "Heat exch. — spiral plate":    SVG_HX_SHELL_TUBE,
    "Heat exch. — air cooler":      SVG_HX_AIR_COOLER,
    "Heat exch. — kettle reboiler": SVG_HX_KETTLE,

    # Pumps
    "Pump — centrifugal":           SVG_PUMP_CENTRIFUGAL,
    "Pump — positive displacement": SVG_PUMP_RECIP,
    "Pump — reciprocating":         SVG_PUMP_RECIP,

    # Compressors / fans
    "Compressor — axial":           SVG_COMPRESSOR,
    "Compressor — centrifugal":     SVG_COMPRESSOR,
    "Compressor — reciprocating":   SVG_COMPRESSOR_RECIP,
    "Compressor — rotary":          SVG_COMPRESSOR,
    "Fan — axial":                  SVG_FAN,
    "Fan — centrifugal radial":     SVG_FAN,

    # Reactors
    "Reactor — autoclave":          SVG_REACTOR_AUTOCLAVE,
    "Reactor — jacketed agitated":  SVG_REACTOR_JACKETED,
    "Reactor — jacketed non-agit.": SVG_REACTOR_JACKETED_NA,

    # Vessels
    "Vessel — vertical":            SVG_VESSEL_VERTICAL,
    "Vessel — horizontal":          SVG_VESSEL_HORIZONTAL,

    # Towers
    "Tower (column shell)":         SVG_TOWER,

    # Storage
    "Storage tank — cone roof":     SVG_TANK_CONE,
    "Storage tank — floating roof": SVG_TANK_FLOAT,

    # Fired heaters
    "Fired heater — non-reformer":  SVG_FURNACE,
    "Fired heater — reformer":      SVG_FURNACE,

    # Solids / sep.
    "Filter — belt":                SVG_FILTER,
    "Dryer — drum":                 SVG_DRYER,
    "Evaporator — vertical":        SVG_EVAPORATOR,
    "Crystallizer":                 SVG_CRYSTALLIZER,
}


def get_icon_svg(eq_type):
    """Devuelve el SVG string para un eq_type, o None si no hay ícono."""
    return SVG_ICONS.get(eq_type)
