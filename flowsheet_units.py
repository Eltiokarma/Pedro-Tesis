"""
FLOWSHEET UNITS — conversión de unidades de flujo másico para la UI.

El modelo guarda mass_flow internamente en **tm/año** (siempre).
Para mostrar valores en la UI, convertimos hacia/desde esta unidad
canónica.

API:
  FLOW_UNITS                       lista de (clave, label) en orden de menú
  to_display(value_tm_yr, unit)    tm/año → unidad de display
  from_display(value, unit)        unidad de display → tm/año
  format_flow(value_tm_yr, unit)   string para UI (ej "11.000 tm/año")

Unidades soportadas (sin requerir peso molecular):

    tm/año    tonelada métrica por año            (1)
    kg/h      kilogramo por hora                  (1000/8760)
    kg/s      kilogramo por segundo               (1000/(8760·3600))
    t/d       tonelada por día                    (1/365)
    lb/h      libra por hora                      (2204.62/8760)

Para soportar kmol/hr o flujo en moles habría que extender Stream
con peso molecular del fluido — out of scope.

OPERACIÓN
  asumimos operación continua 8760 h/año (factor de servicio 100%).
  Si el proyecto define operating_hours_per_year en el flowsheet,
  ese override aplica.  Hoy usamos 8760 fijo.
"""

HOURS_PER_YEAR = 8760.0
SEC_PER_YEAR   = HOURS_PER_YEAR * 3600.0


# Factor de conversión: tm/año × factor = unidad_display
# inverso: unidad_display / factor = tm/año
FLOW_FACTORS = {
    "tm/año":  1.0,
    "kg/h":    1000.0 / HOURS_PER_YEAR,
    "kg/s":    1000.0 / SEC_PER_YEAR,
    "t/d":     1.0 / 365.0,
    "lb/h":    2204.6226 / HOURS_PER_YEAR,
}

# Orden de aparición en menús
FLOW_UNITS_ORDER = ["tm/año", "kg/h", "kg/s", "t/d", "lb/h"]


def to_display(value_tm_yr, unit):
    """tm/año (modelo) → valor en la unidad de display."""
    if unit not in FLOW_FACTORS:
        return value_tm_yr
    return float(value_tm_yr) * FLOW_FACTORS[unit]


def from_display(value, unit):
    """unidad de display → tm/año (modelo)."""
    if unit not in FLOW_FACTORS or FLOW_FACTORS[unit] == 0:
        return float(value)
    return float(value) / FLOW_FACTORS[unit]


def format_flow(value_tm_yr, unit):
    """String formateado para UI.  Usa formato adecuado según la
    magnitud de la unidad."""
    v = to_display(value_tm_yr, unit)
    if unit == "kg/s":
        return f"{v:.3g} {unit}"
    if abs(v) < 1:
        return f"{v:.3g} {unit}"
    if abs(v) < 100:
        return f"{v:.2f} {unit}"
    if abs(v) < 100_000:
        return f"{v:,.0f} {unit}".replace(",", " ")
    return f"{v:.3e} {unit}"


# ════════════════════════════════════════════════════════
#  SISTEMA GLOBAL DE UNIDADES (flujo + T + P + energía)
# ════════════════════════════════════════════════════════
# Unidades canónicas del modelo: flujo tm/año · T °C · P bar · energía kW.
# El "sistema activo" elige una unidad de display por magnitud; afecta UI
# y exportación.  Default = unidades del modelo (no cambia el look actual
# hasta que el usuario elija otro sistema con el botón global).

TEMP_UNITS_ORDER     = ["°C", "K", "°F"]
PRESSURE_UNITS_ORDER = ["bar", "kPa", "atm", "psi", "MPa"]
ENERGY_UNITS_ORDER   = ["kW", "MW", "Gcal/h", "MMBtu/h", "hp"]

# bar × factor = unidad
PRESSURE_FACTORS = {
    "bar": 1.0, "kPa": 100.0, "MPa": 0.1,
    "atm": 1.0 / 1.01325, "psi": 14.503773773,
}
# kW × factor = unidad
ENERGY_FACTORS = {
    "kW": 1.0, "MW": 1e-3,
    "Gcal/h": 0.000859845, "MMBtu/h": 0.00341214, "hp": 1.3410220896,
}

