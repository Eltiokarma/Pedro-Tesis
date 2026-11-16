"""Independent conservation, analytic, event and strict-domain checks for v3."""
import copy
import math
import os
import sys

import numpy as np
import pytest
from scipy.linalg import expm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dynamic_tank import default_thermal_loop_case, simulate_dynamic_tank, validate_case
from dynamic_thermal_loop import advective_exchange, heater_power, pump_heat_to_liquid


def case():
    c = default_thermal_loop_case()
    c["controller"]["enabled"] = False
    c["inputs"].update(agitator_power_W=0.0)
    c["instrumentation"]["valve_actuator"]["enabled"] = False
    for sensor in c["instrumentation"]["temperature_sensors"].values():
        sensor["time_constant_s"] = 0.0
    c["simulation"].update(duration_s=200.0, output_interval_s=10.0, max_step_s=5.0,
                           rtol=1e-9, atol=1e-10)
    return c


def isolated_reservoir():
    c = case()
    c["inputs"].update(pump_speed_fraction=0.0, heater_power_request_W=1000.0)
    c["utility_loop"].update(initial_temperature_K=300., ua_ambient_W_K=0., heater_efficiency=1.)
    c["wall"].update(ua_tank_W_K=0., ua_jacket_W_K=0., ua_ambient_W_K=0.)
    return c


def test_reservoir_heating_slope_and_cumulative_energy_are_analytic():
    c = isolated_reservoir()
    result = simulate_dynamic_tank(c)
    assert result["summary"]["success"]
    for row in result["series"]:
        assert row["utility_reservoir_temperature_K"] == pytest.approx(300 + 1000*row["time_s"]/(100*4180), abs=2e-10)
        assert row["cumulative_heater_heat_J"] == pytest.approx(1000*row["time_s"], abs=1e-7)
        assert row["cumulative_utility_transfer_J"] == 0
        assert row["utility_flow_kg_s"] == 0
        assert row["pump_heat_to_loop_W"] == 0
    assert result["audit"]["max_energy_residual_relative"] < 1e-12


def test_heater_saturation_preserves_requested_and_applied_electric_and_thermal_powers():
    c = isolated_reservoir()
    c["utility_loop"].update(heater_max_power_W=500., heater_efficiency=.8)
    c["inputs"]["heater_power_request_W"] = 1200.
    result = simulate_dynamic_tank(c)
    assert result["summary"]["success"]
    end = result["series"][-1]
    assert end["heater_power_request_W"] == 1200
    assert end["heater_applied_power_W"] == 500
    assert end["heater_heat_W"] == 400
    assert end["heater_saturated"] is True
    assert end["utility_reservoir_temperature_K"] == pytest.approx(300 + 400*200/(100*4180), abs=2e-10)


def test_exact_heater_cut_event_and_dense_sampling_do_not_change_trajectory():
    c = isolated_reservoir()
    c["simulation"].update(duration_s=30., output_interval_s=10.)
    c["events"] = [{"time_s": 7.3, "changes": {"heater_power_request_W": 0.}}]
    first = simulate_dynamic_tank(c)
    second = simulate_dynamic_tank(c, sample_times_s=[1., 3., 7.3, 7.4, 29.])
    assert first["summary"]["success"] and second["summary"]["success"]
    row = next(r for r in first["series"] if r["time_s"] == 7.3)
    assert row["heater_heat_W"] == 0
    for result in (first, second):
        for r in result["series"]:
            assert r["utility_reservoir_temperature_K"] == pytest.approx(300+1000*min(r["time_s"],7.3)/(100*4180), abs=2e-10)
        assert result["series"][-1]["cumulative_heater_heat_J"] == pytest.approx(7300., abs=1e-8)


