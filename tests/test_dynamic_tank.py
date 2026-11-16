"""Independent balance/analytical/event checks for the bounded transient pilot."""
import json
import math
import os
import sys

import numpy as np
import pytest
from scipy.linalg import expm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dynamic_tank import default_case, simulate_dynamic_tank, validate_case


def isolated_case():
    c = default_case()
    c["controller"]["enabled"] = False
    c["inputs"].update(valve_opening=0.0, agitator_power_W=0.0)
    c["wall"]["ua_ambient_W_K"] = 0.0
    c["simulation"].update(duration_s=200.0, output_interval_s=5.0, max_step_s=5.0,
                           rtol=1e-9, atol=1e-10)
    return c


def uncoupled_case():
    c = isolated_case()
    c["wall"].update(ua_tank_W_K=0.0, ua_jacket_W_K=0.0)
    c["tank"].update(initial_mass_kg=100.0, initial_temperature_K=300.0,
                      initial_tracer_mass_fraction=0.1)
    return c


def test_closed_thermal_system_matches_independent_matrix_exponential():
    c = isolated_case()
    c["tank"]["initial_temperature_K"] = 290.0
    c["wall"]["initial_temperature_K"] = 320.0
    c["jacket"]["initial_temperature_K"] = 350.0
    ct = c["tank"]["initial_mass_kg"] * c["tank"]["cp_J_kg_K"]
    cw = c["wall"]["heat_capacity_J_K"]
    cj = c["jacket"]["mass_kg"] * c["jacket"]["cp_J_kg_K"]
    a, b = c["wall"]["ua_tank_W_K"], c["wall"]["ua_jacket_W_K"]
    matrix = np.array([[-a / ct, a / ct, 0], [a / cw, -(a+b) / cw, b / cw], [0, b / cj, -b / cj]])
    result = simulate_dynamic_tank(c)
    assert result["summary"]["success"]
    for row in result["series"]:
        expected = expm(matrix * row["time_s"]) @ [290., 320., 350.]
        actual = [row["tank_temperature_K"], row["wall_temperature_K"], row["jacket_temperature_K"]]
        np.testing.assert_allclose(actual, expected, rtol=0, atol=3e-6)
    assert result["audit"]["max_energy_residual_relative"] < 1e-12
    assert result["audit"]["max_mass_residual_kg"] == 0


def test_cstr_washout_and_temperature_match_analytical_solution():
    c = uncoupled_case()
    c["inputs"].update(feed_flow_kg_s=2.0, outlet_flow_kg_s=2.0,
                        feed_temperature_K=330.0, feed_tracer_mass_fraction=0.4)
    result = simulate_dynamic_tank(c)
    assert result["summary"]["success"]
    for row in result["series"]:
        decay = math.exp(-2 * row["time_s"] / 100.)
        assert row["mass_kg"] == pytest.approx(100.)
        assert row["tank_temperature_K"] == pytest.approx(330.-30.*decay, abs=3e-6)
        assert row["tracer_mass_fraction"] == pytest.approx(.4-.3*decay, abs=3e-8)
    assert result["audit"]["max_tracer_residual_relative"] < 1e-12
    assert result["audit"]["max_energy_residual_relative"] < 1e-12


def test_variable_inventory_conserves_tracer_and_energy_without_temperature_shortcut():
    c = uncoupled_case()
    c["simulation"]["duration_s"] = 100.0
    c["inputs"].update(feed_flow_kg_s=2., outlet_flow_kg_s=1., feed_tracer_mass_fraction=.3,
                        feed_temperature_K=340.)
    result = simulate_dynamic_tank(c)
    assert result["summary"]["success"]
    end = result["series"][-1]
    assert end["mass_kg"] == pytest.approx(200., abs=1e-8)
    assert end["tracer_mass_fraction"] == pytest.approx(.25, abs=1e-8)
    assert end["tank_temperature_K"] == pytest.approx(330., abs=2e-6)


def test_external_energy_budget_includes_feed_utility_agitation_wall_loss_and_pump_fraction():
    c = default_case()
    c["controller"]["enabled"] = False
    c["simulation"].update(duration_s=200., max_step_s=2.)
    c["inputs"].update(feed_flow_kg_s=.2, outlet_flow_kg_s=.1, feed_temperature_K=310.)
    c["jacket"]["pump_heat_fraction"] = .75
    result = simulate_dynamic_tank(c)
    end = result["series"][-1]
    assert result["summary"]["success"]
    assert end["mass_kg"] == pytest.approx(520.)
    assert end["pump_heat_to_jacket_W"] == pytest.approx(.75 * end["pump_shaft_power_W"])
    assert result["audit"]["max_mass_residual_relative"] < 1e-12
    assert result["audit"]["max_energy_residual_relative"] < 1e-12


