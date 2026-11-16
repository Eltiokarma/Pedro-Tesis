"""Analytical and conservation checks for explicitly instrumented tank cases.

The expectations use closed-form scalar dynamics, not simulator-generated data.
These are numerical tests, not evidence about a physical sensor or valve.
"""
from __future__ import annotations

import copy
import json
import math

import pytest

from dynamic_instrumentation import advance_actuator, tracking_integral_update
from dynamic_hydraulics import solve_circuit
from dynamic_tank import default_case, default_instrumented_case, simulate_dynamic_tank, validate_case


NAMES = ("tank", "wall", "jacket")


def constant_temperature_case():
    case = default_instrumented_case()
    case["controller"]["enabled"] = False
    case["inputs"].update(valve_opening=0.0, agitator_power_W=0.0,
                          utility_supply_temperature_K=300.0, ambient_temperature_K=300.0)
    case["wall"].update(ua_tank_W_K=0.0, ua_jacket_W_K=0.0, ua_ambient_W_K=0.0)
    for name in NAMES:
        case[name]["initial_temperature_K"] = 300.0
        case["instrumentation"]["temperature_sensors"][name].update(
            initial_temperature_K=300.0, time_constant_s=10.0, bias_K=0.0)
    case["instrumentation"]["valve_actuator"].update(enabled=False, initial_opening=0.0)
    case["simulation"].update(duration_s=60.0, output_interval_s=2.0, max_step_s=2.0,
                               rtol=1e-10, atol=1e-11)
    return case


@pytest.mark.parametrize("method", ["BDF", "Radau"])
def test_sensor_relaxation_matches_closed_form_without_changing_equipment_energy(method):
    case = constant_temperature_case()
    case["simulation"]["method"] = method
    settings = ((290.0, 8.0, 1.5), (320.0, 12.0, -2.0), (285.0, 20.0, 0.25))
    for name, (initial, tau, bias) in zip(NAMES, settings):
        case["instrumentation"]["temperature_sensors"][name].update(
            initial_temperature_K=initial, time_constant_s=tau, bias_K=bias)
    result = simulate_dynamic_tank(case, sample_times_s=[8.0, 8.0 * math.log(10.0)])
    assert result["summary"]["success"]
    assert result["schema_version"] == "dynamic-tank/v2"
    energy = result["series"][0]["total_stored_energy_J"]
    for row in result["series"]:
        for name, (initial, tau, bias) in zip(NAMES, settings):
            expected = 300.0 + (initial - 300.0) * math.exp(-row["time_s"] / tau)
            assert row[f"{name}_temperature_K"] == pytest.approx(300.0, abs=1e-9)
            assert row[f"{name}_sensor_temperature_K"] == pytest.approx(expected, abs=2e-6)
            assert row[f"{name}_indicated_temperature_K"] == pytest.approx(expected + bias, abs=2e-6)
        assert row["total_stored_energy_J"] == pytest.approx(energy, abs=1e-7)
    at_tau = next(row for row in result["series"] if row["time_s"] == 8.0)
    at_t90 = next(row for row in result["series"] if row["time_s"] == 8.0 * math.log(10.0))
    assert (at_tau["tank_sensor_temperature_K"] - 290.0) / 10.0 == pytest.approx(1 - math.exp(-1), abs=2e-7)
    assert at_t90["tank_sensor_temperature_K"] == pytest.approx(299.0, abs=2e-6)


def test_zero_time_constant_is_algebraic_and_keeps_indication_separate():
    case = constant_temperature_case()
    case["instrumentation"]["temperature_sensors"]["tank"].update(
        time_constant_s=0.0, initial_temperature_K=285.0, bias_K=-4.0)
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    for row in result["series"]:
        assert row["tank_sensor_temperature_K"] == pytest.approx(row["tank_temperature_K"])
        assert row["tank_indicated_temperature_K"] == pytest.approx(296.0)


def actuator_settings():
    return {"enabled": True, "time_constant_s": 2.0, "opening_rate_per_s": 0.05,
            "closing_rate_per_s": 0.1, "initial_opening": 0.0}


