"""Independent analytical and boundary checks for the transient pilot."""
import copy
import json
import math

import numpy as np
import pytest
from scipy.linalg import expm

from dynamic_tank import default_case, simulate_dynamic_tank


def isolated_case():
    case = default_case()
    case["controller"]["enabled"] = False
    case["inputs"].update(valve_opening=0, agitator_power_W=0)
    case["wall"].update(ua_tank_W_K=0, ua_jacket_W_K=0, ua_ambient_W_K=0)
    case["simulation"].update(duration_s=40, output_interval_s=7, max_step_s=2)
    return case


@pytest.mark.parametrize("method", ["BDF", "Radau"])
def test_variable_inventory_mixing_matches_closed_form_across_feed_change(method):
    case = isolated_case()
    case["simulation"].update(method=method, rtol=1e-9, atol=1e-10)
    case["tank"].update(initial_mass_kg=100, initial_temperature_K=300,
                        initial_tracer_mass_fraction=.2)
    case["inputs"].update(feed_flow_kg_s=3, outlet_flow_kg_s=1,
                          feed_temperature_K=320, feed_tracer_mass_fraction=.8)
    case["events"] = [{"time_s": 20, "changes": {
        "feed_flow_kg_s": 1, "outlet_flow_kg_s": 4,
        "feed_temperature_K": 290, "feed_tracer_mass_fraction": .1}}]
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    # For a mixed nonreactive tank: z-z_feed=(z0-z_feed)*(M0/M)**(Fin/(Fin-Fout)).
    t20 = 320 + (300 - 320) * (100 / 140) ** 1.5
    z20 = .8 + (.2 - .8) * (100 / 140) ** 1.5
    expected_t = 290 + (t20 - 290) * (140 / 80) ** (-1 / 3)
    expected_z = .1 + (z20 - .1) * (140 / 80) ** (-1 / 3)
    last = result["series"][-1]
    assert last["time_s"] == 40
    assert last["mass_kg"] == pytest.approx(80, abs=1e-7)
    assert last["tank_temperature_K"] == pytest.approx(expected_t, abs=2e-5)
    assert last["tracer_mass_fraction"] == pytest.approx(expected_z, abs=2e-7)
    at_change = next(row for row in result["series"] if row["time_s"] == 20)
    assert at_change["feed_flow_kg_s"] == 1
    assert at_change["tank_temperature_K"] == pytest.approx(t20, abs=2e-5)


def test_three_body_heat_exchange_matches_matrix_exponential():
    case = isolated_case()
    case["simulation"].update(duration_s=1000, output_interval_s=37, max_step_s=20)
    case["tank"]["initial_temperature_K"] = 300
    case["wall"].update(initial_temperature_K=340, ua_tank_W_K=700, ua_jacket_W_K=1100)
    case["jacket"]["initial_temperature_K"] = 320
    ct = case["tank"]["initial_mass_kg"] * case["tank"]["cp_J_kg_K"]
    cw = case["wall"]["heat_capacity_J_K"]
    cj = case["jacket"]["mass_kg"] * case["jacket"]["cp_J_kg_K"]
    matrix = np.array([[-700 / ct, 700 / ct, 0],
                       [700 / cw, -1800 / cw, 1100 / cw],
                       [0, 1100 / cj, -1100 / cj]])
    expected = expm(matrix * 1000) @ np.array([300, 340, 320])
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    row = result["series"][-1]
    for name, value in zip(("tank_temperature_K", "wall_temperature_K", "jacket_temperature_K"), expected):
        assert row[name] == pytest.approx(value, abs=2e-5)
    assert row["total_stored_energy_J"] == pytest.approx(result["series"][0]["total_stored_energy_J"], rel=1e-11)
    assert row["cumulative_net_energy_J"] == pytest.approx(0, abs=1e-10)


def test_drain_limit_reports_exact_event_time_and_no_negative_inventory():
    case = isolated_case()
    case["tank"].update(initial_mass_kg=50, min_mass_kg=5)
    case["inputs"]["outlet_flow_kg_s"] = 2
    result = simulate_dynamic_tank(case)
    assert not result["summary"]["success"]
    assert result["summary"]["stop_reason"] == "minimum_inventory"
    assert result["summary"]["final_time_s"] == pytest.approx(22.5, abs=1e-8)
    assert result["series"][-1]["time_s"] == pytest.approx(22.5, abs=1e-8)
    assert result["series"][-1]["mass_kg"] == pytest.approx(5, abs=1e-8)
    assert all(row["mass_kg"] >= 5 - 1e-8 for row in result["series"])


def test_output_sampling_does_not_change_dynamics_or_event_response():
    case = isolated_case()
    case["wall"].update(ua_tank_W_K=700, ua_jacket_W_K=1100)
    case["inputs"]["valve_opening"] = .5
    case["events"] = [{"time_s": 13.3, "changes": {"valve_opening": .9}}]
    other = copy.deepcopy(case)
    other["simulation"]["output_interval_s"] = 1
    a, b = simulate_dynamic_tank(case), simulate_dynamic_tank(other)
    assert a["summary"]["success"] and b["summary"]["success"]
    for name in ("tank_temperature_K", "wall_temperature_K", "jacket_temperature_K", "total_stored_energy_J"):
        assert a["series"][-1][name] == b["series"][-1][name]
    for result in (a, b):
        times = [row["time_s"] for row in result["series"]]
        assert times == sorted(set(times))
        at_change = next(row for row in result["series"] if row["time_s"] == 13.3)
        assert at_change["valve_opening"] == .9


def test_controller_payload_and_decimal_sample_events_are_json_safe():
    case = default_case()
    case["controller"]["sample_s"] = .1
    case["simulation"].update(duration_s=1, output_interval_s=.1, max_step_s=.1)
    case["events"] = [{"time_s": .3, "changes": {"temperature_setpoint_K": 320}}]
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    json.dumps(result, allow_nan=False)
    controls = [event for event in result["events"] if event["kind"] == "controller_sample"]
    at_change = [event for event in controls if math.isclose(event["time_s"], .3, abs_tol=1e-12)]
    assert len(at_change) == 1
    # The new setpoint must be visible to the coincident controller sample.
    assert at_change[0]["error_K"] < 23
    assert all(type(event["saturated"]) is bool for event in controls)


@pytest.mark.parametrize("section,key", [
    ("tank", "cp_J_kg_K"), ("tank", "volume_capacity_m3"),
    ("wall", "heat_capacity_J_K"), ("jacket", "mass_kg"),
    ("inputs", "feed_flow_kg_s"), ("controller", "kp_per_K"),
])
def test_finite_inputs_that_overflow_derived_physics_are_rejected_early(section, key):
    case = default_case()
    case[section][key] = 1e308
    with pytest.raises(ValueError, match="no finitos"):
        simulate_dynamic_tank(case)


def test_trace_washout_reports_numerical_bounds_without_silent_clipping():
    case = isolated_case()
    case["tank"].update(initial_mass_kg=10, min_mass_kg=1, initial_tracer_mass_fraction=.1)
    case["inputs"].update(feed_flow_kg_s=1, outlet_flow_kg_s=1)
    case["simulation"].update(duration_s=1000, max_step_s=100, output_interval_s=1)
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    minimum = min(row["tracer_mass_fraction"] for row in result["series"])
    audit = result["audit"]
    assert audit["min_tracer_mass_fraction"] == minimum
    assert minimum >= -audit["tracer_fraction_absolute_tolerance"]
    if minimum < 0:
        assert any("trazador fuera de [0,1]" in item for item in result["diagnostics"])
