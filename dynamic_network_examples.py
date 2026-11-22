"""Reproducible network cases and independent, problem-specific closed forms.

References here do not import the production integrator, RHS or graph assembly.
All generated trajectories are theoretical/synthetic, never plant measurements.
"""
from __future__ import annotations

import math

import numpy as np

ENERGYPLUS_URL = "https://github.com/NatLabRockies/EnergyPlus/blob/v24.2.0/tst/EnergyPlus/unit/WaterThermalTanks.unit.cc#L1060"


def _node(identifier, mass=100.0, temperature=298.15, tracer=0.0):
    return {"id": identifier, "initial_mass_kg": mass, "min_mass_kg": 1.0,
            "max_mass_kg": mass * 3, "initial_temperature_K": temperature,
            "initial_tracer_mass_fraction": tracer, "inventory_mode": "fixed",
            "heat_power_W": 0.0, "ua_ambient_W_K": 0.0}


def _edge(identifier, source, target, flow=1.0):
    return {"id": identifier, "source": source, "target": target, "mass_flow_kg_s": flow}


def _base(identifier, title):
    return {"schema_version": "dynamic-network/v1", "case_id": identifier, "title": title,
            "provenance": {"classification": "analytical_limit",
                           "source": "Balances de mezcla perfecta; solución analítica propia documentada en docs/REDES_TRANSITORIAS.md.",
                           "notes": "Parámetros propios para verificación; no son registros de planta ni resultados de otro simulador."},
            "fluid": {"cp_J_kg_K": 4180.0, "density_kg_m3": 998.0},
            "nodes": [], "sources": [], "edges": [], "heat_links": [],
            "ambient_temperature_K": 298.15,
            "simulation": {"duration_s": 600.0, "output_interval_s": 10.0,
                           "max_step_s": 10.0, "rtol": 1e-8, "atol": 1e-10, "method": "BDF",
                           "min_temperature_K": 278.15, "max_temperature_K": 363.15},
            "events": []}


def example_cases():
    cascade = _base("analytical-cascade", "Tres tanques en serie: residencia y trazador")
    cascade["nodes"] = [_node(name) for name in ("A", "B", "C")]
    cascade["sources"] = [{"id": "feed", "temperature_K": 338.15, "tracer_mass_fraction": 1.0}]
    cascade["edges"] = [_edge("feed_A", "feed", "A"), _edge("A_B", "A", "B"),
                         _edge("B_C", "B", "C"), _edge("C_out", "C", None)]

    branch = _base("analytical-split-merge", "Bifurcación 60/40 y mezcla con inventario")
    branch["nodes"] = [_node("A"), _node("B", 60.0), _node("C", 40.0), _node("D")]
    branch["sources"] = [{"id": "feed", "temperature_K": 338.15, "tracer_mass_fraction": 1.0}]
    branch["edges"] = [_edge("feed_A", "feed", "A"), _edge("A_B", "A", "B", .6),
                        _edge("A_C", "A", "C", .4), _edge("B_D", "B", "D", .6),
                        _edge("C_D", "C", "D", .4), _edge("D_out", "D", None)]

    ring = _base("analytical-recirculation", "Recirculación con parada, reinicio y contacto térmico")
    ring["nodes"] = [_node("A", 100.0, 338.15, 1.0), _node("B", 50.0)]
    ring["edges"] = [_edge("A_B", "A", "B"), _edge("B_A", "B", "A")]
    ring["heat_links"] = [{"id": "contact", "first": "A", "second": "B", "ua_W_K": 200.0}]
    ring["events"] = [
        {"time_s": 100.0, "changes": {"edges": {key: {"mass_flow_kg_s": 0.0} for key in ("A_B", "B_A")}}},
        {"time_s": 200.0, "changes": {"edges": {key: {"mass_flow_kg_s": 1.0} for key in ("A_B", "B_A")}}},
    ]

    published = _base("energyplus-mixed-tank", "Depósito mezclado: parámetros publicados de EnergyPlus v24.2.0")
    published["provenance"] = {
        "classification": "published_reproduction", "source": ENERGYPLUS_URL,
        "notes": "Prueba numérica WaterThermalTank_CalcTempIntegral, blob dcc74d48ce4f02eb4d465633336f6d24414d13d3. "
                 "Mismos parámetros del depósito; temperaturas convertidas de °C a K. Integral publicada 14716.6 ± 0.1 °C·s. "
                 "No se ejecutó EnergyPlus ni se usaron mediciones experimentales.",
    }
    published["fluid"]["cp_J_kg_K"] = 4183.9
    published["nodes"] = [_node("tank", 148.67, 330.37)]
    published["nodes"][0]["ua_ambient_W_K"] = 5.0
    published["sources"] = [{"id": "feed", "temperature_K": 287.59, "tracer_mass_fraction": 0.0}]
    published["edges"] = [_edge("feed_tank", "feed", "tank", .06761), _edge("tank_out", "tank", None, .06761)]
    published["ambient_temperature_K"] = 292.87
    published["simulation"].update(duration_s=269.2, output_interval_s=1.0, max_step_s=2.0)
    return {"cascade.json": cascade, "split_merge.json": branch, "recirculation.json": ring,
            "energyplus_mixed_tank.json": published}


