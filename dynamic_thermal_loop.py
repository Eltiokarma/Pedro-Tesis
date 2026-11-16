"""Conservative connections for the finite, single-liquid thermal service loop.

These helpers contain no integration or controllers. Positive connection heat
flows from supply to return; the two control volumes receive opposite powers.
All quantities are SI. The reservoir and jacket share the same liquid Cp/rho.
"""
from __future__ import annotations

import math


def advective_exchange(mass_flow_kg_s: float, cp_J_kg_K: float,
                       supply_temperature_K: float,
                       return_temperature_K: float) -> tuple[float, float]:
    """Return (supply power, return power) with exact opposite signs."""
    values = (mass_flow_kg_s, cp_J_kg_K, supply_temperature_K, return_temperature_K)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Thermal connection requires finite quantities")
    if mass_flow_kg_s < 0 or cp_J_kg_K <= 0:
        raise ValueError("Thermal connection requires nonnegative flow and positive Cp")
    heat = mass_flow_kg_s * cp_J_kg_K * (supply_temperature_K - return_temperature_K)
    if not math.isfinite(heat):
        raise ValueError("Thermal connection power exceeds numerical range")
    return -heat, heat


def heater_power(request_W: float, maximum_W: float, efficiency: float) -> dict:
    """A bounded electric heater: the applied electric demand is explicitly capped."""
    if not all(math.isfinite(v) for v in (request_W, maximum_W, efficiency)):
        raise ValueError("Heater requires finite quantities")
    if request_W < 0 or maximum_W < 0 or not 0 < efficiency <= 1:
        raise ValueError("Heater requires nonnegative powers and efficiency in (0,1]")
    applied = min(request_W, maximum_W)
    return {"heater_power_request_W": request_W, "heater_applied_power_W": applied,
            "heater_heat_W": efficiency * applied, "heater_saturated": request_W > maximum_W}


def thermal_reservoir_rates(*, mass_flow_kg_s: float, cp_J_kg_K: float,
                            reservoir_temperature_K: float, return_temperature_K: float,
                            ua_ambient_W_K: float, ambient_temperature_K: float,
                            heater_heat_W: float, pump_heat_W: float) -> dict[str, float]:
    """Energy rates for a mixed finite reservoir and its conservative return port.

    A prescribed return temperature can also exercise this component in isolation;
    a closed-loop caller must obtain it from the connected return control volume.
    """
    values = (ua_ambient_W_K, ambient_temperature_K, heater_heat_W, pump_heat_W)
    if not all(math.isfinite(value) for value in values) or ua_ambient_W_K < 0:
        raise ValueError("Invalid finite reservoir heat inputs")
    supply_heat, return_heat = advective_exchange(mass_flow_kg_s, cp_J_kg_K,
                                                reservoir_temperature_K, return_temperature_K)
    loss = ua_ambient_W_K * (reservoir_temperature_K - ambient_temperature_K)
    rate = supply_heat + heater_heat_W + pump_heat_W - loss
    if not all(math.isfinite(value) for value in (loss, rate)):
        raise ValueError("Reservoir power exceeds numerical range")
    return {"reservoir_energy_rate_W": rate, "return_heat_W": return_heat,
            "ambient_loss_W": loss}


def pump_heat_to_liquid(hydraulic_power_W: float, shaft_power_W: float,
                        loss_to_fluid_fraction: float) -> float:
    """Hydraulic work dissipates in the closed loop; pump shaft losses are partitioned.

    The underlying pump model reports zero useful shaft power at zero flow.
    This expression does not invent unmodelled dead-head motor losses.
    """
    values = (hydraulic_power_W, shaft_power_W, loss_to_fluid_fraction)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Pump heat requires finite quantities")
    if hydraulic_power_W < 0 or shaft_power_W < hydraulic_power_W or not 0 <= loss_to_fluid_fraction <= 1:
        raise ValueError("Invalid pump power or loss allocation")
    heat = hydraulic_power_W + loss_to_fluid_fraction * (shaft_power_W - hydraulic_power_W)
    if not math.isfinite(heat):
        raise ValueError("Pump heat exceeds numerical range")
    return heat
