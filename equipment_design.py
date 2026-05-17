"""
EQUIPMENT_DESIGN — Dimensionamiento de bombas y compresores.

Calcula potencia hidráulica/isentrópica + eléctrica, head, NPSH,
T de descarga y otros parámetros de diseño.  Usa thermo_db para
propiedades del fluido.

API:
    pump_sizing(m_kg_s, dp_bar, rho, eta_hyd=0.75, eta_motor=0.95,
                 T_K=298, p_vap_bar=0.03)
        → dict {W_hyd_kW, W_shaft_kW, W_elec_kW, head_m,
                NPSHa_m, NPSHr_m_est, Q_m3_h, eta_total}

    compressor_sizing(m_kg_s, P_in_bar, P_out_bar, T_in_K,
                       mw_avg, k=1.4, eta_isen=0.75, eta_mech=0.95)
        → dict {W_isen_kW, W_act_kW, T_out_K, ratio, n_stages_est,
                Q_m3_h_actual}

Casos:
    · Centrifuga single-stage: ratio < 4, T_out moderada
    · Multi-stage: ratio > 4 → recomendar etapas con intercoolers
    · Reciprocating: ratio alto pero caudal bajo (no implementado)

VALIDACIÓN:  vs casos clásicos Perry, Walas.
"""

import math
from typing import Dict, Optional


# ============================================================
# BOMBAS
# ============================================================

def pump_sizing(m_kg_s:     float,
                dp_bar:     float,
                rho_kg_m3:  float,
                eta_hyd:    float = 0.75,
                eta_motor:  float = 0.95,
                T_K:        float = 298.15,
                p_vap_bar:  float = 0.03,
                p_in_bar:   float = 1.013,
                z_elev_m:   float = 0.0,
                N_rpm:      float = 3550.0,
                N_ss:       float = 9000.0) -> Optional[Dict]:
    """Dimensiona una bomba centrífuga.

    NPSHr — Velocidad específica de succión (Perry 8ª §10.4,
    Walas §10.3-3, Karassik Pump Handbook 4ª §2.3):

        N_ss = N · sqrt(Q) / NPSHr^(3/4)        (US customary)
        ⇒  NPSHr [ft] = ( N · sqrt(Q[gpm]) / N_ss )^(4/3)
        ⇒  NPSHr [m]  = NPSHr[ft] · 0.3048

    Donde:
        N      = velocidad de la bomba (rpm).  Default 3550 = motor
                 2-polos 60 Hz, estándar industrial centrífuga.
        N_ss   = velocidad específica de succión.  Valor de diseño
                 conservador 9000 (Hydraulic Institute API 610);
                 valores agresivos llegan a 11000-14000 pero
                 reducen vida útil del impeller.

    Args:
        m_kg_s:    caudal másico
        dp_bar:    ΔP requerida (descarga - succión)
        rho_kg_m3: densidad del fluido
        eta_hyd:   eficiencia hidráulica (default 0.75 centrífuga)
        eta_motor: eficiencia del motor eléctrico (default 0.95)
        T_K:       temperatura del fluido
        p_vap_bar: presión de vapor a T_K (para NPSH)
        p_in_bar:  presión de succión disponible
        z_elev_m:  altura de succión + (negativo si bomba está arriba)
        N_rpm:     velocidad de rotación (default 3550)
        N_ss:      suction specific speed (default 9000, conservador)

    Returns dict {
        W_hyd_kW:    potencia hidráulica = m·ΔP/ρ
        W_shaft_kW:  = W_hyd / η_hyd
        W_elec_kW:   = W_shaft / η_motor
        head_m:      = ΔP_Pa / (ρ·g)
        Q_m3_h:      caudal volumétrico
        NPSHa_m:     NPSH disponible = (P_in - P_vap)/(ρg) + z_elev
        NPSHr_m_est: NPSHr estimado por suction specific speed
                     (Perry/Walas/Karassik).  None si Q≈0.
        eta_total:   η_hyd · η_motor
        cavitation_margin_m: NPSHa - NPSHr (None si NPSHr es None)
    }
    """
    if m_kg_s <= 0 or rho_kg_m3 <= 0 or dp_bar <= 0:
        return None
    g = 9.81
    dp_Pa = dp_bar * 1e5
    Q_m3_s = m_kg_s / rho_kg_m3
    Q_m3_h = Q_m3_s * 3600
    # Potencia hidráulica
    W_hyd = m_kg_s * dp_Pa / rho_kg_m3 / 1000.0    # kW
    eta_h = max(min(eta_hyd, 0.95), 0.30)
    eta_m = max(min(eta_motor, 0.99), 0.50)
    W_shaft = W_hyd / eta_h
    W_elec  = W_shaft / eta_m
    # Head
    head_m = dp_Pa / (rho_kg_m3 * g)
    # NPSH disponible: NPSHa = (P_in - P_vap)/(ρg) + Δz
    npsha = (p_in_bar - p_vap_bar) * 1e5 / (rho_kg_m3 * g) + z_elev_m
    # NPSHr por suction specific speed (Perry 8ª §10.4):
    #   NPSHr[ft] = ( N · sqrt(Q[gpm]) / N_ss )^(4/3)
    # Conversiones: 1 m³/h = 4.40287 gpm ; 1 ft = 0.3048 m
    Q_gpm = Q_m3_h * 4.40287
    if Q_gpm > 1e-6 and N_ss > 0 and N_rpm > 0:
        npshr_ft = (N_rpm * math.sqrt(Q_gpm) / N_ss) ** (4.0 / 3.0)
        npshr_est = npshr_ft * 0.3048
        cav_margin = npsha - npshr_est
    else:
        npshr_est = None
        cav_margin = None
    return dict(
        W_hyd_kW=W_hyd,
        W_shaft_kW=W_shaft,
        W_elec_kW=W_elec,
        head_m=head_m,
        Q_m3_h=Q_m3_h,
        NPSHa_m=npsha,
        NPSHr_m_est=npshr_est,
        cavitation_margin_m=cav_margin,
        eta_total=eta_h * eta_m,
    )


