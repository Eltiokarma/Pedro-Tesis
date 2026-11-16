"""Screening steam turbine with condensation on the shared caloric basis.

At saturation, s_fg = h_fg / T and h = h_f + x h_fg. Sensible entropy
changes integrate Cp/T. The saturation curve is the existing water Antoine
fit; enthalpies are the existing stream model, NOT IAPWS steam tables.
Pressure departures, near-critical accuracy and liquid turbine work are not
represented. This avoids silently extrapolating dry ideal steam below Tsat.

Thermodynamic conventions: NIST steam tables manual,
https://www.nist.gov/system/files/documents/srd/steam-manual-222.pdf
"""
import copy
import math

from scipy.integrate import quad
from scipy.optimize import brentq

import thermo_db
from flowsheet_model import SEC_PER_YEAR, TM_TO_KG
from stream_enthalpy import (_resolve_cp, specific_enthalpy_kJ_kg,
                             stream_enthalpy_kW, temperature_for_enthalpy)


def saturation_temperature_C(pressure_bar):
    """Invert the shared subcritical water saturation curve, or raise."""
    water = thermo_db.get("water")
    if not math.isfinite(pressure_bar) or not 0 < pressure_bar < water.pc_bar:
        raise ValueError("steam pressure must be positive and subcritical")
    return brentq(lambda t: thermo_db.vapor_pressure_bar("water", t) - pressure_bar,
                  .01, water.tc_c - .01, xtol=1e-9)


def wet_steam_expander(feed, pressure_out_bar, efficiency=.75,
                       mechanical_efficiency=.95):
    """Return gas_machine_for_stream-compatible design, or None if unsupported.

    A pure-water vapor inlet must be at or above saturation; a wet inlet
    must be at saturation and carry a mass vapor fraction in [0,1]. No stream
    is mutated. Negative W_act is exported shaft power; mechanical loss is
    positive heat rejected, so Hout-Hin = W_act-Q_mechanical_loss.
    """
    try:
        pin, pout = float(feed.pressure_bar), float(pressure_out_bar)
        tin = float(feed.temperature)
        eta, eta_m = float(efficiency), float(mechanical_efficiency)
        if (not all(math.isfinite(v) for v in (pin, pout, tin, eta, eta_m, feed.mass_flow))
                or not 0 < pout < pin or not 0 < eta <= 1
                or not 0 < eta_m <= 1 or feed.mass_flow <= 0):
            return None
        composition = feed.composition or {feed.main_component: 1.0}
        if (not composition or sum(composition.values()) <= 0
                or any(not math.isfinite(w) or w < 0 or
                       (w > 0 and thermo_db.get(name) is not thermo_db.get("water"))
                       for name, w in composition.items())):
            return None
        probe = copy.copy(feed)
        probe.composition, probe.main_component = {"water": 1.0}, "water"
        probe.mass_flow = SEC_PER_YEAR / TM_TO_KG  # one kg/s

        def cp_entropy(lo, hi, phase):
            probe.phase = phase
            def integrand(tk):
                cp = _resolve_cp(probe, tk - 273.15)
                if cp is None or not math.isfinite(cp) or cp <= 0:
                    raise ValueError("water Cp unavailable")
                return cp / tk
            return quad(integrand, lo + 273.15, hi + 273.15,
                        epsabs=1e-9, epsrel=1e-9)[0]

        def saturation(pressure):
            t = saturation_temperature_C(pressure)
            hf = specific_enthalpy_kJ_kg({"water": 1.0}, t, "liquid")
            hg = specific_enthalpy_kJ_kg({"water": 1.0}, t, "vapor")
            if hf is None or hg is None or hg <= hf:
                raise ValueError("water saturation calorics unavailable")
            sf = cp_entropy(25., t, "liquid")
            return t, hf, hg, sf, sf + (hg - hf) / (t + 273.15)

        t1, hf1, hg1, sf1, sg1 = saturation(pin)
        t2, hf2, hg2, sf2, sg2 = saturation(pout)
        phase = (feed.phase or "").lower()
        if phase in ("vapor", "gas"):
            if tin < t1 - .01:
                return None  # a mislabeled subcooled vapor is not steam
            x_in = 1.0
            sin = sg1 + cp_entropy(t1, tin, "vapor")
        elif phase in ("two_phase", "2ph", "mixed"):
            x_in = float(feed.vapor_fraction)
            if not math.isfinite(x_in) or not 0 <= x_in <= 1 or abs(tin - t1) > .01:
                return None
            sin = sf1 + x_in * (sg1 - sf1)
        else:
            return None
        hin = stream_enthalpy_kW(feed) * SEC_PER_YEAR / (feed.mass_flow * TM_TO_KG)
        if sin < sf2:
            return None  # compressed-liquid work needs a pressure-aware model
        if sin <= sg2:
            xs = (sin - sf2) / (sg2 - sf2)
            ts, hs = t2, hf2 + xs * (hg2 - hf2)
        else:
            def entropy_residual(t):
                return sg2 + cp_entropy(t2, t, "vapor") - sin
            ts = brentq(entropy_residual, t2, max(tin, t2), xtol=1e-9)
            hs = specific_enthalpy_kJ_kg({"water": 1.0}, ts, "vapor")
            xs = 1.0
        if hs is None or hs >= hin:
            return None
        dh_s = hs - hin
        hout = hin + eta * dh_s
        if hout < hf2:
            return None
        if hout <= hg2:
            quality = (hout - hf2) / (hg2 - hf2)
            tout, phase_out = t2, "two_phase"
            sout = sf2 + quality * (sg2 - sf2)
        else:
            probe.phase, probe.temperature = "vapor", max(t2, tin)
            probe.vapor_fraction = 1.0
            tout = temperature_for_enthalpy(probe, hout, lo_C=t2)
            if tout is None:
                return None
            quality, phase_out = 1.0, "vapor"
            sout = sg2 + cp_entropy(t2, tout, "vapor")
        mass = feed.mass_flow * TM_TO_KG / SEC_PER_YEAR
        w_gas = mass * (hout - hin)
        w_actual = w_gas * eta_m
        water = thermo_db.get("water")
        # Ideal vapor plus incompressible liquid, for screening flow sizing.
        v_in = x_in * 8314 / water.mw * (tin + 273.15) / (pin * 1e5) + (1-x_in) / 1000
        return {
            "ratio": pout / pin, "ratio_per_stage": pout / pin,
            "n_stages": 1, "n_stages_rec": 1,
            "W_isen_kW": mass * dh_s, "W_gas_kW": w_gas,
            "W_act_kW": w_actual, "Q_intercool_kW": 0.0,
            "Q_mechanical_loss_kW": w_actual - w_gas,
            "T_out_K": tout + 273.15, "T_out_C": tout,
            "T_isen_K": ts + 273.15, "T_isen_C": ts,
            "Q_in_m3_h": mass * v_in * 3600,
            "head_kJ_kg": dh_s, "eta_total": eta * eta_m,
            "phase": phase_out, "vapor_fraction": quality,
            "isentropic_vapor_fraction": xs,
            "s_in_kJ_kgK": sin, "s_out_kJ_kgK": sout,
            "model": "approximate wet steam; Antoine saturation and shared Cp/enthalpy; not IAPWS",
        }
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return None
