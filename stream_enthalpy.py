"""
STREAM_ENTHALPY — entalpía térmica de corrientes (FUENTE ÚNICA).

Entalpía física "térmica" (sensible + latente) referida a líquido a
T_REF=25 °C, en kJ/kg.  NO incluye entalpía de formación ni de mezcla (es
una entalpía física de corriente, consistente entre corrientes de igual
composición), por lo que la variación a través de un bloque captura el
cambio sensible/latente — para un HX coincide con el duty térmico.

ESTE módulo es la ÚNICA implementación de entalpía de corriente del
proyecto.  El solver (flowsheet_solver._stream_enthalpy_kW) y la UI
(stream_bubbles, stream_inspector, flowsheet_qt) consumen las MISMAS
funciones de acá — antes había una copia divergente en el solver que
resolvía cp/Δh_vap mejor (vía main_component, components.py legacy y
overrides) mientras la UI caía a 0 silencioso.  Unificadas en la versión
del solver (canónica) en PR-C.

Convención de "no resoluble": las funciones devuelven None (no 0) cuando
no pueden resolver cp/Δh_vap, para que la UI muestre "n/d" en vez de un 0
engañoso.

API:
  specific_enthalpy_kJ_kg(composition, T_C, phase, vapor_fraction=0.0) -> float|None
  stream_enthalpy_kW(stream)                ṁ·h  → kW (potencia entálpica) | None
  block_delta_h_kW(streams_in, streams_out) Σ_out − Σ_in  → kW | None
"""
from __future__ import annotations

from typing import Dict, List, Optional

# Constantes compartidas con el modelo (single source of truth).  Fallback
# defensivo por si flowsheet_model no está disponible al importar.
try:
    from flowsheet_model import T_REF_C, SEC_PER_YEAR, TM_TO_KG
except Exception:                       # pragma: no cover
    T_REF_C = 25.0
    SEC_PER_YEAR = 8760.0 * 3600.0
    TM_TO_KG = 1000.0


# ──────────────────────────────────────────────────────────────────────
# Resolución stream-aware de propiedades (movida desde flowsheet_solver
# en PR-C — era la versión canónica que resolvía más casos).
# ──────────────────────────────────────────────────────────────────────
def _resolve_cp(s, T_eval=None):
    """Devuelve el Cp (kJ/kg·K) de un stream a la temperatura T_eval
    (default = s.temperature).

    Prioridad:
      1. THERMO_DB (DIPPR-100 polinomio cuártico, mucho más preciso a
         alta T) — si el componente está cubierto.
      2. components.py legacy (Cp lineal) — fallback para componentes
         no en thermo_db (genéricos, etc.).
      3. s.cp > 0 (override manual) — constante.
      4. None.
    """
    if T_eval is None:
        T_eval = s.temperature
    phase = s.phase or "liquid"

    # --- Prioridad 1: thermo_db (DIPPR) ---
    try:
        import thermo_db as _td
    except ImportError:
        _td = None
    if _td is not None:
        if s.composition:
            cp = _td.cp_mix_kJ_kg_K(s.composition, T_eval, phase)
            if cp > 0:
                return cp
        if s.main_component:
            cp = _td.cp_kJ_kg_K(s.main_component, T_eval, phase)
            if cp is not None and cp > 0:
                return cp

    # --- Prioridad 2: components.py legacy (Cp lineal) ---
    try:
        import components as comp_mod
    except ImportError:
        comp_mod = None
    if comp_mod is not None:
        if s.composition:
            cp = comp_mod.cp_mix_kJ_kg_K(s.composition, T_eval, phase)
            if cp > 0:
                return cp
        if s.main_component:
            c = comp_mod.get(s.main_component)
            if c is not None:
                return c.cp(T_eval, phase)

    if s.cp > 0:
        return s.cp
    return None


def _resolve_dh_vap(s):
    """ΔH_vap de un stream (kJ/kg).  None si no se puede calcular.

    Prioridad:
      1. s.delta_h_vap_override (manual del user).
      2. THERMO_DB (Clausius-Clapeyron derivado de Antoine — varía con T).
      3. components.py legacy (constante en Tb).
    """
    if s.delta_h_vap_override > 0:
        return s.delta_h_vap_override

    T_eval = s.temperature

    # --- Prioridad 1: thermo_db (Clausius-Clapeyron) ---
    try:
        import thermo_db as _td
    except ImportError:
        _td = None
    if _td is not None:
        if s.composition:
            dh = _td.delta_h_vap_mix_kJ_kg(s.composition, T_eval)
            if dh > 0:
                return dh
        if s.main_component:
            dh = _td.delta_h_vap_kJ_kg(s.main_component, T_eval)
            if dh is not None and dh > 0:
                return dh

    # --- Prioridad 2: components.py legacy ---
    try:
        import components as comp_mod
    except ImportError:
        return None
    if s.composition:
        dh = comp_mod.delta_h_vap_mix(s.composition)
        if dh > 0:
            return dh
    if s.main_component:
        c = comp_mod.get(s.main_component)
        if c is not None:
            return c.dh_vap
    return None