def test_four_volume_circuit_matches_independently_assembled_affine_matrix():
    c = case()
    c["utility_loop"]["pump_loss_to_fluid_fraction"] = .25
    ct = c["tank"]["initial_mass_kg"] * c["tank"]["cp_J_kg_K"]
    cw = c["wall"]["heat_capacity_J_K"]
    cj = c["jacket"]["mass_kg"] * c["jacket"]["cp_J_kg_K"]
    cr = c["utility_loop"]["mass_kg"] * c["jacket"]["cp_J_kg_K"]
    a,b,w,r = c["wall"]["ua_tank_W_K"],c["wall"]["ua_jacket_W_K"],c["wall"]["ua_ambient_W_K"],c["utility_loop"]["ua_ambient_W_K"]
    opening = c["inputs"]["valve_opening"]
    valve_resistance = (1e5/(1000*9.80665)) * (3600/(c["circuit"]["valve_kv_m3_h"]*opening))**2
    flow = math.sqrt(c["pump"]["shutoff_head_m"]/(c["pump"]["curve_coefficient_s2_m5"]+c["circuit"]["resistance_s2_m5"]+valve_resistance))
    rho = c["jacket"]["density_kg_m3"]
    hydraulic_power = rho*9.80665*flow*(c["pump"]["shutoff_head_m"]-c["pump"]["curve_coefficient_s2_m5"]*flow**2)
    pump_heat = hydraulic_power + .25*(hydraulic_power/c["pump"]["efficiency"]-hydraulic_power)
    k = flow*rho*c["jacket"]["cp_J_kg_K"]
    ta = c["inputs"]["ambient_temperature_K"]
    heater_heat = 6000*.98
    matrix = np.array([[-a/ct,a/ct,0,0,0],
                       [a/cw,-(a+b+w)/cw,b/cw,0,w*ta/cw],
                       [0,b/cj,-(b+k)/cj,k/cj,0],
                       [0,0,k/cr,-(k+r)/cr,(heater_heat+pump_heat+r*ta)/cr],
                       [0,0,0,0,0]])
    initial = [c["tank"]["initial_temperature_K"],c["wall"]["initial_temperature_K"],
               c["jacket"]["initial_temperature_K"],c["utility_loop"]["initial_temperature_K"],1]
    result = simulate_dynamic_tank(c)
    assert result["summary"]["success"]
    for row in result["series"]:
        expected = (expm(matrix*row["time_s"]) @ initial)[:4]
        actual = [row[k] for k in ("tank_temperature_K","wall_temperature_K","jacket_temperature_K","utility_reservoir_temperature_K")]
        np.testing.assert_allclose(actual, expected, atol=3e-6, rtol=0)
        assert row["pump_heat_to_loop_W"] == pytest.approx(pump_heat)
        assert row["pump_heat_to_jacket_W"] == 0
    assert result["audit"]["max_energy_residual_relative"] < 1e-12


def test_closed_circuit_energy_counts_heater_and_pump_once_and_internal_transfer_never():
    c = case()
    c["wall"]["ua_ambient_W_K"] = c["utility_loop"]["ua_ambient_W_K"] = 0.
    result = simulate_dynamic_tank(c)
    assert result["summary"]["success"]
    start, end = result["series"][0], result["series"][-1]
    expected = (end["heater_heat_W"]+end["pump_heat_to_loop_W"])*200
    assert end["total_stored_energy_J"]-start["total_stored_energy_J"] == pytest.approx(expected, abs=1e-6)
    assert end["cumulative_net_energy_J"] == pytest.approx(expected, abs=1e-6)
    assert abs(end["cumulative_utility_transfer_J"]) > expected


def test_pump_stop_and_restart_are_right_continuous_and_do_not_freeze_heat_exchange():
    c = case()
    c["events"] = [{"time_s": 30.,"changes":{"pump_speed_fraction":0.}},
                   {"time_s": 60.,"changes":{"pump_speed_fraction":1.}}]
    result = simulate_dynamic_tank(c)
    assert result["summary"]["success"]
    rows = {r["time_s"]:r for r in result["series"]}
    assert rows[30.]["utility_flow_kg_s"] == 0
    assert rows[30.]["pump_heat_to_loop_W"] == 0
    assert rows[60.]["utility_flow_kg_s"] > 0
    assert rows[50.]["jacket_temperature_K"] != rows[30.]["jacket_temperature_K"]
    assert rows[50.]["utility_reservoir_temperature_K"] > rows[30.]["utility_reservoir_temperature_K"]
    assert result["audit"]["max_energy_residual_relative"] < 1e-12


def test_stopped_pump_can_start_later_with_dynamic_actuator():
    c = case()
    c["inputs"]["pump_speed_fraction"] = 0.
    c["instrumentation"]["valve_actuator"]["enabled"] = True
    c["events"] = [{"time_s": 30.,"changes":{"pump_speed_fraction":1.}}]
    result = simulate_dynamic_tank(c)
    assert result["summary"]["success"]
    assert result["series"][0]["utility_flow_kg_s"] == 0
    assert result["series"][-1]["utility_flow_kg_s"] > 0