# ============================================================
# COMPRESORES (isentrópico)
# ============================================================

def compressor_sizing(m_kg_s:    float,
                       P_in_bar:  float,
                       P_out_bar: float,
                       T_in_K:    float,
                       mw_avg:    float,
                       k:         float = 1.4,
                       eta_isen:  float = 0.75,
                       eta_mech:  float = 0.95,
                       z:         float = 1.0) -> Optional[Dict]:
    """Dimensiona un compresor centrífugo/axial isentrópico.

    Trabajo isentrópico (ideal, gas ideal — Turton 5ª §6.5):
        W_s = m·z·R·T_in/MW · k/(k-1) · [(P2/P1)^((k-1)/k) - 1]

    Trabajo real:
        W_act = W_s / η_isen

    Temperatura de descarga (forma correcta, NO dividir T entera
    por η).  Derivación: ΔT_real = ΔT_isen / η_isen, donde
    ΔT_isen = T_in · ((P2/P1)^((k-1)/k) − 1).  Por lo tanto:

        T_out = T_in · [ 1 + ((P2/P1)^((k-1)/k) − 1) / η_isen ]

    Test de referencia (aire k=1.4, T_in=300 K, P1→P2 = 1→5 bar,
    η_isen=0.75):
        ΔT_isen = 300·(5^0.2857 − 1) = 175.13 K
        T_out   = 300 + 175.13/0.75 = 533.50 K   (NO 633 K como
                                                    daría la división
                                                    incorrecta de T)

    Etapas recomendadas: ratio_per_stage ≤ 4 industrial.  Si
    ratio total > 4, recomendar multi-stage con intercoolers.

    Args:
        m_kg_s:    caudal másico
        P_in_bar:  presión succión
        P_out_bar: presión descarga
        T_in_K:    T succión
        mw_avg:    MW promedio de la mezcla (g/mol)
        k:         Cp/Cv (default 1.4 = gases biatómicos diluidos)
        eta_isen:  eficiencia isentrópica (0.7-0.8 centrífugo típico)
        eta_mech:  eficiencia mecánica (0.95 default)
        z:         factor de compresibilidad (1 = gas ideal)

    Returns dict {
        ratio:           P_out/P_in
        n_stages_rec:    etapas recomendadas (ratio_per_stage ≤ 4)
        W_isen_kW:       potencia isentrópica
        W_act_kW:        = W_isen / (η_isen · η_mech)
        T_out_K:         temperatura de descarga
        T_out_C:         idem en °C
        Q_in_m3_h:       caudal de succión (gas ideal)
        head_kJ_kg:      head específico
    }
    """
    if (m_kg_s <= 0 or P_in_bar <= 0 or P_out_bar <= P_in_bar
            or T_in_K <= 0 or mw_avg <= 0):
        return None
    R = 8.314  # J/(mol·K)
    ratio = P_out_bar / P_in_bar
    k_eff = max(min(k, 1.7), 1.05)
    # Trabajo isentrópico (J/kg)
    exponent = (k_eff - 1.0) / k_eff
    factor = (ratio ** exponent) - 1.0
    R_specific = R / (mw_avg * 1e-3)   # J/(kg·K)
    w_isen_J_kg = z * R_specific * T_in_K * (k_eff / (k_eff - 1.0)) * factor
    W_isen_kW = m_kg_s * w_isen_J_kg / 1000.0
    eta_i = max(min(eta_isen, 0.95), 0.30)
    eta_m = max(min(eta_mech, 0.99), 0.50)
    W_act_kW = W_isen_kW / (eta_i * eta_m)
    # T_out isentrópica: T_out_s = T_in · ratio^((k-1)/k)
    T_out_s = T_in_K * (ratio ** exponent)
    # T_out real (corrigiendo por ineficiencia):
    # h_out = h_in + (h_out_s - h_in) / η_isen → ΔT_act = ΔT_isen / η_isen
    delta_T = (T_out_s - T_in_K) / eta_i
    T_out = T_in_K + delta_T
    # Q de succión: V = n·R·T/P, n_mol/s = m_kg_s / MW_kg
    Q_m3_s = m_kg_s / (mw_avg * 1e-3) * R * T_in_K / (P_in_bar * 1e5)
    Q_m3_h = Q_m3_s * 3600
    # Etapas: si ratio > 4, multi-stage con ratio_per_stage = ratio^(1/n)
    n_stages_rec = max(1, math.ceil(math.log(ratio) / math.log(4.0)))
    return dict(
        ratio=ratio,
        n_stages_rec=n_stages_rec,
        W_isen_kW=W_isen_kW,
        W_act_kW=W_act_kW,
        T_out_K=T_out,
        T_out_C=T_out - 273.15,
        Q_in_m3_h=Q_m3_h,
        head_kJ_kg=w_isen_J_kg / 1000.0,
        eta_total=eta_i * eta_m,
    )


