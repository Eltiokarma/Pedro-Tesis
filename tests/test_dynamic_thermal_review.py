"""Independent regression checks for coupled-loop event and inventory boundaries."""
import pytest

from dynamic_tank import default_thermal_loop_case, simulate_dynamic_tank


def isolated_case():
    case = default_thermal_loop_case()
    case["controller"]["enabled"] = False
    case["inputs"].update(agitator_power_W=0.0, heater_power_request_W=0.0,
                         temperature_setpoint_K=300.0)
    case["wall"].update(ua_tank_W_K=0.0, ua_jacket_W_K=0.0, ua_ambient_W_K=0.0)
    case["utility_loop"].update(ua_ambient_W_K=0.0, heater_efficiency=1.0)
    return case


def test_initially_stopped_pump_restarts_without_spurious_terminal_root():
    case = isolated_case()
    case["inputs"]["pump_speed_fraction"] = 0.0
    case["simulation"].update(duration_s=240.0, output_interval_s=13.0)
    case["events"] = [{"time_s": 101.0, "changes": {"pump_speed_fraction": 1.0}},
                      {"time_s": 199.0, "changes": {"pump_speed_fraction": 0.0}}]
    result = simulate_dynamic_tank(case, sample_times_s=[100.999, 101.0, 198.999, 199.0])
    assert result["summary"]["success"]
    rows = {row["time_s"]: row for row in result["series"]}
    for time in (0.0, 100.999, 199.0, 240.0):
        assert rows[time]["utility_flow_kg_s"] == 0.0
        assert rows[time]["pump_heat_to_loop_W"] == 0.0
    assert rows[101.0]["utility_flow_kg_s"] > 0.0
    assert rows[198.999]["utility_flow_kg_s"] > 0.0
    assert rows[101.0]["utility_reservoir_temperature_K"] == pytest.approx(
        rows[100.999]["utility_reservoir_temperature_K"], abs=1e-9)
    assert result["audit"]["max_energy_residual_relative"] < 1e-10


def test_reservoir_limit_occurs_at_independent_heating_time_with_sensor_states():
    case = isolated_case()
    case["utility_loop"].update(initial_temperature_K=300.0, heater_max_power_W=1000.0)
    for name in ("tank", "wall", "jacket"):
        case[name]["initial_temperature_K"] = 300.0
        case["instrumentation"]["temperature_sensors"][name]["initial_temperature_K"] = 300.0
    case["inputs"].update(pump_speed_fraction=0.0, heater_power_request_W=1000.0)
    case["simulation"].update(duration_s=1000.0, output_interval_s=73.0,
                              max_temperature_K=301.0, max_step_s=100.0)
    result = simulate_dynamic_tank(case)
    expected_time = case["utility_loop"]["mass_kg"] * case["jacket"]["cp_J_kg_K"] / 1000.0
    assert result["summary"]["status"] == "limit"
    assert result["summary"]["stop_reason"] == "utility_reservoir_temperature_high"
    assert result["summary"]["final_time_s"] == pytest.approx(expected_time, abs=1e-7)
    final = result["series"][-1]
    assert final["utility_reservoir_temperature_K"] == pytest.approx(301.0, abs=1e-10)
    assert final["cumulative_heater_heat_J"] == pytest.approx(1000.0 * expected_time, abs=1e-4)
    # The extra reservoir states must not be mistaken for the three sensor states.
    for name in ("tank", "wall", "jacket"):
        assert final[name + "_temperature_K"] == pytest.approx(300.0, abs=1e-10)
        assert final[name + "_sensor_temperature_K"] == pytest.approx(300.0, abs=1e-10)


def test_cold_reservoir_reverses_exchange_and_keeps_both_inventory_balances():
    case = isolated_case()
    case["utility_loop"]["initial_temperature_K"] = 280.0
    case["jacket"]["initial_temperature_K"] = 330.0
    case["instrumentation"]["valve_actuator"]["enabled"] = False
    case["simulation"].update(duration_s=100.0, output_interval_s=5.0)
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    initial, final = result["series"][0], result["series"][-1]
    transfer = final["cumulative_utility_transfer_J"]
    assert initial["utility_heat_W"] < 0
    assert transfer < 0
    cj = case["jacket"]["mass_kg"] * case["jacket"]["cp_J_kg_K"]
    cr = case["utility_loop"]["mass_kg"] * case["jacket"]["cp_J_kg_K"]
    jacket_change = cj * (final["jacket_temperature_K"] - initial["jacket_temperature_K"])
    reservoir_change = cr * (final["utility_reservoir_temperature_K"] - initial["utility_reservoir_temperature_K"])
    # Constant hydraulics makes pump input exactly constant; no production audit is reused.
    pump_input = initial["pump_heat_to_loop_W"] * 100.0
    assert jacket_change == pytest.approx(transfer, abs=1e-5)
    assert reservoir_change == pytest.approx(-transfer + pump_input, abs=1e-5)
    assert jacket_change + reservoir_change == pytest.approx(pump_input, abs=1e-5)


def test_prolonged_dynamic_closure_keeps_finite_loop_trajectory_valid():
    case = isolated_case()
    case["inputs"]["valve_opening"] = 0.0
    case["simulation"].update(duration_s=2000.0, output_interval_s=100.0)
    result = simulate_dynamic_tank(case)
    assert result["summary"]["success"]
    flow = [row["utility_flow_kg_s"] for row in result["series"]]
    assert flow[0] > 0.0
    assert all(0.0 <= after <= before for before, after in zip(flow, flow[1:]))
    assert flow[-1] < 1e-100
    assert result["audit"]["max_energy_residual_relative"] < 1e-10
