"""
EQUIPMENT_PORTS — catálogo de puertos por tipo de equipo + tags ISA-5.1.

Cada eq_type del catálogo de equipment_costs.py se mapea a un dict de
puertos:

    {port_name: (side, frac)}

donde:
  side ∈ {'left', 'right', 'top', 'bottom'}
  frac ∈ [0, 1]   posición fraccional sobre ese lado
                  (0 = arriba/izquierda, 1 = abajo/derecha)

Los nombres de puerto siguen convenciones de ingeniería química:

  HX shell-and-tube:  tube_in / tube_out / shell_in / shell_out
  Bomba / compresor:  succion / descarga
  Reactor:            alimentacion / producto / util_in / util_out
  Tanque flash:       alimentacion / vapor / liquido
  Columna:            alimentacion / vapor_tope / liquido_fondo
                      reflujo / reboiler / extraccion_lateral
  Tanque:             entrada / salida
  Horno:              proceso_in / proceso_out / combustible / chimenea

Los tags de bloque siguen ISA-5.1:

  E   = heat exchanger / cooler / condenser / reboiler
  P   = pump
  K   = compressor
  R   = reactor
  T   = tower / column
  V   = vessel / flash drum
  F   = fired heater / furnace
  TK  = storage tank
  FN  = fan / blower
  FL  = filter
  DR  = dryer
  EV  = evaporator
  CR  = crystallizer

Numeración: empieza en 101 (101–199 = unidad de proceso 1).
"""


# ======================================================
# CATÁLOGOS DE PUERTOS POR CATEGORÍA
# ======================================================

# Heat exchanger genérico (shell-and-tube): 4 puertos de proceso/servicio
# + vent del shell + drenaje del shell para flexibilidad de armado.
HX_PORTS = {
    "tube_in":    ("left",   0.30),
    "tube_out":   ("right",  0.30),
    "shell_in":   ("right",  0.70),
    "shell_out":  ("left",   0.70),
    "shell_vent": ("top",    0.5),     # venteo del shell-side
    "shell_drain":("bottom", 0.5),     # drenaje del shell-side
}

# Air cooler: proceso + aire + un par adicional para multi-pass (manifold
# de 2 pasos por tubo, común en air-coolers grandes).
AIR_COOLER_PORTS = {
    "proceso_in":   ("left",   0.30),
    "proceso_out":  ("right",  0.30),
    "proceso_in_2": ("left",   0.70),
    "proceso_out_2":("right",  0.70),
    "aire_in":      ("bottom", 0.5),
    "aire_out":     ("top",    0.5),
}

# Reboiler kettle: lado proceso + lado servicio + vent / drain.
REBOILER_PORTS = {
    "liq_in":      ("left",   0.30),
    "vap_out":     ("right",  0.30),
    "steam_in":    ("left",   0.70),
    "cond_out":    ("right",  0.70),
    "vent":        ("top",    0.50),
    "drain":       ("bottom", 0.50),
}

# Pump
PUMP_PORTS = {
    "succion":   ("left",   0.5),
    "descarga":  ("right",  0.5),
    "drain":     ("bottom", 0.5),     # drenaje de casing
}

# Compressor / Fan — succion, descarga, intercooler tap (gas grande),
# drain del casing.
COMPRESSOR_PORTS = {
    "succion":         ("left",   0.5),
    "descarga":        ("right",  0.5),
    "intercooler_in":  ("top",    0.30),
    "intercooler_out": ("top",    0.70),
    "drain":           ("bottom", 0.5),
}

# Reactor con servicios de utilidad (chaqueta o serpentín).
REACTOR_PORTS = {
    "alimentacion":   ("left",   0.25),
    "alimentacion_2": ("left",   0.50),    # co-feed
    "alimentacion_3": ("left",   0.75),    # third feed (cat., promoter)
    "producto":       ("right",  0.30),
    "producto_2":     ("right",  0.70),    # side draw o purge
    "util_in":        ("top",    0.30),
    "util_out":       ("top",    0.70),
    "venteo":         ("top",    0.50),    # alivio de presión
    "drenaje":        ("bottom", 0.5),
}

# Vessel vertical (flash drum, separador): más puertos para drenaje, vent,
# segunda alimentación, recirculación.
VESSEL_VERT_PORTS = {
    "alimentacion":   ("left",   0.40),
    "alimentacion_2": ("left",   0.70),
    "vapor":          ("top",    0.5),
    "venteo":         ("top",    0.20),    # alivio
    "liquido":        ("bottom", 0.5),
    "drenaje":        ("bottom", 0.20),
    "recirculacion":  ("right",  0.5),
    # Aliases compat con Storage tank (algunos ejemplos viejos usan estos
    # nombres): entrada → alimentacion, salida → liquido.
    "entrada":        ("left",   0.40),
    "salida":         ("bottom", 0.5),
}

# Vessel horizontal (KO drum): similar al vertical pero con vapor + drain
# laterales.
VESSEL_HORZ_PORTS = {
    "alimentacion":   ("left",   0.40),
    "alimentacion_2": ("left",   0.70),
    "vapor":          ("top",    0.70),
    "venteo":         ("top",    0.30),
    "liquido":        ("right",  0.5),
    "drenaje":        ("bottom", 0.20),
    "interfase":      ("bottom", 0.70),    # extracción de interfase
    "entrada":        ("left",   0.40),
    "salida":         ("right",  0.5),
}

