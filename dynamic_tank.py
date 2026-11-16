"""Conservative transient pilot: mixed liquid tank, wall and water jacket.

This deliberately bounded model uses specified constant liquid properties. It
does not predict boiling, pressure dynamics, reactions or pump cavitation. A
successful integration does not establish empirical validity; numerical correctness
requires separate verification.
All public quantities are SI, temperatures absolute kelvin and times seconds.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
import scipy
from scipy.integrate import solve_ivp

from dynamic_hydraulics import solve_circuit
from dynamic_instrumentation import (
    SENSOR_NAMES, advance_actuator, tracking_integral_update, validate_instrumentation,
)

SCHEMA_VERSION = "dynamic-tank/v1"
INSTRUMENTED_SCHEMA_VERSION = "dynamic-tank/v2"
MODEL_VERSION = "1.1.0"
REFERENCE_TEMPERATURE_K = 273.15
MAX_SAMPLES = 50000
MAX_SEGMENTS = 50000
MAX_RHS_EVALUATIONS = 500000


def default_case() -> dict[str, Any]:
    """Return an editable synthetic case, not manufacturer or plant data."""
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": "synthetic-jacketed-tank",
        "title": "Tanque con camisa de agua: ejemplo sintético",
        "provenance": {
            "data_kind": "synthetic",
            "source": "Parámetros didácticos; no corresponden a un fabricante o planta.",
            "notes": "Requiere identificación de parámetros y validación experimental.",
        },
        "tank": {
            "volume_capacity_m3": 1.0,
            "initial_mass_kg": 500.0,
            "min_mass_kg": 5.0,
            "initial_temperature_K": 298.15,
            "initial_tracer_mass_fraction": 0.0,
            "density_kg_m3": 998.0,
            "cp_J_kg_K": 4180.0,
        },
        "wall": {
            "heat_capacity_J_K": 45000.0,
            "initial_temperature_K": 298.15,
            "ua_tank_W_K": 800.0,
            "ua_jacket_W_K": 1200.0,
            "ua_ambient_W_K": 12.0,
        },
        "jacket": {
            "mass_kg": 35.0,
            "cp_J_kg_K": 4180.0,
            "density_kg_m3": 998.0,
            "initial_temperature_K": 298.15,
            "pump_heat_fraction": 0.0,
        },
        "inputs": {
            "feed_flow_kg_s": 0.0,
            "outlet_flow_kg_s": 0.0,
            "feed_temperature_K": 298.15,
            "feed_tracer_mass_fraction": 0.0,
            "utility_supply_temperature_K": 353.15,
            "ambient_temperature_K": 298.15,
            "agitator_power_W": 100.0,
            "valve_opening": 0.5,
            "temperature_setpoint_K": 323.15,
        },
        "pump": {
            "shutoff_head_m": 18.0,
            "curve_coefficient_s2_m5": 2.0e7,
            "speed_fraction": 1.0,
            "efficiency": 0.65,
            "max_flow_m3_s": 0.001,
        },
        "circuit": {
            "static_head_m": 0.0,
            "resistance_s2_m5": 1.5e7,
            "valve_kv_m3_h": 3.0,
        },
        "controller": {
            "enabled": True,
            "direction": "heating",
            "kp_per_K": 0.06,
            "ki_per_K_s": 0.00015,
            "bias": 0.2,
            "sample_s": 5.0,
        },
        "simulation": {
            "duration_s": 3600.0,
            "output_interval_s": 10.0,
            "max_step_s": 10.0,
            "rtol": 1.0e-7,
            "atol": 1.0e-8,
            "method": "BDF",
            "min_temperature_K": 278.15,
            "max_temperature_K": 363.15,
        },
        "events": [],
    }


def default_instrumented_case() -> dict[str, Any]:
    """Return a synthetic v2 example; instrument parameters need characterisation."""
    case = default_case()
    case["schema_version"] = INSTRUMENTED_SCHEMA_VERSION
    case["case_id"] = "synthetic-instrumented-jacketed-tank"
    case["title"] = "Tanque instrumentado: ejemplo sintético"
    case["instrumentation"] = {
        "temperature_sensors": {
            name: {"time_constant_s": tau, "bias_K": 0.0,
                   "initial_temperature_K": case[name]["initial_temperature_K"]}
            for name, tau in zip(SENSOR_NAMES, (20.0, 10.0, 10.0))
        },
        "valve_actuator": {
            "enabled": True, "time_constant_s": 2.0,
            "opening_rate_per_s": 0.05, "closing_rate_per_s": 0.1,
            "initial_opening": case["inputs"]["valve_opening"],
        },
        "tracking_time_s": 30.0,
    }
    return case


def _number(value: Any, name: str, *, low: float | None = None,
            high: float | None = None, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: se requiere un número real finito.")
    try:
        value = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name}: se requiere un número real finito.") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name}: se requiere un número real finito.")
    if positive and value <= 0:
        raise ValueError(f"{name}: debe ser mayor que cero.")
    if low is not None and value < low:
        raise ValueError(f"{name}: debe ser >= {low}.")
    if high is not None and value > high:
        raise ValueError(f"{name}: debe ser <= {high}.")
    return value


def _keys(value: Any, expected: set[str], name: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name}: se requiere un objeto JSON.")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{name}: las claves deben ser texto.")
    missing, unknown = expected - value.keys(), value.keys() - expected
    if missing or unknown:
        raise ValueError(f"{name}: faltan {sorted(missing)}; claves desconocidas {sorted(unknown)}.")


def validate_case(config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the complete versioned schema without silent defaults/typos."""
    version = config.get("schema_version") if isinstance(config, Mapping) else None
    template = default_instrumented_case() if version == INSTRUMENTED_SCHEMA_VERSION else default_case()
    _keys(config, set(template), "caso")
    c = copy.deepcopy(dict(config))
    if version not in (SCHEMA_VERSION, INSTRUMENTED_SCHEMA_VERSION):
        raise ValueError(f"schema_version: se requiere {SCHEMA_VERSION} o {INSTRUMENTED_SCHEMA_VERSION}.")
    for key in ("case_id", "title"):
        if not isinstance(c[key], str) or not c[key].strip():
            raise ValueError(f"{key}: texto no vacío requerido.")
    for section in ("provenance", "tank", "wall", "jacket", "inputs", "pump", "circuit", "controller", "simulation"):
        _keys(c[section], set(template[section]), section)
    for key, value in c["provenance"].items():
        if not isinstance(value, str):
            raise ValueError(f"provenance.{key}: texto requerido.")
    if c["provenance"]["data_kind"] not in {"synthetic", "measured", "mixed"}:
        raise ValueError("provenance.data_kind: synthetic, measured o mixed.")
    if not c["provenance"]["source"].strip():
        raise ValueError("provenance.source: la procedencia es obligatoria.")
    for section in ("tank", "wall", "jacket", "inputs", "pump", "circuit"):
        for key, value in c[section].items():
            c[section][key] = _number(value, f"{section}.{key}", low=0)
    t, w, j, s, ctrl = (c[key] for key in ("tank", "wall", "jacket", "simulation", "controller"))
    for key in ("volume_capacity_m3", "initial_mass_kg", "min_mass_kg", "density_kg_m3", "cp_J_kg_K"):
        _number(t[key], f"tank.{key}", positive=True)
    _number(t["initial_tracer_mass_fraction"], "tank.initial_tracer_mass_fraction", high=1)
    if not t["min_mass_kg"] < t["initial_mass_kg"] < t["volume_capacity_m3"] * t["density_kg_m3"]:
        raise ValueError("La masa inicial debe estar estrictamente entre mínimo y capacidad del tanque.")
    _number(w["heat_capacity_J_K"], "wall.heat_capacity_J_K", positive=True)
    for key in ("mass_kg", "cp_J_kg_K", "density_kg_m3"):
        _number(j[key], f"jacket.{key}", positive=True)
    _number(j["pump_heat_fraction"], "jacket.pump_heat_fraction", high=1)
    if not isinstance(ctrl["enabled"], bool):
        raise ValueError("controller.enabled: booleano requerido.")
    if ctrl["direction"] not in ("heating", "cooling"):
        raise ValueError("controller.direction: heating o cooling.")
    for key in ("kp_per_K", "ki_per_K_s", "bias", "sample_s"):
        ctrl[key] = _number(ctrl[key], f"controller.{key}", low=0)
    _number(ctrl["bias"], "controller.bias", high=1)
    _number(ctrl["sample_s"], "controller.sample_s", positive=True)
    for key in set(s) - {"method"}:
        s[key] = _number(s[key], f"simulation.{key}", positive=True)
    if s["method"] not in ("BDF", "Radau"):
        raise ValueError("simulation.method: BDF o Radau.")
    if not 1e-12 <= s["rtol"] <= 1e-2 or not 1e-14 <= s["atol"] <= 1e-2:
        raise ValueError("Tolerancias fuera del rango permitido (rtol 1e-12..1e-2; atol 1e-14..1e-2).")
    if s["min_temperature_K"] >= s["max_temperature_K"]:
        raise ValueError("Rango de temperatura vacío.")
    if s["duration_s"] / s["output_interval_s"] > MAX_SAMPLES - 2:
        raise ValueError(f"Demasiadas muestras: máximo {MAX_SAMPLES}.")
    if s["duration_s"] / s["max_step_s"] > MAX_RHS_EVALUATIONS / 10:
        raise ValueError("max_step_s exige demasiados pasos; aumente el paso máximo.")
    n_controls = s["duration_s"] / ctrl["sample_s"] if ctrl["enabled"] else 0
    if n_controls > MAX_SEGMENTS - 2:
        raise ValueError("Demasiadas actualizaciones del controlador.")
    lo, hi = s["min_temperature_K"], s["max_temperature_K"]
    for section in ("tank", "wall", "jacket"):
        value = c[section]["initial_temperature_K"]
        if not lo < value < hi:
            raise ValueError(f"{section}.initial_temperature_K debe estar dentro del rango abierto de propiedades.")
    if version == INSTRUMENTED_SCHEMA_VERSION:
        c["instrumentation"] = validate_instrumentation(c["instrumentation"], lo, hi)

    def check_inputs(inputs: Mapping[str, Any], name: str) -> None:
        for key, value in inputs.items():
            _number(value, f"{name}.{key}", low=0)
            if key.endswith("temperature_K") or key == "temperature_setpoint_K":
                _number(value, f"{name}.{key}", low=lo, high=hi)
            if key in ("valve_opening", "feed_tracer_mass_fraction"):
                _number(value, f"{name}.{key}", high=1)

    check_inputs(c["inputs"], "inputs")
    if not isinstance(c["events"], list) or len(c["events"]) > 10000:
        raise ValueError("events: lista de hasta 10000 cambios requerida.")
    previous = 0.0
    for idx, event in enumerate(c["events"]):
        _keys(event, {"time_s", "changes"}, f"events[{idx}]")
        time = _number(event["time_s"], f"events[{idx}].time_s", positive=True, high=s["duration_s"])
        if time <= previous:
            raise ValueError("Los eventos deben estar ordenados con tiempos únicos mayores que cero.")
        previous = time
        changes = event["changes"]
        if not isinstance(changes, Mapping) or not changes or set(changes) - set(c["inputs"]):
            raise ValueError(f"events[{idx}].changes: requiere claves válidas de inputs.")
        if ctrl["enabled"] and "valve_opening" in changes:
            raise ValueError("No se puede imponer apertura manual con el controlador habilitado.")
        check_inputs(changes, f"events[{idx}].changes")
    if len(c["events"]) + n_controls > MAX_SEGMENTS - 2:
        raise ValueError("Demasiados segmentos temporales.")
    if math.ceil(s["duration_s"] / s["output_interval_s"]) + math.ceil(n_controls) + len(c["events"]) + 2 > MAX_SAMPLES:
        raise ValueError(f"La combinación de muestras, control y eventos excede {MAX_SAMPLES} puntos.")
    # The hydraulics module validates pump/circuit units, ranges and finite values.
    solve_circuit(c["pump"], c["circuit"], c["inputs"]["valve_opening"], j["density_kg_m3"])
    if version == INSTRUMENTED_SCHEMA_VERSION and c["instrumentation"]["valve_actuator"]["enabled"]:
        solve_circuit(c["pump"], c["circuit"], c["instrumentation"]["valve_actuator"]["initial_opening"],
                      j["density_kg_m3"])
    # Finite scalar inputs can still overflow derived capacities, energies and
    # external fluxes. Reject these configurations before creating a trajectory.
    temperature_scale = max(abs(lo - REFERENCE_TEMPERATURE_K), abs(hi - REFERENCE_TEMPERATURE_K), 1.)
    derived = [t["volume_capacity_m3"] * t["density_kg_m3"],
               t["initial_mass_kg"] * t["cp_J_kg_K"] * temperature_scale,
               w["heat_capacity_J_K"] * temperature_scale,
               j["mass_kg"] * j["cp_J_kg_K"] * temperature_scale,
               (w["ua_tank_W_K"] + w["ua_jacket_W_K"] + w["ua_ambient_W_K"]) * (hi - lo),
               ctrl["kp_per_K"] * (hi - lo), ctrl["ki_per_K_s"] * (hi - lo) * ctrl["sample_s"]]
    if version == INSTRUMENTED_SCHEMA_VERSION:
        bias = c["instrumentation"]["temperature_sensors"]["tank"]["bias_K"]
        indicated_error_bound = hi - lo + abs(bias)
        derived.extend((indicated_error_bound, ctrl["kp_per_K"] * indicated_error_bound,
                        ctrl["ki_per_K_s"] * indicated_error_bound * ctrl["sample_s"]))
    for values in [c["inputs"]] + [e["changes"] for e in c["events"]]:
        for key in ("feed_flow_kg_s", "outlet_flow_kg_s"):
            if key in values:
                derived.append(values[key] * t["cp_J_kg_K"] * temperature_scale)
        if "agitator_power_W" in values:
            derived.append(values["agitator_power_W"] * s["duration_s"])
    if not all(math.isfinite(v) for v in derived) or not math.isfinite(sum(derived)):
        raise ValueError("Los parámetros generan capacidades, energías o flujos no finitos.")
    return c