def reference_trajectories(case_id, times):
    """Closed forms for the documented example parameters, not arbitrary cases.

    Cascade: Erlang step responses. Split/merge: the same residence time on
    both branches. Ring: mean invariant and decaying difference with two clocks.
    EnergyPlus: scalar affine ODE solution with the published parameters.
    """
    t = np.asarray(times, dtype=float)
    if np.any(~np.isfinite(t)) or np.any(t < 0):
        raise ValueError("Nonnegative finite reference times required")
    if case_id in ("analytical-cascade", "analytical-split-merge"):
        x = t / 100.0
        response = [1 - np.exp(-x), 1 - np.exp(-x) * (1 + x),
                    1 - np.exp(-x) * (1 + x + x*x/2)]
        levels = {"A": 0, "B": 1, "C": 2} if case_id == "analytical-cascade" else {"A": 0, "B": 1, "C": 1, "D": 2}
        return {name: {"temperature_K": 298.15 + 40 * response[level],
                       "tracer_mass_fraction": response[level]} for name, level in levels.items()}
    if case_id == "analytical-recirculation":
        active_time = np.minimum(t, 100.0) + np.maximum(t - 200.0, 0.0)
        thermal_decay = np.exp(-(.01 + .02) * (active_time + 200.0 / 4180.0 * t))
        tracer_decay = np.exp(-(.01 + .02) * active_time)
        mean_t = (100 * 338.15 + 50 * 298.15) / 150
        mean_z = 100 / 150
        return {name: {"temperature_K": mean_t + factor * 40 * thermal_decay,
                       "tracer_mass_fraction": mean_z + factor * tracer_decay}
                for name, factor in (("A", 1/3), ("B", -2/3))}
    if case_id == "energyplus-mixed-tank":
        cp, mass, flow, ua = 4183.9, 148.67, .06761, 5.0
        equilibrium = (flow*cp*287.59 + ua*292.87) / (flow*cp + ua)
        rate = (flow*cp + ua) / (mass*cp)
        return {"tank": {"temperature_K": equilibrium + (330.37-equilibrium)*np.exp(-rate*t),
                         "tracer_mass_fraction": np.zeros_like(t)}}
    raise ValueError("No independent closed form registered for this case_id")


def energyplus_integral_C_s(duration=269.2):
    """Analytical scalar integral for checking the published rounded number."""
    cp, mass, flow, ua = 4183.9, 148.67, .06761, 5.0
    equilibrium = (flow*cp*14.44 + ua*19.72)/(flow*cp+ua)
    rate = (flow*cp+ua)/(mass*cp)
    return equilibrium*duration + (57.22-equilibrium)*(-math.expm1(-rate*duration))/rate