# Tower / columna — con múltiples cortes laterales y alimentaciones
# (típico en CDU, hidrocracker, FCC).
TOWER_PORTS = {
    # entradas / salidas principales
    "alimentacion":      ("left",   0.5),
    "vapor_tope":        ("top",    0.5),
    "liquido_fondo":     ("bottom", 0.5),
    "reflujo":           ("top",    0.20),
    "reboiler":          ("bottom", 0.20),
    # extracción lateral por defecto (compat con ejemplos viejos)
    "extraccion_lateral":("right",  0.5),
    # múltiples cortes laterales (alto = liviano, bajo = pesado)
    "extraccion_alta":   ("right",  0.30),    # ~25-30% desde el tope (nafta pesada)
    "extraccion_media":  ("right",  0.50),    # mitad (querosén)
    "extraccion_baja":   ("right",  0.70),    # ~70% (diésel ligero)
    # alimentaciones secundarias (multi-feed columns)
    "alimentacion_alta": ("left",   0.30),
    "alimentacion_baja": ("left",   0.70),
    # entrada de stripping steam (cerca del fondo)
    "stripping_steam":   ("bottom", 0.50),
}

# Storage tank: entradas/salidas + vent + drenaje + recirculación
TANK_PORTS = {
    "entrada":       ("top",    0.30),
    "entrada_2":     ("top",    0.70),     # segunda alimentación (makeup)
    "salida":        ("bottom", 0.30),
    "recirculacion": ("right",  0.5),      # loop de mezcla / circulation
    "venteo":        ("top",    0.5),      # vent atmospheric
    "drenaje":       ("bottom", 0.70),     # drain to sewer
}

# Fired heater / horno: multi-pass + aire de combustión.
FURNACE_PORTS = {
    "proceso_in":    ("left",   0.30),
    "proceso_out":   ("right",  0.30),
    "proceso_in_2":  ("left",   0.70),     # 2do paso de tubo
    "proceso_out_2": ("right",  0.70),
    "combustible":   ("bottom", 0.30),
    "aire_in":       ("bottom", 0.70),     # aire de combustión forzada
    "chimenea":      ("top",    0.5),
}

# Solids: filter, dryer, evaporator, crystallizer.
SOLIDS_PORTS = {
    "alimentacion":   ("left",   0.5),
    "producto":       ("right",  0.30),
    "producto_2":     ("right",  0.70),    # licor madre / segunda fase
    "util_in":        ("top",    0.30),
    "util_out":       ("top",    0.70),
    "venteo":         ("top",    0.5),
    "drenaje":        ("bottom", 0.5),
}

# Mixer: 4 entradas, 1 salida — para flexibilidad cuando el user
# necesita mezclar más de 2 corrientes.
MIXER_PORTS = {
    "alimentacion_1": ("left",   0.20),
    "alimentacion_2": ("left",   0.45),
    "alimentacion_3": ("left",   0.65),
    "alimentacion_4": ("left",   0.85),
    "producto":       ("right",  0.50),
    # aliases para compat con ejemplos viejos
    "entrada1":       ("left",   0.20),
    "entrada2":       ("left",   0.45),
    "salida":         ("right",  0.50),
}

# Splitter: 1 entrada, 4 salidas (flow divider con varias rutas).
SPLITTER_PORTS = {
    "alimentacion":   ("left",   0.50),
    "producto_1":     ("right",  0.20),
    "producto_2":     ("right",  0.45),
    "producto_3":     ("right",  0.65),
    "producto_4":     ("right",  0.85),
    # aliases compat
    "entrada":        ("left",   0.50),
    "salida_1":       ("right",  0.20),
    "salida_2":       ("right",  0.45),
}

# Cyclone gas/sólido: feed lateral, gas arriba, sólido abajo + venteo extra.
CYCLONE_PORTS = {
    "alimentacion":   ("left",   0.30),
    "alimentacion_2": ("left",   0.70),
    "venteo":         ("top",    0.50),
    "producto":       ("bottom", 0.50),
    "drenaje":        ("bottom", 0.20),
}

# Decanter: 1+ entrada, 2 fases + drenaje de interfase.
DECANTER_PORTS = {
    "alimentacion":   ("left",   0.30),
    "alimentacion_2": ("left",   0.70),
    "fase_liviana":   ("right",  0.30),
    "fase_pesada":    ("right",  0.70),
    "interfase":      ("bottom", 0.50),
    "venteo":         ("top",    0.50),
}

# Centrifuga: líquido + sólido + agua de lavado.
CENTRIFUGE_PORTS = {
    "alimentacion":   ("left",   0.30),
    "agua_lavado":    ("top",    0.30),    # wash water
    "liquido":        ("right",  0.30),
    "solido":         ("bottom", 0.50),
    "drenaje":        ("bottom", 0.80),
}

# Válvulas: 1-in / 1-out + drenaje
VALVE_PORTS = {
    "alimentacion":   ("left",   0.50),
    "producto":       ("right",  0.50),
    "drenaje":        ("bottom", 0.50),
}

