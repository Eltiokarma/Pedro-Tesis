"""
FLOWSHEET VALIDATION — reglas semánticas para conexiones entre
equipos de un PFD.

Cada puerto tiene un fluid type (líquido, vapor, gas, steam, etc.).
Al conectar dos puertos, validamos compatibilidad.  Tres niveles:

  ok    silencioso, conexión típica
  warn  conexión atípica pero físicamente posible (ej. salida de
        un reactor a una bomba sin separador previo)
  error conexión físicamente imposible o catastrófica
        (ej. fuel a la succión de una bomba de proceso)

API pública:

  get_port_fluid_type(eq_type, port_name) → str
  validate_connection(fs, src_id, dst_id, src_port, dst_port)
      → (severity, message)
  validate_all_streams(fs)
      → list of (stream_name, severity, message) — para auditoría global

Las reglas vienen del modelo simplificado de Aspen / HYSYS / ChemCAD:
solo chequeamos compatibilidad de FASE, no composición química
(no sabemos qué hay en el stream, solo si es líquido/vapor/etc.).

Para esquemas más rigurosos (ej. validar que se conecta benceno a un
reactor que SOLO acepta benceno) habría que extender Stream con
'composition' y agregar reglas por componente — out of scope acá.
"""

import equipment_ports as ep


# ======================================================
# FLUID TYPES POR PUERTO Y EQUIPO
# ======================================================
# Mapping: eq_type → {port_name: fluid_type}
# Si un eq_type no está en el dict, todos sus puertos se asumen 'any'
# (sin restricción).  Si un puerto específico no está, también 'any'.

