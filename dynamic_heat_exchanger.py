"""Finite-volume, two-stream sensible heat exchanger with a finite wall.

Positive prescribed flows; constant properties; co-current or counter-current.
Each axial cell contains two fluid inventories and one wall capacity. Upwind
transport is first order in space. There is no axial conduction or pressure solve.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.sparse import lil_matrix

from dynamic_network import _keys, _number

SCHEMA_VERSION = "dynamic-heat-exchanger/v1"
MODEL_VERSION = "1.0.0"
TREF = 273.15
MAX_CELLS = 128
MAX_PROFILE_VALUES = 500000
MAX_RHS_EVALUATIONS = 200000


def default_case():
    return {
        "schema_version": SCHEMA_VERSION, "case_id": "synthetic-counter-current-hx",
        "title": "Intercambiador sensible con pared y residencia distribuidas",
        "provenance": {"classification": "analytical_limit", "source": "Balances propios de volúmenes finitos y referencias analíticas.",
                       "notes": "Parámetros sintéticos; no son datos de planta ni de fabricante."},
        "cells": 20, "flow_arrangement": "counter_current",
        "geometry": {"length_m": 2.0, "hot_cross_area_m2": .005, "cold_cross_area_m2": .005,
                     "hot_heat_area_m2": 1.0, "cold_heat_area_m2": 1.0},
        "hot_fluid": {"density_kg_m3": 1000., "cp_J_kg_K": 4180.},
        "cold_fluid": {"density_kg_m3": 1000., "cp_J_kg_K": 4180.},
        "wall": {"thickness_m": .002, "conductivity_W_m_K": 15., "density_kg_m3": 7800., "cp_J_kg_K": 500.},
        "heat_transfer": {"hot_h_W_m2_K": 1000., "cold_h_W_m2_K": 1000.},
        "initial": {"hot_temperature_K": 300., "cold_temperature_K": 300., "wall_temperature_K": 300.},
        "inputs": {"hot_flow_kg_s": .2, "cold_flow_kg_s": .2,
                   "hot_inlet_temperature_K": 360., "cold_inlet_temperature_K": 300.},
        "simulation": {"duration_s": 500., "output_interval_s": 5., "max_step_s": 5.,
                       "rtol": 1e-8, "atol": 1e-9, "method": "BDF", "min_temperature_K": 275., "max_temperature_K": 370.},
        "events": [],
    }


def _coefficients(case):
    g, w, ht, n = case["geometry"], case["wall"], case["heat_transfer"], case["cells"]
    area = (g["hot_heat_area_m2"] + g["cold_heat_area_m2"]) / 2
    mass_h = case["hot_fluid"]["density_kg_m3"] * g["hot_cross_area_m2"] * g["length_m"]
    mass_c = case["cold_fluid"]["density_kg_m3"] * g["cold_cross_area_m2"] * g["length_m"]
    wall_capacity = w["density_kg_m3"] * area * w["thickness_m"] * w["cp_J_kg_K"]
    half_wall = 2 * w["conductivity_W_m_K"] * area / w["thickness_m"]
    conductances = []
    for side in ("hot", "cold"):
        film = ht[side + "_h_W_m2_K"] * g[side + "_heat_area_m2"]
        if not math.isfinite(film):
            raise ValueError("Conductancia de pelicula fuera del rango numerico.")
        # Harmonic combination avoids overflow of a product of conductances.
        lo, hi = min(film, half_wall), max(film, half_wall)
        conductances.append(0. if lo == 0 else lo / (1 + lo / hi))
    capacities = np.repeat([mass_h * case["hot_fluid"]["cp_J_kg_K"] / n,
                            mass_c * case["cold_fluid"]["cp_J_kg_K"] / n, wall_capacity / n], n)
    if (not np.all(np.isfinite(capacities)) or np.any(capacities <= 0)
            or half_wall <= 0
            or not all(math.isfinite(v) for v in (area, mass_h, mass_c, half_wall, *conductances))):
        raise ValueError("Geometría/capacidades fuera del rango numérico.")
    return capacities, conductances[0] / n, conductances[1] / n, mass_h, mass_c


def validate_heat_exchanger(config):
    """Validate all intervals before integrating; overflow is an input error."""
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _validate_heat_exchanger(config)
    except (FloatingPointError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError("Parametros derivados fuera del rango numerico.") from exc


def _validate_heat_exchanger(config):
    template = default_case()
    _keys(config, set(template), "intercambiador")
    c = copy.deepcopy(dict(config))
    if c["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version: se requiere {SCHEMA_VERSION}.")
    for name in ("case_id", "title"):
        if not isinstance(c[name], str) or not c[name].strip():
            raise ValueError(f"{name}: texto no vacío requerido.")
    for section in ("provenance", "geometry", "hot_fluid", "cold_fluid", "wall", "heat_transfer", "initial", "inputs", "simulation"):
        _keys(c[section], set(template[section]), section)
    for value in c["provenance"].values():
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Procedencia textual completa requerida.")
    if c["provenance"]["classification"] not in ("analytical_limit", "documented_adaptation", "published_reproduction"):
        raise ValueError("Clasificación de procedencia desconocida.")
    if isinstance(c["cells"], bool) or not isinstance(c["cells"], int) or not 1 <= c["cells"] <= MAX_CELLS:
        raise ValueError(f"cells: entero entre 1 y {MAX_CELLS}.")
    if c["flow_arrangement"] not in ("co_current", "counter_current"):
        raise ValueError("flow_arrangement: co_current o counter_current.")
    for section in ("geometry", "hot_fluid", "cold_fluid", "wall", "heat_transfer"):
        for key, value in c[section].items():
            c[section][key] = _number(value, section + "." + key, low=0, positive=section != "heat_transfer")
    sim = c["simulation"]
    for key in set(sim) - {"method"}:
        sim[key] = _number(sim[key], "simulation." + key, positive=True)
    if sim["method"] not in ("BDF", "Radau"):
        raise ValueError("Método requerido: BDF o Radau.")
    if not 1e-12 <= sim["rtol"] <= 1e-2 or not 1e-14 <= sim["atol"] <= 1e-2:
        raise ValueError("Tolerancias fuera del dominio numérico permitido.")
    low, high = sim["min_temperature_K"], sim["max_temperature_K"]
    if not low < high:
        raise ValueError("Intervalo térmico vacío.")
    for key, value in c["initial"].items():
        values = value if isinstance(value, list) else [value] * c["cells"]
        if len(values) != c["cells"]:
            raise ValueError(f"initial.{key}: longitud distinta de cells.")
        values = [_number(v, "initial." + key, low=low, high=high) for v in values]
        if any(v <= low or v >= high for v in values):
            raise ValueError("Temperaturas iniciales fuera del intervalo abierto.")
        c["initial"][key] = values

    def check_inputs(values):
        for key, value in values.items():
            values[key] = _number(value, "inputs." + key, low=low if key.endswith("temperature_K") else 0,
                                   high=high if key.endswith("temperature_K") else None)
    check_inputs(c["inputs"])
    if not isinstance(c["events"], list) or len(c["events"]) > 1000:
        raise ValueError("events: lista de hasta 1000 cambios.")
    previous = 0.
    for event in c["events"]:
        _keys(event, {"time_s", "changes"}, "evento")
        event["time_s"] = _number(event["time_s"], "evento.time_s", positive=True, high=sim["duration_s"])
        if event["time_s"] <= previous:
            raise ValueError("Eventos con tiempos únicos y crecientes requeridos.")
        previous = event["time_s"]
        _keys(event["changes"], set(), "evento.changes", optional=c["inputs"])
        if not event["changes"]:
            raise ValueError("Evento vacío.")
        check_inputs(event["changes"])
    samples = sim["duration_s"] / sim["output_interval_s"] + len(c["events"]) + 2
    if samples * (3*c["cells"] + 2) > MAX_PROFILE_VALUES:
        raise ValueError("Demasiados valores de perfil; aumente el intervalo de salida.")
    if sim["duration_s"] / sim["max_step_s"] > MAX_RHS_EVALUATIONS / 10:
        raise ValueError("Demasiados pasos solicitados.")
    coef = _coefficients(c)
    initial = np.concatenate([c["initial"][key] for key in ("hot_temperature_K", "cold_temperature_K", "wall_temperature_K")])
    if not math.isfinite(float(np.sum(coef[0] * max(abs(low-TREF), abs(high-TREF))))):
        raise ValueError("Energía almacenada fuera del rango numérico.")
    active = dict(c["inputs"])
    for change in [{}, *(e["changes"] for e in c["events"])]:
        active.update(change)
        rates, external, absolute, _ = _rates(c, initial, active, coef)
        if not np.all(np.isfinite(rates / coef[0])) or not math.isfinite(external + absolute):
            raise ValueError("Flujos/derivadas fuera del rango numérico.")
        max_flux = sum(active[side + "_flow_kg_s"] * c[side + "_fluid"]["cp_J_kg_K"]
                       for side in ("hot", "cold")) * 2 * max(abs(low-TREF), abs(high-TREF))
        if not math.isfinite(max_flux * sim["duration_s"]):
            raise ValueError("Integral de energia fuera del rango numerico.")
    return c


def _rates(c, temperatures, inputs, coefficients):
    n = c["cells"]
    capacity, gh, gc, _, _ = coefficients
    hot, cold, wall = np.asarray(temperatures[:3*n]).reshape((3, n))
    hot_up = np.concatenate(([inputs["hot_inlet_temperature_K"]], hot[:-1]))
    counter = c["flow_arrangement"] == "counter_current"
    cold_up = (np.concatenate((cold[1:], [inputs["cold_inlet_temperature_K"]])) if counter
               else np.concatenate(([inputs["cold_inlet_temperature_K"]], cold[:-1])))
    fh = inputs["hot_flow_kg_s"] * c["hot_fluid"]["cp_J_kg_K"]
    fc = inputs["cold_flow_kg_s"] * c["cold_fluid"]["cp_J_kg_K"]
    qh, qc = gh * (hot-wall), gc * (cold-wall)
    rates = np.concatenate((fh*(hot_up-hot)-qh, fc*(cold_up-cold)-qc, qh+qc))
    th_out, tc_out = float(hot[-1]), float(cold[0] if counter else cold[-1])
    external = fh*(inputs["hot_inlet_temperature_K"]-th_out) + fc*(inputs["cold_inlet_temperature_K"]-tc_out)
    absolute = fh*(abs(inputs["hot_inlet_temperature_K"]-TREF)+abs(th_out-TREF))
    absolute += fc*(abs(inputs["cold_inlet_temperature_K"]-TREF)+abs(tc_out-TREF))
    if not np.all(np.isfinite(rates)) or not all(math.isfinite(x) for x in (external, absolute)):
        raise ValueError("Flujos no finitos en el intercambiador.")
    return rates, external, absolute, (qh, qc)


def _sparsity(n, counter):
    pattern = lil_matrix((3*n+2, 3*n+2), dtype=int)
    for i in range(n):
        pattern[i, i] = pattern[i, 2*n+i] = 1
        if i: pattern[i, i-1] = 1
        pattern[n+i, n+i] = pattern[n+i, 2*n+i] = 1
        upstream = i+1 if counter else i-1
        if 0 <= upstream < n: pattern[n+i, n+upstream] = 1
        pattern[2*n+i, i] = pattern[2*n+i, n+i] = pattern[2*n+i, 2*n+i] = 1
    pattern[3*n:, n-1] = 1
    pattern[3*n:, n if counter else 2*n-1] = 1
    return pattern.tocsr()


class _Cancelled(Exception): pass
class _WorkLimit(Exception): pass


def simulate_heat_exchanger(config, *, cancel=None):
    c = validate_heat_exchanger(config)
    n, sim = c["cells"], c["simulation"]
    coef = _coefficients(c)
    capacities = coef[0]
    initial = np.concatenate([c["initial"][key] for key in ("hot_temperature_K", "cold_temperature_K", "wall_temperature_K")])
    y = np.concatenate((initial, [0., 0.]))
    initial_energy = float(capacities @ (initial-TREF))
    inputs = dict(c["inputs"])
    series, events, diagnostics = [], [], []
    evaluations, now = 0, 0.
    status, reason = "ok", "completed"
    max_residual, max_relative, max_rate_relative = 0., 0., 0.

    def rhs(time, state):
        nonlocal evaluations
        evaluations += 1
        if cancel is not None and cancel(): raise _Cancelled()
        if evaluations > MAX_RHS_EVALUATIONS: raise _WorkLimit()
        rates, external, absolute, _ = _rates(c, state, inputs, coef)
        return np.concatenate((rates / capacities, [external, absolute]))

    def record(time, state):
        nonlocal max_residual, max_relative, max_rate_relative
        rates, external, absolute, (qh, qc) = _rates(c, state, inputs, coef)
        hot, cold, wall = state[:3*n].reshape((3, n))
        energy = float(capacities @ (state[:3*n]-TREF))
        residual = energy-initial_energy-float(state[3*n])
        relative = abs(residual) / max(1., abs(initial_energy), float(state[3*n+1]))
        rate_relative = abs(float(np.sum(rates))-external) / max(1., absolute, float(np.sum(np.abs(qh)+np.abs(qc))))
        max_residual = max(max_residual, abs(residual))
        max_relative, max_rate_relative = max(max_relative, relative), max(max_rate_relative, rate_relative)
        row = {"time_s": float(time), "hot_temperature_K": list(map(float, hot)),
               "cold_temperature_K": list(map(float, cold)), "wall_temperature_K": list(map(float, wall)),
               "hot_outlet_temperature_K": float(hot[-1]),
               "cold_outlet_temperature_K": float(cold[0] if c["flow_arrangement"] == "counter_current" else cold[-1]),
               "hot_to_wall_heat_W": float(np.sum(qh)), "cold_to_wall_heat_W": float(np.sum(qc)),
               "wall_energy_rate_W": float(np.sum(qh+qc)), "total_stored_energy_J": energy,
               "cumulative_external_energy_J": float(state[3*n]), "energy_balance_error_J": residual, **inputs}
        if series and series[-1]["time_s"] == time: series[-1] = row
        else: series.append(row)

    def lower(time, state): return float(min(state[:3*n]))-sim["min_temperature_K"]
    def upper(time, state): return sim["max_temperature_K"]-float(max(state[:3*n]))
    for fun in (lower, upper): fun.terminal, fun.direction = True, -1
    changes = {e["time_s"]: e["changes"] for e in c["events"]}
    times = [*np.arange(0., sim["duration_s"], sim["output_interval_s"]), sim["duration_s"]]
    sample_index = 1
    record(0., y)
    sparsity = _sparsity(n, c["flow_arrangement"] == "counter_current")
    for end in sorted({sim["duration_s"], *changes}):
        try:
            if cancel is not None and cancel(): raise _Cancelled()
            solution = solve_ivp(rhs, (now, end), y, method=sim["method"], rtol=sim["rtol"], atol=sim["atol"],
                                 max_step=sim["max_step_s"], jac_sparsity=sparsity, events=[lower, upper], dense_output=True)
            if not np.all(np.isfinite(solution.y[:, -1])): raise ValueError("Estado no finito.")
            now, y = float(solution.t[-1]), solution.y[:, -1]
            while sample_index < len(times) and times[sample_index] <= now:
                time = float(times[sample_index])
                record(time, solution.sol(time))
                sample_index += 1
            record(now, y)
            if not solution.success:
                status, reason = "error", "integration_failed"
                diagnostics.append(str(solution.message))
                break
            if solution.status == 1:
                status, reason = "limit", "temperature_low" if len(solution.t_events[0]) else "temperature_high"
                events.append({"time_s": now, "kind": "terminal_limit", "reason": reason})
                break
            if end in changes:
                inputs.update(changes[end])
                events.append({"time_s": end, "kind": "input_change", "changes": changes[end]})
                record(end, y)
        except (_Cancelled, _WorkLimit) as exc:
            status = "cancelled" if isinstance(exc, _Cancelled) else "error"
            reason = "user_cancelled" if isinstance(exc, _Cancelled) else "evaluation_budget_exceeded"
            break
        except (ValueError, FloatingPointError, OverflowError) as exc:
            status, reason = "error", "integration_failed"
            diagnostics.append(f"{type(exc).__name__}: {exc}")
            break
    if max_relative > max(100*sim["rtol"], 1e-7) and status == "ok":
        status, reason = "error", "energy_audit_failed"
    result = {
        "schema_version": SCHEMA_VERSION, "configuration": c,
        "summary": {"success": status == "ok", "status": status, "stop_reason": reason,
                    "final_time_s": series[-1]["time_s"], "requested_duration_s": sim["duration_s"],
                    "samples": len(series), "rhs_evaluations": evaluations},
        "metadata": {"model_version": MODEL_VERSION, "config_sha256": hashlib.sha256(json.dumps(c, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest(),
                     "provenance": c["provenance"], "simulation_data_kind": "synthetic", "validation_state": "unvalidated_against_plant",
                     "numpy_version": np.__version__, "scipy_version": scipy.__version__, "time_convention": "right_continuous",
                     "solver": sim["method"], "spatial_scheme": "first_order_upwind_finite_volume", "reference_temperature_K": TREF},
        "geometry": {"cell_centres_m": list(map(float, (np.arange(n)+.5)*c["geometry"]["length_m"]/n)),
                     "hot_total_mass_kg": coef[3], "cold_total_mass_kg": coef[4],
                     "wall_total_heat_capacity_J_K": float(np.sum(capacities[2*n:])),
                     "hot_to_wall_total_conductance_W_K": coef[1]*n, "cold_to_wall_total_conductance_W_K": coef[2]*n},
        "audit": {"max_energy_residual_J": max_residual, "max_energy_residual_relative": max_relative,
                  "max_energy_rate_residual_relative": max_rate_relative,
                  "mass_balance": "fixed inventories; equal inlet/outlet prescribed flow separately on each side",
                  "scope": "both fluids and wall; only boundary enthalpy crosses the model boundary",
                  "evaluated_at": "reported_samples_and_segment_endpoints"},
        "assumptions": ["Dos fluidos monofásicos con Cp y densidad constantes, sin mezcla entre ellos.",
                        "Caudales no negativos impuestos; sin presión dinámica ni inversión de flujo.",
                        "Mezcla perfecta por celda, advección upwind de primer orden; sin conducción axial ni dispersión física añadida.",
                        "Pared de capacidad finita por celda; resistencias de película y media pared en serie; coeficientes constantes.",
                        "Sin pérdidas al ambiente, cambio de fase, reacción, sensores ni control automático.",
                        "Los perfiles son promedios de celda; un refinamiento temporal no elimina el error espacial.",
                        "Inicialización con perfiles dados; no se impone un estado estacionario."],
        "events": events, "diagnostics": diagnostics, "series": series,
    }
    json.dumps(result, allow_nan=False)
    return result