# Boiler de vapor (caldera) — recibe agua + combustible, produce
# vapor a varios niveles + tiene blowdown y chimenea.
BOILER_PORTS = {
    "agua_in":      ("left",   0.5),    # boiler feed water tratada
    "combustible":  ("bottom", 0.30),   # fuel gas o petróleo
    "vapor_out":    ("right",  0.5),    # steam principal
    "blowdown":     ("bottom", 0.70),   # purga de sales
    "chimenea":     ("top",    0.5),    # gases de combustión
}

# Cooling tower — recibe agua caliente del proceso, devuelve fría;
# pierde agua por evaporación, requiere makeup y blowdown.
COOLING_TOWER_PORTS = {
    "agua_caliente": ("top",   0.30),   # warm return from process
    "agua_fria":     ("bottom",0.5),    # cold supply to process
    "makeup":        ("left",  0.5),    # agua de reposición
    "blowdown":      ("bottom",0.80),   # purga concentración
    "vapor_loss":    ("top",   0.70),   # pérdida por evaporación
}

# Atmósfera / ambiente — source/sink de aire, chimenea, blowdown, etc.
# (corrientes auxiliares auto-instanciadas).  Tiene ambos puertos: salida
# (cuando actúa de fuente, p.ej. aire de entrada) y entrada (cuando actúa
# de sumidero, p.ej. chimenea/venteo).
AMBIENT_PORTS = {
    "entrada": ("top",    0.5),
    "salida":  ("bottom", 0.5),
}

# Header de utility (lazo cerrado): supply en top, return en bottom — ambos
# puertos del mismo lado para que las dos corrientes se vean como UN lazo.
UTIL_HEADER_PORTS = {
    "salida":  ("right", 0.30),   # supply OUT  → al equipo
    "entrada": ("right", 0.70),   # return IN   ← del equipo
}

# Fallback (equipos no catalogados)
DEFAULT_PORTS = {
    "in":  ("left",  0.5),
    "out": ("right", 0.5),
}


# ======================================================
# CLASIFICACIÓN POR TIPO — para colorear los puertos
# ======================================================
# Cada puerto se clasifica en uno de:
#   process_in   — entrada de proceso (feed, alimentación, succión, reflujo)
#   process_out  — salida de proceso (producto, descarga, vapor_tope,
#                   liquido_fondo, fase_*)
#   utility_in   — entrada de servicio (steam, CW, jacket, shell, util_in)
#   utility_out  — salida de servicio (cond, jacket out, shell out)
#   fuel         — combustible
#   vent         — venteo / atmósfera / chimenea / blowdown
#   drain        — drenaje
#   aux          — fallback (puerto raro o multi-uso)

PORT_KIND_BY_NAME = {
    # ── PROCESO IN ─────────────────────────────────────────
    "tube_in":         "process_in",
    "proceso_in":      "process_in",
    "proceso_in_2":    "process_in",
    "alimentacion":    "process_in",
    "alimentacion_1":  "process_in",
    "alimentacion_2":  "process_in",
    "alimentacion_3":  "process_in",
    "alimentacion_4":  "process_in",
    "alimentacion_alta":"process_in",
    "alimentacion_baja":"process_in",
    "entrada":         "process_in",
    "entrada1":        "process_in",
    "entrada2":        "process_in",
    "entrada_2":       "process_in",
    "succion":         "process_in",
    "reflujo":         "process_in",
    "reboiler":        "process_in",
    "liq_in":          "process_in",
    "agua_in":         "process_in",
    "agua_caliente":   "process_in",      # cooling tower warm return
    "stripping_steam": "process_in",
    "makeup":          "process_in",
    "in":              "process_in",
    # ── PROCESO OUT ────────────────────────────────────────
    "tube_out":        "process_out",
    "proceso_out":     "process_out",
    "proceso_out_2":   "process_out",
    "producto":        "process_out",
    "producto_1":      "process_out",
    "producto_2":      "process_out",
    "producto_3":      "process_out",
    "producto_4":      "process_out",
    "salida":          "process_out",
    "salida_1":        "process_out",
    "salida_2":        "process_out",
    "descarga":        "process_out",
    "vapor":           "process_out",
    "vapor_tope":      "process_out",
    "vapor_out":       "process_out",
    "vap_out":         "process_out",
    "liquido":         "process_out",
    "liquido_fondo":   "process_out",
    "fase_liviana":    "process_out",
    "fase_pesada":     "process_out",
    "solido":          "process_out",
    "agua_fria":       "process_out",     # cooling tower cold supply
    "extraccion_lateral":"process_out",
    "extraccion_alta": "process_out",
    "extraccion_media":"process_out",
    "extraccion_baja": "process_out",
    "interfase":       "process_out",
    "recirculacion":   "process_out",
    "out":             "process_out",
    # ── UTILITY IN ─────────────────────────────────────────
    "shell_in":        "utility_in",
    "util_in":         "utility_in",
    "steam_in":        "utility_in",
    "intercooler_in":  "utility_in",
    "agua_lavado":     "utility_in",
    # ── UTILITY OUT ────────────────────────────────────────
    "shell_out":       "utility_out",
    "util_out":        "utility_out",
    "cond_out":        "utility_out",
    "intercooler_out": "utility_out",
    # ── FUEL ───────────────────────────────────────────────
    "combustible":     "fuel",
    # ── VENT / ATMOSPHERE ──────────────────────────────────
    "chimenea":        "vent",
    "venteo":          "vent",
    "vent":            "vent",
    "shell_vent":      "vent",
    "vapor_loss":      "vent",
    "blowdown":        "vent",
    "aire_in":         "vent",            # intake atmosférico
    "aire_out":        "vent",
    # ── DRAIN ──────────────────────────────────────────────
    "drenaje":         "drain",
    "drain":           "drain",
    "shell_drain":     "drain",
}