def stream_enthalpy_kW(s) -> Optional[float]:
    """Entalpía total de una corriente referida a T_REF_C, kW.
    Incluye:
      · sensible heat: m·Cp·(T - T_REF)
      · latente: si phase = 'vapor', sumar ΔH_vap completo
                 si phase = 'two_phase', sumar vapor_fraction × ΔH_vap

    Cp se evalúa a la temperatura promedio entre T_REF y T (mejor
    aproximación que evaluar en T sola, para Cp(T) variable).

    Devuelve None si ṁ ≤ 0 o si no se puede resolver Cp (NO devuelve 0,
    para que la UI muestre "n/d" en vez de un 0 engañoso).
    """
    if s.mass_flow <= 0:
        return None

    # Cp a T promedio (mejora vs evaluar solo en T)
    T_avg = (s.temperature + T_REF_C) / 2.0
    cp = _resolve_cp(s, T_eval=T_avg)
    if cp is None or cp <= 0:
        return None

    m_kg_s = (s.mass_flow * TM_TO_KG) / SEC_PER_YEAR
    h_sensible = m_kg_s * cp * (s.temperature - T_REF_C)

    # contribución latente si hay cambio de fase respecto al estado
    # de referencia (líquido a T_REF).
    h_latent = 0.0
    if s.phase in ("vapor", "gas"):
        dh = _resolve_dh_vap(s)
        if dh is not None:
            h_latent = m_kg_s * dh
    elif s.phase == "two_phase":
        dh = _resolve_dh_vap(s)
        if dh is not None:
            h_latent = m_kg_s * s.vapor_fraction * dh

    return h_sensible + h_latent


# ──────────────────────────────────────────────────────────────────────
# Shim composición→stream para reusar la resolución stream-aware desde la
# API basada en composición (la usa la UI: bubbles / inspector).
# ──────────────────────────────────────────────────────────────────────
class _CompStream:
    """Stream mínimo construido desde (composition, T, phase, vfrac) para
    alimentar _resolve_cp / _resolve_dh_vap sin un Stream real."""
    __slots__ = ("composition", "temperature", "phase", "vapor_fraction",
                 "main_component", "cp", "delta_h_vap_override", "mass_flow")

    def __init__(self, composition, T_C, phase, vapor_fraction):
        self.composition = composition or {}
        self.temperature = float(T_C)
        self.phase = (phase or "liquid")
        self.vapor_fraction = float(vapor_fraction or 0.0)
        self.main_component = ""
        self.cp = 0.0
        self.delta_h_vap_override = 0.0
        self.mass_flow = 1.0


def specific_enthalpy_kJ_kg(composition: Dict[str, float], T_C: float,
                            phase: str = "liquid",
                            vapor_fraction: float = 0.0) -> Optional[float]:
    """Entalpía específica [kJ/kg] de la mezcla a T (°C) y fase dada,
    referida a líquido saturado a 25 °C.  Reimplementada sobre la
    resolución canónica (_resolve_cp / _resolve_dh_vap).

        líquido:  h = Cp·(T − 25)
        vapor:    h = Cp·(T − 25) + ΔH_vap(T)
        2-fase:   h = Cp·(T − 25) + V·ΔH_vap(T)   (V = vapor_fraction)

    Devuelve None (no 0) si no se puede resolver el Cp de la mezcla.
    """
    sh = _CompStream(composition, T_C, phase, vapor_fraction)
    T_avg = 0.5 * (sh.temperature + T_REF_C)
    cp = _resolve_cp(sh, T_eval=T_avg)
    if cp is None or cp <= 0:
        return None
    h = cp * (sh.temperature - T_REF_C)
    ph = sh.phase.lower()
    if ph in ("vapor", "gas"):
        frac_vap = 1.0
    elif ph in ("two_phase", "2ph", "mixed"):
        frac_vap = max(0.0, min(1.0, sh.vapor_fraction))
    else:
        frac_vap = 0.0
    if frac_vap > 0:
        dhv = _resolve_dh_vap(sh)
        if dhv is not None and dhv > 0:
            h += frac_vap * dhv
    return h


def block_delta_h_kW(streams_in: List, streams_out: List) -> Optional[float]:
    """ΔH a través de un bloque [kW] = Σ(ṁ·h)_salida − Σ(ṁ·h)_entrada.
    Para un HX coincide aproximadamente con el duty térmico.

    Devuelve None si ALGUNA corriente no resuelve su entalpía (para no
    reportar un ΔH engañoso construido sobre ceros silenciosos)."""
    h_in = 0.0
    for s in streams_in:
        h = stream_enthalpy_kW(s)
        if h is None:
            return None
        h_in += h
    h_out = 0.0
    for s in streams_out:
        h = stream_enthalpy_kW(s)
        if h is None:
            return None
        h_out += h
    return h_out - h_in