@pytest.mark.parametrize("time", [0.0, 1.0, 10.0, 18.0, 19.5, 30.0, 100.0])
def test_opening_actuator_has_linear_then_exponential_response(time):
    # Opening from 0 to 1: rate .05 until x=.9 at t=18 s, then first order.
    expected = .05 * time if time <= 18.0 else 1.0 - .1 * math.exp(-(time - 18.0) / 2.0)
    actual = advance_actuator(0.0, 1.0, time, actuator_settings())
    assert actual == pytest.approx(expected, abs=2e-14)
    assert 0 <= actual <= 1


@pytest.mark.parametrize("time", [0.0, 1.0, 5.0, 8.0, 9.5, 30.0, 100.0])
def test_closing_actuator_uses_its_distinct_rate_limit(time):
    # Closing from 1 to 0: rate -.1 until x=.2 at t=8 s, then first order.
    expected = 1.0 - .1 * time if time <= 8.0 else .2 * math.exp(-(time - 8.0) / 2.0)
    assert advance_actuator(1.0, 0.0, time, actuator_settings()) == pytest.approx(expected, abs=2e-14)


def test_small_valve_move_is_exponential_without_artificial_initial_ramp():
    for time in [0.0, .1, 1.0, 4.0, 20.0]:
        expected = .55 - .05 * math.exp(-time / 2.0)
        assert advance_actuator(.5, .55, time, actuator_settings()) == pytest.approx(expected, abs=2e-14)


@pytest.mark.parametrize("elapsed", [0.0, .01, 1.0, 1000.0])
def test_tracking_integral_remains_finite_for_large_sample_to_tracking_ratio(elapsed):
    # Test the held-input linear equation independently, including its limit.
    initial, error, position, bias, kp, ki, tracking = 3.0, -5.0, .2, .1, .4, .03, .02
    equilibrium = tracking * ki * error + position - bias - kp * error
    expected = equilibrium + (initial - equilibrium) * math.exp(-elapsed / tracking)
    actual = tracking_integral_update(initial, error, position, bias, kp, ki, elapsed, tracking)
    assert math.isfinite(actual)
    assert actual == pytest.approx(expected, rel=1e-13, abs=1e-13)


def test_controller_uses_indicated_temperature_and_reports_real_initial_position():
    case = constant_temperature_case()
    case["controller"].update(enabled=True, kp_per_K=.05, ki_per_K_s=0.0, bias=.1)
    case["inputs"]["temperature_setpoint_K"] = 310.0
    case["instrumentation"]["temperature_sensors"]["tank"].update(time_constant_s=0.0, bias_K=5.0)
    case["instrumentation"]["valve_actuator"].update(enabled=True, initial_opening=.2)
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    first = result["series"][0]
    assert first["tank_temperature_K"] == pytest.approx(300.0)
    assert first["tank_indicated_temperature_K"] == pytest.approx(305.0)
    assert first["valve_command"] == pytest.approx(.35)
    assert first["valve_opening"] == pytest.approx(.2)


def test_valve_reversal_preserves_position_continuity_and_uses_new_command():
    case = constant_temperature_case()
    case["inputs"]["valve_opening"] = 1.0
    case["instrumentation"]["valve_actuator"].update(actuator_settings())
    case["events"] = [{"time_s": 10.0, "changes": {"valve_opening": 0.0}}]
    result = simulate_dynamic_tank(case, sample_times_s=[9.999, 10.0, 10.001, 12.0, 13.0, 15.0])
    assert result["summary"]["success"]
    rows = {row["time_s"]: row for row in result["series"]}
    assert rows[10.0]["valve_opening"] == pytest.approx(.5, abs=1e-12)
    assert rows[10.0]["valve_command"] == 0
    assert rows[9.999]["valve_opening"] < rows[10.0]["valve_opening"]
    assert rows[10.001]["valve_opening"] < rows[10.0]["valve_opening"]
    assert rows[12.0]["valve_opening"] == pytest.approx(.3, abs=1e-12)
    assert rows[13.0]["valve_opening"] == pytest.approx(.2, abs=1e-12)
    assert rows[15.0]["valve_opening"] == pytest.approx(.2 * math.exp(-1), abs=1e-12)