def get_port_kind(eq_type: str, port_name: str) -> str:
    """Clasifica un puerto en una de 8 categorías para colorearlo.
    Returns 'process_in' | 'process_out' | 'utility_in' | 'utility_out'
            | 'fuel' | 'vent' | 'drain' | 'aux'."""
    return PORT_KIND_BY_NAME.get(port_name, "aux")


EQUIPMENT_PORTS = {
    "Heat exch. — U-tube":          HX_PORTS,
    "Heat exch. — floating head":   HX_PORTS,
    "Heat exch. — fixed tube":      HX_PORTS,
    "Heat exch. — flat plate":      HX_PORTS,
    "Heat exch. — multiple pipe":   HX_PORTS,
    "Heat exch. — double pipe":     HX_PORTS,
    "Heat exch. — spiral plate":    HX_PORTS,
    "Heat exch. — air cooler":      AIR_COOLER_PORTS,
    "Heat exch. — kettle reboiler": REBOILER_PORTS,
    # WHB (Sinnott): shell-tube clásico — tube=proceso caliente, shell=BFW/steam.
    "Heat exch. — WHB packaged":      HX_PORTS,
    "Heat exch. — WHB field erected": HX_PORTS,
    # Condensadores (mismos puertos que su HX padre):
    "Heat exch. — condenser shell-tube":  HX_PORTS,
    "Heat exch. — condenser air-cooled":  AIR_COOLER_PORTS,

    "Pump — centrifugal":           PUMP_PORTS,
    "Pump — positive displacement": PUMP_PORTS,
    "Pump — reciprocating":         PUMP_PORTS,

    "Compressor — axial":           COMPRESSOR_PORTS,
    "Compressor — centrifugal":     COMPRESSOR_PORTS,
    "Compressor — reciprocating":   COMPRESSOR_PORTS,
    "Compressor — rotary":          COMPRESSOR_PORTS,
    "Fan — axial":                  COMPRESSOR_PORTS,
    "Fan — centrifugal radial":     COMPRESSOR_PORTS,

    "Reactor — autoclave":          REACTOR_PORTS,
    "Reactor — jacketed agitated":  REACTOR_PORTS,
    "Reactor — jacketed non-agit.": REACTOR_PORTS,
    "Reactor — PFR (tubular)":      REACTOR_PORTS,
    "Reactor — CSTR (agitado)":     REACTOR_PORTS,

    "Vessel — vertical":            VESSEL_VERT_PORTS,
    "Vessel — horizontal":          VESSEL_HORZ_PORTS,

    "Tower (column shell)":         TOWER_PORTS,

    "Storage tank — cone roof":     TANK_PORTS,
    "Storage tank — floating roof": TANK_PORTS,

    "Fired heater — non-reformer":  FURNACE_PORTS,
    "Fired heater — reformer":      FURNACE_PORTS,

    "Filter — belt":                SOLIDS_PORTS,
    "Dryer — drum":                 SOLIDS_PORTS,
    "Evaporator — vertical":        SOLIDS_PORTS,
    "Crystallizer":                 SOLIDS_PORTS,

    # Mixers / splitters
    "Mixer — inline":                MIXER_PORTS,
    "Mixer — static":                MIXER_PORTS,
    "Splitter — flow divider":       SPLITTER_PORTS,

    # Separadores adicionales
    "Centrifuge — disc stack":       CENTRIFUGE_PORTS,
    "Centrifuge — decanter":         CENTRIFUGE_PORTS,
    "Cyclone — gas/solid":           CYCLONE_PORTS,
    "Decanter — gravity":            DECANTER_PORTS,

    # Válvulas
    "Valve — control globe":         VALVE_PORTS,
    "Valve — relief":                VALVE_PORTS,
    "Valve — 3-way":                 SPLITTER_PORTS,  # 1 in, 2 out

    # Utilities (planta de servicios)
    "Boiler — fire tube":           BOILER_PORTS,
    "Boiler — water tube":          BOILER_PORTS,
    "Cooling tower — induced draft":COOLING_TOWER_PORTS,
    "Cooling tower — natural draft":COOLING_TOWER_PORTS,
    "Ambient":                      AMBIENT_PORTS,
    "Utility header":               UTIL_HEADER_PORTS,
}


# ======================================================
# ISA-5.1 PREFIXES PARA NAMING AUTOMÁTICO
# ======================================================

