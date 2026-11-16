"""Independent hydraulic intersections, affinity and invalid-domain checks."""
import copy
import math

import pytest

from dynamic_hydraulics import solve_circuit


def configs():
    return (
        dict(shutoff_head_m=20.0, curve_coefficient_s2_m5=100000.0,
             speed_fraction=1.0, efficiency=0.7, max_flow_m3_s=0.02),
        dict(static_head_m=3.0, resistance_s2_m5=50000.0, valve_kv_m3_h=40.0),
    )


def test_intersection_matches_head_equations_and_energy():
    pump, circuit = configs()
    result = solve_circuit(pump, circuit, 0.6, 950.0)
    valve_k = 1e5 / (1000 * 9.80665) * (3600 / (40 * 0.6)) ** 2
    expected_q = math.sqrt((20 - 3) / (100000 + 50000 + valve_k))
    assert result["flow_m3_s"] == pytest.approx(expected_q)
    assert result["pump_head_m"] == pytest.approx(20 - 100000 * expected_q ** 2)
    assert result["pipe_head_m"] == pytest.approx(50000 * expected_q ** 2)
    # Independently convert the conventional Kv differential pressure.
    dp_valve_pa = (950 / 1000) * (expected_q * 3600 / (40 * 0.6)) ** 2 * 1e5
    assert result["valve_head_m"] == pytest.approx(dp_valve_pa / (950 * 9.80665))
    assert result["pump_head_m"] == pytest.approx(
        3 + result["pipe_head_m"] + result["valve_head_m"])
    assert result["hydraulic_power_W"] == pytest.approx(950 * 9.80665 * expected_q * result["pump_head_m"])
    assert result["shaft_power_W"] == pytest.approx(result["hydraulic_power_W"] / .7)
    assert result["mass_flow_kg_s"] == pytest.approx(950 * expected_q)
    assert result["head_balance_residual_m"] == pytest.approx(0, abs=1e-12)
    assert result["operating_point_valid"]


def test_speed_affinity_at_zero_static_head():
    pump, circuit = configs()
    circuit["static_head_m"] = 0
    full = solve_circuit(pump, circuit, .8)
    pump["speed_fraction"] = .5
    half = solve_circuit(pump, circuit, .8)
    assert half["flow_m3_s"] == pytest.approx(full["flow_m3_s"] / 2)
    assert half["pump_head_m"] == pytest.approx(full["pump_head_m"] / 4)
    assert half["shaft_power_W"] == pytest.approx(full["shaft_power_W"] / 8)
    assert half["maximum_validated_flow_m3_s"] == .01


def test_density_changes_mass_and_power_but_not_head_or_volume():
    pump, circuit = configs()
    dense = solve_circuit(pump, circuit, .7, 1000)
    light = solve_circuit(pump, circuit, .7, 500)
    assert light["flow_m3_s"] == pytest.approx(dense["flow_m3_s"])
    assert light["pump_head_m"] == pytest.approx(dense["pump_head_m"])
    assert light["mass_flow_kg_s"] == pytest.approx(dense["mass_flow_kg_s"] / 2)
    assert light["shaft_power_W"] == pytest.approx(dense["shaft_power_W"] / 2)


@pytest.mark.parametrize("blocked", ["valve", "speed", "static", "equal_head"])
def test_blocked_or_insufficient_head_never_invents_reverse_flow(blocked):
    pump, circuit = configs()
    opening = 1
    if blocked == "valve":
        opening = 0
    elif blocked == "speed":
        pump["speed_fraction"] = 0
    elif blocked == "static":
        circuit["static_head_m"] = 30
    else:
        circuit["static_head_m"] = 20
    result = solve_circuit(pump, circuit, opening)
    assert result["flow_m3_s"] == 0
    assert result["shaft_power_W"] == 0
    assert result["head_balance_residual_m"] is None
    assert result["warnings"]


def test_outside_curve_is_flagged_without_clamping_flow():
    pump, circuit = configs()
    expected = solve_circuit(pump, circuit, 1)["flow_m3_s"]
    pump["max_flow_m3_s"] = expected / 2
    result = solve_circuit(pump, circuit, 1)
    assert result["flow_m3_s"] == expected
    assert not result["operating_point_valid"]
    assert any("extrapolated" in warning for warning in result["warnings"])


def test_closed_and_part_open_valve_characteristic_is_monotone():
    pump, circuit = configs()
    values = [solve_circuit(pump, circuit, x)["flow_m3_s"] for x in (0, .01, .1, .5, 1)]
    assert values == sorted(values)
    assert len(set(values)) == 5


@pytest.mark.parametrize("group,key,value", [
    ("pump", "shutoff_head_m", math.nan),
    ("pump", "shutoff_head_m", -1),
    ("pump", "curve_coefficient_s2_m5", 0),
    ("pump", "curve_coefficient_s2_m5", math.inf),
    ("pump", "speed_fraction", -0.1),
    ("pump", "speed_fraction", 1.1),
    ("pump", "efficiency", 0),
    ("pump", "efficiency", 1.01),
    ("pump", "max_flow_m3_s", 0),
    ("circuit", "static_head_m", -1),
    ("circuit", "resistance_s2_m5", -1),
    ("circuit", "valve_kv_m3_h", 0),
    ("circuit", "valve_kv_m3_h", "40"),
    ("circuit", "valve_kv_m3_h", True),
])
def test_invalid_configuration_is_rejected_even_when_valve_closed(group, key, value):
    pump, circuit = configs()
    (pump if group == "pump" else circuit)[key] = value
    with pytest.raises(ValueError):
        solve_circuit(pump, circuit, 0)


@pytest.mark.parametrize("opening,density", [(math.nan, 998), (math.inf, 998),
    (-.1, 998), (1.1, 998), (True, 998), (.5, 0), (.5, -1), (.5, math.nan)])
def test_invalid_opening_and_density(opening, density):
    pump, circuit = configs()
    with pytest.raises(ValueError):
        solve_circuit(pump, circuit, opening, density)


def test_missing_fields_and_nonmappings_are_rejected():
    pump, circuit = configs()
    del pump["efficiency"]
    with pytest.raises(ValueError, match="Missing pump.efficiency"):
        solve_circuit(pump, circuit, 1)
    with pytest.raises(ValueError, match="mappings"):
        solve_circuit([], circuit, 1)


def test_inputs_are_not_mutated():
    pump, circuit = configs()
    original = copy.deepcopy((pump, circuit))
    solve_circuit(pump, circuit, .75)
    assert (pump, circuit) == original