# Presets de sistema de unidades (el "botón general")
UNIT_SYSTEMS = {
    "Modelo (tm/año)":      {"flow": "tm/año", "temp": "°C", "pressure": "bar", "energy": "kW"},
    "Métrico (ingeniería)": {"flow": "kg/h",   "temp": "°C", "pressure": "bar", "energy": "kW"},
    "SI estricto":          {"flow": "kg/s",   "temp": "K",  "pressure": "kPa", "energy": "kW"},
    "Imperial (US)":        {"flow": "lb/h",   "temp": "°F", "pressure": "psi", "energy": "MMBtu/h"},
    "Magnitudes grandes":   {"flow": "t/d",    "temp": "°C", "pressure": "bar", "energy": "MW"},
}
UNIT_SYSTEMS_ORDER = ["Modelo (tm/año)", "Métrico (ingeniería)", "SI estricto",
                      "Imperial (US)", "Magnitudes grandes"]

_ACTIVE = dict(UNIT_SYSTEMS["Modelo (tm/año)"])


def active():
    """Copia del dict de unidades activas (flow/temp/pressure/energy)."""
    return dict(_ACTIVE)


def active_unit(quantity):
    return _ACTIVE.get(quantity)


def set_quantity(quantity, unit):
    if quantity in _ACTIVE:
        _ACTIVE[quantity] = unit


def set_system(name):
    """Aplica un preset global.  Devuelve True si existe."""
    if name in UNIT_SYSTEMS:
        _ACTIVE.update(UNIT_SYSTEMS[name])
        return True
    return False


def current_system():
    """Nombre del preset que coincide con el estado activo, o 'Personalizado'."""
    for name, units in UNIT_SYSTEMS.items():
        if all(_ACTIVE.get(k) == v for k, v in units.items()):
            return name
    return "Personalizado"


# ── Temperatura (canónica °C; offset, no factor puro) ──
def conv_temp(value_C, unit=None):
    unit = unit or _ACTIVE["temp"]
    if value_C is None:
        return None
    if unit == "K":
        return float(value_C) + 273.15
    if unit in ("°F", "F"):
        return float(value_C) * 9.0 / 5.0 + 32.0
    return float(value_C)


def fmt_temp(value_C, unit=None):
    unit = unit or _ACTIVE["temp"]
    v = conv_temp(value_C, unit)
    return "—" if v is None else f"{v:.1f} {unit}"


# ── Presión (canónica bar) ──
def conv_pressure(value_bar, unit=None):
    unit = unit or _ACTIVE["pressure"]
    if value_bar is None:
        return None
    return float(value_bar) * PRESSURE_FACTORS.get(unit, 1.0)


def fmt_pressure(value_bar, unit=None):
    unit = unit or _ACTIVE["pressure"]
    v = conv_pressure(value_bar, unit)
    if v is None:
        return "—"
    if abs(v) >= 1000:
        return f"{v:,.0f} {unit}".replace(",", " ")
    return f"{v:.3g} {unit}"


# ── Energía / potencia (canónica kW) ──
def conv_energy(value_kW, unit=None):
    unit = unit or _ACTIVE["energy"]
    if value_kW is None:
        return None
    return float(value_kW) * ENERGY_FACTORS.get(unit, 1.0)


def fmt_energy(value_kW, unit=None):
    unit = unit or _ACTIVE["energy"]
    v = conv_energy(value_kW, unit)
    if v is None:
        return "—"
    if abs(v) >= 10000:
        return f"{v:,.0f} {unit}".replace(",", " ")
    return f"{v:.4g} {unit}"


# ── Flujo (wrappers que usan la unidad activa por default) ──
def conv_flow(value_tm_yr, unit=None):
    return to_display(value_tm_yr, unit or _ACTIVE["flow"])


def fmt_flow(value_tm_yr, unit=None):
    return format_flow(value_tm_yr, unit or _ACTIVE["flow"])