ISA_PREFIX = {
    "Heat exch. — U-tube":          "E",
    "Heat exch. — floating head":   "E",
    "Heat exch. — fixed tube":      "E",
    "Heat exch. — flat plate":      "E",
    "Heat exch. — multiple pipe":   "E",
    "Heat exch. — double pipe":     "E",
    "Heat exch. — spiral plate":    "E",
    "Heat exch. — air cooler":      "E",
    "Heat exch. — kettle reboiler": "E",
    "Heat exch. — WHB packaged":      "E",
    "Heat exch. — WHB field erected": "E",

    "Pump — centrifugal":           "P",
    "Pump — positive displacement": "P",
    "Pump — reciprocating":         "P",

    "Compressor — axial":           "K",
    "Compressor — centrifugal":     "K",
    "Compressor — reciprocating":   "K",
    "Compressor — rotary":          "K",
    "Fan — axial":                  "FN",
    "Fan — centrifugal radial":     "FN",

    "Reactor — autoclave":          "R",
    "Reactor — jacketed agitated":  "R",
    "Reactor — jacketed non-agit.": "R",
    "Reactor — PFR (tubular)":      "R",
    "Reactor — CSTR (agitado)":     "R",

    "Vessel — vertical":            "V",
    "Vessel — horizontal":          "V",

    "Tower (column shell)":         "T",

    "Storage tank — cone roof":     "TK",
    "Storage tank — floating roof": "TK",

    "Fired heater — non-reformer":  "F",
    "Fired heater — reformer":      "F",

    "Filter — belt":                "FL",
    "Dryer — drum":                 "DR",
    "Evaporator — vertical":        "EV",
    "Crystallizer":                 "CR",

    "Tray — sieve":                 "TR",
    "Tray — valve":                 "TR",
    "Packing — random":             "PK",
    "Packing — structured":         "PK",

    # Mixers / splitters
    "Mixer — inline":                "MX",
    "Mixer — static":                "MX",
    "Splitter — flow divider":       "SP",
    # Separadores adicionales
    "Centrifuge — disc stack":       "CF",
    "Centrifuge — decanter":         "CF",
    "Cyclone — gas/solid":           "CY",
    "Decanter — gravity":            "D",
    # Válvulas
    "Valve — control globe":         "FV",
    "Valve — relief":                "PSV",
    "Valve — 3-way":                 "FV",

    # Utilities — caldera B-101, torre CT-101
    "Boiler — fire tube":           "B",
    "Boiler — water tube":          "B",
    "Cooling tower — induced draft":"CT",
    "Cooling tower — natural draft":"CT",
}


# ======================================================
# HELPERS
# ======================================================

def get_ports(eq_type):
    """Dict {port_name: (side, frac)} para el eq_type.
    Si no está catalogado, devuelve DEFAULT_PORTS."""
    return EQUIPMENT_PORTS.get(eq_type, DEFAULT_PORTS)


def get_isa_prefix(eq_type):
    """Prefix ISA-5.1 para naming ('E', 'P', ...).
    'X' si el eq_type no está en el catálogo."""
    return ISA_PREFIX.get(eq_type, "X")


def next_block_name(eq_type, existing_names):
    """Siguiente nombre disponible para un bloque de este eq_type
    usando ISA prefix + autoincrement empezando en 101.

    existing_names: iterable con todos los nombres ya en el flowsheet.

    Ejemplo: si existen E-101 y E-102, devuelve 'E-103'.
    """
    prefix = get_isa_prefix(eq_type)
    used = set(existing_names)
    n = 101
    while f"{prefix}-{n}" in used:
        n += 1
    return f"{prefix}-{n}"


def autoselect_outlet(eq_type, used_ports=()):
    """Primer puerto de salida disponible para un eq_type.
    Prioriza lado right > top > bottom > left.
    used_ports: nombres ya conectados como salida en este bloque."""
    ports = get_ports(eq_type)
    used = set(used_ports)
    for preferred_side in ("right", "top", "bottom", "left"):
        for pname, (side, _frac) in ports.items():
            if side == preferred_side and pname not in used:
                return pname
    return next(iter(ports))


def autoselect_inlet(eq_type, used_ports=()):
    """Primer puerto de entrada disponible.
    Prioriza lado left > top > bottom > right."""
    ports = get_ports(eq_type)
    used = set(used_ports)
    for preferred_side in ("left", "top", "bottom", "right"):
        for pname, (side, _frac) in ports.items():
            if side == preferred_side and pname not in used:
                return pname
    return next(iter(ports))


# ======================================================
# AUTO-CONFIG DE reactor_mode AL CREAR EL BLOQUE
# ======================================================
# Algunos eq_types del catálogo implican un modelo de solver
# específico (Capa 5).  Cuando el usuario arrastra uno de estos
# desde la biblioteca, el bloque debe nacer con reactor_mode ya
# seteado para que el solver lo trate como PFR/CSTR sin que el
# user tenga que abrir el diálogo de edición.
#
# Los reactores físicos (autoclave, jacketed agitated/non-agit.)
# NO están acá: quedan en "equilibrium" (default backward-compat),
# y el user elige el modo manualmente si quiere cinética.
REACTOR_MODE_BY_TYPE = {
    "Reactor — PFR (tubular)":  "pfr",
    "Reactor — CSTR (agitado)": "cstr",
    "Reactor — autoclave":      "batch",   # autoclave = batch agitado
}