def test_event_between_output_times_is_exact_and_right_continuous():
    c = uncoupled_case()
    c["simulation"].update(duration_s=13., output_interval_s=10., max_step_s=20.)
    c["inputs"]["feed_flow_kg_s"] = 1.
    c["events"] = [{"time_s": 3.5, "changes": {"feed_flow_kg_s": 3.0}}]
    result = simulate_dynamic_tank(c)
    assert result["summary"]["success"]
    row = next(row for row in result["series"] if row["time_s"] == 3.5)
    assert row["mass_kg"] == pytest.approx(103.5)
    assert row["feed_flow_kg_s"] == 3.
    assert result["series"][-1]["mass_kg"] == pytest.approx(132.)
    assert len({row["time_s"] for row in result["series"]}) == len(result["series"])


@pytest.mark.parametrize("kind,flow,expected_time,reason,expected_mass", [
    ("in", 10., 10., "tank_capacity", 200.),
    ("out", 10., 9.5, "minimum_inventory", 5.),
])
def test_inventory_events_stop_at_exact_boundary(kind, flow, expected_time, reason, expected_mass):
    c = uncoupled_case()
    c["tank"].update(density_kg_m3=1000., volume_capacity_m3=.2)
    c["inputs"]["feed_flow_kg_s" if kind == "in" else "outlet_flow_kg_s"] = flow
    result = simulate_dynamic_tank(c)
    assert not result["summary"]["success"]
    assert result["summary"]["status"] == "limit"
    assert result["summary"]["stop_reason"] == reason
    assert result["summary"]["final_time_s"] == pytest.approx(expected_time, abs=1e-7)
    assert result["series"][-1]["mass_kg"] == pytest.approx(expected_mass, abs=1e-6)


def test_temperature_domain_event_stops_before_extrapolation():
    c = uncoupled_case()
    c["simulation"]["max_temperature_K"] = 310.
    c["inputs"].update(temperature_setpoint_K=305., utility_supply_temperature_K=305.)
    c["inputs"]["agitator_power_W"] = 100. * c["tank"]["cp_J_kg_K"]
    result = simulate_dynamic_tank(c)
    assert result["summary"]["status"] == "limit"
    assert result["summary"]["stop_reason"] == "tank_temperature_high"
    assert result["summary"]["final_time_s"] == pytest.approx(10., abs=1e-7)
    assert result["series"][-1]["tank_temperature_K"] == pytest.approx(310.)


def test_manual_valve_step_preserved_in_series_and_does_not_teleport_temperature():
    c = isolated_case()
    c["events"] = [{"time_s": 7.3, "changes": {"valve_opening": .9}}]
    result = simulate_dynamic_tank(c)
    row = next(row for row in result["series"] if row["time_s"] == 7.3)
    assert row["tank_temperature_K"] == pytest.approx(c["tank"]["initial_temperature_K"])
    assert row["valve_opening"] == .9
    assert row["utility_flow_kg_s"] > 0
    assert result["series"][0]["utility_flow_kg_s"] == 0


def test_sampled_controller_saturates_without_integral_windup_and_reverses():
    c = uncoupled_case()
    c["controller"].update(enabled=True, sample_s=3., kp_per_K=1., ki_per_K_s=1., bias=0.)
    c["simulation"].update(duration_s=30., output_interval_s=10.)
    c["inputs"]["temperature_setpoint_K"] = 350.
    c["events"] = [{"time_s": 19., "changes": {"temperature_setpoint_K": 280.}}]
    result = simulate_dynamic_tank(c)
    controls = [e for e in result["events"] if e["kind"] == "controller_sample"]
    assert all(e["integral"] == 0 for e in controls)
    assert all(e["valve_opening"] == 1 for e in controls if e["time_s"] < 19.)
    assert next(e for e in controls if e["time_s"] == 21.)["valve_opening"] == 0
    row19 = next(row for row in result["series"] if row["time_s"] == 19.)
    assert row19["valve_opening"] == 1  # zero-order hold until the next controller sample
    row21 = next(row for row in result["series"] if row["time_s"] == 21.)
    assert row21["valve_opening"] == 0
    for event in controls:
        assert any(row["time_s"] == event["time_s"] for row in result["series"])


def test_cooling_controller_direction():
    c = uncoupled_case()
    c["controller"].update(enabled=True, direction="cooling", kp_per_K=.5, ki_per_K_s=0.)
    c["simulation"]["duration_s"] = 10.
    c["inputs"].update(temperature_setpoint_K=285., utility_supply_temperature_K=280.)
    result = simulate_dynamic_tank(c)
    assert result["series"][0]["valve_opening"] == 1.


def test_outside_pump_curve_stops_without_clamping_flow():
    c = default_case()
    c["pump"]["max_flow_m3_s"] = 1e-8
    result = simulate_dynamic_tank(c)
    assert result["summary"]["status"] == "limit"
    assert result["summary"]["stop_reason"] == "pump_curve_domain"
    assert result["summary"]["final_time_s"] == 0.
    assert len(result["series"]) == 1