def test_hydraulic_curve_limit_is_detected_inside_actuator_segment():
    case = constant_temperature_case()
    case["inputs"]["valve_opening"] = .9
    case["simulation"].update(duration_s=20.0, output_interval_s=7.0, max_step_s=10.0)
    case["instrumentation"]["valve_actuator"].update(
        enabled=True, initial_opening=.1, time_constant_s=2.0, opening_rate_per_s=.1)
    pump, circuit = case["pump"], case["circuit"]
    # Prescribe the envelope to intersect the valve path at x=.4, reached at 3 s.
    valve_resistance = 1e5 / (1000.0 * 9.80665) * (3600.0 / (circuit["valve_kv_m3_h"] * .4)) ** 2
    pump["max_flow_m3_s"] = math.sqrt(
        (pump["shutoff_head_m"] - circuit["static_head_m"]) /
        (pump["curve_coefficient_s2_m5"] + circuit["resistance_s2_m5"] + valve_resistance))
    result = simulate_dynamic_tank(case)
    assert not result["summary"]["success"]
    assert result["summary"]["stop_reason"] == "pump_curve_domain"
    assert result["summary"]["final_time_s"] == pytest.approx(3.0, abs=2e-7)
    assert result["series"][-1]["valve_opening"] == pytest.approx(.4, abs=2e-8)
    assert result["series"][-1]["utility_flow_kg_s"] == pytest.approx(
        pump["max_flow_m3_s"] * case["jacket"]["density_kg_m3"], rel=1e-8)


def test_constant_valve_at_valid_curve_envelope_does_not_trigger_a_flat_event():
    case = constant_temperature_case()
    case["inputs"]["valve_opening"] = .4
    case["instrumentation"]["valve_actuator"].update(enabled=True, initial_opening=.4)
    flow = solve_circuit(case["pump"], case["circuit"], .4,
                         case["jacket"]["density_kg_m3"])["flow_m3_s"]
    case["pump"]["max_flow_m3_s"] = flow
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    assert result["summary"]["stop_reason"] == "duration_reached"
    assert result["summary"]["final_time_s"] == case["simulation"]["duration_s"]
    assert not any(event.get("reason") == "pump_curve_domain" for event in result["events"])
    for row in result["series"]:
        assert row["valve_opening"] == pytest.approx(.4, abs=1e-14)
        assert row["utility_flow_kg_s"] == pytest.approx(flow * case["jacket"]["density_kg_m3"])


def test_dynamic_position_drives_flow_and_preserves_mass_tracer_and_energy():
    case = default_instrumented_case()
    case["controller"]["enabled"] = False
    case["inputs"].update(valve_opening=1.0, feed_flow_kg_s=1.5, outlet_flow_kg_s=1.0,
                          feed_temperature_K=310.0, feed_tracer_mass_fraction=.2)
    case["instrumentation"]["valve_actuator"]["initial_opening"] = .05
    case["simulation"].update(duration_s=200.0, output_interval_s=2.0, max_step_s=2.0,
                               rtol=1e-9, atol=1e-10)
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    assert result["series"][0]["utility_flow_kg_s"] < result["series"][5]["utility_flow_kg_s"]
    assert result["series"][-1]["mass_kg"] == pytest.approx(600.0, abs=1e-6)
    for quantity in ("mass", "tracer", "energy"):
        assert result["audit"][f"max_{quantity}_residual_relative"] < 1e-10
    json.dumps(result, allow_nan=False)


