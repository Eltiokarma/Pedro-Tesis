"""Assemble distributed exchangers and tanks into one conservative ODE network.

The same finite-volume capacities/conductances as the standalone exchanger are
used. Fluid cells are finite inventories; walls are separate, real solid masses
with their own Cp/rho and no material ports. No sequential time stepping or
output interpolation couples the units: every flux uses the current joint state.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

from dynamic_heat_exchanger import default_case, validate_heat_exchanger, _coefficients
from dynamic_network import (_keys, _items, _identifier, _number, _validate_network_core,
                             _simulate_network_core, MAX_NODES, MAX_EDGES)

SCHEMA_VERSION = "dynamic-network/v2"
MAX_TOTAL_CELLS = 128
MAX_PROFILE_VALUES = 500000
MODEL_FIELDS = ("cells", "flow_arrangement", "geometry", "hot_fluid", "cold_fluid",
                "wall", "heat_transfer", "initial", "provenance")
PORTS = ("hot_in", "hot_out", "cold_in", "cold_out")
BASE_FIELDS = {"schema_version", "case_id", "title", "provenance", "fluid", "nodes",
               "sources", "edges", "heat_links", "ambient_temperature_K", "simulation", "events"}


def component_from_case(identifier, config, *, hot_tracer=0., cold_tracer=0.):
    """Extract equipment and initial state; network edges/events own the inputs.

    Callers deliberately provide the network's schedule. Standalone input,
    simulation and event fields are not accepted inside a connected component.
    """
    c = validate_heat_exchanger(config)
    if c["provenance"]["classification"] == "published_reproduction":
        c["provenance"]["classification"] = "documented_adaptation"
        c["provenance"]["notes"] += " Equipo conectado a una red con fronteras y calendario propios; no reproduce automaticamente el caso publicado completo."
    return {"id": identifier, **{k: copy.deepcopy(c[k]) for k in MODEL_FIELDS},
            "initial_tracer_mass_fraction": {"hot": hot_tracer, "cold": cold_tracer}}


def _public_identifier(value, label):
    identifier = _identifier(value, label)
    if identifier.startswith("dx_"):
        raise ValueError("El prefijo dx_ esta reservado para las celdas internas.")
    return identifier


def prepare_network(config):
    """Return normalized public configuration, validated graph and port mapping."""
    _keys(config, BASE_FIELDS | {"heat_exchangers"}, "red con intercambiadores")
    if config["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Se requiere dynamic-network/v2.")
    c = copy.deepcopy(dict(config))
    _keys(c["fluid"], {"cp_J_kg_K", "density_kg_m3"}, "fluid")
    for key, value in c["fluid"].items():
        c["fluid"][key] = _number(value, "fluid."+key, positive=True)
    _items(c["heat_exchangers"], "heat_exchangers", 8, nonempty=True)
    ids, section_ids = set(), {}
    for section, maximum in (("nodes", MAX_NODES), ("sources", MAX_EDGES),
                             ("edges", MAX_EDGES), ("heat_links", MAX_EDGES)):
        _items(c[section], section, maximum)
        section_ids[section] = set()
        for item in c[section]:
            if not isinstance(item, dict): raise ValueError(section+": objeto requerido.")
            identifier = _public_identifier(item.get("id"), section+".id")
            if identifier in section_ids[section]: raise ValueError("Identificador duplicado: "+identifier)
            section_ids[section].add(identifier)
            if section in ("nodes", "sources"):
                if identifier in ids: raise ValueError("Unidad/frontera duplicada: "+identifier)
                ids.add(identifier)
    expanded = {k: copy.deepcopy(v) for k, v in c.items() if k != "heat_exchangers"}
    expanded["schema_version"] = "dynamic-network/v1"
    mapping, materials, endpoint_map, internal_edges = {}, {}, {}, {}
    total_cells = 0
    for position, component in enumerate(c["heat_exchangers"]):
        _keys(component, {"id", "initial_tracer_mass_fraction", *MODEL_FIELDS}, "intercambiador")
        identifier = _public_identifier(component["id"], "heat_exchanger.id")
        if identifier in ids: raise ValueError("Unidad/frontera duplicada: "+identifier)
        ids.add(identifier)
        model = default_case()
        model.update({k: copy.deepcopy(component[k]) for k in MODEL_FIELDS})
        model["simulation"] = copy.deepcopy(c["simulation"])
        model["inputs"].update(hot_flow_kg_s=0., cold_flow_kg_s=0.,
                               hot_inlet_temperature_K=c["ambient_temperature_K"],
                               cold_inlet_temperature_K=c["ambient_temperature_K"])
        model = validate_heat_exchanger(model)
        for key in MODEL_FIELDS: component[key] = copy.deepcopy(model[key])
        for side in ("hot", "cold"):
            if model[side+"_fluid"] != c["fluid"]:
                raise ValueError(f"{identifier}.{side}: Cp y densidad deben coincidir con el fluido comun de la red.")
        n = model["cells"]
        total_cells += n
        if total_cells > MAX_TOTAL_CELLS: raise ValueError("La red admite hasta 128 celdas de intercambiador en total.")
        _keys(component["initial_tracer_mass_fraction"], {"hot", "cold"}, identifier+".tracer")
        for side, value in component["initial_tracer_mass_fraction"].items():
            values = value if isinstance(value, list) else [value]*n
            if len(values) != n: raise ValueError(identifier+": perfil de trazador de longitud incorrecta.")
            component["initial_tracer_mass_fraction"][side] = [_number(v, "tracer", low=0., high=1.) for v in values]
        capacity, gh, gc, mh, mc = _coefficients(model)
        groups = {side: [f"dx_{position}_{side}_{i}" for i in range(n)] for side in ("hot", "cold", "wall")}
        wall = model["wall"]
        mw_cell = float(capacity[2*n]/wall["cp_J_kg_K"])
        for side, mass in (("hot", mh/n), ("cold", mc/n), ("wall", mw_cell)):
            for i, name in enumerate(groups[side]):
                expanded["nodes"].append({"id": name, "initial_mass_kg": mass, "min_mass_kg": mass/2,
                    "max_mass_kg": mass*2, "initial_temperature_K": model["initial"][side+"_temperature_K"][i],
                    "initial_tracer_mass_fraction": 0. if side == "wall" else component["initial_tracer_mass_fraction"][side][i],
                    "inventory_mode": "fixed", "heat_power_W": 0., "ua_ambient_W_K": 0.})
                if side == "wall":
                    materials[name] = {k: wall[k] for k in ("cp_J_kg_K", "density_kg_m3")}
        for side, conductance in (("hot", gh), ("cold", gc)):
            path = groups[side]
            if side == "cold" and model["flow_arrangement"] == "counter_current": path = list(reversed(path))
            endpoint_map[identifier+"."+side+"_in"] = path[0]
            endpoint_map[identifier+"."+side+"_out"] = path[-1]
            internal_edges[(identifier, side)] = []
            for i, (a, b) in enumerate(zip(path, path[1:])):
                eid = f"dx_{position}_{side}_flow_{i}"
                expanded["edges"].append({"id": eid, "source": a, "target": b, "mass_flow_kg_s": 0.})
                internal_edges[(identifier, side)].append(eid)
            for i in range(n):
                expanded["heat_links"].append({"id": f"dx_{position}_{side}_heat_{i}",
                    "first": groups[side][i], "second": groups["wall"][i], "ua_W_K": conductance})
        mapping[identifier] = {"groups": groups, "model": model, "wall_mass_kg": mw_cell*n,
            "cell_centres_m": [(i+.5)*model["geometry"]["length_m"]/n for i in range(n)],
            "conductances_W_K": {"hot": gh, "cold": gc}}
    samples = model["simulation"]["duration_s"]/model["simulation"]["output_interval_s"] + len(c["events"]) + 2 if isinstance(c["events"], list) else math.inf
    if samples*(5*total_cells + 3*len(c["nodes"])) > MAX_PROFILE_VALUES:
        raise ValueError("Demasiados valores de perfil para la red; aumente el intervalo de salida.")
    outgoing = section_ids["nodes"] | section_ids["sources"] | {p for p in endpoint_map if p.endswith("_out")}
    incoming = section_ids["nodes"] | {p for p in endpoint_map if p.endswith("_in")}
    for edge in c["edges"]:
        _keys(edge, {"id", "source", "target", "mass_flow_kg_s"}, "conexion")
        if not isinstance(edge["source"], str) or edge["source"] not in outgoing:
            raise ValueError(edge["id"]+": origen debe ser tanque, frontera o puerto de salida.")
        if edge["target"] is not None and (not isinstance(edge["target"], str) or edge["target"] not in incoming):
            raise ValueError(edge["id"]+": destino debe ser tanque, puerto de entrada o salida de la red.")
        edge["mass_flow_kg_s"] = _number(edge["mass_flow_kg_s"], edge["id"]+".flow", low=0.)
    # Only tank-to-tank auxiliary heat links are public; exchanger wall links
    # are generated from equipment geometry and cannot be overridden by IDs.
    for link in c["heat_links"]:
        _keys(link, {"id", "first", "second", "ua_W_K"}, "heat_link")
        if any(not isinstance(link[k], str) or link[k] not in section_ids["nodes"] for k in ("first", "second")):
            raise ValueError("Los contactos termicos adicionales conectan tanques.")
    for edge in expanded["edges"][:len(c["edges"])]:
        edge["source"] = endpoint_map.get(edge["source"], edge["source"])
        edge["target"] = endpoint_map.get(edge["target"], edge["target"])
    logical = {edge["id"]: copy.deepcopy(edge) for edge in c["edges"]}

    def channel_changes():
        updates = {}
        for (identifier, side), edge_ids in internal_edges.items():
            entering = math.fsum(e["mass_flow_kg_s"] for e in logical.values() if e["target"] == identifier+"."+side+"_in")
            leaving = math.fsum(e["mass_flow_kg_s"] for e in logical.values() if e["source"] == identifier+"."+side+"_out")
            if abs(entering-leaving) > 1e-12*(entering+leaving):
                raise ValueError(f"{identifier}.{side}: entrada y salida incompatibles con el inventario fijo.")
            updates.update({eid: {"mass_flow_kg_s": entering} for eid in edge_ids})
        return updates

    initial_flows = channel_changes()
    for edge in expanded["edges"]:
        if edge["id"].startswith("dx_"): edge.update(initial_flows[edge["id"]])
    _items(c["events"], "events", 1000)
    expanded["events"] = []
    for event in c["events"]:
        _keys(event, {"time_s", "changes"}, "evento")
        _keys(event["changes"], set(), "evento.changes", optional=("edges", "sources", "nodes"))
        if not event["changes"]: raise ValueError("Evento vacio.")
        for section, updates in event["changes"].items():
            _keys(updates, set(), "evento."+section, optional=section_ids[section])
            if not updates: raise ValueError("Grupo de cambios vacio.")
            if section == "edges":
                for eid, values in updates.items():
                    _keys(values, {"mass_flow_kg_s"}, "evento.edge")
                    values["mass_flow_kg_s"] = _number(values["mass_flow_kg_s"], "evento.flow", low=0.)
                    logical[eid].update(values)
        compiled_event = copy.deepcopy(event)
        updates = channel_changes()
        if updates: compiled_event["changes"].setdefault("edges", {}).update(updates)
        expanded["events"].append(compiled_event)
    # In a one-cell channel its distinct inlet/outlet ports map to one state.
    # A direct return is valid there; ordinary tank self-links remain invalid.
    self_edges = {e["id"] for e in c["edges"] if e["source"] in endpoint_map and e["target"] in endpoint_map
                  and endpoint_map[e["source"]] == endpoint_map[e["target"]]}
    graph = _validate_network_core(expanded, materials=materials,
        max_nodes=MAX_NODES+3*MAX_TOTAL_CELLS, max_edges=MAX_EDGES+2*MAX_TOTAL_CELLS, allow_self_edges=self_edges)
    # Keep normalization of original fields, never expose generated IDs as input.
    for key in ("simulation", "fluid", "ambient_temperature_K", "nodes", "sources", "heat_links"):
        if key in ("nodes", "heat_links"):
            c[key] = [copy.deepcopy(item) for item in graph[key] if not item["id"].startswith("dx_")]
        else: c[key] = copy.deepcopy(graph[key])
    c["events"] = [{"time_s": e["time_s"], "changes": {section: {identifier: values for identifier, values in updates.items()
                  if not identifier.startswith("dx_")} for section, updates in e["changes"].items()
                  if any(not identifier.startswith("dx_") for identifier in updates)}} for e in graph["events"]]
    return c, graph, mapping


def simulate_component_network(config, *, cancel=None):
    c, graph, mapping = prepare_network(config)
    result = _simulate_network_core(graph, cancel=cancel)
    original_nodes = {n["id"] for n in c["nodes"]}
    original_edges = {e["id"]: e for e in c["edges"]}
    for row in result["series"]:
        row["heat_exchangers"] = {}
        for identifier, unit in mapping.items():
            states = {side: [row["nodes"][name] for name in names] for side, names in unit["groups"].items()}
            profiles = {side+"_temperature_K": [s["temperature_K"] for s in values] for side, values in states.items()}
            counter = unit["model"]["flow_arrangement"] == "counter_current"
            profiles.update({side+"_tracer_mass_fraction": [s["tracer_mass_fraction"] for s in states[side]] for side in ("hot", "cold")})
            profiles.update(hot_outlet_temperature_K=profiles["hot_temperature_K"][-1],
                            cold_outlet_temperature_K=profiles["cold_temperature_K"][0 if counter else -1],
                            hot_total_mass_kg=sum(s["mass_kg"] for s in states["hot"]),
                            cold_total_mass_kg=sum(s["mass_kg"] for s in states["cold"]), wall_mass_kg=unit["wall_mass_kg"],
                            energy_J=sum(s["energy_J"] for values in states.values() for s in values),
                            tracer_mass_kg=sum(s["tracer_mass_kg"] for side in ("hot", "cold") for s in states[side]))
            for side in ("hot", "cold"):
                profiles[side+"_to_wall_heat_W"] = unit["conductances_W_K"][side]*sum(a-b for a, b in zip(profiles[side+"_temperature_K"], profiles["wall_temperature_K"]))
            row["heat_exchangers"][identifier] = profiles
        row["nodes"] = {k: v for k, v in row["nodes"].items() if k in original_nodes}
        row["ports"] = [{**p, "source": original_edges[p["id"]]["source"], "target": original_edges[p["id"]]["target"]}
                        for p in row["ports"] if p["id"] in original_edges]
        row["heat_ports"] = [p for p in row["heat_ports"] if not p["id"].startswith("dx_")]
    for event in result["events"]:
        if event["kind"] == "input_change":
            event["changes"] = next(copy.deepcopy(e["changes"]) for e in c["events"] if e["time_s"] == event["time_s"])
    # Translate any physical stop in an internal cell to its equipment label.
    for identifier, unit in mapping.items():
        for side, names in unit["groups"].items():
            for i, name in enumerate(names):
                old, new = name+".", f"{identifier}.{side}[{i}]."
                result["summary"]["stop_reason"] = result["summary"]["stop_reason"].replace(old, new)
                for event in result["events"]:
                    if "reason" in event: event["reason"] = event["reason"].replace(old, new)
    result.update(schema_version=SCHEMA_VERSION, configuration=c)
    result["metadata"].update(model_version="2.0.0", assembly="simultaneous_conservative_finite_volumes",
        config_sha256=hashlib.sha256(json.dumps(c, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest(),
        heat_exchangers={identifier: {"cell_centres_m": unit["cell_centres_m"], "wall_mass_kg": unit["wall_mass_kg"],
                                    "provenance": unit["model"]["provenance"]} for identifier, unit in mapping.items()})
    result["audit"]["scope"] = "all tanks, exchanger fluid cells and real solid wall masses; external boundary ledgers only"
    result["assumptions"][0] = "Un liquido monofasico incompresible; mezcla perfecta en tanques y celdas de fluido, con Cp/rho comunes constantes."
    result["assumptions"].extend(["Intercambiadores distribuidos integrados simultaneamente con los tanques; sin retardo artificial de acoplamiento.",
        "Las paredes son solidos con masa, Cp y densidad propios, sin puertos de materia ni trazador.",
        "Ambos circuitos usan el fluido comun de la red; se rechazan propiedades incompatibles."])
    json.dumps(result, allow_nan=False)
    return result
