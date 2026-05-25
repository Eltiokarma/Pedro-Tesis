"""
STREAM_ENTHALPY — entalpía térmica de corrientes para la UI.

Entalpía específica "térmica" (sensible + latente) referida a líquido a
T_REF=25 °C, en kJ/kg.  NO incluye entalpía de formación (es una entalpía
física de corriente, consistente entre corrientes de igual composición),
por lo que la variación a través de un bloque captura el cambio
sensible/latente — para un HX coincide con el duty térmico.

API:
  specific_enthalpy_kJ_kg(composition, T_C, phase, vapor_fraction=0.0)
  stream_enthalpy_kW(stream)        ṁ·h  → kW (potencia entálpica)
  block_delta_h_kW(streams_in, streams_out)   Σ_out − Σ_in  → kW
"""
from __future__ import annotations

from typing import Dict, List

T_REF_C = 25.0


def specific_enthalpy_kJ_kg(composition: Dict[str, float], T_C: float,
                            phase: str = "liquid",
                            vapor_fraction: float = 0.0) -> float:
    """Entalpía específica [kJ/kg] de la mezcla a T (°C) y fase dada,
    referida a líquido saturado a 25 °C.

        líquido:  h = Cp_liq·(T − 25)
        vapor:    h = Cp_liq·(T − 25) + ΔH_vap(T)
        2-fase:   h = h_liq + V·ΔH_vap(T)   (V = vapor_fraction)
    """
    try:
        import thermo_db as _td
    except ImportError:
        return 0.0
    if not composition:
        return 0.0
    ph = (phase or "").lower()
    # Cp evaluado en el punto medio del intervalo (mejor "Cp promedio").
    T_mid = 0.5 * (T_C + T_REF_C)
    cp_liq = _td.cp_mix_kJ_kg_K(composition, T_mid, "liquid")
    if not cp_liq or cp_liq <= 0:
        cp_liq = _td.cp_mix_kJ_kg_K(composition, T_mid, "gas") or 2.0
    h_sens = cp_liq * (T_C - T_REF_C)
    if ph in ("vapor", "gas"):
        frac_vap = 1.0
    elif ph in ("two_phase", "2ph", "mixed"):
        frac_vap = max(0.0, min(1.0, float(vapor_fraction or 0.0)))
    else:
        frac_vap = 0.0
    if frac_vap > 0:
        dhv = _td.delta_h_vap_mix_kJ_kg(composition, T_C)
        if dhv and dhv > 0:
            h_sens += frac_vap * dhv
    return h_sens


def stream_enthalpy_kW(stream) -> float:
    """Potencia entálpica de la corriente [kW] = ṁ[kg/s]·h[kJ/kg].
    mass_flow del modelo está en tm/año → kg/s."""
    try:
        from flowsheet_model import SEC_PER_YEAR
    except Exception:
        SEC_PER_YEAR = 8760.0 * 3600.0
    mdot_kg_s = float(getattr(stream, "mass_flow", 0.0) or 0.0) * 1000.0 / SEC_PER_YEAR
    if mdot_kg_s <= 0:
        return 0.0
    h = specific_enthalpy_kJ_kg(
        getattr(stream, "composition", {}) or {},
        float(getattr(stream, "temperature", T_REF_C) or T_REF_C),
        getattr(stream, "phase", "") or "",
        getattr(stream, "vapor_fraction", 0.0) or 0.0,
    )
    return mdot_kg_s * h


def block_delta_h_kW(streams_in: List, streams_out: List) -> float:
    """ΔH a través de un bloque [kW] = Σ(ṁ·h)_salida − Σ(ṁ·h)_entrada.
    Para un HX coincide aproximadamente con el duty térmico."""
    h_in = sum(stream_enthalpy_kW(s) for s in streams_in)
    h_out = sum(stream_enthalpy_kW(s) for s in streams_out)
    return h_out - h_in