PORT_FLUID_TYPES = {

    # ---- Bombas: solo líquido (cavitan con vapor) ----
    "Pump — centrifugal": {
        "succion":   "liquid",
        "descarga":  "liquid",
    },
    "Pump — positive displacement": {
        "succion":   "liquid",
        "descarga":  "liquid",
    },
    "Pump — reciprocating": {
        "succion":   "liquid",
        "descarga":  "liquid",
    },

    # ---- Compresores: solo gas/vapor (no comprimen líquido) ----
    "Compressor — axial": {
        "succion":   "gas",
        "descarga":  "gas",
    },
    "Compressor — centrifugal": {
        "succion":   "gas",
        "descarga":  "gas",
    },
    "Compressor — reciprocating": {
        "succion":   "gas",
        "descarga":  "gas",
    },
    "Compressor — rotary": {
        "succion":   "gas",
        "descarga":  "gas",
    },

    # ---- Fans / blowers: gases (típicamente aire) ----
    "Fan — axial":              {"succion": "gas", "descarga": "gas"},
    "Fan — centrifugal radial": {"succion": "gas", "descarga": "gas"},

    # ---- Heat exchangers de proceso: agnósticos ('any') ----
    # los HX shell-and-tube genéricos pueden manejar cualquier fluido
    "Heat exch. — U-tube":         {"tube_in": "any", "tube_out": "any",
                                     "shell_in": "any", "shell_out": "any"},
    "Heat exch. — floating head":  {"tube_in": "any", "tube_out": "any",
                                     "shell_in": "any", "shell_out": "any"},
    "Heat exch. — fixed tube":     {"tube_in": "any", "tube_out": "any",
                                     "shell_in": "any", "shell_out": "any"},
    "Heat exch. — flat plate":     {"tube_in": "any", "tube_out": "any",
                                     "shell_in": "any", "shell_out": "any"},
    "Heat exch. — multiple pipe":  {"tube_in": "any", "tube_out": "any",
                                     "shell_in": "any", "shell_out": "any"},
    "Heat exch. — double pipe":    {"tube_in": "any", "tube_out": "any",
                                     "shell_in": "any", "shell_out": "any"},
    "Heat exch. — spiral plate":   {"tube_in": "any", "tube_out": "any",
                                     "shell_in": "any", "shell_out": "any"},

    # ---- HX air cooler: lado proceso típicamente vapor → líquido ----
    "Heat exch. — air cooler": {
        "proceso_in":  "any",      # puede entrar vapor o líquido caliente
        "proceso_out": "any",
    },

    # ---- Condensadores: agnósticos como sus HX padre ----
    "Heat exch. — condenser shell-tube": {"tube_in":  "any", "tube_out":  "any",
                                            "shell_in": "any", "shell_out": "any"},
    "Heat exch. — condenser air-cooled": {"proceso_in": "any",
                                            "proceso_out": "any"},

    # ---- HX kettle reboiler: roles muy específicos ----
    "Heat exch. — kettle reboiler": {
        "liq_in":     "liquid",       # del fondo de la columna
        "vap_out":    "vapor",        # vuelve a la columna
        "steam_in":   "steam",        # utility
        "cond_out":   "condensate",
    },

    # ---- Reactores: agnósticos en proceso, utility variable ----
    "Reactor — autoclave": {
        "alimentacion": "any",
        "producto":     "any",
        "util_in":      "any",       # steam, cooling, oil térmico
        "util_out":     "any",
    },
    "Reactor — jacketed agitated": {
        "alimentacion": "any",
        "producto":     "any",
        "util_in":      "any",
        "util_out":     "any",
    },
    "Reactor — jacketed non-agit.": {
        "alimentacion": "any",
        "producto":     "any",
        "util_in":      "any",
        "util_out":     "any",
    },
    "Reactor — PFR (tubular)": {
        "alimentacion": "any",
        "producto":     "any",
        "util_in":      "any",
        "util_out":     "any",
    },
    "Reactor — CSTR (agitado)": {
        "alimentacion": "any",
        "producto":     "any",
        "util_in":      "any",
        "util_out":     "any",
    },

    # ---- Vessels: separadores ----
    # Vertical = flash drum: feed agnóstico, vapor por arriba,
    # líquido por abajo
    "Vessel — vertical": {
        "alimentacion": "any",       # mezcla L/V
        "vapor":        "vapor",
        "liquido":      "liquid",
    },
    "Vessel — horizontal": {
        "alimentacion": "any",
        "vapor":        "vapor",
        "liquido":      "liquid",
    },

    # ---- Tower: columna de destilación ----
    "Tower (column shell)": {
        "alimentacion":         "any",      # mezcla a separar
        "vapor_tope":           "vapor",
        "liquido_fondo":        "liquid",
        "reflujo":              "liquid",   # vuelve del condensador
        "reboiler":             "vapor",    # vuelve del reboiler
        "extraccion_lateral":   "any",
    },

    # ---- Storage tanks: solo líquido ----
    "Storage tank — cone roof": {
        "entrada": "liquid",
        "salida":  "liquid",
    },
    "Storage tank — floating roof": {
        "entrada": "liquid",
        "salida":  "liquid",
    },

    # ---- Fired heaters / hornos: combustible separado del proceso ----
    "Fired heater — non-reformer": {
        "proceso_in":  "any",
        "proceso_out": "any",
        "combustible": "fuel",
        "chimenea":    "flue_gas",
    },
    "Fired heater — reformer": {
        "proceso_in":  "any",
        "proceso_out": "any",
        "combustible": "fuel",
        "chimenea":    "flue_gas",
    },

    # ---- Solids equipment: feed sólido ----
    "Filter — belt": {
        "alimentacion": "slurry",   # líquido + sólido
        "producto":     "solid",
        "util_in":      "any",      # típicamente lavado con agua
        "venteo":       "gas",
    },
    "Dryer — drum": {
        "alimentacion": "slurry",
        "producto":     "solid",
        "util_in":      "any",      # aire caliente típico
        "venteo":       "gas",
    },
    "Evaporator — vertical": {
        "alimentacion": "liquid",
        "producto":     "slurry",   # se concentra
        "util_in":      "steam",
        "venteo":       "vapor",
    },
    "Crystallizer": {
        "alimentacion": "liquid",   # solución sobresaturada
        "producto":     "slurry",
        "util_in":      "any",      # cooling
        "venteo":       "gas",
    },
}