def test_cold_reservoir_reverses_heat_transfer_without_clipping():
    c = case()
    c["utility_loop"].update(initial_temperature_K=285., ua_ambient_W_K=0.)
    c["inputs"]["heater_power_request_W"] = 0.
    result = simulate_dynamic_tank(c)
    assert result["summary"]["success"]
    assert result["series"][0]["utility_heat_W"] < 0
    assert result["series"][-1]["cumulative_utility_transfer_J"] < 0


def test_reservoir_temperature_limit_stops_at_analytic_time():
    c = isolated_reservoir()
    c["utility_loop"]["mass_kg"] = 1.
    c["jacket"]["cp_J_kg_K"] = 1000.
    c["inputs"]["temperature_setpoint_K"] = 300.
    c["simulation"]["max_temperature_K"] = 301.
    result = simulate_dynamic_tank(c)
    assert result["summary"]["status"] == "limit"
    assert result["summary"]["stop_reason"] == "utility_reservoir_temperature_high"
    assert result["summary"]["final_time_s"] == pytest.approx(1., abs=1e-10)
    assert result["series"][-1]["utility_reservoir_temperature_K"] == pytest.approx(301.)


def test_instrumented_pi_loop_agrees_between_stiff_methods():
    c = default_thermal_loop_case()
    c["simulation"].update(duration_s=100., output_interval_s=5., max_step_s=2.)
    first = simulate_dynamic_tank(c)
    c["simulation"]["method"] = "Radau"
    second = simulate_dynamic_tank(c)
    assert first["summary"]["success"] and second["summary"]["success"]
    for a,b in zip(first["series"], second["series"]):
        for key in ("tank_temperature_K","utility_reservoir_temperature_K","tank_indicated_temperature_K","valve_opening"):
            assert a[key] == pytest.approx(b[key], abs=1e-4)
    assert first["metadata"]["controller_feedback"] == "tank_indicated_temperature_K"


@pytest.mark.parametrize("path,value",[
    (("utility_loop","mass_kg"),0.), (("utility_loop","heater_efficiency"),0.),
    (("utility_loop","heater_efficiency"),1.1), (("utility_loop","pump_loss_to_fluid_fraction"),-1.),
    (("utility_loop","pump_loss_to_fluid_fraction"),1.1), (("utility_loop","ua_ambient_W_K"),-1.),
    (("utility_loop","heater_max_power_W"),float("inf")), (("utility_loop","mass_kg"),float("nan")),
    (("utility_loop","initial_temperature_K"),400.), (("inputs","heater_power_request_W"),-1.),
    (("inputs","pump_speed_fraction"),1.1), (("inputs","pump_speed_fraction"),True),
    (("circuit","static_head_m"),1.), (("utility_loop","mass_kg"),1e308),
    (("utility_loop","heater_max_power_W"),1e308),
])
def test_invalid_loop_inputs_fail_before_integration(path,value):
    c=case()
    c[path[0]][path[1]]=value
    with pytest.raises(ValueError):
        validate_case(c)


@pytest.mark.parametrize("section,key",[("jacket","pump_heat_fraction"),("pump","speed_fraction"),
                                       ("inputs","utility_supply_temperature_K"),("utility_loop","cp_J_kg_K")])
def test_redundant_or_obsolete_fields_are_rejected(section,key):
    c=case()
    c[section][key]=1.
    with pytest.raises(ValueError):
        validate_case(c)


@pytest.mark.parametrize("changes",[{"heater_power_request_W":-1.},{"pump_speed_fraction":2.},
                                    {"utility_supply_temperature_K":310.}])
def test_invalid_event_changes_are_rejected(changes):
    c=case()
    c["events"]=[{"time_s":10.,"changes":changes}]
    with pytest.raises(ValueError):
        validate_case(c)


def test_cancelled_loop_returns_finite_initial_trajectory():
    c=case()
    result=simulate_dynamic_tank(c,cancel=lambda:True)
    assert result["summary"]["status"]=="cancelled"
    assert len(result["series"])==1
    assert result["series"][0]["utility_reservoir_temperature_K"]==333.15


def test_schema_validation_does_not_mutate_case():
    c=case()
    before=copy.deepcopy(c)
    validate_case(c)
    simulate_dynamic_tank(c)
    assert c==before


def test_modular_exchange_and_power_allocations():
    source,sink=advective_exchange(2.,4000.,330.,300.)
    assert source==-240000. and source+sink==0.
    assert advective_exchange(0.,4000.,330.,300.)==(-0.,0.)
    assert heater_power(2000.,1000.,.8)["heater_heat_W"]==800.
    assert pump_heat_to_liquid(100.,200.,0.)==100.
    assert pump_heat_to_liquid(100.,200.,1.)==200.