def default_reactor_mode(eq_type):
    """Devuelve el reactor_mode implícito por el tipo de equipo, o
    None si el tipo no fuerza un modo (caso normal: el bloque usa
    el default de la dataclass Block, 'equilibrium')."""
    return REACTOR_MODE_BY_TYPE.get(eq_type)


def apply_type_defaults(block):
    """Aplica defaults dependientes del eq_type a un Block recién
    creado.  Hoy solo configura reactor_mode para PFR/CSTR; es el
    punto único de extensión para futuros defaults por tipo.

    Idempotente: solo escribe reactor_mode si el tipo lo fuerza.
    No toca reactor_volume_L (lo declara el user) — pero el solver
    ya avisa con un mensaje claro si V<=0 en modo pfr/cstr."""
    mode = default_reactor_mode(block.eq_type)
    if mode is not None:
        block.reactor_mode = mode
    return block


# ======================================================
# CLASIFICACIÓN PARA LABOR (Turton §8.3)
# ======================================================
# Fórmula de Turton para operadores por turno:
#   Nol = (6.29 + 31.7·P² + 0.23·Nnp)^0.5
# donde:
#   P   = etapas que manejan sólidos particulados
#         (filter, dryer, evaporator, crystallizer, ...)
#   Nnp = equipos no-particulados que sí cuentan
#         (HX, reactor, tower, vessel, compresor, horno)
# Bombas, tanques de almacenamiento, fans/blowers
# tradicionalmente NO se cuentan (Turton/Towler).
# Operadores totales año = Nol × 4.5  (cobertura 24/7 +
# vacaciones + ausentismo, factor estándar Turton).

LABOR_CLASSIFICATION = {
    # particulate (manejo de sólidos) — entran en P
    "Filter — belt":                "particulate",
    "Dryer — drum":                 "particulate",
    "Evaporator — vertical":        "particulate",
    "Crystallizer":                 "particulate",

    # excluidos del conteo (Turton/Towler)
    "Pump — centrifugal":           "excluded",
    "Pump — positive displacement": "excluded",
    "Pump — reciprocating":         "excluded",
    "Storage tank — cone roof":     "excluded",
    "Storage tank — floating roof": "excluded",
    "Fan — axial":                  "excluded",
    "Fan — centrifugal radial":     "excluded",
    "Tray — sieve":                 "excluded",  # interno de columna
    "Tray — valve":                 "excluded",
    "Packing — random":             "excluded",  # interno de columna
    "Packing — structured":         "excluded",
}

# default para los que no estén en el dict arriba: non-particulate
DEFAULT_LABOR_CLASS = "non-particulate"

# parámetros Turton — defaults vienen de econ_defaults.py (perfil activo).
# Acá quedan como aliases para back-compat con código que importaba estos
# nombres directo; las funciones de costing los releen del profile.
try:
    import econ_defaults as _econ
    TURTON_SHIFT_FACTOR  = _econ.get_labor()["shift_factor"]
    TURTON_SALARY_USD_YR = _econ.get_labor()["salary_per_operator_usd_yr"]
except Exception:
    TURTON_SHIFT_FACTOR  = 4.5
    TURTON_SALARY_USD_YR = 25_000


def labor_class_for(eq_type):
    """Devuelve 'particulate', 'non-particulate' o 'excluded'."""
    return LABOR_CLASSIFICATION.get(eq_type, DEFAULT_LABOR_CLASS)


def count_for_labor(blocks):
    """Cuenta (P, Nnp, excluded) para la fórmula Turton.

    blocks: iterable de objetos con atributo .eq_type y .n
    (cantidad de unidades en paralelo: cuentan como N unidades).
    """
    P = Nnp = excl = 0
    for b in blocks:
        cls = labor_class_for(b.eq_type)
        units = max(1, int(getattr(b, "n", 1)))
        if cls == "particulate":
            P   += units
        elif cls == "non-particulate":
            Nnp += units
        else:
            excl += units
    return P, Nnp, excl


def turton_operators(blocks, shift_factor=None):
    """Operadores por turno (Nol) y totales año.

    Args:
        blocks:        iterable de bloques con .eq_type y .n
        shift_factor:  default desde econ_defaults (4.5 PE)

    Returns:
        dict con keys:
          'P', 'Nnp', 'excluded'        — conteos
          'Nol'                         — operadores/turno (float, antes de redondeo)
          'n_total'                     — operadores totales año (int)
    """
    import math
    if shift_factor is None:
        try:
            shift_factor = _econ.get_labor()["shift_factor"]
        except Exception:
            shift_factor = TURTON_SHIFT_FACTOR
    P, Nnp, excluded = count_for_labor(blocks)
    Nol = math.sqrt(6.29 + 31.7 * P * P + 0.23 * Nnp)
    n_total = math.ceil(Nol * shift_factor)
    return {
        "P":         P,
        "Nnp":       Nnp,
        "excluded":  excluded,
        "Nol":       Nol,
        "n_total":   n_total,
    }