def test_v1_stays_explicitly_ideal_and_v2_ideal_open_loop_recovers_its_trajectory():
    legacy = default_case()
    legacy["controller"]["enabled"] = False
    legacy["simulation"].update(duration_s=90.0, output_interval_s=3.0, max_step_s=2.0,
                                 rtol=1e-9, atol=1e-10)
    legacy["events"] = [{"time_s": 30.0, "changes": {"valve_opening": .2}}]
    extended = copy.deepcopy(legacy)
    extended["schema_version"] = "dynamic-tank/v2"
    extended["instrumentation"] = default_instrumented_case()["instrumentation"]
    extended["instrumentation"]["valve_actuator"]["enabled"] = False
    for sensor in extended["instrumentation"]["temperature_sensors"].values():
        sensor.update(time_constant_s=0.0, bias_K=0.0)
    old, new = simulate_dynamic_tank(legacy), simulate_dynamic_tank(extended)
    assert old["summary"]["success"] and new["summary"]["success"]
    assert old["schema_version"] == "dynamic-tank/v1"
    assert "instrumentation" not in old["configuration"]
    assert "valve_command" not in old["series"][0]
    assert not any("sensor" in key or "indicated" in key for key in old["series"][0])
    assert len(old["series"]) == len(new["series"])
    for before, after in zip(old["series"], new["series"]):
        assert before["time_s"] == after["time_s"]
        for name in NAMES:
            assert after[f"{name}_temperature_K"] == pytest.approx(before[f"{name}_temperature_K"], abs=3e-6)
        assert after["valve_opening"] == before["valve_opening"]
        assert after["utility_flow_kg_s"] == pytest.approx(before["utility_flow_kg_s"], rel=1e-12)


@pytest.mark.parametrize("path,value", [
    (("temperature_sensors", "tank", "time_constant_s"), -1.0),
    (("temperature_sensors", "tank", "time_constant_s"), True),
    (("temperature_sensors", "tank", "time_constant_s"), float("inf")),
    (("temperature_sensors", "tank", "bias_K"), float("nan")),
    (("temperature_sensors", "tank", "bias_K"), -400.0),
    (("temperature_sensors", "tank", "initial_temperature_K"), 250.0),
    (("valve_actuator", "enabled"), 1),
    (("valve_actuator", "time_constant_s"), 0.0),
    (("valve_actuator", "opening_rate_per_s"), -1.0),
    (("valve_actuator", "closing_rate_per_s"), 0.0),
    (("valve_actuator", "initial_opening"), 1.01),
    (("tracking_time_s",), 0.0),
])
def test_instrumentation_rejects_invalid_or_nonfinite_parameters(path, value):
    case = default_instrumented_case()
    section = case["instrumentation"]
    for key in path[:-1]:
        section = section[key]
    section[path[-1]] = value
    with pytest.raises(ValueError):
        validate_case(case)


def test_schema_never_silently_enables_or_discards_instrumentation():
    case = default_instrumented_case()
    del case["instrumentation"]
    with pytest.raises(ValueError):
        validate_case(case)
    case = default_instrumented_case()
    case["schema_version"] = "dynamic-tank/v1"
    with pytest.raises(ValueError):
        validate_case(case)
    case = default_instrumented_case()
    case["instrumentation"]["temperature_sensors"]["tank"]["time_constant_ms"] = 10.0
    with pytest.raises(ValueError):
        validate_case(case)


def test_instrumented_cancellation_returns_finite_traceable_partial_state():
    result = simulate_dynamic_tank(default_instrumented_case(), cancel=lambda: True)
    assert result["summary"]["status"] == "cancelled"
    assert result["summary"]["final_time_s"] == 0
    assert len(result["series"]) == 1
    assert result["series"][0]["valve_opening"] == .5
    assert "tank_indicated_temperature_K" in result["series"][0]
    json.dumps(result, allow_nan=False)


def test_long_closing_stroke_never_overflows_hydraulic_resistance():
    case = constant_temperature_case()
    case["inputs"]["valve_opening"] = 0.0
    case["instrumentation"]["valve_actuator"].update(
        enabled=True, initial_opening=.8, time_constant_s=2.0, closing_rate_per_s=.1)
    case["simulation"].update(duration_s=2000.0, max_step_s=10.0, output_interval_s=10.0)
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    flows = [row["utility_flow_kg_s"] for row in result["series"]]
    assert all(after <= before for before, after in zip(flows, flows[1:]))
    assert result["series"][-1]["valve_opening"] == 0
    for row in result["series"]:
        assert all(math.isfinite(row[key]) for key in (
            "pump_head_m", "pump_shaft_power_W", "utility_flow_kg_s"))
    for quantity in ("mass", "tracer", "energy"):
        assert result["audit"][f"max_{quantity}_residual_relative"] < 1e-10
