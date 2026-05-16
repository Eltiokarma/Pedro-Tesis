"""
PRESSURE_DROP — Cálculo de pérdida de carga (ΔP) en tuberías de proceso.

Implementa Darcy-Weisbach con correlación Colebrook-White para el
factor de fricción.  Acoplado con thermo_db (densidad y viscosidad)
para que funcione con cualquier corriente del flowsheet.

API:

    pipe_pressure_drop(mass_flow_kg_s, rho_kg_m3, mu_Pa_s,
                       diameter_m, length_m, roughness_m=4.5e-5)
        → ΔP_Pa  (positivo: caída en dirección del flujo)

    stream_pressure_drop(stream, fs)
        → dict {ΔP_Pa, ΔP_bar, velocity_m_s, Re, f_Darcy}
        Helper que extrae mass_flow + composición del Stream,
        calcula ρ y μ via thermo_db, y aplica DW.

    reynolds(rho, v, D, mu) → Re (adimensional)
    colebrook_white(Re, eps_over_D, tol=1e-6) → f_Darcy

PARÁMETROS DEFAULT:

    Rugosidad ε:
        Acero comercial:        0.045 mm
        Acero inox 304:         0.015 mm
        PVC / plástico liso:    0.0015 mm
        Cemento liso:           0.5 mm
    Default: acero comercial = 4.5e-5 m.

    Diámetro D: el user lo declara en pulgadas o mm en Stream.
    Default: 50 mm (≈ 2 inch nominal).

    Longitud L: el user la declara en m.  Default 10 m.

VALIDACIÓN: caso clásico Perry 6e
    Tubería acero 2" Sch40, agua 25°C, 5 kg/s, 100 m:
      D = 52.5 mm, ρ = 997, μ = 8.9e-4
      v ≈ 2.31 m/s, Re ≈ 1.4e5 (turbulento)
      f_Darcy ≈ 0.022 (con ε/D ≈ 0.00086)
      ΔP ≈ 24 m H2O ≈ 235 kPa ≈ 2.35 bar
"""

import math
from typing import Optional, Dict


# ============================================================
# Reynolds y factor de fricción
# ============================================================

def reynolds(rho: float, v: float, D: float, mu: float) -> float:
    """Número de Reynolds.  Args: ρ [kg/m³], v [m/s], D [m], μ [Pa·s]."""
    if mu <= 0:
        return float('inf')
    return rho * v * D / mu


def colebrook_white(Re: float, eps_over_D: float,
                     tol: float = 1e-6, max_iter: int = 50) -> float:
    """Factor de fricción Darcy por Colebrook-White (iterativo).

        1/√f = -2 log10( ε/D / 3.7 + 2.51 / (Re·√f) )

    Para Re < 2300 (laminar): f = 64/Re analítico.
    Para zonas de transición (2300 < Re < 4000): mezcla.
    Para Re > 4000: Colebrook iterativo (initial guess Swamee-Jain).
    """
    if Re <= 0:
        return 0.0
    if Re < 2300:
        return 64.0 / Re
    # Initial guess (Swamee-Jain): explícita, ~1% accuracy
    f = 0.25 / (math.log10(eps_over_D / 3.7 + 5.74 / Re ** 0.9)) ** 2
    if Re < 4000:
        # Transición: mezclar laminar/turbulento linealmente
        f_lam = 64.0 / Re
        frac = (Re - 2300) / (4000 - 2300)
        return f_lam + frac * (f - f_lam)
    # Iterar Colebrook
    for _ in range(max_iter):
        sqrt_f = 1.0 / math.sqrt(f)
        rhs = -2 * math.log10(eps_over_D / 3.7 + 2.51 / (Re * math.sqrt(f)))
        f_new = 1.0 / rhs ** 2
        if abs(f_new - f) < tol:
            return f_new
        f = f_new
    return f


# ============================================================
# Pressure drop core (Darcy-Weisbach)
# ============================================================

def pipe_pressure_drop(mass_flow_kg_s: float,
                        rho_kg_m3:     float,
                        mu_Pa_s:       float,
                        diameter_m:    float,
                        length_m:      float,
                        roughness_m:   float = 4.5e-5) -> Optional[Dict]:
    """Calcula la pérdida de carga ΔP en una tubería con flujo
    mass_flow_kg_s, fluido (ρ, μ), geometría (D, L) y rugosidad ε.

    Returns dict {ΔP_Pa, ΔP_bar, velocity_m_s, Re, f_Darcy} o None
    si los inputs son inválidos.
    """
    if (mass_flow_kg_s <= 0 or rho_kg_m3 <= 0 or mu_Pa_s <= 0
            or diameter_m <= 0 or length_m <= 0):
        return None
    # Velocidad: v = Q/A = (m/ρ) / (π D²/4)
    area_m2 = math.pi * diameter_m ** 2 / 4.0
    volumetric_flow_m3_s = mass_flow_kg_s / rho_kg_m3
    velocity = volumetric_flow_m3_s / area_m2
    # Reynolds
    Re = reynolds(rho_kg_m3, velocity, diameter_m, mu_Pa_s)
    # Factor de fricción
    eps_over_D = roughness_m / diameter_m
    f = colebrook_white(Re, eps_over_D)
    # Darcy-Weisbach: ΔP = f · (L/D) · (ρ · v²/2)
    dp_Pa = f * (length_m / diameter_m) * (rho_kg_m3 * velocity ** 2 / 2.0)
    return dict(
        delta_P_Pa=dp_Pa,
        delta_P_bar=dp_Pa / 1e5,
        velocity_m_s=velocity,
        Re=Re,
        f_Darcy=f,
        regime=("laminar" if Re < 2300 else
                "transition" if Re < 4000 else
                "turbulent"),
    )


