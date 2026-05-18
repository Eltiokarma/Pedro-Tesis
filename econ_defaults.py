"""
econ_defaults.py — Defaults económicos centralizados.

Antes había 'magic numbers' dispersos en 4-5 módulos:
  · equipment_ports.py:  salario operador, precios de utilities
  · equipment_costs.py:  tax_rate, disc_rate, fracciones CGR
  · flowsheet_export.py: sensibilidad ±25 %, hurdle rate
  · templates.py:        Labor default, fracciones FCOP/CAPEX

Acá se concentran TODOS los valores económicos editables del modelo,
con su unidad, rango típico y fuente.  Si tu mercado real difiere
(otro país, año, contrato laboral, contrato eléctrico, etc.), editás
acá y el cambio se propaga a todos los costing/profitability calcs.

NO se ponen acá:
  · Propiedades físicas de utilities (delta_h vapor, LHV gas, Cp agua)
    — esas son leyes termodinámicas, no economía.
  · Coeficientes de la ecuación Turton 8.2 (0.180, 0.305, 2.73, 1.23)
    — son LA fórmula, no parámetros ajustables.
  · Correlaciones Cp Turton (K1, K2, K3) — base CEPCI=397 año 2001.
  · Valores técnicos de sizing (U coef HX, τ residencia, ρ liq/gas)
    — esos viven en equipment_sizing.py.

Para cambiar defaults sin tocar Python: editá los dicts abajo,
o llamá load_profile("USA_2024") / etc. para perfiles regionales.
"""
from typing import Dict, Any
import copy


# ─────────────────────────────────────────────────────────────
# CEPCI year target (escalado de costos desde 2001 Turton)
# ─────────────────────────────────────────────────────────────
CEPCI_YEAR_TARGET = 2026


# ─────────────────────────────────────────────────────────────
# MANO DE OBRA (Turton § 8.3)
# ─────────────────────────────────────────────────────────────
LABOR = {
    "salary_per_operator_usd_yr": 25_000,
    # PE 2024: ~S/. 3 500/mes × 14 sueldos + cargas sociales (ESSALUD,
    # AFP, gratificaciones, CTS) ≈ USD 25 000/yr.
    # USA: ~80 000.  Chile: ~30 000.  Europa: ~50 000.

    "shift_factor": 4.5,
    # Turton: 4.5 = 5 turnos rotativos cubriendo 24/7 con vacaciones
    # y ausentismo.  Para planta 8h/día sería 1.2-1.5.
}


# ─────────────────────────────────────────────────────────────
# UTILITIES — precios (mercado Perú 2024 estimado)
# Las propiedades térmicas (delta_h, T_range, efficiency) están en
# equipment_ports.UTILITIES por ser leyes físicas, no economía.
# ─────────────────────────────────────────────────────────────
UTILITY_PRICES = {
    "steam_LP":      {"price": 20.0,  "unit": "tm"},   # vapor 5 barg
    "steam_MP":      {"price": 25.0,  "unit": "tm"},   # vapor 11 barg
    "steam_HP":      {"price": 28.0,  "unit": "tm"},   # vapor 40 barg
    "fuel_gas":      {"price": 300.0, "unit": "tm"},   # gas natural
    "cooling_water": {"price": 0.30,  "unit": "tm"},   # agua enfriamiento
    "refrigeration": {"price": 8.0,   "unit": "tm"},   # refrigerante
    "electricity":   {"price": 0.08,  "unit": "kWh"},  # tarifa industrial PE
}


# ─────────────────────────────────────────────────────────────
# FINANCIAL (Turton Ch 9-10)
# ─────────────────────────────────────────────────────────────
FINANCIAL = {
    "tax_rate":           0.30,
    # Impuesto a la renta empresarial: PE 29.5 %, USA fed ~21 % +
    # estado, Chile 27 %, Argentina 35 %.  Acá 30 % como estándar
    # internacional Turton.

    "discount_rate":      0.10,
    # Hurdle rate / WACC.  Turton sugiere 10 % para proyectos
    # químicos estándar; planta grande con financiamiento puede usar
    # 8 %, capital de riesgo 15-20 %.

    "project_years":      10,
    # Horizonte de evaluación NPV.  Turton estándar 10.  Plantas
    # petroleras grandes: 20-25.  Pilots: 5-7.

    "construction_years": 2,
    # Años de inversión antes de operación.

    "salvage_value_frac": 0.0,
    # Fracción de FCI recuperable al final del proyecto.
}


