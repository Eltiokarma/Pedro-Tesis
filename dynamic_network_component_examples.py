"""Connected exchanger cases and an independent closed-circuit matrix oracle."""
from __future__ import annotations

import copy

import numpy as np
from scipy.linalg import expm

from dynamic_heat_exchanger import default_case
from dynamic_network_components import component_from_case
from dynamic_network_examples import _base, _node, _edge
from dynamic_heat_exchanger_examples import _reference_system


def example_cases():
    c = _base("coupled-recirculation", "Dos depositos conectados por un intercambiador distribuido")
    c.update(schema_version="dynamic-network/v2", ambient_temperature_K=300.)
    c["fluid"]["density_kg_m3"] = 1000.
    c["nodes"] = [_node("HotTank", 20., 350., 1.), _node("ColdTank", 30., 290., 0.)]
    hx = default_case()
    hx.update(cells=6)
    hx["initial"].update(hot_temperature_K=350., cold_temperature_K=290., wall_temperature_K=320.)
    c["heat_exchangers"] = [component_from_case("HX1", hx, hot_tracer=1.)]
    c["edges"] = [_edge("hot_supply", "HotTank", "HX1.hot_in", .2),
                  _edge("hot_return", "HX1.hot_out", "HotTank", .2),
                  _edge("cold_supply", "ColdTank", "HX1.cold_in", .2),
                  _edge("cold_return", "HX1.cold_out", "ColdTank", .2)]
    c["simulation"].update(duration_s=300., output_interval_s=5., max_step_s=5., max_temperature_K=370.)
    c["events"] = [{"time_s": t, "changes": {"edges": {e["id"]: {"mass_flow_kg_s": flow} for e in c["edges"]}}}
                   for t, flow in ((40., 0.), (70., .2))]
    c["provenance"].update(source="Balances propios; exponencial matricial independiente del circuito cerrado.",
                            notes="Caso sintetico de verificacion de acoplamiento, no una instalacion industrial.")
    feed = copy.deepcopy(c)
    feed.update(case_id="coupled-feed", title="Intercambiador alimentado y dos depositos de descarga")
    feed["nodes"] = [_node("HotTank", 5., 300., 0.), _node("ColdTank", 7., 300., 0.)]
    hx = default_case()
    hx["cells"] = 4
    feed["heat_exchangers"] = [component_from_case("HX1", hx)]
    feed["sources"] = [{"id": "HotFeed", "temperature_K": 360., "tracer_mass_fraction": 1.},
                       {"id": "ColdFeed", "temperature_K": 300., "tracer_mass_fraction": 0.}]
    feed["edges"][0]["source"] = "HotFeed"
    feed["edges"][2]["source"] = "ColdFeed"
    feed["edges"].extend([_edge("hot_discharge", "HotTank", None, .2), _edge("cold_discharge", "ColdTank", None, .2)])
    feed["events"] = []
    feed["provenance"].update(source="Intercambiador de fronteras constantes y depositos de descarga; balances propios.")
    return {"coupled_recirculation.json": c, "coupled_feed.json": feed}


def recirculation_reference(case, times):
    """Case-specific analytical coupling: 2 tank temperatures plus 3N cells.

    Uses the independently assembled exchanger matrix, replaces its fixed inlet
    terms with tank state columns, and writes both tank balances explicitly.
    No production network graph, RHS or coefficient builder is consulted.
    """
    unit = case["heat_exchangers"][0]
    n = unit["cells"]
    state = np.r_[[node["initial_temperature_K"] for node in case["nodes"]],
                  *[np.broadcast_to(unit["initial"][side+"_temperature_K"], (n,)) for side in ("hot", "cold", "wall")]]
    flow = {edge["id"]: edge["mass_flow_kg_s"] for edge in case["edges"]}
    changes = iter(case["events"])
    event, now, cache = next(changes, None), 0., {}

    def matrix():
        fh, fc = flow["hot_supply"], flow["cold_supply"]
        inputs = {"hot_flow_kg_s": fh, "cold_flow_kg_s": fc,
                  "hot_inlet_temperature_K": 0., "cold_inlet_temperature_K": 0.}
        sub = _reference_system(unit, inputs)[:-1, :-1]
        a = np.zeros((2+3*n, 2+3*n))
        a[2:, 2:] = sub
        hot_cell_mass = unit["geometry"]["length_m"]*unit["geometry"]["hot_cross_area_m2"]*unit["hot_fluid"]["density_kg_m3"]/n
        cold_cell_mass = unit["geometry"]["length_m"]*unit["geometry"]["cold_cross_area_m2"]*unit["cold_fluid"]["density_kg_m3"]/n
        counter = unit["flow_arrangement"] == "counter_current"
        a[2, 0] = fh/hot_cell_mass
        a[2+n+(n-1 if counter else 0), 1] = fc/cold_cell_mass
        a[0, 0], a[0, 2+n-1] = -fh/case["nodes"][0]["initial_mass_kg"], fh/case["nodes"][0]["initial_mass_kg"]
        a[1, 1], a[1, 2+n+(0 if counter else n-1)] = -fc/case["nodes"][1]["initial_mass_kg"], fc/case["nodes"][1]["initial_mass_kg"]
        return a

    a, results = matrix(), []
    def advance(target):
        nonlocal state, now
        dt = target-now
        if dt > 0:
            if dt not in cache: cache[dt] = expm(a*dt)
            state, now = cache[dt]@state, target
    for time in times:
        while event is not None and event["time_s"] <= time:
            advance(event["time_s"])
            for eid, values in event["changes"].get("edges", {}).items(): flow[eid] = values["mass_flow_kg_s"]
            a, cache = matrix(), {}
            event = next(changes, None)
        advance(float(time))
        results.append(state.copy())
    return np.asarray(results)