def get_port_fluid_type(eq_type, port_name):
    """Devuelve el fluid type de un puerto.  'any' si no hay regla."""
    eq_ports = PORT_FLUID_TYPES.get(eq_type)
    if eq_ports is None:
        return "any"
    return eq_ports.get(port_name, "any")


# ======================================================
# MATRIZ DE COMPATIBILIDAD
# ======================================================
# from → set de tipos a los que puede conectarse sin problemas (ok).
#
# Conexiones cruzadas no listadas → severity = 'warn' (atípica pero
# físicamente posible, ej. salida de un reactor a una bomba).
#
# Los casos imposibles (ERROR) son explicítos abajo.

COMPATIBLE_OK = {
    "any":          {"any", "liquid", "vapor", "gas", "steam",
                     "condensate", "cooling_water", "fuel",
                     "flue_gas", "solid", "slurry"},
    # liquid: queda líquido (mismo proceso) o vaporiza en un heater
    "liquid":       {"liquid", "vapor", "any"},
    # vapor: queda vapor, condensa, o se trata como gas (sinónimos en PFD)
    "vapor":        {"vapor", "liquid", "gas", "any"},
    # gas: queda gas o se trata como vapor.  gas → liquid es warn
    # (necesita knock-out drum antes para condensar)
    "gas":          {"gas", "vapor", "any"},
    # steam: utility chain (steam → condensate de retorno)
    "steam":        {"steam", "condensate", "any"},
    "condensate":   {"condensate", "liquid", "steam", "any"},
    "cooling_water":{"cooling_water", "liquid", "any"},
    "fuel":         {"fuel", "any"},
    "flue_gas":     {"flue_gas", "any"},
    "solid":        {"solid", "slurry", "any"},
    "slurry":       {"slurry", "solid", "liquid", "any"},
}


# Conexiones explícitamente PROHIBIDAS (severity = 'error').
# Listamos solo las catastróficas — el resto cae en 'warn'.

INCOMPATIBLE_ERROR = {
    # Bombas no aceptan gas (cavitación)
    ("gas",       "liquid"): "Una bomba no puede aspirar gas (cavita).",
    ("vapor",     "liquid"): None,    # warn, no error: puede ser vapor saturado
    # Compresores no aceptan líquido (golpe de líquido)
    ("liquid",    "gas"):    "Un compresor no puede aspirar líquido (golpe de líquido — knock-out drum requerido antes).",
    # Fuel a proceso o viceversa
    ("fuel",      "liquid"): "Combustible no debe ir a un puerto de proceso.",
    ("fuel",      "vapor"):  "Combustible no debe ir a un puerto de proceso.",
    ("fuel",      "gas"):    "Combustible no debe ir a un puerto de proceso (es de servicio).",
    ("liquid",    "fuel"):   "Líquido de proceso no es combustible.",
    ("vapor",     "fuel"):   "Vapor de proceso no es combustible.",
    # Flue gas no se reusa
    ("flue_gas",  "liquid"): "Flue gas (chimenea) no debe ir a proceso.",
    ("flue_gas",  "vapor"):  "Flue gas no debe ir a proceso.",
    ("flue_gas",  "gas"):    "Flue gas no debe ir a proceso.",
    ("flue_gas",  "fuel"):   "Flue gas no se reusa como combustible.",
    # Sólidos en bombas, compresores
    ("solid",     "liquid"): "Sólido no debe ir a línea de líquido (clogging).",
    ("solid",     "vapor"):  "Sólido no debe ir a línea de vapor.",
    ("solid",     "gas"):    "Sólido no debe ir a línea de gas.",
}


