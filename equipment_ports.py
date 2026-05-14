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

# Heat exchanger genérico (shell-and-tube): 4 puertos
HX_PORTS = {
    "tube_in":   ("left",  0.30),
    "tube_out":  ("right", 0.30),
    "shell_in":  ("right", 0.70),
    "shell_out": ("left",  0.70),
}

# Air cooler: solo el lado de proceso (el aire se omite del PFD)
AIR_COOLER_PORTS = {
    "proceso_in":  ("left",  0.5),
    "proceso_out": ("right", 0.5),
}

# Reboiler kettle: lado proceso (líquido fondo / vapor de retorno)
# + lado servicio (vapor / condensado)
REBOILER_PORTS = {
    "liq_in":     ("left",  0.30),    # del fondo de la columna
    "vap_out":    ("right", 0.30),    # vapor de retorno
    "steam_in":   ("left",  0.70),
    "cond_out":   ("right", 0.70),
}

# Pump
PUMP_PORTS = {
    "succion":   ("left",  0.5),
    "descarga":  ("right", 0.5),
}

# Compressor / Fan
COMPRESSOR_PORTS = {
    "succion":   ("left",  0.5),
    "descarga":  ("right", 0.5),
}

# Reactor con servicios de utilidad (chaqueta o serpentín)
REACTOR_PORTS = {
    "alimentacion": ("left",  0.5),
    "producto":     ("right", 0.5),
    "util_in":      ("top",   0.30),
    "util_out":     ("top",   0.70),
}

# Vessel vertical (flash drum, separador)
VESSEL_VERT_PORTS = {
    "alimentacion": ("left",   0.5),
    "vapor":        ("top",    0.5),
    "liquido":      ("bottom", 0.5),
}

# Vessel horizontal (KO drum)
VESSEL_HORZ_PORTS = {
    "alimentacion": ("left",   0.5),
    "vapor":        ("top",    0.7),
    "liquido":      ("right",  0.5),
}

# Tower / columna
TOWER_PORTS = {
    "alimentacion":      ("left",   0.5),
    "vapor_tope":        ("top",    0.5),
    "liquido_fondo":     ("bottom", 0.5),
    "reflujo":           ("top",    0.20),
    "reboiler":          ("bottom", 0.20),
    "extraccion_lateral":("right",  0.5),
}

# Storage tank
TANK_PORTS = {
    "entrada": ("top",    0.5),
    "salida":  ("bottom", 0.5),
}

# Fired heater / horno
FURNACE_PORTS = {
    "proceso_in":  ("left",   0.5),
    "proceso_out": ("right",  0.5),
    "combustible": ("bottom", 0.30),
    "chimenea":    ("top",    0.5),
}

# Solids: filter, dryer, evaporator, crystallizer
SOLIDS_PORTS = {
    "alimentacion": ("left",   0.5),
    "producto":     ("right",  0.5),
    "util_in":      ("top",    0.5),
    "venteo":       ("top",    0.20),
}

# Fallback (equipos no catalogados)
DEFAULT_PORTS = {
    "in":  ("left",  0.5),
    "out": ("right", 0.5),
}


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
}

# default para los que no estén en el dict arriba: non-particulate
DEFAULT_LABOR_CLASS = "non-particulate"

# parámetros Turton
TURTON_SHIFT_FACTOR  = 4.5     # turnos × cobertura para operación 24/7
TURTON_SALARY_USD_YR = 25_000  # salario operador industrial Perú (sueldo + cargas)


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


def turton_operators(blocks):
    """Operadores por turno (Nol) y totales año.

    Returns:
        dict con keys:
          'P', 'Nnp', 'excluded'        — conteos
          'Nol'                         — operadores/turno (float, antes de redondeo)
          'n_total'                     — operadores totales año (int)
    """
    import math
    P, Nnp, excluded = count_for_labor(blocks)
    Nol = math.sqrt(6.29 + 31.7 * P * P + 0.23 * Nnp)
    n_total = math.ceil(Nol * TURTON_SHIFT_FACTOR)
    return {
        "P":         P,
        "Nnp":       Nnp,
        "excluded":  excluded,
        "Nol":       Nol,
        "n_total":   n_total,
    }


def turton_labor_cost(blocks, salary_per_op=TURTON_SALARY_USD_YR):
    """Costo anual de mano de obra según Turton.

    Returns:
        dict con keys de turton_operators + 'labor_usd_yr'.
    """
    res = turton_operators(blocks)
    res["salary_per_op"] = salary_per_op
    res["labor_usd_yr"]  = res["n_total"] * salary_per_op
    return res

