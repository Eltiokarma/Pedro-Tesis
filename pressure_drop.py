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
                        roughness_m:   float = 4.5e-5,
                        K_local:       float = 0.0) -> Optional[Dict]:
    """Calcula la pérdida de carga ΔP en una tubería con flujo
    mass_flow_kg_s, fluido (ρ, μ), geometría (D, L), rugosidad ε
    y pérdidas locales K_local (Σ de Ks de accesorios).

    ΔP_total = ΔP_fricción + ΔP_local
      ΔP_fricción = f · (L/D) · (ρ v²/2)         (Darcy-Weisbach)
      ΔP_local    = K_local · (ρ v²/2)           (pérdidas menores)

    Returns dict {ΔP_Pa, ΔP_bar, ΔP_fric_Pa, ΔP_local_Pa,
                    velocity_m_s, Re, f_Darcy, regime}.
    """
    if (mass_flow_kg_s <= 0 or rho_kg_m3 <= 0 or mu_Pa_s <= 0
            or diameter_m <= 0 or length_m <= 0):
        return None
    area_m2 = math.pi * diameter_m ** 2 / 4.0
    volumetric_flow_m3_s = mass_flow_kg_s / rho_kg_m3
    velocity = volumetric_flow_m3_s / area_m2
    Re = reynolds(rho_kg_m3, velocity, diameter_m, mu_Pa_s)
    eps_over_D = roughness_m / diameter_m
    f = colebrook_white(Re, eps_over_D)
    dyn_pressure = rho_kg_m3 * velocity ** 2 / 2.0
    dp_fric = f * (length_m / diameter_m) * dyn_pressure
    dp_local = K_local * dyn_pressure if K_local > 0 else 0.0
    dp_total = dp_fric + dp_local
    return dict(
        delta_P_Pa=dp_total,
        delta_P_bar=dp_total / 1e5,
        delta_P_fric_Pa=dp_fric,
        delta_P_local_Pa=dp_local,
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
                    phase: str = "liquid",
                    P_Pa: float = 101325.0) -> Optional[float]:
    """Densidad media ponderada por mass fraction desde thermo_db.

    Para mezclas líquidas: ρ_mix ≈ 1 / Σ(wᵢ / ρᵢ)  (volumes additive,
    aprox razonable para mezclas similares).
    Para gases: ρ ≈ P·MW / (R·T) — usa el P_Pa del caller (default
    1 atm si no se pasa).  Hallazgo 4-B: antes P_Pa estaba hardcodeado
    en 1 atm → densidad de gas a 25 bar mal por 25× → ΔP mal por 25×.
    """
    try:
        import thermo_db as _td
    except ImportError:
        return None
    if not composition:
        return None
    T_C = T_K - 273.15
    if phase in ("vapor", "gas"):
        # Gas ideal con MW promedio y P del caller
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
        P_use = P_Pa if P_Pa > 0 else 101325.0
        return P_use * mw_avg * 1e-3 / (R * T_K)
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
    # Pasamos P real del stream (Hallazgo 4-B): la densidad de gas
    # depende de P; antes era hardcoded en 1 atm y daba 25× error a
    # 25 bar.  Para líquido P no afecta (incompresible).
    P_stream_Pa = (getattr(stream, "pressure_bar", 1.013) or 1.013) * 1e5
    rho = _density_kg_m3(comp, T_K, phase, P_Pa=P_stream_Pa)
    if rho is None or rho <= 0:
        return None
    mu = _viscosity_Pa_s(comp, T_K, phase)
    K_local = getattr(stream, "pipe_K_local", 0.0) or 0.0
    return pipe_pressure_drop(m_kg_s, rho, mu, D, L, eps, K_local)


# ============================================================
# Referencia de Ks típicos (para que el user los sume manualmente)
# ============================================================

K_TYPICAL = {
    # Codos
    "codo 90° estándar":         0.75,
    "codo 90° radio largo":      0.45,
    "codo 45°":                  0.35,
    # Tees
    "tee paso recto":            0.60,
    "tee paso lateral":          1.80,
    # Válvulas (totalmente abiertas)
    "válvula gate":              0.17,
    "válvula globo":            10.00,
    "válvula angular":           5.00,
    "válvula check (swing)":     2.50,
    "válvula bola":              0.05,
    "válvula mariposa":          0.45,
    # Reducciones / expansiones
    "reducción gradual":         0.04,
    "reducción brusca":          0.50,
    "expansión gradual":         0.20,
    "expansión brusca":          1.00,
    # Entradas / salidas
    "entrada brusca a tanque":   1.00,
    "entrada chamfered":         0.25,
    "salida a tanque":           1.00,
}


def sum_K_from_accesories(accesories: dict) -> float:
    """Helper para que el user sume K_local desde un dict de
    accesorios:  {'codo 90° estándar': 3, 'válvula gate': 2}
    → K_total = 3·0.75 + 2·0.17 = 2.59
    """
    total = 0.0
    for name, count in accesories.items():
        K = K_TYPICAL.get(name.lower(), 0.0)
        total += K * count
    return total
