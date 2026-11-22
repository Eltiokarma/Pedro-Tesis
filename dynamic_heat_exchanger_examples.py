"""Cases and independent analytical references for the distributed exchanger.

The reference matrix deliberately does not call the production RHS, validator,
coefficient builder, or numerical integrator. It solves the linear cell balances
by an augmented matrix exponential, piecewise across boundary-input changes.
"""
from __future__ import annotations

import copy
import math

import numpy as np
from scipy.linalg import expm
from scipy.special import gammainc

MSL_URL = "https://github.com/modelica/ModelicaStandardLibrary/blob/v4.1.0/Modelica/Fluid/Examples/HeatExchanger.mo"
MSL_BLOB_SHA = "3b9eba772017e52a407d0da383a3de6574abe9ac"


def example_cases():
    # Only case construction uses the public default; references below are independent.
    from dynamic_heat_exchanger import default_case
    counter = default_case()
    co = copy.deepcopy(counter)
    co.update(case_id="synthetic-co-current-hx", flow_arrangement="co_current")
    co["title"] = "Intercambiador en cocorriente con pared finita"
    transport = copy.deepcopy(counter)
    transport.update(case_id="analytical-residence-delay", cells=16)
    transport["title"] = "Transporte sin intercambio: limite de residencia"
    transport["heat_transfer"].update(hot_h_W_m2_K=0., cold_h_W_m2_K=0.)
    transport["simulation"].update(duration_s=150., output_interval_s=.5, max_step_s=2.)
    adapted = copy.deepcopy(counter)
    adapted.update(case_id="msl-4.1-geometry-adaptation", cells=20)
    adapted["title"] = "Adaptacion de geometria y pared de MSL 4.1.0 BasicHX"
    adapted["geometry"].update(length_m=20., hot_cross_area_m2=4.5e-4,
                               cold_cross_area_m2=4.5e-4, hot_heat_area_m2=1.5, cold_heat_area_m2=1.5)
    adapted["wall"].update(thickness_m=.005, conductivity_W_m_K=100., density_kg_m3=900., cp_J_kg_K=500.)
    adapted["heat_transfer"].update(hot_h_W_m2_K=2000., cold_h_W_m2_K=1000.)
    adapted["simulation"].update(duration_s=180., output_interval_s=2., max_step_s=2.)
    adapted["events"] = [{"time_s": 20., "changes": {"hot_inlet_temperature_K": 340.}},
                         {"time_s": 60., "changes": {"hot_flow_kg_s": 0., "cold_flow_kg_s": 0.}},
                         {"time_s": 90., "changes": {"hot_flow_kg_s": .2, "cold_flow_kg_s": .2}}]
    adapted["provenance"] = {
        "classification": "documented_adaptation", "source": MSL_URL,
        "notes": "Geometria y pared de MSL 4.1.0, blob " + MSL_BLOB_SHA + ". "
                 "Hot corresponde al lado 2; cold al lado 1. Propiedades constantes propias: "
                 "rho=1000 kg/m3 y Cp=4180 J/(kg K). Peliculas constantes 2000/1000 W/(m2 K); "
                 "MSL usa transferencia local dependiente del flujo en el lado 1. Inicializacion "
                 "propia a 300 K, caudales impuestos no negativos, escalones y parada propios. "
                 "Se omiten presion, momento, propiedades variables, inicializacion estacionaria "
                 "y rampa con inversion de MSL. No se ha ejecutado Modelica ni reproducido su ejemplo completo."}
    return {"counter_current.json": counter, "co_current.json": co,
            "transport.json": transport, "msl_geometry_adaptation.json": adapted}


def _reference_system(case, boundary):
    """Independent row-by-row assembly of dT/dt = A T + b (SI)."""
    n, g, w = case["cells"], case["geometry"], case["wall"]
    a = np.zeros((3*n+1, 3*n+1))
    aw = .5 * (g["hot_heat_area_m2"] + g["cold_heat_area_m2"])
    cw = w["cp_J_kg_K"] * w["density_kg_m3"] * aw * w["thickness_m"] / n
    conductances = {}
    for side in ("hot", "cold"):
        h, area = case["heat_transfer"][side + "_h_W_m2_K"], g[side + "_heat_area_m2"]
        conductances[side] = 0. if h == 0 else 1. / (n * (1./(h*area) + w["thickness_m"]/(2*w["conductivity_W_m_K"]*aw)))
    for side, offset in (("hot", 0), ("cold", n)):
        cp = case[side + "_fluid"]["cp_J_kg_K"]
        capacity = case[side + "_fluid"]["density_kg_m3"] * g[side + "_cross_area_m2"] * g["length_m"] * cp / n
        flow_capacity = boundary[side + "_flow_kg_s"] * cp
        film = conductances[side]
        direction = 1 if side == "cold" and case["flow_arrangement"] == "counter_current" else -1
        for cell in range(n):
            row, wr = offset+cell, 2*n+cell
            a[row, row] -= (flow_capacity+film)/capacity
            a[row, wr] += film/capacity
            upstream = cell+direction
            if 0 <= upstream < n:
                a[row, offset+upstream] += flow_capacity/capacity
            else:
                a[row, -1] += flow_capacity * boundary[side + "_inlet_temperature_K"] / capacity
            a[wr, row] += film/cw
            a[wr, wr] -= film/cw
    return a