def test_cancellation_returns_last_complete_checkpoint_without_nonfinite_json():
    c = default_case()
    result = simulate_dynamic_tank(c, cancel=lambda: True)
    assert result["summary"]["status"] == "cancelled"
    assert result["summary"]["final_time_s"] == 0.
    json.dumps(result, allow_nan=False)


def test_cancellation_during_integration_returns_honest_partial_result():
    c = default_case()
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        return calls > 15
    result = simulate_dynamic_tank(c, cancel=cancel)
    assert result["summary"]["status"] == "cancelled"
    assert result["summary"]["final_time_s"] < c["simulation"]["duration_s"]
    assert result["series"][-1]["time_s"] == result["summary"]["final_time_s"]


@pytest.mark.parametrize("section,key,value", [
    ("tank", "initial_mass_kg", float("nan")),
    ("tank", "cp_J_kg_K", 0.),
    ("inputs", "feed_flow_kg_s", -1.),
    ("inputs", "valve_opening", 1.1),
    ("inputs", "feed_tracer_mass_fraction", 1.1),
    ("inputs", "feed_temperature_K", 1000.),
    ("controller", "enabled", 1),
    ("controller", "sample_s", 0.),
    ("controller", "direction", "automatic"),
    ("simulation", "rtol", 0.),
    ("simulation", "duration_s", True),
    ("simulation", "output_interval_s", 1e-20),
    ("simulation", "max_step_s", 1e-20),
    ("simulation", "method", "Euler"),
    ("pump", "efficiency", float("inf")),
])
def test_invalid_inputs_are_rejected(section, key, value):
    c = default_case()
    c[section][key] = value
    with pytest.raises(ValueError):
        validate_case(c)


def test_unknown_fields_and_conflicting_manual_control_are_rejected():
    c = default_case()
    c["inputs"]["feed_fow_kg_s"] = 1.
    with pytest.raises(ValueError, match="desconocidas"):
        validate_case(c)
    c = default_case()
    c["events"] = [{"time_s": 10., "changes": {"valve_opening": .3}}]
    with pytest.raises(ValueError, match="manual"):
        validate_case(c)


def test_reproducible_hash_input_immutability_and_empirical_status():
    c = default_case()
    c["simulation"]["duration_s"] = 10.
    c["provenance"]["data_kind"] = "measured"
    original = json.dumps(c, sort_keys=True)
    first, second = simulate_dynamic_tank(c), simulate_dynamic_tank(c)
    assert json.dumps(c, sort_keys=True) == original
    assert first["metadata"]["config_sha256"] == second["metadata"]["config_sha256"]
    assert first["series"] == second["series"]
    assert first["metadata"]["simulation_data_kind"] == "synthetic"
    assert first["metadata"]["validation_state"] == "unvalidated_against_plant"
    json.dumps(first, allow_nan=False)


def test_radau_agrees_with_bdf_and_tighter_time_resolution():
    c = isolated_case()
    c["wall"]["initial_temperature_K"] = 330.
    coarse = simulate_dynamic_tank(c)
    c["simulation"].update(method="Radau", max_step_s=1.)
    fine = simulate_dynamic_tank(c)
    assert coarse["summary"]["success"] and fine["summary"]["success"]
    assert coarse["series"][-1]["tank_temperature_K"] == pytest.approx(fine["series"][-1]["tank_temperature_K"], abs=3e-6)


@pytest.mark.parametrize("section,key", [("tank", "cp_J_kg_K"), ("wall", "heat_capacity_J_K"),
                                        ("jacket", "mass_kg"), ("tank", "density_kg_m3"),
                                        ("controller", "kp_per_K")])
def test_finite_parameters_with_overflowing_derived_quantities_are_rejected(section, key):
    c = default_case()
    c[section][key] = 1e308
    if key == "density_kg_m3":
        c["tank"]["volume_capacity_m3"] = 10.
    with pytest.raises(ValueError, match="no finitos"):
        validate_case(c)


def test_tracer_roundoff_is_reported_without_silent_clipping():
    c = uncoupled_case()
    c["tank"]["initial_mass_kg"] = 10.
    c["inputs"].update(feed_flow_kg_s=1., outlet_flow_kg_s=1., feed_tracer_mass_fraction=0.)
    c["simulation"].update(duration_s=1000., output_interval_s=1., max_step_s=100., rtol=1e-7, atol=1e-8)
    result = simulate_dynamic_tank(c)
    minimum = min(row["tracer_mass_fraction"] for row in result["series"])
    assert result["audit"]["min_tracer_mass_fraction"] == minimum
    if minimum < 0:
        assert any("Fracción numérica" in message for message in result["diagnostics"])
    assert minimum >= -result["audit"]["tracer_fraction_absolute_tolerance"]
    assert result["summary"]["success"]
