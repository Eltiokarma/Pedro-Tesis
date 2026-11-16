"""Independent analytical checks of instrumented thermal/control dynamics.

Reference predictions are derived here from an affine matrix exponential and
sampled control equations; they do not call the instrumentation helpers or the
example generator. These are numerical checks, not experimental validation.
"""
from __future__ import annotations

import math
from decimal import Decimal, localcontext

import numpy as np
import pytest
from scipy.linalg import expm

from dynamic_hydraulics import solve_circuit
from dynamic_tank import default_case, default_instrumented_case, simulate_dynamic_tank


SECTIONS = ("tank", "wall", "jacket")


def _case():
    case = default_instrumented_case()
    case["controller"]["enabled"] = False
    case["inputs"].update(valve_opening=0.0, agitator_power_W=0.0)
    case["instrumentation"]["valve_actuator"]["initial_opening"] = 0.0
    case["simulation"].update(duration_s=80.0, output_interval_s=13.0,
                              max_step_s=1.0, rtol=1e-9, atol=1e-10)
    return case


def _isothermal_case():
    case = _case()
    case["wall"].update(ua_tank_W_K=0.0, ua_jacket_W_K=0.0, ua_ambient_W_K=0.0)
    for name in SECTIONS:
        case[name]["initial_temperature_K"] = 300.0
        case["instrumentation"]["temperature_sensors"][name].update(
            initial_temperature_K=300.0, time_constant_s=5.0, bias_K=0.0)
    case["inputs"].update(utility_supply_temperature_K=300.0, ambient_temperature_K=300.0)
    return case


@pytest.mark.parametrize("method", ["BDF", "Radau"])
def test_six_temperature_affine_system_matches_independent_matrix_exponential(method):
    case = _case()
    case["simulation"]["method"] = method
    case["inputs"].update(agitator_power_W=250.0, ambient_temperature_K=290.0)
    physical = (320.0, 300.0, 340.0)
    sensor_initial = (285.0, 330.0, 310.0)
    taus = (4.0, 15.0, 40.0)
    biases = (1.25, -0.4, 2.1)
    for name, temp, sensor, tau, bias in zip(SECTIONS, physical, sensor_initial, taus, biases):
        case[name]["initial_temperature_K"] = temp
        case["instrumentation"]["temperature_sensors"][name].update(
            initial_temperature_K=sensor, time_constant_s=tau, bias_K=bias)

    capacities = (case["tank"]["initial_mass_kg"] * case["tank"]["cp_J_kg_K"],
                  case["wall"]["heat_capacity_J_K"],
                  case["jacket"]["mass_kg"] * case["jacket"]["cp_J_kg_K"])
    ct, cw, cj = capacities
    ht, hj, ha = (case["wall"][key] for key in
                  ("ua_tank_W_K", "ua_jacket_W_K", "ua_ambient_W_K"))
    matrix = np.zeros((7, 7))
    matrix[:3, :3] = [[-ht / ct, ht / ct, 0.0],
                       [ht / cw, -(ht + hj + ha) / cw, hj / cw],
                       [0.0, hj / cj, -hj / cj]]
    matrix[:3, 6] = [250.0 / ct, ha * 290.0 / cw, 0.0]
    for index, tau in enumerate(taus):
        matrix[index + 3, index] = 1.0 / tau
        matrix[index + 3, index + 3] = -1.0 / tau
    initial = np.array([*physical, *sensor_initial, 1.0])
    times = [0.0, 1.7, 4.2, 8.8, 19.5, 33.0, 80.0]
    result = simulate_dynamic_tank(case, sample_times_s=times)
    assert result["summary"]["success"], result["summary"]
    actual = {row["time_s"]: row for row in result["series"]}
    for time in times:
        reference = expm(matrix * time) @ initial
        row = actual[time]
        for index, name in enumerate(SECTIONS):
            assert row[name + "_temperature_K"] == pytest.approx(reference[index], abs=2e-5)
            assert row[name + "_sensor_temperature_K"] == pytest.approx(reference[index + 3], abs=2e-5)
            assert row[name + "_indicated_temperature_K"] == pytest.approx(
                reference[index + 3] + biases[index], abs=2e-5)
    assert result["audit"]["max_energy_residual_relative"] < 1e-11


def test_setpoint_step_is_not_integrated_over_the_preceding_interval():
    case = _isothermal_case()
    case["controller"].update(enabled=True, direction="heating", sample_s=10.0,
                              bias=0.2, kp_per_K=0.1, ki_per_K_s=0.02)
    case["instrumentation"]["tracking_time_s"] = 4.0
    case["instrumentation"]["valve_actuator"].update(enabled=False, initial_opening=0.2)
    case["inputs"].update(valve_opening=0.2, temperature_setpoint_K=300.0)
    case["simulation"].update(duration_s=31.0, output_interval_s=1.0)
    case["events"] = [{"time_s": 10.0, "changes": {"temperature_setpoint_K": 302.0}}]
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    sampled = {row["time_s"]: row for row in result["series"]}
    assert sampled[0.0]["valve_command"] == pytest.approx(0.2)
    assert sampled[10.0]["valve_command"] == pytest.approx(0.4, abs=1e-10)
    # The preceding error was zero at t=10, so only P acts immediately. At
    # t=20, ten seconds of the preceding +2 K error have actually elapsed.
    weight = 1.0 - math.exp(-10.0 / 4.0)
    integral_at_twenty = (4.0 * 0.02 * 2.0) * weight
    assert sampled[20.0]["valve_command"] == pytest.approx(0.4 + integral_at_twenty, abs=1e-10)


