"""Directed, prescribed-flow networks of finite well-mixed liquid inventories.

All units are SI. One incompressible liquid has constant Cp/rho throughout the
network; a passive tracer does not change its properties. This is an explicit
initial-value problem, not a pressure/flow solver or an arbitrary DAE flowsheet.
No GUI, calibration or plant-validity claim is implied by a completed run.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.sparse import lil_matrix

SCHEMA_VERSION = "dynamic-network/v1"
MODEL_VERSION = "1.0.0"
REFERENCE_TEMPERATURE_K = 273.15
MAX_NODES = 32
MAX_EDGES = 128
MAX_SAMPLES = 20000
MAX_RHS_EVALUATIONS = 200000


def _keys(value, required, name, *, optional=()):
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        raise ValueError(f"{name}: se requiere un objeto con claves de texto.")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing or extra:
        raise ValueError(f"{name}: faltan {sorted(missing)}; claves desconocidas {sorted(extra)}.")


def _number(value, name, *, low=None, high=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: número finito requerido.")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name}: número finito requerido.") from exc
    if (not math.isfinite(result) or (positive and result <= 0)
            or (low is not None and result < low) or (high is not None and result > high)):
        raise ValueError(f"{name}: valor fuera del dominio permitido.")
    return result


def _identifier(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value):
        raise ValueError(f"{name}: identificador ASCII de 1 a 64 caracteres requerido.")
    return value


def _items(value, name, maximum, *, nonempty=False):
    if not isinstance(value, list) or len(value) > maximum or (nonempty and not value):
        raise ValueError(f"{name}: lista {'no vacía ' if nonempty else ''}de hasta {maximum} elementos.")
    return value


def _apply_changes(case, changes):
    for section, updates in changes.items():
        by_id = {item["id"]: item for item in case[section]}
        for identifier, values in updates.items():
            by_id[identifier].update(values)


def _mass_rates(case):
    incoming = {node["id"]: [] for node in case["nodes"]}
    outgoing = {node["id"]: [] for node in case["nodes"]}
    for edge in case["edges"]:
        flow = edge["mass_flow_kg_s"]
        if edge["source"] in outgoing:
            outgoing[edge["source"]].append(flow)
        if edge["target"] is not None:
            incoming[edge["target"]].append(flow)
    return {key: math.fsum(incoming[key]) - math.fsum(outgoing[key]) for key in incoming}


def _check_fixed_inventories(case, when):
    rates = _mass_rates(case)
    for node in case["nodes"]:
        if node["inventory_mode"] != "fixed":
            continue
        throughput = math.fsum(edge["mass_flow_kg_s"] for edge in case["edges"]
                               if node["id"] in (edge["source"], edge["target"]))
        if abs(rates[node["id"]]) > 1e-12 * throughput:
            raise ValueError(f"{when}: inventario fijo incompatible en {node['id']}; "
                             f"entrada - salida = {rates[node['id']]:.12g} kg/s.")


def validate_network(config):
    if isinstance(config, Mapping) and config.get("schema_version") == "dynamic-network/v2":
        from dynamic_network_components import prepare_network
        return prepare_network(config)[0]
    return _validate_network_core(config)


def _node_property(case, node, key):
    return case.get("_materials", {}).get(node["id"], case["fluid"])[key]


def _validate_network_core(config, *, materials=None, max_nodes=MAX_NODES, max_edges=MAX_EDGES, allow_self_edges=()):
    """Validate initial conditions, graph, every event and fixed-mass constraints.

    Unknown fields are rejected, including unimplemented pressure/level specs.
    Scheduled filling/draining is valid and stops at its declared mass limit.
    """
    _keys(config, {"schema_version", "case_id", "title", "provenance", "fluid", "nodes",
                   "sources", "edges", "heat_links", "ambient_temperature_K", "simulation", "events"}, "caso")
    c = copy.deepcopy(dict(config))
    if materials:
        c["_materials"] = copy.deepcopy(materials)
    if c["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version: se requiere {SCHEMA_VERSION}.")
    for key in ("case_id", "title"):
        if not isinstance(c[key], str) or not c[key].strip():
            raise ValueError(f"{key}: texto no vacío requerido.")
    _keys(c["provenance"], {"classification", "source", "notes"}, "provenance")
    for key, value in c["provenance"].items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"provenance.{key}: texto no vacío requerido.")
    if c["provenance"]["classification"] not in {
            "published_reproduction", "documented_adaptation", "analytical_limit"}:
        raise ValueError("provenance.classification: categoría de verificación teórica requerida.")
    _keys(c["fluid"], {"cp_J_kg_K", "density_kg_m3"}, "fluid")
    for key in c["fluid"]:
        c["fluid"][key] = _number(c["fluid"][key], "fluid." + key, positive=True)
    s = c["simulation"]
    _keys(s, {"duration_s", "output_interval_s", "max_step_s", "rtol", "atol", "method",
              "min_temperature_K", "max_temperature_K"}, "simulation")
    for key in set(s) - {"method"}:
        s[key] = _number(s[key], "simulation." + key, positive=True)
    if s["method"] not in ("BDF", "Radau"):
        raise ValueError("simulation.method: BDF o Radau.")
    if not 1e-12 <= s["rtol"] <= 1e-2 or not 1e-14 <= s["atol"] <= 1e-2:
        raise ValueError("Tolerancias fuera del dominio numérico admitido.")
    lo, hi = s["min_temperature_K"], s["max_temperature_K"]
    if not lo < hi:
        raise ValueError("Intervalo de temperatura vacío.")
    c["ambient_temperature_K"] = _number(c["ambient_temperature_K"], "ambiente", low=lo, high=hi)
    _items(c["nodes"], "nodes", max_nodes, nonempty=True)
    _items(c["sources"], "sources", MAX_EDGES)
    _items(c["edges"], "edges", max_edges)
    _items(c["heat_links"], "heat_links", max_edges)
    ids = set()
    for section in ("nodes", "sources"):
        for item in c[section]:
            required = ({"id", "initial_mass_kg", "min_mass_kg", "max_mass_kg", "initial_temperature_K",
                         "initial_tracer_mass_fraction", "inventory_mode", "heat_power_W", "ua_ambient_W_K"}
                        if section == "nodes" else {"id", "temperature_K", "tracer_mass_fraction"})
            _keys(item, required, section)
            identifier = _identifier(item["id"], section + ".id")
            if identifier in ids:
                raise ValueError(f"Identificador de unidad/frontera duplicado: {identifier}.")
            ids.add(identifier)
            if section == "sources":
                item["temperature_K"] = _number(item["temperature_K"], identifier + ".temperature_K", low=lo, high=hi)
                item["tracer_mass_fraction"] = _number(item["tracer_mass_fraction"], identifier + ".tracer", low=0, high=1)
                continue
            for key in ("initial_mass_kg", "min_mass_kg", "max_mass_kg", "initial_temperature_K"):
                item[key] = _number(item[key], identifier + "." + key, positive=True)
            if not item["min_mass_kg"] < item["initial_mass_kg"] < item["max_mass_kg"]:
                raise ValueError(f"{identifier}: inventario inicial fuera del intervalo abierto de masas.")
            if not lo < item["initial_temperature_K"] < hi:
                raise ValueError(f"{identifier}: temperatura inicial fuera del intervalo abierto.")
            if item["inventory_mode"] not in ("fixed", "variable"):
                raise ValueError(f"{identifier}: inventory_mode debe ser fixed o variable.")
            item["initial_tracer_mass_fraction"] = _number(item["initial_tracer_mass_fraction"], identifier + ".tracer", low=0, high=1)
            item["heat_power_W"] = _number(item["heat_power_W"], identifier + ".heat_power_W")
            item["ua_ambient_W_K"] = _number(item["ua_ambient_W_K"], identifier + ".ua_ambient_W_K", low=0)
    nodes = {n["id"] for n in c["nodes"]}
    for section in ("edges", "heat_links"):
        seen = set()
        for item in c[section]:
            _keys(item, {"id", "source", "target", "mass_flow_kg_s"} if section == "edges"
                  else {"id", "first", "second", "ua_W_K"}, section)
            identifier = _identifier(item["id"], section + ".id")
            if identifier in seen:
                raise ValueError(f"{section}: conexión duplicada {identifier}.")
            seen.add(identifier)
            if section == "edges":
                source, target = item["source"], item["target"]
                if not isinstance(source, str) or source not in ids:
                    raise ValueError(f"{identifier}: origen inexistente.")
                if target is not None and (not isinstance(target, str) or target not in nodes):
                    raise ValueError(f"{identifier}: destino debe ser un inventario o null (salida).")
                if (source == target and identifier not in allow_self_edges) or (source not in nodes and target is None):
                    raise ValueError(f"{identifier}: conexión sin inventario o consigo misma.")
                item["mass_flow_kg_s"] = _number(item["mass_flow_kg_s"], identifier + ".mass_flow_kg_s", low=0)
            else:
                if any(not isinstance(item[k], str) or item[k] not in nodes for k in ("first", "second")):
                    raise ValueError(f"{identifier}: conexión térmica requiere dos inventarios.")
                if item["first"] == item["second"]:
                    raise ValueError(f"{identifier}: conexión térmica consigo misma.")
                item["ua_W_K"] = _number(item["ua_W_K"], identifier + ".ua_W_K", low=0)
    _items(c["events"], "events", 1000)
    if s["duration_s"] / s["output_interval_s"] + len(c["events"]) + 2 > MAX_SAMPLES:
        raise ValueError("Demasiadas muestras de salida.")
    if s["duration_s"] / s["max_step_s"] > MAX_RHS_EVALUATIONS / 10:
        raise ValueError("El paso máximo exige demasiadas evaluaciones.")
    allowed = {"edges": {"mass_flow_kg_s"}, "sources": {"temperature_K", "tracer_mass_fraction"},
               "nodes": {"heat_power_W"}}
    previous = 0.0
    for event in c["events"]:
        _keys(event, {"time_s", "changes"}, "evento")
        event["time_s"] = _number(event["time_s"], "evento.time_s", positive=True, high=s["duration_s"])
        if event["time_s"] <= previous:
            raise ValueError("Los eventos deben tener tiempos únicos crecientes mayores que cero.")
        previous = event["time_s"]
        changes = event["changes"]
        _keys(changes, set(), "evento.changes", optional=allowed)
        if not changes:
            raise ValueError("Evento vacío.")
        for section, updates in changes.items():
            _keys(updates, set(), "evento." + section, optional={item["id"] for item in c[section]})
            if not updates:
                raise ValueError("Grupo de cambios vacío.")
            for identifier, values in updates.items():
                _keys(values, set(), "evento." + identifier, optional=allowed[section])
                if not values:
                    raise ValueError("Cambio vacío.")
                for key, value in values.items():
                    low = lo if key == "temperature_K" else None if key == "heat_power_W" else 0
                    high = hi if key == "temperature_K" else 1 if key == "tracer_mass_fraction" else None
                    values[key] = _number(value, "evento." + identifier + "." + key, low=low, high=high)
    # Check every prescribed interval, including an event at the final time.
    check = copy.deepcopy(c)
    try:
        for node in c["nodes"]:
            cp, rho = (_node_property(c, node, key) for key in ("cp_J_kg_K", "density_kg_m3"))
            envelope = (node["min_mass_kg"] * cp, node["max_mass_kg"] * cp,
                        node["max_mass_kg"] / rho,
                        node["max_mass_kg"] * cp * max(abs(lo - REFERENCE_TEMPERATURE_K), abs(hi - REFERENCE_TEMPERATURE_K)))
            if envelope[0] <= 0 or not all(math.isfinite(v) for v in envelope):
                raise ValueError(f"{node['id']}: dominio físico fuera del rango numérico.")
        initial = _initial_state(c)
        if not np.all(np.isfinite(initial)) or not np.all(np.isfinite(np.abs(initial.reshape((-1, 3))).sum(axis=0))):
            raise ValueError("Inventario inicial fuera del rango numérico.")
        _check_fixed_inventories(check, "t=0")
        _rates(check, initial)
        for event in c["events"]:
            _apply_changes(check, event["changes"])
            _check_fixed_inventories(check, f"t={event['time_s']:g}")
            _rates(check, initial)
    except (OverflowError, FloatingPointError) as exc:
        raise ValueError("Escalas físicas no representables numéricamente.") from exc
    return c


def _initial_state(case):
    return np.array([[n["initial_mass_kg"], n["initial_mass_kg"] * _node_property(case, n, "cp_J_kg_K") *
                      (n["initial_temperature_K"] - REFERENCE_TEMPERATURE_K),
                      n["initial_mass_kg"] * n["initial_tracer_mass_fraction"]]
                     for n in case["nodes"]], dtype=float).reshape(-1)


def _physical(case, state):
    inventories = np.asarray(state[:3 * len(case["nodes"])]).reshape((-1, 3))
    masses = inventories[:, 0]
    cp = np.array([_node_property(case, node, "cp_J_kg_K") for node in case["nodes"]])
    capacity = masses * cp
    if np.any(masses <= 0) or np.any(capacity <= 0) or not np.all(np.isfinite(capacity)):
        raise FloatingPointError("Inventario o capacidad calorífica no representable.")
    temperature = REFERENCE_TEMPERATURE_K + inventories[:, 1] / capacity
    tracer = inventories[:, 2] / masses
    if not np.all(np.isfinite(temperature)) or not np.all(np.isfinite(tracer)):
        raise FloatingPointError("Estado físico no finito.")
    return inventories, temperature, tracer


def _rates(case, state):
    """Assemble each directed transfer ONCE, then scatter equal/opposite fluxes.

    Columns are mass (kg/s), sensible energy (W), passive tracer (kg/s).
    The external ledger is assembled from boundary ports and external heat only.
    """
    inventory, temperature, tracer = _physical(case, state)
    index = {n["id"]: i for i, n in enumerate(case["nodes"])}
    sources = {s["id"]: s for s in case["sources"]}
    rates = np.zeros_like(inventory)
    external, absolute = np.zeros(3), np.zeros(3)
    ports = []
    cp = case["fluid"]["cp_J_kg_K"]
    for edge in case["edges"]:
        source, target, flow = edge["source"], edge["target"], edge["mass_flow_kg_s"]
        if source in index:
            t, z = temperature[index[source]], tracer[index[source]]
        else:
            t, z = sources[source]["temperature_K"], sources[source]["tracer_mass_fraction"]
        t, z = float(t), float(z)
        # A stopped port is exactly zero, even with extreme but finite enthalpy.
        flux = np.zeros(3) if flow == 0 else np.array([flow, flow * cp * (t - REFERENCE_TEMPERATURE_K), flow * z])
        if not np.all(np.isfinite(flux)):
            raise FloatingPointError("Transporte por puerto fuera del rango numérico.")
        if source in index:
            rates[index[source]] -= flux
        else:
            external += flux
            absolute += np.abs(flux)
        if target is not None:
            rates[index[target]] += flux
        else:
            external -= flux
            absolute += np.abs(flux)
        ports.append({"id": edge["id"], "source": source, "target": target,
                      "mass_flow_kg_s": float(flux[0]), "energy_flow_W": float(flux[1]),
                      "tracer_flow_kg_s": float(flux[2]), "donor_temperature_K": float(t),
                      "donor_tracer_mass_fraction": float(z)})
    heat_ports = []
    for link in case["heat_links"]:
        first, second = index[link["first"]], index[link["second"]]
        power = link["ua_W_K"] * (float(temperature[first]) - float(temperature[second]))
        rates[first, 1] -= power
        rates[second, 1] += power
        heat_ports.append({"id": link["id"], "first": link["first"], "second": link["second"],
                           "heat_first_to_second_W": float(power)})
    for i, node in enumerate(case["nodes"]):
        loss = node["ua_ambient_W_K"] * (float(temperature[i]) - case["ambient_temperature_K"])
        power = node["heat_power_W"] - loss
        rates[i, 1] += power
        external[1] += power
        absolute[1] += abs(node["heat_power_W"]) + abs(loss)
    if not all(np.all(np.isfinite(value)) for value in (rates, external, absolute)):
        raise FloatingPointError("Flujos fuera del rango numérico.")
    return rates, external, absolute, ports, heat_ports


class _Cancelled(Exception):
    pass


class _WorkLimit(Exception):
    pass


def simulate_dynamic_network(config, *, cancel=None):
    if isinstance(config, Mapping) and config.get("schema_version") == "dynamic-network/v2":
        from dynamic_network_components import simulate_component_network
        return simulate_component_network(config, cancel=cancel)
    return _simulate_network_core(validate_network(config), cancel=cancel)


def _network_sparsity(case):
    n = len(case["nodes"])
    index = {node["id"]: i for i, node in enumerate(case["nodes"])}
    pattern = lil_matrix((3*n+6, 3*n+6), dtype=int)
    for i in range(n):
        pattern[3*i:3*i+3, 3*i:3*i+3] = 1
    for edge in case["edges"]:
        if edge["source"] in index and edge["target"] in index:
            i, j = index[edge["target"]], index[edge["source"]]
            pattern[3*i:3*i+3, 3*j:3*j+3] = 1
    for link in case["heat_links"]:
        i, j = index[link["first"]], index[link["second"]]
        pattern[3*i:3*i+3, 3*j:3*j+3] = 1
        pattern[3*j:3*j+3, 3*i:3*i+3] = 1
    # Internal recirculation cancels from the external ledger. Marking every
    # state here would defeat sparse finite-difference coloring on large meshes.
    external_nodes = {index[e["source"]] for e in case["edges"] if e["target"] is None and e["source"] in index}
    external_nodes.update(i for i, node in enumerate(case["nodes"]) if node["ua_ambient_W_K"] != 0)
    for i in external_nodes: pattern[3*n:, 3*i:3*i+3] = 1
    return pattern.tocsr()


def _simulate_network_core(c, *, cancel=None):
    """Run BDF/Radau with right-continuous events and global inventory audits.

    Output sampling never restarts the integration. Mass bounds are located
    analytically per constant-flow interval; temperature bounds use root events.
    Cancellation/errors retain completed intervals and never report success.
    """
    active = copy.deepcopy(c)
    sim = c["simulation"]
    n = len(c["nodes"])
    initial = _initial_state(c)
    y = np.concatenate((initial, np.zeros(6)))
    total0 = initial.reshape((n, 3)).sum(axis=0)
    initial_scale = np.abs(initial.reshape((n, 3))).sum(axis=0)
    names, units = ("mass", "energy", "tracer"), ("kg", "J", "kg")
    maximum_residual = np.zeros(3)
    maximum_relative = np.zeros(3)
    maximum_rate_relative = np.zeros(3)
    series, events, diagnostics = [], [], []
    evaluations = 0
    time_now = 0.0
    status, reason = "ok", "completed"
    min_tracer, max_tracer = 1.0, 0.0

    def rhs(time, state):
        nonlocal evaluations
        evaluations += 1
        if cancel is not None and cancel():
            raise _Cancelled()
        if evaluations > MAX_RHS_EVALUATIONS:
            raise _WorkLimit()
        rates, external, absolute, _, _ = _rates(active, state)
        return np.concatenate((rates.reshape(-1), external, absolute))

    def record(time, state):
        nonlocal min_tracer, max_tracer
        inventories, temperature, tracer = _physical(active, state)
        rates, external, _, ports, heat_ports = _rates(active, state)
        residual = inventories.sum(axis=0) - total0 - state[3*n:3*n+3]
        scale = np.maximum.reduce([initial_scale, state[3*n+3:3*n+6], np.array([1., 1., 1e-12])])
        relative = np.abs(residual) / scale
        maximum_residual[:] = np.maximum(maximum_residual, np.abs(residual))
        maximum_relative[:] = np.maximum(maximum_relative, relative)
        rate_error = np.abs(rates.sum(axis=0) - external)
        # Scale by transported quantities, not near-zero net rates at equilibrium.
        transport = np.array([math.fsum(abs(p[key]) for p in ports)
                              for key in ("mass_flow_kg_s", "energy_flow_W", "tracer_flow_kg_s")])
        transport[1] += math.fsum(abs(p["heat_first_to_second_W"]) for p in heat_ports)
        rate_scale = np.maximum(2 * transport + np.abs(rates).sum(axis=0) + np.abs(external), [1e-12, 1e-12, 1e-12])
        maximum_rate_relative[:] = np.maximum(maximum_rate_relative, rate_error / rate_scale)
        min_tracer, max_tracer = min(min_tracer, float(min(tracer))), max(max_tracer, float(max(tracer)))
        row = {"time_s": float(time), "nodes": {}, "ports": ports, "heat_ports": heat_ports,
               "balance_residual": {name + "_" + unit: float(value) for name, unit, value in zip(names, units, residual)}}
        for i, node in enumerate(c["nodes"]):
            row["nodes"][node["id"]] = {
                "mass_kg": float(inventories[i, 0]), "energy_J": float(inventories[i, 1]),
                "tracer_mass_kg": float(inventories[i, 2]), "temperature_K": float(temperature[i]),
                "tracer_mass_fraction": float(tracer[i]),
                "volume_m3": float(inventories[i, 0] / _node_property(c, node, "density_kg_m3")),
                "net_mass_flow_kg_s": float(rates[i, 0]), "net_energy_rate_W": float(rates[i, 1]),
                "net_tracer_flow_kg_s": float(rates[i, 2]),
            }
        if series and time == series[-1]["time_s"]:
            series[-1] = row
        else:
            series.append(row)

    boundaries, boundary_names = [], []
    for i, node in enumerate(c["nodes"]):
        for label, bound, sign in (("temperature_low", sim["min_temperature_K"], 1),
                                   ("temperature_high", sim["max_temperature_K"], -1)):
            def boundary(time, state, i=i, bound=bound, sign=sign):
                return sign * (_physical(active, state)[1][i] - bound)
            boundary.terminal, boundary.direction = True, -1
            boundaries.append(boundary)
            boundary_names.append(node["id"] + "." + label)
    duration = sim["duration_s"]
    output_times = [*np.arange(0, duration, sim["output_interval_s"]), duration]
    output_index = 1
    changes = {event["time_s"]: event["changes"] for event in c["events"]}
    stops = sorted({duration, *changes})
    record(0.0, y)
    solver_options = {"jac_sparsity": _network_sparsity(c)} if c.get("_materials") else {}
    for end in stops:
        if cancel is not None and cancel():
            status, reason = "cancelled", "user_cancelled"
            break
        integration_end, mass_limit = end, None
        masses = y[:3*n].reshape((n, 3))[:, 0]
        mass_rates = _mass_rates(active)
        for i, node in enumerate(c["nodes"]):
            rate = mass_rates[node["id"]]
            if rate == 0:
                continue
            bound = node["max_mass_kg"] if rate > 0 else node["min_mass_kg"]
            hit = time_now + (bound - masses[i]) / rate
            if hit <= integration_end:
                integration_end = max(time_now, hit)
                mass_limit = node["id"] + (".maximum_inventory" if rate > 0 else ".minimum_inventory")
        if integration_end <= time_now:
            status, reason = "limit", mass_limit
            events.append({"time_s": time_now, "kind": "terminal_limit", "reason": reason})
            break
        try:
            solution = solve_ivp(rhs, (time_now, integration_end), y, method=sim["method"],
                                 rtol=sim["rtol"], atol=sim["atol"], max_step=sim["max_step_s"],
                                 events=boundaries, dense_output=True, **solver_options)
            accepted_time = float(solution.t[-1])
            accepted_state = solution.y[:, -1]
            if not np.all(np.isfinite(accepted_state)):
                raise FloatingPointError("Estado final no finito.")
            while output_index < len(output_times) and output_times[output_index] <= accepted_time:
                sample = float(output_times[output_index])
                record(sample, solution.sol(sample))
                output_index += 1
            record(accepted_time, accepted_state)
            time_now, y = accepted_time, accepted_state
        except (_Cancelled, _WorkLimit) as exc:
            status = "cancelled" if isinstance(exc, _Cancelled) else "error"
            reason = "user_cancelled" if isinstance(exc, _Cancelled) else "evaluation_budget_exceeded"
            break
        except (ValueError, FloatingPointError, OverflowError) as exc:
            status, reason = "error", "integration_failed"
            diagnostics.append(f"{type(exc).__name__}: {exc}")
            break
        if not solution.success:
            status, reason = "error", "integration_failed"
            diagnostics.append(str(solution.message))
            break
        if solution.status == 1 or mass_limit is not None:
            status = "limit"
            reason = (boundary_names[next(i for i, hits in enumerate(solution.t_events) if len(hits))]
                      if solution.status == 1 else mass_limit)
            events.append({"time_s": time_now, "kind": "terminal_limit", "reason": reason})
            break
        if end in changes:
            _apply_changes(active, changes[end])
            events.append({"time_s": end, "kind": "input_change", "changes": changes[end]})
            try:
                record(end, y)
            except (ValueError, FloatingPointError, OverflowError) as exc:
                status, reason = "error", "event_flux_failed"
                diagnostics.append(f"{type(exc).__name__}: {exc}")
                break
    tracer_tolerance = max(100 * sim["rtol"], 1e-7)
    if min_tracer < -tracer_tolerance or max_tracer > 1 + tracer_tolerance:
        diagnostics.append("Trazador fuera de [0,1] más allá de la tolerancia; no se recortan estados.")
        if status == "ok":
            status, reason = "error", "tracer_bounds_exceeded"
    if max(maximum_relative) > max(100 * sim["rtol"], 1e-7):
        diagnostics.append("Residuos integrados de conservación fuera de tolerancia.")
        if status == "ok":
            status, reason = "error", "balance_audit_failed"
    result = {
        "schema_version": SCHEMA_VERSION, "configuration": c,
        "summary": {"success": status == "ok", "status": status, "stop_reason": reason,
                    "final_time_s": series[-1]["time_s"], "requested_duration_s": duration,
                    "samples": len(series), "rhs_evaluations": evaluations},
        "metadata": {"model_version": MODEL_VERSION,
                     "config_sha256": hashlib.sha256(json.dumps(c, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest(),
                     "provenance": c["provenance"], "simulation_data_kind": "synthetic",
                     "validation_state": "unvalidated_against_plant", "time_convention": "right_continuous",
                     "reference_temperature_K": REFERENCE_TEMPERATURE_K,
                     "numpy_version": np.__version__, "scipy_version": scipy.__version__, "solver": sim["method"]},
        "assumptions": ["Un líquido monofásico, incompresible y perfectamente mezclado por inventario; Cp/rho constantes comunes.",
                        "Caudales impuestos no negativos; la red no calcula presiones, bomba, válvula ni cambio de sentido.",
                        "Puertos sin inventario, retardo ni pérdidas; la temperatura y el trazador proceden del donante.",
                        "Potencias térmicas netas prescritas y UA constantes; sin reacción, cambio de fase ni dinámica instrumental.",
                        "Energía sensible respecto a 273.15 K; sin energía cinética, potencial ni trabajo de presión.",
                        "La inicialización usa masas, temperaturas y trazador dados; no resuelve un estado estacionario.",
                        "Una corrida completada verifica el problema declarado; no acredita una instalación experimental."],
        "audit": {"max_residual": {name + "_" + unit: float(value) for name, unit, value in zip(names, units, maximum_residual)},
                  "max_relative_residual": dict(zip(names, map(float, maximum_relative))),
                  "max_relative_rate_residual": dict(zip(names, map(float, maximum_rate_relative))),
                  "min_tracer_mass_fraction": min_tracer, "max_tracer_mass_fraction": max_tracer,
                  "scope": "all finite inventories; boundary mass/enthalpy/tracer and external heat",
                  "evaluated_at": "reported_samples_and_segment_endpoints"},
        "events": events, "diagnostics": diagnostics, "series": series,
    }
    json.dumps(result, allow_nan=False)
    return result