def turton_labor_cost(blocks, salary_per_op=None, shift_factor=None):
    """Costo anual de mano de obra según Turton.

    Args:
        blocks:        iterable de bloques
        salary_per_op: USD/yr por operador.  Default: econ_defaults
                       (perfil activo).
        shift_factor:  default: econ_defaults.

    Returns:
        dict con keys de turton_operators + 'salary_per_op' +
        'labor_usd_yr'.
    """
    if salary_per_op is None:
        try:
            salary_per_op = _econ.get_labor()["salary_per_operator_usd_yr"]
        except Exception:
            salary_per_op = TURTON_SALARY_USD_YR
    res = turton_operators(blocks, shift_factor=shift_factor)
    res["salary_per_op"] = salary_per_op
    res["labor_usd_yr"]  = res["n_total"] * salary_per_op
    return res


# ======================================================
# UTILIDADES (utilities) — coupling duty → opex_extras
# ======================================================
# Cada utility tiene:
#   name      → nombre legible para df_variable
#   units     → 'tm' o 'kWh'
#   price     → USD/unit (mercado Perú 2024, estimaciones)
#   delta_h   → kJ/kg de calor entregable o removible
#               (heating: latente vapor / LHV fuel)
#               (cooling: Cp × ΔT de circulación)
#   type      → 'heating', 'cooling', 'electrical'
#   T_range   → (T_min, T_max) °C donde la utility es aplicable
#   efficiency→ eficiencia térmica del equipo que la usa
#               (heaters/coolers ~1.0, hornos ~0.85, bombas ~0.65)

UTILITIES = {
    "steam_LP": {
        "name":       "Steam LP (5 barg)",
        "units":      "tm",
        "price":      20.0,
        "delta_h":    2200,   # kJ/kg latente a 160°C
        "type":       "heating",
        "T_range":    (50, 150),
        "efficiency": 0.95,
    },
    "steam_MP": {
        "name":       "Steam MP (11 barg)",
        "units":      "tm",
        "price":      25.0,
        "delta_h":    2000,
        "type":       "heating",
        "T_range":    (140, 220),
        "efficiency": 0.95,
    },
    "steam_HP": {
        "name":       "Steam HP (40 barg)",
        "units":      "tm",
        "price":      28.0,
        "delta_h":    1700,
        "type":       "heating",
        "T_range":    (200, 280),
        "efficiency": 0.95,
    },
    "fuel_gas": {
        "name":       "Fuel gas (natural)",
        "units":      "tm",
        "price":      300.0,
        "delta_h":    50_000,  # LHV gas natural típico
        "type":       "heating",
        "T_range":    (250, 1200),
        "efficiency": 0.85,    # horno típico ~85%
    },
    "cooling_water": {
        "name":       "Cooling water",
        "units":      "tm",
        "price":      0.30,
        "delta_h":    63.0,    # 4.18 kJ/kg·K × 15 °C ΔT típico
        "type":       "cooling",
        "T_range":    (35, 200),  # no enfría debajo de 35°C
        "efficiency": 1.0,
    },
    "refrigeration": {
        "name":       "Refrigerant",
        "units":      "tm",
        "price":      8.0,
        "delta_h":    200,     # latente NH3 / freón
        "type":       "cooling",
        "T_range":    (-50, 35),
        "efficiency": 0.7,
    },
    # ── GENERACIÓN DE VAPOR (waste heat boiler) ──────────────────
    # HX que CEDE calor del proceso vaporizando BFW → exporta vapor.
    # price NEGATIVO = ingreso por exportación (≈ precio de compra del
    # steam equivalente).  T_sat = T de saturación del lado frío (para
    # el LMTD: el agua hierve a T constante, no es el rango de CW).
    "bfw_to_steam_HP": {
        "name":       "Steam HP (BFW→export)",
        "units":      "tm",
        "price":      -28.0,   # revenue por exportar HP steam
        "delta_h":    1700,
        "type":       "generation",
        "T_range":    (220, 280),
        "T_sat":      250,
        "efficiency": 0.85,    # pérdidas: no todo el calor → vapor útil
    },
    "bfw_to_steam_MP": {
        "name":       "Steam MP (BFW→export)",
        "units":      "tm",
        "price":      -25.0,
        "delta_h":    2000,
        "type":       "generation",
        "T_range":    (160, 220),
        "T_sat":      184,
        "efficiency": 0.85,
    },
    "bfw_to_steam_LP": {
        "name":       "Steam LP (BFW→export)",
        "units":      "tm",
        "price":      -20.0,
        "delta_h":    2200,
        "type":       "generation",
        "T_range":    (110, 160),
        "T_sat":      152,
        "efficiency": 0.85,
    },
    "electricity": {
        "name":       "Electricity",
        "units":      "kWh",
        "price":      0.08,
        "type":       "electrical",
        "efficiency": 0.85,    # eficiencia eléctrica del motor + driver
    },
}


# Re-inyectar PRECIOS desde econ_defaults.py (perfil activo) — así el
# user cambia de PE_2024 a USA_2024 y los precios se actualizan sin
# tocar este módulo.  Las propiedades termodinámicas (delta_h, T_range,
# efficiency) son leyes físicas y permanecen hardcoded acá.
try:
    _prices_overrides = _econ.get_utility_prices()
    for _k, _pdict in _prices_overrides.items():
        if _k in UTILITIES:
            UTILITIES[_k]["price"] = float(_pdict.get("price",
                                                       UTILITIES[_k]["price"]))
            if "unit" in _pdict and UTILITIES[_k].get("units") != _pdict["unit"]:
                UTILITIES[_k]["units"] = _pdict["unit"]