# ======================================================
# VALIDACIÓN
# ======================================================

# Normalización de phases declarados en streams para encajar con los tipos
# de puerto.  Si el user escribe "vapor" lo tratamos como "gas" para la
# matriz de compatibilidad.
_PHASE_TO_PORT_TYPE = {
    "gas":        "gas",
    "vapor":      "gas",
    "two_phase":  "gas",      # mezcla; el lado vapor es el limitante
    "liquid":     "liquid",
    "fuel":       "fuel",
    "flue_gas":   "flue_gas",
    "solid":      "solid",
    "slurry":     "slurry",
    "steam":      "steam",
    "condensate": "condensate",
}


def validate_connection(fs, src_id, dst_id, src_port, dst_port,
                        stream_phase=None):
    """Valida una conexión propuesta entre dos puertos.

    `stream_phase` (opcional): si el stream tiene un `phase` declarado por
    el user (gas/vapor/liquid/solid/…), úsalo como la verdad para validar
    el destino — un tanque "liquid" que en realidad almacena gas (TK de
    N2/CO/aire) deja de disparar 'compresor no puede aspirar liquido'
    cuando el stream declara phase='gas'.

    Returns:
        (severity, message)
        severity: 'ok' | 'warn' | 'error'
        message: str (None si ok)
    """
    src_block = fs.blocks.get(src_id)
    dst_block = fs.blocks.get(dst_id)
    if src_block is None or dst_block is None:
        return "error", "Bloque no existe"
    if src_id == dst_id:
        return "error", "Un equipo no puede conectarse a sí mismo (a menos que sea un reciclo intencional vía otro bloque)"

    src_type = get_port_fluid_type(src_block.eq_type, src_port)
    dst_type = get_port_fluid_type(dst_block.eq_type, dst_port)

    # Si el stream declara fase, esa es la verdad — no la inferida por
    # eq_type.  Sobreescribimos src_type para reflejar lo que realmente
    # sale del source.  El dst_type del puerto sigue siendo el "espera"
    # del equipo destino.
    if stream_phase:
        eff = _PHASE_TO_PORT_TYPE.get(stream_phase.lower())
        if eff:
            src_type = eff

    # 1. Caso explícitamente prohibido
    error_msg = INCOMPATIBLE_ERROR.get((src_type, dst_type))
    if error_msg:
        return "error", (
            f"{src_block.name}.{src_port} ({src_type})  →  "
            f"{dst_block.name}.{dst_port} ({dst_type}):\n\n"
            f"{error_msg}"
        )

    # 2. Caso compatible OK
    compatible_with = COMPATIBLE_OK.get(src_type, set())
    if dst_type in compatible_with:
        return "ok", None

    # 3. Caso atípico (warn)
    return "warn", (
        f"Conexión atípica:\n"
        f"  {src_block.name}.{src_port}  →  {dst_block.name}.{dst_port}\n"
        f"  ({src_type} → {dst_type})\n\n"
        f"Físicamente posible pero no es una conexión estándar.\n"
        f"Verificá que tenga sentido en tu proceso."
    )


def validate_all_streams(fs):
    """Audita todos los streams existentes.  Devuelve list of
    (stream_name, severity, message) — solo para severity != 'ok'."""
    issues = []
    for s in fs.streams.values():
        # Las corrientes auxiliares auto-instanciadas (cooling water, aire,
        # combustible, chimenea, …) son generadas por el sistema y conectan
        # a puertos de utility/ambiente — no deben disparar warnings de
        # conexión atípica ni de puerto huérfano.
        if getattr(s, "auto_aux", False):
            continue
        sev, msg = validate_connection(
            fs, s.src, s.dst, s.src_port, s.dst_port,
            stream_phase=(getattr(s, "phase", "") or "") or None,
        )
        if sev != "ok":
            issues.append((s.name, sev, msg))
    return issues