class _Cancelled(Exception):
    pass


class _WorkLimit(Exception):
    pass


def simulate_dynamic_tank(config: Mapping[str, Any], cancel: Callable[[], bool] | None = None,
                          *, sample_times_s: list[float] | tuple[float, ...] | None = None) -> dict[str, Any]:
    """Integrate the pilot and return JSON-safe trajectories and balance audits.

    Invalid configuration raises ValueError. Physical boundaries, cancellation
    and numerical failure return success=False plus the completed trajectory.
    v1 controllers retain conditional-integration anti-windup. v2 uses the
    indicated tank temperature and sampled external-reset tracking.
    Optional sample times augment the usual output grid using the integrator's
    dense interpolant. They do not restart integration or change the dynamics.
    """
    c = validate_case(config)
    tcfg, wall, jacket, sim, controller = (c[k] for k in ("tank", "wall", "jacket", "simulation", "controller"))
    instrumentation = c.get("instrumentation")
    sensors = instrumentation["temperature_sensors"] if instrumentation else None
    actuator = instrumentation["valve_actuator"] if instrumentation else None
    requested_samples = []
    if sample_times_s is not None:
        if not isinstance(sample_times_s, (list, tuple)) or len(sample_times_s) > MAX_SAMPLES:
            raise ValueError(f"sample_times_s: lista ordenada de hasta {MAX_SAMPLES} tiempos requerida.")
        for value in sample_times_s:
            sample = _number(value, "sample_times_s", low=0, high=sim["duration_s"])
            if requested_samples and sample <= requested_samples[-1]:
                raise ValueError("sample_times_s: tiempos estrictamente crecientes y únicos requeridos.")
            requested_samples.append(sample)
    planned_samples = {0., sim["duration_s"], *requested_samples,
                       *np.arange(0, sim["duration_s"], sim["output_interval_s"]),
                       *(event["time_s"] for event in c["events"])}
    if controller["enabled"]:
        planned_samples.update(np.arange(0, sim["duration_s"], controller["sample_s"]))
    if len(planned_samples) > MAX_SAMPLES:
        raise ValueError(f"Las muestras solicitadas y las del caso exceden {MAX_SAMPLES} puntos.")
    inputs = dict(c["inputs"])
    cp, rho = tcfg["cp_J_kg_K"], tcfg["density_kg_m3"]
    cw, cj = wall["heat_capacity_J_K"], jacket["mass_kg"] * jacket["cp_J_kg_K"]
    tref = REFERENCE_TEMPERATURE_K
    m0 = tcfg["initial_mass_kg"]
    y0 = np.array([m0, m0 * cp * (tcfg["initial_temperature_K"] - tref),
                   m0 * tcfg["initial_tracer_mass_fraction"],
                   cw * (wall["initial_temperature_K"] - tref),
                   cj * (jacket["initial_temperature_K"] - tref), 0., 0., 0., 0., 0., 0.])
    # Ideal sensors are algebraic and add no numerical state. This also keeps
    # the all-ideal v2 open-loop model identical to the v1 integration.
    sensor_indices = {}
    if sensors:
        for name in SENSOR_NAMES:
            if sensors[name]["time_constant_s"] > 0:
                sensor_indices[name] = len(y0)
                y0 = np.append(y0, sensors[name]["initial_temperature_K"])
    y = y0.copy()
    events: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    series: list[dict[str, float]] = []
    status, stop_reason = "ok", "duration_reached"
    valve = inputs["valve_opening"]
    actuator_start = actuator["initial_opening"] if actuator else valve
    actuator_start_time = 0.0
    integral = 0.0
    last_control = 0.0
    previous_error = 0.0
    previous_position = actuator_start
    rhs_evaluations = 0
    time_now = 0.0
    max_mass_error = max_tracer_error = max_energy_error = 0.0
    max_mass_relative = max_tracer_relative = max_energy_relative = 0.0
    min_tracer_fraction = max_tracer_fraction = tcfg["initial_tracer_mass_fraction"]
    # A tolerance, not a projection: preserve raw integrated states and disclose
    # round-off excursions. Larger excursions make the numerical run invalid.
    tracer_tolerance = max(10 * sim["rtol"], 10 * sim["atol"] / tcfg["min_mass_kg"], 1e-12)

    def temperatures(state: np.ndarray) -> tuple[float, float, float]:
        # Solver trial stages may cross a terminal mass boundary; the guard is
        # outside the admitted domain and never accepted as a physical state.
        mass_for_trial = max(float(state[0]), tcfg["min_mass_kg"] * 0.01)
        return (tref + state[1] / (mass_for_trial * cp), tref + state[3] / cw, tref + state[4] / cj)

    def sensor_temperatures(state: np.ndarray) -> tuple[float, float, float]:
        physical = temperatures(state)
        return tuple(float(state[sensor_indices[name]]) if name in sensor_indices else physical[i]
                     for i, name in enumerate(SENSOR_NAMES))

    def actual_position(time: float) -> float:
        if actuator is None:
            return valve
        return advance_actuator(actuator_start, valve, time - actuator_start_time, actuator)

    def update_controller(time: float, state: np.ndarray) -> None:
        nonlocal valve, integral, last_control, previous_error, previous_position
        if not controller["enabled"]:
            valve = inputs["valve_opening"]
            return
        sign = 1.0 if controller["direction"] == "heating" else -1.0
        measured = (sensor_temperatures(state)[0] + sensors["tank"]["bias_K"]
                    if sensors else temperatures(state)[0])
        error = sign * (inputs["temperature_setpoint_K"] - measured)
        if instrumentation:
            integral = tracking_integral_update(
                integral, previous_error, previous_position, controller["bias"],
                controller["kp_per_K"], controller["ki_per_K_s"], time - last_control,
                instrumentation["tracking_time_s"],
            )
            previous_error = error
        else:
            proposed = integral + controller["ki_per_K_s"] * error * (time - last_control)
            trial = controller["bias"] + controller["kp_per_K"] * error + proposed
            if not ((trial > 1 and error > 0) or (trial < 0 and error < 0)):
                integral = proposed
        raw = controller["bias"] + controller["kp_per_K"] * error + integral
        valve = min(1.0, max(0.0, raw))
        if instrumentation:
            # A dynamic actuator is continuous; an ideal actuator jumps to the
            # new command here. Hold the effective position for the upcoming
            # sample interval, not an extra one-sample-old ideal position.
            previous_position = actual_position(time)
        events.append({"time_s": float(time), "kind": "controller_sample", "valve_opening": float(valve),
                       "error_K": float(error), "integral": float(integral), "saturated": bool(raw < 0 or raw > 1)})
        if instrumentation:
            events[-1].update(valve_command=float(valve), valve_opening=float(previous_position),
                              indicated_temperature_K=float(measured),
                              tracking="previous_sample_error_and_position_zero_order_hold")
        last_control = time

    def hydraulics(time: float = 0.0) -> dict[str, Any]:
        return solve_circuit(c["pump"], c["circuit"], actual_position(time), jacket["density_kg_m3"])

    hydro: dict[str, Any] = {}

    def fluxes(time: float, state: np.ndarray) -> tuple[float, ...]:
        current_hydro = hydraulics(time) if instrumentation else hydro
        temp, tw, tj = temperatures(state)
        z = state[2] / max(float(state[0]), tcfg["min_mass_kg"] * 0.01)
        feed, outlet = inputs["feed_flow_kg_s"], inputs["outlet_flow_kg_s"]
        qtw = wall["ua_tank_W_K"] * (tw - temp)
        qjw = wall["ua_jacket_W_K"] * (tj - tw)
        qamb = wall["ua_ambient_W_K"] * (tw - inputs["ambient_temperature_K"])
        hin = feed * cp * (inputs["feed_temperature_K"] - tref)
        hout = outlet * cp * (temp - tref)
        utility_heat = current_hydro["mass_flow_kg_s"] * jacket["cp_J_kg_K"] * (inputs["utility_supply_temperature_K"] - tj)
        pump_heat = jacket["pump_heat_fraction"] * current_hydro["shaft_power_W"]
        agitator = inputs["agitator_power_W"]
        return feed, outlet, z, qtw, qjw, qamb, hin, hout, utility_heat, pump_heat, agitator

    def rhs(time: float, state: np.ndarray) -> np.ndarray:
        nonlocal rhs_evaluations
        rhs_evaluations += 1
        if cancel is not None and cancel():
            raise _Cancelled()
        if rhs_evaluations > MAX_RHS_EVALUATIONS:
            raise _WorkLimit()
        feed, outlet, z, qtw, qjw, qamb, hin, hout, qu, qp, qa = fluxes(time, state)
        dmass = feed - outlet
        dtracer = feed * inputs["feed_tracer_mass_fraction"] - outlet * z
        dext = hin - hout + qu + qp + qa - qamb
        derivative = np.array([dmass, hin - hout + qtw + qa, dtracer, qjw - qtw - qamb,
                         qu - qjw + qp, dmass, dtracer, dext, feed + outlet,
                         feed * inputs["feed_tracer_mass_fraction"] + outlet * abs(z),
                         abs(hin) + abs(hout) + abs(qu) + abs(qp) + abs(qa) + abs(qamb)])
        if sensor_indices:
            physical = dict(zip(SENSOR_NAMES, temperatures(state)))
            derivative = np.append(derivative, [
                (physical[name] - state[index]) / sensors[name]["time_constant_s"]
                for name, index in sensor_indices.items()
            ])
        if not np.all(np.isfinite(derivative)):
            raise FloatingPointError("Derivadas no finitas; revise escalas y parámetros.")
        return derivative

    def record(time: float, state: np.ndarray) -> None:
        nonlocal max_mass_error, max_tracer_error, max_energy_error
        nonlocal max_mass_relative, max_tracer_relative, max_energy_relative
        nonlocal min_tracer_fraction, max_tracer_fraction
        temp, tw, tj = temperatures(state)
        mass_error = float(state[0] - y0[0] - state[5])
        tracer_error = float(state[2] - y0[2] - state[6])
        energy = float(state[1] + state[3] + state[4])
        energy_error = energy - float(y0[1] + y0[3] + y0[4]) - float(state[7])
        mass_scale = max(1., float(y0[0]), float(state[8]))
        tracer_scale = max(1e-12, float(y0[2]), float(state[9]))
        energy_scale = max(1., abs(float(y0[1] + y0[3] + y0[4])), float(state[10]))
        max_mass_error = max(max_mass_error, abs(mass_error))
        max_tracer_error = max(max_tracer_error, abs(tracer_error))
        max_energy_error = max(max_energy_error, abs(energy_error))
        max_mass_relative = max(max_mass_relative, abs(mass_error) / mass_scale)
        max_tracer_relative = max(max_tracer_relative, abs(tracer_error) / tracer_scale)
        max_energy_relative = max(max_energy_relative, abs(energy_error) / energy_scale)
        tracer_fraction = float(state[2] / state[0])
        min_tracer_fraction = min(min_tracer_fraction, tracer_fraction)
        max_tracer_fraction = max(max_tracer_fraction, tracer_fraction)
        *_, qu, qp, qa = fluxes(time, state)
        current_hydro = hydraulics(time) if instrumentation else hydro
        row = {"time_s": float(time), "tank_temperature_K": float(temp), "wall_temperature_K": float(tw),
               "jacket_temperature_K": float(tj), "mass_kg": float(state[0]), "volume_m3": float(state[0] / rho),
               "tracer_mass_fraction": tracer_fraction, "tracer_mass_kg": float(state[2]),
               "valve_opening": float(actual_position(time)), "utility_flow_kg_s": float(current_hydro["mass_flow_kg_s"]),
               "pump_head_m": float(current_hydro["pump_head_m"]), "pump_shaft_power_W": float(current_hydro["shaft_power_W"]),
               "utility_heat_W": float(qu), "pump_heat_to_jacket_W": float(qp),
               "total_stored_energy_J": energy, "cumulative_net_energy_J": float(state[7]),
               "cumulative_net_mass_kg": float(state[5]), "cumulative_net_tracer_kg": float(state[6]),
               "mass_balance_error_kg": mass_error, "tracer_balance_error_kg": tracer_error,
               "energy_balance_error_J": float(energy_error),
               "temperature_setpoint_K": float(inputs["temperature_setpoint_K"]),
               "feed_flow_kg_s": float(inputs["feed_flow_kg_s"]), "outlet_flow_kg_s": float(inputs["outlet_flow_kg_s"]),
               "feed_temperature_K": float(inputs["feed_temperature_K"]),
               "feed_tracer_mass_fraction": float(inputs["feed_tracer_mass_fraction"]),
               "utility_supply_temperature_K": float(inputs["utility_supply_temperature_K"])}
        if sensors:
            for name, sensor_temperature in zip(SENSOR_NAMES, sensor_temperatures(state)):
                row[name + "_sensor_temperature_K"] = float(sensor_temperature)
                row[name + "_indicated_temperature_K"] = float(sensor_temperature + sensors[name]["bias_K"])
            row["valve_command"] = float(valve)
        if series and series[-1]["time_s"] == float(time):
            series[-1] = row  # right-continuous control/input convention
        else:
            series.append(row)

    boundaries: list[Callable] = []
    boundary_names: list[str] = []

    def boundary(name: str, fun: Callable) -> None:
        fun.terminal = True
        fun.direction = -1
        boundaries.append(fun)
        boundary_names.append(name)

    boundary("minimum_inventory", lambda time, state: state[0] - tcfg["min_mass_kg"])
    boundary("tank_capacity", lambda time, state: tcfg["volume_capacity_m3"] * rho - state[0])
    for idx, name in enumerate(("tank", "wall", "jacket")):
        boundary(name + "_temperature_low", lambda time, state, i=idx: temperatures(state)[i] - sim["min_temperature_K"])
        boundary(name + "_temperature_high", lambda time, state, i=idx: sim["max_temperature_K"] - temperatures(state)[i])
    if actuator and actuator["enabled"] and c["pump"]["max_flow_m3_s"] * c["pump"]["speed_fraction"] > 0:
        # A moving valve can leave the supplied pump curve between scheduled
        # events. This continuous root stops the accepted trajectory at its edge.
        boundary("pump_curve_domain", lambda time, state:
                 c["pump"]["max_flow_m3_s"] * c["pump"]["speed_fraction"] * (1 + 1e-12)
                 - hydraulics(time)["flow_m3_s"])

    duration = sim["duration_s"]
    output_times = sorted({*np.arange(0, duration, sim["output_interval_s"]),
                           duration, *requested_samples})
    control_times = list(np.arange(0, duration, controller["sample_s"])) if controller["enabled"] else []
    changes_by_time = {float(e["time_s"]): dict(e["changes"]) for e in c["events"]}
    control_set = set(float(time) for time in control_times)
    # Integration is restarted only at discontinuities/control samples. Output
    # sampling uses the dense interpolant and never modifies the dynamics.
    stops = sorted({0., duration, *control_set, *changes_by_time})
    output_index = 1
    update_controller(0., y)
    hydro = hydraulics(0.0)
    record(0., y)
    if not hydro["operating_point_valid"]:
        status, stop_reason = "limit", "pump_curve_domain"
        events.append({"time_s": 0., "kind": "terminal_limit", "reason": stop_reason})
    elif cancel is not None and cancel():
        status, stop_reason = "cancelled", "user_cancelled"
    else:
        for end in stops[1:]:
            start = time_now
            if end <= start:
                continue
            try:
                solution = solve_ivp(rhs, (start, end), y, method=sim["method"], rtol=sim["rtol"],
                                     atol=sim["atol"], max_step=sim["max_step_s"], events=boundaries, dense_output=True)
            except _Cancelled:
                status, stop_reason = "cancelled", "user_cancelled"
                break
            except _WorkLimit:
                status, stop_reason = "error", "evaluation_budget_exceeded"
                break
            except (ValueError, FloatingPointError, OverflowError) as exc:
                status, stop_reason = "error", "integration_failed"
                diagnostics.append(f"{type(exc).__name__}: {exc}")
                break
            time_now = float(solution.t[-1])
            y = solution.y[:, -1]
            if not np.all(np.isfinite(y)):
                status, stop_reason = "error", "nonfinite_state"
                time_now, y = start, solution.y[:, 0]
                break
            if instrumentation:
                hydro = hydraulics(time_now)
            while output_index < len(output_times) and output_times[output_index] <= time_now:
                sample = float(output_times[output_index])
                record(sample, solution.sol(sample))
                output_index += 1
            if solution.status == 1:
                hit = next(i for i, values in enumerate(solution.t_events) if len(values))
                status, stop_reason = "limit", boundary_names[hit]
                events.append({"time_s": time_now, "kind": "terminal_limit", "reason": stop_reason})
                record(time_now, y)
                break
            if not solution.success:
                status, stop_reason = "error", "integration_failed"
                diagnostics.append(str(solution.message))
                record(time_now, y)
                break
            # Close the old constant-command interval before a command change.
            # This is also done for non-command events, preserving continuity.
            actuator_start = actual_position(time_now)
            actuator_start_time = time_now
            if end in changes_by_time:
                inputs.update(changes_by_time[end])
                events.append({"time_s": time_now, "kind": "input_change", "changes": changes_by_time[end]})
                if not controller["enabled"]:
                    update_controller(time_now, y)
            if end in control_set:
                update_controller(time_now, y)
            hydro = hydraulics(time_now)
            # Keep changes and control actions in the trajectory even if they
            # fall between regular output times. Values are right-continuous.
            record(time_now, y)
            if not hydro["operating_point_valid"]:
                status, stop_reason = "limit", "pump_curve_domain"
                events.append({"time_s": time_now, "kind": "terminal_limit", "reason": stop_reason})
                break
    if hydro.get("warnings"):
        diagnostics.extend(str(item) for item in hydro["warnings"])
    if min_tracer_fraction < 0 or max_tracer_fraction > 1:
        diagnostics.append(f"Fracción numérica de trazador fuera de [0,1]: mínimo={min_tracer_fraction:.6g}, "
                           f"máximo={max_tracer_fraction:.6g}; tolerancia absoluta={tracer_tolerance:.6g}. "
                           "Se conservan los estados calculados sin recortes silenciosos.")
        if min_tracer_fraction < -tracer_tolerance or max_tracer_fraction > 1 + tracer_tolerance:
            if status == "ok":
                status, stop_reason = "error", "tracer_bounds_exceeded"
    if max(max_mass_relative, max_tracer_relative, max_energy_relative) > max(100 * sim["rtol"], 1e-7):
        diagnostics.append("Los residuos de conservación superan la tolerancia de auditoría.")
        if status == "ok":
            status, stop_reason = "error", "balance_audit_failed"
    payload = {
        "schema_version": c["schema_version"],
        "configuration": c,
        "summary": {"success": status == "ok", "status": status, "stop_reason": stop_reason,
                    "final_time_s": time_now, "requested_duration_s": duration, "samples": len(series),
                    "rhs_evaluations": rhs_evaluations},
        "metadata": {"model_version": MODEL_VERSION, "case_id": c["case_id"], "title": c["title"],
                     "config_sha256": hashlib.sha256(json.dumps(c, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest(),
                     "provenance": c["provenance"], "validation_state": "unvalidated_against_plant",
                     "simulation_data_kind": "synthetic", "reference_temperature_K": tref,
                     "numpy_version": np.__version__, "scipy_version": scipy.__version__,
                     "controller": "sampled_PI_conditional_antiwindup", "time_convention": "right_continuous",
                     "solver": sim["method"], "rtol": sim["rtol"], "atol": sim["atol"]},
        "assumptions": ["Líquido monofásico incompresible, mezcla perfecta y propiedades rho/Cp constantes especificadas.",
                        "Sin reacción, evaporación, dinámica de presión ni energía cinética/potencial de inventarios.",
                        "Trazador pasivo: su fracción no modifica densidad ni capacidad calorífica.",
                        "Caudales de proceso impuestos; camisa con inventario fijo y fuente térmica externa a temperatura prescrita.",
                        "Bomba y válvula cuasiestacionarias; no se comprueba NPSH, cavitación ni flujo inverso.",
                        "UA constantes y pared térmica concentrada; no se extrapola fuera del intervalo de temperaturas declarado.",
                        "pump_heat_fraction indica la fracción de potencia de eje disipada en la camisa; el resto queda fuera de la frontera modelada.",
                        "La conservación numérica no establece exactitud experimental ni habilita control de planta."],
        "diagnostics": diagnostics,
        "events": events,
        "audit": {"max_mass_residual_kg": max_mass_error, "max_tracer_residual_kg": max_tracer_error,
                  "max_energy_residual_J": max_energy_error, "max_mass_residual_relative": max_mass_relative,
                  "max_tracer_residual_relative": max_tracer_relative, "max_energy_residual_relative": max_energy_relative,
                  "min_tracer_mass_fraction": min_tracer_fraction, "max_tracer_mass_fraction": max_tracer_fraction,
                  "tracer_fraction_absolute_tolerance": tracer_tolerance,
                  "scope": "tank+wall+jacket; integrated external fluxes", "evaluated_at": "reported_samples_and_segment_endpoints"},
        "series": series,
    }
    if instrumentation:
        payload["metadata"].update(
            controller="sampled_PI_external_reset_previous_sample_hold",
            controller_feedback="tank_indicated_temperature_K",
            actuator="exact_constant_command_first_order_with_asymmetric_rate_limits",
            sensor_model="noninvasive_first_order_state_plus_constant_bias",
        )
        payload["assumptions"][4] = (
            "Hidráulica cuasiestacionaria con posición real de válvula; actuador de primer orden con "
            "velocidades de apertura/cierre limitadas. Sin NPSH, cavitación ni flujo inverso."
        )
        payload["assumptions"].extend([
            "Sensores no invasivos: sus estados no añaden inventario energético al equipo; sin ruido ni tiempo muerto puro.",
            "Lecturas indicadas = estado del sensor + sesgo especificado; los límites físicos usan temperaturas del equipo.",
            "PI discreto: tracking integrado exactamente con error y posición de la muestra anterior retenidos; "
            "no se garantiza estabilidad del lazo ni se modelan banda muerta, histéresis o stiction.",
        ])
    if sample_times_s is not None:
        payload["metadata"].update(
            requested_sample_times_s=requested_samples,
            sampling="solver_dense_output_with_exact_input_and_control_boundaries",
        )
    json.dumps(payload, allow_nan=False)
    return payload