# ─────────────────────────────────────────────────────────────
# CAPITAL ESTIMATION FRACTIONS (Turton Ch 7)
# ─────────────────────────────────────────────────────────────
CAPITAL_FRACS = {
    "OSBL_pct_of_ISBL":         0.30,    # offsites + utility plant
    "engineering_pct":          0.10,    # de (ISBL+OSBL)
    "contingency_pct":          0.10,    # de (ISBL+OSBL), Class 4
    "working_capital_pct":      0.15,    # de FCI

    # Para Grass Roots Capital (Turton Eq 7.10)
    "cgr_contingency_pct":      0.18,    # de ΣCBM
    "cgr_aux_facilities_pct":   0.50,    # de ΣCBM
}


# ─────────────────────────────────────────────────────────────
# FIXED OPEX FRACTIONS (Turton § 8.2)
# Todas son fracciones de Labor / FCI / ISBL+OSBL / WC.
# ─────────────────────────────────────────────────────────────
FCOP_FRACS = {
    "supervision_pct":      0.25,   # de Labor
    "salary_overhead_pct":  0.50,   # de (Labor + Supervision)
    "maintenance_pct":      0.04,   # de FCI (planta continua 4 %)
    "plant_overhead_pct":   0.50,   # de (Labor + Maintenance)
    "tax_insurance_pct":    0.02,   # de (ISBL + OSBL)
    "interest_pct":         0.08,   # costo de capital
    "general_expenses_pct": 0.01,   # de Working Capital
    "royalties_pct":        0.00,   # default 0; depende de licencia
}


# ─────────────────────────────────────────────────────────────
# SENSITIVITY (AACE Class 4 estimate)
# ─────────────────────────────────────────────────────────────
SENSITIVITY = {
    "low_factor":   0.75,    # -25 % CAPEX/OPEX
    "high_factor":  1.25,    # +25 % CAPEX/OPEX
}


# ─────────────────────────────────────────────────────────────
# HEAT INTEGRATION FACTOR
# Sin Pinch analysis explícito, el solver asigna utility a CADA
# bloque con duty != 0 (cooler usa CW, heater usa steam, etc.).
# En una planta REAL, ~40-60 % del calor se recupera vía cross-
# exchange (corrientes calientes calientan frías), reduciendo CUT.
#
# heat_integration_factor: fracción de CUT que SOBREVIVE después
# de heat integration típica.
#   1.0  → sin integración (greenfield, conservador)
#   0.6  → integración moderada (Pinch básico aplicado)
#   0.4  → integración alta (planta moderna, MINLP optimizada)
#   0.2  → integración extrema (industrial best-in-class)
# Default 0.4 = planta moderna con Pinch razonable (fuente única
# de verdad — flowsheet_export y la UI leen via
# get_heat_integration_factor()).
# ─────────────────────────────────────────────────────────────
HEAT_INTEGRATION = {
    "factor": 0.4,    # planta moderna con Pinch razonable
}


# ─────────────────────────────────────────────────────────────
# COM FORMULA COEFFICIENTS (Turton Eq 8.2)
# ─────────────────────────────────────────────────────────────
# COM_d = α·FCI + β·COL + γ·(CUT + CRM + CWT)
#
# Defaults Turton (planta química standalone con G&A típicos):
#   α = 0.180  →  fixed costs sin labor = 18 % de FCI
#                 (maintenance + supplies + taxes + insurance + overhead)
#   β = 2.73   →  Labor + supervision + direct salary overhead
#   γ = 1.23   →  variable costs × 1.23 incluye:
#                   · ventas y distribución (+10 %)
#                   · I+D (+5 %)
#                   · administración general (+5 %)
#                   · royalties típicos (+3 %)
#
# Cuándo BAJAR γ:
#   1.10  →  refinería integrada (Petroperú): tiene red de
#            distribución propia, G&A absorbidos en precio venta
#   1.05  →  commodity bulk con offtake long-term (no spot sales)
#   1.00  →  internal use (productos consumidos en otra planta del
#            mismo holding, sin G&A asignable)
#
# Cuándo SUBIR γ:
#   1.30  →  productos farmacéuticos / especialidad (más R+D,
#            ventas técnicas, regulatorio FDA/EMA)
#   1.50  →  high-tech / pequeño volumen (semicons, agroquímicos)
# ─────────────────────────────────────────────────────────────
COM_COEFFS = {
    "alpha_fci_d":      0.180,   # CON depreciación (COM_d)
    "alpha_fci":        0.305,   # SIN depreciación (COM)
    "beta_col":         2.73,
    "gamma_variable":   1.23,    # overhead sobre VCOP — el más editable
}


