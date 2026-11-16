"""Conservative operating-point model of a water / moist-air cooling tower.

Specified outlet temperatures and air flow are design inputs, not a Merkel
capacity prediction. Evaporation follows the first law using the same caloric
reference as the flowsheet. Water partial pressure must remain below saturation.
Drift is neglected; blowdown is an explicit liquid outlet. Pure water only.
"""
import math

import thermo_db
from stream_enthalpy import specific_enthalpy_kJ_kg


def _composition(stream):
    comp = stream.composition or ({stream.main_component: 1.0}
                                  if stream.main_component else {})
    if (not comp or any(not math.isfinite(float(v)) or v < 0 for v in comp.values())
            or abs(sum(comp.values()) - 1) > 1e-7):
        raise ValueError("feed composition must be finite, nonnegative and sum to 1")
    result = {}
    for name, fraction in comp.items():
        obj = thermo_db.get(name)
        if obj is None or obj.mw <= 0:
            raise ValueError(f"unknown component {name!r}")
        result[obj.name] = result.get(obj.name, 0.0) + fraction
    return result


def _h(comp, temperature, phase):
    if not math.isfinite(temperature):
        raise ValueError("temperatures must be finite")
    value = specific_enthalpy_kJ_kg(comp, temperature, phase)
    if value is None or not math.isfinite(value):
        raise ValueError("enthalpy unavailable for specified stream state")
    return value


def water_relative_humidity(comp, temperature, pressure):
    """Water partial pressure / saturation pressure, from mass composition."""
    if not math.isfinite(pressure) or pressure <= 0:
        raise ValueError("air pressure must be finite and positive")
    psat = thermo_db.vapor_pressure_bar("water", temperature)
    if psat is None or psat <= 0:
        raise ValueError("water saturation pressure unavailable at air temperature")
    moles = {name: value / thermo_db.get(name).mw for name, value in comp.items()}
    return pressure * moles.get("water", 0.0) / sum(moles.values()) / psat


def cooling_tower_outputs(block, inputs, outputs):
    """Validate completely before returning conservative outlet component masses."""
    ports = {s.src_port: s for s in outputs}
    if len(ports) != len(outputs) or set(ports) != {"agua_fria", "blowdown", "vapor_loss"}:
        raise ValueError("requires exactly agua_fria, blowdown and vapor_loss outlets")
    cold, blowdown, exhaust = (ports[k] for k in ("agua_fria", "blowdown", "vapor_loss"))
    if any(s.composition_locked for s in outputs) or blowdown.mass_flow_locked or exhaust.mass_flow_locked:
        raise ValueError("outlet compositions and air/blowdown flows must be unlocked")
    if cold.phase != "liquid" or blowdown.phase != "liquid" or exhaust.phase not in {"gas", "vapor"}:
        raise ValueError("cold water and blowdown must be liquid; exhaust must be moist gas")
    if abs(cold.temperature - blowdown.temperature) > 1e-8:
        raise ValueError("blowdown and cold water must share the basin temperature")
    if block.duty != 0:
        raise ValueError("tower model requires zero external heat duty")
    liquid_mass, incoming_h, air_water = 0.0, 0.0, 0.0
    dry_air = {}
    for stream in inputs:
        mass = float(stream.mass_flow)
        if not math.isfinite(mass) or mass < 0:
            raise ValueError("inlet flow must be finite and nonnegative")
        if mass == 0:
            continue
        comp = _composition(stream)
        if stream.phase in {"gas", "vapor"}:
            if set(comp) - {"water", "nitrogen", "oxygen", "argon", "co2"}:
                raise ValueError("gas feed must be atmospheric air and water")
            if water_relative_humidity(comp, stream.temperature, stream.pressure_bar) > 1 + 1e-8:
                raise ValueError("inlet humidity exceeds saturation")
            for name, fraction in comp.items():
                if name == "water":
                    air_water += mass * fraction
                else:
                    dry_air[name] = dry_air.get(name, 0.0) + mass * fraction
            incoming_h += mass * _h(comp, stream.temperature, "gas")
        elif stream.phase == "liquid" and comp == {"water": 1.0}:
            liquid_mass += mass
            incoming_h += mass * _h(comp, stream.temperature, "liquid")
        else:
            raise ValueError("liquid feed must be pure water; dissolved solids are not modeled")
    if not dry_air or liquid_mass <= 0:
        raise ValueError("requires positive liquid-water and dry-air feed")
    h_cold = _h({"water": 1.0}, cold.temperature, "liquid")
    h_vapor = _h({"water": 1.0}, exhaust.temperature, "gas")
    dry_h = sum(mass * _h({name: 1.0}, exhaust.temperature, "gas") for name, mass in dry_air.items())
    if h_vapor <= h_cold:
        raise ValueError("specified temperatures do not permit latent evaporation")
    evaporated = (incoming_h - liquid_mass * h_cold - dry_h - air_water * h_vapor) / (h_vapor - h_cold)
    if not math.isfinite(evaporated) or evaporated < 0:
        raise ValueError("specified air/water states require condensation, not cooling-tower evaporation")
    fraction = block.cooling_tower_blowdown_fraction
    if fraction is None:
        if not cold.mass_flow_locked or not math.isfinite(cold.mass_flow) or cold.mass_flow <= 0:
            raise ValueError("fixed-circulation mode requires positive locked cold-water flow")
        cold_mass = cold.mass_flow
        blowdown_mass = liquid_mass - evaporated - cold_mass
    else:
        if cold.mass_flow_locked:
            raise ValueError("fractional blowdown mode requires unlocked cold-water flow")
        if not math.isfinite(fraction) or not 0 <= fraction < 1:
            raise ValueError("blowdown fraction must be finite and in [0, 1)")
        blowdown_mass = fraction * liquid_mass
        cold_mass = liquid_mass - evaporated - blowdown_mass
    if cold_mass <= 0 or blowdown_mass < 0:
        raise ValueError("insufficient water: evaporation/circulation exceeds makeup and return")
    gas = dict(dry_air)
    gas["water"] = air_water + evaporated
    gas_mass = sum(gas.values())
    gas_comp = {name: mass / gas_mass for name, mass in gas.items()}
    rh = water_relative_humidity(gas_comp, exhaust.temperature, exhaust.pressure_bar)
    if rh > 1 + 1e-8:
        raise ValueError(f"outlet humidity exceeds saturation (RH={rh:.5g}); increase air flow or revise temperatures")
    return {cold.id: {"water": cold_mass}, blowdown.id: {"water": blowdown_mass}, exhaust.id: gas}


def solve_cooling_towers(fs):
    messages = []
    for block in fs.blocks.values():
        if not getattr(block, "cooling_tower_active", False):
            continue
        inputs = [s for s in fs.streams.values() if s.dst == block.id and s.stream_kind == "mass"]
        outputs = [s for s in fs.streams.values() if s.src == block.id and s.stream_kind == "mass"]
        try:
            amounts = cooling_tower_outputs(block, inputs, outputs)
            for stream in outputs:
                mass = sum(amounts[stream.id].values())
                stream.mass_flow = mass
                stream.composition = {k: v / mass for k, v in amounts[stream.id].items() if v > 0} if mass else {}
                stream.main_component = max(stream.composition, key=stream.composition.get) if mass else ""
            messages.append(f"✓ {block.name}: moist-air tower balances (specified outlet temperatures)")
        except (ValueError, TypeError, OverflowError) as exc:
            messages.append(f"✗ Cooling tower {block.name}: {exc}")
    return messages