# ============================================================
# Wrappers usando Block + Stream del flowsheet
# ============================================================

def design_pump_for_block(block, fs) -> Optional[Dict]:
    """Dimensiona una bomba a partir del bloque del flowsheet.
    Toma feed (input), descarga (output), calcula ΔP necesario.
    """
    try:
        import thermo_db as _td
        import pressure_drop as _pd
    except ImportError:
        return None
    ins  = [s for s in fs.streams.values() if s.dst == block.id]
    outs = [s for s in fs.streams.values() if s.src == block.id]
    if not ins or not outs:
        return None
    feed = ins[0]
    out  = outs[0]
    if feed.mass_flow <= 0 or not (feed.composition or feed.main_component):
        return None
    # ΔP: del block o de la diferencia P_out - P_in
    dp_bar = block.delta_p_bar
    if abs(dp_bar) < 1e-6:
        dp_bar = max(out.pressure_bar - feed.pressure_bar, 0.1)
    if dp_bar <= 0:
        return None
    # Propiedades
    T_K = feed.temperature + 273.15
    comp = feed.composition or {feed.main_component: 1.0}
    rho = _pd._density_kg_m3(comp, T_K, feed.phase or "liquid")
    if rho is None or rho <= 0:
        return None
    # Presión de vapor estimada del componente principal
    p_vap_bar = 0.03   # default conservador
    main = max(comp.items(), key=lambda kv: kv[1])[0] if comp else None
    if main:
        co = _td.get(main)
        if co is not None:
            try:
                pv_kpa = co.vapor_pressure_kPa(feed.temperature)
                if pv_kpa: p_vap_bar = pv_kpa / 100.0
            except Exception:
                pass
    from flowsheet_model import SEC_PER_YEAR, TM_TO_KG  # única fuente §6.3
    m_kg_s = feed.mass_flow * TM_TO_KG / SEC_PER_YEAR
    return pump_sizing(
        m_kg_s=m_kg_s, dp_bar=dp_bar, rho_kg_m3=rho,
        eta_hyd=block.efficiency, T_K=T_K, p_vap_bar=p_vap_bar,
        p_in_bar=feed.pressure_bar)


def design_compressor_for_block(block, fs) -> Optional[Dict]:
    """Dimensiona un compresor a partir del bloque del flowsheet."""
    try:
        import thermo_db as _td
    except ImportError:
        return None
    ins  = [s for s in fs.streams.values() if s.dst == block.id]
    outs = [s for s in fs.streams.values() if s.src == block.id]
    if not ins or not outs:
        return None
    feed = ins[0]
    out  = outs[0]
    if feed.mass_flow <= 0:
        return None
    comp = feed.composition or {feed.main_component: 1.0}
    if not comp:
        return None
    # MW promedio
    mw_avg = 0.0
    total = 0.0
    for c, w in comp.items():
        co = _td.get(c)
        if co is None or co.mw <= 0:
            continue
        mw_avg += w * co.mw
        total += w
    if total <= 0:
        return None
    mw_avg /= total
    # P in/out
    P_in = feed.pressure_bar if feed.pressure_bar > 0 else 1.013
    if block.delta_p_bar > 0:
        P_out = P_in + block.delta_p_bar
    elif out.pressure_bar > P_in:
        P_out = out.pressure_bar
    else:
        return None
    # k típico: para mezcla heterogénea, usar 1.3-1.4
    # Aprox: si dominan diatomicos N2/O2/H2 → 1.4
    #        si CO2/SO2/poliatómicos → 1.28
    k = 1.4
    if comp.get("co2", 0) > 0.5 or comp.get("water", 0) > 0.3:
        k = 1.30
    from flowsheet_model import SEC_PER_YEAR, TM_TO_KG  # única fuente §6.3
    m_kg_s = feed.mass_flow * TM_TO_KG / SEC_PER_YEAR
    return compressor_sizing(
        m_kg_s=m_kg_s, P_in_bar=P_in, P_out_bar=P_out,
        T_in_K=feed.temperature + 273.15, mw_avg=mw_avg, k=k,
        eta_isen=block.efficiency)