# ─────────────────────────────────────────────────────────────
# PERFILES REGIONALES — overrides sobre los defaults
# ─────────────────────────────────────────────────────────────
PROFILES = {
    "PE_2024": {
        # Perú default — los valores arriba son ya PE 2024.
    },

    "USA_2024": {
        "labor": {"salary_per_operator_usd_yr": 80_000},
        "utility_prices": {
            "electricity": {"price": 0.10, "unit": "kWh"},
            "fuel_gas":    {"price": 200.0, "unit": "tm"},
        },
        "financial": {"tax_rate": 0.27},     # federal + estado promedio
    },

    "CL_2024": {
        "labor": {"salary_per_operator_usd_yr": 30_000},
        "financial": {"tax_rate": 0.27},
        "utility_prices": {"electricity": {"price": 0.12, "unit": "kWh"}},
    },

    "EU_2024": {
        "labor": {"salary_per_operator_usd_yr": 55_000},
        "utility_prices": {
            "electricity": {"price": 0.18, "unit": "kWh"},
            "fuel_gas":    {"price": 450.0, "unit": "tm"},
        },
    },
}


# ─────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────

# Profile activo en el módulo (cambiable runtime via set_profile)
_ACTIVE_PROFILE = "PE_2024"


def load_profile(name: str = "PE_2024") -> Dict[str, Any]:
    """Devuelve dict completo de defaults con overrides del perfil.

    Si name no existe, devuelve los defaults base (PE_2024)."""
    profile = PROFILES.get(name, {})
    result = {
        "labor":          dict(LABOR),
        "utility_prices": copy.deepcopy(UTILITY_PRICES),
        "financial":      dict(FINANCIAL),
        "capital_fracs":  dict(CAPITAL_FRACS),
        "fcop_fracs":     dict(FCOP_FRACS),
        "sensitivity":    dict(SENSITIVITY),
    }
    # Apply profile overrides (shallow merge per section)
    for section, overrides in profile.items():
        if section not in result:
            result[section] = overrides
            continue
        if section == "utility_prices":
            for util, vals in overrides.items():
                if util in result[section]:
                    result[section][util].update(vals)
                else:
                    result[section][util] = dict(vals)
        else:
            result[section].update(overrides)
    return result


def set_active_profile(name: str):
    """Cambia el perfil activo globalmente.  Los módulos que llamen
    get_*() reciben los valores del nuevo perfil."""
    global _ACTIVE_PROFILE
    if name not in PROFILES:
        raise ValueError(f"Perfil desconocido: {name}. "
                          f"Disponibles: {list(PROFILES)}")
    _ACTIVE_PROFILE = name


def active_profile() -> str:
    return _ACTIVE_PROFILE


def get_labor():
    return load_profile(_ACTIVE_PROFILE)["labor"]


def get_utility_prices():
    return load_profile(_ACTIVE_PROFILE)["utility_prices"]


def get_financial():
    return load_profile(_ACTIVE_PROFILE)["financial"]


def get_capital_fracs():
    return load_profile(_ACTIVE_PROFILE)["capital_fracs"]


def get_fcop_fracs():
    return load_profile(_ACTIVE_PROFILE)["fcop_fracs"]


def get_sensitivity():
    return load_profile(_ACTIVE_PROFILE)["sensitivity"]


def get_heat_integration_factor() -> float:
    """Factor (0-1) que se aplica al CUT total para reflejar heat
    integration realista.  Ver HEAT_INTEGRATION dict."""
    return HEAT_INTEGRATION["factor"]


def set_heat_integration_factor(f: float):
    """Setea factor de heat integration (0-1)."""
    if not 0.0 <= f <= 1.0:
        raise ValueError(f"factor debe estar en [0, 1], no {f}")
    HEAT_INTEGRATION["factor"] = float(f)


def get_com_coeffs():
    """Devuelve coeficientes de la ecuación Turton 8.2 (α, β, γ).
    Permite ajustar γ (default 1.23) para refinerías/commodity/specialty."""
    return dict(COM_COEFFS)


def set_com_gamma(gamma: float):
    """Setea γ (overhead sobre variable costs).  Rangos típicos:
        1.05-1.10 → refinería integrada / commodity
        1.23      → planta química standalone (Turton default)
        1.30-1.50 → farma / specialty / agroquímicos"""
    if not 1.0 <= gamma <= 2.0:
        raise ValueError(f"gamma debe estar en [1.0, 2.0], no {gamma}")
    COM_COEFFS["gamma_variable"] = float(gamma)
