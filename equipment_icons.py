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
    """Envuelve un body en un SVG bien formado.

    Sin declaración XML porque QSvgRenderer a veces falla parsearla
    cuando viene en bytes encoded.  Sin namespace explícito tampoco
    porque algunos parsers se confunden.
    """
    return (
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
    "Reactor — PFR (tubular)":      SVG_REACTOR_JACKETED_NA,
    "Reactor — CSTR (agitado)":     SVG_REACTOR_JACKETED,

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
"""
EQUIPMENT ICONS — PARCHE PFD-ICN-001
=====================================
Añade 20 íconos SVG faltantes a ``equipment_icons.SVG_ICONS``
siguiendo las convenciones gráficas de:

  · ISA-5.1-2009    — Instrumentation Symbols and Identification
  · ISO 10628-2:2012 — Diagrams for the chemical/petrochemical industry
  · DIN 28004-3     — Diagramas de flujo

Convenciones heredadas de ``equipment_icons.py``:
  · viewBox  "0 0 130 60"   (= BLOCK_W × BLOCK_H del flowsheet_model)
  · stroke   1.5 px         (principal)
  · paleta   _C_OUTLINE / _C_OUTLINE_2 / _C_GRAY + fondos pastel
             categorizados por servicio.

Cómo aplicar
------------
**Opción A** (preferida, mínima fricción):
    Pegar todo el contenido de este archivo AL FINAL de
    ``equipment_icons.py`` (después del ``SVG_ICONS = {...}`` ya
    existente).  El ``SVG_ICONS.update(...)`` al final del archivo
    extiende el dict sin sobrescribir nada.

**Opción B** (mantener separado):
    Guardar este archivo como ``equipment_icons_extra.py`` en la
    misma carpeta que ``equipment_icons.py``, y al final de
    ``equipment_icons.py`` agregar:

        import equipment_icons_extra  # noqa: F401   (registra los íconos)

    Para que esto funcione, este archivo debe importar las
    constantes y el helper ``_svg`` desde ``equipment_icons``:

        from equipment_icons import (
            _svg, SVG_ICONS,
            _C_OUTLINE, _C_OUTLINE_2, _C_GRAY,
            _C_BG_BLUE, _C_BG_GREEN, _C_BG_YELLOW, _C_BG_RED,
            _C_BG_ORANGE, _C_BG_CYAN, _C_BG_GRAY, _C_BG_INDIGO,
            _C_FLAME, _C_FLAME_DK,
        )

    (Las primeras líneas activas de este archivo, descomentar.)

Resultado esperado
------------------
Después de aplicar el parche, ``get_icon_svg(eq_type)`` resuelve
los 46 tipos de ``equipment_costs.EQUIPMENT_DATA``.  Sin parche,
sólo resolvía 26 (43 % sin ícono — fallback a rectángulo plano).

Tests rápidos (pytest)
----------------------
    def test_iconos_cubren_equipment_data():
        from equipment_costs import EQUIPMENT_DATA
        from equipment_icons  import SVG_ICONS
        faltan = set(EQUIPMENT_DATA) - set(SVG_ICONS)
        assert not faltan, f"sin ícono: {faltan}"

    def test_svgs_renderan():
        from equipment_icons import get_icon_svg
        for k in EQUIPMENT_DATA:
            svg = get_icon_svg(k)
            assert svg and svg.startswith("<svg"), k
"""

# ─────────────────────────────────────────────────────────────────
# OPCIÓN B — descomentar este bloque si se guarda como archivo separado
# ─────────────────────────────────────────────────────────────────
# from equipment_icons import (
#     _svg, SVG_ICONS,
#     _C_OUTLINE, _C_OUTLINE_2, _C_GRAY,
#     _C_BG_BLUE, _C_BG_GREEN, _C_BG_YELLOW, _C_BG_RED,
#     _C_BG_ORANGE, _C_BG_CYAN, _C_BG_GRAY, _C_BG_INDIGO,
#     _C_FLAME, _C_FLAME_DK,
# )


# ======================================================
# HEAT EXCHANGERS — CONDENSADORES
# ======================================================

# Carcasa + tubos + fila de gotas de condensado + flecha ↓
# Diferencia el condensador del HX genérico (mismo coeficiente de costo
# Turton pero servicio térmico distinto: U alto, ΔTlm chico).
SVG_HX_CONDENSER_ST = _svg(f"""
  <rect x="18" y="16" width="94" height="28" rx="3"
        fill="{_C_BG_BLUE}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="22" y1="22" x2="108" y2="22" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="22" y1="30" x2="108" y2="30" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="22" y1="38" x2="108" y2="38" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="42" y1="18" x2="42" y2="42" stroke="{_C_GRAY}" stroke-width="0.6" stroke-dasharray="2,2"/>
  <line x1="65" y1="18" x2="65" y2="42" stroke="{_C_GRAY}" stroke-width="0.6" stroke-dasharray="2,2"/>
  <line x1="88" y1="18" x2="88" y2="42" stroke="{_C_GRAY}" stroke-width="0.6" stroke-dasharray="2,2"/>
  <path d="M 30 50 Q 32 54 30 56 Q 28 54 30 50 Z" fill="{_C_OUTLINE_2}"/>
  <path d="M 50 50 Q 52 54 50 56 Q 48 54 50 50 Z" fill="{_C_OUTLINE_2}"/>
  <path d="M 70 50 Q 72 54 70 56 Q 68 54 70 50 Z" fill="{_C_OUTLINE_2}"/>
  <path d="M 90 50 Q 92 54 90 56 Q 88 54 90 50 Z" fill="{_C_OUTLINE_2}"/>
  <path d="M 100 47 L 100 54 L 97 51 M 100 54 L 103 51"
        stroke="{_C_OUTLINE_2}" stroke-width="1" fill="none" stroke-linecap="round"/>
""")

# Condensador aéreo: banco de tubos + fans en el tope (tiro inducido,
# convención ISO para condensadores aéreos) + gotas saliendo abajo.
SVG_HX_CONDENSER_AC = _svg(f"""
  <rect x="18" y="22" width="94" height="20" rx="2"
        fill="{_C_BG_BLUE}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="22" y1="28" x2="108" y2="28" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="22" y1="34" x2="108" y2="34" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <line x1="22" y1="40" x2="108" y2="40" stroke="{_C_GRAY}" stroke-width="0.8"/>
  <circle cx="50" cy="14" r="7" fill="{_C_BG_CYAN}" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <path d="M 50 14 L 50 8 Q 53 11 50 14" fill="{_C_OUTLINE_2}" opacity="0.55"/>
  <path d="M 50 14 L 55 16 Q 53 18 50 14" fill="{_C_OUTLINE_2}" opacity="0.55"/>
  <path d="M 50 14 L 47 18 Q 45 16 50 14" fill="{_C_OUTLINE_2}" opacity="0.55"/>
  <circle cx="80" cy="14" r="7" fill="{_C_BG_CYAN}" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <path d="M 80 14 L 80 8 Q 83 11 80 14" fill="{_C_OUTLINE_2}" opacity="0.55"/>
  <path d="M 80 14 L 85 16 Q 83 18 80 14" fill="{_C_OUTLINE_2}" opacity="0.55"/>
  <path d="M 80 14 L 77 18 Q 75 16 80 14" fill="{_C_OUTLINE_2}" opacity="0.55"/>
  <path d="M 30 48 Q 32 52 30 54 Q 28 52 30 48 Z" fill="{_C_OUTLINE_2}"/>
  <path d="M 60 48 Q 62 52 60 54 Q 58 52 60 48 Z" fill="{_C_OUTLINE_2}"/>
  <path d="M 90 48 Q 92 52 90 54 Q 88 52 90 48 Z" fill="{_C_OUTLINE_2}"/>
""")


# ======================================================
# CENTRÍFUGAS
# ======================================================

# Disc-stack: cilindro vertical con pila de platos cónicos visible.
SVG_CENTRIFUGE_DISC = _svg(f"""
  <ellipse cx="65" cy="10" rx="22" ry="4"
           fill="{_C_BG_GRAY}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 43 10 L 43 44 Q 43 50 50 52 L 80 52 Q 87 50 87 44 L 87 10"
        fill="{_C_BG_GRAY}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <ellipse cx="65" cy="10" rx="22" ry="4" fill="none"
           stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="48" y1="18" x2="82" y2="22" stroke="{_C_OUTLINE_2}" stroke-width="0.9"/>
  <line x1="48" y1="24" x2="82" y2="28" stroke="{_C_OUTLINE_2}" stroke-width="0.9"/>
  <line x1="48" y1="30" x2="82" y2="34" stroke="{_C_OUTLINE_2}" stroke-width="0.9"/>
  <line x1="48" y1="36" x2="82" y2="40" stroke="{_C_OUTLINE_2}" stroke-width="0.9"/>
  <line x1="48" y1="42" x2="82" y2="46" stroke="{_C_OUTLINE_2}" stroke-width="0.9"/>
  <line x1="65" y1="4" x2="65" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="2"/>
  <rect x="61" y="0" width="8" height="5" fill="{_C_OUTLINE_2}"/>
""")

# Decanter horizontal con screw conveyor visible.
SVG_CENTRIFUGE_DEC = _svg(f"""
  <path d="M 18 22 L 95 22 L 110 30 L 95 38 L 18 38 Z"
        fill="{_C_BG_GRAY}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 24 30 Q 30 24 36 30 Q 42 36 48 30 Q 54 24 60 30
           Q 66 36 72 30 Q 78 24 84 30 Q 90 36 96 30"
        fill="none" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <line x1="18" y1="30" x2="108" y2="30" stroke="{_C_OUTLINE_2}"
        stroke-width="0.6" stroke-dasharray="2,2"/>
  <rect x="6" y="26" width="10" height="8" fill="{_C_OUTLINE_2}"/>
  <line x1="16" y1="30" x2="20" y2="30" stroke="{_C_OUTLINE_2}" stroke-width="1.5"/>
  <line x1="108" y1="42" x2="112" y2="50" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="106" y1="44" x2="108" y2="48" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
""")


# ======================================================
# CICLÓN / DECANTADOR POR GRAVEDAD
# ======================================================

# Ciclón: cilindro + cono 30° + vortex finder + inlet tangencial.
SVG_CYCLONE = _svg(f"""
  <rect x="48" y="8" width="34" height="20"
        fill="{_C_BG_GRAY}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 48 28 L 82 28 L 68 52 L 62 52 Z"
        fill="{_C_BG_GRAY}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 25 14 L 48 18" fill="none" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 25 18 L 48 18" fill="none" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="65" y1="2" x2="65" y2="20" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="62" y1="2" x2="62" y2="14" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="68" y1="2" x2="68" y2="14" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 56 22 Q 65 18 74 24 Q 65 28 56 30 Q 65 34 72 38"
        fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <circle cx="65" cy="56" r="1" fill="{_C_OUTLINE_2}"/>
  <circle cx="65" cy="58" r="1" fill="{_C_OUTLINE_2}"/>
""")

# Decantador L-L horizontal con interfaz visible y weir interno.
SVG_DECANTER = _svg(f"""
  <path d="M 22 18 Q 14 18 14 26 Q 14 34 22 34 L 22 42
           Q 14 42 14 50" fill="none" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 108 18 Q 116 18 116 26 Q 116 34 108 34 L 108 42
           Q 116 42 116 50" fill="none" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <rect x="22" y="18" width="86" height="32" fill="{_C_BG_BLUE}" stroke="none"/>
  <line x1="22" y1="18" x2="108" y2="18" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="22" y1="50" x2="108" y2="50" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="20" y1="30" x2="110" y2="30" stroke="{_C_OUTLINE_2}"
        stroke-width="1.2" stroke-dasharray="6,2"/>
  <circle cx="40" cy="42" r="0.8" fill="{_C_OUTLINE_2}"/>
  <circle cx="55" cy="44" r="0.8" fill="{_C_OUTLINE_2}"/>
  <circle cx="70" cy="42" r="0.8" fill="{_C_OUTLINE_2}"/>
  <circle cx="85" cy="44" r="0.8" fill="{_C_OUTLINE_2}"/>
  <line x1="95" y1="30" x2="95" y2="50" stroke="{_C_OUTLINE}" stroke-width="1.2"/>
""")


# ======================================================
# TRAYS — PLATOS DE DESTILACIÓN
# ======================================================

# Plato perforado (sieve) con downcomer y vapor ascendente.
SVG_TRAY_SIEVE = _svg(f"""
  <line x1="20" y1="6" x2="20" y2="54" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="110" y1="6" x2="110" y2="54" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <rect x="20" y="6" width="90" height="48" fill="{_C_BG_BLUE}" opacity="0.55"/>
  <line x1="20" y1="30" x2="110" y2="30" stroke="{_C_OUTLINE_2}" stroke-width="1.8"/>
  <circle cx="30" cy="30" r="1.2" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="0.6"/>
  <circle cx="40" cy="30" r="1.2" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="0.6"/>
  <circle cx="50" cy="30" r="1.2" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="0.6"/>
  <circle cx="60" cy="30" r="1.2" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="0.6"/>
  <circle cx="70" cy="30" r="1.2" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="0.6"/>
  <circle cx="80" cy="30" r="1.2" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="0.6"/>
  <circle cx="90" cy="30" r="1.2" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="0.6"/>
  <circle cx="100" cy="30" r="1.2" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="0.6"/>
  <line x1="20" y1="30" x2="26" y2="48" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <line x1="26" y1="48" x2="26" y2="30" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <line x1="26" y1="26" x2="104" y2="26" stroke="{_C_OUTLINE_2}"
        stroke-width="0.6" stroke-dasharray="2,2"/>
  <path d="M 50 22 L 50 16 M 48 18 L 50 16 L 52 18"
        stroke="{_C_OUTLINE_2}" stroke-width="0.8" fill="none"/>
  <path d="M 70 22 L 70 16 M 68 18 L 70 16 L 72 18"
        stroke="{_C_OUTLINE_2}" stroke-width="0.8" fill="none"/>
""")

# Plato con válvulas: caps semicirculares en lugar de perforaciones.
SVG_TRAY_VALVE = _svg(f"""
  <line x1="20" y1="6" x2="20" y2="54" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="110" y1="6" x2="110" y2="54" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <rect x="20" y="6" width="90" height="48" fill="{_C_BG_BLUE}" opacity="0.55"/>
  <line x1="20" y1="30" x2="110" y2="30" stroke="{_C_OUTLINE_2}" stroke-width="1.8"/>
  <path d="M 28 30 a 3 3 0 0 1 6 0" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="31" y1="27" x2="31" y2="22" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <path d="M 42 30 a 3 3 0 0 1 6 0" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="45" y1="27" x2="45" y2="22" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <path d="M 56 30 a 3 3 0 0 1 6 0" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="59" y1="27" x2="59" y2="22" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <path d="M 70 30 a 3 3 0 0 1 6 0" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="73" y1="27" x2="73" y2="22" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <path d="M 84 30 a 3 3 0 0 1 6 0" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="87" y1="27" x2="87" y2="22" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <path d="M 98 30 a 3 3 0 0 1 6 0" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="101" y1="27" x2="101" y2="22" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="20" y1="30" x2="26" y2="48" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <line x1="26" y1="48" x2="26" y2="30" stroke="{_C_OUTLINE}" stroke-width="1"/>
""")


# ======================================================
# PACKING — EMPAQUES
# ======================================================

# Empaque al azar: distribuidor + anillos desordenados + soporte.
SVG_PACKING_RANDOM = _svg(f"""
  <line x1="20" y1="6" x2="20" y2="54" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="110" y1="6" x2="110" y2="54" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <rect x="20" y="6" width="90" height="48" fill="{_C_BG_BLUE}"/>
  <line x1="22" y1="10" x2="108" y2="10" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <line x1="35" y1="10" x2="35" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="50" y1="10" x2="50" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="65" y1="10" x2="65" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="80" y1="10" x2="80" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="95" y1="10" x2="95" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <circle cx="30" cy="22" r="2.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <ellipse cx="42" cy="20" rx="3" ry="1.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8" transform="rotate(20,42,20)"/>
  <circle cx="55" cy="25" r="2.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <ellipse cx="68" cy="22" rx="2.5" ry="1.4" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8" transform="rotate(-30,68,22)"/>
  <circle cx="82" cy="24" r="2.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <ellipse cx="95" cy="20" rx="3" ry="1.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8" transform="rotate(40,95,20)"/>
  <circle cx="35" cy="32" r="2.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <ellipse cx="50" cy="34" rx="2.5" ry="1.4" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8" transform="rotate(-15,50,34)"/>
  <circle cx="65" cy="36" r="2.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <ellipse cx="80" cy="33" rx="3" ry="1.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8" transform="rotate(60,80,33)"/>
  <circle cx="95" cy="35" r="2.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <ellipse cx="30" cy="44" rx="3" ry="1.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8" transform="rotate(10,30,44)"/>
  <circle cx="45" cy="45" r="2.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <circle cx="60" cy="44" r="2.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <ellipse cx="75" cy="45" rx="2.5" ry="1.4" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8" transform="rotate(-25,75,45)"/>
  <circle cx="90" cy="44" r="2.5" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="20" y1="50" x2="110" y2="50" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
""")

# Empaque estructurado: patrón chevrón 45° (Mellapak/Flexipac).
SVG_PACKING_STRUCT = _svg(f"""
  <line x1="20" y1="6" x2="20" y2="54" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="110" y1="6" x2="110" y2="54" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <rect x="20" y="6" width="90" height="48" fill="{_C_BG_BLUE}"/>
  <line x1="22" y1="10" x2="108" y2="10" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <line x1="40" y1="10" x2="40" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="65" y1="10" x2="65" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="90" y1="10" x2="90" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <path d="M 22 18 L 32 28 L 42 18 L 52 28 L 62 18 L 72 28 L 82 18 L 92 28 L 102 18 L 108 22"
        stroke="{_C_OUTLINE_2}" stroke-width="0.7" fill="none"/>
  <path d="M 22 24 L 32 34 L 42 24 L 52 34 L 62 24 L 72 34 L 82 24 L 92 34 L 102 24 L 108 28"
        stroke="{_C_OUTLINE_2}" stroke-width="0.7" fill="none"/>
  <path d="M 22 30 L 32 40 L 42 30 L 52 40 L 62 30 L 72 40 L 82 30 L 92 40 L 102 30 L 108 34"
        stroke="{_C_OUTLINE_2}" stroke-width="0.7" fill="none"/>
  <path d="M 22 36 L 32 46 L 42 36 L 52 46 L 62 36 L 72 46 L 82 36 L 92 46 L 102 36 L 108 40"
        stroke="{_C_OUTLINE_2}" stroke-width="0.7" fill="none"/>
  <line x1="20" y1="50" x2="110" y2="50" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
""")


# ======================================================
# MIXERS / SPLITTER
# ======================================================

# Mezclador inline: Y de entrada + cuerpo con aspas en X + salida.
SVG_MIXER_INLINE = _svg(f"""
  <line x1="6" y1="14" x2="34" y2="26" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <line x1="6" y1="46" x2="34" y2="34" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <rect x="34" y="22" width="50" height="16" rx="2"
        fill="{_C_BG_INDIGO}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="42" y1="26" x2="50" y2="34" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <line x1="50" y1="26" x2="42" y2="34" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <line x1="58" y1="26" x2="66" y2="34" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <line x1="66" y1="26" x2="58" y2="34" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <line x1="74" y1="26" x2="82" y2="34" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <line x1="82" y1="26" x2="74" y2="34" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <line x1="84" y1="30" x2="120" y2="30" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <path d="M 116 26 L 122 30 L 116 34" fill="{_C_OUTLINE}"/>
""")

# Mezclador estático: tubo con elementos cruzados alternados (Kenics).
SVG_MIXER_STATIC = _svg(f"""
  <line x1="6" y1="30" x2="20" y2="30" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <rect x="20" y="22" width="90" height="16" rx="2"
        fill="{_C_BG_INDIGO}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="25" y1="24" x2="35" y2="36" stroke="{_C_OUTLINE_2}" stroke-width="1.4"/>
  <line x1="40" y1="36" x2="50" y2="24" stroke="{_C_OUTLINE_2}" stroke-width="1.4"/>
  <line x1="55" y1="24" x2="65" y2="36" stroke="{_C_OUTLINE_2}" stroke-width="1.4"/>
  <line x1="70" y1="36" x2="80" y2="24" stroke="{_C_OUTLINE_2}" stroke-width="1.4"/>
  <line x1="85" y1="24" x2="95" y2="36" stroke="{_C_OUTLINE_2}" stroke-width="1.4"/>
  <line x1="100" y1="36" x2="106" y2="28" stroke="{_C_OUTLINE_2}" stroke-width="1.4"/>
  <line x1="22" y1="30" x2="108" y2="30" stroke="{_C_OUTLINE_2}"
        stroke-width="0.5" stroke-dasharray="2,2"/>
  <line x1="110" y1="30" x2="124" y2="30" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <path d="M 120 26 L 126 30 L 120 34" fill="{_C_OUTLINE}"/>
""")

# Splitter / divisor de flujo: rombo + 2 salidas con flecha.
SVG_SPLITTER = _svg(f"""
  <line x1="6" y1="30" x2="50" y2="30" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <path d="M 50 22 L 70 30 L 50 38 Z"
        fill="{_C_BG_INDIGO}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="52" y1="30" x2="68" y2="30" stroke="{_C_OUTLINE_2}"
        stroke-width="0.8" stroke-dasharray="2,2"/>
  <line x1="70" y1="30" x2="90" y2="14" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <line x1="70" y1="30" x2="90" y2="46" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <line x1="100" y1="10" x2="120" y2="10" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <path d="M 116 6 L 122 10 L 116 14" fill="{_C_OUTLINE}"/>
  <line x1="100" y1="50" x2="120" y2="50" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <path d="M 116 46 L 122 50 L 116 54" fill="{_C_OUTLINE}"/>
  <line x1="90" y1="14" x2="100" y2="10" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <line x1="90" y1="46" x2="100" y2="50" stroke="{_C_OUTLINE}" stroke-width="2"/>
""")


# ======================================================
# VÁLVULAS
# ======================================================

# Globe valve con actuador diafragma + bubble de instrumento (ISA).
SVG_VALVE_CONTROL = _svg(f"""
  <line x1="6" y1="40" x2="48" y2="40" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <line x1="82" y1="40" x2="124" y2="40" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <path d="M 48 32 L 48 48 L 65 40 Z" fill="#fff" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 82 32 L 82 48 L 65 40 Z" fill="#fff" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <circle cx="65" cy="40" r="3" fill="{_C_BG_INDIGO}" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <line x1="65" y1="32" x2="65" y2="18" stroke="{_C_OUTLINE_2}" stroke-width="1.5"/>
  <path d="M 52 8 Q 52 14 65 14 Q 78 14 78 8 L 78 4 L 52 4 Z"
        fill="{_C_BG_INDIGO}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="52" y1="9" x2="78" y2="9" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <circle cx="92" cy="14" r="6" fill="#fff" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="86" y1="14" x2="98" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="0.4"/>
  <line x1="92" y1="20" x2="92" y2="32" stroke="{_C_OUTLINE_2}"
        stroke-width="0.4" stroke-dasharray="1.5,1.5"/>
""")

# PSV: cuerpo angular + resorte visible + bonnet (ISA-5.1).
SVG_VALVE_RELIEF = _svg(f"""
  <line x1="50" y1="56" x2="50" y2="40" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <path d="M 42 32 L 58 32 L 50 48 Z" fill="#fff" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 58 26 L 58 42 L 74 34 Z" fill="#fff" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="74" y1="34" x2="100" y2="34" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <path d="M 96 30 L 102 34 L 96 38" fill="{_C_OUTLINE}"/>
  <path d="M 50 32 L 46 26 L 54 22 L 46 18 L 54 14 L 50 10 L 50 6"
        fill="none" stroke="{_C_OUTLINE_2}" stroke-width="1.4"/>
  <rect x="44" y="4" width="12" height="4" fill="{_C_OUTLINE_2}"/>
""")

# Válvula 3 vías: 3 triángulos confluyendo + disco central + handwheel.
SVG_VALVE_3WAY = _svg(f"""
  <line x1="6" y1="38" x2="48" y2="38" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <line x1="82" y1="38" x2="124" y2="38" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <line x1="65" y1="56" x2="65" y2="48" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <path d="M 48 30 L 48 46 L 65 38 Z" fill="#fff" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 82 30 L 82 46 L 65 38 Z" fill="#fff" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 57 54 L 73 54 L 65 38 Z" fill="#fff" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <circle cx="65" cy="38" r="2.5" fill="{_C_OUTLINE_2}"/>
  <line x1="65" y1="30" x2="65" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="1.5"/>
  <circle cx="65" cy="10" r="4" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="1.2"/>
  <line x1="61" y1="10" x2="69" y2="10" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="65" y1="6" x2="65" y2="14" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
""")


# ======================================================
# CALDERAS
# ======================================================

# Fire-tube: cilindro horizontal con tubos rojos + chimenea + llama.
SVG_BOILER_FIRE = _svg(f"""
  <path d="M 22 14 Q 14 14 14 28 Q 14 42 22 42
           L 108 42 Q 116 42 116 28 Q 116 14 108 14 Z"
        fill="{_C_BG_YELLOW}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="26" y1="22" x2="104" y2="22" stroke="{_C_FLAME_DK}" stroke-width="1.2"/>
  <line x1="26" y1="28" x2="104" y2="28" stroke="{_C_FLAME_DK}" stroke-width="1.2"/>
  <line x1="26" y1="34" x2="104" y2="34" stroke="{_C_FLAME_DK}" stroke-width="1.2"/>
  <rect x="100" y="2" width="10" height="14"
        fill="{_C_BG_YELLOW}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 6 22 L 12 18 L 8 26 L 14 26 L 8 32 L 12 38 L 6 36 Z"
        fill="{_C_FLAME}" stroke="{_C_FLAME_DK}" stroke-width="0.8"/>
  <line x1="65" y1="14" x2="65" y2="4" stroke="{_C_OUTLINE}" stroke-width="2"/>
  <path d="M 60 8 Q 65 4 70 8" fill="none" stroke="{_C_OUTLINE_2}" stroke-width="0.8"/>
  <line x1="18" y1="20" x2="112" y2="20"
        stroke="{_C_OUTLINE_2}" stroke-width="0.6" stroke-dasharray="3,2"/>
""")

# Water-tube: steam drum + mud drum + tubos verticales + furnace lateral.
SVG_BOILER_WATER = _svg(f"""
  <rect x="34" y="4" width="62" height="12" rx="6"
        fill="{_C_BG_YELLOW}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <rect x="34" y="46" width="62" height="10" rx="5"
        fill="{_C_BG_YELLOW}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="42" y1="16" x2="42" y2="46" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="50" y1="16" x2="50" y2="46" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="58" y1="16" x2="58" y2="46" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="66" y1="16" x2="66" y2="46" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="74" y1="16" x2="74" y2="46" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="82" y1="16" x2="82" y2="46" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <line x1="90" y1="16" x2="90" y2="46" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
  <path d="M 100 50 L 104 38 L 108 50 Z" fill="{_C_FLAME}" stroke="{_C_FLAME_DK}" stroke-width="0.6"/>
  <path d="M 110 50 L 114 36 L 118 50 Z" fill="{_C_FLAME}" stroke="{_C_FLAME_DK}" stroke-width="0.6"/>
  <rect x="22" y="22" width="8" height="14"
        fill="{_C_BG_YELLOW}" stroke="{_C_OUTLINE}" stroke-width="1.2"/>
  <line x1="65" y1="4" x2="65" y2="0" stroke="{_C_OUTLINE}" stroke-width="2"/>
""")


# ======================================================
# TORRES DE ENFRIAMIENTO
# ======================================================

# Tiro inducido (mecánico): caja + fan grande arriba + fill + basin.
SVG_CT_INDUCED = _svg(f"""
  <path d="M 30 14 L 100 14 L 100 54 L 30 54 Z"
        fill="{_C_BG_CYAN}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <circle cx="65" cy="10" r="9" fill="{_C_BG_CYAN}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <path d="M 65 10 L 65 2 Q 71 6 65 10" fill="{_C_OUTLINE_2}" opacity="0.55"/>
  <path d="M 65 10 L 73 13 Q 70 18 65 10" fill="{_C_OUTLINE_2}" opacity="0.55"/>
  <path d="M 65 10 L 57 13 Q 60 18 65 10" fill="{_C_OUTLINE_2}" opacity="0.55"/>
  <circle cx="65" cy="10" r="1.5" fill="{_C_OUTLINE_2}"/>
  <line x1="40" y1="22" x2="40" y2="40" stroke="{_C_OUTLINE}" stroke-width="0.6"/>
  <line x1="50" y1="22" x2="50" y2="40" stroke="{_C_OUTLINE}" stroke-width="0.6"/>
  <line x1="60" y1="22" x2="60" y2="40" stroke="{_C_OUTLINE}" stroke-width="0.6"/>
  <line x1="70" y1="22" x2="70" y2="40" stroke="{_C_OUTLINE}" stroke-width="0.6"/>
  <line x1="80" y1="22" x2="80" y2="40" stroke="{_C_OUTLINE}" stroke-width="0.6"/>
  <line x1="90" y1="22" x2="90" y2="40" stroke="{_C_OUTLINE}" stroke-width="0.6"/>
  <line x1="34" y1="30" x2="96" y2="30" stroke="{_C_OUTLINE_2}" stroke-width="0.6"/>
  <line x1="34" y1="34" x2="96" y2="34" stroke="{_C_OUTLINE_2}" stroke-width="0.6"/>
  <path d="M 30 44 L 100 44 L 100 50 L 30 50 Z" fill="{_C_BG_BLUE}" stroke="none"/>
  <line x1="30" y1="44" x2="100" y2="44" stroke="{_C_OUTLINE_2}" stroke-width="0.6" stroke-dasharray="3,2"/>
  <line x1="30" y1="52" x2="34" y2="50" stroke="{_C_OUTLINE}" stroke-width="0.8"/>
  <line x1="100" y1="52" x2="96" y2="50" stroke="{_C_OUTLINE}" stroke-width="0.8"/>
""")

# Tiro natural: silueta hiperbólica clásica sin ventilador.
SVG_CT_NATURAL = _svg(f"""
  <path d="M 38 2
           C 42 18, 50 26, 50 30
           C 50 36, 42 44, 38 56
           L 92 56
           C 88 44, 80 36, 80 30
           C 80 26, 88 18, 92 2
           Z"
        fill="{_C_BG_CYAN}" stroke="{_C_OUTLINE}" stroke-width="1.5"/>
  <line x1="50" y1="32" x2="80" y2="32" stroke="{_C_OUTLINE_2}" stroke-width="0.6"/>
  <line x1="48" y1="36" x2="82" y2="36" stroke="{_C_OUTLINE_2}" stroke-width="0.6"/>
  <line x1="40" y1="48" x2="46" y2="44" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <line x1="42" y1="52" x2="48" y2="48" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <line x1="44" y1="56" x2="50" y2="52" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <line x1="84" y1="44" x2="90" y2="48" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <line x1="82" y1="48" x2="88" y2="52" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <line x1="80" y1="52" x2="86" y2="56" stroke="{_C_OUTLINE}" stroke-width="1"/>
  <line x1="38" y1="56" x2="92" y2="56" stroke="{_C_OUTLINE_2}" stroke-width="1"/>
""")


# ======================================================
# MAPEO — extiende SVG_ICONS sin sobrescribir nada
# ======================================================

SVG_ICONS.update({
    # Heat exchangers — condensadores
    "Heat exch. — condenser shell-tube": SVG_HX_CONDENSER_ST,
    "Heat exch. — condenser air-cooled": SVG_HX_CONDENSER_AC,

    # Solids / sep.
    "Centrifuge — disc stack":           SVG_CENTRIFUGE_DISC,
    "Centrifuge — decanter":             SVG_CENTRIFUGE_DEC,
    "Cyclone — gas/solid":               SVG_CYCLONE,
    "Decanter — gravity":                SVG_DECANTER,

    # Trays / packing
    "Tray — sieve":                      SVG_TRAY_SIEVE,
    "Tray — valve":                      SVG_TRAY_VALVE,
    "Packing — random":                  SVG_PACKING_RANDOM,
    "Packing — structured":              SVG_PACKING_STRUCT,

    # Mixers / splitters
    "Mixer — inline":                    SVG_MIXER_INLINE,
    "Mixer — static":                    SVG_MIXER_STATIC,
    "Splitter — flow divider":           SVG_SPLITTER,

    # Valves
    "Valve — control globe":             SVG_VALVE_CONTROL,
    "Valve — relief":                    SVG_VALVE_RELIEF,
    "Valve — 3-way":                     SVG_VALVE_3WAY,

    # Utilities
    "Boiler — fire tube":                SVG_BOILER_FIRE,
    "Boiler — water tube":               SVG_BOILER_WATER,
    "Cooling tower — induced draft":     SVG_CT_INDUCED,
    "Cooling tower — natural draft":     SVG_CT_NATURAL,
})
