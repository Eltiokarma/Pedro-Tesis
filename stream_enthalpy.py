"""
STREAM_ENTHALPY — entalpía térmica de corrientes (FUENTE ÚNICA).

Entalpía física "térmica" (sensible + latente) referida a líquido a
T_REF=25 °C, o gas a 25 °C para gases permanentes, en kJ/kg.
Integra Cp de cada fase y utiliza un salto de referencia fijo; NO añade
ΔHvap(T) al calor sensible de gas (eso viola dh/dT=Cp). NO incluye
entalpía de formación ni de mezcla (es
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

import copy
import math
from functools import lru_cache
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
def _canonical_caloric_name(name):
    import thermo_db
    import components
    component = thermo_db.get(name) or components.get(name)
    return component.name if component is not None else name


def _component_qualities(s):
    """Validate an explicit species allocation; unused reaction keys allowed."""
    declared = getattr(s, "component_vapor_fractions", {})
    if not isinstance(declared, dict):
        return None
    result = {}
    for name, fraction in declared.items():
        if not isinstance(fraction, (int, float)) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
            return None
        key = _canonical_caloric_name(name)
        if key in result and result[key] != fraction:
            return None
        result[key] = fraction
    composition = s.composition or ({s.main_component: 1.0} if s.main_component else {})
    if result and any(w > 0 and _canonical_caloric_name(name) not in result
                      for name, w in composition.items()):
        return None
    return result


def resolved_vapor_fraction(s):
    """Actual mass quality from explicit allocation, or the bulk phase spec."""
    qualities = _component_qualities(s)
    if qualities is None:
        return None
    if qualities:
        composition = s.composition or ({s.main_component: 1.0} if s.main_component else {})
        if (not composition or any(not math.isfinite(w) or w < 0 for w in composition.values())
                or sum(composition.values()) <= 0):
            return None
        return sum(w * qualities[_canonical_caloric_name(name)]
                   for name, w in composition.items() if w > 0) / sum(composition.values())
    phase = (s.phase or "liquid").lower()
    quality = (1.0 if phase in ("gas", "vapor") else
               s.vapor_fraction if phase in ("two_phase", "2ph", "mixed") else 0.0)
    return quality if math.isfinite(quality) and 0 <= quality <= 1 else None


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

    # Resolve each species through the same database -> legacy -> manual
    # sequence as enthalpy. A positive partial mixture sum is not a Cp.
    import thermo_db as td
    import components

    composition = s.composition or ({s.main_component: 1.0}
                                      if s.main_component else {})
    if not composition:
        return s.cp if math.isfinite(s.cp) and s.cp > 0 else None
    if any(not math.isfinite(w) or w < 0 for w in composition.values()):
        return None
    total = sum(composition.values())
    if total <= 0:
        return None
    qualities = _component_qualities(s)
    quality = resolved_vapor_fraction(s)
    if qualities is None or quality is None:
        return None
    result = 0.0
    for name, fraction in composition.items():
        if fraction == 0:
            continue
        beta = qualities[_canonical_caloric_name(name)] if qualities else quality
        for phase_fraction, component_phase in ((1-beta, "liquid"), (beta, "gas")):
            if phase_fraction == 0:
                continue
            cp = td.cp_kJ_kg_K(name, T_eval, component_phase)
            if cp is None or not math.isfinite(cp) or not 0.1 <= cp <= 50:
                legacy = components.get(name)
                cp = legacy.cp(T_eval, component_phase) if legacy is not None else None
            if cp is None or not math.isfinite(cp) or cp <= 0:
                cp = s.cp if math.isfinite(s.cp) and s.cp > 0 else None
            if cp is None:
                return None
            result += fraction / total * phase_fraction * cp
    return result



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
    Integra Cp(T) con una referencia fija por especie/fase y mezcla por
    fracción másica. Un caudal cero transporta exactamente cero energía.
    Devuelve None para caudales negativos o propiedades no resolubles.
    """
    if not math.isfinite(s.mass_flow) or s.mass_flow < 0:
        return None
    if s.mass_flow == 0:
        return 0.0
    h = _specific_stream_enthalpy(s)
    return None if h is None else s.mass_flow * TM_TO_KG / SEC_PER_YEAR * h


@lru_cache(maxsize=16384)
def _integral_dippr(coefs, mw, lo, hi):
    """Cache numerical integration by immutable coefficients, never name.

    Edits to the property database/overlay naturally produce a new key.
    """
    mid, half = (lo + hi) / 2.0 + 273.15, (hi - lo) / 2.0
    a, b, c, d, e = coefs
    values = []
    for x in (-math.sqrt(3/5), 0.0, math.sqrt(3/5)):
        T = mid + half*x
        cp = ((((e*T+d)*T+c)*T+b)*T+a) / (1000*mw)
        # Match the existing resolver's policy before using its fast path.
        if not math.isfinite(cp) or cp < .1 or cp > 50:
            return None
        values.append(cp)
    return half * (5*values[0] + 8*values[1] + 5*values[2]) / 9