def test_indication_outside_property_domain_does_not_move_a_physical_boundary():
    case = _isothermal_case()
    case["instrumentation"]["temperature_sensors"]["tank"]["bias_K"] = 90.0
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    last = result["series"][-1]
    assert last["tank_temperature_K"] == pytest.approx(300.0)
    assert last["tank_indicated_temperature_K"] == pytest.approx(390.0)
    assert last["tank_indicated_temperature_K"] > case["simulation"]["max_temperature_K"]
    assert result["audit"]["max_energy_residual_relative"] < 1e-12


def test_physical_high_temperature_stops_even_while_indication_stays_cool():
    case = _isothermal_case()
    case["tank"].update(initial_mass_kg=5.1, initial_temperature_K=362.0)
    case["inputs"]["agitator_power_W"] = 100_000.0
    case["instrumentation"]["temperature_sensors"]["tank"].update(
        time_constant_s=1000.0, initial_temperature_K=300.0, bias_K=-20.0)
    result = simulate_dynamic_tank(case)
    assert not result["summary"]["success"]
    assert result["summary"]["stop_reason"] == "tank_temperature_high"
    expected_time = (case["simulation"]["max_temperature_K"] - 362.0) * 5.1 * 4180.0 / 100_000.0
    assert result["summary"]["final_time_s"] == pytest.approx(expected_time, abs=1e-7)
    last = result["series"][-1]
    assert last["tank_temperature_K"] == pytest.approx(case["simulation"]["max_temperature_K"], abs=1e-7)
    assert last["tank_indicated_temperature_K"] < 281.0


def _decimal_hydraulic_reference(pump, circuit, opening):
    """Direct pump/Kv intersection at high precision, without scaled-root code."""
    d = lambda value: Decimal.from_float(float(value))
    with localcontext() as context:
        context.prec = 90
        available = d(pump["shutoff_head_m"]) * d(pump["speed_fraction"]) ** 2
        net = available - d(circuit["static_head_m"])
        valve_resistance = (d(100000.0) / (d(1000.0) * d(9.80665))
                            * (d(3600.0) / (d(circuit["valve_kv_m3_h"]) * d(opening))) ** 2)
        resistance = d(pump["curve_coefficient_s2_m5"]) + d(circuit["resistance_s2_m5"]) + valve_resistance
        flow_squared = net / resistance
        return (float(flow_squared.sqrt()),
                float(d(circuit["resistance_s2_m5"]) * flow_squared),
                float(valve_resistance * flow_squared))


@pytest.mark.parametrize("head,opening", [
    (18.0, 1e-320), (18.0, 4e-321), (18.0, math.ulp(0.0)),
    (1e8, 1e-320), (1e100, 1e-320), (1e-280, 1e-200), (1e308, 1e-200),
])
def test_nearly_closed_hydraulics_matches_high_precision_without_intermediate_underflow(head, opening):
    case = default_case()
    pump, circuit = case["pump"], case["circuit"]
    pump["shutoff_head_m"] = head
    expected_flow, expected_pipe, expected_valve = _decimal_hydraulic_reference(pump, circuit, opening)
    actual = solve_circuit(pump, circuit, opening)
    flow = actual["flow_m3_s"]
    assert all(math.isfinite(actual[key]) for key in
               ("flow_m3_s", "mass_flow_kg_s", "pump_head_m", "pipe_head_m", "valve_head_m",
                "hydraulic_power_W", "shaft_power_W", "head_balance_residual_m"))
    if expected_flow == 0:
        assert flow == 0  # Only the final physical flow may underflow to zero.
    else:
        assert flow > 0
        assert abs(flow - expected_flow) <= max(2e-13 * expected_flow, math.ulp(expected_flow))
    assert actual["pipe_head_m"] == pytest.approx(expected_pipe, rel=2e-13, abs=math.ulp(expected_pipe))
    assert actual["valve_head_m"] == pytest.approx(expected_valve, rel=2e-13, abs=math.ulp(expected_valve))
    assert abs(actual["head_balance_residual_m"]) <= head * 2e-13
    assert actual["operating_point_valid"]


def test_tiny_positive_flow_still_respects_the_declared_curve_envelope():
    case = default_case()
    pump, circuit = case["pump"], case["circuit"]
    pump["shutoff_head_m"] = 1e100
    expected_flow, _, _ = _decimal_hydraulic_reference(pump, circuit, 1e-320)
    pump["max_flow_m3_s"] = expected_flow / 2.0
    actual = solve_circuit(pump, circuit, 1e-320)
    assert actual["flow_m3_s"] == pytest.approx(expected_flow, rel=2e-13, abs=0.0)
    assert not actual["operating_point_valid"]
    assert any("extrapolated" in note for note in actual["warnings"])


def test_underflowed_curve_envelope_is_rejected_instead_of_accepted_as_zero():
    case = default_case()
    case["pump"].update(speed_fraction=1e-10, max_flow_m3_s=1e-320)
    # The exact flow is about 1.1e-328, above the declared 1e-330 limit.
    # Both round to zero in binary64; accepting 0 <= 0 would conceal a
    # domain violation, so this scale must be rejected explicitly.
    with pytest.raises(ValueError, match="envelope underflows"):
        solve_circuit(case["pump"], case["circuit"], 1e-315)
