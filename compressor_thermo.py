"""Ideal-gas compressor/expander calculation with the stream caloric model.

The reversible state solves integral(Cp(T)/T dT) = R_specific ln(P2/P1).
Isentropic efficiency acts on enthalpy differences, not temperature ratios.
This is an ideal-gas approximation; it is not a real-gas high-pressure EOS.
Internal interstage cooling and motor/mechanical losses are explicit duties.
"""
import copy
import math

from scipy.integrate import quad
from scipy.optimize import brentq

from flowsheet_model import SEC_PER_YEAR, TM_TO_KG
from stream_enthalpy import _resolve_cp, stream_enthalpy_kW, temperature_for_enthalpy


def mixture_molecular_weight(composition):
    """Return kg/kmol from mass fractions: 1/M = sum(w_i/M_i)."""
    import thermo_db
    import components
    moles, total = 0.0, 0.0
    for name, fraction in composition.items():
        if fraction <= 0:
            continue
        component = thermo_db.get(name) or components.get(name)
        mw = getattr(component, "mw", 0.0)
        if not mw or not math.isfinite(mw) or mw <= 0:
            return None
        moles += fraction / mw
        total += fraction
    return total / moles if moles > 0 else None


def gas_machine_for_stream(feed, pressure_out_bar, efficiency=0.75,
                           mechanical_efficiency=0.95, max_ratio_per_stage=4.0):
    """Return thermal/electrical design without mutating the feed.

Positive W_act is electricity consumed, negative is electricity generated.
Q_intercool and Q_mechanical_loss are positive heat rejected. Therefore
Hout-Hin = W_act-Q_intercool-Q_mechanical_loss for the complete machine.
"""
    pin, pout = float(feed.pressure_bar), float(pressure_out_bar)
    tin = float(feed.temperature) + 273.15
    eta, eta_m = float(efficiency), float(mechanical_efficiency)
    if (not all(math.isfinite(x) for x in (pin, pout, tin, eta, eta_m))
            or min(pin, pout, tin) <= 0 or not 0 < eta <= 1
            or not 0 < eta_m <= 1 or feed.mass_flow <= 0):
        return None
    composition = feed.composition or {feed.main_component: 1.0}
    mw = mixture_molecular_weight(composition)
    if mw is None:
        return None
    if pout < pin:
        import thermo_db
        if all((thermo_db.get(name) is not None
                and thermo_db.get(name).name == "water")
               for name, fraction in composition.items() if fraction > 0):
            from steam_expander import wet_steam_expander
            return wet_steam_expander(feed, pout, eta, eta_m)
    probe = copy.copy(feed)
    probe.phase = "gas"
    probe.vapor_fraction = 1.0
    probe.mass_flow = SEC_PER_YEAR / TM_TO_KG  # one kg/s: H[kW] = h[kJ/kg]
    hin = stream_enthalpy_kW(probe)
    if hin is None:
        return None
    ratio = pout / pin
    compressing = ratio >= 1
    stages = (max(1, math.ceil(math.log(ratio) /
                 math.log(max(1.2, max_ratio_per_stage)))) if ratio > 1 else 1)
    stage_ratio = ratio ** (1.0 / stages)
    r_specific = 8.314 / mw

    def entropy_residual(tout):
        def cp_over_t(t):
            cp = _resolve_cp(probe, t - 273.15)
            if cp is None or not math.isfinite(cp) or cp <= r_specific:
                raise ValueError("gas Cp unavailable or Cp <= R")
            return cp / t
        return quad(cp_over_t, tin, tout, epsabs=1e-9, epsrel=1e-9)[0] - \
            r_specific * math.log(stage_ratio)

    try:
        if ratio == 1:
            ts = tin
        elif compressing:
            upper = min(max(tin * 1.5, tin + 50), 2273.15)
            while entropy_residual(upper) < 0 and upper < 2273.15:
                upper = min(2273.15, upper * 1.5)
            ts = brentq(entropy_residual, tin, upper, xtol=1e-9)
        else:
            lower = max(1.0, tin / 2)
            while entropy_residual(lower) > 0 and lower > 1.0:
                lower = max(1.0, lower / 2)
            ts = brentq(entropy_residual, lower, tin, xtol=1e-9)
    except (ValueError, OverflowError):
        return None
    probe.temperature = ts - 273.15
    hs = stream_enthalpy_kW(probe)
    if hs is None:
        return None
    dh_s = hs - hin
    dh_stage = dh_s / eta if compressing else eta * dh_s
    tout_c = temperature_for_enthalpy(probe, hin + dh_stage)
    if tout_c is None:
        return None
    mass = feed.mass_flow * TM_TO_KG / SEC_PER_YEAR
    w_gas = mass * dh_stage * stages
    w_actual = w_gas / eta_m if compressing else w_gas * eta_m
    q_mech = w_actual - w_gas
    q_ic = mass * dh_stage * (stages - 1)
    return {
        "ratio": ratio, "ratio_per_stage": stage_ratio,
        "n_stages": stages, "n_stages_rec": stages,
        "W_isen_kW": mass * dh_s * stages, "W_gas_kW": w_gas,
        "W_act_kW": w_actual, "Q_intercool_kW": q_ic,
        "Q_mechanical_loss_kW": q_mech,
        "T_out_K": tout_c + 273.15, "T_out_C": tout_c,
        "T_isen_K": ts, "T_isen_C": ts - 273.15,
        "Q_in_m3_h": mass * 8314 / mw * tin / (pin * 1e5) * 3600,
        "head_kJ_kg": dh_s * stages, "eta_total": eta * eta_m,
        "phase": "gas", "vapor_fraction": 1.0,
        "model": "ideal gas; Cp(T) and enthalpy from stream property model",
    }