def _integral_cp(s, lo, hi, phase):
    """Three-point Gauss integration: exact for the quartic DIPPR Cp.

    Cp is always evaluated in the requested phase.  Never differentiate
    a temperature-dependent latent heat as though it were sensible heat.
    """
    if s.main_component:
        import thermo_db as td
        comp = td.get(s.main_component)
        if comp is not None and comp.cp_condensed_powers:
            low, high = comp.cp_condensed_range_K
            u, v = lo + 273.15, hi + 273.15
            if min(u, v) < low or max(u, v) > high:
                return None
            return sum(a * (math.log(v/u) if p == -1 else
                            (v**(p+1)-u**(p+1))/(p+1))
                       for p, a in comp.cp_condensed_powers)
        if comp is not None and phase in ("gas", "vapor") and comp.cp_gas_shomate:
            # Shomate contains E/t², so use its analytic integral rather
            # than the polynomial quadrature. Split at validity boundaries.
            tlo, thi = sorted((lo + 273.15, hi + 273.15))
            cursor, integral = tlo, 0.0
            for aT, bT, a, b, c, d, e in comp.cp_gas_shomate:
                end = min(thi, bT)
                if aT <= cursor <= end:
                    u, v = cursor / 1000, end / 1000
                    integral += 1000 * (a*(v-u) + b*(v*v-u*u)/2
                        + c*(v**3-u**3)/3 + d*(v**4-u**4)/4 - e*(1/v-1/u))
                    cursor = end
                    if cursor >= thi:
                        return (1 if hi >= lo else -1) * integral / comp.mw
            return None
        if comp is not None and comp.mw > 0:
            coefs = comp.cp_gas_coefs if phase in ("gas", "vapor") else comp.cp_liq_coefs
            if coefs is not None:
                integral = _integral_dippr(tuple(coefs), comp.mw, lo, hi)
                if integral is not None:
                    return integral
    probe = copy.copy(s)
    probe.phase = phase
    mid, half = (lo + hi) / 2.0, (hi - lo) / 2.0
    values = [_resolve_cp(probe, mid + half * x)
              for x in (-math.sqrt(3 / 5), 0.0, math.sqrt(3 / 5))]
    if any(v is None or not math.isfinite(v) or v <= 0 for v in values):
        return None
    return half * (5 * values[0] + 8 * values[1] + 5 * values[2]) / 9


def _species_streams(s):
    """Resolve every positive mass fraction, never drop unknown species."""
    comp = s.composition or ({s.main_component: 1.0} if s.main_component else {})
    if not comp:
        return [(1.0, s)]
    if any(not math.isfinite(w) or w < 0 for w in comp.values()):
        return None
    total = sum(comp.values())
    if total <= 0:
        return None
    parts = []
    for name, w in comp.items():
        if w == 0:
            continue
        # A caloric probe only needs these slots, not the complete mutable
        # flowsheet Stream (which carries UI, hydraulic and locking state).
        probe = _CompStream({name: 1.0}, s.temperature, s.phase, s.vapor_fraction)
        probe.main_component = name
        probe.cp = s.cp
        probe.delta_h_vap_override = s.delta_h_vap_override
        parts.append((w / total, probe))
    return parts


def _gas_reference_offset(s):
    """Fixed h_gas(25 C), relative to h_liquid(25 C)=0 where defined.

    Use formation-enthalpy differences when available (Hess' law).
    Otherwise follow liquid sensible -> boiling latent -> gas sensible.
    Permanent gases with Tc below 25 C use gas at 25 C as reference:
    extrapolating a nonexistent liquid to 25 C is not a valid reference.
    No pressure departure or excess enthalpy is represented in this model.
    """
    import thermo_db as td
    c = td.get(s.main_component) if s.main_component else None
    if c is not None and c.cp_condensed_powers:
        return 0.0  # carried particles retain their condensed reference
    if c is not None and s.delta_h_vap_override <= 0:
        if c.tc_c is not None and c.tc_c <= T_REF_C:
            return 0.0
        if (c.mw > 0 and c.dh_f_gas_kJ_mol is not None
                and c.dh_f_liq_kJ_mol is not None):
            return (c.dh_f_gas_kJ_mol - c.dh_f_liq_kJ_mol) * 1000 / c.mw
    # A manual latent-heat override is anchored at the normal boiling
    # point as well (25 C only when no boiling point is known).
    # A normal boiling point below the reference is still usable if the
    # subcritical liquid Cp and the boiling latent heat are available.
    tb = c.tb_c if c is not None else T_REF_C
    probe = copy.copy(s)
    probe.temperature = tb
    latent = _resolve_dh_vap(probe)
    if latent is None:
        # No liquid reference data: use the declared gas reference at 25 C.
        return 0.0
    hl = _integral_cp(s, T_REF_C, tb, "liquid")
    hg = _integral_cp(s, T_REF_C, tb, "gas")
    if hl is None or hg is None:
        return None
    return hl + latent - hg