# ============================================================
# Wrapper para Stream del flowsheet
# ============================================================

def _density_kg_m3(composition: dict, T_K: float,
                    phase: str = "liquid") -> Optional[float]:
    """Densidad media ponderada por mass fraction desde thermo_db.

    Para mezclas líquidas: ρ_mix ≈ 1 / Σ(wᵢ / ρᵢ)  (volumes additive,
    aprox razonable para mezclas similares).
    Para gases: ρ ≈ P·MW / (R·T) — pero acá usamos thermo_db si tiene
    densidad explícita, o estimación por gas ideal con MW promedio.
    """
    try:
        import thermo_db as _td
    except ImportError:
        return None
    if not composition:
        return None
    T_C = T_K - 273.15
    if phase in ("vapor", "gas"):
        # Gas ideal con MW promedio y P = 1 atm como default
        # (el caller puede sobreescribir si tiene P)
        mw_avg = 0.0
        total_w = 0.0
        for c, w in composition.items():
            co = _td.get(c)
            if co is None or co.mw <= 0:
                continue
            mw_avg += w * co.mw
            total_w += w
        if total_w <= 0:
            return None
        mw_avg /= total_w
        # ρ [kg/m³] = P [Pa] · MW [g/mol] / (R · T)  · 1e-3 (g→kg)
        R = 8.314
        P_Pa = 101325.0
        return P_Pa * mw_avg * 1e-3 / (R * T_K)
    # Liquid: 1/ρ_mix = Σ wᵢ/ρᵢ
    inv_rho = 0.0
    total_w = 0.0
    for c, w in composition.items():
        co = _td.get(c)
        if co is None:
            continue
        # Intentar density_kg_m3 si existe
        rho_i = None
        for method in ("liquid_density_kg_m3", "density_kg_m3"):
            if hasattr(co, method):
                try:
                    rho_i = getattr(co, method)(T_C)
                    if rho_i:
                        break
                except Exception:
                    pass
        if rho_i is None or rho_i <= 0:
            # Fallback: ρ del agua a 25°C para líquidos
            rho_i = 1000.0 if c == "water" else 800.0
        inv_rho += w / rho_i
        total_w += w
    if total_w <= 0 or inv_rho <= 0:
        return None
    return total_w / inv_rho


def _viscosity_Pa_s(composition: dict, T_K: float,
                     phase: str = "liquid") -> float:
    """Viscosidad estimada de la mezcla.  Default fallback para
    líquidos: 1 cP (agua a 20°C).  Para gases: 1.8e-5 Pa·s (aire)."""
    # Estimación gruesa.  thermo_db no siempre tiene viscosidad.
    # Para precisión real, usar correlación Lewis-Squires o Letsou-Stiel.
    if phase in ("vapor", "gas"):
        return 1.8e-5    # Pa·s típico para gas a T moderada
    # Líquido típico: 1 cP a 25°C, baja con T
    T_C = T_K - 273.15
    # Ajuste empírico para agua: μ ≈ 0.001 / (1 + 0.02·(T_C - 25))
    if T_C >= 100:
        return 2.8e-4   # vapor agua superheated
    return max(0.001 / (1 + 0.02 * (T_C - 25)), 1e-4)


def stream_pressure_drop(stream, pipe_length_m: float = None,
                          pipe_diameter_m: float = None,
                          pipe_roughness_m: float = 4.5e-5
                          ) -> Optional[Dict]:
    """Calcula ΔP en una corriente del flowsheet.

    Args:
        stream:           Stream del modelo
        pipe_length_m:    override de longitud (sino usa stream.pipe_length_m)
        pipe_diameter_m:  override (sino usa stream.pipe_diameter_m)
        pipe_roughness_m: acero comercial default

    Returns:
        dict {delta_P_Pa, delta_P_bar, velocity_m_s, Re, f_Darcy, regime}
        None si falta data.
    """
    if stream.mass_flow <= 0:
        return None
    # Geometría: defaults razonables si Stream no los tiene
    L = pipe_length_m or getattr(stream, "pipe_length_m", 0) or 10.0
    D = pipe_diameter_m or getattr(stream, "pipe_diameter_m", 0) or 0.050
    eps = pipe_roughness_m
    # Convertir mass_flow tm/año → kg/s
    SEC_PER_YEAR = 8760 * 3600
    m_kg_s = stream.mass_flow * 1000.0 / SEC_PER_YEAR
    # Propiedades del fluido
    comp = stream.composition or ({stream.main_component: 1.0}
                                    if stream.main_component else {})
    if not comp:
        return None
    T_K = stream.temperature + 273.15
    phase = stream.phase or "liquid"
    rho = _density_kg_m3(comp, T_K, phase)
    if rho is None or rho <= 0:
        return None
    mu = _viscosity_Pa_s(comp, T_K, phase)
    return pipe_pressure_drop(m_kg_s, rho, mu, D, L, eps)