def matrix_reference(case, times):
    """Temperature profiles at increasing times, including non-grid input events.

    Boundary values are right-continuous; state profiles remain continuous.
    The last augmented coordinate is one, so expm also integrates inlet terms.
    """
    times = np.asarray(times, dtype=float)
    if times.ndim != 1 or np.any(~np.isfinite(times)) or np.any(times < 0) or np.any(np.diff(times) < 0):
        raise ValueError("Nonnegative increasing reference times required.")
    n = case["cells"]
    state = np.r_[*[np.broadcast_to(case["initial"][side + "_temperature_K"], (n,))
                    for side in ("hot", "cold", "wall")], 1.]
    boundary = dict(case["inputs"])
    events = iter(case["events"])
    event = next(events, None)
    matrix, cache = _reference_system(case, boundary), {}
    result, now = [], 0.

    def advance(target):
        nonlocal now, state
        step = target-now
        if step > 0:
            # Exact float key: never round an event interval to reuse a propagator.
            if step not in cache:
                cache[step] = expm(matrix*step)
            state = cache[step] @ state
            now = target

    for time in times:
        while event is not None and event["time_s"] <= time:
            advance(event["time_s"])
            boundary.update(event["changes"])
            matrix, cache = _reference_system(case, boundary), {}
            event = next(events, None)
        advance(float(time))
        result.append(state[:-1].copy())
    return np.asarray(result)


def steady_reference(case):
    """Continuum effectiveness/NTU reference, including the full wall resistance.

    This is independent of the finite-volume matrix. It has no dependence on N,
    cell initialization, or solver settings. Both capacity flows must be positive.
    """
    g, w, boundary = case["geometry"], case["wall"], case["inputs"]
    ch = boundary["hot_flow_kg_s"] * case["hot_fluid"]["cp_J_kg_K"]
    cc = boundary["cold_flow_kg_s"] * case["cold_fluid"]["cp_J_kg_K"]
    if min(ch, cc) <= 0:
        raise ValueError("Positive capacity flows required by the NTU reference.")
    aw = (g["hot_heat_area_m2"]+g["cold_heat_area_m2"])/2
    if min(case["heat_transfer"].values()) == 0:
        ua = 0.
    else:
        resistance = sum(1./(case["heat_transfer"][side + "_h_W_m2_K"]*g[side + "_heat_area_m2"]) for side in ("hot", "cold"))
        ua = 1./(resistance + w["thickness_m"]/(w["conductivity_W_m_K"]*aw))
    minimum, maximum = min(ch, cc), max(ch, cc)
    ratio, ntu = minimum/maximum, ua/minimum
    if case["flow_arrangement"] == "co_current":
        effectiveness = -math.expm1(-ntu*(1+ratio))/(1+ratio)
    elif abs(1-ratio) < 1e-12:
        effectiveness = ntu/(1+ntu)
    else:
        factor = math.exp(-ntu*(1-ratio))
        effectiveness = (1-factor)/(1-ratio*factor)
    heat = effectiveness*minimum*(boundary["hot_inlet_temperature_K"]-boundary["cold_inlet_temperature_K"])
    return {"hot_outlet_temperature_K": boundary["hot_inlet_temperature_K"]-heat/ch,
            "cold_outlet_temperature_K": boundary["cold_inlet_temperature_K"]+heat/cc,
            "heat_W": heat, "effectiveness": effectiveness, "NTU": ntu, "UA_W_K": ua}


def transport_outlet_reference(case, times):
    """Erlang step response of N cells without heat transfer (hot side)."""
    g = case["geometry"]
    residence = case["hot_fluid"]["density_kg_m3"]*g["hot_cross_area_m2"]*g["length_m"]/case["inputs"]["hot_flow_kg_s"]
    initial = float(np.asarray(case["initial"]["hot_temperature_K"]).flat[0])
    return initial + (case["inputs"]["hot_inlet_temperature_K"]-initial)*gammainc(case["cells"], case["cells"]*np.asarray(times)/residence)