def reference_phase_offset_kJ_kg(s, phase="gas"):
    """Reference offset for converting gas-based reaction heat to this basis.

    Reaction balances use sum(m_out * offset) - sum(m_in * offset)
    when combining gas-reference reaction heats with thermal enthalpies.
    """
    if phase not in ("gas", "vapor"):
        return 0.0
    parts = _species_streams(s)
    if parts is None:
        return None
    result = 0.0
    for w, probe in parts:
        offset = _gas_reference_offset(probe)
        if offset is None:
            return None
        result += w * offset
    return result


def _specific_stream_enthalpy(s):
    if not math.isfinite(s.temperature) or s.temperature <= -273.15:
        return None
    qualities = _component_qualities(s)
    bulk_beta = resolved_vapor_fraction(s)
    if qualities is None or bulk_beta is None:
        return None
    parts = _species_streams(s)
    if parts is None:
        return None
    result = 0.0
    for w, probe in parts:
        beta = qualities[_canonical_caloric_name(probe.main_component)] if qualities else bulk_beta
        hl = _liquid_enthalpy(probe, s.temperature) if beta < 1 else 0.0
        hg = 0.0
        if beta > 0:
            offset = _gas_reference_offset(probe)
            sensible = _integral_cp(probe, T_REF_C, s.temperature, "gas")
            if offset is None or sensible is None:
                return None
            hg = offset + sensible
        if hl is None:
            return None
        result += w * ((1 - beta) * hl + beta * hg)
    return result


def _liquid_enthalpy(s, temperature):
    """Use a reachable boiling reference for cryogenic permanent gases.

    Their zero is gas at 25 C: cool that gas to Tb, condense there, then
    integrate liquid Cp from Tb. Integrating liquid Cp from 25 C crosses
    the critical point and extrapolates a phase that does not exist.
    """
    import thermo_db as td
    component = td.get(s.main_component) if s.main_component else None
    if (component is None or component.tc_c is None
            or component.tc_c > T_REF_C or component.cp_condensed_powers):
        return _integral_cp(s, T_REF_C, temperature, "liquid")
    boiling = component.tb_c
    probe = copy.copy(s)
    probe.temperature = boiling
    latent = _resolve_dh_vap(probe)
    gas_to_boiling = _integral_cp(s, T_REF_C, boiling, "gas")
    liquid_sensible = _integral_cp(s, boiling, temperature, "liquid")
    if latent is None or gas_to_boiling is None or liquid_sensible is None:
        return None
    return gas_to_boiling - latent + liquid_sensible


def temperature_for_enthalpy(s, target_kW, lo_C=-273.14, hi_C=2000.0):
    """Invert the same fixed-phase caloric model without mutating the stream.

    Returns None for invalid/unbracketed states.  Phase and (mass) quality
    are fixed: a pressure-enthalpy equilibrium flash is a separate problem.
    """
    if s.mass_flow <= 0 or not math.isfinite(target_kW):
        return None
    target = target_kW * SEC_PER_YEAR / (s.mass_flow * TM_TO_KG)
    probe = copy.copy(s)
    # Expand around the current state: avoids evaluating invalid Cp at
    # arbitrary extreme temperatures when the answer is nearby.
    centre = min(max(s.temperature, lo_C), hi_C)
    bracket = []
    for width in (0, 10, 30, 100, 300, 1000, hi_C - lo_C):
        for T in (max(lo_C, centre - width), min(hi_C, centre + width)):
            probe.temperature = T
            h = _specific_stream_enthalpy(probe)
            if h is not None and math.isfinite(h):
                bracket.append((T, h - target))
        bracket.sort()
        for (lo, flo), (hi, fhi) in zip(bracket, bracket[1:]):
            if abs(flo) <= 1e-8:
                return lo
            if flo * fhi <= 0:
                for _ in range(80):
                    mid = (lo + hi) / 2
                    probe.temperature = mid
                    hmid = _specific_stream_enthalpy(probe)
                    if hmid is None:
                        return None
                    fm = hmid - target
                    if abs(fm) <= 1e-8 or hi - lo < 1e-8:
                        return mid
                    if flo * fm <= 0:
                        hi = mid
                    else:
                        lo, flo = mid, fm
                return (lo + hi) / 2
    return None


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
    """Entalpía específica [kJ/kg] mediante el mismo modelo que el solver.

    h_liq = integral(Cp_liq, 25, T); h_gas = offset + integral(Cp_gas,25,T).
    Two-phase interpolates these with the MASS vapor fraction.  Pressure
    departures and excess/mixing enthalpy are outside this caloric model.
    """
    sh = _CompStream(composition, T_C, phase, vapor_fraction)
    return _specific_stream_enthalpy(sh)


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
