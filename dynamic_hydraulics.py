"""Quasi-steady, single-liquid pump / pipe / control-valve circuit.

SI units are used except for the conventional valve Kv in m3/h at 1 bar
pressure drop for reference water (1000 kg/m3).  The pump curve is
``H = H0 * speed_fraction**2 - k_pump * Q**2``.  Both H0 and the maximum
validated flow are specified at speed_fraction=1; affinity laws scale that
flow limit linearly with speed.  The pump curve is an input, not a vendor
certification or an inferred industrial operating envelope.

The valve has a *linear inherent characteristic*: its effective Kv is
Kv * opening.  The installed flow is nonlinear because of the circuit.
With SG=rho/1000, dp_bar=SG*(3600*Q/Kv_effective)**2.  Converting pressure
drop to liquid head cancels rho, giving a valve head resistance
``(1e5/(1000*g)) * (3600/Kv_effective)**2``.

This model excludes reverse flow (an ideal check valve is assumed), NPSH,
cavitation, flashing, viscosity corrections and pump/actuator inertia.
Efficiency is a specified constant.  A zero-flow result has zero *useful*
hydraulic/shaft power here; it does not predict real dead-head motor loss
or certify that a pump can operate safely against a closed valve.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from numbers import Real


G_M_S2 = 9.80665
REFERENCE_DENSITY_KG_M3 = 1000.0


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _field(data: Mapping, key: str, prefix: str) -> float:
    if key not in data:
        raise ValueError(f"Missing {prefix}.{key}")
    return _finite_number(data[key], f"{prefix}.{key}")


def solve_circuit(
    pump: dict,
    circuit: dict,
    valve_opening: float,
    rho_kg_m3: float = 998.0,
) -> dict:
    """Intersect the supplied pump curve with static, pipe and valve head.

    ``pump`` requires ``shutoff_head_m >= 0``,
    ``curve_coefficient_s2_m5 > 0``, ``speed_fraction`` in [0, 1],
    ``efficiency`` in (0, 1] and ``max_flow_m3_s > 0``.
    ``circuit`` requires ``static_head_m >= 0``,
    ``resistance_s2_m5 >= 0`` and ``valve_kv_m3_h > 0``.

    Invalid inputs raise ValueError.  A calculated operating point outside
    the supplied flow envelope is returned without clipping, marked
    ``operating_point_valid=False``.  This must not be treated as a validated
    trajectory by a calling dynamic simulator.  ``operating_point_valid``
    refers only to the stated curve envelope and numerical head balance;
    the unmodelled phenomena listed in this module still require checking.

    When a stopped/closed circuit or insufficient pump head gives Q=0,
    an ideal check/isolation valve supports the unmatched static head.
    ``head_balance_residual_m`` therefore applies only to flowing states;
    it is None for blocked states.
    """
    if not isinstance(pump, Mapping) or not isinstance(circuit, Mapping):
        raise ValueError("pump and circuit must be mappings")
    h0 = _field(pump, "shutoff_head_m", "pump")
    kp = _field(pump, "curve_coefficient_s2_m5", "pump")
    speed = _field(pump, "speed_fraction", "pump")
    efficiency = _field(pump, "efficiency", "pump")
    max_flow = _field(pump, "max_flow_m3_s", "pump")
    static_head = _field(circuit, "static_head_m", "circuit")
    pipe_k = _field(circuit, "resistance_s2_m5", "circuit")
    kv = _field(circuit, "valve_kv_m3_h", "circuit")
    opening = _finite_number(valve_opening, "valve_opening")
    rho = _finite_number(rho_kg_m3, "rho_kg_m3")
    if h0 < 0 or kp <= 0 or max_flow <= 0:
        raise ValueError("Pump head must be nonnegative; curve coefficient and max flow must be positive")
    if not 0 <= speed <= 1 or not 0 < efficiency <= 1:
        raise ValueError("Pump speed_fraction must be in [0, 1] and efficiency in (0, 1]")
    if static_head < 0 or pipe_k < 0 or kv <= 0:
        raise ValueError("Static head and pipe resistance must be nonnegative; valve Kv must be positive")
    if not 0 <= opening <= 1 or rho <= 0:
        raise ValueError("valve_opening must be in [0, 1]; density must be positive")

    available_head = h0 * speed * speed
    envelope_max_flow = max_flow * speed
    result = {
        "flow_m3_s": 0.0,
        "mass_flow_kg_s": 0.0,
        "pump_head_m": available_head,
        "hydraulic_power_W": 0.0,
        "shaft_power_W": 0.0,
        "valve_head_m": 0.0,
        "pipe_head_m": 0.0,
        "available_head_m": available_head,
        "maximum_validated_flow_m3_s": envelope_max_flow,
        "head_balance_residual_m": None,
        "operating_point_valid": True,
        "warnings": [],
    }
    if opening == 0:
        result["warnings"].append("Closed valve: zero flow; real dead-head pump losses are not modelled.")
        return result
    if speed == 0:
        result["warnings"].append("Pump stopped: zero forward flow with ideal check valve.")
        return result
    if available_head <= static_head:
        result["warnings"].append("Pump head cannot overcome static head: zero forward flow with ideal check valve.")
        return result

    # Computing the norm of square-root resistances avoids squaring a very
    # large valve resistance before the actual operating flow is known.
    valve_root_k = 3600.0 * math.sqrt(1e5 / (REFERENCE_DENSITY_KG_M3 * G_M_S2)) / kv / opening
    total_root_k = math.hypot(math.sqrt(kp), math.sqrt(pipe_k), valve_root_k)
    if not math.isfinite(total_root_k):
        raise ValueError("Circuit resistance exceeds the supported numerical range")
    net_head = available_head - static_head
    flow = math.sqrt(net_head) / total_root_k
    pipe_head = (math.sqrt(pipe_k) / total_root_k) ** 2 * net_head
    valve_head = (valve_root_k / total_root_k) ** 2 * net_head
    pump_head = static_head + pipe_head + valve_head
    hydraulic_power = rho * G_M_S2 * flow * pump_head
    shaft_power = hydraulic_power / efficiency
    mass_flow = rho * flow
    curve_head = available_head - (math.sqrt(kp) / total_root_k) ** 2 * net_head
    if not all(math.isfinite(v) for v in (flow, mass_flow, pump_head, hydraulic_power, shaft_power)):
        raise ValueError("Hydraulic outputs exceed the supported numerical range")
    result.update({
        "flow_m3_s": flow,
        "mass_flow_kg_s": mass_flow,
        "pump_head_m": pump_head,
        "hydraulic_power_W": hydraulic_power,
        "shaft_power_W": shaft_power,
        "valve_head_m": valve_head,
        "pipe_head_m": pipe_head,
        "head_balance_residual_m": curve_head - pump_head,
    })
    if flow > envelope_max_flow * (1 + 1e-12):
        result["operating_point_valid"] = False
        result["warnings"].append(
            "Calculated flow exceeds the supplied pump-curve envelope at this speed; "
            "the operating point is extrapolated and must not be accepted as validated."
        )
    return result
