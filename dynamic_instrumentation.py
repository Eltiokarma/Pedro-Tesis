"""Deterministic sensor/actuator equations for the bounded dynamic pilot.

These are explicitly parameterised approximations, not manufacturer models.
The valve position solves a first-order lag with separate opening/closing rate
limits. The sampled PI helper integrates its linear tracking term exactly for
the PREVIOUS held error and measured position; this is not a stability proof.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Mapping


SENSOR_NAMES = ("tank", "wall", "jacket")


def _number(value, name, *, lower=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: finite real number required")
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name}: finite real number required") from exc
    if not math.isfinite(value) or (positive and value <= 0) or (lower is not None and value < lower):
        raise ValueError(f"{name}: value outside its finite physical domain")
    return value


def _keys(value, expected, name):
    if not isinstance(value, Mapping) or set(value) != set(expected):
        raise ValueError(f"{name}: requires exactly {sorted(expected)}")


def validate_instrumentation(config, minimum_temperature_K, maximum_temperature_K):
    """Return an independent, strictly validated instrument configuration."""
    _keys(config, {"temperature_sensors", "valve_actuator", "tracking_time_s"}, "instrumentation")
    result = copy.deepcopy(dict(config))
    sensors = result["temperature_sensors"]
    _keys(sensors, SENSOR_NAMES, "instrumentation.temperature_sensors")
    for name in SENSOR_NAMES:
        sensor = sensors[name]
        prefix = f"instrumentation.temperature_sensors.{name}"
        _keys(sensor, {"time_constant_s", "bias_K", "initial_temperature_K"}, prefix)
        sensor["time_constant_s"] = _number(sensor["time_constant_s"], prefix + ".time_constant_s", lower=0)
        sensor["bias_K"] = _number(sensor["bias_K"], prefix + ".bias_K")
        sensor["initial_temperature_K"] = _number(sensor["initial_temperature_K"], prefix + ".initial_temperature_K")
        if not minimum_temperature_K < sensor["initial_temperature_K"] < maximum_temperature_K:
            raise ValueError(prefix + ": initial sensor temperature must lie inside the declared physical domain")
        indicated_range = [bound + sensor["bias_K"] for bound in (minimum_temperature_K, maximum_temperature_K)]
        if any(not math.isfinite(value) or value <= 0 for value in indicated_range):
            raise ValueError(prefix + ": indicated absolute temperature must stay finite and positive")
    actuator = result["valve_actuator"]
    _keys(actuator, {"enabled", "time_constant_s", "opening_rate_per_s", "closing_rate_per_s", "initial_opening"},
          "instrumentation.valve_actuator")
    if not isinstance(actuator["enabled"], bool):
        raise ValueError("instrumentation.valve_actuator.enabled: boolean required")
    for key in ("time_constant_s", "opening_rate_per_s", "closing_rate_per_s"):
        actuator[key] = _number(actuator[key], "instrumentation.valve_actuator." + key, positive=True)
    actuator["initial_opening"] = _number(actuator["initial_opening"], "instrumentation.valve_actuator.initial_opening", lower=0)
    if actuator["initial_opening"] > 1:
        raise ValueError("instrumentation.valve_actuator.initial_opening: fraction in [0,1] required")
    result["tracking_time_s"] = _number(result["tracking_time_s"], "instrumentation.tracking_time_s", positive=True)
    return result


def advance_actuator(initial_opening, command, elapsed_s, config):
    """Exact position for a constant command over a nonnegative elapsed time.

    dx/dt = clip((command-x)/tau, -closing_rate, opening_rate).
    A large move is linear until its remaining distance is rate*tau, then
    exponential. The solution is monotone; no projection of integrated states
    is used to hide an overshoot. A disabled actuator follows command ideally.
    """
    if not isinstance(config, Mapping):
        raise ValueError("Actuator configuration must be a mapping")
    initial = _number(initial_opening, "initial_opening", lower=0)
    target = _number(command, "command", lower=0)
    elapsed = _number(elapsed_s, "elapsed_s", lower=0)
    if initial > 1 or target > 1:
        raise ValueError("Actuator position and command must be fractions in [0,1]")
    if not isinstance(config.get("enabled"), bool):
        raise ValueError("Actuator enabled must be boolean")
    if not config["enabled"]:
        return target
    tau = _number(config["time_constant_s"], "time_constant_s", positive=True)
    delta = target - initial
    if elapsed == 0 or delta == 0:
        return initial
    direction = 1.0 if delta > 0 else -1.0
    rate = _number(config["opening_rate_per_s" if delta > 0 else "closing_rate_per_s"], "stroke_rate", positive=True)
    distance = abs(delta)
    transition_distance = rate * tau
    if distance <= transition_distance:
        return initial + delta * (-math.expm1(-elapsed / tau))
    transition_time = (distance - transition_distance) / rate
    if elapsed <= transition_time:
        return initial + direction * rate * elapsed
    return target - direction * transition_distance * math.exp(-(elapsed - transition_time) / tau)


def tracking_integral_update(integral, error, actual_opening, bias, kp, ki, elapsed_s, tracking_time_s):
    """Exact linear tracking update for previous sampled/held error and position.

    I' = ki*error + (actual_opening-bias-kp*error-I)/tracking_time_s.
    The caller must evolve this state BEFORE evaluating a new setpoint/error;
    using the newly observed error would integrate an event retroactively.
    """
    values = [_number(value, name) for value, name in (
        (integral, "integral"), (error, "error"), (actual_opening, "actual_opening"),
        (bias, "bias"), (kp, "kp"), (ki, "ki"))]
    integral, error, position, bias, kp, ki = values
    elapsed = _number(elapsed_s, "elapsed_s", lower=0)
    tracking = _number(tracking_time_s, "tracking_time_s", positive=True)
    if elapsed == 0:
        return integral
    ratio = elapsed / tracking
    weight = -math.expm1(-ratio)
    # The equivalent integral coefficient is <= min(elapsed, tracking). This
    # ordering avoids forming a huge tracking*ki*error target unnecessarily.
    integration_time = elapsed if ratio == 0 else tracking * weight
    updated = ((1.0 - weight) * integral + weight * (position - bias - kp * error)
               + integration_time * ki * error)
    if not math.isfinite(updated):
        raise FloatingPointError("Nonfinite PI tracking state; review gains and scales")
    return updated