except Exception:
    pass


def refresh_utility_prices():
    """Re-aplica precios desde econ_defaults (perfil activo).  Llamar
    si el usuario cambia el perfil en runtime."""
    try:
        prices = _econ.get_utility_prices()
        for k, pdict in prices.items():
            if k in UTILITIES:
                UTILITIES[k]["price"] = float(pdict.get("price",
                                                         UTILITIES[k]["price"]))
                if "unit" in pdict and UTILITIES[k].get("units") != pdict["unit"]:
                    UTILITIES[k]["units"] = pdict["unit"]
    except Exception:
        pass


# Equipos cuyo "duty" es POTENCIA ELÉCTRICA (kW eléctricos),
# no calor térmico.  En estos el duty se convierte directamente
# a kWh/año.
ELECTRICAL_EQUIPMENT = {
    "Pump — centrifugal", "Pump — positive displacement",
    "Pump — reciprocating",
    "Compressor — axial", "Compressor — centrifugal",
    "Compressor — reciprocating", "Compressor — rotary",
    "Fan — axial", "Fan — centrifugal radial",
}


def is_electrical_equipment(eq_type):
    return eq_type in ELECTRICAL_EQUIPMENT


# Tipos de HX que estructuralmente pueden GENERAR vapor (waste-heat boiler):
# el kettle reboiler (proxy histórico) y las clases WHB dedicadas (Sinnott).
WHB_EQ_TYPES = (
    "Heat exch. — kettle reboiler",
    "Heat exch. — WHB packaged",
    "Heat exch. — WHB field erected",
)


def autoselect_heat_source(eq_type, duty_kw, T_avg):
    """Elige la utility apropiada para un bloque dado su tipo,
    duty (kW) y temperatura promedio del proceso (°C).

    Returns:
        clave de UTILITIES o '' si duty=0 (adiabático).
    """
    if duty_kw == 0:
        return ""
    if is_electrical_equipment(eq_type):
        return "electricity"
    if duty_kw > 0:
        # heating: elegir steam según T del proceso (con ΔT mínimo
        # de 20°C entre utility y proceso)
        if T_avg < 120:
            return "steam_LP"
        if T_avg < 200:
            return "steam_MP"
        if T_avg < 260:
            return "steam_HP"
        return "fuel_gas"

    # duty_kw < 0  → cooling
    # Un WHB (kettle reboiler o las clases WHB dedicadas) que extrae calor
    # a alta T es estructuralmente un waste-heat boiler: vaporiza BFW y
    # EXPORTA vapor (revenue) en vez de tirar el calor a cooling water.
    # La utility de generación se elige por la T del proceso (Tsat).
    if eq_type in WHB_EQ_TYPES:
        if T_avg > 220:
            return "bfw_to_steam_HP"
        if T_avg > 160:
            return "bfw_to_steam_MP"
        if T_avg > 110:
            return "bfw_to_steam_LP"
    # Resto de coolers: agua o refrigerante (la advertencia de "alta T,
    # debería ser WHB" la emite size_heat_exchanger en sus diagnostics).
    if T_avg > 35:
        return "cooling_water"
    return "refrigeration"


def resolve_heat_source(b, T_avg):
    """Resuelve la utility de un bloque respetando heat_source_locked.

    · heat_source_locked=True → devuelve b.heat_source LITERAL (incluso
      vacío) — el user forzó la utility, no se auto-selecciona.
    · si no, usa b.heat_source si está seteado, o autoselect.
    """
    if getattr(b, "heat_source_locked", False):
        return getattr(b, "heat_source", "") or ""
    return (getattr(b, "heat_source", "") or
            autoselect_heat_source(b.eq_type, b.duty, T_avg))


def utility_consumption(util_key, duty_kw_abs):
    """Calcula el consumo anual de una utility dado el duty absoluto
    del bloque (kW) y la operación 8760 h/año (factor de servicio
    se aplica fuera).

    Returns:
        consumo en las unidades de la utility (tm o kWh por año).
    """
    if util_key not in UTILITIES:
        return 0.0
    util = UTILITIES[util_key]
    eff = util.get("efficiency", 1.0)
    duty = abs(duty_kw_abs)

    if util["type"] == "electrical":
        # Q[kW] × 8760 h × (1/η) = kWh/año
        # Para bombas/compresores la "duty" ya viene como potencia al eje;
        # el motor agrega su η.
        return duty * 8760.0 / eff

    # heating o cooling: convertir kW térmicos a tm/año via ΔH_vap
    from flowsheet_model import SEC_PER_YEAR        # única fuente §6.3
    Q_kJ_per_year = duty * SEC_PER_YEAR              # kJ/año (kW · s = kJ)
    delta_h = util.get("delta_h", 1.0)
    mass_kg = Q_kJ_per_year / delta_h
    if util["type"] == "heating":
        mass_kg /= eff       # ineficiencia del horno/equipo
    elif util["type"] == "generation":
        mass_kg *= eff       # sólo η del calor cedido → vapor exportable
    return mass_kg / 1000.0  # tm/año

